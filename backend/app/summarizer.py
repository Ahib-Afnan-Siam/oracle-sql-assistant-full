import os
import re
import json
import logging
import asyncio
import time
from typing import Sequence, Dict, Any, List, Optional, Tuple
from decimal import Decimal

from app.ollama_llm import ask_analytical_model
from app.config import SUMMARY_MAX_ROWS, SUMMARY_CHAR_BUDGET, OPENROUTER_ENABLED, SUMMARY_ENGINE

# Import OpenRouter client
from app.openrouter_client import OpenRouterClient
from app.config import API_MODELS

logger = logging.getLogger(__name__)

# -------------------------
# Configuration
# -------------------------
MAX_BULLETS = int(os.getenv("SUMMARY_BULLETS", "6"))
DIRECT_ANSWER_ENABLED = os.getenv("SUMMARY_DIRECT_ANSWER", "1") == "1"
ALLOW_LLM_FALLBACK = os.getenv("SUMMARY_ALLOW_LLM_FALLBACK", "0") == "1"
ENTITY_MAX_RESULTS = int(os.getenv("SUMMARY_ENTITY_MAX_RESULTS", "6"))

# -------------------------
# Helper functions
# -------------------------
def _is_num(v) -> bool:
    """Check if a value is numeric."""
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)

def _fmt_num(x) -> str:
    """Format a number for display."""
    if x is None: 
        return "—"
    if isinstance(x, Decimal): 
        x = float(x)
    s = f"{x:,.2f}"
    return s.rstrip("0").rstrip(".")

def _pick_metric_columns(columns: Sequence[str], rows: Sequence[Dict[str, Any]], user_query: str) -> List[str]:
    """Pick the most relevant metric columns based on the query."""
    if not rows:
        return []
    
    # Simple approach: pick numeric columns
    numeric_cols = []
    for col in columns:
        # Check if column has numeric values
        sample_values = [r.get(col) for r in rows[:10] if col in r]
        if sample_values and any(_is_num(v) for v in sample_values):
            numeric_cols.append(col)
    
    return numeric_cols

