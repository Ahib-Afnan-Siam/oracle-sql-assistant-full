# backend/app/SOS/hybrid_processor.py
import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime
import re
import time
import asyncio

from .query_classifier import QueryClassifier, ConfidenceThresholdManager, QueryIntent, ModelSelectionStrategy
from .deepseek_client import get_deepseek_client, DeepSeekResponse
from app.ollama_llm import ask_sql_model
from app import config
from app.sql_generator import extract_sql as _extract_sql_basic  # Import the existing function

# Import dashboard recorder for token usage tracking
from app.dashboard_recorder import get_dashboard_recorder

# Phase 5: Import hybrid data recorder for training data collection
# Comment out the old imports as we're fully integrating the new AI training recorder
# try:
#     from app.hybrid_data_recorder import hybrid_data_recorder, record_hybrid_turn
#     TRAINING_DATA_COLLECTION_AVAILABLE = True
# except ImportError:
#     TRAINING_DATA_COLLECTION_AVAILABLE = False
#     hybrid_data_recorder = None
#     record_hybrid_turn = None

# Phase 6: Training data collection is no longer available
NEW_TRAINING_RECORDER_AVAILABLE = False
AITrainingDataRecorder = None
RecordingContext = None
ai_training_data_recorder = None

# Add a constant to indicate we're not using the training system
TRAINING_DATA_COLLECTION_AVAILABLE = False

logger = logging.getLogger(__name__)



# ------------------------------ SQL extractor ------------------------------
def _extract_sql_from_response(response_text: str) -> Optional[str]:
    """
    Robustly extract SQL from LLM responses that may contain explanations.
    Enhanced version that builds upon the existing extract_sql function.

    Returns None for incomplete/multi-field-truncated SQLs.
    """
    if not response_text or not isinstance(response_text, str):
        return None

    # Special rejection: incomplete "SELECT ... , ... FROM" with nothing after FROM
    def _looks_like_incomplete_multifield(txt: str) -> bool:
        return re.search(r'SELECT\s+[^,]+,\s+[^,]+\s+FROM\s*$', txt, re.IGNORECASE) is not None

    # First try the basic extraction path
    basic_sql = _extract_sql_basic(response_text)
    if basic_sql and basic_sql.upper().startswith(('SELECT', 'WITH')):
        if '...' in basic_sql:
            return None
        if _looks_like_incomplete_multifield(basic_sql):
            return None
        # Fix for truncated SQL ending with comma
        basic_sql = basic_sql.rstrip(',').strip()
        # Ensure we have a complete FROM clause with table name
        if re.search(r'\bFROM\s*$', basic_sql.upper()):
            return None  # Incomplete FROM clause
        return basic_sql.strip()

    # If basic extraction failed, do a robust parse
    cleaned_text = response_text.strip()

    if cleaned_text.startswith('```sql'):
        cleaned_text = cleaned_text.replace('```sql', '', 1).strip()
    elif cleaned_text.startswith('```'):
        cleaned_text = cleaned_text.replace('```', '', 1).strip()

    # Handle closing backticks with or without trailing dots
    if cleaned_text.endswith('```'):
        cleaned_text = cleaned_text[:-3].strip()
    elif cleaned_text.endswith('```...'):
        cleaned_text = cleaned_text[:-6].strip()
    elif '```' in cleaned_text:
        # Find the last occurrence of ``` and remove everything after it
        last_backticks = cleaned_text.rfind('```')
        if last_backticks != -1:
            cleaned_text = cleaned_text[:last_backticks].strip()

    # Handle trailing dots case
    if cleaned_text.endswith('...'):
        # Remove trailing dots
        cleaned_text = cleaned_text[:-3].strip()

    if '...' in cleaned_text:
        parts = cleaned_text.split('...')
        if parts[0].strip():
            cleaned_text = parts[0].strip()
        else:
            return None

    lines = cleaned_text.split('\n')
    sql_lines: List[str] = []
    in_sql_block = False
    found_select = False
    found_from = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_sql_block and found_from:
                # allow blank after FROM+clauses; continue
                continue
            elif in_sql_block and not found_from:
                # still in SELECT-list; keep waiting for FROM
                continue
            else:
                continue

        # Stop if the code fence closes
        if stripped.startswith('```'):
            break

        # Skip obvious non-SQL commenty lines
        if stripped.startswith(('--', '/*', '#', '*')):
            continue

        # Enter SQL block on SELECT (or WITH)
        if not in_sql_block and re.search(r'^\s*(SELECT|WITH)\b', stripped, re.IGNORECASE):
            in_sql_block = True
            found_select = True
            sql_lines.append(stripped)
            continue

        if in_sql_block:
            # Once in SQL, just accumulate lines until we hit ';' or fence/end
            sql_lines.append(stripped)
            if re.search(r'^\s*FROM\b', stripped, re.IGNORECASE):
                found_from = True
            if stripped.endswith(';'):
                break

    # Require we actually saw FROM
    if not sql_lines or not found_from:
        return None

    final_sql = ' '.join(sql_lines).rstrip(';').rstrip('`').strip()




    if '...' in final_sql:
        pos = final_sql.find('...')
        if pos > 0:
            final_sql = final_sql[:pos].strip()
        else:
            return None

    if _looks_like_incomplete_multifield(final_sql):
        return None

    # Fix for truncated SQL ending with comma
    final_sql = final_sql.rstrip(',').strip()
    
    # Additional validation to ensure we have a complete SQL statement
    if final_sql.upper().startswith(('SELECT', 'WITH')):
        # Confirm a real table token immediately after FROM
        if re.search(r'\bFROM\s+([A-Z_][A-Z0-9_]*)\b', final_sql, re.IGNORECASE):
            return final_sql
        else:
            return None

# ------------------------------ Dataclasses ------------------------------

@dataclass
class ResponseMetrics:
    """Detailed metrics for response evaluation."""
    sql_validity_score: float
    schema_compliance_score: float
    business_logic_score: float
    performance_score: float
    overall_score: float
    reasoning: List[str]

    # Phase 3 Extensions
    technical_validation_score: float = 0.0
    manufacturing_domain_score: float = 0.0
    query_safety_score: float = 0.0
    execution_time_prediction: float = 0.0
    user_satisfaction_prediction: float = 0.0
    relevance_score: float = 0.0


@dataclass
class ProcessingResult:
    selected_response: str = ""
    local_response: Optional[str] = None
    api_response: Optional[str] = None
    processing_mode: str = "unknown"
    selection_reasoning: str = "No reasoning provided"
    local_confidence: float = 0.0
    api_confidence: float = 0.0
    processing_time: float = 0.0
    model_used: str = "unknown"
    local_metrics: Optional[ResponseMetrics] = None
    api_metrics: Optional[ResponseMetrics] = None
    # Phase 5: Additional attributes for training data collection
    local_model_name: Optional[str] = None
    api_model_name: Optional[str] = None
    local_processing_time: Optional[float] = None
    api_processing_time: Optional[float] = None
    # Phase 5.1: API usage tracking (placeholders)
    api_cost_usd: Optional[float] = None
    api_prompt_tokens: Optional[int] = None
    api_completion_tokens: Optional[int] = None


# ------------------------------ SQL Validator ------------------------------

