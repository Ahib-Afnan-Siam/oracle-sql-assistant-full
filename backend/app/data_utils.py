import logging

logger = logging.getLogger(__name__)

def calculate_swing(rows: list, column_name: str) -> float:
    """Calculate difference between max and min values in a column"""
    if not rows:
        return 0.0
    
    try:
        # Extract values from rows (handling both dict and list formats)
        values = []
        for row in rows:
            if isinstance(row, dict):
                value = row.get(column_name)
            elif isinstance(row, list) and len(row) > 0:
                value = row[0]  # Simple approach for list of lists
            else:
                value = None
                
            if value is not None:
                try:
                    values.append(float(value))
                except (ValueError, TypeError):
                    continue
        
        if not values:
            return 0.0
            
        return max(values) - min(values)
        
    except Exception as e:
        logger.error(f"Swing calculation error: {str(e)}")
        return 0.0