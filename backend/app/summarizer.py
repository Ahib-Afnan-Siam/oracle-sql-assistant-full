import os
import re
import json
import logging
from typing import Sequence, Dict, Any, List, Optional, Tuple
from decimal import Decimal

from app.ollama_llm import ask_analytical_model
from app.config import SUMMARY_MAX_ROWS, SUMMARY_CHAR_BUDGET

logger = logging.getLogger(__name__)

# -------------------------
# Enhanced Domain-Specific Patterns (Based on User Query Analysis)
# -------------------------

# Production-specific metric patterns from user queries
PRODUCTION_METRICS = {
    'production': [r'production.*qty', r'prod.*qty', r'total.*production'],
    'defect': [r'defect.*qty', r'total.*defects?', r'rejection.*qty'],
    'efficiency': [r'dhu', r'efficiency.*rate', r'eff.*rate']
}

# Company patterns from user queries
COMPANY_PATTERNS = {
    'CAL': ['cal', 'chorka'], 'WINNER': ['winner'], 'BIP': ['bip']
}

# Enhanced query intent patterns
INTENT_PATTERNS = {
    'floor_production_summary': [r'floor.*wise.*production.*summary', r'show.*floor.*production'],
    'defect_analysis': [r'defect.*qty.*floor', r'max.*defect.*qty', r'total.*defect.*qty'],
    'employee_lookup': [r'who\s+is\s+\w+', r'salary.*president'],
    'ranking_query': [
        r'top.*\d+.*defect', r'max.*defect.*floor', r'biggest.*production',
        r'which.*floor.*produced.*most', r'which.*floor.*most.*production',
        r'most.*production.*floor', r'floor.*produced.*most',
        r'maximum.*production', r'highest.*production'
    ]
}

# -------------------------
# Configuration
# -------------------------
MAX_BULLETS = int(os.getenv("SUMMARY_BULLETS", "6"))
DIRECT_ANSWER_ENABLED = os.getenv("SUMMARY_DIRECT_ANSWER", "1") == "1"
ALLOW_LLM_FALLBACK = os.getenv("SUMMARY_ALLOW_LLM_FALLBACK", "0") == "1"
ENTITY_MAX_RESULTS = int(os.getenv("SUMMARY_ENTITY_MAX_RESULTS", "6"))

# -------------------------
# Enhanced Functions
# -------------------------

def classify_query_intent(user_query: str) -> str:
    """Enhanced intent classification based on user patterns."""
    query_lower = user_query.lower()
    
    for intent, patterns in INTENT_PATTERNS.items():
        if any(re.search(pattern, query_lower) for pattern in patterns):
            return intent
    
    if any(word in query_lower for word in ['production', 'defect', 'floor']):
        return 'production_data'
    elif any(word in query_lower for word in ['employee', 'salary', 'president']):
        return 'employee_data'
    return 'general'

def extract_production_context(user_query: str, columns: List[str]) -> Dict:
    """Extract production-specific context."""
    context = {'companies': [], 'metrics': [], 'intent': classify_query_intent(user_query)}
    
    query_lower = user_query.lower()
    
    # Extract companies
    for company, variations in COMPANY_PATTERNS.items():
        if any(var in query_lower for var in variations):
            context['companies'].append(company)
    
    # Identify relevant metrics
    for col in columns:
        col_lower = col.lower()
        for metric_type, patterns in PRODUCTION_METRICS.items():
            if any(re.search(pattern, col_lower) for pattern in patterns):
                context['metrics'].append({'column': col, 'type': metric_type})
    
    return context

def _find_column(columns: List[str], candidates: List[str]) -> Optional[str]:
    """Find the best matching column name."""
    columns_lower = [col.lower() for col in columns]
    for candidate in candidates:
        for i, col_lower in enumerate(columns_lower):
            if candidate in col_lower:
                return columns[i]
    return None

def _is_numeric(value) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)

def _format_number(value) -> str:
    """Format numbers consistently."""
    if isinstance(value, Decimal):
        value = float(value)
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip('0').rstrip('.')

# -------------------------
# Enhanced Renderers
# -------------------------