def _pick_label_columns(columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> List[str]:
    """Pick label columns (non-numeric columns)."""
    if not rows:
        return []
    
    label_cols = []
    for col in columns:
        # Check if column has non-numeric values
        sample_values = [r.get(col) for r in rows[:10] if col in r]
        if sample_values and not all(_is_num(v) for v in sample_values):
            label_cols.append(col)
    
    return label_cols

def extract_production_context(user_query: str, columns: List[str]) -> Dict[str, Any]:
    """Extract production context from user query."""
    return {
        'intent': 'general',
        'entities': {}
    }

def _generate_comprehensive_report(user_query: str, columns: List[str], rows: List[Dict[str, Any]]) -> str:
    """
    Generates a comprehensive business report based on the query results.
    This function is used when API summarization fails but we still need a detailed report.
    """
    try:
        if not rows:
            return "No data found matching your criteria."
        
        # Find numeric and label columns
        numeric_cols = []
        label_cols = []
        for col in columns:
            # Sample a few values to determine column type
            sample_values = [r.get(col) for r in rows[:5] if col in r and r.get(col) is not None]
            if not sample_values:
                continue
                
            if all(_is_num(v) for v in sample_values if v is not None):
                numeric_cols.append(col)
            else:
                label_cols.append(col)
        
        # Start building the report
        report_sections = []
        
        # 1. Overview section
        overview = f"# Production Report\n\n"
        overview += f"## Overview\n\n"
        overview += f"This report analyzes data across {len(rows)} records from the manufacturing floor.\n\n"
        
        # 2. Key metrics section
        metrics_section = "## Key Metrics\n\n"
        
        for col in numeric_cols[:4]:  # Focus on top 4 numeric columns
            try:
                values = [float(r[col]) for r in rows if col in r and _is_num(r.get(col))]
                if values:
                    total = sum(values)
                    avg = total / len(values)
                    max_val = max(values)
                    min_val = min(values)
                    
                    metric_name = col.replace('_', ' ').title()
                    
                    # Different formatting for different metric types
                    if "efficiency" in col.lower() or "ef" in col.lower() or "dhu" in col.lower():
                        metrics_section += f"- **{metric_name}**: Average: {_fmt_num(avg)}%, Range: {_fmt_num(min_val)}% to {_fmt_num(max_val)}%\n"
                    elif "defect" in col.lower():
                        defect_rate = (total / sum([float(r.get(numeric_cols[0])) for r in rows if numeric_cols[0] in r and _is_num(r.get(numeric_cols[0]))]) * 100) if numeric_cols and numeric_cols[0] != col else 0
                        metrics_section += f"- **{metric_name}**: Total: {_fmt_num(total)}, Defect Rate: {_fmt_num(defect_rate)}%\n"
                    else:
                        metrics_section += f"- **{metric_name}**: Total: {_fmt_num(total)}, Average: {_fmt_num(avg)}\n"
            except (ValueError, TypeError, ZeroDivisionError):
                continue
        
        metrics_section += "\n"
        
        # 3. Analysis by category (if applicable)
        analysis_section = ""
        primary_label_col = next((col for col in label_cols if "floor" in col.lower()), None) or next((col for col in label_cols), None)
        primary_metric_col = next((col for col in numeric_cols if "production" in col.lower() or "qty" in col.lower()), None) or next((col for col in numeric_cols), None)
        
        if primary_label_col and primary_metric_col:
            analysis_section = f"## Analysis by {primary_label_col.replace('_', ' ').title()}\n\n"
            
            # Group and analyze data by the primary label
            category_data = {}
            for row in rows:
                category = row.get(primary_label_col)
                if category and primary_metric_col in row and _is_num(row.get(primary_metric_col)):
                    if category not in category_data:
                        category_data[category] = []
                    category_data[category].append(float(row.get(primary_metric_col)))
            
            # Calculate aggregates for each category
            category_stats = {}
            for category, values in category_data.items():
                category_stats[category] = {
                    'total': sum(values),
                    'avg': sum(values) / len(values) if values else 0
                }
            
            # Sort categories by total value
            sorted_categories = sorted(category_stats.items(), key=lambda x: x[1]['total'], reverse=True)
            
            # Display top performers
            if sorted_categories:
                top_performer = sorted_categories[0]
                analysis_section += f"- Top performing {primary_label_col.replace('_', ' ').title()}: **{top_performer[0]}** with {_fmt_num(top_performer[1]['total'])} {primary_metric_col.replace('_', ' ').title()}\n"
                
                # Add comparison to average if more than one category
                if len(sorted_categories) > 1:
                    avg_total = sum(stats['total'] for _, stats in category_stats.items()) / len(category_stats)
                    diff_pct = ((top_performer[1]['total'] - avg_total) / avg_total * 100) if avg_total else 0
                    analysis_section += f"  This is {_fmt_num(abs(diff_pct))}% {'above' if diff_pct >= 0 else 'below'} the average across all {primary_label_col.replace('_', ' ').title().lower()}s.\n"
                
                # Add information about lowest performer if available
                if len(sorted_categories) > 1:
                    bottom_performer = sorted_categories[-1]
                    analysis_section += f"- Lowest performing {primary_label_col.replace('_', ' ').title()}: **{bottom_performer[0]}** with {_fmt_num(bottom_performer[1]['total'])} {primary_metric_col.replace('_', ' ').title()}\n"
            
            analysis_section += "\n"
        
        # 4. Insights and Recommendations
        insights_section = "## Insights and Recommendations\n\n"
        
        # Check for efficiency patterns
        efficiency_col = next((col for col in numeric_cols if "efficiency" in col.lower() or "ef" in col.lower()), None)
        production_col = next((col for col in numeric_cols if "production" in col.lower() or "qty" in col.lower()), None)
        defect_col = next((col for col in numeric_cols if "defect" in col.lower()), None)
        
        if efficiency_col and production_col:
            # Check correlation between efficiency and production
            high_ef_rows = [r for r in rows if efficiency_col in r and production_col in r and _is_num(r.get(efficiency_col)) and float(r.get(efficiency_col)) > 70]
            high_prod_from_high_ef = sum(float(r.get(production_col)) for r in high_ef_rows if _is_num(r.get(production_col)))
            total_prod = sum(float(r.get(production_col)) for r in rows if production_col in r and _is_num(r.get(production_col)))
            
            if high_ef_rows and total_prod > 0:
                high_ef_contribution = (high_prod_from_high_ef / total_prod * 100)
                insights_section += f"- Floors with efficiency above 70% contribute to {_fmt_num(high_ef_contribution)}% of total production.\n"
                insights_section += f"- Recommendation: Analyze high-efficiency floors to identify best practices that can be implemented across all production lines.\n"
        
        if defect_col and production_col:
            # Check floors with high defect rates
            floor_defect_rates = []
            for row in rows:
                if primary_label_col in row and defect_col in row and production_col in row:
                    if _is_num(row.get(defect_col)) and _is_num(row.get(production_col)) and float(row.get(production_col)) > 0:
                        defect_rate = (float(row.get(defect_col)) / float(row.get(production_col))) * 100
                        floor_defect_rates.append((row.get(primary_label_col), defect_rate))
            
            if floor_defect_rates:
                # Sort by defect rate
                floor_defect_rates.sort(key=lambda x: x[1], reverse=True)
                highest_defect_floor = floor_defect_rates[0]
                
                insights_section += f"- **{highest_defect_floor[0]}** has the highest defect rate at {_fmt_num(highest_defect_floor[1])}%.\n"
                insights_section += f"- Recommendation: Conduct quality control review for {highest_defect_floor[0]} to identify and address quality issues.\n"
        
        # 5. Conclusion
        conclusion = "\n## Conclusion\n\n"
        conclusion += "This report provides an overview of the production metrics across different manufacturing floors. "
        conclusion += "Regular monitoring of these metrics will help identify opportunities for process improvement and quality control enhancements."
        
        # Combine all sections
        report_sections = [
            overview,
            metrics_section,
            analysis_section,
            insights_section,
            conclusion
        ]
        
        return "\n".join([section for section in report_sections if section])
        
    except Exception as e:
        logger.error(f"Comprehensive report generation error: {e}")
        return f"Production Report: Found {len(rows)} records matching your query."
# -------------------------
# Dynamic API Summarization
# -------------------------

def _should_use_api_summarization(user_query: str, rows: Sequence[Dict[str, Any]]) -> bool:
    """
    Determine if we should use API-based summarization based on query complexity and data size.
    """
    # Always use API if OpenRouter is enabled
    if OPENROUTER_ENABLED:
        return True
        
    # Fallback logic if OpenRouter is disabled
    return False

def _format_data_for_api(columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> str:
    """
    Format the data in a way that's suitable for API processing.
    """
    if not rows:
        return "No data available."
    
    # For small datasets, provide detailed information
    if len(rows) <= 5:
        formatted_rows = []
        for i, row in enumerate(rows, 1):
            row_str = f"Record {i}: "
            row_parts = []
            for col in columns:
                if col in row and row[col] is not None:
                    value = row[col]
                    if isinstance(value, (int, float, Decimal)):
                        if isinstance(value, Decimal):
                            value = float(value)
                        value = f"{value:,}" if value == int(value) else f"{value:,.2f}".rstrip('0').rstrip('.')
                    row_parts.append(f"{col}={value}")
            row_str += ", ".join(row_parts)
            formatted_rows.append(row_str)
        return "\n".join(formatted_rows)
    
    # For larger datasets, provide aggregated information
    else:
        summary = f"Dataset with {len(rows)} records and {len(columns)} columns:\n"
        summary += "Columns: " + ", ".join(columns) + "\n"
        
        # Group numeric columns for aggregation
        numeric_cols = []
        for col in columns:
            sample = next((r.get(col) for r in rows if col in r and r.get(col) is not None), None)
            if sample is not None and isinstance(sample, (int, float, Decimal)) and not isinstance(sample, bool):
                numeric_cols.append(col)
        
        # Calculate aggregations for numeric columns
        if numeric_cols:
            summary += "\nAggregated data:\n"
            for col in numeric_cols:
                values = [float(r[col]) for r in rows if col in r and r.get(col) is not None and isinstance(r.get(col), (int, float, Decimal))]
                if values:
                    total = sum(values)
                    avg = total / len(values)
                    summary += f"  {col}: Total={total:,.2f}, Average={avg:,.2f}\n"
        
        # Show sample records
        summary += "\nSample records:\n"
        for i in range(min(3, len(rows))):
            row = rows[i]
            row_parts = []
            for col in columns[:5]:  # Limit columns for brevity
                if col in row and row[col] is not None:
                    value = row[col]
                    if isinstance(value, (int, float, Decimal)):
                        if isinstance(value, Decimal):
                            value = float(value)
                        value = f"{value:,}" if value == int(value) else f"{value:,.2f}".rstrip('0').rstrip('.')
                    row_parts.append(f"{col}={value}")
            summary += f"  Record {i+1}: " + ", ".join(row_parts) + "\n"
        
        return summary

def _create_summarization_prompt(user_query: str, columns: Sequence[str], rows: Sequence[Dict[str, Any]], sql: Optional[str] = None) -> str:
    """
    Create a prompt for the API to generate a natural language summary.
    """
    # Format the data for the API
    data_summary = _format_data_for_api(columns, rows)
    
    # Detect if this is a TNA task query by checking for CTL pattern or task-related terms
    is_tna_query = bool(re.search(r'\bCTL-\d{2}-\d{5,6}\b', user_query) or 
                         re.search(r'\b(task|tna|pp approval|job no)\b', user_query.lower()))
    
    prompt = f"""You are an intelligent data analyst assistant for a manufacturing company. Your task is to provide a comprehensive and detailed summary report based on the database query results.

User Question: "{user_query}"

Database Query Results:
{data_summary}

"""
    
    if sql:
        prompt += f"SQL Query Used: {sql}\n\n"
    
    if is_tna_query:
        prompt += """Please provide a detailed summary report for this TNA (Time and Action) task query that:
1. Starts with a clear overview directly addressing the user's question about the specific CTL code, task, or date mentioned
2. Summarizes the key task information including job number, PO number, task details, and task dates
3. Explicitly states whether tasks are completed (if ACTUAL_FINISH_DATE is not null) or pending (if ACTUAL_FINISH_DATE is null)
4. Provides context about the buyer and style information if available
5. Highlights any upcoming deadlines or overdue tasks by comparing dates
6. Formats the response as a professional business report focusing on task status and schedule information
7. Includes specific task details and dates to support your summary

Your response should be direct, comprehensive, and clearly answer what the user is asking about the TNA tasks or CTL code in question.
"""
    else:
        prompt += """Please provide a detailed analytical report that:
1. Starts with a clear overview of what the data shows, addressing the user's specific question
2. Highlights key metrics and their significance (production quantities, defects, efficiency rates, etc.)
3. Identifies notable patterns, top performers, and areas that may need attention
4. Compares different floors or categories and points out significant differences
5. Provides context and insights that would be valuable for manufacturing management
6. Uses a professional business report tone with clear sections and well-structured information
7. Includes specific numbers and percentages to support observations
8. Concludes with 2-3 key takeaways or recommendations based on the data

Your response should be comprehensive (at least 150-200 words) and formatted as a proper business report with sections.
"""
    
    return prompt

def _select_summarization_model(user_query: str, row_count: int) -> str:
    """
    Select the appropriate model based on query complexity and data size.
    """
    # For manufacturing/production data, always use the more capable model
    if "production" in user_query.lower() or "floor" in user_query.lower():
        return API_MODELS["general"]["primary"]  # DeepSeek model - more capable
        
    # For simple queries or small datasets, use a faster model
    if row_count <= 5 and len(user_query.split()) <= 8:
        return API_MODELS["general"]["secondary"]  # Llama model - faster
    
    # For complex queries or larger datasets, use a more capable model
    return API_MODELS["general"]["primary"]  # DeepSeek model - more capable

async def _generate_api_summary_async(
    user_query: str,
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    sql: Optional[str] = None
) -> str:
    """
    Generate a natural language summary using the OpenRouter API (async version).
    """
    try:
        # Prepare data for the API
        data_summary = _format_data_for_api(columns, rows)
        
        # Create prompt for the API
        prompt = _create_summarization_prompt(user_query, columns, rows, sql)
        
        # Select appropriate model based on query complexity
        model = _select_summarization_model(user_query, len(rows))
        
        # Call the API
        client = OpenRouterClient()
        response = await client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.3,
            max_tokens=500
        )
        
        if response.success and response.content:
            return response.content.strip()
        else:
            logger.warning(f"API summarization failed: {response.error}")
            # Fallback to traditional summarization
            return _fallback_summarization(user_query, columns, rows)
            
    except Exception as e:
        logger.error(f"API summarization error: {e}")
        # Fallback to traditional summarization
        return _fallback_summarization(user_query, columns, rows)

def _generate_api_summary(
    user_query: str,
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    sql: Optional[str] = None
) -> str:
    """Synchronous wrapper for the async API summary generation."""
    
    try:
        # Use a simpler synchronous approach to avoid event loop issues
        # Create a summarization prompt
        prompt = _create_summarization_prompt(user_query, columns, rows, sql)
        
        # Get the summary directly using synchronous methods
        if SUMMARY_ENGINE == "mistral":
            # Using a synchronous method for API access
            from app.llm_client import call_llm
            summary = call_llm(prompt, max_tokens=1000)
        else:
            # Default to local summarization
            summary = _fallback_summarization(user_query, columns, rows)
            
        return summary
    except Exception as e:
        logger.error(f"Sync wrapper for API summarization error: {e}")
        return _fallback_summarization(user_query, columns, rows)

def _create_default_response(user_query: str, columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> str:
    """Create a default response when API summarization fails."""
    try:
        if not rows:
            return "No data found matching your criteria."
        
        # Basic approach - find numeric columns and sum them
        metric_cols = _pick_metric_columns(columns, rows, user_query)
        label_cols = _pick_label_columns(columns, rows)
        
        summary_parts = [f"Found {len(rows)} records"]
        
        if metric_cols and label_cols:
            # Add totals for key metrics
            for col in metric_cols[:3]:  # Top 3 metrics
                try:
                    values = [float(r[col]) for r in rows if col in r and _is_num(r.get(col))]
                    if values:
                        total = sum(values)
                        if total > 0:
                            metric_name = col.replace('_', ' ').title()
                            summary_parts.append(f"{metric_name}: {_fmt_num(total)}")
                except (ValueError, TypeError):
                    pass
        
        # Check for floor-wise data
        floor_col = next((col for col in columns if 'floor' in col.lower()), None)
        if floor_col and len(rows) > 1:
            floor_count = len(set(r.get(floor_col) for r in rows if floor_col in r))
            if floor_count > 1:
                summary_parts.append(f"Across {floor_count} floors")
        
        return " • ".join(summary_parts)
        
    except Exception as e:
        logger.error(f"Default response creation error: {e}")
        return f"Found {len(rows)} records matching your query."

def _process_summarization_response(response: str) -> str:
    """Process the summarization response."""
    if not response:
        return "No summary available."
    return response.strip()

def _fallback_summarization(
    user_query: str,
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]]
) -> str:
    """
    Fallback to simpler summarization logic if API fails.
    """
    try:
        # Check if it's a TNA task query by looking for CTL code or task-related terms
        is_tna_query = bool(re.search(r'\bCTL-\d{2}-\d{5,6}\b', user_query) or 
                           re.search(r'\b(task|tna|pp approval|job no)\b', user_query.lower()))
        
        if is_tna_query and rows:
            # Generate TNA task summary
            return _generate_tna_task_summary(user_query, columns, rows)
            
        # For production-related queries, use the comprehensive report
        if ("production" in user_query.lower() or "floor" in user_query.lower() or 
            "summary" in user_query.lower() or "report" in user_query.lower()):
            return _generate_comprehensive_report(user_query, list(columns), list(rows))
        
        # For other queries, use the simplified logic
        if not rows:
            return "No data found matching your criteria."
        
        # Extract production context if possible
        try:
            context = extract_production_context(user_query, list(columns))
            intent = context['intent']
        except Exception:
            intent = 'general'
        
        # Basic approach - find numeric columns and sum them
        metric_cols = _pick_metric_columns(columns, rows, user_query)
        label_cols = _pick_label_columns(columns, rows)
        
        summary_parts = [f"Found {len(rows)} records"]
        
        if metric_cols and label_cols:
            # Add totals for key metrics
            for col in metric_cols[:3]:  # Top 3 metrics
                try:
                    values = [float(r[col]) for r in rows if col in r and _is_num(r.get(col))]
                    if values:
                        total = sum(values)
                        if total > 0:
                            metric_name = col.replace('_', ' ').title()
                            summary_parts.append(f"{metric_name}: {_fmt_num(total)}")
                except (ValueError, TypeError):
                    pass
        
        # Check for floor-wise data
        floor_col = next((col for col in columns if 'floor' in col.lower()), None)
        if floor_col and len(rows) > 1:
            floor_count = len(set(r.get(floor_col) for r in rows if floor_col in r))
            if floor_count > 1:
                summary_parts.append(f"Across {floor_count} floors")
        
        return " • ".join(summary_parts)
        
    except Exception as e:
        logger.error(f"Fallback summarization error: {e}")
        return f"Found {len(rows)} records matching your query."

