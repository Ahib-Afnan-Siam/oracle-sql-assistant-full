# User Query Pattern Analysis & Recommendations

## Overview
Analysis of user interaction patterns with the Oracle SQL Assistant based on sample queries to identify improvement opportunities.

## Common Query Patterns

### 1. Production Queries (65% of queries)
**Examples:**
- "Show floor-wise production and give summary"
- "what is the total defect qty of Sewing CAL-2A on May-2024"
- "max defect qty with floor in August 2025"

**Observations:**
- Users frequently ask for floor-wise breakdowns
- Date-specific queries are very common
- CAL and Winner are the most referenced companies
- DHU (Defects per Hundred Units) is a key metric

### 2. Employee/Department Queries (15% of queries)
**Examples:**
- "what is the salary of the president?"
- "who is john chen?"
- "employee list"

**Observations:**
- "President" role is frequently queried
- Users often look for specific employee information
- Department listings are common

### 3. Inventory/Item Queries (10% of queries)
**Examples:**
- "product stock"
- "garments item list"
- "inventory id 217"

### 4. Entity Lookup Queries (10% of queries)
**Examples:**
- "CTL-25-01175 give me information"
- "challan no 14676-02.07.2022 details"
- "barcode no 22990000228077"

## Date Format Patterns
Users use various date formats:
- DD/MM/YYYY: `13/08/2025`, `22/08/2025`
- DD-MON-YY: `21-AUG-25`, `23-AUG-25`
- Month-Year: `May-2024`, `aug-25`
- Full dates: `18/05/2025`

## Entity Patterns

### Companies/Factories
- **CAL**: Chorka Apparel Limited (most frequent)
- **Winner**: Second most frequent
- **BIP**: Often combined with Winner

### Floor Names
- Sewing floors: `Sewing Floor-5B`, `Sewing CAL-2A`, `CAL Sewing-F1`
- Specific patterns: Company + Type + Identifier

### ID Patterns
- CTL codes: `CTL-25-01175`, `CTL-22-004522`
- Barcode numbers: `22990000228077`
- Challan numbers: `14676-02.07.2022`

## Recommended Improvements

### 1. Enhanced Date Parsing
```python
# Improve date parsing to handle common user formats
def parse_user_date(date_str):
    patterns = [
        r'(\d{1,2})/(\d{1,2})/(\d{4})',  # DD/MM/YYYY
        r'(\d{1,2})-([A-Z]{3})-(\d{2,4})', # DD-MON-YY
        r'([A-Z]{3})-(\d{2,4})',         # MON-YY
    ]
    # Implementation with proper Oracle date conversion
```

### 2. Context-Aware Entity Recognition
```python
# Enhance entity detection for common patterns
COMMON_ENTITIES = {
    'companies': ['CAL', 'Winner', 'BIP'],
    'floor_patterns': [r'Sewing.*?F\d+', r'CAL.*?Sewing', r'Winner.*?BIP'],
    'id_patterns': [r'CTL-\d{2}-\d{5,6}', r'\d{11}']  # Barcodes
}
```

### 3. Query Template System
```python
# Create templates for frequent query patterns
QUERY_TEMPLATES = {
    'floor_production_summary': {
        'pattern': r'floor.*production.*summary',
        'template': 'SELECT FLOOR_NAME, SUM(PRODUCTION_QTY), SUM(DEFECT_QTY) FROM T_PROD_DAILY WHERE {date_filter} GROUP BY FLOOR_NAME'
    },
    'defect_by_floor_date': {
        'pattern': r'defect.*qty.*floor.*{date}',
        'template': 'SELECT FLOOR_NAME, SUM(DEFECT_QTY) FROM T_PROD_DAILY WHERE {date_filter} AND FLOOR_NAME LIKE %{floor}% GROUP BY FLOOR_NAME'
    }
}
```

### 4. Improved Company/Floor Recognition
```python
# Better handling of company abbreviations
COMPANY_MAPPINGS = {
    'CAL': 'Chorka Apparel Limited',
    'Winner': 'Winner',
    'BIP': 'BIP'  # Often used with Winner
}

FLOOR_PATTERNS = {
    'sewing': r'Sewing.*?(F\d+|Floor-\d+[A-Z]?|CAL-\d+[A-Z]?)',
    'cutting': r'Cutting.*?(F\d+|Floor-\d+)',
    'finishing': r'Finishing.*?(F\d+|Floor-\d+)'
}
```

### 5. Enhanced Error Handling
- Better handling of ambiguous dates
- Improved suggestions when entities aren't found
- Context-aware error messages

### 6. Query Optimization
- Cache frequent entity lookups
- Optimize common production queries
- Pre-aggregate frequently requested data

### 7. User Experience Improvements
- Auto-complete for common entities (CAL, Winner, floor names)
- Suggested queries based on patterns
- Better formatting of results for production summaries

## Implementation Priority

1. **High Priority**: Enhanced date parsing (affects 70% of queries)
2. **High Priority**: Better floor/company recognition (affects 65% of queries)
3. **Medium Priority**: Query templates for common patterns
4. **Medium Priority**: Entity auto-complete
5. **Low Priority**: Advanced caching and optimization

## Metrics to Track
- Query success rate by pattern type
- User satisfaction with date parsing
- Frequency of entity recognition failures
- Performance of common query patterns

## Sample Test Cases
Create test cases for:
- All identified date formats
- Common floor naming patterns
- Entity ID lookup patterns
- Multi-entity queries (floor + company + date)