def _render_floor_production_summary(user_query: str, columns: List[str], rows: List[Dict], context: Dict) -> str:
    """Enhanced floor-wise production summary."""
    if not rows:
        return "No production data found."
    
    floor_col = _find_column(columns, ['floor_name', 'floor', 'line_name'])
    prod_col = _find_column(columns, ['production_qty', 'prod_qty', 'total_production'])
    defect_col = _find_column(columns, ['defect_qty', 'total_defects', 'rejection_qty'])
    
    if not floor_col:
        return "Floor information not found."
    
    # Group by floor
    floor_data = {}
    for row in rows:
        floor = row.get(floor_col, 'Unknown')
        if floor not in floor_data:
            floor_data[floor] = {'production': 0, 'defects': 0}
        
        if prod_col and _is_numeric(row.get(prod_col)):
            floor_data[floor]['production'] += float(row[prod_col])
        if defect_col and _is_numeric(row.get(defect_col)):
            floor_data[floor]['defects'] += float(row[defect_col])
    
    # Format summary
    summary_parts = []
    total_production = sum(data['production'] for data in floor_data.values())
    total_defects = sum(data['defects'] for data in floor_data.values())
    
    summary_parts.append(f"Total Production: {_format_number(total_production)} pieces")
    if total_defects > 0:
        summary_parts.append(f"Total Defects: {_format_number(total_defects)} pieces")
        if total_production > 0:
            dhu = (total_defects / total_production) * 100
            summary_parts.append(f"Overall DHU: {dhu:.2f}%")
    
    # Top performer
    if len(floor_data) > 1:
        top_floor = max(floor_data.items(), key=lambda x: x[1]['production'])
        summary_parts.append(f"Top Floor: {top_floor[0]} ({_format_number(top_floor[1]['production'])} pieces)")
    
    return " • ".join(summary_parts)

def _render_defect_analysis(user_query: str, columns: List[str], rows: List[Dict]) -> str:
    """Enhanced defect analysis."""
    if not rows:
        return "No defect data found."
    
    floor_col = _find_column(columns, ['floor_name', 'floor', 'line_name'])
    defect_col = _find_column(columns, ['defect_qty', 'total_defects', 'rejection_qty'])
    
    if not defect_col:
        return "Defect information not found."
    
    defect_data = []
    for row in rows:
        if _is_numeric(row.get(defect_col)):
            floor = row.get(floor_col, 'Unknown') if floor_col else 'Unknown'
            defects = float(row[defect_col])
            defect_data.append({'floor': floor, 'defects': defects})
    
    if not defect_data:
        return "No valid defect data found."
    
    total_defects = sum(item['defects'] for item in defect_data)
    max_defect_entry = max(defect_data, key=lambda x: x['defects'])
    
    summary_parts = []
    summary_parts.append(f"Total Defects: {_format_number(total_defects)}")
    summary_parts.append(f"Max Defects: {max_defect_entry['floor']} ({_format_number(max_defect_entry['defects'])})")
    
    return " • ".join(summary_parts)

def _render_employee_lookup(user_query: str, columns: List[str], rows: List[Dict]) -> str:
    """Enhanced employee lookup."""
    if not rows:
        return "No employee found."
    
    if len(rows) == 1:
        row = rows[0]
        name_col = _find_column(columns, ['ename', 'name', 'employee_name'])
        job_col = _find_column(columns, ['job', 'position', 'title'])
        sal_col = _find_column(columns, ['sal', 'salary', 'pay'])
        
        parts = []
        if name_col and row.get(name_col):
            parts.append(f"Name: {row[name_col]}")
        if job_col and row.get(job_col):
            parts.append(f"Position: {row[job_col]}")
        if sal_col and _is_numeric(row.get(sal_col)):
            parts.append(f"Salary: ${_format_number(row[sal_col])}")
        
        return " • ".join(parts) if parts else "Employee information found."
    
    return f"Found {len(rows)} employees matching your criteria."

# -------------------------
# Original Functions (preserved for compatibility)
# -------------------------

def _strip_tables_and_code(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return text.strip()

def _is_num(v): 
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)

def _fmt_num(v):
    if isinstance(v, Decimal): 
        v = float(v)
    s = f"{v:,.2f}"
    return s.rstrip("0").rstrip(".")

def _pretty(name: str) -> str:
    return name.replace('_', ' ').title()

def _pick_metric_columns(columns: Sequence[str], rows: Sequence[Dict[str, Any]], user_query: str = "") -> List[str]:
    if not columns or not rows: 
        return []
    
    nums = []
    for c in columns:
        sample = next((r.get(c) for r in rows if c in r and r.get(c) is not None), None)
        if sample is not None and _is_num(sample):
            # Enhanced scoring for production metrics
            score = 0
            cl = c.lower()
            if 'prod' in cl or 'output' in cl or cl.endswith('qty'): 
                score -= 4
            if re.search(r'(defect|rej)', cl): 
                score -= 3
            if re.search(r'(dhu|eff)', cl): 
                score -= 2
            nums.append((score, c))
    
    nums.sort(key=lambda x: (x[0], x[1].lower()))
    return [c for _, c in nums]

