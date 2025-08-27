# Integration Guide: Enhanced Query Processing

This guide shows how to integrate the enhanced date parser and entity recognizer into the existing Oracle SQL Assistant.

## Files Created

1. **enhanced_date_parser.py** - Better date parsing for user queries
2. **enhanced_entity_recognizer.py** - Improved entity recognition  
3. **USER_QUERY_ANALYSIS.md** - Comprehensive analysis document

## Integration Steps

### 1. Integrate Enhanced Date Parser

```python
# In app/rag_engine.py, add at the top:
from app.enhanced_date_parser import EnhancedDateParser

# Initialize in the answer() function:
date_parser = EnhancedDateParser()

# Use enhanced date parsing:
def extract_enhanced_date_range(user_query: str) -> Optional[Dict[str, str]]:
    """Enhanced date extraction using the new parser."""
    
    # Try the enhanced parser first
    enhanced_result = date_parser.parse_date_from_query(user_query)
    if enhanced_result:
        return enhanced_result
    
    # Try relative dates
    relative_result = date_parser.extract_relative_dates(user_query)
    if relative_result:
        return relative_result
    
    # Fallback to existing parsing
    return extract_explicit_date_range(user_query)
```

### 2. Integrate Enhanced Entity Recognizer

```python
# In app/rag_engine.py, add at the top:
from app.enhanced_entity_recognizer import EnhancedEntityRecognizer

# Initialize in the answer() function:
entity_recognizer = EnhancedEntityRecognizer()

# Use enhanced entity recognition:
def extract_enhanced_entities(user_query: str) -> Dict:
    """Enhanced entity extraction using the new recognizer."""
    
    analysis = entity_recognizer.analyze_query_intent(user_query)
    
    # Extract specific entities for query building
    companies = [comp['code'] for comp in analysis['companies']]
    floors = [floor['name'] for floor in analysis['floors']]
    ids_and_codes = [id_info['value'] for id_info in analysis['ids_and_codes']]
    
    return {
        'companies': companies,
        'floors': floors,
        'ids_and_codes': ids_and_codes,
        'query_type': analysis['query_type'],
        'metrics': analysis['metrics']
    }
```

### 3. Enhanced Query Planning

```python
# Modified query planning function:
def enhanced_query_planning(user_query: str, options: Dict) -> Dict:
    """Enhanced query planning with better entity and date recognition."""
    
    # Get enhanced entity analysis
    entities = extract_enhanced_entities(user_query)
    date_info = extract_enhanced_date_range(user_query)
    
    # Build plan based on enhanced analysis
    plan = {
        "table": None,
        "metrics": [],
        "filters": {},
        "date_range": date_info,
        "entities": entities
    }
    
    # Company-specific table selection
    if 'CAL' in entities['companies']:
        # Prefer CAL-specific tables or filters
        plan["filters"]["company"] = "CAL"
    
    if 'WINNER' in entities['companies']:
        plan["filters"]["company"] = "WINNER"
    
    # Floor-specific filtering
    if entities['floors']:
        plan["filters"]["floors"] = entities['floors']
    
    # Query type specific logic
    if entities['query_type'] == 'production_summary':
        plan["table"] = select_production_table(date_info, entities)
        plan["metrics"] = ["PRODUCTION_QTY", "DEFECT_QTY"]
        
    elif entities['query_type'] == 'employee_lookup':
        plan["table"] = "EMP"
        if 'president' in [role.lower() for role in entities.get('job_roles', [])]:
            plan["filters"]["job"] = "PRESIDENT"
    
    return plan

def select_production_table(date_info: Dict, entities: Dict) -> str:
    """Select appropriate production table based on date and entities."""
    
    # If specific date mentioned, prefer daily table
    if date_info and date_info.get('type') == 'single_day':
        return "T_PROD_DAILY"
    
    # If month range, could use either
    elif date_info and date_info.get('type') == 'month_range':
        return "T_PROD_DAILY"  # Can aggregate daily data
    
    # Default to daily for most production queries
    return "T_PROD_DAILY"
```

### 4. Enhanced SQL Generation