class SQLValidator:
    """Advanced SQL validation and scoring engine."""

    def __init__(self):
        self.oracle_keywords = {
            'SELECT', 'FROM', 'WHERE', 'GROUP BY', 'ORDER BY', 'HAVING',
            'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER',
            'TO_DATE', 'SYSDATE', 'DECODE', 'NVL', 'ROWNUM', 'DUAL'
        }

        # Table patterns for schema compliance validation
        self.table_patterns = {
            'T_PROD': r'\bT_PROD\b',
            'T_PROD_DAILY': r'\bT_PROD_DAILY\b',
            'T_TNA_STATUS': r'\bT_TNA_STATUS\b',
            'EMP': r'\bEMP\b',
            'T_EMP_ATTENDANCE': r'\bT_EMP_ATTENDANCE\b',
            'T_DEFECT_DETAILS': r'\bT_DEFECT_DETAILS\b',
            'T_EFFICIENCY_LOG': r'\bT_EFFICIENCY_LOG\b'
        }

        # Dynamic sets (populate from schema when available)
        self.manufacturing_tables = set()
        self.manufacturing_columns = set()
        self.company_patterns = set()
        self.ctl_pattern = re.compile(r'\bCTL-\d{2}-\d{5,6}\b', re.IGNORECASE)
        self.indexed_columns = set()

        # Safety
        self.dangerous_patterns = [
            r'\bDROP\s+TABLE\b', r'\bDELETE\s+FROM\b.*WHERE\s*1\s*=\s*1',
            r'\bTRUNCATE\b', r'\bALTER\s+TABLE\b', r';\s*--',
            r'\bUNION\s+ALL\s+SELECT\b.*FROM\s+DUAL'
        ]

        self.oracle_functions = {
            'TO_DATE', 'TO_CHAR', 'SYSDATE', 'ADD_MONTHS', 'MONTHS_BETWEEN',
            'DECODE', 'NVL', 'NVL2', 'COALESCE', 'CASE', 'TRUNC', 'ROUND'
        }

    def _first_table_after_from(self, sql: str) -> Optional[str]:
        """
        Return the first base table name that appears immediately after FROM,
        ignoring whitespace, aliases, commas, and JOIN keywords.
        """
        m = re.search(
            r'\bFROM\s+([A-Z_][A-Z0-9_]*)(?=\s*(?:AS\b|\bJOIN\b|\bWHERE\b|\bGROUP\b|\bORDER\b|\bHAVING\b|,|\)|$))',
            sql,
            re.IGNORECASE
        )
        return m.group(1) if m else None


    def validate_sql(self, sql: str, query_context: Dict[str, Any]) -> ResponseMetrics:
        reasoning: List[str] = []

        sql_validity_score = self._assess_sql_validity(sql, reasoning)
        schema_compliance_score = self._assess_schema_compliance(sql, query_context, reasoning)
        business_logic_score = self._assess_business_logic(sql, query_context, reasoning)
        performance_score = self._assess_performance_potential(sql, reasoning)

        technical_validation_score = self._assess_technical_validation(sql, reasoning)
        manufacturing_domain_score = self._assess_manufacturing_domain(sql, query_context, reasoning)
        query_safety_score = self._assess_query_safety(sql, reasoning)
        execution_time_prediction = self._predict_execution_time(sql, query_context)
        user_satisfaction_prediction = self._predict_user_satisfaction(sql, query_context)
        relevance_score = self._assess_relevance(sql, query_context, reasoning)

        overall_score = (
            sql_validity_score * 0.20 +
            schema_compliance_score * 0.15 +
            business_logic_score * 0.20 +
            performance_score * 0.15 +
            technical_validation_score * 0.10 +
            manufacturing_domain_score * 0.10 +
            query_safety_score * 0.05 +
            relevance_score * 0.05
        )

        return ResponseMetrics(
            sql_validity_score=sql_validity_score,
            schema_compliance_score=schema_compliance_score,
            business_logic_score=business_logic_score,
            performance_score=performance_score,
            overall_score=overall_score,
            reasoning=reasoning,
            technical_validation_score=technical_validation_score,
            manufacturing_domain_score=manufacturing_domain_score,
            query_safety_score=query_safety_score,
            execution_time_prediction=execution_time_prediction,
            user_satisfaction_prediction=user_satisfaction_prediction,
            relevance_score=relevance_score
        )

    def _assess_technical_validation(self, sql: str, reasoning: List[str]) -> float:
        score = 0.5
        sql_upper = sql.upper()

        oracle_functions_used = 0
        for func in self.oracle_functions:
            if func in sql_upper:
                oracle_functions_used += 1
                score += 0.06
                reasoning.append(f"Uses Oracle function: {func}")

        if 'TO_DATE' in sql_upper:
            date_format_patterns = ['DD-MON-YY', 'DD-MON-YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD']
            found_format = False
            for pattern in date_format_patterns:
                if pattern in sql or pattern.lower() in sql:
                    found_format = True
                    score += 0.2
                    reasoning.append(f"Proper Oracle date format: {pattern}")
                    break

            for mon in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']:
                if f"'{mon}'" in sql_upper or f"'-{mon}-'" in sql_upper:
                    score += 0.1
                    reasoning.append(f"Uses correct month abbreviation: {mon}")
                    found_format = True
                    break

            if not found_format:
                score -= 0.05
                reasoning.append("TO_DATE without proper format")

        advanced_functions = ['ADD_MONTHS', 'MONTHS_BETWEEN', 'ROUND', 'TRUNC']
        advanced_used = sum(1 for f in advanced_functions if f in sql_upper)
        if advanced_used > 0:
            score += min(advanced_used * 0.08, 0.15)
            reasoning.append(f"Uses advanced Oracle functions ({advanced_used})")

        join_types = ['INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'FULL OUTER JOIN']
        proper_joins = sum(1 for jt in join_types if jt in sql_upper)
        if proper_joins > 0:
            score += min(proper_joins * 0.12, 0.25)
            reasoning.append(f"Uses proper JOIN syntax ({proper_joins} joins)")

        if 'GROUP BY' in sql_upper and 'HAVING' in sql_upper:
            score += 0.1
            reasoning.append("Uses advanced GROUP BY with HAVING")

        if 'SELECT' in sql_upper:
            if sql_upper.count('SELECT') > 1:
                if '(' in sql and ')' in sql:
                    score += 0.12
                    reasoning.append("Properly structured subqueries")
                else:
                    score -= 0.1
                    reasoning.append("Potential subquery syntax issues")

        # Enhanced time-series and trend analysis detection
        time_series_indicators = ['TO_CHAR', 'TRUNC', 'ADD_MONTHS', 'MONTHS_BETWEEN']
        time_series_used = sum(1 for ind in time_series_indicators if ind in sql_upper)
        if time_series_used > 0:
            score += min(time_series_used * 0.1, 0.2)
            reasoning.append(f"Uses time-series functions ({time_series_used} functions)")

        # Enhanced date grouping patterns for trend analysis
        if 'GROUP BY' in sql_upper:
            date_grouping_patterns = [
                r'TO_CHAR\s*\(\s*[A-Z_][A-Z0-9_]*_DATE\s*,\s*\'MON-YYYY\'\s*\)',
                r'TRUNC\s*\(\s*[A-Z_][A-Z0-9_]*_DATE\s*,\s*\'MM\'\s*\)',
                r'TRUNC\s*\(\s*[A-Z_][A-Z0-9_]*_DATE\s*,\s*\'IW\'\s*\)'
            ]
            for pattern in date_grouping_patterns:
                if re.search(pattern, sql_upper, re.IGNORECASE):
                    score += 0.15
                    reasoning.append("Uses appropriate date grouping for trend analysis")
                    break

        # Enhanced window function detection for trend analysis
        window_functions = ['OVER', 'PARTITION BY', 'ROW_NUMBER', 'RANK', 'LAG', 'LEAD']
        window_used = sum(1 for wf in window_functions if wf in sql_upper)
        if window_used > 0:
            score += min(window_used * 0.08, 0.2)
            reasoning.append(f"Uses window functions for trend analysis ({window_used} functions)")

        # Enhanced ordering for time-series data
        if 'ORDER BY' in sql_upper:
            # Check for date-based ordering
            date_columns = ['PROD_DATE', 'TASK_FINISH_DATE', 'DATE']
            if any(col in sql_upper for col in date_columns):
                score += 0.1
                reasoning.append("Orders by date column for time-series analysis")

        return max(0.0, min(score, 1.0))

    def _assess_manufacturing_domain(self, sql: str, query_context: Dict[str, Any], reasoning: List[str]) -> float:
        score = 0.0
        entities = query_context.get('entities', {})
        intent = query_context.get('intent')
        user_query = query_context.get('user_query', '').lower()
        sql_upper = sql.upper()

        companies_mentioned = entities.get('companies', [])
        for company in companies_mentioned:
            if company.upper() in sql_upper:
                score += 0.3
                reasoning.append(f"Accurately recognizes company: {company}")

        # Enhanced company recognition with flexible patterns
        company_patterns = {
            'CAL': ['cal', 'chorka', 'chorka apparel', 'chorka apparel limited'],
            'WINNER': ['winner', 'winner bip'],
            'BIP': ['bip']
        }
        for company_code, patterns in company_patterns.items():
            if any(pattern in user_query for pattern in patterns):
                # Check for flexible company matching in SQL
                if f"UPPER(FLOOR_NAME) LIKE '%{company_code}%'" in sql_upper or company_code.upper() in sql_upper:
                    score += 0.2
                    reasoning.append(f"Uses flexible company pattern matching for {company_code}")

        if intent == QueryIntent.PRODUCTION_QUERY or intent == 'production_query' or intent == 'floor_production_summary':
            if any(t in sql_upper for t in ['T_PROD', 'T_PROD_DAILY']):
                score += 0.25
                reasoning.append("Uses appropriate production tables")

            # Enhanced production metrics relationships
            production_metrics = {
                'PRODUCTION_QTY': ['production', 'qty', 'quantity', 'output'],
                'DEFECT_QTY': ['defect', 'defective', 'faulty'],
                'DHU': ['dhu', 'defect per hundred', 'defect rate'],
                'FLOOR_EF': ['efficiency', 'ef', 'floor ef']
            }
            
            # Check for proper metric usage based on query context
            metrics_used = []
            for metric, keywords in production_metrics.items():
                if metric in sql_upper:
                    metrics_used.append(metric)
                    # Check if the query context matches the metric
                    if any(keyword in user_query for keyword in keywords):
                        score += 0.15
                        reasoning.append(f"Correctly uses {metric} for '{keywords[0]}' context")
                    else:
                        score += 0.1
                        reasoning.append(f"Uses {metric} metric")

            # Enhanced validation for metric relationships
            if 'DHU' in metrics_used and ('DEFECT_QTY' in metrics_used or 'PRODUCTION_QTY' in metrics_used):
                score += 0.1
                reasoning.append("Correctly relates DHU with defect/production quantities")
            
            # Check for proper aggregation in production queries
            if 'GROUP BY' in sql_upper and 'FLOOR_NAME' in sql_upper:
                score += 0.15
                reasoning.append("Properly groups by FLOOR_NAME for production analysis")

            # Enhanced time-series analysis for production data
            trend_indicators = entities.get('trend_indicators', [])
            if trend_indicators:
                # Check for date-based grouping
                date_grouping_patterns = [
                    r'TO_CHAR\s*\(\s*PROD_DATE\s*,\s*\'MON-YYYY\'\s*\)',
                    r'TRUNC\s*\(\s*PROD_DATE\s*,\s*\'MM\'\s*\)',
                    r'TRUNC\s*\(\s*PROD_DATE\s*,\s*\'IW\'\s*\)'
                ]
                for pattern in date_grouping_patterns:
                    if re.search(pattern, sql_upper):
                        score += 0.2
                        reasoning.append("Uses appropriate date grouping for production trend analysis")
                        break
                
                # Check for time-based ordering
                if 'ORDER BY' in sql_upper and 'PROD_DATE' in sql_upper:
                    score += 0.1
                    reasoning.append("Orders production data by date for trend analysis")

        if intent == QueryIntent.TNA_TASK_QUERY or intent == 'tna_task_query':
            if 'T_TNA_STATUS' in sql_upper:
                score += 0.3
                reasoning.append("Uses TNA status table")
            
            ctl_codes = entities.get('ctl_codes', [])
            for ctl in ctl_codes:
                if ctl.upper() in sql_upper:
                    score += 0.3
                    reasoning.append(f"Handles CTL code: {ctl}")
            
            # Enhanced CTL code validation and business context awareness
            if ctl_codes and 'WHERE' in sql_upper:
                # Check for proper CTL code filtering
                ctl_columns = ['JOB_NO', 'CTL_NUMBER', 'CTL_CODE']
                if any(col in sql_upper for col in ctl_columns):
                    score += 0.2
                    reasoning.append("Uses appropriate CTL code filtering columns")
            
            tna_columns = ['TASK_SHORT_NAME', 'TASK_FINISH_DATE', 'JOB_NO', 'PO_NUMBER', 'BUYER_NAME', 'STYLE_REF']
            used = sum(1 for c in tna_columns if c in sql_upper)
            if used > 0:
                score += min(used * 0.08, 0.2)
                reasoning.append(f"Uses TNA-specific columns ({used} columns)")
            
            if 'PP APPROVAL' in sql_upper or 'PP_APPROVAL' in sql_upper:
                score += 0.15
                reasoning.append("Handles PP Approval tasks specifically")
            
            # Business context awareness for TNA tasks
            if 'TASK_FINISH_DATE' in sql_upper and 'ORDER BY' in sql_upper:
                score += 0.1
                reasoning.append("Properly orders TNA tasks by finish date")

        if intent == QueryIntent.HR_EMPLOYEE_QUERY or intent == 'hr_employee_query':
            if 'EMP' in sql_upper:
                score += 0.25
                reasoning.append("Uses employee table")
            hr_columns = ['SALARY', 'JOB_TITLE', 'FULL_NAME', 'EMP_ID']
            used = sum(1 for c in hr_columns if c in sql_upper)
            if used > 0:
                score += min(used * 0.1, 0.2)
                reasoning.append(f"Uses HR-specific columns ({used} columns)")

        dates_mentioned = entities.get('dates', [])
        if dates_mentioned and 'WHERE' in sql_upper:
            score += 0.2
            reasoning.append("Incorporates date context in filtering")
            
            # Enhanced date handling validation
            if 'PROD_DATE' in sql_upper and any(t in sql_upper for t in ['T_PROD', 'T_PROD_DAILY']):
                score += 0.1
                reasoning.append("Uses appropriate date column for production tables")

        # Enhanced multi-field query handling
        multi_field_indicators = ['vs', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
        has_multi_fields = any(ind in user_query for ind in multi_field_indicators)
        if has_multi_fields:
            select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_upper, re.IGNORECASE | re.DOTALL)
            if select_match:
                select_content = select_match.group(1).strip()
                if ',' in select_content:
                    score += 0.2
                    reasoning.append("Properly handles multi-field query with multiple SELECT columns")
                elif select_content.count(' ') > 2:  # Complex single field (e.g., SUM(x) as total)
                    score += 0.1
                    reasoning.append("Handles complex single-field query in multi-field context")

        # Enhanced trend analysis detection
        trend_indicators = entities.get('trend_indicators', [])
        if trend_indicators:
            # Check for time-series functions
            time_series_functions = ['TO_CHAR', 'TRUNC', 'ADD_MONTHS', 'MONTHS_BETWEEN']
            if any(func in sql_upper for func in time_series_functions):
                score += 0.15
                reasoning.append("Uses time-series functions for trend analysis")
            
            # Check for grouping by time periods
            if 'GROUP BY' in sql_upper:
                time_groupings = ['MONTH', 'YEAR', 'WEEK', 'QUARTER']
                if any(group in sql_upper for group in time_groupings):
                    score += 0.1
                    reasoning.append("Groups by time periods for trend analysis")

        return min(score, 1.0)

    def _assess_query_safety(self, sql: str, reasoning: List[str]) -> float:
        score = 1.0
        for pattern in self.dangerous_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                score -= 0.3
                reasoning.append(f"Potential security risk: {pattern}")

        if "'" in sql and 'TO_DATE' not in sql.upper():
            score -= 0.1
            reasoning.append("Unescaped string literals (injection risk)")

        if sql.upper().strip().startswith('SELECT'):
            pass  # safe
        else:
            score -= 0.2
            reasoning.append("Non-SELECT operation (higher risk)")

        if 'WHERE' not in sql.upper() and 'T_PROD' in sql.upper():
            score -= 0.1
            reasoning.append("Missing WHERE clause on large table")

        return max(0.0, min(score, 1.0))

    def _predict_execution_time(self, sql: str, query_context: Dict[str, Any]) -> float:
        base_time = 0.5
        sql_upper = sql.upper()
        
        # Enhanced table-based time prediction
        table_times = {
            'T_PROD': 2.0,
            'T_PROD_DAILY': 3.0,
            'T_TNA_STATUS': 1.5,
            'EMP': 1.0,
            'T_DEFECT_DETAILS': 2.5,
            'T_EFFICIENCY_LOG': 2.0
        }
        
        for table, time_value in table_times.items():
            if table in sql_upper:
                base_time += time_value

        # Enhanced JOIN complexity prediction
        join_count = sql_upper.count('JOIN')
        base_time += join_count * 0.8
        
        # Enhanced WHERE clause analysis
        if 'WHERE' in sql_upper:
            # Count complex conditions
            complex_conditions = sql_upper.count(' AND ') + sql_upper.count(' OR ')
            base_time += complex_conditions * 0.3
            
            # Check for indexed column usage
            indexed_columns = ['PROD_DATE', 'JOB_NO', 'EMP_ID', 'CTL_CODE', 'FLOOR_NAME']
            indexed_filters = sum(1 for col in indexed_columns if col in sql_upper)
            base_time -= indexed_filters * 0.25  # Indexes reduce time
            
            # Check for LIKE operations (slower)
            like_operations = sql_upper.count(' LIKE ')
            base_time += like_operations * 0.5

        # Enhanced aggregation analysis
        agg_operations = ['SUM', 'COUNT', 'AVG', 'MAX', 'MIN']
        agg_count = sum(1 for agg in agg_operations if agg in sql_upper)
        base_time += agg_count * 0.4
        
        # GROUP BY complexity
        if 'GROUP BY' in sql_upper:
            group_fields = sql_upper.count(',')
            base_time += 0.5 + (group_fields * 0.3)
            
        # ORDER BY complexity
        if 'ORDER BY' in sql_upper:
            order_fields = sql_upper.count(',')
            base_time += 0.3 + (order_fields * 0.2)

        return max(0.1, base_time)


    def _predict_user_satisfaction(self, sql: str, query_context: Dict[str, Any]) -> float:
        score = 0.5
        intent = query_context.get('intent')
        entities = query_context.get('entities', {})
        user_query = query_context.get('user_query', '').lower()
        sql_upper = sql.upper()

        # Enhanced intent matching
        if intent in (QueryIntent.PRODUCTION_QUERY, 'production_query') and 'PRODUCTION_QTY' in sql_upper:
            score += 0.25
        elif intent in (QueryIntent.TNA_TASK_QUERY, 'tna_task_query') and 'T_TNA_STATUS' in sql_upper:
            score += 0.25
        elif intent in (QueryIntent.HR_EMPLOYEE_QUERY, 'hr_employee_query') and 'EMP' in sql_upper:
            score += 0.25

        # Enhanced company recognition
        for company in entities.get('companies', []):
            if company.upper() in sql_upper:
                score += 0.15

        # Enhanced date handling
        if entities.get('dates') and 'WHERE' in sql_upper:
            score += 0.15

        # Enhanced ordering validation
        if 'ORDER BY' in sql_upper:
            score += 0.1
            # Check if ordering makes sense for the query type
            if intent in (QueryIntent.PRODUCTION_QUERY, 'production_query') and ('PRODUCTION_QTY' in sql_upper or 'DEFECT_QTY' in sql_upper):
                if 'DESC' in sql_upper:
                    score += 0.05  # Descending order often preferred for production data
            elif intent in (QueryIntent.TNA_TASK_QUERY, 'tna_task_query') and 'TASK_FINISH_DATE' in sql_upper:
                if 'ASC' in sql_upper:
                    score += 0.05  # Ascending order for task dates

        # Enhanced grouping validation
        if 'GROUP BY' in sql_upper and intent in (QueryIntent.PRODUCTION_QUERY, 'production_query', 'floor_production_summary'):
            score += 0.15
            # Check if grouping is by appropriate columns
            if 'FLOOR_NAME' in sql_upper:
                score += 0.05

        # Enhanced multi-field handling
        multi_field_indicators = ['vs', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
        has_multi_fields = any(ind in user_query for ind in multi_field_indicators)
        if has_multi_fields:
            select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_upper, re.IGNORECASE | re.DOTALL)
            if select_match:
                select_content = select_match.group(1).strip()
                if ',' in select_content and select_content.count(',') >= 1:
                    score += 0.2
                    # Removed invalid reference to 'reasoning' variable

        # Enhanced metric selection based on query context
        query_metrics = {
            'production': ['PRODUCTION_QTY', 'TOTAL_PRODUCTION'],
            'defect': ['DEFECT_QTY', 'TOTAL_DEFECTS', 'DHU'],
            'efficiency': ['FLOOR_EF', 'EFFICIENCY'],
            'salary': ['SALARY', 'WAGE']
        }
        
        for keyword, metrics in query_metrics.items():
            if keyword in user_query:
                if any(metric in sql_upper for metric in metrics):
                    score += 0.1
                break

        return max(0.0, min(score, 1.0))

    def _assess_relevance(self, sql: str, query_context: Dict[str, Any], reasoning: List[str]) -> float:
        score = 0.5
        user_query = query_context.get('user_query', '').lower()

        query_keywords = ['production', 'defect', 'efficiency', 'salary', 'task', 'approval', 'employee']
        relevant = 0
        for kw in query_keywords:
            if kw in user_query:
                if kw == 'production' and 'PRODUCTION_QTY' in sql.upper():
                    relevant += 1
                elif kw == 'defect' and 'DEFECT_QTY' in sql.upper():
                    relevant += 1
                elif kw == 'salary' and 'SALARY' in sql.upper():
                    relevant += 1
                elif kw == 'task' and 'TASK_SHORT_NAME' in sql.upper():
                    relevant += 1
                elif kw == 'employee' and 'EMP' in sql.upper():
                    relevant += 1
        if relevant > 0:
            score += min(relevant * 0.1, 0.3)
            reasoning.append(f"Relevant to query keywords ({relevant} matches)")

        if 'SELECT *' in sql.upper():
            score -= 0.1
            reasoning.append("Generic column selection (less specific)")
        else:
            score += 0.1
            reasoning.append("Specific column selection")

        return max(0.0, min(score, 1.0))

    def _assess_sql_validity(self, sql: str, reasoning: List[str]) -> float:
        score = 0.0
        if not sql or not isinstance(sql, str):
            reasoning.append("Empty or invalid SQL")
            return 0.0

        sql_upper = sql.upper().strip()

        if '...' in sql:
            reasoning.append("Incomplete SQL with ellipsis")
            return 0.0

        # Check for truncated SQL ending with comma
        if sql.endswith(','):
            reasoning.append("Truncated SQL ending with comma")
            return 0.0

        if sql_upper.startswith('SELECT'):
            score += 0.3
            reasoning.append("Valid SELECT statement start")
        else:
            reasoning.append("Missing SELECT statement")
            return 0.0

        # ✅ Correct FROM parsing (uses helper)
        first_table = self._first_table_after_from(sql)
        if first_table:
            score += 0.3
            reasoning.append(f"Has FROM clause with table: {first_table}")
        else:
            reasoning.append("Missing or malformed FROM clause")
            return 0.0

        if sql.count('(') == sql.count(')'):
            score += 0.2
            reasoning.append("Balanced parentheses")
        else:
            reasoning.append("Unbalanced parentheses")
            score -= 0.2

        oracle_elements = ['TO_DATE', 'SYSDATE', 'DUAL', 'NVL', 'DECODE']
        oracle_count = sum(1 for el in oracle_elements if el in sql_upper)
        if oracle_count > 0:
            score += min(oracle_count * 0.1, 0.3)
            reasoning.append(f"Uses Oracle-specific elements ({oracle_count})")

        for kw in ['SELECT ', 'FROM ', 'WHERE ', 'GROUP ', 'ORDER ', 'HAVING ']:
            if sql_upper.strip().endswith(kw.strip()):
                reasoning.append(f"Incomplete SQL ending with {kw.strip()}")
                return 0.0

        # Multi-field completeness check
        sm = re.search(r'SELECT\s+(.*?)\s+FROM', sql_upper, re.IGNORECASE | re.DOTALL)
        if sm:
            select_content = sm.group(1).strip()
            if ',' in select_content:
                if select_content.endswith(',') or any(select_content.endswith(kw) for kw in ['SELECT', 'AS']):
                    reasoning.append("Incomplete multi-field SELECT clause")
                    return 0.0

        return max(0.0, min(score, 1.0))

    def _assess_schema_compliance(self, sql: str, query_context: Dict[str, Any], reasoning: List[str]) -> float:
        score = 0.5
        sql_upper = sql.upper()
        user_query = query_context.get('user_query', '').lower()

        # Detect multi-field intent
        multi_field_indicators = ['vs', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
        has_multi_fields = any(ind in user_query for ind in multi_field_indicators)

        # Hard penalty: SELECT 1 FROM DUAL for multi-field user ask
        if has_multi_fields and "SELECT 1 FROM DUAL" in sql_upper:
            reasoning.append("❌ CRITICAL: Using SELECT 1 FROM DUAL for a multi-field query")
            return 0.0

        if 'COMPANY' in sql_upper and 'T_PROD' in sql_upper:
            score -= 0.5
            reasoning.append("❌ CRITICAL: Uses non-existent COMPANY column in production tables")
            reasoning.append("💡 Should use FLOOR_NAME for company grouping instead")

        # Validate tables
        tables = re.findall(r'\bFROM\s+([A-Z_][A-Z0-9_]*)', sql_upper)
        tables += re.findall(r'\bJOIN\s+([A-Z_][A-Z0-9_]*)', sql_upper)

        schema_context = query_context.get('schema_context', '')
        valid_tables_from_schema: List[str] = []
        if schema_context:
            valid_tables_from_schema = re.findall(r'\bTABLE:\s*([A-Z_][A-Z0-9_]*)', schema_context)

        for t in tables:
            if t in self.manufacturing_tables:
                score += 0.1
                reasoning.append(f"✅ Valid manufacturing table: {t}")
            elif valid_tables_from_schema and t in valid_tables_from_schema:
                score += 0.1
                reasoning.append(f"✅ Schema-validated table: {t}")
            else:
                score -= 0.1
                reasoning.append(f"⚠️ Unvalidated table reference: {t}")

        if 'FLOOR_NAME' in sql_upper:
            score += 0.2
            reasoning.append("✅ Uses correct FLOOR_NAME column for grouping")

        for col in ['PRODUCTION_QTY', 'DEFECT_QTY', 'DHU', 'FLOOR_EF']:
            if col in sql_upper:
                score += 0.05
                reasoning.append(f"✅ Valid production metric: {col}")

        if any(col in sql_upper for col in ['PROD_DATE', 'TASK_FINISH_DATE']):
            score += 0.1
            reasoning.append("✅ Uses appropriate date column")

        return min(score, 1.0)

    def _assess_business_logic(self, sql: str, query_context: Dict[str, Any], reasoning: List[str]) -> float:
        score = 0.0
        entities = query_context.get('entities', {})
        user_query = query_context.get('user_query', '').lower()
        sql_upper = sql.upper()

        # Enhanced company recognition
        if entities.get('companies'):
            for company in entities['companies']:
                if company.upper() in sql_upper:
                    score += 0.3
                    reasoning.append(f"Recognizes company: {company}")
                    break
                # Check for flexible company pattern matching
                elif any(pattern in sql_upper for pattern in [f"LIKE '%{company.upper()}%'", f"LIKE '%{company}%'"]):
                    score += 0.25
                    reasoning.append(f"Uses flexible company pattern matching: {company}")

        # Enhanced CTL code handling
        if entities.get('ctl_codes'):
            for ctl in entities['ctl_codes']:
                if ctl.upper() in sql_upper:
                    score += 0.3
                    reasoning.append(f"Handles CTL code: {ctl}")
                    break
                # Check for proper CTL code column usage
                ctl_columns = ['JOB_NO', 'CTL_CODE', 'CTL_NUMBER']
                if any(col in sql_upper for col in ctl_columns):
                    score += 0.2
                    reasoning.append("Uses appropriate CTL code columns")

        # Enhanced multi-field relevance with manufacturing context
        multi_field_indicators = ['vs', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
        has_multi_fields = any(ind in user_query for ind in multi_field_indicators)
        if has_multi_fields:
            sm = re.search(r'SELECT\s+(.*?)\s+FROM', sql_upper, re.IGNORECASE | re.DOTALL)
            if sm:
                select_content = sm.group(1).strip()
                field_count = select_content.count(',') + 1
                if field_count > 1:
                    score += min(field_count * 0.1, 0.4)
                    reasoning.append(f"Handles multiple fields ({field_count} fields detected)")
                    
                    # Enhanced validation for manufacturing multi-field queries
                    manufacturing_metrics = ['PRODUCTION_QTY', 'DEFECT_QTY', 'DHU', 'FLOOR_EF']
                    used_metrics = [metric for metric in manufacturing_metrics if metric in sql_upper]
                    if len(used_metrics) > 1:
                        score += 0.15
                        reasoning.append(f"Properly combines manufacturing metrics: {', '.join(used_metrics)}")
                else:
                    reasoning.append("User requested multiple fields but SQL only contains one field")
                    score -= 0.2

        # Enhanced metric recognition based on query context
        metric_mappings = {
            'production': ['PRODUCTION_QTY', 'TOTAL_PRODUCTION'],
            'defect': ['DEFECT_QTY', 'TOTAL_DEFECTS', 'DHU'],
            'efficiency': ['FLOOR_EF', 'EFFICIENCY'],
            'dhu': ['DHU', 'DEFECT_QTY']
        }
        
        for keyword, metrics in metric_mappings.items():
            if keyword in user_query:
                if any(metric in sql_upper for metric in metrics):
                    score += 0.2
                    reasoning.append(f"Correctly uses {keyword} metrics")
                break

        # Enhanced aggregation function validation
        aggregations = entities.get('aggregations', [])
        if aggregations:
            agg_functions = ['SUM', 'AVG', 'COUNT', 'MAX', 'MIN']
            used_aggs = [agg for agg in agg_functions if agg in sql_upper]
            if used_aggs:
                score += min(len(used_aggs) * 0.1, 0.3)
                reasoning.append(f"Uses appropriate aggregation functions: {', '.join(used_aggs)}")

        # Enhanced date handling
        if entities.get('dates') and 'WHERE' in sql_upper:
            score += 0.2
            reasoning.append("Incorporates date filtering")
            
            # Check for proper date column usage
            date_columns = ['PROD_DATE', 'TASK_FINISH_DATE']
            if any(col in sql_upper for col in date_columns):
                score += 0.1
                reasoning.append("Uses appropriate date columns")

        # Enhanced intent-specific validation
        intent = query_context.get('intent')
        if intent in ['tna_task_query', QueryIntent.TNA_TASK_QUERY] and 'T_TNA_STATUS' in sql_upper:
            score += 0.25
            reasoning.append("Proper TNA table usage")
            
            # Enhanced TNA validation
            tna_required_columns = ['TASK_SHORT_NAME', 'TASK_FINISH_DATE', 'JOB_NO']
            used_tna_columns = [col for col in tna_required_columns if col in sql_upper]
            if used_tna_columns:
                score += 0.1
                reasoning.append(f"Uses key TNA columns: {', '.join(used_tna_columns)}")
                
        elif intent in ['production_query', 'floor_production_summary', QueryIntent.PRODUCTION_QUERY] and any(
            t in sql_upper for t in ['T_PROD', 'T_PROD_DAILY']
        ):
            score += 0.25
            reasoning.append("Proper production table usage")
            
            # Enhanced production validation
            if 'GROUP BY' in sql_upper and 'FLOOR_NAME' in sql_upper:
                score += 0.15
                reasoning.append("Properly groups production data by floor")
                
        elif intent in ['hr_employee_query', QueryIntent.HR_EMPLOYEE_QUERY] and 'EMP' in sql_upper:
            score += 0.2
            reasoning.append("Proper employee table usage")

        # Enhanced ordering direction validation
        ordering_directions = entities.get('ordering_directions', [])
        if ordering_directions and 'ORDER BY' in sql_upper:
            if any(direction in ['desc', 'descending'] for direction in ordering_directions) and 'DESC' in sql_upper:
                score += 0.1
                reasoning.append("Correctly uses descending order")
            elif any(direction in ['asc', 'ascending'] for direction in ordering_directions) and 'ASC' in sql_upper:
                score += 0.1
                reasoning.append("Correctly uses ascending order")

        return min(score, 1.0)

    def _assess_performance_potential(self, sql: str, reasoning: List[str]) -> float:
        score = 0.5
        if 'WHERE' in sql:
            score += 0.2
            reasoning.append("Uses WHERE clause for filtering")

        if any(idx in sql for idx in ['PROD_DATE', 'JOB_NO', 'EMP_ID']):
            score += 0.15
            reasoning.append("Uses likely indexed columns")

        if 'SELECT *' in sql.upper():
            score -= 0.2
            reasoning.append("Uses SELECT * (performance concern)")

        if sql.upper().count('JOIN') > 3:
            score -= 0.1
            reasoning.append("Multiple JOINs (complexity concern)")

        complexity_keywords = sql.upper().count('GROUP BY') + sql.upper().count('ORDER BY') + sql.upper().count('HAVING')
        if complexity_keywords <= 2:
            score += 0.15
            reasoning.append("Reasonable query complexity")

        return max(0.0, min(score, 1.0))


# ------------------------------ Local simulation helper (optional) ------------------------------

def _simulate_local_processing_enhanced(user_query: str, schema_context: str) -> str:
    """Enhanced local processing simulation with better response formatting."""
    try:
        response = ("SELECT FLOOR_NAME, "
                    "SUM(PRODUCTION_QTY) as TOTAL_PRODUCTION, "
                    "SUM(DEFECT_QTY) as TOTAL_DEFECTS "
                    "FROM T_PROD_DAILY "
                    "WHERE PROD_DATE >= TO_DATE('01-JAN-2025','DD-MON-YYYY') "
                    "GROUP BY FLOOR_NAME "
                    "ORDER BY TOTAL_PRODUCTION DESC")
        return str(response)
    except Exception as e:
        logger.error(f"Local processing simulation failed: {e}")
        return "SELECT 'Local processing result' as RESPONSE FROM DUAL"

# ------------------------------ Advanced response selector ------------------------------

class AdvancedResponseSelector:
    """
    Phase 3.2: Advanced weighted response selection algorithm with domain-specific rules.
    """
    def __init__(self):
        self.weights = {
            'technical_accuracy': 0.35,
            'business_logic': 0.35,
            'performance': 0.15,
            'model_confidence': 0.10,
            'manufacturing_domain': 0.05
        }
        # Initialize domain rules with dynamically populated preferred models
        from app.config import API_MODELS
        
        # Get the primary models for each domain
        production_primary = API_MODELS["production"]["primary"]
        hr_primary = API_MODELS["hr"]["primary"]
        tna_primary = API_MODELS["tna"]["primary"]
        general_primary = API_MODELS["general"]["primary"]
        
        self.domain_rules = {
            'cal_winner_queries': {
                'preferred_models': [production_primary],  # Use production primary model
                'weight_boost': 0.15,
                'patterns': [r'\b(CAL|Winner)\b', r'\bproduction\b', r'\bfloor\b', r'\bsewing\b', r'\bdefect\b']
            },
            'hr_queries': {
                'preferred_models': [hr_primary, 'meta-llama/llama-3.1-8b-instruct'],
                'weight_boost': 0.12,
                'patterns': [r'\b(employee|staff|worker|hr)\b', r'\b(salary|designation)\b', r'\b(president|manager)\b']
            },
            'ctl_task_queries': {
                'preferred_models': [tna_primary],  # Use TNA primary model
                'weight_boost': 0.18,
                'patterns': [r'\bCTL-\d{2}-\d{5,6}\b', r'\b(task|TNA|approval)\b', r'\b(pp\s+approval)\b']
            },
            'complex_analytics': {
                'preferred_models': [general_primary, 'meta-llama/llama-3.1-8b-instruct'],
                'weight_boost': 0.10,
                'patterns': [r'\b(trend|analysis|compare|correlation)\b', r'\b(average|sum|group\s+by)\b', r'\b(monthly|weekly)\b']
            },
            'efficiency_queries': {
                'preferred_models': [production_primary],  # Use production primary model
                'weight_boost': 0.13,
                'patterns': [r'\b(efficiency|dhu|floor\s+ef)\b', r'\bperformance\b', r'\b(productivity)\b']
            },
            'multi_field_queries': {
                'preferred_models': [general_primary],  # Use general primary model
                'weight_boost': 0.14,
                'patterns': [r'\b(vs|versus|compare)\b', r'\b(and|with)\b', r'\b(&)\b']
            },
            'time_series_queries': {
                'preferred_models': [general_primary],  # Use general primary model
                'weight_boost': 0.11,
                'patterns': [r'\b(last\s+week|last\s+month|trend)\b', r'\b(daily|weekly|monthly)\b', r'\bover\s+time\b']
            }
        }
        self.logger = logging.getLogger(__name__)

    def select_best_response(
        self,
        local_response: Optional[str],
        api_response: Optional[str],
        local_metrics: Optional[ResponseMetrics],
        api_metrics: Optional[ResponseMetrics],
        query_context: Dict[str, Any],
        local_confidence: float = 0.5,
        api_confidence: float = 0.5,
        model_used: str = "unknown"
    ) -> Tuple[str, str, Dict[str, Any]]:

        if not local_response and not api_response:
            return "", "No responses available", {}

        if not local_response:
            return api_response or "", "Only API response available", {"api_score": 1.0}

        if not api_response:
            return local_response, "Only local response available", {"local_score": 1.0}

        local_score, local_breakdown = self._calculate_comprehensive_score(
            local_response, local_metrics, local_confidence, query_context, "local", ""
        )
        api_score, api_breakdown = self._calculate_comprehensive_score(
            api_response, api_metrics, api_confidence, query_context, "api", model_used
        )

        local_score, local_domain_boost = self._apply_domain_rules(local_score, query_context, "local", "")
        api_score, api_domain_boost = self._apply_domain_rules(api_score, query_context, "api", model_used)

        selected_response, selection_reasoning = self._make_selection_decision(
            local_response, api_response, local_score, api_score,
            local_breakdown, api_breakdown, local_domain_boost, api_domain_boost
        )

        detailed_scores = {
            "local_score": local_score,
            "api_score": api_score,
            "local_breakdown": local_breakdown,
            "api_breakdown": api_breakdown,
            "local_domain_boost": local_domain_boost,
            "api_domain_boost": api_domain_boost,
            "weights_used": self.weights,
            "selection_margin": abs(local_score - api_score)
        }

        self.logger.info(f"Response selection: {selection_reasoning} (Local: {local_score:.3f}, API: {api_score:.3f})")
        return selected_response, selection_reasoning, detailed_scores

    def _calculate_comprehensive_score(
        self,
        response: str,
        metrics: Optional[ResponseMetrics],
        model_confidence: float,
        query_context: Dict[str, Any],
        model_type: str,
        model_name: str
    ) -> Tuple[float, Dict[str, float]]:

        if metrics:
            technical_score = (
                metrics.sql_validity_score * 0.4 +
                metrics.schema_compliance_score * 0.3 +
                metrics.technical_validation_score * 0.3
            )
            business_score = (
                metrics.business_logic_score * 0.6 +
                metrics.manufacturing_domain_score * 0.4
            )
            performance_score = (
                metrics.performance_score * 0.7 +
                (1.0 - min(metrics.execution_time_prediction / 10.0, 1.0)) * 0.3
            )
            manufacturing_domain_score = metrics.manufacturing_domain_score
        else:
            technical_score = self._estimate_technical_score(response)
            business_score = self._estimate_business_score(response, query_context)
            performance_score = self._estimate_performance_score(response)
            manufacturing_domain_score = self._estimate_manufacturing_domain_score(response, query_context)

        technical_score = max(0, min(1, technical_score))
        business_score = max(0, min(1, business_score))
        performance_score = max(0, min(1, performance_score))
        manufacturing_domain_score = max(0, min(1, manufacturing_domain_score))
        confidence_score = max(0, min(1, model_confidence))

        overall = (
            technical_score * self.weights['technical_accuracy'] +
            business_score * self.weights['business_logic'] +
            performance_score * self.weights['performance'] +
            confidence_score * self.weights['model_confidence'] +
            manufacturing_domain_score * self.weights['manufacturing_domain']
        )
        return overall, {
            'technical_accuracy': technical_score,
            'business_logic': business_score,
            'performance': performance_score,
            'model_confidence': confidence_score,
            'manufacturing_domain': manufacturing_domain_score,
            'weighted_overall': overall
        }

    def _estimate_manufacturing_domain_score(self, response: str, context: Dict[str, Any]) -> float:
        """Estimate manufacturing domain score when detailed metrics are not available."""
        score = 0.5
        user_query = context.get('user_query', '').lower()
        response_upper = response.upper()
        
        # Check for manufacturing tables
        manufacturing_tables = ['T_PROD', 'T_PROD_DAILY', 'T_TNA_STATUS', 'EMP']
        table_matches = sum(1 for table in manufacturing_tables if table in response_upper)
        score += table_matches * 0.1
        
        # Check for manufacturing metrics
        manufacturing_metrics = ['PRODUCTION_QTY', 'DEFECT_QTY', 'DHU', 'FLOOR_EF', 'FLOOR_NAME']
        metric_matches = sum(1 for metric in manufacturing_metrics if metric in response_upper)
        score += min(metric_matches * 0.08, 0.3)
        
        # Check for manufacturing keywords in query
        manufacturing_keywords = ['production', 'defect', 'efficiency', 'floor', 'sewing', 'dhu']
        keyword_matches = sum(1 for keyword in manufacturing_keywords if keyword in user_query)
        score += min(keyword_matches * 0.07, 0.25)
        
        # Check for CTL codes
        if re.search(r'\bCTL-\d{2}-\d{5,6}\b', user_query, re.IGNORECASE):
            if 'T_TNA_STATUS' in response_upper:
                score += 0.2
        
        return max(0, min(1, score))

    def _apply_domain_rules(self, base_score: float, query_context: Dict[str, Any], model_type: str, model_name: str):
        query_text = query_context.get('original_query', '').lower()
        intent = query_context.get('intent', 'general')

        domain_boosts = {}
        total_boost = 0.0

        for rule_name, cfg in self.domain_rules.items():
            matches = any(re.search(p, query_text, re.IGNORECASE) for p in cfg['patterns'])
            if matches:
                if model_name in cfg['preferred_models']:
                    boost = cfg['weight_boost']
                    domain_boosts[rule_name] = boost
                    total_boost += boost
                elif model_type == 'local' and not model_name:
                    boost = cfg['weight_boost'] * 0.3
                    domain_boosts[f"{rule_name}_local"] = boost
                    total_boost += boost

        # Enhanced intent-based boosting for manufacturing scenarios
        if intent in ('production_query', QueryIntent.PRODUCTION_QUERY) and isinstance(model_name, str) and 'llama' in model_name.lower():
            b = 0.08
            domain_boosts['production_intent_boost'] = b
            total_boost += b
        elif intent in ('hr_employee_query', QueryIntent.HR_EMPLOYEE_QUERY) and isinstance(model_name, str) and 'llama' in model_name.lower():
            b = 0.06
            domain_boosts['hr_intent_boost'] = b
            total_boost += b
        elif intent in ('tna_task_query', QueryIntent.TNA_TASK_QUERY) and isinstance(model_name, str) and 'llama' in model_name.lower():
            b = 0.10
            domain_boosts['tna_intent_boost'] = b
            total_boost += b
        elif intent in ('complex_analytics', QueryIntent.COMPLEX_ANALYTICS) and isinstance(model_name, str) and 'llama' in model_name.lower():
            b = 0.09
            domain_boosts['analytics_intent_boost'] = b
            total_boost += b

        # Enhanced boosting for specific manufacturing scenarios
        # Efficiency/DHU queries
        if any(word in query_text for word in ['efficiency', 'dhu', 'floor ef']):
            if isinstance(model_name, str) and 'deepseek' in model_name.lower():
                b = 0.07
                domain_boosts['efficiency_domain_boost'] = b
                total_boost += b

        # Multi-field queries
        multi_field_indicators = ['vs', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
        if any(ind in query_text for ind in multi_field_indicators):
            if isinstance(model_name, str) and 'deepseek' in model_name.lower():
                b = 0.08
                domain_boosts['multi_field_boost'] = b
                total_boost += b

        # Time-series/trend analysis
        if any(word in query_text for word in ['trend', 'analysis', 'over time', 'monthly', 'weekly', 'last week', 'last month']):
            if isinstance(model_name, str) and 'deepseek' in model_name.lower():
                b = 0.07
                domain_boosts['trend_analysis_boost'] = b
                total_boost += b

        # CTL code queries
        if re.search(r'\bCTL-\d{2}-\d{5,6}\b', query_text, re.IGNORECASE):
            if isinstance(model_name, str) and 'deepseek' in model_name.lower():
                b = 0.10
                domain_boosts['ctl_code_boost'] = b
                total_boost += b

        boosted = base_score + (total_boost * (1 - base_score))
        return min(boosted, 1.0), domain_boosts

    def _estimate_technical_score(self, response: str) -> float:
        score = 0.5
        if not response or '...' in response:
            return max(0, score - 0.4)
        if 'SELECT' in response.upper() and 'FROM' in response.upper():
            score += 0.2
        for func in ['TO_DATE', 'NVL', 'DECODE', 'SYSDATE']:
            if func in response.upper():
                score += 0.05
        if 'JOIN' in response.upper() and 'ON' in response.upper():
            score += 0.1
        if response.count('(') != response.count(')'):
            score -= 0.2
        if response.strip().endswith(','):
            score -= 0.3
        return max(0, min(1, score))

    def _estimate_business_score(self, response: str, context: Dict[str, Any]) -> float:
        score = 0.5
        for t in ['T_PROD', 'T_PROD_DAILY', 'T_TNA_STATUS', 'EMP']:
            if t in response.upper():
                score += 0.1
        for company in ['CAL', 'WINNER', 'BIP']:
            if company in response.upper():
                score += 0.08
        if re.search(r'\bCTL-\d{2}-\d{5,6}\b', response, re.IGNORECASE):
            score += 0.15

        intent = context.get('intent', '')
        if 'production' in str(intent).lower() and 'T_PROD' in response.upper():
            score += 0.1
        elif 'hr' in str(intent).lower() and 'EMP' in response.upper():
            score += 0.1
        elif 'tna' in str(intent).lower() and 'T_TNA_STATUS' in response.upper():
            score += 0.1
        return max(0, min(1, score))

    def _estimate_performance_score(self, response: str) -> float:
        score = 0.7
        if any(col in response.upper() for col in ['PROD_DATE', 'JOB_NO', 'EMP_ID', 'COMPANY']):
            score += 0.1
        if 'SELECT *' in response.upper():
            score -= 0.1
        if response.upper().count('OR') > 3:
            score -= 0.05
        if 'LIKE %' in response.upper():
            score -= 0.1
        return max(0, min(1, score))

    def _make_selection_decision(
        self,
        local_response: str,
        api_response: str,
        local_score: float,
        api_score: float,
        local_breakdown: Dict[str, float],
        api_breakdown: Dict[str, float],
        local_domain_boost: Dict[str, Any],
        api_domain_boost: Dict[str, Any]
    ) -> Tuple[str, str]:

        diff = api_score - local_score
        if diff > 0.05:
            selected = api_response
            reason = f"API response selected (score: {api_score:.3f} vs {local_score:.3f}). "
            reason += f"API excelled in: {self._get_top_scores(api_breakdown)}"
            if api_domain_boost:
                reason += f". Domain boosts: {list(api_domain_boost.keys())}"
        elif diff < -0.05:
            selected = local_response
            reason = f"Local response selected (score: {local_score:.3f} vs {api_score:.3f}). "
            reason += f"Local excelled in: {self._get_top_scores(local_breakdown)}"
            if local_domain_boost:
                reason += f". Domain boosts: {list(local_domain_boost.keys())}"
        else:
            if diff >= 0:
                selected = api_response
                reason = f"API response selected in close call (score: {api_score:.3f} vs {local_score:.3f}). "
                reason += "Minimal difference, preferring API capability."
            else:
                selected = local_response
                reason = f"Local response selected in close call (score: {local_score:.3f} vs {api_score:.3f}). "
                reason += "Minimal difference, preferring local efficiency."
        return selected, reason

    def _get_top_scores(self, breakdown: Dict[str, float]) -> str:
        top2 = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)[:2]
        return ", ".join([f"{k}: {v:.2f}" for k, v in top2])

# ------------------------------ Advanced parallel processor ------------------------------
class AdvancedParallelProcessor:
    """Enhanced parallel processing engine with race condition handling."""

    def __init__(self):
        self.classifier = QueryClassifier()
        self.threshold_manager = ConfidenceThresholdManager(config)
        self.deepseek_client = get_deepseek_client()
        self.sql_validator = SQLValidator()

        # Prefer advanced selector if available; else fallback
        try:
            self.selector = AdvancedResponseSelector()
        except Exception:
            self.selector = self._create_fallback_selector()

        self.logger = logging.getLogger(__name__)

        # Default timeouts
        self.local_timeout = 30.0
        self.api_timeout = 45.0
        self.total_timeout = 60.0

        self.processing_stats = {
            "local": 0,
            "api": 0,
            "local_fail": 0,
            "api_fail": 0,
            "local_timeout": 0,
            "api_timeout": 0,
            "local_success": 0,
            "api_success": 0,
            "local_retries": 0,
            "api_retries": 0,
            "local_retries_success": 0,
            "api_retries_success": 0,
            "local_retries_fail": 0,
            "api_retries_fail": 0,
            "local_retries_timeout": 0,
            "api_retries_timeout": 0,
        }

    def _create_fallback_selector(self):
        return AdvancedResponseSelector()

    def _process_query(self, query: str) -> Tuple[str, str]:
        local_response = self._get_local_response(query)
        api_response = self._get_api_response(query)

        # Use a simple scoring approach since AdvancedResponseSelector doesn't have a score method
        local_score = len(local_response) if local_response else 0
        api_score = len(api_response) if api_response else 0

        if local_score > api_score:
            selected = local_response
            reason = f"Local response selected (length: {local_score} vs {api_score})."
        elif api_score > local_score:
            selected = api_response
            reason = f"API response selected (length: {api_score} vs {local_score})."
        else:
            if local_response:
                selected = local_response
                reason = "Responses equal, selecting local response."
            else:
                selected = api_response or ""
                reason = "No valid responses available."
        return selected, reason

    def _get_local_response(self, query: str) -> str:
        try:
            local_response = self._local_query(query)
            self.processing_stats["local_success"] += 1
            return local_response
        except Exception as e:
            self.processing_stats["local_fail"] += 1
            self.logger.error(f"Local query failed: {e}")
            return ""

    def _get_api_response(self, query: str) -> str:
        try:
            api_response = self._api_query(query)
            self.processing_stats["api_success"] += 1
            return api_response
        except Exception as e:
            self.processing_stats["api_fail"] += 1
            self.logger.error(f"API query failed: {e}")
            return ""

    def _local_query(self, query: str) -> str:
        raise NotImplementedError("Local query method not implemented.")

    def _api_query(self, query: str) -> str:
        raise NotImplementedError("API query method not implemented.")

    def process(self, query: str) -> str:
        selected, reason = self._process_query(query)
        self.logger.info(f"Selected response: {selected}")
        self.logger.info(f"Reason: {reason}")
        return selected

# ------------------------------ Hybrid processor ------------------------------
class HybridProcessor:
    """Enhanced hybrid processor with proper mode tracking for all processing modes."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.query_classifier = QueryClassifier()
        self.confidence_manager = ConfidenceThresholdManager(config)
        self.sql_validator = SQLValidator()
        self.deepseek_client = get_deepseek_client()
        
        # Initialize threshold manager and selector
        self.threshold_manager = ConfidenceThresholdManager(config)
        try:
            self.selector = AdvancedResponseSelector()
        except Exception:
            self.selector = self._create_fallback_selector()

        # Timing configuration
        self.local_timeout = 30.0
        self.api_timeout = 45.0
        self.total_timeout = 60.0
        self._local_processing_time = 0.0
        self._api_processing_time = 0.0
        self.processing_stats = {
            'total_queries': 0,
            'parallel_successes': 0,
            'api_selections': 0,
            'local_selections': 0,
            'average_processing_time': 0.0
        }
        # Initialize training data recorder
        self.training_data_recorder = None
        
        # Initialize dashboard recorder for token usage tracking
        self.dashboard_recorder = get_dashboard_recorder()

    def _create_fallback_selector(self):
        class FallbackResponseSelector:
            def select_best_response(self, local_response, api_response, local_metrics,
                                     api_metrics, query_context, local_confidence,
                                     api_confidence, model_used):
                if api_response and api_response.strip():
                    return (api_response, "Selected API response as it was available",
                            {"confidence": api_confidence or 0.8})
                elif local_response and local_response.strip():
                    return (local_response, "Selected local response as API was not available",
                            {"confidence": local_confidence or 0.7})
                else:
                    return ("", "No valid response available", {"confidence": 0.0})
        return FallbackResponseSelector()

    async def process_query_advanced(self,
                                     user_query: str,
                                     schema_context: str = "",
                                     local_confidence: float = 0.5,
                                     query_type: str = "sql",  # Add query_type parameter
                                     # Phase 5: Add training data collection parameters
                                     turn_id: Optional[int] = None,
                                     session_id: Optional[str] = None,
                                     client_ip: Optional[str] = None,
                                     user_agent: Optional[str] = None,
                                     classification_time_ms: float = 0.0,
                                     # File analysis parameters
                                     file_content: Optional[str] = None,
                                     file_name: Optional[str] = None,
                                     # Dashboard recording parameters
                                     chat_id: Optional[int] = None) -> ProcessingResult:
        """
        Advanced parallel processing with sophisticated response selection.
        """
        start_time = time.time()
        processing_result = None
        
        # Log dashboard recorder status
        self.logger.info(f"Dashboard recorder status: {self.dashboard_recorder is not None}")
        if self.dashboard_recorder is None:
            self.logger.warning("Dashboard recorder is not available - token usage will not be recorded")
        
        # Handle general queries - bypass SQL-specific processing
        # Note: General query handling should be done in the HybridProcessor class
        # which has access to the _process_general_query method
        if query_type == "general":
            # For AdvancedParallelProcessor, we'll return a simple error
            # The HybridProcessor will handle this properly
            processing_time = time.time() - start_time
            return ProcessingResult(
                selected_response="General query processing not available at this level",
                local_response=None,
                api_response=None,
                processing_mode="general_query_unsupported",
                selection_reasoning="General query processing not available in AdvancedParallelProcessor",
                local_confidence=0.0,
                api_confidence=0.0,
                processing_time=processing_time,
                model_used="unsupported",
                local_model_name=None,
                api_model_name=None,
                local_processing_time=None,
                api_processing_time=None
            )
        
        # ---- Helper: pick a safe reasoning list (never None / never undefined)
        def _pick_reasoning(*candidates):
            for c in candidates:
                try:
                    # If it's already a list, use it
                    if isinstance(c, list):
                        return c
                    # Object with .reasoning list (e.g., metrics object)
                    if hasattr(c, "reasoning") and isinstance(c.reasoning, list):
                        return c.reasoning
                    # Plain non-empty string → wrap as single-item list
                    if isinstance(c, str) and c.strip():
                        return [c.strip()]
                except Exception:
                    pass
            return []
        
        try:
            # Detect multi-field queries early
            mf_indicators = [' vs ', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
            has_multi_fields = any(ind in user_query.lower() for ind in mf_indicators)

            # Timeout tuning for multi-field
            if has_multi_fields:
                self.logger.info("Detected multi-field query, adjusting processing parameters...")
                self.local_timeout = 40.0
                self.api_timeout = 45.0
                self.total_timeout = 60.0
                processing_mode = "hybrid_parallel"
            else:
                self.local_timeout = 30.0
                self.api_timeout = 45.0
                self.total_timeout = 60.0

            # Enhanced query analysis
            from .rag_engine import analyze_enhanced_query
            query_analysis = analyze_enhanced_query(user_query)

            processing_mode = "SOS"  # Default value for SOS mode
            if not has_multi_fields:
                processing_mode = self.assess_query_complexity(user_query, query_analysis)

            thresholds = self.calibrate_confidence_thresholds(query_analysis)

            logger.info(f"Enhanced analysis: {query_analysis.get('intent')} "
                        f"(confidence: {query_analysis.get('intent_confidence', 0):.2f}, "
                        f"mode: {processing_mode})")

            # Create a proper classification object
            from app.SOS.query_classifier import QueryClassification, QueryIntent, ModelSelectionStrategy
            
            # Map custom intent names to valid QueryIntent enum values
            intent_mapping = {
                'floor_production_summary': QueryIntent.PRODUCTION_QUERY,
                'efficiency_query': QueryIntent.PRODUCTION_QUERY,
                'defect_analysis': QueryIntent.PRODUCTION_QUERY,
                'employee_lookup': QueryIntent.HR_EMPLOYEE_QUERY,
                'tna_task_query': QueryIntent.TNA_TASK_QUERY,
                'trend_analysis': QueryIntent.COMPLEX_ANALYTICS,
                'ranking_query': QueryIntent.COMPLEX_ANALYTICS,
                'general': QueryIntent.GENERAL_QUERY
            }
            
            intent_value = query_analysis.get('intent', 'general')
            mapped_intent = intent_mapping.get(intent_value, QueryIntent.GENERAL_QUERY)
            
            classification = QueryClassification(
                intent=mapped_intent,
                confidence=query_analysis.get('intent_confidence', 0.5),
                strategy=ModelSelectionStrategy.HYBRID_PARALLEL,
                reasoning=f"Enhanced analysis: {intent_value}",
                entities=query_analysis.get('entities', {}),
                complexity_score=query_analysis.get('complexity_score', 0.0)
            )

            query_context: Dict[str, Any] = {
                'user_query': user_query,
                'intent': query_analysis.get('intent', 'general'),
                'entities': query_analysis.get('entities', {}),
                'schema_context': schema_context,
                'original_query': user_query
            }

            decision = self.threshold_manager.get_processing_decision(local_confidence, classification)

            # Record query classification if training data collection is available
            # Training data recording is disabled
            classification_id = None

            # Record schema context is disabled
            schema_id = None

            # Execute with timeouts
            local_response: Optional[str] = None
            api_response: Optional[str] = None
            api_response_obj = None  # To store the full API response object for token usage
            
            if decision['use_local'] and decision['use_api']:
                # For parallel execution, we need to get the API response object separately
                try:
                    # Call the API processing method directly to get the full response for token usage tracking
                    model_type = self._get_model_type_for_intent(classification.intent)
                    enhanced_query = self._preprocess_dates_for_oracle(user_query)
                    
                    # Multi-field detection
                    mf_indicators = [' vs ', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
                    has_multi_fields = any(ind in user_query.lower() for ind in mf_indicators)
                    if has_multi_fields:
                        enhanced_query = f"{enhanced_query} (Please provide SQL that returns multiple fields as requested, not just a single value)"
                    
                    api_response_obj = await self.deepseek_client.get_sql_response(
                        user_query=enhanced_query,
                        schema_context=schema_context,
                        model_type=model_type
                    )
                    
                    # Extract the SQL from the response
                    if api_response_obj.success:
                        api_response = _extract_sql_from_response(api_response_obj.content)
                        if api_response:
                            api_response = self._normalize_sql(api_response)
                    else:
                        api_response = None
                        api_response_obj = None  # Clear the object if the response failed
                except Exception as e:
                    self.logger.error(f"Error getting full API response for token tracking: {e}")
                    api_response_obj = None  # Clear the object if there was an error
                
                # Execute the parallel processing
                local_response, api_response_parallel = await self._execute_parallel_with_timeout(
                    user_query, schema_context, classification
                )
                
                # Use the parallel response if we didn't get a successful API response object
                if api_response is None and api_response_parallel:
                    api_response = api_response_parallel
            elif decision['use_api']:
                # For API-only execution, we need to get the full response object
                try:
                    # Call the API processing method directly to get the full response
                    model_type = self._get_model_type_for_intent(classification.intent)
                    enhanced_query = self._preprocess_dates_for_oracle(user_query)
                    
                    # Multi-field detection
                    mf_indicators = [' vs ', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
                    has_multi_fields = any(ind in user_query.lower() for ind in mf_indicators)
                    if has_multi_fields:
                        enhanced_query = f"{enhanced_query} (Please provide SQL that returns multiple fields as requested, not just a single value)"
                    
                    api_response_obj = await self.deepseek_client.get_sql_response(
                        user_query=enhanced_query,
                        schema_context=schema_context,
                        model_type=model_type
                    )
                    
                    if api_response_obj.success:
                        api_response = _extract_sql_from_response(api_response_obj.content)
                        if api_response:
                            api_response = self._normalize_sql(api_response)
                    else:
                        api_response = None
                except Exception as e:
                    self.logger.error(f"Error getting full API response: {e}")
                    api_response = await self._execute_api_with_timeout(user_query, schema_context, classification)
            else:
                local_response = await self._execute_local_with_timeout(user_query, schema_context)

            # Score candidates
            local_metrics = self.sql_validator.validate_sql(local_response, query_context) if local_response else None
            if local_metrics:
                self.logger.info(f"Local response score: {local_metrics.overall_score:.2f}")

            api_metrics = self.sql_validator.validate_sql(api_response, query_context) if api_response else None
            if api_metrics:
                self.logger.info(f"API response score: {api_metrics.overall_score:.2f}")

            # Build a safe reasoning list once and reuse everywhere
            reasoning_list = _pick_reasoning(
                locals().get("selection_reasoning"),
                locals().get("reasoning"),
                getattr(local_metrics, "reasoning", None) if local_metrics else None,
                getattr(api_metrics, "reasoning", None) if api_metrics else None,
                [f"Enhanced analysis: {query_analysis.get('intent', 'unknown')} "
                 f"(confidence: {query_analysis.get('intent_confidence', 0):.2f})"]
            )

            # Select best response
            selector_result = self.selector.select_best_response(
                local_response=local_response,
                api_response=api_response,
                local_metrics=local_metrics,
                api_metrics=api_metrics,
                query_context=query_context,
                local_confidence=local_confidence,
                api_confidence=query_analysis.get('intent_confidence', 0.5),
                model_used="hybrid_parallel"
            )

            selected_response, selection_reasoning, selection_metadata = selector_result

            # Record model interactions is disabled
            local_interaction_id = None
            api_interaction_id = None

            # Record response selection is disabled
            selection_id = None

            # Record SQL processing is disabled
            processing_id = None

            processing_time = time.time() - start_time

            # Extract token usage data if available
            api_cost_usd = None
            api_prompt_tokens = None
            api_completion_tokens = None
            
            self.logger.info(f"Extracting token usage data: api_response_obj={api_response_obj is not None}")
            if api_response_obj and hasattr(api_response_obj, 'metadata') and api_response_obj.metadata:
                token_usage = api_response_obj.metadata.get('token_usage', {})
                self.logger.info(f"Token usage from api_response_obj: {token_usage}")
                if isinstance(token_usage, dict) and token_usage:
                    api_prompt_tokens = token_usage.get('prompt_tokens')
                    api_completion_tokens = token_usage.get('completion_tokens')
                    self.logger.info(f"Extracted prompt_tokens: {api_prompt_tokens}, completion_tokens: {api_completion_tokens}")
                    # Calculate cost based on token usage
                    if api_prompt_tokens is not None and api_completion_tokens is not None:
                        api_cost_usd = (
                            api_prompt_tokens * 0.0000001 +  # Prompt token cost
                            api_completion_tokens * 0.0000002 +  # Completion token cost
                            0.0001  # Base model cost per request
                        )
                        self.logger.info(f"Calculated API cost: {api_cost_usd}")
            else:
                self.logger.info("No api_response_obj or metadata available for token usage extraction")
            
            processing_result = ProcessingResult(
                selected_response=selected_response or "",
                local_response=local_response,
                api_response=api_response,
                processing_mode=processing_mode,
                selection_reasoning=selection_reasoning,
                local_confidence=local_confidence,
                api_confidence=query_analysis.get('intent_confidence', 0.5),
                processing_time=processing_time,
                model_used="hybrid_parallel",
                local_model_name="ollama" if local_response else None,
                api_model_name=api_response_obj.model if api_response_obj else ("deepseek-chat" if api_response else None),
                local_processing_time=processing_time if local_response else None,
                api_processing_time=processing_time if api_response else None,
                api_cost_usd=api_cost_usd,
                api_prompt_tokens=api_prompt_tokens,
                api_completion_tokens=api_completion_tokens
            )

            # Record user query and AI response in dashboard if chat_id is provided
            if chat_id is not None:
                self.logger.info(f"Recording dashboard data for chat_id: {chat_id}")
                # Record user query
                self._record_user_query(
                    chat_id=chat_id,
                    content=user_query,
                    processing_time_ms=int(processing_time * 1000) if processing_time else None,
                    model_name="user"
                )
                
                # Record AI response and capture message ID for token usage recording
                ai_response_content = processing_result.selected_response or ""
                ai_response_message_id = None
                if ai_response_content:
                    ai_response_message_id = self._record_ai_response(
                        chat_id=chat_id,
                        content=ai_response_content,
                        processing_time_ms=int(processing_time * 1000) if processing_time else None,
                        model_name=processing_result.api_model_name or processing_result.local_model_name,
                        status="success" if processing_result.selected_response else "error"
                    )
                
                # Record token usage if we have API response data and a valid message ID
                self.logger.info(f"Checking token usage recording conditions: ai_response_message_id={ai_response_message_id}, api_response_obj={api_response_obj is not None}")
                if ai_response_message_id and api_response_obj and hasattr(api_response_obj, 'metadata') and api_response_obj.metadata:
                    token_usage = api_response_obj.metadata.get('token_usage', {})
                    self.logger.info(f"Token usage data available: {bool(token_usage)}, type: {type(token_usage)}, content: {token_usage}")
                    if isinstance(token_usage, dict) and token_usage:
                        # Only record if we have token data
                        total_tokens = token_usage.get('total_tokens', 0)
                        self.logger.info(f"Total tokens: {total_tokens}")
                        if total_tokens > 0:
                            self.logger.info(f"Recording token usage for chat {chat_id}, message {ai_response_message_id}")
                            self._record_token_usage(chat_id, ai_response_message_id, api_response_obj)
                        else:
                            self.logger.info("Not recording token usage - no tokens or zero tokens")
                    else:
                        self.logger.info("Not recording token usage - no valid token usage data")
                else:
                    self.logger.info("Not recording token usage - conditions not met")
                
                # Fix: Remove query history recording from SOS processor to prevent duplicates
                # Query history is now recorded in main.py for all processing paths
                # This prevents duplicate entries with mismatched data

            return processing_result

        except Exception as e:
            self.logger.error(f"[HYBRID_PROCESSOR] Advanced query processing failed: {e}")
            processing_time = time.time() - start_time
            
            # Fix: Remove query history recording from SOS processor error path to prevent duplicates
            # Query history for failed queries is now recorded in main.py for all processing paths
            # This prevents duplicate entries with mismatched data
            
            # Fallback event recording is disabled
            
            return ProcessingResult(
                selected_response=f"Sorry, I couldn't process that query: {str(e)}",
                local_response=None,
                api_response=None,
                processing_mode="processing_error",
                selection_reasoning=f"Error during processing: {str(e)}",
                local_confidence=0.0,
                api_confidence=0.0,
                processing_time=processing_time,
                model_used="error",
                local_model_name=None,
                api_model_name=None,
                local_processing_time=None,
                api_processing_time=None
            )

            
            # Fallback event recording is disabled
            
            return ProcessingResult(
                selected_response=f"Sorry, I couldn't process that query: {str(e)}",
                local_response=None,
                api_response=None,
                processing_mode="processing_error",
                selection_reasoning=f"Error during processing: {str(e)}",
                local_confidence=0.0,
                api_confidence=0.0,
                processing_time=processing_time,
                model_used="error",
                local_model_name=None,
                api_model_name=None,
                local_processing_time=None,
                api_processing_time=None
            )
        
        finally:
            # Record training data with the new AI training recorder only (removed)
            # if turn_id and processing_result is not None and NEW_TRAINING_RECORDER_AVAILABLE and self.training_data_recorder:
            #     try:
            #         self.record_processing_result_with_ai_recorder(
            #             user_query=user_query,
            #             processing_result=processing_result,
            #             turn_id=turn_id,
            #             session_id=session_id or "",
            #             client_ip=client_ip or "",
            #             user_agent=user_agent or "",
            #             query_analysis=locals().get('query_analysis'),
            #             schema_context=schema_context,
            #             processing_mode=locals().get('processing_mode', 'unknown'),
            #             classification_time_ms=classification_time_ms
            #         )
            #     except Exception as record_error:
            #         self.logger.error(f"[AI_TRAINING] Failed to record hybrid turn with new recorder: {record_error}")
            pass  # Properly close the finally block


    def _record_user_query(self, chat_id: int, content: str, processing_time_ms: Optional[int] = None,
                          tokens_used: Optional[int] = None, model_name: Optional[str] = None) -> Optional[int]:
        """
        Record a user query message in the dashboard_messages table.
        
        Args:
            chat_id: Chat identifier
            content: User query content
            processing_time_ms: Processing time in milliseconds
            tokens_used: Number of tokens used
            model_name: Model name used
            
        Returns:
            Message ID of the newly created message or None if failed
        """
        try:
            message_id = self.dashboard_recorder.record_user_query(
                chat_id=chat_id,
                content=content,
                processing_time_ms=processing_time_ms,
                tokens_used=tokens_used,
                model_name=model_name
            )
            
            if message_id:
                self.logger.info(f"Recorded user query message {message_id} for chat {chat_id}")
            else:
                self.logger.warning(f"Failed to record user query message for chat {chat_id}")
                
            return message_id
        except Exception as e:
            self.logger.error(f"Error recording user query: {str(e)}")
            return None

    def _record_ai_response(self, chat_id: int, content: str, processing_time_ms: Optional[int] = None,
                           tokens_used: Optional[int] = None, model_name: Optional[str] = None,
                           status: str = 'success') -> Optional[int]:
        """
        Record an AI response message in the dashboard_messages table.
        
        Args:
            chat_id: Chat identifier
            content: AI response content
            processing_time_ms: Processing time in milliseconds
            tokens_used: Number of tokens used
            model_name: Model name used
            status: Message status ('success', 'error', 'timeout')
            
        Returns:
            Message ID of the newly created message or None if failed
        """
        try:
            message_id = self.dashboard_recorder.record_ai_response(
                chat_id=chat_id,
                content=content,
                processing_time_ms=processing_time_ms,
                tokens_used=tokens_used,
                model_name=model_name,
                status=status
            )
            
            if message_id:
                self.logger.info(f"Recorded AI response message {message_id} for chat {chat_id}")
            else:
                self.logger.warning(f"Failed to record AI response message for chat {chat_id}")
                
            return message_id
        except Exception as e:
            self.logger.error(f"Error recording AI response: {str(e)}")
            return None

    # Confidence threshold calibration method
    def calibrate_confidence_thresholds(self, query_analysis: Dict) -> Dict:
        """Calibrates confidence thresholds for processing queries."""
        base = {
            'local_confidence': 0.7,
            'skip_api': 0.85,
            'force_hybrid': 0.3
        }
        intent = query_analysis.get('intent')
        if intent == 'floor_production_summary':
            base['local_confidence'] -= 0.1
        if query_analysis.get('entities', {}).get('ctl_codes'):
            base['skip_api'] += 0.05
        if len(query_analysis.get('entities', {}).get('aggregations', [])) > 1:
            base['force_hybrid'] += 0.2
        # Fix: Ensure intent_confidence is properly retrieved and compared
        intent_confidence = query_analysis.get('intent_confidence', 1.0)
        if isinstance(intent_confidence, (int, float)) and intent_confidence < 0.5:
            base['force_hybrid'] += 0.15
        return base

    async def _process_general_query(self, user_query: str, schema_context: str = "", 
                                  file_content: Optional[str] = None, 
                                  file_name: Optional[str] = None) -> ProcessingResult:
        """
        Process general knowledge queries that don't require SQL generation.
        
        Args:
            user_query: The user's general knowledge question
            schema_context: Context/instructions for the AI model
            file_content: Optional file content for file analysis
            file_name: Optional file name for file analysis
            
        Returns:
            ProcessingResult with the general knowledge response
        """
        start_time = time.time()
        
        try:
            # Use DeepSeek client for general knowledge queries
            from .deepseek_client import get_deepseek_client
            client = get_deepseek_client()
            
            # Check if this is a file analysis request
            if file_content and file_name:
                # File analysis mode - use multimodal capabilities
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Please analyze the following file and answer the question: {user_query}\n\nFile Name: {file_name}"
                            },
                            {
                                "type": "text",
                                "text": f"File Content:\n{file_content}"
                            }
                        ]
                    }
                ]
            else:
                # Regular general knowledge mode
                # Ensure we have a system prompt that enforces English responses
                system_prompt = "You are a helpful AI assistant. ALL RESPONSES MUST BE IN ENGLISH LANGUAGE. Provide clear, accurate, and helpful responses to user questions."
                if schema_context and schema_context.strip():
                    system_prompt = f"{system_prompt}\n\nAdditional context:\n{schema_context}"
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ]
            
            # Use appropriate model for general queries
            # Use the general model configuration from config
            from app.config import API_MODELS
            model_config = API_MODELS.get("general", {
                "primary": "meta-llama/llama-3.3-8x22b-instruct:free",
                "secondary": "openchat/openchat-8b",
                "fallback": "microsoft/WizardLM-2-8x22B"
            })
            
            # For file analysis, use DeepSeek Coder model exclusively
            if file_content and file_name:
                model = "deepseek-coder"
            else:
                model = model_config["primary"]
            
            # Make API call
            response = await client.chat_completion(
                messages=messages,
                model=model,
                temperature=0.3 if file_content and file_name else 0.7,  # Lower temperature for file analysis
                max_tokens=2048 if file_content and file_name else 1024
            )
            
            processing_time = time.time() - start_time
            
            if response.success and response.content:
                return ProcessingResult(
                    selected_response=response.content,
                    local_response=None,
                    api_response=response.content,
                    processing_mode="file_analysis" if file_content and file_name else "general_query",
                    selection_reasoning="Generated response for file analysis" if file_content and file_name else "Generated response for general knowledge query",
                    local_confidence=0.0,
                    api_confidence=0.95 if file_content and file_name else 0.9,  # Higher confidence for file analysis
                    processing_time=processing_time,
                    model_used=model,
                    local_model_name=None,
                    api_model_name=model,
                    local_processing_time=None,
                    api_processing_time=processing_time
                )
            else:
                # For general mode, don't fallback to local model - return error instead
                # This ensures that general mode uses API models independently
                processing_time = time.time() - start_time
                
                return ProcessingResult(
                    selected_response=f"Sorry, I couldn't process that general question. The API service is currently unavailable or taking too long to respond. Please try again later.",
                    local_response=None,
                    api_response=None,
                    processing_mode="general_query_api_error",
                    selection_reasoning="API service unavailable or timeout for general query",
                    local_confidence=0.0,
                    api_confidence=0.0,
                    processing_time=processing_time,
                    model_used="api_error",
                    local_model_name=None,
                    api_model_name=None,
                    local_processing_time=None,
                    api_processing_time=None
                )
                
        except Exception as e:
            self.logger.error(f"[HYBRID_PROCESSOR] General query processing failed: {e}")
            processing_time = time.time() - start_time
            
            return ProcessingResult(
                selected_response=f"Sorry, I couldn't process that general question: {str(e)}",
                local_response=None,
                api_response=None,
                processing_mode="general_query_error",
                selection_reasoning=f"Error during general query processing: {str(e)}",
                local_confidence=0.0,
                api_confidence=0.0,
                processing_time=processing_time,
                model_used="error",
                local_model_name=None,
                api_model_name=None,
                local_processing_time=None,
                api_processing_time=None
            )


    # -------- Parallel/timeout helpers --------

    async def _execute_parallel_with_timeout(self, user_query: str, schema_context: str, classification) -> Tuple[Optional[str], Optional[str]]:
        self.logger.info("Starting advanced parallel processing with timeout handling...")
        loop = asyncio.get_event_loop()

        local_coro = self._local_processing(user_query, schema_context)
        api_coro = self._api_processing(user_query, schema_context, classification)

        local_task = loop.create_task(asyncio.wait_for(local_coro, timeout=self.local_timeout))
        api_task = loop.create_task(asyncio.wait_for(api_coro, timeout=self.api_timeout))

        local_response: Optional[str] = None
        api_response: Optional[str] = None

        done, pending = await asyncio.wait({local_task, api_task}, timeout=self.total_timeout, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            try:
                res = task.result()
                if task is local_task:
                    local_response = res
                    self.logger.info("Local processing completed first")
                else:
                    api_response = res
                    self.logger.info("API processing completed first")
            except Exception as e:
                self.logger.error(f"Task failed: {e}")

        # Give the slower one a bit more (up to 5s) if overall budget allows
        if pending and len(done) == 1:
            try:
                more_done, still_pending = await asyncio.wait(pending, timeout=5.0)
                for task in more_done:
                    try:
                        res = task.result()
                        if task is local_task and local_response is None:
                            local_response = res
                            self.logger.info("Local processing completed second")
                        elif task is api_task and api_response is None:
                            api_response = res
                            self.logger.info("API processing completed second")
                    except Exception as e:
                        self.logger.error(f"Second task failed: {e}")
                for task in still_pending:
                    task.cancel()
            except asyncio.TimeoutError:
                self.logger.warning("Second task timed out")
                for task in pending:
                    task.cancel()

        # Cancel any stragglers
        for task in pending:
            if not task.done():
                task.cancel()

        return local_response, api_response

    async def _execute_api_with_timeout(self, user_query: str, schema_context: str, classification) -> Optional[str]:
        try:
            return await asyncio.wait_for(self._api_processing(user_query, schema_context, classification), timeout=self.api_timeout)
        except asyncio.TimeoutError:
            self.logger.error("API processing timeout")
            return None
        except Exception as e:
            self.logger.error(f"API processing failed: {e}")
            return None

    async def _execute_local_with_timeout(self, user_query: str, schema_context: str) -> Optional[str]:
        try:
            return await asyncio.wait_for(self._local_processing(user_query, schema_context), timeout=self.local_timeout)
        except asyncio.TimeoutError:
            self.logger.error("Local processing timeout")
            return None
        except Exception as e:
            self.logger.error(f"Local processing failed: {e}")
            return None

    # -------- SQL normalizer for Oracle date patterns --------
    def _normalize_sql(self, sql: str) -> str:
        """
        Normalize common Oracle date patterns while avoiding TRUNC(SYSDATE ...),
        because downstream lint rejects it.

        Rules:
        - WHERE/AND <DATE_COL> >= TRUNC(SYSDATE) - N
            -> WHERE/AND TRUNC(<DATE_COL>) >= SYSDATE - N
        - WHERE/AND <DATE_COL> >= SYSDATE - N   (leave it, but ensure left side is TRUNC(col))
            -> WHERE/AND TRUNC(<DATE_COL>) >= SYSDATE - N
        - BETWEEN variants:
            WHERE <DATE_COL> BETWEEN (TRUNC(SYSDATE) - N) AND TRUNC(SYSDATE)
            -> WHERE TRUNC(<DATE_COL>) BETWEEN (SYSDATE - N) AND SYSDATE
        - If the model already produced TRUNC(SYSDATE) anywhere, rewrite to SYSDATE.
        """
        if not sql or not isinstance(sql, str):
            return sql

        # 0) Strip TRUNC around SYSDATE globally (safest since linter forbids it)
        sql = re.sub(r'TRUNC\s*\(\s*SYSDATE\s*\)', 'SYSDATE', sql, flags=re.IGNORECASE)

        # 1) >= patterns with explicit TRUNC(SYSDATE) - N (after step 0 it's just SYSDATE - N)
        def wrap_col_ge_repl(m):
            kw = m.group(1)          # WHERE/AND
            col = m.group(2)         # <DATE_COL> like PROD_DATE
            days = m.group(3)        # N
            return f"{kw} TRUNC({col}) >= SYSDATE - {days}"

        sql = re.sub(
            r'\b(WHERE|AND)\s+([A-Z_][A-Z0-9_]*_DATE)\s*>=\s*SYSDATE\s*-\s*(\d+)',
            wrap_col_ge_repl,
            sql,
            flags=re.IGNORECASE
        )

        # 2) BETWEEN SYSDATE - N AND SYSDATE (or had TRUNCs, already removed)
        def between_repl(m):
            kw = m.group(1)      # WHERE
            col = m.group(2)     # <DATE_COL>
            days = m.group(3)    # N
            return f"{kw} TRUNC({col}) BETWEEN SYSDATE - {days} AND SYSDATE"

        sql = re.sub(
            r'\b(WHERE)\s+([A-Z_][A-Z0-9_]*_DATE)\s+BETWEEN\s+SYSDATE\s*-\s*(\d+)\s+AND\s+SYSDATE\b',
            between_repl,
            sql,
            flags=re.IGNORECASE
        )

        # 3) >= TRUNC(SYSDATE) - N case that might still show up (defensive)
        #    (Step 0 already removed TRUNC(SYSDATE), but keep a safety pass for mixed casing/spacing)
        sql = re.sub(
            r'\b(WHERE|AND)\s+([A-Z_][A-Z0-9_]*_DATE)\s*>=\s*TRUNC\s*\(\s*SYSDATE\s*\)\s*-\s*(\d+)',
            wrap_col_ge_repl,
            sql,
            flags=re.IGNORECASE
        )

        return sql


    # -------- API/local processing --------

    async def _api_processing(self, user_query: str, schema_context: str, classification) -> Optional[str]:
        """Process query using OpenRouter API with multi-field awareness."""
        model_type = self._get_model_type_for_intent(classification.intent)

        # Multi-field detection
        mf_indicators = [' vs ', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
        has_multi_fields = any(ind in user_query.lower() for ind in mf_indicators)

        api_start = time.time()
        try:
            enhanced_query = self._preprocess_dates_for_oracle(user_query)
            if has_multi_fields:
                enhanced_query = f"{enhanced_query} (Please provide SQL that returns multiple fields as requested, not just a single value)"

            response = await self.deepseek_client.get_sql_response(
                user_query=enhanced_query,
                schema_context=schema_context,
                model_type=model_type
            )

            self._api_processing_time = time.time() - api_start

            if not response.success:
                self.logger.error(f"API processing failed: {response.error}")
                return None

            final_sql = _extract_sql_from_response(response.content)
            if final_sql:
                final_sql = self._normalize_sql(final_sql)
            if not final_sql:
                self.logger.warning(f"API did not return valid SQL: {response.content[:200]}...")
                return None

            # Multi-field post-check: prefer multiple fields but allow dim+aggregate
            if has_multi_fields:
                sm = re.search(r'SELECT\s+(.*?)\s+FROM', final_sql, re.IGNORECASE | re.DOTALL)
                if sm:
                    sel = sm.group(1).strip()
                    has_comma = (',' in sel)
                    has_dim = re.search(r'\bFLOOR_NAME\b', final_sql, re.IGNORECASE) is not None
                    has_agg = re.search(r'\b(SUM|AVG|COUNT|MAX|MIN)\s*\(', final_sql, re.IGNORECASE) is not None

                    if not (has_comma or (has_dim and has_agg)):
                        self.logger.warning(
                            f"API returned likely single-field SQL for multi-field query: {final_sql}"
                        )

            validity_score = self.sql_validator._assess_sql_validity(final_sql, [])
            if validity_score < 0.3:
                # Soft gate: keep structurally acceptable SQL (has SELECT/FROM and a table)
                if self.sql_validator._first_table_after_from(final_sql):
                    self.logger.warning(
                        f"Low validity score ({validity_score:.2f}) but structurally acceptable; keeping candidate."
                    )
                else:
                    self.logger.warning(
                        f"Dropping SQL (no table after FROM): {final_sql[:160]}..."
                    )
                    return None

            self.logger.info(f"API generated SQL: {final_sql}")
            return final_sql

        except Exception as e:
            self._api_processing_time = time.time() - api_start
            self.logger.error(f"API processing exception: {e}")
            return None

    def _preprocess_dates_for_oracle(self, query: str) -> str:
        """
        Preprocess dates in user queries to make them Oracle-friendly.
        Uses the existing date parsing functions from query_engine.
        """
        from .query_engine import _parse_day_first_date, _to_oracle_date
        date_pattern = re.compile(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b')

        def replacer(m):
            date_str = m.group(0)
            dt = _parse_day_first_date(date_str)
            if dt:
                return _to_oracle_date(dt)
            return date_str

        processed = date_pattern.sub(replacer, query)
        if processed != query:
            self.logger.info(f"Preprocessed dates in query: '{query}' → '{processed}'")
        return processed

    async def _local_processing(self, user_query: str, schema_context: str) -> Optional[str]:
        """Process query using local Ollama model with dynamic schema context."""
        self.logger.info("Local processing using Ollama model with dynamic context")
        local_start = time.time()
        try:
            from .rag_engine import create_dynamic_prompt_context

            enhanced_query = self._preprocess_dates_for_oracle(user_query)
            dynamic_prompt = create_dynamic_prompt_context(
                enhanced_query,
                schema_context,
                "source_db_1"  # keep as-is; UI now controls DB routing in your app
            )

            sql_response = await asyncio.to_thread(ask_sql_model, dynamic_prompt)

            self._local_processing_time = time.time() - local_start
            if sql_response and isinstance(sql_response, str):
                final_sql = _extract_sql_from_response(sql_response)
                if final_sql:
                    final_sql = self._normalize_sql(final_sql)  # ← add this line
                    validity_score = self.sql_validator._assess_sql_validity(final_sql, [])
                    if validity_score < 0.3:
                        if self.sql_validator._first_table_after_from(final_sql):
                            self.logger.warning(
                                f"Low validity score ({validity_score:.2f}) but structurally acceptable; keeping candidate."
                            )
                        else:
                            self.logger.warning(
                                f"Dropping SQL (no table after FROM): {final_sql[:160]}..."
                            )
                            return None

                    self.logger.info(f"Local Ollama generated SQL: {final_sql[:200]}...")
                    return final_sql
                else:
                    self.logger.warning(f"Local Ollama did not return valid SQL: {str(sql_response)[:200]}...")
                    return None

            self.logger.warning("Local Ollama returned empty response")
            return None

        except Exception as e:
            self._local_processing_time = time.time() - local_start
            self.logger.error(f"Local Ollama processing failed: {e}")
            return None

    # -------- Model helpers, complexity, thresholds --------

    def _get_api_model_name(self, classification) -> str:
        model_type = self._get_model_type_for_intent(classification.intent)
        # Use the configured models from API_MODELS instead of hardcoded values
        from app.config import API_MODELS
        model_config = API_MODELS.get(model_type, API_MODELS["general"])
        return model_config["primary"]

    def _get_model_type_for_intent(self, intent: QueryIntent) -> str:
        """Map query intent to appropriate model type."""
        intent_to_model = {
            QueryIntent.PRODUCTION_QUERY: "production",
            QueryIntent.HR_EMPLOYEE_QUERY: "hr",
            QueryIntent.TNA_TASK_QUERY: "tna",
            QueryIntent.SIMPLE_LOOKUP: "general",
            QueryIntent.COMPLEX_ANALYTICS: "analytics",
            QueryIntent.GENERAL_QUERY: "general",
            QueryIntent.DATABASE_QUERY: "general"  # Database queries use general model
        }
        return intent_to_model.get(intent, "general")


    def assess_query_complexity(self, user_query: str, analysis: Dict) -> str:
        """Assess query complexity to determine processing mode."""
        # Simple heuristic: if query mentions multiple entities or has complex logic, use hybrid
        complexity_indicators = [
            'compare', 'versus', 'vs', 'and', 'with', 'between',
            'trend', 'analysis', 'over time', 'monthly', 'weekly',
            'defect', 'production', 'efficiency', 'dhu'
        ]
        
        if any(indicator in user_query.lower() for indicator in complexity_indicators):
            return "hybrid_parallel"
        else:
            return "local_preferred"

    def _record_token_usage(self, chat_id: int, message_id: int, response) -> None:
        """
        Record token usage for a DeepSeek API response.
        
        Args:
            chat_id: Chat identifier
            message_id: Message identifier
            response: DeepSeekResponse object containing token usage data
        """
        try:
            self.logger.info(f"_record_token_usage called with chat_id={chat_id}, message_id={message_id}, response={type(response)}")
            # Extract token usage data from response
            if hasattr(response, 'metadata') and isinstance(response.metadata, dict):
                token_usage = response.metadata.get('token_usage', {})
                self.logger.info(f"Token usage from response metadata: {token_usage}")
                if isinstance(token_usage, dict) and token_usage:
                    prompt_tokens = token_usage.get('prompt_tokens', 0)
                    completion_tokens = token_usage.get('completion_tokens', 0)
                    total_tokens = token_usage.get('total_tokens', 0)
                    
                    self.logger.info(f"Extracted token data: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
                    
                    # Only record if we have token data
                    if total_tokens > 0:
                        # Calculate cost based on token usage
                        cost_usd = (
                            prompt_tokens * 0.0000001 +  # Prompt token cost
                            completion_tokens * 0.0000002 +  # Completion token cost
                            0.0001  # Base model cost per request
                        )
                        
                        self.logger.info(f"Calculated cost: ${round(cost_usd, 6)}")
                        
                        # Get database type from chat
                        database_type = None
                        if self.dashboard_recorder:
                            try:
                                chat = self.dashboard_recorder.dashboard_service.chats.get_chat_by_id(chat_id)
                                database_type = chat.get('database_type') if chat else None
                            except Exception as e:
                                self.logger.error(f"Error getting database type for token usage recording: {str(e)}")
                        
                        # Record token usage in dashboard
                        if self.dashboard_recorder:
                            self.logger.info("Calling dashboard_recorder.record_token_usage")
                            usage_id = self.dashboard_recorder.record_token_usage(
                                chat_id=chat_id,
                                message_id=message_id,
                                model_type="api",
                                model_name=getattr(response, 'model', 'unknown'),
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                total_tokens=total_tokens,
                                cost_usd=round(cost_usd, 6),
                                database_type=database_type
                            )
                            
                            if usage_id:
                                self.logger.info(f"Recorded token usage {usage_id} for chat {chat_id}, message {message_id}: "
                                           f"{total_tokens} tokens, ${round(cost_usd, 6)} cost")
                            else:
                                self.logger.warning(f"Failed to record token usage for chat {chat_id}, message {message_id}")
                        else:
                            self.logger.warning("No dashboard_recorder available for token usage recording")
                    else:
                        self.logger.info("Not recording token usage - total tokens is zero or negative")
                else:
                    self.logger.info("No valid token usage data in response")
            else:
                self.logger.info("Response doesn't have valid metadata for token usage")
        except Exception as e:
            self.logger.error(f"Error recording token usage: {str(e)}", exc_info=True)
