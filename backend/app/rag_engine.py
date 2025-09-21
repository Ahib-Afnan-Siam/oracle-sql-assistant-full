# app/rag_engine.py
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime as _dt
import os
from decimal import Decimal
from app.query_engine import _MONTH_ALIASES
from app.vector_store_chroma import hybrid_schema_value_search
from app.db_connector import connect_to_source
from app.ollama_llm import ask_sql_planner
from app.config import SUMMARY_ENGINE, SUMMARY_MAX_ROWS, SUMMARY_CHAR_BUDGET, SUMMARIZATION_CONFIG
from app.query_engine import _get_table_colmeta
from functools import lru_cache
from app.summarizer import summarize_results_async

# Add debug logging
logger = logging.getLogger(__name__)
logger.info("Loading RAG engine with new summarizer integration")

# Reuse the deterministic SQL toolbox + summarizer you already have
from app.query_engine import (
    build_sql_from_plan,
    normalize_dates,
    enforce_wide_projection_for_generic,
    value_aware_text_filter,
    enforce_predicate_type_compat,
    is_valid_sql,
    run_sql,
    determine_display_mode,
    widen_results_if_needed,
    summarize_results,
    ensure_label_filter,
    extract_explicit_date_range,
    extract_relative_date_range,
    # Entity-lookup fast path (importing "private" helpers is acceptable inside the app)
    _is_entity_lookup,
    _needle_from_question,
    _candidate_columns,
    _list_name_like_columns,
    _merge_candidates,
    _quick_value_probe,
    _is_banned_table,
    _filter_banned_tables,
    _extract_id_lookup,
    _list_id_like_columns,
    _set_case_insensitive_session,
)

from app.summarizer import summarize_with_mistral, _fallback_summarization

# Add this import to ensure we're using the API-based summarizer
from app.summarizer import summarize_results


from app.query_classifier import has_visualization_intent

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    from app.hybrid_processor import HybridProcessor
    from app.config import HYBRID_ENABLED, OPENROUTER_ENABLED, COLLECT_TRAINING_DATA
    HYBRID_PROCESSING_AVAILABLE = HYBRID_ENABLED and OPENROUTER_ENABLED
    if HYBRID_PROCESSING_AVAILABLE:
        logger.info("[RAG] Hybrid AI processing system enabled")
        # Test hybrid processor initialization
        try:
            _test_processor = HybridProcessor()
            logger.info("[RAG] Hybrid processor initialized successfully")
        except Exception as test_error:
            HYBRID_PROCESSING_AVAILABLE = False
            logger.error(f"[RAG] Hybrid processor initialization failed: {test_error}")
    else:
        logger.info("[RAG] Hybrid processing disabled in configuration")
        
    # Import training data collection system if available
    if COLLECT_TRAINING_DATA:
        try:
            from app.hybrid_data_recorder import hybrid_data_recorder
            from app.query_classifier import QueryClassifier
            logger.info("[RAG] Training data collection system enabled")
        except ImportError as e:
            logger.warning(f"[RAG] Training data collection dependencies not available: {e}")
            COLLECT_TRAINING_DATA = False
    
except ImportError as e:
    HYBRID_PROCESSING_AVAILABLE = False
    logger.warning(f"[RAG] Hybrid processing dependencies not available: {e}")
except Exception as e:
    HYBRID_PROCESSING_AVAILABLE = False
    logger.error(f"[RAG] Hybrid processing setup failed: {e}")

# Local parser for TO_CHAR dims used in validation (aligns with query_engine)
_TOCHAR_WHITELIST = {"MON-YY", "MON-YYYY", "YYYY-MM", "YYYY", "DD-MON-YYYY"}
_TOCHAR_RX = re.compile(
    r"""(?is)^\s*TO_CHAR\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*'([A-Za-z\-]+)'\s*\)\s*$"""
)

DYNAMIC_ENTITY_PATTERNS = {
    'company_variations': {
        'CAL': ['cal', 'chorka', 'chorka apparel', 'chorka apparel limited'],
        'WINNER': ['winner', 'winner bip'],
        'BIP': ['bip']
    },
    'floor_patterns': [
        r'(?i)sewing\s+(?:floor-)?(\d+[a-z]?)',
        r'(?i)(?:cal|winner)\s+sewing[-\s]f?(\d+)',
        r'(?i)floor[-\s](\d+[a-z]?)'
    ],
    'date_patterns': [
        r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b',
        r'\b\d{1,2}[-\s][a-z]{3}[-\s]\d{2,4}\b',
        r'\b[a-z]{3}[-\s]\d{2,4}\b',
        r'\bthis\s+month\b',
        r'\blast\s+\d+\s+days?\b',
        r'\blast\s+day\b',
        r'\blast\s+week\b',
        r'\blast\s+month\b'
    ],
    'ordering_patterns': [
        r'\basc\b',
        r'\bascending\b',
        r'\bdesc\b',
        r'\bdescending\b'
    ],
    'lowest_patterns': [
        r'\blowest\b',
        r'\bmin\b',
        r'\bsmallest\b',
        r'\bleast\b'
    ],
    'aggregation_patterns': [
        r'\baverage\b',
        r'\bavarage\b',  # Typo handling
        r'\bavg\b',
        r'\bsum\b',
        r'\btotal\b'
    ]
}

INTENT_CLASSIFICATION_PATTERNS = {
    'production_summary': {
        'keywords': ['floor-wise', 'production', 'summary'],
        'variations': ['floor wise', 'floorwise', 'production summary'],
        'table_preference': ['T_PROD_DAILY', 'T_PROD']
    },
    'defect_analysis': {
        'keywords': ['defect', 'max', 'big', 'top'],
        'aggregations': ['max', 'sum', 'top n'],
        'table_preference': ['T_PROD_DAILY']
    },
    'employee_lookup': {
        'keywords': ['president', 'salary', 'email', 'who is'],
        'entity_types': ['person_name', 'job_title'],
        'table_preference': ['EMP', 'T_USERS']
    },
    'efficiency_query': {
        'keywords': ['efficiency', 'floor ef', 'dhu'],
        'metrics': ['FLOOR_EF', 'DHU'],
        'table_preference': ['T_PROD_DAILY']
    },
    'tna_task_query': {
        'keywords': ['task', 'tna', 'job', 'po', 'buyer', 'style', 'ctl', 'information'],
        'variations': ['task status', 'job information', 'po status'],
        'table_preference': ['T_TNA_STATUS']
    },
    'trend_analysis': {
        'keywords': ['trend', 'analysis', 'over time', 'monthly', 'weekly'],
        'variations': ['trend analysis', 'time series', 'historical'],
        'table_preference': ['T_PROD_DAILY']
    },
    'ranking_query': {
        'keywords': ['lowest', 'highest', 'top', 'bottom', 'rank'],
        'variations': ['rank by', 'order by', 'sort by'],
        'table_preference': ['T_PROD_DAILY']
    }
}

# Prefer daily-granularity tables when the question mentions a specific day
_DAILY_HINT_RX = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|"          # 2025-08-21
    r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|"  # 21/08/25 or 21-08-2025
    r"\b\d{2}-[A-Za-z]{3}-\d{2,4}\b|"  # 21-AUG-25 / 21-AUG-2025
    r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}\b|" # 21 Aug 2025
    r"\bday\b",
    re.IGNORECASE,
)

def _parse_relative_date_expression(expression: str) -> Optional[Dict[str, Any]]:
    """
    Parse relative date expressions like 'last day', 'last 7 days', 'last week' into 
    appropriate date filters for Oracle SQL.
    """
    expression = expression.lower().strip()
    
    # Handle "last day" - find the most recent date with data
    if expression in ['last day', 'yesterday']:
        return {
            'type': 'max_date',
            'table': 'T_PROD_DAILY',
            'date_column': 'PROD_DATE'
        }
    
    # Handle "last week" - previous 7 days including today
    if expression == 'last week':
        return {
            'type': 'range',
            'start': "TRUNC(SYSDATE) - 7",
            'end': "TRUNC(SYSDATE) - 1",
            'inclusive': True
        }
    
    # Handle "last N days" patterns
    days_match = re.search(r'last\s+(\d+)\s+days?', expression)
    if days_match:
        days = int(days_match.group(1))
        return {
            'type': 'range',
            'start': f"TRUNC(SYSDATE) - {days}",
            'end': "TRUNC(SYSDATE) - 1",
            'inclusive': True
        }
    
    # Handle "last month"
    if expression == 'last month':
        return {
            'type': 'range',
            'start': "TRUNC(SYSDATE, 'MM') - INTERVAL '1' MONTH",
            'end': "TRUNC(SYSDATE, 'MM') - INTERVAL '1' DAY",
            'inclusive': True
        }
    
    return None

def _build_date_filter_from_relative_expression(expression: str, date_column: str = 'PROD_DATE') -> Optional[str]:
    """
    Build an appropriate Oracle SQL WHERE clause for relative date expressions.
    """
    parsed = _parse_relative_date_expression(expression)
    if not parsed:
        return None
    
    if parsed['type'] == 'max_date':
        return f"{date_column} = (SELECT MAX({date_column}) FROM {parsed['table']})"
    
    if parsed['type'] == 'range':
        if parsed['inclusive']:
            return f"{date_column} BETWEEN {parsed['start']} AND {parsed['end']}"
        else:
            return f"{date_column} > {parsed['start']} AND {date_column} <= {parsed['end']}"
    
    return None

def _bias_tables_for_day(tables: List[str], user_query: str) -> List[str]:
    if not tables:
        return tables
    if not _DAILY_HINT_RX.search(user_query or ""):
        return tables

    def score(t: str) -> tuple[int, str]:
        T = t.upper()
        # very simple daily-ish signal: *_DAILY, *_DLY, *_DAY
        dailyish = bool(re.search(r"(?:^|_)(DAILY|DLY|DAY)(?:$|_)", T))
        return (0 if dailyish else 1, T)   # daily tables first, then alpha for determinism

    return sorted(tables, key=score)

# ---- Multi-metric, schema-driven selection -----------------------------------
_METRIC_WORDS_RX = re.compile(
    r"\b(qty|quantity|pcs?|pieces?|rate|percent|pct|eff|efficiency|score|dhu|"
    r"defect|reject(?:ion|ed)?|rework|alter|stain|dirty|spot|hole|skip)\b", re.I
)

def _extract_metric_phrases(uq: str, max_parts: int = 8) -> list[str]:
    parts = re.split(r"\b(?:and|&|,|plus|with|as well as)\b", uq or "", flags=re.I)
    out = []
    for p in parts:
        p = p.strip()
        if p and _METRIC_WORDS_RX.search(p):
            out.append(p)
    return out[:max_parts]

def _score_metric_col(col: str, phrase: str) -> int:
    c = col.lower(); p = phrase.lower()
    score = 0
    # token overlap
    for t in re.findall(r"[a-z0-9]+", p):
        if t and t in c: score += 3
    # universal boosts
    if "qty" in p or "pcs" in p or "piece" in p:
        if "qty" in c or "pcs" in c: score += 5
    if "eff" in p or "efficiency" in p or "rate" in p or "percent" in p or "pct" in p:
        if "eff" in c or "rate" in c or "pct" in c or "percent" in c: score += 5
    if "dhu" in p and "dhu" in c: score += 8
    if ("defect" in p or "reject" in p) and ("defect" in c or "rej" in c): score += 4
    if ("stain" in p or "dirty" in p) and ("stain" in c or "dirty" in c): score += 6
    # Handle "average" and "avarage" typos
    if ("average" in p or "avarage" in p) and ("avg" in c): score += 7
    return score

def _choose_metrics_for_phrases(phrases: list[str], table: str, options: dict,
                                max_metrics: int = 8) -> list[str]:
    numeric_cols = list(options.get("numeric_columns", {}).get(table, []) or [])
    chosen: list[str] = []
    for ph in phrases:
        best = None; best_s = -1
        for col in numeric_cols:
            s = _score_metric_col(col, ph)
            if s > best_s:
                best, best_s = col, s
        if best_s > 0 and best not in chosen:
            chosen.append(best)
    return chosen[:max_metrics]

def _augment_plan_with_metrics(uq: str, plan: dict, options: dict) -> dict:
    if not isinstance(plan, dict):
        return plan

    is_two_table = bool(plan.get("tables") and plan.get("joins"))
    base = plan.get("table") if not is_two_table else (plan.get("tables") or [None])[0]
    if not base:
        return plan

    phrases = _extract_metric_phrases(uq)
    if not phrases:
        return plan

    picks = _choose_metrics_for_phrases(phrases, base, options)

    # Only consider switching tables on SINGLE-TABLE plans
    if not picks and not is_two_table:
        best = (0, None, [])
        for t in options.get("tables", []):
            cols = _choose_metrics_for_phrases(phrases, t, options)
            if len(cols) > best[0]:
                best = (len(cols), t, cols)
        if best[1]:
            plan["table"] = best[1]
            picks = best[2]

    if picks:
        plan["metrics"] = list(dict.fromkeys((plan.get("metrics") or []) + picks))[:8]
        if "limit" in plan and not re.search(r"\b(top\s*\d+|top|max|min|highest|lowest|first|last)\b", uq or "", re.I):
            plan.pop("limit", None)

    # Add ordering information if present
    entities = dynamic_entity_recognition(uq)
    if entities.get('ordering') or entities.get('extremes'):
        # Initialize order_by if not present
        if "order_by" not in plan:
            plan["order_by"] = []
        
        # Determine ordering direction
        direction = "DESC"  # Default to DESC
        
        # Check for explicit ordering direction
        if entities.get('ordering'):
            ordering = entities['ordering'][0].upper()
            if ordering in ['ASC', 'ASCENDING']:
                direction = "ASC"
            elif ordering in ['DESC', 'DESCENDING']:
                direction = "DESC"
        
        # If we have extremes like 'lowest', adjust direction
        if entities.get('extremes'):
            extremes = [e.upper() for e in entities['extremes']]
            if any(e in ['LOWEST', 'MIN', 'SMALLEST', 'LEAST'] for e in extremes):
                direction = "ASC"
            elif any(e in ['HIGHEST', 'MAX', 'BIGGEST', 'MOST'] for e in extremes):
                direction = "DESC"
        
        # Add ordering to plan if we have metrics
        if picks and plan.get("order_by") is not None:
            # Use the first metric for ordering if not already specified
            if not plan["order_by"]:
                plan["order_by"].append({"key": picks[0], "dir": direction})
    
    # Handle relative dates
    if entities.get('relative_dates'):
        # Import the date filter function from query_engine
        from app.query_engine import _build_date_filter_from_relative_expression
        
        # Get the date column for this table
        date_col = plan.get("date_col", "PROD_DATE")  # Default to PROD_DATE
        
        # Build date filter for the first relative date expression found
        if entities['relative_dates']:
            rel_date_expr = entities['relative_dates'][0]
            date_filter = _build_date_filter_from_relative_expression(rel_date_expr, date_col)
            if date_filter:
                # Add to filters if not already present
                if "filters" not in plan:
                    plan["filters"] = []
                plan["filters"].append(date_filter)

    return plan

def dynamic_entity_recognition(user_query: str) -> Dict[str, Any]:
    """Enhanced entity recognition with pattern matching"""
    
    entities = {
        'companies': [],
        'floors': [],
        'dates': [],
        'ctl_codes': [],
        'aggregations': [],
        'metrics': [],
        'ordering': None,  # New field for ordering direction
        'extremes': [],  # New field for min/max indicators
        'relative_dates': []
    }
    
    query_lower = user_query.lower()
    
    # Company recognition
    for company, variations in DYNAMIC_ENTITY_PATTERNS['company_variations'].items():
        if any(var in query_lower for var in variations):
            entities['companies'].append(company)
    
    # Floor pattern recognition
    for pattern in DYNAMIC_ENTITY_PATTERNS['floor_patterns']:
        matches = re.finditer(pattern, user_query)
        for match in matches:
            entities['floors'].append(match.group(0))
    
    # Date pattern recognition
    for pattern in DYNAMIC_ENTITY_PATTERNS['date_patterns']:
        matches = re.findall(pattern, user_query, re.IGNORECASE)
        entities['dates'].extend(matches)
    
    # Special handling for relative date expressions
    relative_date_patterns = [
        r'\blast\s+day\b',
        r'\blast\s+week\b',
        r'\blast\s+month\b',
        r'\blast\s+\d+\s+days?\b',
        r'\byesterday\b'
    ]
    
    for pattern in relative_date_patterns:
        matches = re.findall(pattern, user_query, re.IGNORECASE)
        entities['relative_dates'].extend(matches)
    
    # CTL code recognition
    ctl_matches = re.finditer(r'\bCTL-\d{2}-\d{5,6}\b', user_query)
    for match in ctl_matches:
        entities['ctl_codes'].append(match.group(0))
    
    # Aggregation detection
    agg_patterns = ['max', 'min', 'sum', 'total', 'avg', 'top', 'big', 'maximum']
    for agg in agg_patterns:
        if agg in query_lower:
            entities['aggregations'].append(agg)
    
    # Metric detection
    metric_patterns = ['production', 'defect', 'efficiency', 'dhu', 'salary']
    for metric in metric_patterns:
        if metric in query_lower:
            entities['metrics'].append(metric)
    
    # Ordering direction detection
    if re.search(r'\basc\b|\bascending\b', query_lower):
        entities['ordering'] = 'ASC'
    elif re.search(r'\bdesc\b|\bdescending\b', query_lower):
        entities['ordering'] = 'DESC'
    
    # Extreme value detection (min/max)
    if re.search(r'\blowest\b|\bmin\b|\bsmallest\b|\bleast\b', query_lower):
        entities['extremes'].append('min')
    if re.search(r'\bhighest\b|\bmax\b|\bbiggest\b|\btop\b|\bmost\b', query_lower):
        entities['extremes'].append('max')
    
    return entities

