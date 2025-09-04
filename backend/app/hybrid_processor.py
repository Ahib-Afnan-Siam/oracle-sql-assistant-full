# c:\Users\MIS\oracle-sql-assistant-full\backend\app\hybrid_processor.py
import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime as _dt
import re
import time
import asyncio

from .query_classifier import QueryClassifier, ConfidenceThresholdManager, QueryIntent, ModelSelectionStrategy
from .openrouter_client import get_openrouter_client
from .ollama_llm import ask_sql_model
from . import config
from .sql_generator import extract_sql as _extract_sql_basic  # Import the existing function

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

        oracle_functions_used = 0
        for func in self.oracle_functions:
            if func in sql.upper():
                oracle_functions_used += 1
                score += 0.06
                reasoning.append(f"Uses Oracle function: {func}")

        if 'TO_DATE' in sql.upper():
            date_format_patterns = ['DD-MON-YY', 'DD-MON-YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD']
            found_format = False
            for pattern in date_format_patterns:
                if pattern in sql or pattern.lower() in sql:
                    found_format = True
                    score += 0.2
                    reasoning.append(f"Proper Oracle date format: {pattern}")
                    break

            for mon in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']:
                if f"'{mon}'" in sql.upper() or f"'-{mon}-'" in sql.upper():
                    score += 0.1
                    reasoning.append(f"Uses correct month abbreviation: {mon}")
                    found_format = True
                    break

            if not found_format:
                score -= 0.05
                reasoning.append("TO_DATE without proper format")

        advanced_functions = ['ADD_MONTHS', 'MONTHS_BETWEEN', 'ROUND', 'TRUNC']
        advanced_used = sum(1 for f in advanced_functions if f in sql.upper())
        if advanced_used > 0:
            score += min(advanced_used * 0.08, 0.15)
            reasoning.append(f"Uses advanced Oracle functions ({advanced_used})")

        join_types = ['INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'FULL OUTER JOIN']
        proper_joins = sum(1 for jt in join_types if jt in sql.upper())
        if proper_joins > 0:
            score += min(proper_joins * 0.12, 0.25)
            reasoning.append(f"Uses proper JOIN syntax ({proper_joins} joins)")

        if 'GROUP BY' in sql.upper() and 'HAVING' in sql.upper():
            score += 0.1
            reasoning.append("Uses advanced GROUP BY with HAVING")

        if 'SELECT' in sql.upper():
            if sql.upper().count('SELECT') > 1:
                if '(' in sql and ')' in sql:
                    score += 0.12
                    reasoning.append("Properly structured subqueries")
                else:
                    score -= 0.1
                    reasoning.append("Potential subquery syntax issues")

        return max(0.0, min(score, 1.0))

    def _assess_manufacturing_domain(self, sql: str, query_context: Dict[str, Any], reasoning: List[str]) -> float:
        score = 0.0
        entities = query_context.get('entities', {})
        intent = query_context.get('intent')

        companies_mentioned = entities.get('companies', [])
        for company in companies_mentioned:
            if company.upper() in sql.upper():
                score += 0.3
                reasoning.append(f"Accurately recognizes company: {company}")

        if intent == QueryIntent.PRODUCTION_QUERY or intent == 'production_query' or intent == 'production_summary':
            if any(t in sql.upper() for t in ['T_PROD', 'T_PROD_DAILY']):
                score += 0.25
                reasoning.append("Uses appropriate production tables")

            production_metrics = ['PRODUCTION_QTY', 'DEFECT_QTY', 'DHU', 'FLOOR_EF']
            used = sum(1 for m in production_metrics if m in sql.upper())
            if used > 0:
                score += min(used * 0.12, 0.25)
                reasoning.append(f"Uses production metrics ({used} metrics)")

        if intent == QueryIntent.TNA_TASK_QUERY or intent == 'tna_task_query':
            if 'T_TNA_STATUS' in sql.upper():
                score += 0.3
                reasoning.append("Uses TNA status table")
            ctl_codes = entities.get('ctl_codes', [])
            for ctl in ctl_codes:
                if ctl.upper() in sql.upper():
                    score += 0.3
                    reasoning.append(f"Handles CTL code: {ctl}")
            tna_columns = ['TASK_SHORT_NAME', 'TASK_FINISH_DATE', 'JOB_NO', 'PO_NUMBER']
            used = sum(1 for c in tna_columns if c in sql.upper())
            if used > 0:
                score += min(used * 0.08, 0.2)
                reasoning.append(f"Uses TNA-specific columns ({used} columns)")
            if 'PP APPROVAL' in sql.upper() or 'PP_APPROVAL' in sql.upper():
                score += 0.15
                reasoning.append("Handles PP Approval tasks specifically")

        if intent == QueryIntent.HR_EMPLOYEE_QUERY or intent == 'hr_employee_query':
            if 'EMP' in sql.upper():
                score += 0.25
                reasoning.append("Uses employee table")
            hr_columns = ['SALARY', 'JOB_TITLE', 'FULL_NAME', 'EMP_ID']
            used = sum(1 for c in hr_columns if c in sql.upper())
            if used > 0:
                score += min(used * 0.1, 0.2)
                reasoning.append(f"Uses HR-specific columns ({used} columns)")

        dates_mentioned = entities.get('dates', [])
        if dates_mentioned and 'WHERE' in sql.upper():
            score += 0.2
            reasoning.append("Incorporates date context in filtering")

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
        for table in ['T_PROD', 'T_PROD_DAILY', 'T_TNA_STATUS']:
            if table in sql.upper():
                base_time += 1.0
        base_time += sql.upper().count('JOIN') * 0.5
        if 'WHERE' in sql.upper():
            indexed_filters = sum(1 for col in self.indexed_columns if col in sql.upper())
            base_time -= indexed_filters * 0.2
        agg_count = sum(1 for agg in ['SUM', 'COUNT', 'AVG', 'MAX', 'MIN', 'GROUP BY'] if agg in sql.upper())
        base_time += agg_count * 0.3
        return max(0.1, base_time)

    def _predict_user_satisfaction(self, sql: str, query_context: Dict[str, Any]) -> float:
        score = 0.5
        intent = query_context.get('intent')
        entities = query_context.get('entities', {})

        if intent in (QueryIntent.PRODUCTION_QUERY, 'production_query') and 'PRODUCTION_QTY' in sql.upper():
            score += 0.2
        elif intent in (QueryIntent.TNA_TASK_QUERY, 'tna_task_query') and 'T_TNA_STATUS' in sql.upper():
            score += 0.2
        elif intent in (QueryIntent.HR_EMPLOYEE_QUERY, 'hr_employee_query') and 'EMP' in sql.upper():
            score += 0.2

        for company in entities.get('companies', []):
            if company.upper() in sql.upper():
                score += 0.1

        if entities.get('dates') and 'WHERE' in sql.upper():
            score += 0.1

        if 'ORDER BY' in sql.upper():
            score += 0.05
        if 'GROUP BY' in sql.upper() and intent in (QueryIntent.PRODUCTION_QUERY, 'production_query', 'production_summary'):
            score += 0.1

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

        if entities.get('companies'):
            for company in entities['companies']:
                if company.upper() in sql.upper():
                    score += 0.3
                    reasoning.append(f"Recognizes company: {company}")
                    break

        if entities.get('ctl_codes'):
            for ctl in entities['ctl_codes']:
                if ctl.upper() in sql.upper():
                    score += 0.3
                    reasoning.append(f"Handles CTL code: {ctl}")
                    break

        # Multi-field relevance
        multi_field_indicators = ['vs', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
        has_multi_fields = any(ind in user_query for ind in multi_field_indicators)
        if has_multi_fields:
            sm = re.search(r'SELECT\s+(.*?)\s+FROM', sql.upper(), re.IGNORECASE | re.DOTALL)
            if sm:
                select_content = sm.group(1).strip()
                field_count = select_content.count(',') + 1
                if field_count > 1:
                    score += min(field_count * 0.1, 0.4)
                    reasoning.append(f"Handles multiple fields ({field_count} fields detected)")
                else:
                    reasoning.append("User requested multiple fields but SQL only contains one field")
                    score -= 0.2

        schema_context = query_context.get('schema_context', '')
        if schema_context:
            numeric_columns = re.findall(r'\b([A-Z_][A-Z0-9_]*)\s+(?:NUMBER|FLOAT|DECIMAL|INT)', schema_context)
            metrics_used = 0
            for col in numeric_columns:
                if col in sql.upper():
                    metrics_used += 1
                    reasoning.append(f"Uses numeric metric: {col}")
            if metrics_used > 0:
                score += min(metrics_used * 0.1, 0.3)

        if entities.get('dates') and 'WHERE' in sql.upper():
            score += 0.2
            reasoning.append("Incorporates date filtering")

        intent = query_context.get('intent')
        if intent in ['tna_task_query', QueryIntent.TNA_TASK_QUERY] and 'T_TNA_STATUS' in sql.upper():
            score += 0.2
            reasoning.append("Proper TNA table usage")
        elif intent in ['production_query', 'production_summary', QueryIntent.PRODUCTION_QUERY] and any(
            t in sql.upper() for t in ['T_PROD', 'T_PROD_DAILY']
        ):
            score += 0.2
            reasoning.append("Proper production table usage")
        elif intent in ['hr_employee_query', QueryIntent.HR_EMPLOYEE_QUERY] and 'EMP' in sql.upper():
            score += 0.2
            reasoning.append("Proper employee table usage")

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
            'technical_accuracy': 0.40,
            'business_logic': 0.30,
            'performance': 0.20,
            'model_confidence': 0.10
        }
        self.domain_rules = {
            'cal_winner_queries': {
                'preferred_models': ['deepseek/deepseek-chat'],
                'weight_boost': 0.15,
                'patterns': [r'\b(CAL|Winner)\b', r'\bproduction\b', r'\bfloor\b']
            },
            'hr_queries': {
                'preferred_models': ['meta-llama/llama-3.1-8b-instruct'],
                'weight_boost': 0.12,
                'patterns': [r'\b(employee|staff|worker|hr)\b', r'\b(salary|designation)\b']
            },
            'ctl_task_queries': {
                'preferred_models': ['deepseek/deepseek-chat'],
                'weight_boost': 0.18,
                'patterns': [r'\bCTL-\d{2}-\d{5,6}\b', r'\b(task|TNA|approval)\b']
            },
            'complex_analytics': {
                'preferred_models': ['deepseek/deepseek-chat', 'meta-llama/llama-3.1-8b-instruct'],
                'weight_boost': 0.10,
                'patterns': [r'\b(trend|analysis|compare|correlation)\b', r'\b(average|sum|group\s+by)\b']
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

        selected_response, reasoning = self._make_selection_decision(
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

        self.logger.info(f"Response selection: {reasoning} (Local: {local_score:.3f}, API: {api_score:.3f})")
        return selected_response, reasoning, detailed_scores

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
        else:
            technical_score = self._estimate_technical_score(response)
            business_score = self._estimate_business_score(response, query_context)
            performance_score = self._estimate_performance_score(response)

        technical_score = max(0, min(1, technical_score))
        business_score = max(0, min(1, business_score))
        performance_score = max(0, min(1, performance_score))
        confidence_score = max(0, min(1, model_confidence))

        overall = (
            technical_score * self.weights['technical_accuracy'] +
            business_score * self.weights['business_logic'] +
            performance_score * self.weights['performance'] +
            confidence_score * self.weights['model_confidence']
        )
        return overall, {
            'technical_accuracy': technical_score,
            'business_logic': business_score,
            'performance': performance_score,
            'model_confidence': confidence_score,
            'weighted_overall': overall
        }

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

        if intent in ('production_query', QueryIntent.PRODUCTION_QUERY) and isinstance(model_name, str) and 'deepseek' in model_name.lower():
            b = 0.08
            domain_boosts['production_intent_boost'] = b
            total_boost += b
        elif intent in ('hr_employee_query', QueryIntent.HR_EMPLOYEE_QUERY) and isinstance(model_name, str) and 'llama' in model_name.lower():
            b = 0.06
            domain_boosts['hr_intent_boost'] = b
            total_boost += b
        elif intent in ('tna_task_query', QueryIntent.TNA_TASK_QUERY) and isinstance(model_name, str) and 'deepseek' in model_name.lower():
            b = 0.10
            domain_boosts['tna_intent_boost'] = b
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
        self.openrouter_client = get_openrouter_client()
        self.sql_validator = SQLValidator()

        # Prefer advanced selector if available; else fallback
        try:
            self.selector = AdvancedResponseSelector()
        except Exception:
            self.selector = self._create_fallback_selector()

        self.logger = logging.getLogger(__name__)
        self.selection_weights = config.RESPONSE_SELECTION_WEIGHTS

        # Default timeouts
        self.local_timeout = 30.0
        self.api_timeout = 45.0
        self.total_timeout = 60.0

        self.processing_stats = {
            'total_queries': 0,
            'parallel_successes': 0,
            'api_selections': 0,
            'local_selections': 0,
            'average_processing_time': 0.0
        }

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
                                     local_confidence: float = 0.5) -> ProcessingResult:
        """
        Advanced parallel processing with sophisticated response selection.
        """
        start_time = time.time()
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
            from app.rag_engine import analyze_enhanced_query
            query_analysis = analyze_enhanced_query(user_query)

            if not has_multi_fields:
                processing_mode = self.assess_query_complexity(user_query, query_analysis)

            thresholds = self.calibrate_confidence_thresholds(query_analysis)

            logger.info(f"Enhanced analysis: {query_analysis.get('intent')} "
                        f"(confidence: {query_analysis.get('intent_confidence', 0):.2f}, "
                        f"mode: {processing_mode})")

            classification = type('obj', (object,), {
                'intent': QueryIntent.GENERAL_QUERY,
                'confidence': query_analysis.get('intent_confidence', 0.5),
                'strategy': ModelSelectionStrategy.HYBRID_PARALLEL
            })()

            query_context: Dict[str, Any] = {
                'user_query': user_query,
                'intent': query_analysis.get('intent', 'general'),
                'entities': query_analysis.get('entities', {}),
                'schema_context': schema_context,
                'original_query': user_query
            }

            decision = self.threshold_manager.get_processing_decision(local_confidence, classification)

            # Execute with timeouts
            local_response: Optional[str] = None
            api_response: Optional[str] = None
            if decision['use_local'] and decision['use_api']:
                local_response, api_response = await self._execute_parallel_with_timeout(
                    user_query, schema_context, classification
                )
            elif decision['use_api']:
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

            # Select best response
            try:
                selected_response, selection_reasoning, sel_details = self.selector.select_best_response(
                    local_response, api_response, local_metrics, api_metrics, query_context,
                    local_confidence=local_confidence, api_confidence=classification.confidence,
                    model_used=self._get_api_model_name(classification)
                )
                selected_confidence = float(sel_details.get("selection_margin", 0.0)) if isinstance(sel_details, dict) else 0.0
                model_used = self._get_api_model_name(classification) if selected_response == (api_response or "") else "Local"
            except Exception as selector_error:
                self.logger.error(f"Response selector failed: {selector_error}")
                if api_response and api_response.strip():
                    selected_response = api_response
                    selection_reasoning = "Selected API response (selector fallback)"
                    selected_confidence = 0.8
                    model_used = "API"
                elif local_response and local_response.strip():
                    selected_response = local_response
                    selection_reasoning = "Selected local response (selector fallback)"
                    selected_confidence = 0.7
                    model_used = "Local"
                else:
                    selected_response = ""
                    selection_reasoning = "No valid response available"
                    selected_confidence = 0.0
                    model_used = "None"

            # Multi-field safety net: prevent SELECT 1 FROM DUAL and generate dynamic SQL
            if has_multi_fields and (not selected_response or selected_response.strip().upper() == "SELECT 1 FROM DUAL"):
                self.logger.info("Multi-field query detected but no valid response available. Generating dynamic SQL.")
                # Parse month/year if present
                m = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})',
                              user_query, re.IGNORECASE)
                month_name = m.group(1).capitalize() if m else None
                year = m.group(2) if m else str(_dt.now().year)
                has_floor = 'floor' in user_query.lower()
                mentions_prod = any(w in user_query.lower() for w in ['production', 'prod', 'qty'])
                mentions_defect = 'defect' in user_query.lower()

                if (mentions_prod or 'qty' in user_query.lower()) and mentions_defect:
                    if has_floor and month_name:
                        month_abbr = month_name[:3].upper()
                        selected_response = f"""
SELECT 
    FLOOR_NAME, 
    SUM(PRODUCTION_QTY) AS TOTAL_PRODUCTION_QTY, 
    SUM(DEFECT_QTY)     AS TOTAL_DEFECT_QTY
FROM 
    T_PROD_DAILY
WHERE 
    PROD_DATE BETWEEN TO_DATE('01-{month_abbr}-{year}', 'DD-MON-YYYY') 
                   AND LAST_DAY(TO_DATE('01-{month_abbr}-{year}', 'DD-MON-YYYY'))
GROUP BY 
    FLOOR_NAME
ORDER BY 
    FLOOR_NAME
""".strip()
                        selection_reasoning = f"Generated dynamic SQL for multi-field production vs defect by floor for {month_name} {year}"
                        model_used = "Dynamic"
                        selected_confidence = 0.65
                    else:
                        selected_response = """
SELECT 
    FLOOR_NAME, 
    SUM(PRODUCTION_QTY) AS TOTAL_PRODUCTION_QTY, 
    SUM(DEFECT_QTY)     AS TOTAL_DEFECT_QTY
FROM 
    T_PROD_DAILY
GROUP BY 
    FLOOR_NAME
ORDER BY 
    FLOOR_NAME
""".strip()
                        selection_reasoning = "Generated dynamic SQL for multi-field production vs defect by floor"
                        model_used = "Dynamic"
                        selected_confidence = 0.6

            # Update stats
            processing_time = time.time() - start_time
            self.processing_stats['total_queries'] += 1
            if model_used and "API" in model_used.upper():
                self.processing_stats['api_selections'] += 1
            elif model_used and "LOCAL" in model_used.upper():
                self.processing_stats['local_selections'] += 1
            if local_response and api_response:
                self.processing_stats['parallel_successes'] += 1
            self.processing_stats['average_processing_time'] = (
                (self.processing_stats['average_processing_time'] * (self.processing_stats['total_queries'] - 1) + processing_time) /
                self.processing_stats['total_queries']
            )

            result = ProcessingResult(
                selected_response=selected_response or "",
                local_response=local_response,
                api_response=api_response,
                processing_mode=processing_mode or "unknown",
                selection_reasoning=selection_reasoning or "No selection reasoning provided",
                local_confidence=local_confidence or 0.0,
                api_confidence=selected_confidence if selected_confidence is not None else 0.0,
                processing_time=processing_time,
                model_used=model_used or "Unknown",
                local_metrics=local_metrics,
                api_metrics=api_metrics,
                local_model_name="ollama_deepseek_coder_v2",
                api_model_name=self._get_api_model_name(classification),
                local_processing_time=getattr(self, '_local_processing_time', None),
                api_processing_time=getattr(self, '_api_processing_time', None)
            )
            self.logger.info(f"Advanced processing completed in {processing_time:.2f}s using {model_used}")
            return result

        except Exception as e:
            self.logger.error(f"Advanced processing failed: {e}")
            processing_time = time.time() - start_time
            return ProcessingResult(
                selected_response="",
                local_response=None,
                api_response=None,
                processing_mode="error",
                selection_reasoning=f"Error during processing: {str(e)}",
                local_confidence=0.0,
                api_confidence=0.0,
                processing_time=processing_time,
                model_used="None",
                local_metrics=None,
                api_metrics=None,
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

            response = await self.openrouter_client.get_sql_response(
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
        from app.query_engine import _parse_day_first_date, _to_oracle_date
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
            from app.rag_engine import create_dynamic_prompt_context

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
        model_mapping = {
            "production": "deepseek/deepseek-chat",
            "hr": "deepseek/deepseek-chat",
            "tna": "deepseek/deepseek-chat",
            "general": "deepseek/deepseek-chat"
        }
        return model_mapping.get(model_type, "deepseek/deepseek-chat")

    def _get_model_type_for_intent(self, intent: QueryIntent) -> str:
        mapping = {
            QueryIntent.PRODUCTION_QUERY: "production",
            QueryIntent.HR_EMPLOYEE_QUERY: "hr",
            QueryIntent.TNA_TASK_QUERY: "tna",
            QueryIntent.COMPLEX_ANALYTICS: "production",
            QueryIntent.SIMPLE_LOOKUP: "general",
            QueryIntent.GENERAL_QUERY: "general"
        }
        return mapping.get(intent, "general")

    def assess_query_complexity(self, user_query: str, analysis: Dict) -> str:
        complexity_factors = {
            'multiple_entities': len(analysis.get('entities', {}).get('companies', [])) +
                                 len(analysis.get('entities', {}).get('floors', [])) > 2,
            'date_operations': bool(analysis.get('entities', {}).get('dates')),
            'aggregations': bool(analysis.get('entities', {}).get('aggregations')),
            'ctl_codes': bool(analysis.get('entities', {}).get('ctl_codes')),
            'multiple_metrics': len(analysis.get('entities', {}).get('metrics', [])) > 1,
            'ambiguous_intent': analysis.get('intent_confidence', 1.0) < 0.7
        }
        complexity_score = sum(complexity_factors.values())
        if complexity_score >= 4:
            return "api_preferred"
        elif complexity_score >= 2:
            return "hybrid_parallel"
        else:
            return "local_preferred"

    def calibrate_confidence_thresholds(self, query_analysis: Dict) -> Dict:
        base = {
            'local_confidence': 0.7,
            'skip_api': 0.85,
            'force_hybrid': 0.3
        }
        intent = query_analysis.get('intent')
        if intent == 'production_summary':
            base['local_confidence'] -= 0.1
        if query_analysis.get('entities', {}).get('ctl_codes'):
            base['skip_api'] += 0.05
        if len(query_analysis.get('entities', {}).get('aggregations', [])) > 1:
            base['force_hybrid'] += 0.2
        if query_analysis.get('intent_confidence', 1.0) < 0.5:
            base['force_hybrid'] += 0.15
        return base


# ------------------------------ Public HybridProcessor wrapper ------------------------------

class HybridProcessor(AdvancedParallelProcessor):
    """Main hybrid processor with backward compatibility."""

    async def process_query(self, *args, **kwargs) -> ProcessingResult:
        return await self.process_query_advanced(*args, **kwargs)
