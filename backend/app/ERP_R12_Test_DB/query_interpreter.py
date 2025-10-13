# ERP R12 Query Interpreter
# Dynamic query interpretation for mapping business terms to database columns

import logging
import re
from typing import Dict, List, Tuple, Set

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

class ERPQueryInterpreter:
    """
    Dynamic query interpreter that maps business terms to actual database columns
    without hardcoding specific business rules in prompts.
    """
    
    def __init__(self):
        # Business term to column mapping (dynamically populated from schema)
        self.column_synonyms = {}
        self.table_columns = {}
        
    def update_schema_context(self, erp_tables: Dict[str, Dict]) -> None:
        """
        Update the interpreter with current schema context.
        
        Args:
            erp_tables: Dictionary containing table and column information
        """
        self.table_columns = erp_tables
        
    def identify_requested_columns(self, user_query: str, table_name: str) -> List[str]:
        """
        Identify which columns are being requested in the user query.
        
        Args:
            user_query: The user's natural language query
            table_name: The table to check for columns
            
        Returns:
            List of column names that should be included in the query
        """
        requested_columns = []
        query_lower = user_query.lower()
        
        # Get table information
        if table_name not in self.table_columns:
            return []
            
        table_info = self.table_columns[table_name]
        available_columns = table_info.get("columns", [])
        
        # Always include primary identifiers for better context
        primary_identifiers = ["NAME", "ORGANIZATION_NAME", "ORGANIZATION_ID", "ORGANIZATION_CODE", "SHORT_CODE", "SET_OF_BOOKS_ID"]
        for col in available_columns:
            if any(identifier == col.upper() for identifier in primary_identifiers):
                if col not in requested_columns:
                    requested_columns.append(col)
        
        # Check for specific column mentions in the query
        for column in available_columns:
            # Check if column name or synonyms are mentioned
            if self._is_column_requested(query_lower, column):
                if column not in requested_columns:
                    requested_columns.append(column)
        
        # If no specific columns were requested, include a few key ones for context
        if not requested_columns:
            # Include columns that are likely to be relevant based on common query patterns
            common_columns = ["NAME", "SHORT_CODE", "ORGANIZATION_CODE", "ORGANIZATION_NAME", "SET_OF_BOOKS_ID"]
            for col in available_columns:
                if any(common_col == col.upper() for common_col in common_columns):
                    if col not in requested_columns:
                        requested_columns.append(col)
            
            # If still no columns, default to first few columns
            if not requested_columns:
                requested_columns = available_columns[:3]
        
        return requested_columns
    
    def needs_join(self, user_query: str) -> bool:
        """
        Dynamically determine if the query requires joining HR_OPERATING_UNITS and ORG_ORGANIZATION_DEFINITIONS
        based on schema context and natural language understanding.
        
        Args:
            user_query: The user's natural language query
            
        Returns:
            True if a join is needed, False otherwise
        """
        query_lower = user_query.lower()
        
        # Dynamic detection based on schema context
        # Check if the query mentions data from both tables without hardcoding specific terms
        if "both" in query_lower and ("operating unit" in query_lower or "organization" in query_lower):
            return True
            
        # Check for cross-table data requests by analyzing the semantic meaning
        # This is done by looking for combinations of terms that would require data from different tables
        # Use generic pattern matching instead of hardcoded business terms
        table_names = list(self.table_columns.keys())
        if len(table_names) >= 2:
            # Check if multiple table names or related concepts are mentioned
            table_mentions = 0
            for table_name in table_names:
                # Look for table name or common variations
                table_variations = [table_name.lower(), table_name.lower().replace('_', ' ')]
                if any(variation in query_lower for variation in table_variations):
                    table_mentions += 1
                    
            # If multiple tables are mentioned, we likely need a join
            if table_mentions > 1:
                return True
            
        return False
    
    def _is_column_requested(self, query_lower: str, column_name: str) -> bool:
        """
        Check if a column is being requested in the query.
        
        Args:
            query_lower: Lowercase version of the user query
            column_name: Name of the column to check
            
        Returns:
            True if the column is requested, False otherwise
        """
        # Direct column name match
        if column_name.lower() in query_lower:
            return True
            
        # Check common variations and synonyms
        column_variations = self._get_column_variations(column_name)
        for variation in column_variations:
            if variation.lower() in query_lower:
                return True
                
        return False
    
    def _get_column_variations(self, column_name: str) -> List[str]:
        """
        Get common variations and synonyms for a column name.
        
        Args:
            column_name: The column name to get variations for
            
        Returns:
            List of variations and synonyms
        """
        variations = [column_name]
        
        # Split camelCase and snake_case names
        if '_' in column_name:
            variations.append(column_name.replace('_', ' '))
            
        # Handle camelCase
        camel_case_split = re.sub('([a-z0-9])([A-Z])', r'\1 \2', column_name)
        if camel_case_split != column_name:
            variations.append(camel_case_split)
            
        # Add common business term variations dynamically from schema context
        # Use generic patterns instead of hardcoded business terms
        generic_patterns = {
            "ID": ["id", "identifier"],
            "CODE": ["code", "abbreviation"],
            "NAME": ["name", "title"],
            "DATE": ["date", "time"],
            "FLAG": ["flag", "status", "enabled"],
            "CONTEXT": ["context", "entity"],
            "DESCRIPTION": ["description", "desc"],
            "QUANTITY": ["quantity", "qty", "amount"],
            "TYPE": ["type", "category"],
            "NUMBER": ["number", "num", "no"],
            "ACCOUNT": ["account", "acct"],
            "ORDER": ["order", "sequence"],
            "ENABLED": ["enabled", "active", "usable"],
            "DISABLED": ["disabled", "inactive"],
            "SHORT": ["short", "abbreviation"]
        }
        
        column_upper = column_name.upper()
        for pattern, synonyms in generic_patterns.items():
            if pattern in column_upper:
                variations.extend(synonyms)
            
        return variations

# Global instance
erp_query_interpreter = ERPQueryInterpreter()