def enhanced_intent_classification(user_query: str, entities: Dict) -> Dict[str, Any]:
    """Enhanced intent classification based on patterns and entities"""
    
    query_lower = user_query.lower()
    intent_scores = {}
    
    # Check for CTL codes first - this should be high priority
    if entities.get('ctl_codes'):
        intent_scores['tna_task_query'] = 0.8  # High score for CTL codes
    
    # Score each intent based on patterns
    for intent, config in INTENT_CLASSIFICATION_PATTERNS.items():
        score = intent_scores.get(intent, 0)  # Keep existing CTL score
        
        # Keyword matching
        for keyword in config['keywords']:
            if keyword in query_lower:
                score += 0.3
        
        # Variation matching
        for variation in config.get('variations', []):
            if variation in query_lower:
                score += 0.2
        
        # Entity alignment
        if intent == 'production_summary' and entities.get('companies'):
            score += 0.2
        elif intent == 'defect_analysis' and entities.get('aggregations'):
            score += 0.3
        elif intent == 'employee_lookup' and any(word in query_lower for word in ['president', 'salary', 'email']):
            score += 0.4
        
        intent_scores[intent] = score
    
    # Select best intent
    best_intent = max(intent_scores.items(), key=lambda x: x[1])
    
    return {
        'intent': best_intent[0] if best_intent[1] > 0.3 else 'general',
        'confidence': best_intent[1],
        'all_scores': intent_scores
    }

# app/rag_engine.py (add near other helpers)
_DAILY_NAME_RX = re.compile(r'(?:^|_)(DAILY|DLY|DAY)(?:$|_)', re.I)

# --- T_PROD vs T_PROD_DAILY cutoff rule (only for source_db_1) ----------------
_CUTOFF_DT = _dt(2025, 1, 15)
_METRIC_HINT_RX = re.compile(
    r"\b(defect|rej(?:ect|ection|n)?|prod(?:uction)?(?:\s*qty)?|production|qty|pieces?|pcs?|output)\b",
    re.I,
)

# Minimal date parsing helpers used to detect the asked window
_MON_ABBR = {m: i+1 for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
)}

def _parse_day_token(s: str) -> Optional[_dt]:
    s = s.strip()
    # 2025-08-20
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return _dt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # 20-AUG-2025 or 20-AUG-25
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2,4})$", s)
    if m:
        d, mon3, y = int(m.group(1)), m.group(2).upper(), int(m.group(3))
        y = 2000 + y if y < 100 else y
        return _dt(y, _MON_ABBR.get(mon3, 1), d)
    # 20/08/2025 or 20/08/25
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", s)
    if m:
        d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = 2000 + y if y < 100 else y
        return _dt(y, mth, d)
    # 20 Aug 2025 / 20 Aug 25
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})$", s)
    if m:
        d, mon3, y = int(m.group(1)), m.group(2).upper(), int(m.group(3))
        y = 2000 + y if y < 100 else y
        return _dt(y, _MON_ABBR.get(mon3, 1), d)
    return None

# -------------------------
# Enhanced Entity Recognition (Integrated from enhanced_entity_recognizer.py)
# -------------------------

def extract_enhanced_companies(query: str) -> List[Dict[str, str]]:
    """Extract company references from query."""
    company_mappings = {
        'CAL': {
            'full_name': 'Chorka Apparel Limited',
            'variations': ['cal', 'CAL', 'chorka', 'Chorka'],
            'floor_patterns': [r'CAL.*?Sewing-F\d+', r'Sewing.*?CAL-\d+[A-Z]?']
        },
        'WINNER': {
            'full_name': 'Winner',
            'variations': ['winner', 'Winner', 'WINNER'],
            'floor_patterns': [r'Winner.*?BIP.*?sewing', r'Sewing.*?Winner-\d+']
        },
        'BIP': {
            'full_name': 'BIP',
            'variations': ['bip', 'BIP'],
            'floor_patterns': [r'Winner.*?BIP']
        }
    }
    
    companies = []
    query_lower = query.lower()
    
    for company_code, company_info in company_mappings.items():
        for variation in company_info['variations']:
            if variation.lower() in query_lower:
                companies.append({
                    'code': company_code,
                    'full_name': company_info['full_name'],
                    'variation_found': variation
                })
                break
    
    return companies

def extract_enhanced_floors(query: str) -> List[Dict[str, str]]:
    """Extract floor references from query."""
    floor_patterns = {
        'sewing_floors': [
            r'Sewing\s+Floor-\d+[A-Z]?',  # Sewing Floor-5B
            r'Sewing\s+CAL-\d+[A-Z]?',    # Sewing CAL-2A
            r'CAL\s+Sewing-F\d+',         # CAL Sewing-F1
            r'Winner.*?BIP.*?sewing',      # Winner BIP sewing
            r'Sewing\s+Winner-\d+',       # Sewing Winner-1
        ],
        'cutting_floors': [
            r'Cutting\s+Floor-\d+[A-Z]?',
            r'Cutting\s+CAL-\d+[A-Z]?'
        ],
        'finishing_floors': [
            r'Finishing\s+Floor-\d+[A-Z]?'
        ]
    }
    
    floors = []
    
    for floor_type, patterns in floor_patterns.items():
        for pattern in patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE)
            for match in matches:
                floors.append({
                    'type': floor_type.replace('_floors', ''),
                    'name': match.group(0),
                    'pattern_matched': pattern
                })
    
    return floors

def extract_enhanced_metrics(query: str) -> List[str]:
    """Extract metric-related terms from query."""
    metric_patterns = [
        r'\bproduction\s+qty\b',
        r'\bdefect\s+qty\b',
        r'\bDHU\b',
        r'\btotal\s+production\b',
        r'\bmax\s+defect\b',
        r'\bsalary\b',
        r'\bstock\b',
        r'\bon[-\s]?hand\s+qty\b'
    ]
    
    metrics = []
    for pattern in metric_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            metrics.append(pattern.strip(r'\b'))
    
    return metrics

def classify_enhanced_query_intent(query: str) -> str:
    """Enhanced query intent classification based on user patterns."""
    query_lower = query.lower()

    intent_patterns = {
        'floor_production_summary': [
            r'floor.*wise.*production.*summary',
            r'show.*floor.*production'
        ],
        'defect_analysis': [
            r'defect.*qty.*floor',
            r'max.*defect.*qty',
            r'total.*defect.*qty'
        ],
        'employee_lookup': [
            r'who\s+is\s+\w+',
            r'salary.*president',
            r'give\s+me\s+email.*of\s+\w+',
            r'email.*address.*of\s+\w+',
            r'find\s+email.*\w+',
            r'contact.*info.*of\s+\w+',
            r'\w+.*email.*address',
            r'email.*\w+',
            r'get.*email.*of\s+\w+'
        ],
        # NEW: TNA / task queries (includes PP Approval)
        'tna_task_query': [
            r'\bpp\s+approval\b',
            r'task.*status',
            r'\btna\b.*status',
            r'\bjob.*no\b',
            r'\bpo.*number\b',
            r'style.*ref',
            r'buyer.*name',
            r'shipment.*date',
            r'task.*finish',
            r'task.*update',
            r'approval.*update',
            r'fabric.*receive',
            r'cutting.*production',
            r'sewing.*production',
            r'garment.*inspection',
            r'ex.*factory',
            r'\bknit.*fabric\b',
            # CTL job number patterns / phrasing
            r'\bCTL-\d{2}-\d{5,6}\b',
            r'\bctl-\d{2}-\d{5,6}\b',
            r'job.*number.*CTL',
            r'\bCTL.*information\b'
        ],
        'ranking_query': [
            r'top.*\d+.*defect',
            r'max.*defect.*floor',
            r'biggest.*production',
            r'which.*floor.*produced.*most',
            r'which.*floor.*most.*production',
            r'most.*production.*floor',
            r'floor.*produced.*most',
            r'maximum.*production',
            r'highest.*production'
        ]
    }

    for intent, patterns in intent_patterns.items():
        if any(re.search(p, query_lower) for p in patterns):
            return intent

    if any(w in query_lower for w in ['production', 'defect', 'floor']):
        return 'production_data'
    elif any(w in query_lower for w in ['employee', 'salary', 'president', 'email', 'contact']):
        return 'employee_data'
    elif any(w in query_lower for w in ['task', 'tna', 'job', 'po', 'buyer', 'style', 'shipment', 'approval']):
        return 'tna_task_data'
    elif any(w in query_lower for w in ['stock', 'inventory', 'item', 'product']):
        return 'inventory_data'

    return 'general'


def analyze_enhanced_query(user_query: str) -> Dict[str, Any]:
    """Main enhanced query analysis function integrating all components"""
    
    # Step 1: Dynamic entity recognition
    entities = dynamic_entity_recognition(user_query)
    
    # Step 2: Enhanced intent classification
    intent_result = enhanced_intent_classification(user_query, entities)
    
    # Step 3: Smart table selection
    selected_tables = smart_table_selection(user_query, entities, intent_result['intent'])
    
    # Step 4: Dynamic column selection
    column_selections = dynamic_column_selection(selected_tables, entities, intent_result['intent'])
    
    # Step 5: Compile comprehensive analysis
    analysis_result = {
        'entities': entities,
        'intent': intent_result['intent'],
        'intent_confidence': intent_result['confidence'],
        'intent_scores': intent_result['all_scores'],
        'recommended_tables': selected_tables,
        'recommended_columns': column_selections,
        'complexity_factors': {
            'multiple_entities': len(entities.get('companies', [])) + len(entities.get('floors', [])) > 1,
            'has_aggregations': bool(entities.get('aggregations')),
            'has_dates': bool(entities.get('dates')),
            'has_ctl_codes': bool(entities.get('ctl_codes')),
            'multiple_metrics': len(entities.get('metrics', [])) > 1
        }
    }
    
    return analysis_result

def smart_table_selection(user_query: str, entities: Dict, intent: str) -> List[str]:
    """Smart table selection based on query analysis"""
    
    selected_tables = []
    query_lower = user_query.lower()
    
    # Priority 1: CTL code detection - always use T_TNA_STATUS
    if entities.get('ctl_codes'):
        selected_tables.append('T_TNA_STATUS')
        return selected_tables  # Early return for CTL codes
    
    # Priority 2: Intent-based table selection
    if intent == 'production_summary' or intent == 'defect_analysis':
        # Check for date specificity to choose between T_PROD and T_PROD_DAILY
        if any(date in entities.get('dates', []) for date in entities.get('dates', [])):
            if _DAILY_HINT_RX.search(user_query):
                selected_tables.append('T_PROD_DAILY')
            else:
                selected_tables.extend(['T_PROD_DAILY', 'T_PROD'])
        else:
            selected_tables.append('T_PROD_DAILY')
    
    elif intent == 'tna_task_query':
        selected_tables.append('T_TNA_STATUS')
        
    elif intent == 'employee_lookup':
        selected_tables.extend(['EMP', 'T_USERS'])
        
    elif intent == 'efficiency_query':
        selected_tables.append('T_PROD_DAILY')
    
    # Priority 3: Company-based refinement
    companies = entities.get('companies', [])
    if companies and not selected_tables:
        # Default to production tables for company queries
        selected_tables.append('T_PROD_DAILY')
    
    # Priority 4: Keyword-based fallback
    if not selected_tables:
        if any(word in query_lower for word in ['task', 'tna', 'job', 'po', 'buyer', 'style']):
            selected_tables.append('T_TNA_STATUS')
        elif any(word in query_lower for word in ['production', 'defect', 'floor', 'dhu']):
            selected_tables.append('T_PROD_DAILY')
        elif any(word in query_lower for word in ['employee', 'salary', 'president']):
            selected_tables.extend(['EMP', 'T_USERS'])
    
    # Fallback
    if not selected_tables:
        selected_tables.append('T_PROD_DAILY')
    
    return selected_tables

def dynamic_column_selection(tables: List[str], entities: Dict, intent: str) -> Dict[str, List[str]]:
    """Dynamic column selection based on entities and intent"""
    
    column_selections = {}
    
    for table in tables:
        columns = []
        
        if table in ['T_PROD', 'T_PROD_DAILY']:
            # Base production columns
            columns.extend(['FLOOR_NAME', 'PROD_DATE'])
            
            # Intent-specific columns
            if intent == 'production_summary':
                columns.extend(['PRODUCTION_QTY', 'DEFECT_QTY'])
            elif intent == 'defect_analysis':
                columns.extend(['DEFECT_QTY', 'DHU', 'UNCUT_THREAD', 'DIRTY_STAIN'])
            elif intent == 'efficiency_query':
                columns.extend(['FLOOR_EF', 'DHU', 'PRODUCTION_QTY'])
            
            # Company context
            companies = entities.get('companies', [])
            if companies:
                columns.append('FLOOR_NAME')  # For company filtering
            
        elif table == 'T_TNA_STATUS':
            columns.extend(['JOB_NO', 'TASK_SHORT_NAME', 'TASK_FINISH_DATE'])
            
            if entities.get('ctl_codes'):
                columns.extend(['BUYER_NAME', 'STYLE_REF_NO', 'ACTUAL_FINISH_DATE'])
                
        elif table in ['EMP', 'T_USERS']:
            columns.extend(['EMPNO', 'ENAME', 'JOB'])
            
            if 'salary' in intent or any('salary' in m for m in entities.get('metrics', [])):
                columns.append('SAL')
        
        column_selections[table] = list(set(columns))  # Remove duplicates
    
    return column_selections

def _asked_range(uq: str) -> tuple[Optional[_dt], Optional[_dt]]:
    """
    Extract date range from user query.
    Returns (start_date, end_date) or (None, None) if no dates found.
    """
    # 1) explicit range via query_engine (e.g., "between 01/01/2025 and 05/01/2025")
    rng = extract_explicit_date_range(uq or "")
    if rng and rng.get("start") and rng.get("end"):
        # pull literal out of TO_DATE('LIT','FMT')
        def _to_dt(to_date_expr: str) -> Optional[_dt]:
            m = re.search(r"TO_DATE\('([^']+)','([^']+)'\)", to_date_expr, re.I)
            if not m: 
                return None
            lit, fmt = m.group(1), (m.group(2) or "").upper()
            fmt_map = {
                "DD-MON-YYYY": "%d-%b-%Y", "DD-MON-YY": "%d-%b-%y",
                "YYYY-MM-DD": "%Y-%m-%d",
                "DD/MM/YYYY": "%d/%m/%Y", "DD/MM/YY": "%d/%m/%y",
                "MON-YYYY": "%b-%Y", "MON-YY": "%b-%y",
            }
            py = fmt_map.get(fmt)
            if not py: 
                return None
            try:
                return _dt.strptime(lit, py)
            except Exception:
                return None
        sdt = _to_dt(rng["start"]); edt = _to_dt(rng["end"])
        return (sdt, edt)

    # 2) relative date ranges (e.g., "last 7 days")
    relative_range = extract_relative_date_range(uq or "")
    if relative_range:
        def _to_dt(to_date_expr: str) -> Optional[_dt]:
            m = re.search(r"TO_DATE\('([^']+)','([^']+)'\)", to_date_expr, re.I)
            if not m: 
                return None
            lit, fmt = m.group(1), (m.group(2) or "").upper()
            fmt_map = {
                "DD-MON-YYYY": "%d-%b-%Y", "DD-MON-YY": "%d-%b-%y",
                "YYYY-MM-DD": "%Y-%m-%d",
                "DD/MM/YYYY": "%d/%m/%Y", "DD/MM/YY": "%d/%m/%y",
                "MON-YYYY": "%b-%Y", "MON-YY": "%b-%y",
            }
            py = fmt_map.get(fmt)
            if not py: 
                return None
            try:
                return _dt.strptime(lit, py)
            except Exception:
                return None
        sdt = _to_dt(relative_range["start"]); edt = _to_dt(relative_range["end"])
        return (sdt, edt)

    # 3) single-day literals in the question
    m = re.search(
        r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})\b",
        uq or "", re.I
    )
    if m:
        dt = _parse_day_token(m.group(1))
        if dt:
            return (dt, dt)

    # 4) month token like "Aug-2025" or "Aug 2025"
    m = re.search(r"\b([A-Za-z]{3,9})[-\s](\d{2,4})\b", uq or "", re.I)
    if m:
        mon_word, yy = m.group(1), m.group(2)
        mon3 = (_MONTH_ALIASES.get(mon_word.strip().upper())
                or mon_word[:3].upper())
        if mon3 in _MON_ABBR:
            from calendar import monthrange as _mr
            y = int(yy); y = 2000 + y if y < 100 else y
            start = _dt(y, _MON_ABBR[mon3], 1)
            end = _dt(y, _MON_ABBR[mon3], _mr(y, _MON_ABBR[mon3])[1])
            return (start, end)
    return (None, None)

