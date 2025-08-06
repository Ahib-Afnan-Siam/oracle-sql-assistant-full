import json
import re
import logging
from typing import List, Generator
from app.ollama_llm import ask_analytical_model
from app.config import OLLAMA_ANALYTICAL_MODEL
from app.data_utils import calculate_swing

logger = logging.getLogger(__name__)

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

def stream_summary(user_query: str, data_snippet: str) -> Generator[str, None, None]:
    """
    Dynamic, domain-agnostic summary generator
    """
    try:
        logger.info(f"Starting summary for query: {user_query}")
        
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
- Calculate metrics when appropriate (min, max, avg, differences)
- Highlight key patterns and outliers
- Never invent data not present in the preview
- Focus exclusively on addressing the user's exact query
- Use professional but accessible language
- Admit when information is unavailable
""".strip()

        logger.debug(f"Summary prompt: {full_input[:500]}...")  # Truncated for logging

        # Initial phase: Generating summary
        yield json.dumps({"phase": "Generating summary..."})
        
        # Get summary from analytical model
        response = ask_analytical_model(full_input)
        logger.info(f"Analytical model response: {response[:500]}...")  # Log first 500 chars
        
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