def _pick_label_columns(columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> List[str]:
    if not columns or not rows: 
        return []
    
    nonnum = []
    for c in columns:
        sample = next((r.get(c) for r in rows if c in r and r.get(c) is not None), None)
        if sample is not None and not _is_num(sample):
            nonnum.append(c)
    
    # Prioritize floor, name, dept columns
    nonnum.sort(key=lambda c: (0 if re.search(r'(FLOOR|NAME|DEPT)', c, re.I) else 1, c.lower()))
    return nonnum

# -------------------------
# Main summarization function
# -------------------------

def summarize_with_mistral(
    user_query: str,
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    backend_summary: str,
    sql: Optional[str] = None,
    max_rows: int = SUMMARY_MAX_ROWS,
    char_budget: int = SUMMARY_CHAR_BUDGET,
) -> str:
    """Enhanced summarizer optimized for production domain."""
    try:
        if not rows:
            return "No data found matching your criteria."
        
        # Extract production context
        context = extract_production_context(user_query, list(columns))
        intent = context['intent']
        
        # Route to enhanced renderers based on intent
        if intent == 'floor_production_summary':
            return _render_floor_production_summary(user_query, list(columns), rows, context)
        elif intent == 'defect_analysis':
            return _render_defect_analysis(user_query, list(columns), rows)
        elif intent == 'employee_lookup':
            return _render_employee_lookup(user_query, list(columns), rows)
        elif intent == 'ranking_query':
            # Handle ranking queries
            metric_cols = _pick_metric_columns(columns, rows, user_query)
            label_cols = _pick_label_columns(columns, rows)
            
            if metric_cols and label_cols:
                # For single result ranking queries (which/most/max)
                if len(rows) == 1 and any(word in user_query.lower() for word in ['which', 'most', 'max', 'highest', 'biggest']):
                    row = rows[0]
                    floor_name = row.get(label_cols[0], 'Unknown')
                    production_value = row.get(metric_cols[0], 0)
                    metric_name = metric_cols[0].replace('_', ' ').title()
                    return f"{floor_name} produced the most with {_fmt_num(production_value)} {metric_name.lower()}"
                
                # Extract top N from query
                top_n = 5
                top_match = re.search(r'top\s*(?:list\s*)?(\d+)', user_query.lower())
                if top_match:
                    top_n = int(top_match.group(1))
                elif 'just one row' in user_query.lower() or 'max' in user_query.lower():
                    top_n = 1
                
                # Sort and format top N
                valid_rows = [r for r in rows if _is_num(r.get(metric_cols[0])) and r.get(label_cols[0])]
                valid_rows.sort(key=lambda r: float(r[metric_cols[0]]), reverse=True)
                top_items = valid_rows[:top_n]
                
                metric_name = metric_cols[0].replace('_', ' ').title()
                ranking_items = []
                for i, item in enumerate(top_items, 1):
                    ranking_items.append(f"{i}) {item[label_cols[0]]} — {_fmt_num(item[metric_cols[0]])}")
                
                return f"Top {len(top_items)} by {metric_name}: " + "; ".join(ranking_items)
        
        # Fallback to enhanced general production summary
        metric_cols = _pick_metric_columns(columns, rows, user_query)
        label_cols = _pick_label_columns(columns, rows)
        
        if metric_cols and label_cols:
            # Group summary with totals
            summary_parts = [f"Found {len(rows)} records"]
            
            for col in metric_cols[:3]:  # Top 3 metrics
                total = sum(float(r[col]) for r in rows if _is_num(r.get(col)))
                if total > 0:
                    metric_name = col.replace('_', ' ').title()
                    summary_parts.append(f"{metric_name}: {_fmt_num(total)}")
            
            # Add company context if available
            if context['companies']:
                summary_parts.append(f"Company: {', '.join(context['companies'])}")
            
            return " • ".join(summary_parts)
        
        return f"Found {len(rows)} records matching your query."
        
    except Exception as e:
        logger.error(f"Enhanced summarizer error: {e}")
        return backend_summary or f"Found {len(rows)} records."

# Backward compatibility
def summarize_results(rows: list, user_query: str, sql: str = None) -> str:
    """Compatibility wrapper for existing code."""
    if not rows:
        return "No data found."
    
    columns = list(rows[0].keys()) if rows else []
    return summarize_with_mistral(user_query, columns, rows, "", sql)