@lru_cache(maxsize=128)
def _table_exists(selected_db: str, name: str) -> bool:
    try:
        with connect_to_source(selected_db) as (conn, _):
            cur = conn.cursor()
            try:
                cur.execute("SELECT 1 FROM user_tables WHERE table_name = :t", t=name.upper())
                return cur.fetchone() is not None
            finally:
                try: cur.close()
                except: pass
    except Exception:
        return False


def _maybe_force_tprod_tables(uq: str, selected_db: str, candidates: list[str]) -> list[str]:
    """
    For source_db_1 'production/defect qty' style questions with a concrete asked window,
    constrain candidate tables strictly to T_PROD or T_PROD_DAILY so the planner cannot
    wander to similarly named daily tables with sparse data.
    """
    candidates = candidates or []
    if selected_db != "source_db_1":
        return candidates

    mentions_tables = bool(re.search(r"\bT_PROD(?:_DAILY)?\b", uq or "", re.I))
    mentions_kpi    = bool(_METRIC_HINT_RX.search(uq or ""))
    if not (mentions_tables or mentions_kpi):
        return candidates

    start_dt, end_dt = _asked_range(uq or "")
    if not (start_dt and end_dt):
        return candidates

    # decide which table to force
    forced = None
    
    # For relative date ranges like "last 7 days", always use T_PROD_DAILY
    if re.search(r"\b(last|past)\s+\d+\s+days?\b", uq or "", re.I):
        forced = "T_PROD_DAILY"
    elif end_dt < _CUTOFF_DT:
        forced = "T_PROD"
    elif start_dt >= _CUTOFF_DT:
        forced = "T_PROD_DAILY"
    else:
        # straddles cutoff → don’t force
        return candidates

    if not _table_exists(selected_db, forced):
        return candidates

    if forced == "T_PROD" and _table_exists(selected_db, "T_PROD"):
        logger.info("[RAG] Forced table by cutoff rule → T_PROD (strict)")
        return ["T_PROD"]
    if forced == "T_PROD_DAILY" and _table_exists(selected_db, "T_PROD_DAILY"):
        logger.info("[RAG] Forced table by cutoff rule → T_PROD_DAILY (strict)")
        return ["T_PROD_DAILY"]
    return candidates

@lru_cache(maxsize=64)
def _discover_dailyish_tables(selected_db: str, limit: int = 6,
                              must_have_cols: tuple[str,...] = ('PRODUCTION_QTY',)) -> list[str]:
    sql = f"""
    SELECT ut.table_name
      FROM user_tables ut
     WHERE REGEXP_LIKE(ut.table_name, '(DAILY|DLY|_DAY)', 'i')
       AND NOT REGEXP_LIKE(ut.table_name, '(^|_)AI_', 'i')
       AND { " AND ".join([f"EXISTS (SELECT 1 FROM user_tab_columns c WHERE c.table_name = ut.table_name AND UPPER(c.column_name) = '{col}')" for col in must_have_cols]) }
     ORDER BY ut.table_name
     FETCH FIRST :lim ROWS ONLY
    """
    out = []
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        cur.execute(sql, lim=limit)
        out = [r[0] for r in cur.fetchall()]
    return out

# Phase 4: Hybrid Processing Integration Helper Functions
# ============================================================================

def _should_use_hybrid_processing(user_query: str, enhanced_analysis: Dict[str, Any]) -> bool:
    """
    Determine if hybrid processing should be used for this query.
    
    Args:
        user_query: The user's natural language query
        enhanced_analysis: Enhanced analysis result from analyze_enhanced_query
        
    Returns:
        True if hybrid processing should be attempted
    """
    # Skip hybrid processing for simple fast-path queries
    if re.match(r'(?is)^\s*select\b', user_query.strip()):
        return False
    
    if re.search(r'\ball\s+table\s+name(s)?\b', user_query, re.I):
        return False
    
    # Use hybrid processing for complex queries that benefit from AI understanding
    complex_indicators = [
        # Manufacturing domain queries
        r'\b(production|defect|dhu|efficiency|floor|company)\b',
        # TNA/CTL queries
        r'\bCTL-\d{2}-\d{5,6}\b',
        r'\b(task|pp\s+approval|tna|finish\s+date)\b',
        # HR queries
        r'\b(employee|salary|staff|worker|president)\b',
        # Analytics queries
        r'\b(summary|total|average|trend|analysis|compare)\b',
        # Date-based queries
        r'\b(last\s+\d+\s+(days?|months?|years?)|this\s+(month|year|week))\b'
    ]
    
    for pattern in complex_indicators:
        if re.search(pattern, user_query, re.IGNORECASE):
            return True
    
    # Use hybrid for queries with multiple entities or complex structure
    if enhanced_analysis:
        if len(enhanced_analysis.get('companies', [])) > 0:
            return True
        if enhanced_analysis.get('intent') in ['production_query', 'tna_task_query', 'employee_lookup']:
            return True
    
    # Default: use hybrid for non-trivial queries
    return len(user_query.split()) > 3