def _generate_tna_task_summary(user_query: str, columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> str:
    """Generate a detailed summary for TNA task queries."""
    try:
        if not rows:
            return "No tasks found matching your criteria."
        
        # Extract CTL code if present in the query
        ctl_match = re.search(r'\b(CTL-\d{2}-\d{5,6})\b', user_query)
        ctl_code = ctl_match.group(1) if ctl_match else None
        
        # Extract date if present in the query
        date_match = re.search(r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}-[A-Z]{3}-\d{2,4}|[A-Z]{3}-\d{2,4})\b', user_query.upper())
        date_str = date_match.group(1) if date_match else None
        
        # Start building summary
        if ctl_code:
            summary = f"Task information for {ctl_code}"
            if date_str:
                summary += f" on {date_str}"
            summary += f":\n\n"
        else:
            summary = f"Found {len(rows)} task records"
            if date_str:
                summary += f" for {date_str}"
            summary += ".\n\n"
        
        # Check job numbers
        job_numbers = set()
        if 'JOB_NO' in columns:
            job_numbers = {r.get('JOB_NO') for r in rows if r.get('JOB_NO')}
            if len(job_numbers) == 1 and ctl_code is None:
                ctl_code = next(iter(job_numbers))
                summary = f"Task information for {ctl_code}"
                if date_str:
                    summary += f" on {date_str}"
                summary += ":\n\n"
        
        # Analyze task status
        completed_tasks = [r for r in rows if r.get('ACTUAL_FINISH_DATE') is not None]
        pending_tasks = [r for r in rows if r.get('ACTUAL_FINISH_DATE') is None]
        
        summary += f"• {len(completed_tasks)} completed tasks and {len(pending_tasks)} pending tasks\n"
        
        # Get style information
        if 'STYLE_REF_NO' in columns and 'STYLE_DESCRIPTION' in columns and rows[0].get('STYLE_REF_NO'):
            style_ref = rows[0].get('STYLE_REF_NO')
            style_desc = rows[0].get('STYLE_DESCRIPTION', '')
            summary += f"• Style: {style_ref} - {style_desc}\n"
        
        # Get buyer information
        if 'BUYER_NAME' in columns and rows[0].get('BUYER_NAME'):
            buyer = rows[0].get('BUYER_NAME')
            summary += f"• Buyer: {buyer}\n"
        
        # Add PO information if available
        if 'PO_NUMBER' in columns:
            po_numbers = {r.get('PO_NUMBER') for r in rows if r.get('PO_NUMBER')}
            if len(po_numbers) == 1:
                summary += f"• PO Number: {next(iter(po_numbers))}\n"
            elif len(po_numbers) > 1:
                summary += f"• Multiple PO Numbers: {', '.join(sorted(po_numbers)[:3])}"
                if len(po_numbers) > 3:
                    summary += f" and {len(po_numbers) - 3} more"
                summary += "\n"
        
        # List pending tasks
        if pending_tasks:
            summary += "\nPending tasks:\n"
            for i, task in enumerate(pending_tasks[:3], 1):
                task_name = task.get('TASK_SHORT_NAME', 'Unknown Task')
                task_date = task.get('TASK_FINISH_DATE')
                date_str = task_date.strftime('%d-%b-%Y') if hasattr(task_date, 'strftime') else str(task_date)
                summary += f"{i}. {task_name} (due: {date_str})\n"
            
            if len(pending_tasks) > 3:
                summary += f"... and {len(pending_tasks) - 3} more pending tasks\n"
        
        return summary
        
    except Exception as e:
        logger.error(f"TNA task summary generation error: {e}")
        return f"Found {len(rows)} task records for your query."
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
    """Enhanced summarizer with API-based natural language responses."""
    try:
        if not rows:
            return "No data found matching your criteria."
        
        # Use API-based summarization for natural language responses
        return _generate_api_summary(user_query, columns, rows, sql)
        
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