```python
# Enhanced SQL generation with better filters:
def build_enhanced_sql(plan: Dict, user_query: str) -> str:
    """Build SQL with enhanced entity and date filtering."""
    
    table = plan.get("table", "T_PROD_DAILY")
    metrics = plan.get("metrics", ["*"])
    filters = plan.get("filters", {})
    date_range = plan.get("date_range")
    entities = plan.get("entities", {})
    
    # Build SELECT clause
    if entities.get('query_type') == 'production_summary':
        select_clause = "SELECT FLOOR_NAME, SUM(PRODUCTION_QTY) as TOTAL_PRODUCTION, SUM(DEFECT_QTY) as TOTAL_DEFECTS"
        group_by = "GROUP BY FLOOR_NAME"
    else:
        select_clause = f"SELECT {', '.join(metrics)}"
        group_by = ""
    
    # Build WHERE clause
    where_conditions = []
    
    # Date filtering
    if date_range:
        date_col = get_date_column_for_table(table)
        if date_range.get('type') == 'single_day':
            where_conditions.append(f"{date_col} = {date_range['start']}")
        else:
            where_conditions.append(f"{date_col} BETWEEN {date_range['start']} AND {date_range['end']}")
    
    # Company filtering
    if filters.get('company'):
        # This would need to be mapped to actual column names
        company_col = get_company_column_for_table(table)
        where_conditions.append(f"{company_col} LIKE '%{filters['company']}%'")
    
    # Floor filtering
    if filters.get('floors'):
        floor_conditions = []
        for floor in filters['floors']:
            floor_conditions.append(f"FLOOR_NAME LIKE '%{floor}%'")
        if floor_conditions:
            where_conditions.append(f"({' OR '.join(floor_conditions)})")
    
    # ID/Code filtering
    if entities.get('ids_and_codes'):
        for id_value in entities['ids_and_codes']:
            # Try to find appropriate ID columns
            id_columns = find_id_columns_for_table(table)
            if id_columns:
                id_conditions = []
                for col in id_columns:
                    id_conditions.append(f"{col} = '{id_value}'")
                where_conditions.append(f"({' OR '.join(id_conditions)})")
    
    # Build final SQL
    sql = f"{select_clause} FROM {table}"
    
    if where_conditions:
        sql += f" WHERE {' AND '.join(where_conditions)}"
    
    if group_by:
        sql += f" {group_by}"
    
    # Add ordering for better results
    if entities.get('query_type') == 'production_summary':
        sql += " ORDER BY TOTAL_PRODUCTION DESC"
    
    return sql

def get_date_column_for_table(table: str) -> str:
    """Get the appropriate date column for a table."""
    date_columns = {
        'T_PROD_DAILY': 'PROD_DATE',
        'T_PROD': 'PROD_DATE',
        'EMP': 'HIREDATE',
        'T_ORDC': 'SHIPDATE'
    }
    return date_columns.get(table, 'DATE_CREATED')

def get_company_column_for_table(table: str) -> str:
    """Get the appropriate company column for a table.""" 
    company_columns = {
        'T_PROD_DAILY': 'COMPANY_ID',
        'T_PROD': 'COMPANY_ID',
        'T_ORDC': 'FACTORY'
    }
    return company_columns.get(table, 'COMPANY_ID')

def find_id_columns_for_table(table: str) -> List[str]:
    """Find ID-like columns for a table."""
    # This would query the database schema
    # Simplified version:
    common_id_columns = ['ID', 'CODE', 'NUMBER', 'BARCODE', 'CHALLAN_NO']
    return common_id_columns
```

### 5. Usage in RAG Engine

```python
# Modified answer function in rag_engine.py:
def answer(user_query: str, selected_db: str = "source_db_1") -> Dict[str, Any]:
    """Enhanced answer function with improved parsing."""
    
    # Initialize enhanced parsers
    date_parser = EnhancedDateParser()
    entity_recognizer = EnhancedEntityRecognizer()
    
    # Get schema context (existing code)
    schema_chunks, schema_context_ids = get_schema_context(user_query, selected_db)
    options = parse_schema_context(schema_chunks)
    
    # Enhanced entity analysis
    entity_analysis = entity_recognizer.analyze_query_intent(user_query)
    
    # Check for typos and suggest corrections
    suggestions = entity_recognizer.suggest_corrections(user_query)
    if suggestions:
        logger.info(f"Query suggestions: {suggestions}")
    
    # Enhanced date parsing
    date_info = date_parser.parse_date_from_query(user_query)
    if not date_info:
        date_info = date_parser.extract_relative_dates(user_query)
    
    # Build enhanced plan
    enhanced_plan = enhanced_query_planning(user_query, options)
    enhanced_plan.update({
        'entity_analysis': entity_analysis,
        'date_info': date_info
    })
    
    # Try enhanced SQL generation
    try:
        sql = build_enhanced_sql(enhanced_plan, user_query)
        logger.info(f"Enhanced SQL: {sql}")
        
        # Execute and return results (existing code)
        # ... rest of the function
        
    except Exception as e:
        logger.warning(f"Enhanced SQL generation failed: {e}")
        # Fallback to existing logic
        return original_answer_logic(user_query, selected_db)
```

## Benefits of Integration

1. **Better Date Handling**: Handles all common date formats users actually use
2. **Improved Entity Recognition**: Recognizes company codes, floor names, and ID patterns
3. **Query Type Classification**: Better understanding of what users want
4. **Typo Correction**: Suggests corrections for common typos
5. **Context-Aware Table Selection**: Chooses appropriate tables based on entities and dates

## Testing

Create test cases for:
- All date formats from the sample queries
- Company and floor name recognition
- ID pattern matching
- Query type classification
- Integration with existing RAG engine

## Monitoring

Track metrics for:
- Improved query success rates
- Better date parsing accuracy
- Entity recognition effectiveness
- User satisfaction with results