async def _try_hybrid_processing(
    user_query: str,
    schema_context: str,
    enhanced_analysis: Dict[str, Any],
    options: Dict[str, Any],
    schema_chunks: List[str],
    schema_context_ids: List[str],
    turn_id: Optional[int] = None,
    session_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    hybrid_context_info: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Attempt hybrid processing for SQL generation with enhanced schema context and comprehensive training data collection.
    """
    processing_start_time = time.time()
    classification_start_time = time.time()
    
    try:
        # Initialize hybrid processor
        processor = HybridProcessor()
        
        # Use enhanced schema context for better API model performance
        enhanced_schema_context = _search_schema_enhanced(user_query, "source_db_1", top_k=20)
        # Add forced table information to the schema context if available
        if hybrid_context_info and hybrid_context_info.get("forced_table"):
            forced_table = hybrid_context_info["forced_table"]
            enhanced_schema_context += f"\n\nCRITICAL TABLE SELECTION INFORMATION:\n"
            enhanced_schema_context += f"FORCED TABLE: {forced_table}\n"
            enhanced_schema_context += f"REASON: Date cutoff rule applied\n"
            enhanced_schema_context += f"IMPORTANT: MUST USE {forced_table} TABLE FOR THIS QUERY\n"
        # Phase 5.1: Query Classification and Entity Extraction for Training Data
        classification_result = None
        if COLLECT_TRAINING_DATA and turn_id:
            try:
                # Initialize query classifier for training data collection
                classifier = QueryClassifier()
                classification_result = classifier.classify_query(user_query)
                classification_time_ms = (time.time() - classification_start_time) * 1000
                logger.info(f"[RAG] Query classified as {classification_result.intent} with confidence {classification_result.confidence:.3f}")
            except Exception as e:
                logger.warning(f"[RAG] Query classification failed for training data: {e}")
                classification_time_ms = 0.0
        else:
            classification_time_ms = 0.0
        
        # Create enhanced context for hybrid processing
        hybrid_context = {
            "schema_context": enhanced_schema_context,  # Use enhanced context
            "enhanced_analysis": enhanced_analysis,
            "available_tables": options.get("tables", []),
            "numeric_columns": options.get("numeric_columns", {}),
            "text_columns": options.get("text_columns", {}),
            "date_columns": options.get("date_columns", {}),
        }
        
        # Process query with hybrid system
        processing_result = await processor.process_query_advanced(
            user_query=user_query,
            schema_context=enhanced_schema_context,  # Pass enhanced context
            local_confidence=0.6  # Default confidence for RAG context
        )
        
        if not processing_result or not processing_result.selected_response:
            # Phase 5.2: Record failed processing attempt for training data
            if COLLECT_TRAINING_DATA and turn_id and classification_result:
                try:
                    # Create a minimal ProcessingResult for failed attempts
                    from app.hybrid_processor import ProcessingResult
                    failed_result = ProcessingResult(
                        processing_mode="failed",
                        model_used="none",
                        selected_response="",
                        selection_reasoning="No response generated",
                        processing_time=time.time() - processing_start_time,
                        local_confidence=0.0,
                        api_confidence=0.0
                    )
                    
                    hybrid_data_recorder.record_complete_hybrid_turn(
                        turn_id=turn_id,
                        classification_result=classification_result,
                        processing_result=failed_result,
                        entities=enhanced_analysis.get('entities', {}),
                        schema_tables_used=options.get("tables", []),
                        business_context=f"Enhanced analysis: {enhanced_analysis.get('intent', 'unknown')}",
                        sql_execution_success=False,
                        sql_execution_error="No SQL generated",
                        classification_time_ms=classification_time_ms,
                        session_id=session_id,
                        client_ip=client_ip,
                        user_agent=user_agent
                    )
                    logger.info("[RAG] Recorded failed hybrid processing attempt for training data")
                except Exception as e:
                    logger.warning(f"[RAG] Failed to record failed processing attempt: {e}")
            
            return None
        
        # Parse the selected response (should be SQL)
        sql_response = processing_result.selected_response.strip()
        
        # Clean markdown formatting if present
        if sql_response.startswith('```sql'):
            sql_response = sql_response.replace('```sql', '').replace('```', '').strip()
        elif sql_response.startswith('```'):
            sql_response = sql_response.replace('```', '').strip()
            
        # Remove any trailing backticks that might remain
        sql_response = sql_response.rstrip('`').strip()
        
        # Enhanced extraction: Handle mixed responses with natural language and SQL
        # Look for SQL code blocks or SELECT statements within the response
        sql_start_patterns = [r'```sql\s*(SELECT.*)', r'```(?:\w*\s*)?(SELECT.*)', r'(SELECT.*)']
        import re
        extracted_sql = None
        
        for pattern in sql_start_patterns:
            match = re.search(pattern, sql_response, re.IGNORECASE | re.DOTALL)
            if match:
                extracted_sql = match.group(1).strip()
                break
        
        # If we found SQL within the response, use it
        if extracted_sql:
            sql_response = extracted_sql
        else:
            # Fallback to original extraction logic
            # Extract only the SQL part if there are multiple lines
            lines = sql_response.split('\n')
            sql_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith(('--', '/*', '#', '*')):
                    sql_lines.append(line)
            
            sql_response = ' '.join(sql_lines) if sql_lines else sql_response
        
        # Additional cleaning: Remove any trailing characters that might cause syntax errors
        sql_response = sql_response.rstrip(';').rstrip('`').rstrip().rstrip(';')
        
        # Validate the hybrid-generated SQL
        if not sql_response or not sql_response.upper().startswith('SELECT'):
            logger.warning(f"[RAG] Hybrid processing returned non-SQL response: {sql_response[:100]}...")
            
            # Instead of giving up, use the existing query engine to generate SQL based on the forced table
            # This is a critical fallback for production queries with dates
            forced_table_match = re.search(r"FORCED TABLE:\s*([A-Z_0-9]+)", schema_context or "")
            if forced_table_match and "date" in user_query.lower() and any(word in user_query.lower() for word in ["production", "qty", "dhu"]):
                forced_table = forced_table_match.group(1)
                logger.info(f"[RAG] Using fallback SQL generation with forced table: {forced_table}")
                
                # Extract date information using existing robust date extraction functions
                date_range = extract_enhanced_date_range(user_query)
                date_range = date_range or extract_explicit_date_range(user_query)
                date_range = date_range or extract_relative_date_range(user_query)
                date_range = date_range or extract_month_token_range(user_query)
                date_range = date_range or extract_single_day_range(user_query)
                
                # Build SQL based on the date range and forced table
                if date_range:
                    # Use existing SQL planner to generate SQL (don't hardcode!)
                    plan = {
                        "table": forced_table,
                        "columns": ["PROD_DATE", "FLOOR_NAME", "PRODUCTION_QTY", "DHU"],
                        "filters": []
                    }
                    
                    # Add date filter if available
                    if date_range.get("start") and date_range.get("end"):
                        date_filter = {"column": "PROD_DATE", "operator": "BETWEEN", 
                                      "value": date_range["start"], "value2": date_range["end"]}
                        plan["filters"].append(date_filter)
                    
                    # Use the existing build_sql_from_plan function to generate SQL
                    fallback_sql = build_sql_from_plan(plan, "source_db_1", user_query)
                    
                    # Apply existing validations
                    fallback_sql = normalize_dates(fallback_sql)
                    fallback_sql = enforce_wide_projection_for_generic(user_query, fallback_sql)
                    fallback_sql = value_aware_text_filter(fallback_sql, "source_db_1")
                    fallback_sql = ensure_label_filter(fallback_sql, user_query, "source_db_1")
                    
                    # Execute the fallback SQL
                    logger.info(f"[RAG] Generated fallback SQL: {fallback_sql}")
                    try:
                        rows = run_sql(fallback_sql, "source_db_1")
                        
                        # Process results using existing RAG pipeline
                        display_mode = determine_display_mode(user_query, rows)
                        rows_for_summary = widen_results_if_needed(rows, sql, "source_db_1", display_mode, user_query)
                        python_summary = summarize_results(
                            rows_for_summary,
                            user_query,
                        ) if display_mode in ["summary", "both"] else ""
                        
                        # Generate natural language summary if needed
                        summary = ""
                        if display_mode in ["summary", "both"]:
                            summary = generate_natural_language_summary(
                                user_query=user_query,
                                columns=list(rows[0].keys()) if rows else [],
                                rows=rows,
                                sql=fallback_sql
                            )
                        else:
                            summary = python_summary
                        
                        # Record training data as usual
                        if COLLECT_TRAINING_DATA and turn_id and 'classification_result' in locals():
                            try:
                                # Record hybrid processing data (similar to existing code)
                                # ... existing training data recording code ...
                                pass
                            except Exception as e:
                                logger.warning(f"[RAG] Failed to record hybrid processing training data: {e}")
                        
                        # Return successful fallback result
                        visualization_requested = has_visualization_intent(user_query)
                        return {
                            "status": "success",
                            "summary": summary if display_mode in ["summary", "both"] else "",
                            "sql": fallback_sql,
                            "display_mode": display_mode,
                            "visualization": visualization_requested,
                            "results": {
                                "columns": (list(rows[0].keys()) if rows else []),
                                "rows": [list(r.values()) for r in rows] if rows else [],
                                "row_count": len(rows) if rows else 0,
                            },
                            "schema_context": schema_chunks,
                            "schema_context_ids": schema_context_ids,
                            "hybrid_metadata": {
                                "processing_mode": "fallback_generation",
                                "selection_reasoning": "Generated fallback SQL using extracted date",
                                "model_used": "system",
                                "processing_time": 0.0,
                                "local_confidence": 0.0,
                                "api_confidence": 0.0,
                                "enhanced_schema_used": True,
                                "training_data_recorded": COLLECT_TRAINING_DATA and turn_id is not None,
                            }
                        }
                    except Exception as e:
                        logger.error(f"[RAG] Fallback SQL execution failed: {e}")
            
            # Original code for recording failures
            if COLLECT_TRAINING_DATA and turn_id and classification_result:
                # ... existing code for recording failures ...
                pass
            
            return None
        # Extract only the SQL part if there are multiple lines
        lines = sql_response.split('\n')
        sql_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith(('--', '/*', '#', '*')):
                sql_lines.append(line)
        
        sql_response = ' '.join(sql_lines) if sql_lines else sql_response
        # Extract only the SQL part if there are multiple lines
        lines = sql_response.split('\n')
        sql_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith(('--', '/*', '#', '*')):
                sql_lines.append(line)
        
        sql_response = ' '.join(sql_lines) if sql_lines else sql_response
        
        # Apply existing RAG validations to hybrid-generated SQL
        sql = normalize_dates(sql_response.rstrip(";"))
        sql = enforce_wide_projection_for_generic(user_query, sql)
        sql = value_aware_text_filter(sql, "source_db_1")  # Default to main DB
        sql = ensure_label_filter(sql, user_query, "source_db_1")
        
        # Validate SQL syntax
        enforce_predicate_type_compat(sql, "source_db_1")
        if not is_valid_sql(sql, "source_db_1"):
            logger.warning(f"[RAG] Hybrid-generated SQL failed validation: {sql}")
            
            # Phase 5.2: Record SQL validation failure for training data
            if COLLECT_TRAINING_DATA and turn_id and classification_result:
                try:
                    hybrid_data_recorder.record_complete_hybrid_turn(
                        turn_id=turn_id,
                        classification_result=classification_result,
                        processing_result=processing_result,
                        entities=enhanced_analysis.get('entities', {}),
                        schema_tables_used=options.get("tables", []),
                        business_context=f"Enhanced analysis: {enhanced_analysis.get('intent', 'unknown')}",
                        sql_execution_success=False,
                        sql_execution_error="SQL validation failed",
                        classification_time_ms=classification_time_ms,
                        session_id=session_id,
                        client_ip=client_ip,
                        user_agent=user_agent
                    )
                    logger.info("[RAG] Recorded SQL validation failure for training data")
                except Exception as e:
                    logger.warning(f"[RAG] Failed to record SQL validation failure: {e}")
            
            return None
        
        # Execute the hybrid-generated SQL
        sql_execution_start_time = time.time()
        sql_execution_success = False
        sql_execution_error = None
        result_row_count = 0
        rows = []
        
        try:
            rows = run_sql(sql, "source_db_1")
            sql_execution_success = True
            result_row_count = len(rows) if rows else 0
            logger.info(f"[RAG] Hybrid-generated SQL executed successfully, returned {result_row_count} rows")
        except Exception as e:
            sql_execution_error = str(e)
            logger.error(f"[RAG] Hybrid-generated SQL execution failed: {e}")
        
        sql_execution_time_ms = (time.time() - sql_execution_start_time) * 1000
        
        # Process results using existing RAG pipeline
        display_mode = determine_display_mode(user_query, rows)
        rows_for_summary = widen_results_if_needed(rows, sql, "source_db_1", display_mode, user_query)
        python_summary = summarize_results(
            rows_for_summary,
            user_query,
            sql,
        ) if display_mode in ["summary", "both"] else ""

        # Generate natural language summary if needed
        summary = ""
        if display_mode in ["summary", "both"]:
            # Use our new direct function that avoids asyncio issues
            summary = generate_natural_language_summary(
                user_query=user_query,
                columns=list(rows[0].keys()) if rows else [],
                rows=rows,
                sql=sql
            )
        else:
            summary = python_summary
        
        # Phase 5.3: Record successful hybrid processing with complete training data
        if COLLECT_TRAINING_DATA and turn_id and classification_result:
            try:
                recorded_ids = hybrid_data_recorder.record_complete_hybrid_turn(
                    turn_id=turn_id,
                    classification_result=classification_result,
                    processing_result=processing_result,
                    entities=enhanced_analysis.get('entities', {}),
                    schema_tables_used=options.get("tables", []),
                    business_context=f"Enhanced analysis: {enhanced_analysis.get('intent', 'unknown')}" if enhanced_analysis else "Enhanced analysis: unknown",
                    sql_execution_success=sql_execution_success,
                    sql_execution_error=sql_execution_error,
                    result_row_count=result_row_count,
                    sql_execution_time_ms=sql_execution_time_ms,
                    classification_time_ms=classification_time_ms,
                    session_id=session_id,
                    client_ip=client_ip,
                    user_agent=user_agent
                )
                logger.info(f"[RAG] Recorded complete hybrid processing turn with training data: {recorded_ids}")
            except Exception as e:
                logger.warning(f"[RAG] Failed to record hybrid processing training data: {e}")
        
        # Return successful hybrid result in RAG format
        visualization_requested = has_visualization_intent(user_query)

        # Then modify the return statement to include the visualization flag:
        return {
            "status": "success",
            "summary": summary if display_mode in ["summary", "both"] else "",
            "sql": sql,
            "display_mode": display_mode,
            "visualization": visualization_requested,
            "results": {
                "columns": (list(rows[0].keys()) if rows else []),
                "rows": [list(r.values()) for r in rows] if rows else [],
                "row_count": len(rows) if rows else 0,
            },
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
            # Hybrid-specific metadata
            "hybrid_metadata": {
                "processing_mode": processing_result.processing_mode,
                "selection_reasoning": processing_result.selection_reasoning,
                "model_used": processing_result.model_used,
                "processing_time": processing_result.processing_time or 0.0,
                "local_confidence": processing_result.local_confidence or 0.0,
                "api_confidence": processing_result.api_confidence or 0.0,
                "enhanced_schema_used": True,  # Flag to indicate enhanced schema was used
                # Phase 5: Training data collection metadata
                "training_data_recorded": COLLECT_TRAINING_DATA and turn_id is not None,
                "classification_time_ms": classification_time_ms or 0.0,
                "sql_execution_time_ms": sql_execution_time_ms or 0.0,
                "sql_execution_success": sql_execution_success,
            }
        }
        
    except Exception as e:
        logger.error(f"[RAG] Hybrid processing failed: {e}")
        
        # Phase 5.2: Record processing failure for training data
        if COLLECT_TRAINING_DATA and turn_id and 'classification_result' in locals():
            try:
                from app.hybrid_processor import ProcessingResult, ResponseMetrics
                # Create dummy metrics for error case
                dummy_metrics = ResponseMetrics(
                    sql_validity_score=0.0,
                    schema_compliance_score=0.0,
                    business_logic_score=0.0,
                    performance_score=0.0,
                    overall_score=0.0,
                    reasoning=["Processing error occurred"]
                )
                
                error_result = ProcessingResult(
                    selected_response="",
                    local_response=None,
                    api_response=None,
                    processing_mode="error",
                    selection_reasoning=f"Processing error: {str(e)}",
                    local_confidence=0.0,
                    api_confidence=0.0,
                    processing_time=0.0,
                    model_used="none",
                    local_metrics=dummy_metrics,
                    api_metrics=dummy_metrics
                )
                
                # Ensure classification_time_ms is not None to prevent format string errors
                safe_classification_time_ms = 0.0
                if 'classification_time_ms' in locals() and classification_time_ms is not None:
                    safe_classification_time_ms = classification_time_ms
                
                hybrid_data_recorder.record_complete_hybrid_turn(
                    turn_id=turn_id,
                    classification_result=classification_result,
                    processing_result=error_result,
                    entities=enhanced_analysis.get('entities', {}),
                    schema_tables_used=options.get("tables", []),
                    business_context=f"Enhanced analysis: {enhanced_analysis.get('intent', 'unknown')}" if enhanced_analysis else "unknown",
                    sql_execution_success=False,
                    sql_execution_error=f"Processing error: {str(e)}",
                    classification_time_ms=safe_classification_time_ms,
                    session_id=session_id,
                    client_ip=client_ip,
                    user_agent=user_agent
                )
                logger.info("[RAG] Recorded processing error for training data")
            except Exception as record_error:
                logger.warning(f"[RAG] Failed to record processing error: {record_error}")
        
        return None

# -------------------------
# Learn data patterns (Dynamic, not hardcoded)
# -------------------------  
def learn_data_patterns_dynamically(selected_db: str, table_name: str, sample_size: int = 100) -> Dict[str, Any]:
    """
    Dynamically learn data patterns from actual database content.
    This replaces hardcoded patterns with real data analysis.
    """
    patterns = {
        'floor_name_patterns': [],
        'date_formats': [],
        'company_variations': [],
        'common_values': {},
        'data_types': {},
        'value_ranges': {}
    }
    
    try:
        with connect_to_source(selected_db) as (conn, _):
            cursor = conn.cursor()
            
            # Get column information
            cursor.execute("""
                SELECT column_name, data_type, nullable
                FROM user_tab_columns 
                WHERE table_name = :table_name
                ORDER BY column_id
            """, {"table_name": table_name.upper()})
            
            columns_info = cursor.fetchall()
            
            for col_name, data_type, nullable in columns_info:
                patterns['data_types'][col_name] = data_type
                
                # Sample actual values for pattern learning
                if data_type in ['VARCHAR2', 'CHAR', 'NVARCHAR2']:
                    try:
                        cursor.execute(f"""
                            SELECT DISTINCT {col_name}
                            FROM {table_name}
                            WHERE {col_name} IS NOT NULL
                            AND ROWNUM <= :sample_size
                        """, {"sample_size": sample_size})
                        
                        values = [row[0] for row in cursor.fetchall() if row[0]]
                        patterns['common_values'][col_name] = values[:10]  # Top 10 examples
                        
                        # Learn specific patterns
                        if 'floor' in col_name.lower():
                            patterns['floor_name_patterns'] = values[:5]
                        elif any(word in col_name.lower() for word in ['company', 'buyer']):
                            patterns['company_variations'] = values[:5]
                            
                    except Exception as e:
                        logger.debug(f"Could not sample values for {col_name}: {e}")
                        
    except Exception as e:
        logger.error(f"Pattern learning failed for {table_name}: {e}")
    
    return patterns

def create_dynamic_prompt_context(user_query: str, schema_context: str, selected_db: str) -> str:
    """
    Create dynamic prompt context that adapts to query and learned patterns.
    """
    # Extract table mentions from schema context
    mentioned_tables = []
    for line in schema_context.split('\n'):
        if line.startswith('TABLE:'):
            table_name = line.replace('TABLE:', '').strip()
            mentioned_tables.append(table_name)
    
    # Learn patterns from mentioned tables
    learned_patterns = {}
    for table in mentioned_tables[:3]:  # Limit to avoid performance issues
        learned_patterns[table] = learn_data_patterns_dynamically(selected_db, table)
    
    # Determine correct table based on date logic
    query_lower = user_query.lower()
    default_table = "T_PROD_DAILY"  # Default for all current queries
    
    # Only use T_PROD if specifically asking for early January 2025
    if any(phrase in query_lower for phrase in ['january 2025', 'jan 2025', 'early 2025', 'before january 15']):
        default_table = "T_PROD"
    
    # Build adaptive prompt
    prompt_parts = [
        "You are an Oracle SQL expert generating queries for a manufacturing database.",
        "",
        "CRITICAL TABLE SELECTION:",
        f"- DEFAULT TABLE: {default_table}",
        "- T_PROD_DAILY: Use for ALL current data (January 15, 2025 onwards)",
        "- T_PROD: Only for historical data (January 1-15, 2025)",
        "",
        "SCHEMA CONTEXT:",
        schema_context,
        "",
        "LEARNED DATA PATTERNS:"
    ]
    
    # Add learned patterns dynamically
    for table, patterns in learned_patterns.items():
        if patterns['floor_name_patterns']:
            prompt_parts.append(f"{table} floor names examples: {', '.join(patterns['floor_name_patterns'][:3])}")
        
        if patterns['company_variations']:
            prompt_parts.append(f"{table} company examples: {', '.join(patterns['company_variations'][:3])}")
    
    prompt_parts.extend([
        "",
        "REQUIREMENTS:",
        f"- Use {default_table} table (NOT T_PROD unless specifically querying January 1-15, 2025)",
        "- Generate only valid Oracle SQL SELECT statements",
        "- Use exact table and column names from schema",
        "- Use LIKE patterns for partial text matching",
        "- Use TO_DATE() for date filters with DD-MON-YYYY format",
        "- Current year is 2025 (NOT 2023)",
        "- Use UPPER() for case-insensitive string comparisons",
        "",
        f"USER QUERY: {user_query}",
        "",
        f"SQL (using {default_table}):"
    ])
    
    return "\n".join(prompt_parts)
# -------------------------
# Critical Table Schema Definitions (Dynamic, not hardcoded)
# -------------------------
def get_critical_table_schemas(selected_db: str) -> Dict[str, Dict]:
    """
    Dynamically fetch schema information for critical tables.
    """
    critical_tables = ['T_PROD', 'T_PROD_DAILY', 'T_TNA_STATUS']
    schemas: Dict[str, Dict] = {}

    try:
        with connect_to_source(selected_db) as (conn, _):
            cur = conn.cursor()

            for table in critical_tables:
                cur.execute("""
                    SELECT COLUMN_NAME, DATA_TYPE, NULLABLE, DATA_DEFAULT, COLUMN_ID
                    FROM USER_TAB_COLUMNS
                    WHERE TABLE_NAME = :table_name
                    ORDER BY COLUMN_ID
                """, {"table_name": table.upper()})

                columns = cur.fetchall()
                if not columns:
                    continue

                schemas[table] = {
                    'columns': {},
                    'date_columns': [],
                    'numeric_columns': [],
                    'text_columns': [],
                    'key_columns': {}
                }

                for col_name, data_type, nullable, default, col_id in columns:
                    dt = str(data_type or "").upper()
                    schemas[table]['columns'][col_name] = {
                        'type': dt,
                        'nullable': (nullable == 'Y'),
                        'default': default,
                        'position': col_id
                    }
                    if 'DATE' in dt or 'TIMESTAMP' in dt:
                        schemas[table]['date_columns'].append(col_name)
                    elif any(k in dt for k in ('NUMBER','FLOAT','INTEGER','BINARY')):
                        schemas[table]['numeric_columns'].append(col_name)
                    else:
                        schemas[table]['text_columns'].append(col_name)

                schemas[table]['key_columns'] = _get_key_columns_for_table(table)

        logger.info(f"[RAG] Loaded schemas for {len(schemas)} critical tables")
        return schemas
    except Exception as e:
        logger.error(f"[RAG] Failed to load critical table schemas: {e}")
        return {}

def _get_key_columns_for_table(table: str) -> Dict[str, List[str]]:
    key_mappings: Dict[str, Dict[str, List[str]]] = {
        'T_PROD': {
            'date_filters': ['PROD_DATE'],
            'grouping_columns': ['FLOOR_NAME', 'PM_OR_APM_NAME'],
            'metric_columns': ['PRODUCTION_QTY', 'DEFECT_QTY', 'DHU', 'FLOOR_EF'],
            'defect_details': ['UNCUT_THREAD', 'DIRTY_STAIN', 'BROKEN_STITCH', 'SKIP_STITCH', 'OPEN_SEAM'],
            'efficiency_columns': ['FLOOR_EF', 'DHU', 'DEFECT_PERS']
        },
        'T_PROD_DAILY': {
            'date_filters': ['PROD_DATE'],
            'grouping_columns': ['FLOOR_NAME', 'PM_OR_APM_NAME'],
            'metric_columns': ['PRODUCTION_QTY', 'DEFECT_QTY', 'DHU', 'FLOOR_EF'],
            'defect_details': ['UNCUT_THREAD', 'DIRTY_STAIN', 'BROKEN_STITCH', 'SKIP_STITCH', 'OPEN_SEAM'],
            'efficiency_columns': ['FLOOR_EF', 'DHU', 'DEFECT_PERS'],
            'time_columns': ['AC_PRODUCTION_HOUR', 'AC_WORKING_HOUR']
        },
        'T_TNA_STATUS': {
            'date_filters': ['TASK_FINISH_DATE', 'ACTUAL_FINISH_DATE', 'PO_RECEIVED_DATE', 'SHIPMENT_DATE'],
            'grouping_columns': ['BUYER_NAME', 'TEAM_LEADER_NAME', 'TEAM_MEMBER_NAME'],
            'identifier_columns': ['JOB_NO', 'PO_NUMBER', 'STYLE_REF_NO'],
            'task_columns': ['TASK_NUMBER', 'TASK_SHORT_NAME'],
            'style_columns': ['STYLE_REF_NO', 'STYLE_DESCRIPTION']
        }
    }
    return key_mappings.get(table, {})

def enhance_query_with_critical_table_knowledge(user_query: str, plan: Dict, options: Dict, selected_db: str) -> Dict:
    """
    If the planner picks one of the critical tables, auto-augment dims/metrics based on the question.
    """
    if not isinstance(plan, dict):
        return plan

    table = plan.get('table')
    if not table or table.upper() not in {'T_PROD','T_PROD_DAILY','T_TNA_STATUS'}:
        return plan
    table = table.upper()

    critical = get_critical_table_schemas(selected_db)
    if table not in critical:
        return plan

    key_cols = critical[table].get('key_columns', {})
    q = (user_query or "").lower()
    out = dict(plan)

    # metrics
    if any(w in q for w in ['production','qty','quantity','piece','pieces']):
        out.setdefault('metrics', [])
        if 'PRODUCTION_QTY' not in out['metrics']:
            out['metrics'].append('PRODUCTION_QTY')

    if any(w in q for w in ['defect','rejection','dhu']):
        out.setdefault('metrics', [])
        for m in ['DEFECT_QTY', 'DHU']:
            if m not in out['metrics']:
                out['metrics'].append(m)

    if any(w in q for w in ['efficiency','eff','rate','percent','pct']):
        out.setdefault('metrics', [])
        if 'FLOOR_EF' not in out['metrics']:
            out['metrics'].append('FLOOR_EF')

    # defect detail columns
    if any(w in q for w in ['broken','skip','stitch','seam','thread','stain','dirty']):
        out.setdefault('metrics', [])
        for m in key_cols.get('defect_details', []):
            if m not in out['metrics']:
                out['metrics'].append(m)

    # dims
    if any(w in q for w in ['floor','wise','by floor','each floor']):
        out.setdefault('dims', [])
        if 'FLOOR_NAME' not in out['dims']:
            out['dims'].append('FLOOR_NAME')

    if any(w in q for w in ['manager','pm','apm']):
        out.setdefault('dims', [])
        if 'PM_OR_APM_NAME' not in out['dims']:
            out['dims'].append('PM_OR_APM_NAME')

    if table == 'T_TNA_STATUS':
        if any(w in q for w in ['buyer','customer']):
            out.setdefault('dims', [])
            if 'BUYER_NAME' not in out['dims']:
                out['dims'].append('BUYER_NAME')
        if any(w in q for w in ['style','design']):
            out.setdefault('dims', [])
            for c in ['STYLE_REF_NO','STYLE_DESCRIPTION']:
                if c not in out['dims']:
                    out['dims'].append(c)

    if table == 'T_PROD_DAILY' and any(w in q for w in ['hour','working','production hour']):
        out.setdefault('metrics', [])
        for c in ['AC_PRODUCTION_HOUR','AC_WORKING_HOUR']:
            if c not in out['metrics']:
                out['metrics'].append(c)

    # dedupe/limit - fixed to handle both strings and dictionaries
    if 'metrics' in out:
        # Metrics are typically strings, so we can use the simple deduplication
        seen = set()
        deduped_metrics = []
        for item in out['metrics']:
            if item not in seen:
                seen.add(item)
                deduped_metrics.append(item)
        out['metrics'] = deduped_metrics[:10]
        
    if 'dims' in out:
        # Dims can contain both strings and dictionaries, so we need special handling
        seen = []
        deduped_dims = []
        for item in out['dims']:
            # For dictionaries, convert to a comparable form
            if isinstance(item, dict):
                # Check if we've already seen this dictionary
                already_seen = False
                for seen_item in seen:
                    if isinstance(seen_item, dict) and seen_item == item:
                        already_seen = True
                        break
                if not already_seen:
                    seen.append(item)
                    deduped_dims.append(item)
            else:
                # For strings and other hashable types
                if item not in seen:
                    seen.append(item)
                    deduped_dims.append(item)
        out['dims'] = deduped_dims[:5]

    return out

def _intelligent_table_selection(user_query: str, candidate_tables: List[str], selected_db: str) -> List[str]:
    q = (user_query or "").lower()
    crit = {'T_PROD','T_PROD_DAILY','T_TNA_STATUS'}
    scores: Dict[str,int] = {}

    for t in candidate_tables:
        T = t.upper()
        s = 0
        if T in crit: s += 10

        if any(w in q for w in ['production','defect','floor','dhu','efficiency']):
            if T in {'T_PROD','T_PROD_DAILY'}:
                s += 20
                if T == 'T_PROD_DAILY' and _DAILY_HINT_RX.search(user_query or ''):
                    s += 5

        if any(w in q for w in ['task','tna','job','po','buyer','style','shipment','approval','ctl']):
            if T == 'T_TNA_STATUS':
                s += 20

        if T in {'T_PROD','T_PROD_DAILY'}:
            start_dt, end_dt = _asked_range(user_query or "")
            if start_dt and end_dt:
                if end_dt < _CUTOFF_DT and T == 'T_PROD':
                    s += 10
                elif start_dt >= _CUTOFF_DT and T == 'T_PROD_DAILY':
                    s += 10

        scores[T] = s

    return sorted(candidate_tables, key=lambda x: (-scores.get(x.upper(), 0), x.upper()))

def get_smart_column_suggestions(table: str, user_query: str, selected_db: str) -> List[str]:
    T = (table or "").upper()
    if T not in {'T_PROD','T_PROD_DAILY','T_TNA_STATUS'}:
        return []

    q = (user_query or "").lower()
    schemas = get_critical_table_schemas(selected_db)
    if T not in schemas:
        return []

    sug: List[str] = []
    if T in {'T_PROD','T_PROD_DAILY'}:
        sug += ['PROD_DATE','FLOOR_NAME']
    elif T == 'T_TNA_STATUS':
        sug += ['JOB_NO','STYLE_REF_NO']

    intent_map = {
        'production': ['PRODUCTION_QTY'],
        'defect': ['DEFECT_QTY','DHU'],
        'efficiency': ['FLOOR_EF','DHU'],
        'floor': ['FLOOR_NAME'],
        'manager': ['PM_OR_APM_NAME'],
        'buyer': ['BUYER_NAME'],
        'style': ['STYLE_REF_NO','STYLE_DESCRIPTION'],
        'task': ['TASK_SHORT_NAME','TASK_NUMBER'],
        'date': ['PROD_DATE','TASK_FINISH_DATE','SHIPMENT_DATE']
    }
    for k, cols in intent_map.items():
        if k in q:
            sug += cols

    # keep only real columns, dedupe, cap
    cols_set = set(schemas[T]['columns'].keys())
    out: List[str] = []
    seen = set()
    for c in sug:
        if c in cols_set and c not in seen:
            out.append(c); seen.add(c)
    return out[:8]

def _search_schema_enhanced(user_query: str, selected_db: str, top_k: int = 15) -> str:
    """Enhanced schema search with comprehensive context building."""
    try:
        results = hybrid_schema_value_search(user_query, selected_db=selected_db, top_k=top_k) or []
        return create_comprehensive_schema_context(results, selected_db, user_query)
    except Exception as e:
        logger.warning(f"[RAG] Enhanced schema search failed: {e}")
        return "Schema information unavailable due to search error."

def create_comprehensive_schema_context(results: List[Dict[str, Any]], selected_db: str, user_query: str = "") -> str:
    """
    Create comprehensive schema context with examples, patterns, and best practices.
    This replaces hardcoded patterns with dynamic learning from actual data.
    """
    if not results:
        return "No schema information available."
    
    # Group results by type for better organization
    tables_info = {}
    sample_data = {}
    patterns_discovered = {}
    
    for result in results:
        content = result.get('content', '')
        metadata = result.get('metadata', {})
        
        table_name = metadata.get('table', metadata.get('source_table', ''))
        if not table_name:
            continue
            
        if table_name not in tables_info:
            tables_info[table_name] = {
                'columns': [],
                'sample_values': {},
                'patterns': [],
                'description': '',
                'data_types': {}
            }
        
        # Extract column information
        if 'columns:' in content.lower() or 'column_name' in content.lower():
            tables_info[table_name]['description'] = content
            
        # Extract sample values and patterns
        if 'sample_values:' in content.lower() or 'example:' in content.lower():
            sample_data[table_name] = content
            
    # Build dynamic schema context
    context_parts = []
    
    # 1. Database Overview
    context_parts.append(f"DATABASE: {selected_db}")
    context_parts.append(f"AVAILABLE TABLES: {', '.join(tables_info.keys())}")
    context_parts.append("")
    
    # 2. Critical Table Selection Rules
    context_parts.append("TABLE SELECTION RULES:")
    context_parts.append("DEFAULT TABLE: T_PROD_DAILY (use this unless specifically querying data before January 15, 2025)")
    context_parts.append("T_PROD: Contains data from January 1, 2025 to January 15, 2025 ONLY")
    context_parts.append("T_PROD_DAILY: Contains data from January 15, 2025 onwards (current active table)")
    context_parts.append("RULE: If no specific date is mentioned, ALWAYS use T_PROD_DAILY")
    context_parts.append("RULE: Only use T_PROD if query specifically asks for data before January 15, 2025")
    context_parts.append("")
    
    # 3. Table-specific information with learned patterns
    for table_name, info in tables_info.items():
        context_parts.append(f"TABLE: {table_name}")
        
        # Add specific guidance for production tables
        if table_name == "T_PROD_DAILY":
            context_parts.append("PURPOSE: Current production data (January 15, 2025 onwards)")
            context_parts.append("USE FOR: All current queries, efficiency, floor data, recent production")
        elif table_name == "T_PROD":
            context_parts.append("PURPOSE: Historical production data (January 1-15, 2025 only)")
            context_parts.append("USE FOR: Only when specifically querying early January 2025 data")
        
        context_parts.append(f"DESCRIPTION: {info['description'][:200]}...")
        
        # Extract and include actual data patterns
        if table_name in sample_data:
            context_parts.append(f"DATA PATTERNS: {sample_data[table_name][:150]}...")
        
        context_parts.append("")
    
    # 4. Query-specific guidance
    query_lower = user_query.lower()
    
    # Add contextual examples based on query content
    if any(word in query_lower for word in ['floor', 'sewing', 'cal']):
        context_parts.append("FLOOR NAME PATTERNS:")
        context_parts.append("- Use LIKE patterns for partial matches")
        context_parts.append("- Consider variations in naming (CAL Sewing -F2, Sewing CAL-2A)")
        context_parts.append("- Use UPPER() for case-insensitive matching")
        context_parts.append("")
        
    # Enhanced date guidance with table selection logic
    if any(word in query_lower for word in ['aug', 'date', 'month']) or not any(word in query_lower for word in ['january', 'jan', 'early', '2025']):
        context_parts.append("DATE HANDLING FOR CURRENT QUERIES:")
        context_parts.append("- Current date context: 2025 (not 2023)")
        context_parts.append("- Default table: T_PROD_DAILY for any date after January 15, 2025")
        context_parts.append("- Use month ranges: aug-25 = August 2025 (full month)")
        context_parts.append("- Use TO_DATE() with DD-MON-YYYY format")
        context_parts.append("")
    
    # 5. Best practices (learned from vector store)
    context_parts.append("SQL BEST PRACTICES:")
    context_parts.append("- ALWAYS use T_PROD_DAILY unless specifically querying January 1-15, 2025")
    context_parts.append("- Use proper Oracle syntax (TO_DATE, UPPER, etc.)")
    context_parts.append("- Group by all non-aggregate columns")
    context_parts.append("- Use appropriate JOINs when needed")
    context_parts.append("- Consider performance with proper WHERE clauses")
    
    return "\n".join(context_parts)
# ---------------------------
# Retrieval
# ---------------------------
def _search_schema(user_query: str, selected_db: str, top_k: int = 12) -> List[Dict[str, Any]]:
    """Wrap Chroma hybrid search."""
    try:
        return hybrid_schema_value_search(user_query, selected_db=selected_db, top_k=top_k) or []
    except Exception as e:
        logger.warning(f"[RAG] Schema search failed: {e}")
        return []
    
def _search_schema_enhanced(user_query: str, selected_db: str, top_k: int = 15) -> str:
    """Enhanced schema search with comprehensive context building."""
    try:
        results = hybrid_schema_value_search(user_query, selected_db=selected_db, top_k=top_k) or []
        return create_comprehensive_schema_context(results, selected_db, user_query)
    except Exception as e:
        logger.warning(f"[RAG] Enhanced schema search failed: {e}")
        return "Schema information unavailable due to search error."

def _extract_context_ids(results: List[Dict[str, Any]]) -> List[str]:
    """Stable-ish IDs for observability/debugging."""
    out: List[str] = []
    seen = set()
    for r in results or []:
        md = (r or {}).get("metadata", {}) or {}
        candidates = [
            r.get("id"),
            md.get("id"),
            md.get("chunk_id"),
            md.get("doc_id"),
            md.get("source_id"),
            md.get("collection_id"),
            md.get("table"),
            md.get("source_table"),
            md.get("file"),
            md.get("path"),
            md.get("source"),
        ]
        rid = next((c for c in candidates if c), None)
        if not rid:
            continue
        s = str(rid)
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= 50:
            break
    return out


def _tables_from_results(results: List[Dict[str, Any]]) -> List[str]:
    """Prefer table names from metadata; dedup while preserving order."""
    seen = set()
    out: List[str] = []
    for r in results or []:
        t = ((r or {}).get("metadata") or {}).get("source_table")
        if not t:
            continue
        u = str(t).upper()
        if u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= 12:
            break
    return out


# ---------------------------
# Live metadata → runtime options
# ---------------------------
@lru_cache(maxsize=256)
def _fk_edges(selected_db: str, tables_key: tuple) -> List[Dict[str, str]]:
    """
    Build FK join edges among the provided tables using live metadata.
    Cached by (selected_db, tuple_of_tables).
    Returns edges like {"left":"CHILD.COL", "right":"PARENT.COL", "type":"INNER"}.
    """
    tables = list(tables_key)
    if not tables:
        return []
    placeholders = ",".join([f":t{i}" for i in range(len(tables))])
    qs = f"""
    SELECT ac.table_name child_table, acc.column_name child_col,
           pk.table_name parent_table, acc_pk.column_name parent_col
      FROM all_constraints ac
      JOIN all_cons_columns acc
        ON acc.owner = ac.owner AND acc.constraint_name = ac.constraint_name
      JOIN all_constraints pk
        ON pk.owner = ac.r_owner AND pk.constraint_name = ac.r_constraint_name
      JOIN all_cons_columns acc_pk
        ON acc_pk.owner = pk.owner AND acc_pk.constraint_name = pk.constraint_name AND acc_pk.position = acc.position
     WHERE ac.constraint_type = 'R'
       AND ac.owner = USER
       AND ac.table_name IN ({placeholders})
       AND pk.table_name IN ({placeholders})
    """
    edges: List[Dict[str, str]] = []
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        params = {f"t{i}": t for i, t in enumerate(tables)}
        try:
            cur.execute(qs, {**params, **params})
            for child_t, child_c, parent_t, parent_c in cur.fetchall():
                edges.append({
                    "left": f"{str(child_t).upper()}.{str(child_c).upper()}",
                    "right": f"{str(parent_t).upper()}.{str(parent_c).upper()}",
                    "type": "INNER",
                })
        except Exception as e:
            logger.warning(f"[RAG] FK edge discovery failed: {e}")
        finally:
            try: cur.close()
            except Exception: pass
    return edges



def _build_runtime_options(selected_db: str, tables: List[str],
                           limit_tables: int = 6, limit_cols: int = 60) -> Dict[str, Any]:
    """
    Build dynamic options strictly from live Oracle metadata for a *small* set of tables.
    Keeping this tight is what tends to make the planner accurate.
    """
    picked = _filter_banned_tables((tables or [])[:limit_tables])
    columns: Dict[str, List[Dict[str, str]]] = {}
    date_cols: Dict[str, List[str]] = {}
    num_cols: Dict[str, List[str]] = {}
    txt_cols: Dict[str, List[str]] = {}

    for t in picked:
        meta = _get_table_colmeta(selected_db, t)
        if not meta:
            continue

        # sorted by column name for determinism
        items = sorted(meta.items(), key=lambda kv: kv[0])

        # Per-type pools
        d = [c for c, dt in items if ("DATE" in dt) or ("TIMESTAMP" in dt)]
        n = [c for c, dt in items if any(k in dt for k in ("NUMBER", "FLOAT", "INTEGER", "BINARY"))]
        x = [c for c, dt in items if any(k in dt for k in ("CHAR", "VARCHAR", "NCHAR", "CLOB"))]

        date_cols[t] = d
        num_cols[t] = n
        txt_cols[t] = x

        columns[t] = [{"name": c, "type": dt} for c, dt in items[:limit_cols]]

    joins = _fk_edges(selected_db, tuple(t for t in picked if t in columns))


    return {
        "tables": [t for t in picked if t in columns],  # keep only tables that resolved to columns
        "columns": columns,
        "date_columns": date_cols,
        "numeric_columns": num_cols,
        "text_columns": txt_cols,
        "joins": joins,   # NEW: allowed join edges discovered from FKs
    }


# ---------------------------
# Planner
# ---------------------------

def _planner_prompt(user_query: str, options: Dict[str, Any]) -> str:
    """
    Planner prompt that returns JSON only. It now supports:
    - order_by, limit
    - optional 2-table join (restricted to OPTIONS.joins)
    - TO_CHAR(<date_col>,'MON-YY'|'MON-YYYY') dims via {"expr": "...", "as": "..."}
    """
    return f"""
You are a SQL planning assistant. Choose only from the provided tables, columns, and joins.
Do NOT invent names. Return ONLY valid JSON, no preface, no trailing text.

USER QUESTION:
{user_query}

OPTIONS (from live Oracle metadata):
{json.dumps(options, indent=2)}

Return JSON with one of these schemas:

1) Single-table plan
{{
  "table": "<one table from options.tables>",
  "dims": ["<0..2 column names>", {{ "expr": "TO_CHAR(<date_col>,'MON-YY')", "as": "MONTH" }}],
  "metrics": ["<0..3 numeric columns>"],
  "date_col": "<optional: one from options.date_columns[table]>",
  "filters": [{{"col":"<col>","op":"="|"LIKE"|"IN"|">="|"<="|">"|"<","val":<value>}}],
  "order_by": [{{"key":"<metric_or_dim_or_alias>","dir":"DESC|ASC"}}],
  "limit": <integer 1..500>
}}

