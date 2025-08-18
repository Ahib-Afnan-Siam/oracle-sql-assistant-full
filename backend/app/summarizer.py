import json
import re
import logging
from app.data_utils import calculate_swing

import math
from typing import Sequence, Dict, Any, List, Optional, Generator
from app.ollama_llm import ask_analytical_model
from app.config import SUMMARY_MAX_ROWS, SUMMARY_CHAR_BUDGET, OLLAMA_ANALYTICAL_MODEL

logger = logging.getLogger(__name__)

# --- Sanitizers: remove tables/code from LLM text ----------------------------
_TABLE_BLOCK_RX = re.compile(
    r"(^|\n)(\s*\|.*\|\s*\n\s*\|(?:\s*:?-+:?\s*\|)+\s*\n(?:\s*\|.*\|\s*\n?)+)",
    re.MULTILINE,
)

def _strip_tables_and_code(text: str) -> str:
    """Remove markdown code fences and markdown tables from a string."""
    if not text:
        return text
    # code fences
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # markdown tables
    text = _TABLE_BLOCK_RX.sub("\n", text)
    return text.strip()

def _pipe_snapshot(columns: Sequence[str], rows: Sequence[Dict[str, Any]], 
                   max_rows: int, char_budget: int) -> str:
    """Build a compact pipe-delimited snapshot with a hard char budget."""
    if not columns:
        return ""
    header = " | ".join(map(str, columns))
    lines = [header]
    if not rows:
        return "\n".join(lines)

    # Head + tail sampling (keeps context from both ends)
    head_n = min(max_rows // 2, len(rows))
    tail_n = min(max_rows - head_n, max(0, len(rows) - head_n))
    sample = rows[:head_n] + (rows[-tail_n:] if tail_n else [])

    def clean(val: Any) -> str:
        s = "" if val is None else str(val)
        # keep single line to avoid prompt bloat
        return s.replace("\n", " ").replace("\r", " ").strip()

    for r in sample:
        lines.append(" | ".join(clean(r.get(c)) for c in columns))

    snap = "\n".join(lines)
    if len(snap) <= char_budget:
        return snap

    # If we exceeded, drop rows proportionally until we fit.
    # Never drop the header.
    keep = max(1, int(len(sample) * (char_budget / max(1, len(snap)))))
    keep = min(keep, len(sample))
    trimmed = [header] + lines[1:1+keep]
    return "\n".join(trimmed)

def summarize_with_mistral(
    user_query: str,
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    backend_summary: str,
    sql: Optional[str] = None,
    max_rows: int = SUMMARY_MAX_ROWS,
    char_budget: int = SUMMARY_CHAR_BUDGET,
) -> str:
    """
    Produce a human-friendly summary with Mistral using both:
    - backend_summary: stats from Python
    - a compact table snapshot: header + sampled rows
    """
    try:
        snapshot = _pipe_snapshot(columns, rows, max_rows=max_rows, char_budget=char_budget)

        prompt = f"""
You are a senior data analyst. Write a concise, business-ready summary that directly answers the user's EXACT question
using ONLY the provided DATA SNAPSHOT and BACKEND STATS. Never invent numbers.

OUTPUT RULES
- Start with a 1–2 sentence overview.
- Then 5–9 short bullets (≤ 20 words each).
- Do NOT include any tables (no Markdown/HTML tables) and do NOT use code fences.
- Include: totals/averages, top/bottom categories, notable swings/outliers, date coverage, and any data quality notes (nulls/row count).
- Use column names exactly as shown. Do not repeat the full table.
- If the question asks for a time window, respect it; otherwise do not assume one.
- If BACKEND STATS and snapshot conflict, prefer BACKEND STATS and note the discrepancy in one short bullet.
- If there are no rows, say so clearly.

USER QUESTION
{user_query}

SQL USED
{sql or '—'}

BACKEND STATS (from Python)
{backend_summary}

DATA SNAPSHOT (pipe-delimited: header then rows; up to {max_rows} rows)
{snapshot}
""".strip()

        # Call Mistral (via your existing wrapper)
        response = ask_analytical_model(prompt)
        cleaned = _strip_tables_and_code(response.strip() or backend_summary)
        return cleaned
    except Exception as e:
        logger.error(f"LLM summary failed, falling back. Reason: {e}")
        return backend_summary

def summarize_with_mistral_with_prompt(
    user_query: str,
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    backend_summary: str,
    sql: Optional[str] = None,
    max_rows: int = SUMMARY_MAX_ROWS,
    char_budget: int = SUMMARY_CHAR_BUDGET,
) -> tuple[str, str]:
    """
    Back-compat helper that returns (cleaned_summary_text, prompt).
    It builds the exact prompt sent to the analytical model.
    """
    try:
        snapshot = _pipe_snapshot(columns, rows, max_rows=max_rows, char_budget=char_budget)

        prompt = f"""
You are a senior data analyst. Write a concise, business-ready summary that directly answers the user's EXACT question
using ONLY the provided DATA SNAPSHOT and BACKEND STATS. Never invent numbers.

OUTPUT RULES
- Start with a 1–2 sentence overview.
- Then 5–9 short bullets (≤ 20 words each).
- Do NOT include any tables (no Markdown/HTML tables) and do NOT use code fences.
- Include: totals/averages, top/bottom categories, notable swings/outliers, date coverage, and any data quality notes (nulls/row count).
- Use column names exactly as shown. Do not repeat the full table.
- If the question asks for a time window, respect it; otherwise do not assume one.
- If BACKEND STATS and snapshot conflict, prefer BACKEND STATS and note the discrepancy in one short bullet.
- If there are no rows, say so clearly.

USER QUESTION
{user_query}

SQL USED
{sql or '—'}

BACKEND STATS (from Python)
{backend_summary}

DATA SNAPSHOT (pipe-delimited: header then rows; up to {max_rows} rows)
{snapshot}
""".strip()

        response = ask_analytical_model(prompt)
        cleaned = _strip_tables_and_code(response.strip() or backend_summary)
        return cleaned, prompt
    except Exception as e:
        logger.error(f"LLM summary failed, falling back. Reason: {e}")
        # On failure, still return a prompt string (minimal) so callers can log it
        fallback_prompt = f"FALLBACK SUMMARY for: {user_query}"
        return backend_summary, fallback_prompt


def extract_insights(response: str) -> List[str]:
    """
    Split summary into individual insights, handling various formats.
    Returns: List of insight strings
    """
    # Handle numbered lists with potential sub-bullets
    if re.search(r'\n\d+\.', response):
        # Split while preserving numbers
        insights = []
        current = []
        for line in response.splitlines():
            line = line.strip()
            if re.match(r'^\d+\.', line):
                if current:  # Save previous insight
                    insights.append("\n".join(current))
                    current = []
                current.append(line)
            elif line:  # Non-empty line
                current.append(line)
        if current:
            insights.append("\n".join(current))
        return insights

    # Try to split by common insight markers
    for delimiter in ["\n- ", "\n* ", "\n• "]:
        if delimiter in response:
            parts = response.split(delimiter)
            insights = [parts[0].strip()]
            insights.extend([delimiter.strip() + p.strip() for p in parts[1:]])
            return insights
    
    # Last resort: split by double newlines
    return [s.strip() for s in response.split('\n\n') if s.strip()]

def generate_dynamic_guidelines(user_query: str, header: List[str]) -> str:
    """
    Create context-aware guidelines based on query and columns
    """
    query = user_query.lower()
    guidelines = [
        "NEVER invent numbers not in data",
        "Refer to columns exactly as they appear in header",
        "ALWAYS address the user's EXACT query"
    ]
    
    # Pattern detection
    patterns = {
        r"\b(swing|variation|difference|range)\b": [
            "Calculate differences between max and min values",
            "Highlight largest variations",
            "Identify outliers in the data"
        ],
        r"\b(sum|total|amount|quantity)\b": [
            "Calculate totals where appropriate",
            "Aggregate values when possible",
            "Show cumulative figures"
        ],
        r"\b(month|date|time|year|period)\b": [
            "Filter results to specified time period",
            "Note temporal patterns",
            "Compare to previous periods"
        ],
        r"\b(summary|report|overview|insight)\b": [
            "Focus on key findings and patterns",
            "Highlight most important metrics",
            "Provide high-level conclusions"
        ],
        r"\b(compare|comparison|vs|versus)\b": [
            "Identify comparison targets from query",
            "Highlight differences between compared items",
            "Show relative performance"
        ],
        r"\b(manager|employee|staff|personnel)\b": [
            "Explain reporting relationships using IDs",
            "Note manager-employee connections",
            "Identify leadership structure"
        ],
        r"\b(region|area|territory|zone)\b": [
            "Group results by geographical terms",
            "Compare regional performance",
            "Note any regional patterns"
        ],
        r"\b(product|item|sku|inventory)\b": [
            "Focus on product attributes",
            "Note stock levels where available",
            "Compare product performance"
        ],
        r"\b(sales|revenue|profit|income)\b": [
            "Focus on financial metrics",
            "Calculate totals and averages",
            "Identify top performers"
        ],
        r"\b(production|output|yield|efficiency)\b": [
            "Analyze production metrics",
            "Note quality vs quantity tradeoffs",
            "Identify efficiency patterns"
        ]
    }
    
    # Add pattern-based guidelines
    for pattern, pattern_guides in patterns.items():
        if re.search(pattern, query):
            guidelines.extend(pattern_guides)
    
    # Column-based guidance
    col_guidelines = []
    if header:  # Add safety check for empty header
        for col in header:
            col_lower = col.lower()
            if any(term in col_lower for term in ["date", "time", "year", "month"]):
                col_guidelines.append(f"Note temporal patterns in {col}")
            if any(term in col_lower for term in ["amount", "total", "sum", "qty", "quantity"]):
                col_guidelines.append(f"Calculate min/max/sum for {col} where appropriate")
            if "id" in col_lower:
                col_guidelines.append(f"Use {col} for reference, not as quantitative value")
    
    if col_guidelines:
        guidelines.extend(col_guidelines)
    
    # Format as numbered list
    return "\n".join([f"{i+1}. {g}" for i, g in enumerate(guidelines)])

def stream_summary(user_query: str, data_snippet: str = "") -> Generator[str, None, None]:
    """
    Dynamic, domain-agnostic summary generator
    """
    try:
        logger.info(f"Starting summary for query: {user_query}")

        # --- local sanitizer: strip code fences and markdown tables -------------
        _table_block_rx = re.compile(
            r"(^|\n)(\s*\|.*\|\s*\n\s*\|(?:\s*:?-+:?\s*\|)+\s*\n(?:\s*\|.*\|\s*\n?)+)",
            re.MULTILINE,
        )

        def _strip_tables_and_code(text: str) -> str:
            if not text:
                return text
            # Remove fenced code blocks
            text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            # Remove Markdown tables
            text = _table_block_rx.sub("\n", text)
            return text.strip()
        # -----------------------------------------------------------------------

        # Extract header from data snippet
        lines = data_snippet.splitlines()
        header = []
        if lines:
            header = [col.strip() for col in lines[0].split("|") if col.strip()]

        # Generate dynamic guidelines
        guidelines = generate_dynamic_guidelines(user_query, header)

        # Add swing calculations when relevant
        swing_info = ""
        if "swing" in user_query.lower():
            try:
                # Parse data preview into structured format
                data_rows = []
                for i, row in enumerate(lines[1:]):
                    if not row.strip():
                        continue
                    values = [v.strip() for v in row.split("|")]
                    if len(values) == len(header):
                        data_rows.append(dict(zip(header, values)))

                # Calculate swings for relevant columns
                for col in header:
                    if any(term in col.lower() for term in ["qty", "amount", "pers", "percent", "value"]):
                        swing_val = calculate_swing(data_rows, col)
                        if swing_val > 0:  # Only show if valid calculation
                            swing_info += f"- Swing for {col}: {swing_val:.2f}\n"
            except Exception as e:
                logger.error(f"Swing calculation error: {str(e)}")
                swing_info = "- Could not calculate swings\n"

        full_input = f"""
You are a senior data analyst. Provide insights based on the user's EXACT query and the data preview.

USER'S EXACT QUERY: "{user_query}"

DATA PREVIEW (first row is header):
{data_snippet}

{swing_info if swing_info else ""}

ANALYSIS GUIDELINES:
{guidelines}

INSTRUCTIONS:
- Respond in clear, concise bullet points
- Do NOT include any tables (no Markdown/HTML tables) and do NOT use code fences
- Calculate metrics when appropriate (min, max, avg, differences)
- Highlight key patterns and outliers
- Never invent data not present in the preview
- Focus exclusively on addressing the user's exact query
- Use professional but accessible language
- Admit when information is unavailable
""".strip()

        logger.debug(f"Summary prompt: {full_input[:500]}...")  # Truncated for logging

        yield json.dumps({
            "stage": "summary_start",
            "prompt": full_input,        # <-- exact prompt string sent to LLM
            "snapshot": data_snippet     # <-- helpful for storage too
        })

        # Initial phase: Generating summary
        yield json.dumps({"phase": "Generating summary..."})

        # Get summary from analytical model
        response = ask_analytical_model(full_input)
        logger.info(f"Analytical model response: {response[:500]}...")  # Log first 500 chars

        # Sanitize: remove any tables and code blocks the model might still emit
        response = _strip_tables_and_code(response)

        # Phase: Processing summary
        yield json.dumps({"phase": "Processing summary..."})

        # Extract insights
        insights = extract_insights(response)
        logger.info(f"Extracted {len(insights)} insights")

        # Phase: Sending insights
        yield json.dumps({"phase": "Sending insights..."})

        # Yield each insight
        for s in insights:
            yield json.dumps({"summary": s})

        # Final phase: Summary complete
        yield json.dumps({"phase": "Summary complete"})

    except Exception as e:
        logger.error(f"Summary generation failed: {str(e)}")
        yield json.dumps({"error": f"Summary generation failed: {str(e)}"})
