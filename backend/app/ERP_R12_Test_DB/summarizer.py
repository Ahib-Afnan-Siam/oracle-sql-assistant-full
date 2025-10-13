# ERP R12 Summarizer
import logging
from typing import List, Dict, Any
# Use the correct function from ollama_llm
from app.ollama_llm import ask_analytical_model
from app.config import OLLAMA_ANALYTICAL_MODEL, OLLAMA_ANALYTICAL_URL

logger = logging.getLogger(__name__)

def _create_default_response(user_query: str, columns: List[str], rows: List[Dict], sql: str) -> str:
    """
    Create a default summary response when LLM generation fails.
    
    Args:
        user_query: The original user query
        columns: List of column names
        rows: List of result rows
        sql: The SQL query that was executed
        
    Returns:
        A default summary string
    """
    row_count = len(rows)
    
    if row_count == 0:
        return "No data found matching your query criteria."
    
    # Create a simple summary of the data
    summary_parts = [f"Found {row_count} records"]
    
    # Mention key columns if they exist
    if columns:
        key_columns = [col for col in columns if any(keyword in col.lower() for keyword in 
                       ['name', 'id', 'code', 'description'])]
        if key_columns:
            summary_parts.append(f"with {', '.join(key_columns[:3])} information")
    
    return " ".join(summary_parts) + "."

def _process_summarization_response(response: str, fallback: str) -> str:
    """
    Process the LLM response and provide a fallback if needed.
    
    Args:
        response: The LLM response
        fallback: Fallback text if response is invalid
        
    Returns:
        Processed summary text
    """
    if not response or not response.strip():
        return fallback
    
    # Clean up the response
    summary = response.strip()
    
    # Remove any markdown artifacts
    if summary.startswith("```"):
        # Find the end of the code block
        lines = summary.split("\n")
        if len(lines) > 1:
            summary = "\n".join(lines[1:]).strip()
        if summary.endswith("```"):
            summary = summary[:-3].strip()
    
    # If the summary is too short or looks like an error, use fallback
    if len(summary) < 10 or "error" in summary.lower():
        return fallback
    
    return summary

def summarize_results(user_query: str, columns: List[str], rows: List[Dict], sql: str) -> str:
    """
    Generate a natural language summary of ERP R12 query results.
    
    Args:
        user_query: The original user question
        columns: List of column names in results
        rows: List of result rows
        sql: The SQL query that produced the results
        
    Returns:
        Natural language summary of the results
    """
    try:
        # Handle empty results
        if not rows:
            return "No data found matching your query criteria."
        
        # Limit the data we send to the LLM to avoid context overflow
        sample_rows = rows[:50]  # Limit to first 50 rows
        row_count = len(rows)
        
        # Create a data sample for the prompt
        data_sample = []
        for i, row in enumerate(sample_rows):
            row_str = ", ".join([f"{k}: {v}" for k, v in row.items() if v is not None])
            data_sample.append(f"Row {i+1}: {row_str}")
            if i >= 9:  # Limit to 10 sample rows in the prompt
                break
        
        # Create a detailed prompt for summarization
        prompt = f"""
You are an expert ERP R12 data analyst. Provide a clear, concise summary of the following query results in natural language.

Original Question: {user_query}

Data Structure:
Columns: {', '.join(columns)}

Sample Data:
{chr(10).join(data_sample)}

Total Records: {row_count}

Key ERP R12 Context:
- This data comes from Oracle ERP R12 system
- Business Groups organize Operating Units
- Operating Units link to Organizations
- All dates are in standard Oracle date format

Provide a summary that:
1. Answers the original question directly
2. Highlights key findings or patterns
3. Mentions any important data points
4. Uses business terminology appropriate for ERP
5. Is concise but informative (2-3 sentences max)
6. Do not include any markdown formatting
7. Do not include any explanations, just the summary

Summary:
"""
        
        # Generate summary using the analytical model with correct function call
        response = ask_analytical_model(prompt)
        
        # Process the response
        fallback = _create_default_response(user_query, columns, rows, sql)
        summary = _process_summarization_response(response, fallback)
        
        logger.info("Summary generated successfully")
        return summary
        
    except Exception as e:
        logger.error(f"Summary generation failed: {e}", exc_info=True)
        # Return a default summary
        return _create_default_response(user_query, columns, rows, sql)

# Test code removed for production use