2) Two-table plan (only if necessary, and only using OPTIONS.joins; at most two tables)
{{
  "tables": ["<t1>","<t2>"],
  "joins": [{{"left":"T1.COL","right":"T2.COL","type":"INNER"}}],
  "dims": ["<0..2 column names from the FIRST table only>", {{ "expr": "TO_CHAR(<date_col>,'MON-YY')", "as":"MONTH" }}],
  "metrics": ["<0..3 numeric columns from the FIRST table only>"],
  "date_col": "<optional date col from the FIRST table>",
  "filters": [{{"col":"<col from EITHER table>","op":"="|"LIKE"|...,"val":<value>}}],
  "order_by": [{{"key":"<metric_or_dim_or_alias>","dir":"DESC|ASC"}}],
  "limit": <integer 1..500>
}}

Rules:
- If the user asks for monthly rollups or a format like MON-YY/MON-YYYY, include a TO_CHAR(<date_col>,'MON-YY'|'MON-YYYY') dimension with alias "MONTH".
- If the user asks for "max", "top N", or "just one row", set order_by on the primary metric DESC and set limit accordingly.
- Prefer a single-table plan unless a join is clearly needed. If joining, you MUST use only a join present in OPTIONS.joins and only two tables.
- Use only columns present in OPTIONS.columns for the chosen table(s). Never invent names.
- If you are certain of the full SELECT, you MAY return {{ "sql": "<SELECT ...>" }} instead of a plan.
- If nothing matches the question, return {{ "decision": "fallback" }}.
- Never add a date/time filter unless the user explicitly mentions a date, month, year, or a relative window (e.g., "last month", "May 2024", "2024", "24/05/2024").
- If the user doesn't specify time, do NOT filter by date. You may include a TO_CHAR(<date_col>, ...) dimension for grouping if asked, but no WHERE on dates.
- Do NOT echo or copy OPTIONS back. If unsure, return {{ "decision":"fallback" }} only.
- If the user requests a time window, do not add equality/LIKE predicates on any other date columns (e.g., LAST_UPDATE = '...'). Use only the range on the chosen date column.
""".strip()


def _extract_first_json(text: str) -> Optional[dict]:
    """Tolerant JSON sniffer: accepts exact or first {...} block."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _ask_planner(user_query: str, options: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call the planner LLM and parse JSON."""
    try:
        prompt = _planner_prompt(user_query, options)
        raw = ask_sql_planner(prompt)
        plan = _extract_first_json((raw or "").strip().strip("`"))
        logger.debug("[RAG] planner_raw=%s", (raw or "")[:1000])
        logger.debug("[RAG] planner_json=%s", plan)
        return plan
    except Exception as e:
        logger.warning(f"[Planner] failed: {e}")
        return None


def _validate_tochar_dim(dim_obj: dict, table: str, options: Dict[str, Any]) -> bool:
    """Allow dims with TO_CHAR(<date_col>,'FMT') AS <alias>."""
    expr = (dim_obj or {}).get("expr", "")
    m = _TOCHAR_RX.match(expr or "")
    if not m:
        return False
    col, fmt = m.group(1), (m.group(2) or "").upper()
    if fmt not in _TOCHAR_WHITELIST:
        return False
    # must be a real date/timestamp column of the base table
    date_cols = set(options.get("date_columns", {}).get(table, []))
    return col in date_cols

def _validate_plan(plan: Dict[str, Any], options: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Strict plan validator. Every identifier must exist in options.
    Supports either:
      - single-table {"table": ...}
      - two-table {"tables": [t1, t2], "joins": [...]} with joins restricted to options["joins"].

    Relaxed rule: filters may reference columns (or TO_CHAR of date columns) from either side
    of the join. Dimensions, metrics, and date_col remain restricted to the FIRST table.
    """
    if not plan or not isinstance(plan, dict):
        return False, "no plan"

    if plan.get("decision") == "fallback":
        return False, "fallback"

    # If planner returned raw SQL in 'sql'/'query', that's OK — caller will validate it later.
    if isinstance(plan.get("sql") or plan.get("query"), str):
        return True, None

    tables_opt = options.get("tables") or []
    cols_by_tbl = {tbl: {c["name"] for c in options.get("columns", {}).get(tbl, [])} for tbl in tables_opt}
    nums_by_tbl = {tbl: set(options.get("numeric_columns", {}).get(tbl, [])) for tbl in tables_opt}
    dates_by_tbl = {tbl: set(options.get("date_columns", {}).get(tbl, [])) for tbl in tables_opt}
    allowed_joins = options.get("joins") or []

    # Accept either "table" or "tables"+"joins"
    t = plan.get("table")
    tables = plan.get("tables") or []
    joins = plan.get("joins") or []

    use_two_tables = bool(tables and joins)
    base_table: Optional[str] = None

    if use_two_tables:
        if len(tables) > 2:
            return False, "too many tables"
        for tt in tables:
            if tt not in tables_opt:
                return False, "invalid table in join"

        # joins must be subset of allowed_joins (match left/right/type; allow either direction)
        edge_set = {(e["left"], e["right"], (e.get("type") or "INNER").upper()) for e in allowed_joins}
        for j in joins:
            left = (j.get("left") or "").upper()
            right = (j.get("right") or "").upper()
            jtype = (j.get("type") or "INNER").upper()
            if (left, right, jtype) not in edge_set and (right, left, jtype) not in edge_set:
                return False, "invalid join edge"
        base_table = tables[0]  # dims/metrics/date_col restricted to FIRST table
    else:
        if not t or t not in tables_opt:
            return False, "invalid table"
        base_table = t

    # Determine second_table for relaxed filter validation
    second_table = tables[1] if use_two_tables and len(tables) == 2 else None

    dims = plan.get("dims") or []
    metrics = plan.get("metrics") or []
    date_col = plan.get("date_col", None)

    # ---------- Filters normalization & basic structure checks ----------
    # Make sure filters is always a list[dict]. Accept dict -> [dict], try JSON if string.
    filters_raw = plan.get("filters", [])
    if isinstance(filters_raw, list):
        filters = filters_raw
    elif isinstance(filters_raw, dict):
        filters = [filters_raw]
    elif isinstance(filters_raw, str):
        # Attempt to parse a JSON string form
        try:
            parsed = json.loads(filters_raw)
            if isinstance(parsed, dict):
                filters = [parsed]
            elif isinstance(parsed, list):
                filters = parsed
            else:
                return False, "Filters must be a list of dictionaries"
        except Exception:
            return False, "Filters must be a list of dictionaries"
    elif filters_raw in (None, ""):
        filters = []
    else:
        return False, "Filters must be a list of dictionaries"

    # Every filter item must be a dict with at least a 'col' key
    for f in filters:
        if not isinstance(f, dict):
            return False, "Invalid filter format"
        if "col" not in f:
            return False, "Invalid filter format"

    # ---- Dimensions: only columns of the base table or TO_CHAR(<date_col>,'FMT') ----
    for d in dims:
        if isinstance(d, str):
            if d in cols_by_tbl[base_table]:
                continue
            # allow a bare TO_CHAR(...) string as a dim
            m = _TOCHAR_RX.match(d or "")
            if m:
                dcol, fmt = m.group(1), (m.group(2) or "").upper()
                if fmt in _TOCHAR_WHITELIST and dcol in dates_by_tbl[base_table]:
                    continue
            return False, "invalid dim"
        elif isinstance(d, dict):
            if not _validate_tochar_dim(d, base_table, options):
                return False, "invalid tochar dim"
        else:
            return False, "invalid dim type"

    # ---- Metrics must be numeric columns of the base table (validate even if no dims) ----
    for mcol in metrics:
        if mcol not in nums_by_tbl[base_table]:
            return False, "invalid metric"

    # ---- date_col, if present, must be a date/timestamp column of the base table ----
    if date_col is not None and date_col not in dates_by_tbl[base_table]:
        return False, "invalid date_col"

    # ---- Filters: allow plain cols or TO_CHAR(<date_col>,'FMT')
    #               (now from either base_table OR second_table if present) ----
    ALLOWED_OPS = {"=", "LIKE", "IN", ">=", "<=", ">", "<", "BETWEEN"}
    for f in filters:
        c = f.get("col")
        op = f.get("op")
        if op not in ALLOWED_OPS:
            return False, "invalid op"
        if op == "BETWEEN" and not (isinstance(f.get("val"), list) and len(f["val"]) == 2):
            return False, "invalid op"

        okcol = False
        if isinstance(c, str):
            # plain column on base or second table
            if c in cols_by_tbl.get(base_table, set()):
                okcol = True
            elif second_table and c in cols_by_tbl.get(second_table, set()):
                okcol = True
            else:
                # TO_CHAR(date_col,'FMT') allowed from either table's date columns
                m = _TOCHAR_RX.match(c or "")
                if m:
                    dcol, fmt = m.group(1), (m.group(2) or "").upper()
                    if fmt in _TOCHAR_WHITELIST and (
                        dcol in dates_by_tbl.get(base_table, set())
                        or (second_table and dcol in dates_by_tbl.get(second_table, set()))
                    ):
                        okcol = True

        if not okcol:
            return False, "invalid filter content"

    # order_by/limit are optional; keys are checked later by the SQL builder
    return True, None

def _enhanced_employee_lookup(user_query: str, selected_db: str, enhanced_analysis: Dict) -> Dict[str, Any]:
    """Enhanced employee lookup using intent analysis."""
    try:
        # Extract person name or role from query
        query_lower = user_query.lower()
        
        # Extract the person's name from the query
        name_patterns = [
            r'email.*(?:address\s+)?of\s+(\w+)',
            r'give\s+me\s+email.*of\s+(\w+)',
            r'(\w+).*email',
            r'who\s+is\s+(?:employee\s+)?(\w+)'
        ]
        
        person_name = None
        for pattern in name_patterns:
            match = re.search(pattern, query_lower)
            if match:
                person_name = match.group(1).upper()
                break
        
        # Determine what information is being requested
        wants_email = any(word in query_lower for word in ['email', 'contact', 'address'])
        wants_salary = any(word in query_lower for word in ['salary', 'pay', 'wage'])
        
        # For T_USERS table (since the query went there), select appropriate columns
        if wants_email:
            columns_str = "USER_ID, USERNAME, FULL_NAME, EMAIL_ADDRESS, PHONE_NUMBER"
        elif wants_salary:
            columns_str = "USER_ID, USERNAME, FULL_NAME"  # T_USERS doesn't have salary
        else:
            columns_str = "USER_ID, USERNAME, FULL_NAME, EMAIL_ADDRESS"
        
        # Build the SQL for T_USERS table
        if person_name:
            sql = f"""
            SELECT {columns_str}
            FROM T_USERS 
            WHERE (UPPER(USERNAME) LIKE '%{person_name}%' 
                   OR UPPER(FULL_NAME) LIKE '%{person_name}%')
            ORDER BY USER_ID
            FETCH FIRST 5 ROWS ONLY
            """
        else:
            # Generic user search
            sql = f"""
            SELECT {columns_str}
            FROM T_USERS 
            ORDER BY USER_ID
            FETCH FIRST 10 ROWS ONLY
            """
        
        logger.info(f"[RAG] Enhanced employee lookup SQL: {sql}")
        
        # Execute query
        rows = run_sql(sql, selected_db)
        
        # Format results
        display_mode = determine_display_mode(user_query, rows)
        rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
        
        # Use enhanced summarizer for employee lookup
        python_summary = summarize_results(
            rows_for_summary,
            user_query,
            sql
        ) if display_mode in ["summary", "both"] else ""
        try:
            from decimal import Decimal
            summary = summarize_with_mistral(
                user_query=user_query,
                columns=list(rows[0].keys()) if rows else [],
                rows=rows,
                backend_summary=python_summary,
                sql=sql,
            ) if SUMMARY_ENGINE == "llm" and display_mode in ["summary","both"] else python_summary
        except Exception as e:
            logger.error(f"Natural language summary error: {e}")
            summary = f"Found {len(rows)} records matching your query."

            return {
                "status": "success",
                "summary": summary if display_mode in ["summary","both"] else "",
                "sql": sql,
                "display_mode": display_mode,
                "visualization": visualization_requested,
                "results": {
                    "columns": (list(rows[0].keys()) if rows else []),
                    "rows": [list(r.values()) for r in rows] if rows else [],
                    "row_count": len(rows) if rows else 0,
                },
                "schema_context": schema_chunks,
                "schema_context_ids": schema_context_ids,
                "hybrid_metadata": hybrid_result.get("hybrid_metadata") if hybrid_result else None,
            }
        except Exception as e:
            return {"status": "error", "message": f"Oracle query failed: {e}", "sql": sql}
        
    except Exception as e:
        logger.error(f"[RAG] Enhanced employee lookup failed: {e}")
        # Fall back to generic entity lookup
        return _entity_lookup_path(user_query, selected_db, [], [])
    
def _enhanced_tna_task_lookup(user_query: str, selected_db: str, enhanced_analysis: Dict) -> Dict[str, Any]:
    """Enhanced TNA task lookup using intent analysis."""
    try:
        # Initialize empty variables that will be used in the return statement
        schema_chunks = []
        schema_context_ids = []
        hybrid_result = None
        
        # Check for visualization intent
        from app.query_classifier import has_visualization_intent
        visualization_requested = has_visualization_intent(user_query)
        
        ql = (user_query or "").lower()
        # Highest priority: exact CTL job number (CTL-NN-NNNNN or CTL-NN-NNNNNN)
        ctl_match = re.search(r'\bCTL-\d{2}-\d{5,6}\b', user_query, re.IGNORECASE)
        if ctl_match:
            full_ctl = ctl_match.group(0).upper()
            # Check for task number filter
            task_filter = ""
            task_match = re.search(r'\btask\s+(?:number\s+)?(\d+)\b', user_query, re.IGNORECASE)
            if task_match:
                task_number = task_match.group(1)
                task_filter = f" AND TASK_NUMBER = {task_number}"
                logger.info(f"[RAG] Adding task number filter: {task_number}")
            
            # Comprehensive date detection for any format
            date_filter = ""
            try:
                # Enhanced date pattern matching (covers ALL common formats)
                date_patterns = [
                    # DD/MM/YYYY and DD-MM-YYYY
                    (r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', 'dmy'),
                    # MM/DD/YYYY and MM-DD-YYYY
                    (r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', 'mdy'),
                    # DD-MON-YY and DD-MON-YYYY (Oracle style)
                    (r'\b(\d{1,2})-([A-Z]{3})-(\d{2,4})\b', 'dd_mon_yy'),
                    # DD MMM YYYY (space separated)
                    (r'\b(\d{1,2})\s+([A-Z]{3,9})\s+(\d{4})\b', 'dd_mmm_yyyy'),
                    # YYYY-MM-DD (ISO format)
                    (r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', 'iso'),
                    # MON-YY and Month YYYY
                    (r'\b([A-Z]{3,9})[-\s](\d{2,4})\b', 'mon_yy')
                ]
                
                date_obj = None
                for pattern, format_type in date_patterns:
                    match = re.search(pattern, user_query.upper())
                    if match:
                        try:
                            if format_type == 'dmy':
                                day, month, year = match.groups()
                                date_obj = _dt(int(year), int(month), int(day))
                            elif format_type == 'mdy':
                                month, day, year = match.groups()
                                date_obj = _dt(int(year), int(month), int(day))
                            elif format_type == 'dd_mon_yy':
                                day, month_str, year = match.groups()
                                month_abbr = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                                            'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                                month = month_abbr.get(month_str.upper())
                                if month:
                                    year_int = int(year)
                                    if year_int < 100:
                                        year_int += 2000
                                    date_obj = _dt(year_int, month, int(day))
                            elif format_type == 'dd_mmm_yyyy':
                                day, month_str, year = match.groups()
                                month_abbr = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                                            'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12,
                                            'JANUARY':1,'FEBRUARY':2,'MARCH':3,'APRIL':4,'MAY':5,'JUNE':6,
                                            'JULY':7,'AUGUST':8,'SEPTEMBER':9,'OCTOBER':10,'NOVEMBER':11,'DECEMBER':12}
                                month = month_abbr.get(month_str.upper())
                                if month:
                                    date_obj = _dt(int(year), month, int(day))
                            elif format_type == 'iso':
                                year, month, day = match.groups()
                                date_obj = _dt(int(year), int(month), int(day))
                            elif format_type == 'mon_yy':
                                month_str, year = match.groups()
                                month_abbr = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                                            'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                                month = month_abbr.get(month_str.upper())
                                if month:
                                    year_int = int(year)
                                    if year_int < 100:
                                        year_int += 2000
                                    date_obj = _dt(year_int, month, 1)
                            
                            if date_obj:
                                oracle_date = f"TO_DATE('{date_obj.day:02d}-{['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][date_obj.month-1]}-{date_obj.year}','DD-MON-YYYY')"
                                date_filter = f" AND TASK_FINISH_DATE = {oracle_date}"
                                logger.info(f"[RAG] Adding date filter: {match.group(0)} -> {oracle_date}")
                                break
                        except (ValueError, IndexError) as e:
                            logger.warning(f"[RAG] Failed to parse date {match.group(0)}: {e}")
                            continue
                
            except Exception as e:
                logger.warning(f"[RAG] Date extraction failed in CTL lookup: {e}")
            
            sql = f"""
            SELECT JOB_NO, PO_NUMBER, TASK_SHORT_NAME, TASK_FINISH_DATE,
                   ACTUAL_FINISH_DATE, BUYER_NAME, STYLE_REF_NO, STYLE_DESCRIPTION
            FROM T_TNA_STATUS
            WHERE UPPER(JOB_NO) = '{full_ctl}'{task_filter}{date_filter}
            ORDER BY TASK_NUMBER DESC
            FETCH FIRST 50 ROWS ONLY
            """
            logger.info(f"[RAG] CTL pattern detected → exact JOB_NO match: {full_ctl}{' with task filter' if task_filter else ''}{' with date filter' if date_filter else ''}")
            rows = run_sql(sql, selected_db)
            display_mode = determine_display_mode(user_query, rows)
            rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
            python_summary = summarize_results(
                rows_for_summary,
                user_query,
                sql,
            ) if display_mode in ["summary","both"] else ""
            try:
                from decimal import Decimal
                # Import SUMMARY_ENGINE to avoid "not defined" error
                from app.config import SUMMARY_ENGINE
                summary = summarize_with_mistral(
                    user_query=user_query,
                    columns=list(rows[0].keys()) if rows else [],
                    rows=rows,
                    backend_summary=python_summary,
                    sql=sql,
                ) if SUMMARY_ENGINE == "llm" and display_mode in ["summary","both"] else python_summary
            except Exception as e:
                logger.error(f"Natural language summary error: {e}")
                summary = f"Found {len(rows)} records matching your query."

            return {
                "status": "success",
                "summary": summary if display_mode in ["summary","both"] else "",
                "sql": sql,
                "display_mode": display_mode,
                "visualization": visualization_requested, 
                "results": {
                    "columns": (list(rows[0].keys()) if rows else []),
                    "rows": [list(r.values()) for r in rows] if rows else [],
                    "row_count": len(rows) if rows else 0,
                },
                "schema_context": schema_chunks,
                "schema_context_ids": schema_context_ids,
                "hybrid_metadata": hybrid_result.get("hybrid_metadata") if hybrid_result else None,
            }
        # ----------------------------------------------
        # Recognize key task phrases (PP Approval first)
        # ----------------------------------------------
        if 'pp approval' in ql:
            sql = """
            SELECT JOB_NO, PO_NUMBER, TASK_SHORT_NAME, TASK_FINISH_DATE,
                   ACTUAL_FINISH_DATE, BUYER_NAME, STYLE_REF_NO
            FROM T_TNA_STATUS
            WHERE UPPER(TASK_SHORT_NAME) LIKE '%PP APPROVAL%'
            ORDER BY TASK_FINISH_DATE DESC
            FETCH FIRST 20 ROWS ONLY
            """
        else:
            task_patterns = [
                r'pp\s+approval',
                r'fabric.*receive',
                r'cutting.*production',
                r'sewing.*production',
                r'garment.*inspection',
                r'ex.*factory',
                r'knit.*fabric'
            ]
            sql = None
            for pat in task_patterns:
                m = re.search(pat, ql, re.IGNORECASE)
                if m:
                    task_term = re.sub(r'\s+', '%', m.group(0))  # space→% for LIKE
                    esc = task_term.replace("'", "''")
                    sql = f"""
                    SELECT JOB_NO, PO_NUMBER, TASK_SHORT_NAME, TASK_FINISH_DATE,
                           ACTUAL_FINISH_DATE, BUYER_NAME, STYLE_REF_NO
                    FROM T_TNA_STATUS
                    WHERE UPPER(TASK_SHORT_NAME) LIKE UPPER('%{esc}%')
                    ORDER BY TASK_FINISH_DATE DESC
                    FETCH FIRST 20 ROWS ONLY
                    """
                    break

            if sql is None:
                # generic recent tasks
                sql = """
                SELECT JOB_NO, PO_NUMBER, TASK_SHORT_NAME, TASK_FINISH_DATE,
                       ACTUAL_FINISH_DATE, BUYER_NAME, STYLE_REF_NO
                FROM T_TNA_STATUS
                ORDER BY TASK_FINISH_DATE DESC
                FETCH FIRST 20 ROWS ONLY
                """

        logger.info(f"[RAG] Enhanced TNA task lookup SQL: {sql.strip()}")

        rows = run_sql(sql, selected_db)
        display_mode = determine_display_mode(user_query, rows)
        rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
        python_summary = summarize_results(
            rows_for_summary,
            user_query,
        ) if display_mode in ["summary", "both"] else ""
        
        try:
            # Import SUMMARY_ENGINE to avoid "not defined" error
            from app.config import SUMMARY_ENGINE
            
            summary = (
                summarize_with_mistral(
                    user_query=user_query,
                    columns=list(rows_for_summary[0].keys()) if rows_for_summary else [],
                    rows=rows_for_summary,
                    backend_summary=python_summary,
                    sql=sql,
                )
                if SUMMARY_ENGINE == "llm" and display_mode in ["summary", "both"]
                else python_summary
            )
        except Exception as e:
            logger.error(f"[RAG] Summary generation failed: {e}")
            summary = python_summary
        
        # Then modify the return statement to include the visualization flag:
        return {
            "status": "success",
            "summary": summary if display_mode in ["summary", "both"] else "",
            "sql": sql,
            "display_mode": display_mode,
            "visualization": visualization_requested,
            "results": {
                "columns": (list(rows[0].keys()) if rows else []),
                "rows": [list(r.values()) for r in rows] if rows else [],
                "row_count": len(rows) if rows else 0,
            },
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
        } 

    except Exception as e:
        logger.error(f"[RAG] Enhanced TNA task lookup failed: {e}")
        return _entity_lookup_path(user_query, selected_db, [], [])


# ---------------------------
# Fallback: entity lookup
# ---------------------------
def _entity_lookup_path(user_query: str, selected_db: str,
                        schema_chunks: List[str],
                        schema_context_ids: List[str]) -> Dict[str, Any]:
    """
    Try to resolve queries like IDs, codes, job numbers, barcodes, names, etc.
    Uses quick column candidates + LIKE probe; never invents identifiers.
    """

    # NEW: ID/NO/CODE fast-path
    hit = _extract_id_lookup(user_query)
    if hit:
        id_val = hit["value"]
        hint = hit["hint_table"]
        id_cols = _list_id_like_columns(selected_db)

        # Prefer tables that match the hint (e.g., SHIPMENTS for "shipment id ...")
        if hint:
            id_cols = [x for x in id_cols if hint in x["table"].upper()] or id_cols

        # Probe a few promising columns quickly using equality (not LIKE)
        best = None
        try:
            with connect_to_source(selected_db) as (conn, _):
                cur = conn.cursor()
                _set_case_insensitive_session(cur)
                for x in id_cols:
                    t, c, dt = x["table"], x["column"], x["dtype"]
                    try:
                        if any(k in dt for k in ("NUMBER", "INTEGER", "FLOAT", "BINARY")):
                            cur.execute(f"SELECT 1 FROM {t} WHERE {c} = :v AND ROWNUM = 1", v=id_val)
                        else:
                            cur.execute(f"SELECT 1 FROM {t} WHERE {c} = :v AND ROWNUM = 1", v=str(id_val))
                        if cur.fetchone():
                            best = (t, c, dt)
                            break
                    except Exception:
                        continue
        except Exception:
            pass

        if best:
            t, c, dt = best
            if any(k in dt for k in ("NUMBER", "INTEGER", "FLOAT", "BINARY")):
                sql = f"SELECT * FROM {t} WHERE {c} = {id_val} FETCH FIRST 200 ROWS ONLY"
            else:
                id_val_esc = str(id_val).replace("'", "''")
                sql = f"SELECT * FROM {t} WHERE {c} = '{id_val_esc}' FETCH FIRST 200 ROWS ONLY"
            try:
                rows = run_sql(sql, selected_db)
                display_mode = determine_display_mode(user_query, rows)
                rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
                py_sum = summarize_results(
                    rows_for_summary,
                    user_query,
                ) if display_mode in ["summary", "both"] else ""
                if display_mode in ["summary", "both"]:
                    summary = (
                        summarize_with_mistral(
                            user_query=user_query,
                            columns=list(rows_for_summary[0].keys()) if rows_for_summary else [],
                            rows=rows_for_summary,
                            backend_summary=py_sum,
                            sql=sql,
                        )
                        if SUMMARY_ENGINE == "llm"
                        else py_sum
                    )
                else:
                    summary = ""
                if trend_intent:
                    # Prefer the trend-focused summary we just generated
                    summary = python_summary
                else:
                    # Use the API-based summarizer for all cases
                    summary = (
                        summarize_results(
                            rows,
                            user_query,
                            sql,
                        )
                        if SUMMARY_ENGINE == "llm" and display_mode in ["summary", "both"]
                        else python_summary
                    )

                return {
                    "status": "success",
                    "summary": summary,
                    "sql": sql,
                    "display_mode": display_mode,
                    "results": {
                        "columns": (list(rows[0].keys()) if rows else []),
                        "rows": [list(r.values()) for r in rows] if rows else [],
                        "row_count": len(rows) if rows else 0,
                    },
                    "schema_context": schema_chunks,
                    "schema_context_ids": schema_context_ids,
                }
            except Exception as e:
                return {"status": "error", "message": f"Oracle query failed: {e}", "sql": sql}

    # … fall through to the existing name/text entity logic afterwards …

    needle = _needle_from_question(user_query)
    candidates = _candidate_columns(selected_db, user_query)
    if len(candidates) < 5:
        meta_cols = _list_name_like_columns(selected_db, query_text=user_query)
        candidates = _merge_candidates(candidates, meta_cols, cap=200)

    probe_hits = _quick_value_probe(selected_db, needle, candidates)
    if not probe_hits:
        return {
            "status": "success",
            "summary": "No matching entities found.",
            "sql": None,
            "display_mode": "summary",
            "results": {"columns": [], "rows": [], "row_count": 0},
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
        }

    # Select the most frequent (table, column) from probe hits
    from collections import Counter
    cc = Counter((h["table"], h["column"]) for h in probe_hits)
    ranked = sorted(cc.items(), key=lambda kv: kv[1], reverse=True)
    best_pair = next(((t, c) for (t, c), _cnt in ranked if not _is_banned_table(t)), None)
    if not best_pair:
        return {
            "status": "success",
            "summary": "No matching entities found.",
            "sql": None,
            "display_mode": "summary",
            "results": {"columns": [], "rows": [], "row_count": 0},
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
        }

    best_table, best_col = best_pair
    esc = needle.upper().replace("'", "''")
    sql = f"SELECT * FROM {best_table} WHERE UPPER({best_col}) LIKE '%{esc}%' FETCH FIRST 200 ROWS ONLY"

    try:
        rows = run_sql(sql, selected_db)
        display_mode = determine_display_mode(user_query, rows)
        rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
        python_summary = summarize_results(
            rows_for_summary,
            user_query,
        ) if display_mode in ["summary", "both"] else ""
        if display_mode in ["summary", "both"]:
            summary = (
                summarize_with_mistral(
                    user_query=user_query,
                    columns=list(rows_for_summary[0].keys()) if rows_for_summary else [],
                    rows=rows_for_summary,
                    backend_summary=python_summary,
                    sql=sql,
                )
                if SUMMARY_ENGINE == "llm"
                else python_summary
            )
        else:
            summary = ""
        
        return {
            "status": "success",
            "summary": summary,
            "sql": sql,
            "display_mode": display_mode,
            "results": {
                "columns": (list(rows[0].keys()) if rows else []),
                "rows": [list(r.values()) for r in rows] if rows else [],
                "row_count": len(rows) if rows else 0,
            },
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
        }
    except Exception as e:
        logger.error(f"[EntityLookup] Oracle error: {e}")
        return {"status": "error", "message": f"Oracle query failed: {str(e)}", "sql": sql}

def _generic_browse_fallback(user_query: str, selected_db: str, options: Dict[str, Any],
                             schema_chunks: List[str], schema_context_ids: List[str]) -> Dict[str, Any]:
    """
    If the planner fails, show *something sensible*:
    pick the best-matching table from options and return SELECT * ... FETCH FIRST 200.
    """
    # ADD THESE TWO LINES
    visualization_requested = has_visualization_intent(user_query)
    hybrid_result = None
    
    tables = options.get("tables") or []
    if not tables:
        return {
            "status": "error",
            "message": "Planner failed and no candidate tables were available.",
            "schema_context_ids": schema_context_ids,
        }

    # score tables by overlap of user tokens with column names (lightweight & deterministic)
    toks = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", user_query or "") if len(t) >= 3]
    def tscore(t: str) -> int:
        cols = [c["name"] for c in (options.get("columns", {}).get(t, []) or [])]
        score = sum(any(tok in (cname.lower()) for tok in toks) for cname in cols)
        # gentle boost for obvious domain cues in table name
        if re.search(r"(pay|payment|import|lc|bill)", t, re.I):
            score += 3
        return score

    best = max(tables, key=tscore)
    sql = f"SELECT * FROM {best} FETCH FIRST 200 ROWS ONLY"

    try:
        rows = run_sql(sql, selected_db)
        display_mode = determine_display_mode(user_query, rows)
        rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
        python_summary = summarize_results(
            rows_for_summary,
            user_query,
        ) if display_mode in ["summary", "both"] else ""
        try:
            from decimal import Decimal
            summary = summarize_with_mistral(
                user_query=user_query,
                columns=list(rows[0].keys()) if rows else [],
                rows=rows,
                backend_summary=python_summary,
                sql=sql,
            ) if SUMMARY_ENGINE == "llm" and display_mode in ["summary","both"] else python_summary
        except Exception as e:
            logger.error(f"Natural language summary error: {e}")
            summary = f"Found {len(rows)} records matching your query."
    
        return {
            "status": "success",
            "summary": summary if display_mode in ["summary","both"] else "",
            "sql": sql,
            "display_mode": display_mode,
            "visualization": visualization_requested,   # now defined
            "results": {
                "columns": (list(rows[0].keys()) if rows else []),
                "rows": [list(r.values()) for r in rows] if rows else [],
                "row_count": len(rows) if rows else 0,
            },
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
            "hybrid_metadata": None,  # remove reference to out-of-scope variable
        }
    except Exception as e:
        logger.error(f"[Fallback] Oracle error: {e}")
        return {"status": "error", "message": f"Oracle query failed: {str(e)}", "sql": sql}
        
# Add this new function after existing functions but before answer()
def generate_natural_language_summary(
    user_query: str,
    columns: List[str],
    rows: List[Dict[str, Any]],
    sql: Optional[str] = None
) -> str:
    """
    Generate a natural language summary directly using the OpenRouter client.
    This is a simpler implementation that avoids asyncio complexities.
    """
    try:
        if not rows:
            return "No data found matching your criteria."
            
        # Format data for the prompt
        data_summary = f"Dataset with {len(rows)} records and {len(columns)} columns:\n"
        
        # Format sample records - show more data for better analysis
        sample_size = min(8, len(rows))  # Increased from 3 to 8
        sample_data = []
        for i in range(sample_size):
            row_data = []
            for col in columns:
                if col in rows[i] and rows[i][col] is not None:
                    value = rows[i][col]
                    if isinstance(value, (int, float, Decimal)):
                        if isinstance(value, Decimal):
                            value = float(value)
                        formatted_value = f"{value:,}" if value == int(value) else f"{value:,.2f}".rstrip('0').rstrip('.')
                    else:
                        formatted_value = str(value)
                    row_data.append(f"{col}={formatted_value}")
            sample_data.append(f"Record {i+1}: {', '.join(row_data)}")
            
        data_summary += "\n".join(sample_data)
        
        # For larger datasets, also mention that there are more records
        if len(rows) > sample_size:
            data_summary += f"\n... (showing first {sample_size} of {len(rows)} total records)"
        
        # Create the prompt
        prompt = f"""You are an intelligent data analyst for a manufacturing company. Your task is to provide a clear, natural language response to the user's question based on the query results.

User Question: "{user_query}"

Data Results:
{data_summary}

SQL Used: {sql or "N/A"}

Please provide a response that directly answers the user's question in natural, conversational language. Focus on the most relevant information and metrics. Avoid technical database terminology unless necessary. Do not start with phrases like "Based on the data" or "The results show".

Important: The dataset contains {len(rows)} total records. While only a sample is shown above for context, your analysis should consider the complete dataset when providing insights and trends.
"""
        
        # Use the OpenRouter client directly, no asyncio
        try:
            from app.openrouter_client import OpenRouterClient
            client = OpenRouterClient()
            
            # This is a synchronous version that handles async internally
            messages = [{"role": "user", "content": prompt}]
            model = "deepseek/deepseek-chat-v3.1:free"  # Changed from "deepseek/deepseek-chat"
            # Create the request payload
            max_tokens = SUMMARIZATION_CONFIG.get("api_max_tokens", 500)
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": max_tokens
            }
            
            # Use the OpenRouter client's HTTP request directly
            response = client._make_request_sync(payload)
            
            if response.success and response.content:
                return response.content
            else:
                logger.warning(f"OpenRouter summary failed: {response.error}")
                # Fall back to basic summary
                return f"Found {len(rows)} records matching your query."
                
        except Exception as e:
            logger.error(f"OpenRouter summary error: {e}")
            return f"Found {len(rows)} records matching your query."
            
    except Exception as e:
        logger.error(f"Natural language summary error: {e}")
        return f"Found {len(rows)} records matching your query."
# ---------------------------
# Public API
# ---------------------------
async def answer(
    user_query: str,
    selected_db: str,
    mode: str = "General",  # Add mode parameter with default value
    session_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main RAG orchestrator with hybrid AI processing and comprehensive training data collection.

    Args:
        user_query: The user's natural language query
        selected_db: Database to query against
        mode: Processing mode - "General", "SOS", or "Test DB"
        session_id: Session identifier for training data collection
        client_ip: Client IP address for training data collection
        user_agent: User agent string for training data collection

    Returns:
        Dictionary with query results and metadata
    """
    # Handle General mode queries (non-database queries)
    if mode == "General":
        # For general queries, use the hybrid processor's general query handling
        try:
            if HYBRID_PROCESSING_AVAILABLE:
                from app.hybrid_processor import HybridProcessor
                processor = HybridProcessor()
                
                # Process as a general knowledge query
                processing_result = await processor._process_general_query(
                    user_query=user_query,
                    schema_context="",  # No schema context needed for general queries
                )
                
                # Check if we got a valid response
                if processing_result and processing_result.selected_response:
                    # Check if this is an error response
                    if processing_result.processing_mode in ["general_query_api_error", "general_query_error"]:
                        # Return error response
                        return {
                            "status": "error",
                            "message": processing_result.selected_response,
                            "sql": None,
                            "schema_context": [],
                            "schema_context_ids": [],
                        }
                    
                    # Return successful response
                    return {
                        "status": "success",
                        "summary": processing_result.selected_response,
                        "sql": None,
                        "display_mode": "summary",
                        "results": {
                            "columns": [],
                            "rows": [],
                            "row_count": 0,
                        },
                        "schema_context": [],
                        "schema_context_ids": [],
                        "hybrid_metadata": {
                            "processing_mode": processing_result.processing_mode,
                            "selection_reasoning": processing_result.selection_reasoning,
                            "model_used": processing_result.model_used,
                            "processing_time": processing_result.processing_time,
                            "local_confidence": processing_result.local_confidence,
                            "api_confidence": processing_result.api_confidence,
                        }
                    }
            
            # For general mode, if hybrid processing is not available, return an error
            # rather than falling back to local model
            return {
                "status": "error",
                "message": "General mode is not available. Hybrid processing system is not enabled or configured properly.",
                "sql": None,
                "schema_context": [],
                "schema_context_ids": [],
            }
        except Exception as e:
            logger.error(f"[RAG] General query processing failed: {e}")
            return {
                "status": "error",
                "message": f"General query processing failed: {str(e)}",
                "sql": None,
                "schema_context": [],
                "schema_context_ids": [],
            }
    
    # For database modes (SOS, Test DB), continue with existing database processing
    uq = user_query.strip()
    if not uq:
        return {"status": "error", "message": "Empty query."}

    # Detect trend analysis intent (used to force a summary even if UI mode = table)
    trend_intent = bool(re.search(r"\btrend\s+analysis\b", uq, re.IGNORECASE))

    # Enhanced query analysis for dynamic processing
    enhanced_analysis = analyze_enhanced_query(uq)
    logger.info(
        f"[RAG] Enhanced analysis: {enhanced_analysis['intent']} "
        f"({enhanced_analysis['intent_confidence']:.2f})"
    )
    visualization_requested = has_visualization_intent(user_query)

    # Enhanced intent-based routing - use enhanced analysis before vector search
    if enhanced_analysis["intent"] == "employee_lookup":
        logger.info("[RAG] Routing to employee lookup based on enhanced analysis")
        return _enhanced_employee_lookup(uq, selected_db, enhanced_analysis)

    # NEW: TNA/task routing
    if enhanced_analysis["intent"] in ("tna_task_query", "tna_task_data"):
        logger.info("[RAG] Routing to TNA task query based on enhanced analysis")
        return _enhanced_tna_task_lookup(uq, selected_db, enhanced_analysis)

    # 0) Fast paths -------------------------------------------------------------
    # 0.a) Raw SELECT passthrough (validated)
    if re.match(r"(?is)^\s*select\b", uq):
        # Retrieve schema context for fast path
        results = _search_schema(user_query, selected_db, top_k=12)
        schema_chunks = [r.get("document") for r in results] if results else []
        schema_context_ids = _extract_context_ids(results)
        sql = normalize_dates(uq.rstrip(";"))
        try:
            enforce_predicate_type_compat(sql, selected_db)
            if not is_valid_sql(sql, selected_db):
                return {"status": "error", "message": "Invalid SQL", "sql": sql}

            rows = run_sql(sql, selected_db)
            display_mode = determine_display_mode(user_query, rows)

            # Build python_summary using async trend-aware summarizer when needed
            rows_for_summary = widen_results_if_needed(
                rows, sql, selected_db, display_mode, user_query
            )
            if display_mode in ["summary", "both"] or trend_intent:
                columns_for_summary = list(rows[0].keys()) if rows else []
                # Use the API-based summarizer instead of the basic one
                python_summary = await summarize_results_async(
                    results={"rows": rows_for_summary},
                    user_query=user_query,
                    columns=columns_for_summary,
                    sql=sql,
                )
            else:
                python_summary = ""

            try:
                from decimal import Decimal  # noqa: F401

                if trend_intent:
                    # Prefer the trend-focused summary we just generated
                    summary = python_summary
                else:
                    # Use the API-based summarizer for all cases
                    summary = (
                        summarize_results(
                            rows,
                            user_query,
                            sql,
                        )
                        if SUMMARY_ENGINE == "llm" and display_mode in ["summary", "both"]
                        else python_summary
                    )
            except Exception as e:
                logger.error(f"Natural language summary error: {e}")
                summary = f"Found {len(rows)} records matching your query."

            return {
                "status": "success",
                "summary": summary if (display_mode in ["summary", "both"] or trend_intent) else "",
                "sql": sql,
                "display_mode": display_mode,
                "visualization": visualization_requested,
                "results": {
                    "columns": (list(rows[0].keys()) if rows else []),
                    "rows": [list(r.values()) for r in rows] if rows else [],
                    "row_count": len(rows) if rows else 0,
                },
                "schema_context": schema_chunks,
                "schema_context_ids": schema_context_ids,
                "hybrid_metadata": None,
            }
        except Exception as e:
            return {"status": "error", "message": f"Oracle query failed: {e}", "sql": sql}

    # 0.b) "All table names" → system metadata
    if re.search(r"\ball\s+table\s+name(s)?\b", uq, re.I):
        try:
            with connect_to_source(selected_db) as (conn, _):
                cur = conn.cursor()
                cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
                rows = [{"TABLE_NAME": r[0]} for r in cur.fetchall()]
            return {
                "status": "success",
                "summary": "",
                "sql": "SELECT table_name FROM user_tables ORDER BY table_name",
                "display_mode": "table",
                "results": {
                    "columns": ["TABLE_NAME"],
                    "rows": [[r["TABLE_NAME"]] for r in rows],
                    "row_count": len(rows),
                },
                "schema_context": [],
                "schema_context_ids": [],
            }
        except Exception as e:
            return {"status": "error", "message": f"Oracle query failed: {e}"}

    # 1) Retrieve schema context from vector store -----------------------------
    results = _search_schema(user_query, selected_db, top_k=12)
    schema_chunks = [r.get("document") for r in results] if results else []
    schema_context_ids = _extract_context_ids(results)

    candidate_tables = _tables_from_results(results)
    candidate_tables = _filter_banned_tables(candidate_tables)

    # NEW: prioritize critical tables based on query content
    candidate_tables = _intelligent_table_selection(user_query, candidate_tables, selected_db)
    candidate_tables = _bias_tables_for_day(candidate_tables, uq)

    # NEW: if it's a single-day/"day" query, make sure daily tables are present
    if _DAILY_HINT_RX.search(uq):
        extras = _discover_dailyish_tables(selected_db, must_have_cols=("PRODUCTION_QTY", "FLOOR_NAME"))
        extras = _filter_banned_tables(extras)
        # keep order: already-retrieved tables first, then extras not already present
        seen = {t.upper() for t in candidate_tables}
        candidate_tables += [t for t in extras if t.upper() not in seen]

    # Force T_PROD vs T_PROD_DAILY ordering when applicable
    candidate_tables = _maybe_force_tprod_tables(uq, selected_db, candidate_tables)

    # Store the forced table information for hybrid processing
    forced_table = None
    if len(candidate_tables) == 1:
        forced_table = candidate_tables[0]

    # (optional safety) re-filter in case the forcing step ever reintroduces something
    candidate_tables = _filter_banned_tables(candidate_tables)

    # 2) Build runtime options from live metadata (keep this **tight**) --------
    options = _build_runtime_options(selected_db, candidate_tables)
    if not options.get("tables"):
        if _is_entity_lookup(user_query):
            return _entity_lookup_path(user_query, selected_db, schema_chunks, schema_context_ids)
        return {
            "status": "error",
            "message": "No relevant tables found.",
            "schema_context_ids": schema_context_ids,
        }

    # Phase 4.1: Try hybrid processing first if available and conditions are met
    hybrid_result = None
    if HYBRID_PROCESSING_AVAILABLE and _should_use_hybrid_processing(user_query, enhanced_analysis):
        logger.info("[RAG] Attempting hybrid processing for SQL generation")
        logger.info(f"[RAG] COLLECT_TRAINING_DATA is {COLLECT_TRAINING_DATA}")

        # Create an actual turn_id for training data collection if not available
        temp_turn_id = None
        if COLLECT_TRAINING_DATA:
            try:
                # Create actual AI_TURN record for training data collection during RAG processing
                from app.feedback_store import insert_turn

                temp_turn_id = insert_turn(
                    source_db_id="source_db_1",
                    client_ip=client_ip,
                    user_question=user_query,
                    schema_context_text="\n\n".join(schema_chunks[:5]),  # Limited context for temp record
                    schema_context_ids=schema_context_ids[:10] if schema_context_ids else [],
                    meta={
                        "temp_record_for_training": True,
                        "enhanced_analysis": enhanced_analysis.get("intent", "unknown")
                        if enhanced_analysis
                        else "unknown",
                    },
                )
                logger.info(f"[RAG] Created temporary turn_id {temp_turn_id} for training data collection")
            except Exception as e:
                logger.warning(f"[RAG] Failed to create temporary turn_id: {e}")

        # Pass the forced table information to hybrid processing
        hybrid_context_info = {
            "forced_table": forced_table,
            "date_cutoff_applied": forced_table in ["T_PROD", "T_PROD_DAILY"],
        }

        hybrid_result = await _try_hybrid_processing(
            user_query=user_query,
            schema_context="\n\n".join(schema_chunks),
            enhanced_analysis=enhanced_analysis,
            options=options,
            schema_chunks=schema_chunks,
            schema_context_ids=schema_context_ids,
            turn_id=temp_turn_id,  # Use actual turn_id for training data collection
            session_id=session_id,
            client_ip=client_ip,
            user_agent=user_agent,
            hybrid_context_info=hybrid_context_info,  # Pass the forced table information
        )

        if hybrid_result and hybrid_result.get("status") == "success":
            processing_mode = "unknown"
            if "hybrid_metadata" in hybrid_result and "processing_mode" in hybrid_result["hybrid_metadata"]:
                processing_mode = hybrid_result["hybrid_metadata"]["processing_mode"]
            elif "processing_mode" in hybrid_result:
                processing_mode = hybrid_result["processing_mode"]

            processing_mode = processing_mode or "unknown"
            logger.info(f"[RAG] Hybrid processing successful with {processing_mode} mode")

            result = hybrid_result.copy()
            result["schema_context"] = schema_chunks
            result["schema_context_ids"] = schema_context_ids
            result["hybrid_metadata"] = {
                "processing_mode": hybrid_result.get("processing_mode", "unknown"),
                "selection_reasoning": hybrid_result.get("selection_reasoning", ""),
                "model_used": hybrid_result.get("model_used", "unknown"),
                "processing_time": hybrid_result.get("processing_time", 0.0),
                "local_confidence": hybrid_result.get("local_confidence"),
                "api_confidence": hybrid_result.get("api_confidence"),
                "enhanced_schema_used": hybrid_result.get("enhanced_schema_used", False),
                "training_data_recorded": hybrid_result.get("training_data_recorded", False),
                "classification_time_ms": hybrid_result.get("classification_time_ms", 0.0),
                "sql_execution_time_ms": hybrid_result.get("sql_execution_time_ms", 0.0),
                "sql_execution_success": hybrid_result.get("sql_execution_success", False),
                "temp_turn_id": temp_turn_id,
            }
            return result
        else:
            logger.info("[RAG] Hybrid processing failed or returned no result, falling back to traditional RAG pipeline")

    # 3) Planner → STRICT validation ------------------------------------------
    plan = _ask_planner(user_query, options)

    # ---- Additional upfront plan structure check ----
    if not isinstance(plan, dict):
        return {
            "status": "error",
            "message": "Invalid plan format",
        }

    ok, why = _validate_plan(plan or {}, options)
    if not ok:
        logger.info(f"[RAG] Planner not directly usable ({why}).")
        if _is_entity_lookup(user_query):
            return _entity_lookup_path(user_query, selected_db, schema_chunks, schema_context_ids)
        # NEW: graceful table-browse fallback
        return _generic_browse_fallback(user_query, selected_db, options, schema_chunks, schema_context_ids)

    # NEW: add business-aware dims/metrics for critical tables
    plan = enhance_query_with_critical_table_knowledge(user_query, plan, options, selected_db)
    plan = _augment_plan_with_metrics(uq, plan, options)

    # (plan remains a dict after augmentation, but be defensive anyway)
    if not isinstance(plan, dict):
        return {
            "status": "error",
            "message": "Invalid plan format after augmentation",
        }

    ok, why = _validate_plan(plan or {}, options)
    if not ok:
        logger.info(f"[RAG] Plan invalid after augmentation ({why}).")
        if _is_entity_lookup(user_query):
            return _entity_lookup_path(user_query, selected_db, schema_chunks, schema_context_ids)
        return _generic_browse_fallback(uq, selected_db, options, schema_chunks, schema_context_ids)

    # If planner returned raw SQL, validate and use it; otherwise build from plan
    maybe_sql = (plan or {}).get("sql") or (plan or {}).get("query")
    try:
        if isinstance(maybe_sql, str) and maybe_sql.strip().lower().startswith("select"):
            sql = maybe_sql.strip().rstrip(";")
        else:
            sql = build_sql_from_plan(plan, selected_db, user_query)

        sql = normalize_dates(sql)
        sql = enforce_wide_projection_for_generic(user_query, sql)
        sql = value_aware_text_filter(sql, selected_db)
        sql = ensure_label_filter(sql, user_query, selected_db)
        enforce_predicate_type_compat(sql, selected_db)
        if not is_valid_sql(sql, selected_db):
            raise ValueError("Generated SQL failed prepare() validation")
    except Exception as e:
        logger.warning(f"[RAG] SQL build/validation error: {e}")
        if _is_entity_lookup(user_query):
            return _entity_lookup_path(user_query, selected_db, schema_chunks, schema_context_ids)
        return {
            "status": "error",
            "message": f"SQL generation failed: {str(e)}",
            "schema_context_ids": schema_context_ids,
        }

    # 4) Execute ---------------------------------------------------------------
    try:
        rows = run_sql(sql, selected_db)
    except Exception as e:
        logger.error(f"[RAG] Oracle error during execute: {e}")
        return {
            "status": "error",
            "message": f"Oracle query failed: {str(e)}",
            "sql": sql,
            "schema_context_ids": schema_context_ids,
        }

    # --- Retry path for day-level questions that returned 0 rows -------------
    if not rows and _DAILY_HINT_RX.search(uq):
        # Prefer only daily-ish tables from the earlier retrieval set
        daily_only = _filter_banned_tables([t for t in candidate_tables if _DAILY_NAME_RX.search(t)])
        if daily_only:
            # Apply T_PROD vs T_PROD_DAILY forcing within the daily-only set
            forced_daily = _maybe_force_tprod_tables(uq, selected_db, daily_only)
            options2 = _build_runtime_options(selected_db, forced_daily)
            plan2 = _ask_planner(uq, options2)

            # ---- Additional upfront check for retry plan as well ----
            if not isinstance(plan2, dict):
                logger.warning("[RAG] Daily retry planner returned invalid plan format")
            else:
                ok2, _ = _validate_plan(plan2 or {}, options2)
                if ok2:
                    try:
                        sql2 = build_sql_from_plan(plan2, selected_db, uq)
                        sql2 = normalize_dates(sql2)
                        sql2 = enforce_wide_projection_for_generic(uq, sql2)
                        sql2 = value_aware_text_filter(sql2, selected_db)
                        sql2 = ensure_label_filter(sql2, uq, selected_db)
                        enforce_predicate_type_compat(sql2, selected_db)
                        if is_valid_sql(sql2, selected_db):
                            rows2 = run_sql(sql2, selected_db)
                            if rows2:
                                # promote the successful retry to the main flow
                                sql, rows = sql2, rows2
                    except Exception as e:
                        logger.warning(f"[RAG] Daily retry failed: {e}")

    # 5) Summarize + format envelope ------------------------------------------
    display_mode = determine_display_mode(user_query, rows)

    rows_for_summary = widen_results_if_needed(
        rows, sql, selected_db, display_mode, user_query
    )
    if display_mode in ["summary", "both"] or trend_intent:
        columns_for_summary = list(rows[0].keys()) if rows else []
        python_summary = await summarize_results_async(
            results={"rows": rows_for_summary},
            user_query=user_query,
            columns=columns_for_summary,
            sql=sql,
        )
    else:
        python_summary = ""

    if display_mode in ["summary", "both"] or trend_intent:
        try:
            if trend_intent:
                summary = python_summary
            else:
                summary = summarize_with_mistral(
                    user_query=user_query,
                    columns=list(rows[0].keys()) if rows else [],
                    rows=rows,
                    backend_summary=python_summary,
                    sql=sql,
                )
        except Exception as e:
            logger.warning(f"[RAG] Natural language summary failed; falling back. Reason: {e}")
            summary = python_summary
    else:
        summary = ""

    # Check for visualization intent once (to avoid duplicate computation)
    visualization_requested = has_visualization_intent(user_query)

    # Special UX for explicit date-range queries → no data
    if not rows and extract_explicit_date_range(user_query):
        return {
            "status": "success",
            "summary": "No data found for the requested date range.",
            "sql": sql,
            "display_mode": determine_display_mode(user_query, []),
            "visualization": visualization_requested,
            "results": {"columns": [], "rows": [], "row_count": 0},
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
        }

    return {
        "status": "success",
        "summary": summary,
        "sql": sql,
        "display_mode": display_mode,
        "visualization": visualization_requested,
        "results": {
            "columns": (list(rows[0].keys()) if rows else []),
            "rows": [list(r.values()) for r in rows] if rows else [],
            "row_count": len(rows) if rows else 0,
        },
        "schema_context": schema_chunks,
        "schema_context_ids": schema_context_ids,
    }