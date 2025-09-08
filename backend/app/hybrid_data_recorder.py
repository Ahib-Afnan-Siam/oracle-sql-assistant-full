# app/hybrid_data_recorder.py
"""
Enhanced data recording system for hybrid AI processing.
Integrates with existing feedback_store.py and extends it for hybrid system training data.
Collects comprehensive training data including query context, model responses, 
response metrics, selection decisions, performance metrics, user patterns, and API usage.

Phase 5 Training Data Collection System:

1. Data Collection Components:
   - Query Classification Context (AI_HYBRID_CONTEXT)
   - Model Responses (AI_MODEL_RESPONSES)
   - Response Quality Metrics (AI_RESPONSE_METRICS)
   - Selection Decisions (AI_SELECTION_DECISIONS)
   - Performance Metrics (AI_PERFORMANCE_METRICS)
   - User Interaction Patterns (AI_USER_PATTERNS)
   - API Usage Tracking (AI_API_USAGE_LOG)

2. Quality Metrics Analysis:
   - Success Rates (Query Understanding, SQL Execution)
   - User Satisfaction (Acceptance, Feedback, Engagement)
   - Business Logic Compliance
   - System Health Monitoring

3. API Endpoints:
   - /quality-metrics/dashboard - System health dashboard
   - /quality-metrics - Comprehensive metrics report
   - /quality-metrics/success-rates - Success rate metrics
   - /quality-metrics/user-satisfaction - User satisfaction metrics
   - /quality-metrics/test - System testing endpoint
   - /quality-metrics/status - System status endpoint
   - /training-data/test - Training data collection testing
   - /training-data/status - Training data collection status
   - /learning/performance-comparison - Performance comparison between models
   - /learning/model-strengths - Model strengths by domain
   - /learning/user-preferences - User preference patterns
   - /learning/insights - Comprehensive learning insights
   - /training-data/high-quality-samples - High-quality sample identification
   - /training-data/datasets/{type} - Training dataset creation by type

4. Training Data Structure:
   - Complete query processing context
   - Model responses from both local and API models
   - Detailed quality metrics for each response
   - Selection decision rationale
   - Performance timing data
   - User interaction patterns
   - API usage and cost tracking

5. Continuous Learning Capabilities:
   - Performance comparison analysis
   - Model strength identification
   - User preference pattern analysis
   - Learning insights generation
   - Quality reporting with alerts
   - High-quality sample identification
   - Training dataset creation

Phase 6: Continuous Learning Loop (Day 15+)

The continuous learning loop enables the system to automatically improve by analyzing patterns in:
1. Performance Comparison: Local vs API accuracy by query type, response time analysis, user preference patterns
2. Model Strength Identification: DeepSeek strengths (production, TNA, Oracle), Llama strengths (HR, business logic), local model improvement areas
3. Training Data Preparation: High-quality sample identification and training dataset creation

Key Features:
- Automated pattern analysis across query types and model responses
- Performance benchmarking between local and API models
- Domain-specific model strength identification
- User preference tracking and analysis
- Actionable insights generation for system optimization
- API endpoints for accessing learning insights
- High-quality sample identification for model fine-tuning
- Training dataset creation for different domains

Learning Insights Process:
1. Data Collection: Comprehensive training data is collected for every query processed
2. Pattern Analysis: System analyzes performance patterns across different query types and models
3. Model Comparison: Local vs API models are compared on quality, speed, and user satisfaction
4. Strength Identification: Each model's strengths in different domains are identified
5. Recommendation Generation: Actionable recommendations are generated for system improvements
6. Continuous Improvement: Insights are used to optimize model selection and routing strategies
7. Training Data Preparation: High-quality samples are identified and organized into domain-specific datasets

API Endpoints for Continuous Learning:
- GET /learning/performance-comparison: Compare local vs API model performance by query type
- GET /learning/model-strengths: Identify model strengths by domain/query type
- GET /learning/user-preferences: Analyze user preference patterns for different models
- GET /learning/insights: Get comprehensive learning insights from pattern analysis
- GET /training-data/high-quality-samples: Identify high-quality samples for training
- GET /training-data/datasets/{type}: Create training datasets for specific domains

The continuous learning system provides valuable insights that can be used to:
- Optimize model selection strategies
- Improve response quality over time
- Reduce processing costs
- Enhance user satisfaction
- Identify areas for model fine-tuning
- Prepare high-quality training datasets for model improvement
"""
import json
import logging
import time
from typing import Dict, Any, Optional, List, Union
from datetime import datetime as _dt, timezone, timedelta
import traceback

from .feedback_store import _json_dumps, _insert_with_returning
from .db_connector import connect_feedback
from .hybrid_processor import ProcessingResult, ResponseMetrics
from .query_classifier import QueryClassification

logger = logging.getLogger(__name__)

class QualityMetricsAnalyzer:
    """
    Step 5.2: Quality Metrics System
    Analyzes success rates, user satisfaction, and business logic compliance.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def calculate_success_rates(self, time_window_hours: int = 24) -> Dict[str, float]:
        """
        Calculate query understanding accuracy and SQL execution success rates.
        
        Args:
            time_window_hours: Time window for analysis (default: last 24 hours)
            
        Returns:
            Dictionary with success rate metrics
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                
                # Calculate time window
                window_start = _dt.now(timezone.utc) - timedelta(hours=time_window_hours)
                
                # Query understanding accuracy
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_queries,
                        SUM(CASE WHEN hc.QUERY_CONFIDENCE >= 0.7 THEN 1 ELSE 0 END) as high_confidence_queries,
                        AVG(hc.QUERY_CONFIDENCE) as avg_confidence,
                        COUNT(DISTINCT hc.QUERY_INTENT) as intent_variety
                    FROM AI_HYBRID_CONTEXT hc
                    JOIN AI_TURN t ON hc.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                """, {"window_start": window_start})
                
                understanding_stats = cur.fetchone()
                
                # SQL execution success rates
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_executions,
                        SUM(CASE WHEN rm.EXECUTION_SUCCESS = 'Y' THEN 1 ELSE 0 END) as successful_executions,
                        AVG(rm.EXECUTION_TIME_MS) as avg_execution_time,
                        AVG(rm.RESULT_ROW_COUNT) as avg_row_count
                    FROM AI_RESPONSE_METRICS rm
                    JOIN AI_MODEL_RESPONSES mr ON rm.MODEL_RESPONSE_ID = mr.ID
                    JOIN AI_TURN t ON mr.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                """, {"window_start": window_start})
                
                execution_stats = cur.fetchone()
                
                # Business logic compliance
                cur.execute("""
                    SELECT 
                        AVG(rm.BUSINESS_LOGIC_SCORE) as avg_business_score,
                        AVG(rm.SCHEMA_COMPLIANCE_SCORE) as avg_schema_compliance,
                        AVG(rm.OVERALL_SCORE) as avg_overall_score,
                        COUNT(CASE WHEN rm.SECURITY_RISK_DETECTED = 'Y' THEN 1 END) as security_issues
                    FROM AI_RESPONSE_METRICS rm
                    JOIN AI_MODEL_RESPONSES mr ON rm.MODEL_RESPONSE_ID = mr.ID
                    JOIN AI_TURN t ON mr.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                """, {"window_start": window_start})
                
                compliance_stats = cur.fetchone()
                
                # Calculate success rates
                total_queries = understanding_stats[0] if understanding_stats[0] else 1
                total_executions = execution_stats[0] if execution_stats[0] else 1
                
                return {
                    "query_understanding_accuracy": (understanding_stats[1] / total_queries) if total_queries > 0 else 0.0,
                    "sql_execution_success_rate": (execution_stats[1] / total_executions) if total_executions > 0 else 0.0,
                    "business_logic_compliance": compliance_stats[0] if compliance_stats[0] else 0.0,
                    "schema_compliance_rate": compliance_stats[1] if compliance_stats[1] else 0.0,
                    "overall_quality_score": compliance_stats[2] if compliance_stats[2] else 0.0,
                    "avg_confidence_score": understanding_stats[2] if understanding_stats[2] else 0.0,
                    "avg_execution_time_ms": execution_stats[2] if execution_stats[2] else 0.0,
                    "avg_result_row_count": execution_stats[3] if execution_stats[3] else 0.0,
                    "security_issues_count": compliance_stats[3] if compliance_stats[3] else 0,
                    "intent_variety_score": understanding_stats[3] if understanding_stats[3] else 0,
                    "total_queries_analyzed": total_queries,
                    "time_window_hours": time_window_hours
                }
                
        except Exception as e:
            self.logger.error(f"Failed to calculate success rates: {e}")
            return {}
    
    def analyze_user_satisfaction(self, time_window_hours: int = 24) -> Dict[str, float]:
        """
        Analyze user satisfaction indicators including acceptance, retry rates, and feedback.
        
        Args:
            time_window_hours: Time window for analysis
            
        Returns:
            Dictionary with user satisfaction metrics
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                
                window_start = _dt.now(timezone.utc) - timedelta(hours=time_window_hours)
                
                # Response acceptance rate (based on user actions)
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_interactions,
                        AVG(CASE WHEN USER_SATISFACTION IS NOT NULL THEN USER_SATISFACTION ELSE 3 END) as avg_satisfaction,
                        SUM(RETRY_COUNT) as total_retries,
                        SUM(COPY_COUNT) as total_copies,
                        AVG(TIME_SPENT_VIEWING_MS) as avg_viewing_time
                    FROM AI_USER_PATTERNS up
                    WHERE up.INTERACTION_AT >= :window_start
                """, {"window_start": window_start})
                interaction_stats = cur.fetchone()
                
                # Explicit feedback scores
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_feedback,
                        COUNT(CASE WHEN FEEDBACK_TYPE = 'good' THEN 1 END) as positive_feedback,
                        COUNT(CASE WHEN FEEDBACK_TYPE = 'wrong' THEN 1 END) as negative_feedback,
                        COUNT(CASE WHEN FEEDBACK_TYPE = 'needs_improvement' THEN 1 END) as improvement_feedback
                    FROM AI_FEEDBACK f
                    JOIN AI_TURN t ON f.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                """, {"window_start": window_start})
                
                feedback_stats = cur.fetchone()
                
                # Processing efficiency and user satisfaction prediction
                cur.execute("""
                    SELECT 
                        AVG(rm.OVERALL_SCORE) as predicted_satisfaction,
                        COUNT(CASE WHEN mr.STATUS = 'success' THEN 1 END) as successful_responses,
                        COUNT(*) as total_responses,
                        AVG(mr.RESPONSE_TIME_MS) as avg_response_time
                    FROM AI_RESPONSE_METRICS rm
                    JOIN AI_MODEL_RESPONSES mr ON rm.MODEL_RESPONSE_ID = mr.ID
                    JOIN AI_TURN t ON mr.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                """, {"window_start": window_start})
                efficiency_stats = cur.fetchone()
                
                # Calculate satisfaction metrics
                total_interactions = interaction_stats[0] if interaction_stats[0] else 1
                total_feedback = feedback_stats[0] if feedback_stats[0] else 1
                total_responses = efficiency_stats[3] if efficiency_stats[3] else 1
                
                return {
                    "response_acceptance_rate": (efficiency_stats[1] / total_responses) if total_responses > 0 else 0.0,
                    "retry_frequency": (interaction_stats[2] / total_interactions) if total_interactions > 0 else 0.0,
                    "copy_action_rate": (interaction_stats[3] / total_interactions) if total_interactions > 0 else 0.0,
                    "positive_feedback_rate": (feedback_stats[1] / total_feedback) if total_feedback > 0 else 0.0,
                    "negative_feedback_rate": (feedback_stats[2] / total_feedback) if total_feedback > 0 else 0.0,
                    "avg_explicit_satisfaction": interaction_stats[1] if interaction_stats[1] else 3.0,
                    "predicted_satisfaction_score": efficiency_stats[0] if efficiency_stats[0] else 0.0,
                    "avg_viewing_time_ms": interaction_stats[4] if interaction_stats[4] else 0.0,
                    "avg_response_time_ms": efficiency_stats[3] if efficiency_stats[3] else 0.0,
                    "total_feedback_received": total_feedback,
                    "engagement_score": min((interaction_stats[4] / 10000.0) if interaction_stats[4] else 0.0, 1.0),  # Normalize viewing time
                    "time_window_hours": time_window_hours
                }
                
        except Exception as e:
            self.logger.error(f"Failed to analyze user satisfaction: {e}")
            return {}
    
    def generate_quality_report(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Generate comprehensive quality metrics report.
        
        Args:
            time_window_hours: Time window for analysis
            
        Returns:
            Complete quality metrics report
        """
        success_metrics = self.calculate_success_rates(time_window_hours)
        satisfaction_metrics = self.analyze_user_satisfaction(time_window_hours)
        
        # Calculate composite scores
        overall_quality = (
            success_metrics.get("overall_quality_score", 0.0) * 0.4 +
            satisfaction_metrics.get("predicted_satisfaction_score", 0.0) * 0.3 +
            success_metrics.get("sql_execution_success_rate", 0.0) * 0.3
        )
        
        system_health = "excellent" if overall_quality >= 0.8 else "good" if overall_quality >= 0.6 else "needs_attention"
        
        return {
            "report_timestamp": _dt.now(timezone.utc).isoformat(),
            "time_window_hours": time_window_hours,
            "success_metrics": success_metrics,
            "satisfaction_metrics": satisfaction_metrics,
            "composite_scores": {
                "overall_quality_score": overall_quality,
                "system_health_status": system_health,
                "recommendation": self._generate_recommendation(success_metrics, satisfaction_metrics)
            },
            "alerts": self._generate_alerts(success_metrics, satisfaction_metrics)
        }
    
    def _generate_recommendation(self, success_metrics: Dict, satisfaction_metrics: Dict) -> str:
        """Generate actionable recommendations based on metrics."""
        recommendations = []
        
        if success_metrics.get("sql_execution_success_rate", 0) < 0.8:
            recommendations.append("Improve SQL validation and error handling")
        
        if satisfaction_metrics.get("retry_frequency", 0) > 0.3:
            recommendations.append("Enhance query understanding and response relevance")
        
        if success_metrics.get("business_logic_compliance", 0) < 0.7:
            recommendations.append("Strengthen business domain knowledge integration")
        
        if satisfaction_metrics.get("positive_feedback_rate", 0) < 0.6:
            recommendations.append("Focus on user experience improvements")
        
        if not recommendations:
            recommendations.append("System performing well, continue monitoring")
        
        return "; ".join(recommendations)

    def _generate_alerts(self, success_metrics: Dict, satisfaction_metrics: Dict) -> List[str]:
        """Generate alerts for critical issues."""
        alerts = []
        
        if success_metrics.get("sql_execution_success_rate", 0) < 0.5:
            alerts.append("CRITICAL: SQL execution success rate below 50%")
        
        if satisfaction_metrics.get("negative_feedback_rate", 0) > 0.4:
            alerts.append("WARNING: High negative feedback rate detected")
        
        if success_metrics.get("security_issues_count", 0) > 0:
            alerts.append(f"SECURITY: {success_metrics['security_issues_count']} security issues detected")
        
        if satisfaction_metrics.get("retry_frequency", 0) > 0.5:
            alerts.append("WARNING: High retry frequency indicates poor initial response quality")
        
        return alerts

    # ------------------------------ Phase 6: Continuous Learning Loop ------------------------------
    
    def analyze_performance_comparison(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Phase 6.1: Performance comparison between local and API models by query type.
        
        Args:
            time_window_hours: Time window for analysis
            
        Returns:
            Performance comparison metrics by query type
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                
                window_start = _dt.now(timezone.utc) - timedelta(hours=time_window_hours)
                
                # Get performance comparison by query intent
                cur.execute("""
                    SELECT 
                        hc.QUERY_INTENT,
                        mr.MODEL_TYPE,
                        COUNT(*) as response_count,
                        AVG(rm.OVERALL_SCORE) as avg_quality_score,
                        AVG(mr.RESPONSE_TIME_MS) as avg_response_time_ms,
                        AVG(CASE WHEN rm.EXECUTION_SUCCESS = 'Y' THEN 1 ELSE 0 END) as execution_success_rate,
                        AVG(CASE WHEN sd.SELECTED_RESPONSE_ID = mr.ID THEN 1 ELSE 0 END) as selection_rate
                    FROM AI_HYBRID_CONTEXT hc
                    JOIN AI_MODEL_RESPONSES mr ON hc.TURN_ID = mr.TURN_ID
                    JOIN AI_RESPONSE_METRICS rm ON mr.ID = rm.MODEL_RESPONSE_ID
                    LEFT JOIN AI_SELECTION_DECISIONS sd ON hc.TURN_ID = sd.TURN_ID
                    JOIN AI_TURN t ON hc.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                    GROUP BY hc.QUERY_INTENT, mr.MODEL_TYPE
                    ORDER BY hc.QUERY_INTENT, mr.MODEL_TYPE
                """, {"window_start": window_start})
                
                performance_data = cur.fetchall()
                
                # Organize results by query intent
                performance_comparison = {}
                for row in performance_data:
                    intent, model_type, count, quality_score, response_time, success_rate, selection_rate = row
                    
                    if intent not in performance_comparison:
                        performance_comparison[intent] = {}
                    
                    performance_comparison[intent][model_type] = {
                        "response_count": count,
                        "avg_quality_score": round(quality_score, 3) if quality_score else 0.0,
                        "avg_response_time_ms": round(response_time, 1) if response_time else 0.0,
                        "execution_success_rate": round(success_rate, 3) if success_rate else 0.0,
                        "selection_rate": round(selection_rate, 3) if selection_rate else 0.0
                    }
                
                # Calculate performance differences
                performance_insights = {}
                for intent, models in performance_comparison.items():
                    local = models.get("local", {})
                    api = models.get("api", {})
                    
                    performance_insights[intent] = {
                        "quality_difference": round(
                            api.get("avg_quality_score", 0.0) - local.get("avg_quality_score", 0.0), 3
                        ),
                        "time_difference": round(
                            api.get("avg_response_time_ms", 0.0) - local.get("avg_response_time_ms", 0.0), 1
                        ),
                        "success_rate_difference": round(
                            api.get("execution_success_rate", 0.0) - local.get("execution_success_rate", 0.0), 3
                        ),
                        "preference": "api" if api.get("selection_rate", 0.0) > local.get("selection_rate", 0.0) else "local"
                    }
                
                return {
                    "performance_by_intent": performance_comparison,
                    "performance_insights": performance_insights,
                    "time_window_hours": time_window_hours,
                    "total_query_intents": len(performance_comparison)
                }
                
        except Exception as e:
            self.logger.error(f"Failed to analyze performance comparison: {e}")
            return {}

    def identify_model_strengths(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Phase 6.1: Identify model strengths by domain/query type.
        
        Args:
            time_window_hours: Time window for analysis
            
        Returns:
            Model strengths by domain/query type
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                
                window_start = _dt.now(timezone.utc) - timedelta(hours=time_window_hours)
                
                # Get model performance by query intent and model name
                cur.execute("""
                    SELECT 
                        hc.QUERY_INTENT,
                        mr.MODEL_NAME,
                        mr.MODEL_TYPE,
                        COUNT(*) as response_count,
                        AVG(rm.OVERALL_SCORE) as avg_quality_score,
                        AVG(mr.RESPONSE_TIME_MS) as avg_response_time_ms,
                        AVG(CASE WHEN rm.EXECUTION_SUCCESS = 'Y' THEN 1 ELSE 0 END) as execution_success_rate,
                        AVG(CASE WHEN sd.SELECTED_RESPONSE_ID = mr.ID THEN 1 ELSE 0 END) as selection_rate
                    FROM AI_HYBRID_CONTEXT hc
                    JOIN AI_MODEL_RESPONSES mr ON hc.TURN_ID = mr.TURN_ID
                    JOIN AI_RESPONSE_METRICS rm ON mr.ID = rm.MODEL_RESPONSE_ID
                    LEFT JOIN AI_SELECTION_DECISIONS sd ON hc.TURN_ID = sd.TURN_ID
                    JOIN AI_TURN t ON hc.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                    GROUP BY hc.QUERY_INTENT, mr.MODEL_NAME, mr.MODEL_TYPE
                    ORDER BY hc.QUERY_INTENT, mr.MODEL_TYPE, avg_quality_score DESC
                """, {"window_start": window_start})
                
                strength_data = cur.fetchall()
                
                # Organize results by query intent
                model_strengths = {}
                model_performance = {}
                
                for row in strength_data:
                    intent, model_name, model_type, count, quality_score, response_time, success_rate, selection_rate = row
                    
                    if intent not in model_strengths:
                        model_strengths[intent] = []
                        model_performance[intent] = {}
                    
                    model_info = {
                        "model_name": model_name,
                        "model_type": model_type,
                        "response_count": count,
                        "avg_quality_score": round(quality_score, 3) if quality_score else 0.0,
                        "avg_response_time_ms": round(response_time, 1) if response_time else 0.0,
                        "execution_success_rate": round(success_rate, 3) if success_rate else 0.0,
                        "selection_rate": round(selection_rate, 3) if selection_rate else 0.0
                    }
                    
                    model_strengths[intent].append(model_info)
                    model_performance[intent][model_name] = model_info
                
                # Identify top models by intent
                top_models = {}
                for intent, models in model_performance.items():
                    if models:
                        # Sort by quality score and selection rate
                        sorted_models = sorted(
                            models.items(), 
                            key=lambda x: (x[1]["avg_quality_score"], x[1]["selection_rate"]), 
                            reverse=True
                        )
                        top_models[intent] = sorted_models[0][0] if sorted_models else "unknown"
                
                # Domain-specific strength identification
                domain_strengths = {
                    "production": {
                        "best_model": top_models.get("production_query", "deepseek"),
                        "strengths": ["complex production queries", "CTL code handling", "efficiency metrics"]
                    },
                    "tna": {
                        "best_model": top_models.get("tna_task_query", "deepseek"),
                        "strengths": ["task tracking", "CTL code processing", "status analysis"]
                    },
                    "hr": {
                        "best_model": top_models.get("hr_employee_query", "llama"),
                        "strengths": ["employee data", "department analysis", "job role queries"]
                    },
                    "analytics": {
                        "best_model": top_models.get("complex_analytics", "deepseek"),
                        "strengths": ["trend analysis", "time-series data", "multi-field queries"]
                    },
                    "general": {
                        "best_model": top_models.get("general_query", "deepseek"),
                        "strengths": ["broad knowledge", "simple lookups", "general SQL generation"]
                    }
                }
                
                return {
                    "model_strengths_by_intent": model_strengths,
                    "top_models_by_intent": top_models,
                    "domain_strengths": domain_strengths,
                    "time_window_hours": time_window_hours
                }
                
        except Exception as e:
            self.logger.error(f"Failed to identify model strengths: {e}")
            return {}

    def analyze_user_preference_patterns(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Phase 6.1: Analyze user preference patterns for different models.
        
        Args:
            time_window_hours: Time window for analysis
            
        Returns:
            User preference patterns analysis
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                
                window_start = _dt.now(timezone.utc) - timedelta(hours=time_window_hours)
                
                # Get user preference patterns
                cur.execute("""
                    SELECT 
                        hc.QUERY_INTENT,
                        mr.MODEL_TYPE,
                        COUNT(*) as total_responses,
                        SUM(CASE WHEN sd.SELECTED_RESPONSE_ID = mr.ID THEN 1 ELSE 0 END) as selected_count,
                        AVG(up.USER_SATISFACTION) as avg_user_satisfaction,
                        AVG(up.RETRY_COUNT) as avg_retry_count,
                        AVG(up.TIME_SPENT_VIEWING_MS) as avg_viewing_time_ms
                    FROM AI_HYBRID_CONTEXT hc
                    JOIN AI_MODEL_RESPONSES mr ON hc.TURN_ID = mr.TURN_ID
                    LEFT JOIN AI_SELECTION_DECISIONS sd ON hc.TURN_ID = sd.TURN_ID
                    LEFT JOIN AI_USER_PATTERNS up ON hc.TURN_ID = up.TURN_ID
                    JOIN AI_TURN t ON hc.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                    GROUP BY hc.QUERY_INTENT, mr.MODEL_TYPE
                    ORDER BY hc.QUERY_INTENT, mr.MODEL_TYPE
                """, {"window_start": window_start})
                
                preference_data = cur.fetchall()
                
                # Organize results
                preference_patterns = {}
                for row in preference_data:
                    intent, model_type, total_responses, selected_count, satisfaction, retry_count, viewing_time = row
                    
                    if intent not in preference_patterns:
                        preference_patterns[intent] = {}
                    
                    selection_rate = selected_count / total_responses if total_responses > 0 else 0.0
                    
                    preference_patterns[intent][model_type] = {
                        "total_responses": total_responses,
                        "selected_count": selected_count,
                        "selection_rate": round(selection_rate, 3),
                        "avg_user_satisfaction": round(satisfaction, 2) if satisfaction else 0.0,
                        "avg_retry_count": round(retry_count, 1) if retry_count else 0.0,
                        "avg_viewing_time_ms": round(viewing_time, 1) if viewing_time else 0.0
                    }
                
                # Identify overall preferences
                overall_preferences = {}
                for intent, models in preference_patterns.items():
                    if models:
                        # Model with highest selection rate is preferred
                        preferred_model = max(models.items(), key=lambda x: x[1]["selection_rate"])
                        overall_preferences[intent] = {
                            "preferred_model": preferred_model[0],
                            "selection_rate": preferred_model[1]["selection_rate"],
                            "user_satisfaction": preferred_model[1]["avg_user_satisfaction"]
                        }
                
                return {
                    "preference_patterns": preference_patterns,
                    "overall_preferences": overall_preferences,
                    "time_window_hours": time_window_hours
                }
                
        except Exception as e:
            self.logger.error(f"Failed to analyze user preference patterns: {e}")
            return {}

    def generate_learning_insights(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Phase 6.1: Generate comprehensive learning insights from pattern analysis.
        
        Args:
            time_window_hours: Time window for analysis
            
        Returns:
            Comprehensive learning insights
        """
        performance_comparison = self.analyze_performance_comparison(time_window_hours)
        model_strengths = self.identify_model_strengths(time_window_hours)
        preference_patterns = self.analyze_user_preference_patterns(time_window_hours)
        
        # Combine insights
        insights = {
            "timestamp": _dt.now(timezone.utc).isoformat(),
            "time_window_hours": time_window_hours,
            "performance_comparison": performance_comparison,
            "model_strengths": model_strengths,
            "preference_patterns": preference_patterns
        }
        
        # Generate actionable recommendations
        recommendations = []
        
        # Performance-based recommendations
        performance_insights = performance_comparison.get("performance_insights", {})
        for intent, metrics in performance_insights.items():
            if metrics["quality_difference"] > 0.1:
                recommendations.append(f"For {intent}: API model shows significantly better quality (+{metrics['quality_difference']})")
            elif metrics["quality_difference"] < -0.1:
                recommendations.append(f"For {intent}: Local model shows significantly better quality ({metrics['quality_difference']})")
            
            if metrics["time_difference"] > 1000:  # 1 second
                recommendations.append(f"For {intent}: Local model is significantly faster by {abs(metrics['time_difference'])}ms")
        
        # Model strength recommendations
        domain_strengths = model_strengths.get("domain_strengths", {})
        for domain, info in domain_strengths.items():
            recommendations.append(f"For {domain} queries: Use {info['best_model']} for optimal results")
        
        # Preference-based recommendations
        overall_preferences = preference_patterns.get("overall_preferences", {})
        for intent, pref in overall_preferences.items():
            if pref["selection_rate"] > 0.7 and pref["user_satisfaction"] < 3.0:
                recommendations.append(f"For {intent}: High selection rate but low satisfaction - investigate quality issues")
        
        insights["recommendations"] = recommendations
        return insights

    def identify_high_quality_samples(self, time_window_hours: int = 168, min_quality_score: float = 0.8) -> Dict[str, Any]:
        """
        Step 6.2: Identify high-quality samples for training data preparation.
        
        Args:
            time_window_hours: Time window for analysis (default: 168 hours/1 week)
            min_quality_score: Minimum quality score threshold for high-quality samples
            
        Returns:
            Dictionary with high-quality samples categorized by type
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                
                window_start = _dt.now(timezone.utc) - timedelta(hours=time_window_hours)
                
                # 1. API responses that outperformed local models
                cur.execute("""
                    SELECT 
                        hc.TURN_ID,
                        hc.QUERY_INTENT,
                        hc.ENTITIES_JSON,
                        mr_api.MODEL_NAME as API_MODEL,
                        mr_local.MODEL_NAME as LOCAL_MODEL,
                        mr_api.RESPONSE_TEXT as API_RESPONSE,
                        mr_local.RESPONSE_TEXT as LOCAL_RESPONSE,
                        rm_api.OVERALL_SCORE as API_SCORE,
                        rm_local.OVERALL_SCORE as LOCAL_SCORE,
                        sd.SELECTION_REASONING,
                        t.USER_QUESTION
                    FROM AI_HYBRID_CONTEXT hc
                    JOIN AI_MODEL_RESPONSES mr_api ON hc.TURN_ID = mr_api.TURN_ID AND mr_api.MODEL_TYPE = 'api'
                    JOIN AI_MODEL_RESPONSES mr_local ON hc.TURN_ID = mr_local.TURN_ID AND mr_local.MODEL_TYPE = 'local'
                    JOIN AI_RESPONSE_METRICS rm_api ON mr_api.ID = rm_api.MODEL_RESPONSE_ID
                    JOIN AI_RESPONSE_METRICS rm_local ON mr_local.ID = rm_local.MODEL_RESPONSE_ID
                    JOIN AI_SELECTION_DECISIONS sd ON hc.TURN_ID = sd.TURN_ID
                    JOIN AI_TURN t ON hc.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                    AND rm_api.OVERALL_SCORE > rm_local.OVERALL_SCORE + 0.1
                    AND rm_api.OVERALL_SCORE >= :min_score
                    ORDER BY (rm_api.OVERALL_SCORE - rm_local.OVERALL_SCORE) DESC
                """, {"window_start": window_start, "min_score": min_quality_score})
                
                api_better_samples = cur.fetchall()
                
                # 2. Successful query-response pairs
                cur.execute("""
                    SELECT 
                        hc.TURN_ID,
                        hc.QUERY_INTENT,
                        hc.ENTITIES_JSON,
                        mr.MODEL_TYPE,
                        mr.MODEL_NAME,
                        mr.RESPONSE_TEXT,
                        rm.OVERALL_SCORE,
                        rm.SQL_VALIDITY_SCORE,
                        rm.SCHEMA_COMPLIANCE_SCORE,
                        rm.BUSINESS_LOGIC_SCORE,
                        rm.PERFORMANCE_SCORE,
                        rm.EXECUTION_SUCCESS,
                        rm.RESULT_ROW_COUNT,
                        t.USER_QUESTION
                    FROM AI_HYBRID_CONTEXT hc
                    JOIN AI_MODEL_RESPONSES mr ON hc.TURN_ID = mr.TURN_ID
                    JOIN AI_RESPONSE_METRICS rm ON mr.ID = rm.MODEL_RESPONSE_ID
                    JOIN AI_TURN t ON hc.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                    AND rm.OVERALL_SCORE >= :min_score
                    AND rm.EXECUTION_SUCCESS = 'Y'
                    AND rm.RESULT_ROW_COUNT > 0
                    ORDER BY rm.OVERALL_SCORE DESC
                """, {"window_start": window_start, "min_score": min_quality_score})
                
                successful_samples = cur.fetchall()
                
                # 3. Domain-specific improvements needed (samples with low scores in specific domains)
                cur.execute("""
                    SELECT 
                        hc.TURN_ID,
                        hc.QUERY_INTENT,
                        hc.ENTITIES_JSON,
                        mr.MODEL_TYPE,
                        mr.MODEL_NAME,
                        mr.RESPONSE_TEXT,
                        rm.OVERALL_SCORE,
                        rm.BUSINESS_LOGIC_SCORE,
                        rm.SCHEMA_COMPLIANCE_SCORE,
                        t.USER_QUESTION,
                        rm.VALIDATION_REASONING
                    FROM AI_HYBRID_CONTEXT hc
                    JOIN AI_MODEL_RESPONSES mr ON hc.TURN_ID = mr.TURN_ID
                    JOIN AI_RESPONSE_METRICS rm ON mr.ID = rm.MODEL_RESPONSE_ID
                    JOIN AI_TURN t ON hc.TURN_ID = t.ID
                    WHERE t.CREATED_AT >= :window_start
                    AND hc.QUERY_INTENT IN ('production_query', 'tna_task_query', 'hr_employee_query')
                    AND rm.OVERALL_SCORE < 0.5
                    ORDER BY hc.QUERY_INTENT, rm.OVERALL_SCORE ASC
                """, {"window_start": window_start})
                
                domain_improvement_samples = cur.fetchall()
                
                # Process results
                high_quality_data = {
                    "api_outperformed_local": [],
                    "successful_pairs": [],
                    "domain_improvements_needed": []
                }
                
                # Process API better samples
                for row in api_better_samples:
                    turn_id, intent, entities_json, api_model, local_model, api_resp, local_resp, api_score, local_score, reasoning, user_question = row
                    try:
                        entities = json.loads(entities_json) if entities_json else {}
                    except:
                        entities = {}
                    
                    high_quality_data["api_outperformed_local"].append({
                        "turn_id": turn_id,
                        "query_intent": intent,
                        "entities": entities,
                        "api_model": api_model,
                        "local_model": local_model,
                        "api_response": api_resp,
                        "local_response": local_resp,
                        "api_score": round(api_score, 3),
                        "local_score": round(local_score, 3),
                        "improvement": round(api_score - local_score, 3),
                        "selection_reasoning": reasoning,
                        "user_question": user_question
                    })
                
                # Process successful samples
                for row in successful_samples:
                    turn_id, intent, entities_json, model_type, model_name, response, overall_score, sql_score, schema_score, business_score, perf_score, exec_success, row_count, user_question = row
                    try:
                        entities = json.loads(entities_json) if entities_json else {}
                    except:
                        entities = {}
                    
                    high_quality_data["successful_pairs"].append({
                        "turn_id": turn_id,
                        "query_intent": intent,
                        "entities": entities,
                        "model_type": model_type,
                        "model_name": model_name,
                        "response": response,
                        "overall_score": round(overall_score, 3),
                        "sql_validity_score": round(sql_score, 3),
                        "schema_compliance_score": round(schema_score, 3),
                        "business_logic_score": round(business_score, 3),
                        "performance_score": round(perf_score, 3),
                        "execution_success": exec_success,
                        "result_row_count": row_count,
                        "user_question": user_question
                    })
                
                # Process domain improvement samples
                for row in domain_improvement_samples:
                    turn_id, intent, entities_json, model_type, model_name, response, overall_score, business_score, schema_score, user_question, reasoning = row
                    try:
                        entities = json.loads(entities_json) if entities_json else {}
                    except:
                        entities = {}
                    
                    high_quality_data["domain_improvements_needed"].append({
                        "turn_id": turn_id,
                        "query_intent": intent,
                        "entities": entities,
                        "model_type": model_type,
                        "model_name": model_name,
                        "response": response,
                        "overall_score": round(overall_score, 3),
                        "business_logic_score": round(business_score, 3),
                        "schema_compliance_score": round(schema_score, 3),
                        "user_question": user_question,
                        "validation_reasoning": reasoning
                    })
                
                return {
                    "timestamp": _dt.now(timezone.utc).isoformat(),
                    "time_window_hours": time_window_hours,
                    "min_quality_score": min_quality_score,
                    "sample_counts": {
                        "api_outperformed_local": len(high_quality_data["api_outperformed_local"]),
                        "successful_pairs": len(high_quality_data["successful_pairs"]),
                        "domain_improvements_needed": len(high_quality_data["domain_improvements_needed"])
                    },
                    "high_quality_samples": high_quality_data
                }
                
        except Exception as e:
            self.logger.error(f"Failed to identify high-quality samples: {e}")
            return {}

    def create_training_dataset(self, dataset_type: str = "manufacturing", time_window_hours: int = 720) -> Dict[str, Any]:
        """
        Step 6.2: Create training datasets for different domains.
        
        Args:
            dataset_type: Type of dataset to create ('manufacturing', 'oracle_sql', 'business_logic')
            time_window_hours: Time window for analysis (default: 720 hours/30 days)
            
        Returns:
            Dictionary with training dataset information
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                
                window_start = _dt.now(timezone.utc) - timedelta(hours=time_window_hours)
                
                if dataset_type == "manufacturing":
                    # Manufacturing query patterns dataset
                    cur.execute("""
                        SELECT 
                            t.USER_QUESTION,
                            hc.QUERY_INTENT,
                            hc.ENTITIES_JSON,
                            mr.MODEL_NAME,
                            mr.RESPONSE_TEXT,
                            rm.OVERALL_SCORE,
                            rm.BUSINESS_LOGIC_SCORE,
                            sd.SELECTION_REASONING,
                            hc.BUSINESS_CONTEXT
                        FROM AI_HYBRID_CONTEXT hc
                        JOIN AI_MODEL_RESPONSES mr ON hc.TURN_ID = mr.TURN_ID
                        JOIN AI_RESPONSE_METRICS rm ON mr.ID = rm.MODEL_RESPONSE_ID
                        JOIN AI_SELECTION_DECISIONS sd ON hc.TURN_ID = sd.TURN_ID
                        JOIN AI_TURN t ON hc.TURN_ID = t.ID
                        WHERE t.CREATED_AT >= :window_start
                        AND hc.QUERY_INTENT IN ('production_query', 'tna_task_query')
                        AND rm.OVERALL_SCORE >= 0.7
                        AND rm.BUSINESS_LOGIC_SCORE >= 0.6
                        ORDER BY rm.OVERALL_SCORE DESC
                    """, {"window_start": window_start})
                    
                    manufacturing_data = cur.fetchall()
                    training_samples = []
                    
                    for row in manufacturing_data:
                        user_question, intent, entities_json, model_name, response, overall_score, business_score, reasoning, context = row
                        try:
                            entities = json.loads(entities_json) if entities_json else {}
                        except:
                            entities = {}
                        
                        training_samples.append({
                            "input": user_question,
                            "intent": intent,
                            "entities": entities,
                            "model_used": model_name,
                            "output": response,
                            "overall_score": round(overall_score, 3),
                            "business_score": round(business_score, 3),
                            "reasoning": reasoning,
                            "business_context": context
                        })
                    
                    return {
                        "dataset_type": "manufacturing",
                        "description": "Manufacturing query patterns dataset",
                        "sample_count": len(training_samples),
                        "samples": training_samples,
                        "creation_timestamp": _dt.now(timezone.utc).isoformat(),
                        "time_window_hours": time_window_hours
                    }
                
                elif dataset_type == "oracle_sql":
                    # Oracle SQL best practices dataset
                    cur.execute("""
                        SELECT 
                            t.USER_QUESTION,
                            hc.QUERY_INTENT,
                            mr.RESPONSE_TEXT,
                            rm.OVERALL_SCORE,
                            rm.SQL_VALIDITY_SCORE,
                            rm.PERFORMANCE_SCORE,
                            rm.SCHEMA_COMPLIANCE_SCORE
                        FROM AI_HYBRID_CONTEXT hc
                        JOIN AI_MODEL_RESPONSES mr ON hc.TURN_ID = mr.TURN_ID
                        JOIN AI_RESPONSE_METRICS rm ON mr.ID = rm.MODEL_RESPONSE_ID
                        JOIN AI_TURN t ON hc.TURN_ID = t.ID
                        WHERE t.CREATED_AT >= :window_start
                        AND rm.OVERALL_SCORE >= 0.8
                        AND rm.SQL_VALIDITY_SCORE >= 0.9
                        AND rm.PERFORMANCE_SCORE >= 0.7
                        ORDER BY rm.OVERALL_SCORE DESC
                    """, {"window_start": window_start})
                    
                    oracle_data = cur.fetchall()
                    training_samples = []
                    
                    for row in oracle_data:
                        user_question, intent, response, overall_score, sql_score, perf_score, schema_score = row
                        
                        training_samples.append({
                            "input": user_question,
                            "intent": intent,
                            "output": response,
                            "overall_score": round(overall_score, 3),
                            "sql_validity_score": round(sql_score, 3),
                            "performance_score": round(perf_score, 3),
                            "schema_compliance_score": round(schema_score, 3)
                        })
                    
                    return {
                        "dataset_type": "oracle_sql",
                        "description": "Oracle SQL best practices dataset",
                        "sample_count": len(training_samples),
                        "samples": training_samples,
                        "creation_timestamp": _dt.now(timezone.utc).isoformat(),
                        "time_window_hours": time_window_hours
                    }
                
                elif dataset_type == "business_logic":
                    # Business logic examples dataset
                    cur.execute("""
                        SELECT 
                            t.USER_QUESTION,
                            hc.QUERY_INTENT,
                            hc.BUSINESS_CONTEXT,
                            mr.RESPONSE_TEXT,
                            rm.OVERALL_SCORE,
                            rm.BUSINESS_LOGIC_SCORE,
                            rm.SCHEMA_COMPLIANCE_SCORE
                        FROM AI_HYBRID_CONTEXT hc
                        JOIN AI_MODEL_RESPONSES mr ON hc.TURN_ID = mr.TURN_ID
                        JOIN AI_RESPONSE_METRICS rm ON mr.ID = rm.MODEL_RESPONSE_ID
                        JOIN AI_TURN t ON hc.TURN_ID = t.ID
                        WHERE t.CREATED_AT >= :window_start
                        AND rm.OVERALL_SCORE >= 0.75
                        AND rm.BUSINESS_LOGIC_SCORE >= 0.8
                        ORDER BY rm.BUSINESS_LOGIC_SCORE DESC
                    """, {"window_start": window_start})
                    
                    business_data = cur.fetchall()
                    training_samples = []
                    
                    for row in business_data:
                        user_question, intent, context, response, overall_score, business_score, schema_score = row
                        
                        training_samples.append({
                            "input": user_question,
                            "intent": intent,
                            "business_context": context,
                            "output": response,
                            "overall_score": round(overall_score, 3),
                            "business_logic_score": round(business_score, 3),
                            "schema_compliance_score": round(schema_score, 3)
                        })
                    
                    return {
                        "dataset_type": "business_logic",
                        "description": "Business logic examples dataset",
                        "sample_count": len(training_samples),
                        "samples": training_samples,
                        "creation_timestamp": _dt.now(timezone.utc).isoformat(),
                        "time_window_hours": time_window_hours
                    }
                
                else:
                    return {
                        "error": f"Unknown dataset type: {dataset_type}",
                        "supported_types": ["manufacturing", "oracle_sql", "business_logic"]
                    }
                
        except Exception as e:
            self.logger.error(f"Failed to create training dataset for {dataset_type}: {e}")
            return {
                "error": f"Failed to create training dataset: {str(e)}",
                "dataset_type": dataset_type
            }

class HybridDataRecorder:
    """Enhanced data recorder for hybrid AI system training data collection."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.quality_analyzer = QualityMetricsAnalyzer()
        
        # Test database connection and table existence
        self._test_database_connection()
    
    def _test_database_connection(self):
        """Test database connection and verify training data tables exist."""
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                
                # Check if training data tables exist
                training_tables = [
                    'AI_HYBRID_CONTEXT', 'AI_MODEL_RESPONSES', 'AI_RESPONSE_METRICS', 
                    'AI_SELECTION_DECISIONS', 'AI_PERFORMANCE_METRICS', 
                    'AI_USER_PATTERNS', 'AI_API_USAGE_LOG'
                ]
                
                for table in training_tables:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cur.fetchone()[0]
                        self.logger.info(f"[TRAINING_DATA] Table {table} exists with {count} records")
                    except Exception as e:
                        self.logger.error(f"[TRAINING_DATA] Table {table} not accessible: {e}")
                        
                # Check key columns for quality metrics
                self._validate_quality_metrics_schema(cur)
                        
        except Exception as e:
            self.logger.error(f"[TRAINING_DATA] Database connection test failed: {e}")
    
    def _validate_quality_metrics_schema(self, cursor):
        """Validate that required columns exist for quality metrics."""
        try:
            # Check AI_RESPONSE_METRICS columns
            cursor.execute("""
                SELECT column_name FROM user_tab_columns 
                WHERE table_name = 'AI_RESPONSE_METRICS'
                ORDER BY column_name
            """)
            response_columns = {row[0] for row in cursor.fetchall()}
            self.logger.info(f"[QUALITY_METRICS] AI_RESPONSE_METRICS columns: {sorted(response_columns)}")
            
            # Check AI_USER_PATTERNS columns
            cursor.execute("""
                SELECT column_name FROM user_tab_columns 
                WHERE table_name = 'AI_USER_PATTERNS'
                ORDER BY column_name
            """)
            user_columns = {row[0] for row in cursor.fetchall()}
            self.logger.info(f"[QUALITY_METRICS] AI_USER_PATTERNS columns: {sorted(user_columns)}")
            
        except Exception as e:
            self.logger.warning(f"[QUALITY_METRICS] Schema validation failed: {e}")
    def record_hybrid_context(self, 
                            turn_id: int,
                            classification_result: QueryClassification,
                            processing_strategy: str,
                            entities: Dict[str, List[str]],
                            schema_tables_used: List[str],
                            business_context: str = "",
                            classification_time_ms: float = 0.0) -> int:
        """
        Record hybrid query context information.
        
        Args:
            turn_id: Reference to AI_TURN table
            classification_result: QueryClassification object from query_classifier
            processing_strategy: Strategy used for processing
            entities: Extracted entities from query
            schema_tables_used: List of database tables referenced
            business_context: Manufacturing domain context
            classification_time_ms: Time taken for query classification
            
        Returns:
            ID of created AI_HYBRID_CONTEXT record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                context_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_HYBRID_CONTEXT
                      (TURN_ID, QUERY_INTENT, QUERY_CONFIDENCE, QUERY_COMPLEXITY,
                       ENTITIES_JSON, PROCESSING_STRATEGY, SCHEMA_TABLES_USED,
                       BUSINESS_CONTEXT, CLASSIFICATION_TIME_MS)
                    VALUES
                      (:turn_id, :intent, :confidence, :complexity, :entities,
                       :strategy, :tables, :context, :class_time)
                    RETURNING ID INTO :new_id
                    """,
                    {
                        "turn_id": turn_id,
                        "intent": classification_result.intent.value if hasattr(classification_result, 'intent') else None,
                        "confidence": classification_result.confidence if hasattr(classification_result, 'confidence') else None,
                        "complexity": classification_result.complexity_score if hasattr(classification_result, 'complexity_score') else None,
                        "entities": _json_dumps(entities),
                        "strategy": processing_strategy,
                        "tables": _json_dumps(schema_tables_used),
                        "context": business_context,
                        "class_time": classification_time_ms
                    }
                )
                conn.commit()
                self.logger.info(f"Recorded hybrid context {context_id} for turn {turn_id}")
                return context_id
                
        except Exception as e:
            self.logger.error(f"Failed to record hybrid context for turn {turn_id}: {e}")
            return 0
    
    def record_model_response(self,
                            turn_id: int,
                            model_type: str,  # 'local' or 'api'
                            model_name: str,
                            model_provider: str,
                            response_text: str,
                            response_time_ms: float,
                            confidence_score: float = None,
                            token_count: int = None,
                            prompt_tokens: int = None,
                            completion_tokens: int = None,
                            status: str = 'success',
                            error_message: str = None,
                            api_cost_usd: float = None,
                            rate_limit_hit: bool = False,
                            timeout_occurred: bool = False) -> int:
        """
        Record individual model response (local or API).
        
        Args:
            turn_id: Reference to AI_TURN table
            model_type: 'local' or 'api'
            model_name: Name of the model used
            model_provider: Provider (openrouter, ollama, direct_api)
            response_text: Generated response text
            response_time_ms: Processing time in milliseconds
            confidence_score: Model's confidence in response (0.0-1.0)
            token_count: Total tokens in response
            prompt_tokens: Tokens in prompt
            completion_tokens: Tokens in completion
            status: success, timeout, error, failed
            error_message: Error details if any
            api_cost_usd: Cost in USD for API calls
            rate_limit_hit: Whether rate limit was hit
            timeout_occurred: Whether timeout occurred
            
        Returns:
            ID of created AI_MODEL_RESPONSES record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                response_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_MODEL_RESPONSES
                      (TURN_ID, MODEL_TYPE, MODEL_NAME, MODEL_PROVIDER, RESPONSE_TEXT,
                       RESPONSE_TIME_MS, CONFIDENCE_SCORE, TOKEN_COUNT, PROMPT_TOKENS,
                       COMPLETION_TOKENS, STATUS, ERROR_MESSAGE, API_COST_USD,
                       RATE_LIMIT_HIT, TIMEOUT_OCCURRED)
                    VALUES
                      (:turn_id, :type, :name, :provider, :response, :time_ms,
                       :confidence, :tokens, :prompt_tokens, :completion_tokens,
                       :status, :error, :cost, :rate_limit, :timeout)
                    RETURNING ID INTO :new_id
                    """,
                    {
                        "turn_id": turn_id,
                        "type": model_type,
                        "name": model_name,
                        "provider": model_provider,
                        "response": response_text,
                        "time_ms": response_time_ms,
                        "confidence": confidence_score,
                        "tokens": token_count,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "status": status,
                        "error": error_message,
                        "cost": api_cost_usd,
                        "rate_limit": 'Y' if rate_limit_hit else 'N',
                        "timeout": 'Y' if timeout_occurred else 'N'
                    }
                )
                conn.commit()
                self.logger.info(f"Recorded {model_type} model response {response_id} for turn {turn_id}")
                return response_id
                
        except Exception as e:
            self.logger.error(f"Failed to record model response for turn {turn_id}: {e}")
            return 0
    
    def record_response_metrics(self,
                              model_response_id: int,
                              metrics: ResponseMetrics,
                              execution_success: bool = False,
                              execution_error: str = None,
                              result_row_count: int = None,
                              execution_time_ms: float = None,
                              security_risk_detected: bool = False,
                              oracle_specific_score: float = None) -> int:
        """
        Record 4-dimensional response quality metrics.
        
        Args:
            model_response_id: Reference to AI_MODEL_RESPONSES table
            metrics: ResponseMetrics object with scoring details
            execution_success: Whether SQL execution was successful
            execution_error: SQL execution error details
            result_row_count: Number of rows returned
            execution_time_ms: SQL execution time
            security_risk_detected: Whether security risks were detected
            oracle_specific_score: Oracle-specific compliance score
            
        Returns:
            ID of created AI_RESPONSE_METRICS record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                metrics_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_RESPONSE_METRICS
                      (MODEL_RESPONSE_ID, SQL_VALIDITY_SCORE, SCHEMA_COMPLIANCE_SCORE,
                       BUSINESS_LOGIC_SCORE, PERFORMANCE_SCORE, OVERALL_SCORE,
                       VALIDATION_REASONING, EXECUTION_SUCCESS, EXECUTION_ERROR,
                       RESULT_ROW_COUNT, EXECUTION_TIME_MS, SECURITY_RISK_DETECTED,
                       ORACLE_SPECIFIC_SCORE)
                    VALUES
                      (:resp_id, :sql_score, :schema_score, :business_score,
                       :perf_score, :overall_score, :reasoning, :exec_success,
                       :exec_error, :row_count, :exec_time, :security_risk, :oracle_score)
                    RETURNING ID INTO :new_id
                    """,
                    {
                        "resp_id": model_response_id,
                        "sql_score": metrics.sql_validity_score,
                        "schema_score": metrics.schema_compliance_score,
                        "business_score": metrics.business_logic_score,
                        "perf_score": metrics.performance_score,
                        "overall_score": metrics.overall_score,
                        "reasoning": _json_dumps(metrics.reasoning),
                        "exec_success": 'Y' if execution_success else 'N',
                        "exec_error": execution_error,
                        "row_count": result_row_count,
                        "exec_time": execution_time_ms,
                        "security_risk": 'Y' if security_risk_detected else 'N',
                        "oracle_score": oracle_specific_score
                    }
                )
                conn.commit()
                self.logger.info(f"Recorded response metrics {metrics_id} for response {model_response_id}")
                return metrics_id
                
        except Exception as e:
            self.logger.error(f"Failed to record response metrics for response {model_response_id}: {e}")
            return 0

    def record_selection_decision(self,
                                turn_id: int,
                                processing_result: ProcessingResult,
                                local_response_id: int = None,
                                api_response_id: int = None,
                                timeout_handling_used: bool = False,
                                race_condition_handled: bool = False,
                                fallback_triggered: bool = False,
                                context_aware_bonus: float = 0.0) -> int:
        """
        Record advanced response selection decision.
        
        Args:
            turn_id: Reference to AI_TURN table
            processing_result: ProcessingResult from hybrid processor
            local_response_id: ID of local model response
            api_response_id: ID of API model response
            timeout_handling_used: Whether timeout handling was used
            race_condition_handled: Whether race conditions were handled
            fallback_triggered: Whether fallback was triggered
            context_aware_bonus: Intent-based scoring bonus applied
            
        Returns:
            ID of created AI_SELECTION_DECISIONS record
        """
        try:
            # Determine selected response ID - ensure it matches an actual recorded response
            selected_id = None
            if processing_result.model_used == "Local" and local_response_id:
                selected_id = local_response_id
            elif processing_result.model_used == "API" and api_response_id:
                selected_id = api_response_id
            else:
                # Fallback: use the available response ID, but only if it's valid (not 0)
                if local_response_id and local_response_id > 0:
                    selected_id = local_response_id
                elif api_response_id and api_response_id > 0:
                    selected_id = api_response_id
                # If neither is valid, set to NULL (None) to avoid foreign key constraint violation
            
            # Only insert if we have a valid turn_id and can reference valid response IDs
            if turn_id is None or (selected_id is None and local_response_id is None and api_response_id is None):
                self.logger.warning(f"Skipping selection decision recording - missing required references for turn {turn_id}")
                return 0
            
            # Calculate score difference
            local_score = processing_result.local_metrics.overall_score if processing_result.local_metrics else None
            api_score = processing_result.api_metrics.overall_score if processing_result.api_metrics else None
            score_diff = None
            if local_score is not None and api_score is not None:
                score_diff = abs(local_score - api_score)
            
            with connect_feedback() as conn:
                cur = conn.cursor()
                decision_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_SELECTION_DECISIONS
                      (TURN_ID, LOCAL_RESPONSE_ID, API_RESPONSE_ID, SELECTED_RESPONSE_ID,
                       SELECTION_REASONING, PROCESSING_MODE, DECISION_ALGORITHM,
                       LOCAL_SCORE, API_SCORE, SCORE_DIFFERENCE, PROCESSING_TIME_TOTAL_MS,
                       PARALLEL_EFFICIENCY, TIMEOUT_HANDLING_USED, RACE_CONDITION_HANDLED,
                       FALLBACK_TRIGGERED, CONTEXT_AWARE_BONUS)
                    VALUES
                      (:p_turn_id, :p_local_id, :p_api_id, :p_selected_id, :p_reasoning,
                       :p_mode, :p_algorithm, :p_local_score, :p_api_score, :p_score_diff,
                       :p_total_time, :p_efficiency, :p_timeout_used, :p_race_handled,
                       :p_fallback, :p_context_bonus)
                    RETURNING ID INTO :new_id
                    """,
                    {
                        "p_turn_id": turn_id,
                        "p_local_id": local_response_id if local_response_id and local_response_id > 0 else None,
                        "p_api_id": api_response_id if api_response_id and api_response_id > 0 else None,
                        "p_selected_id": selected_id,  # This can be None, which is acceptable
                        "p_reasoning": str(processing_result.selection_reasoning)[:2000] if processing_result.selection_reasoning else '',
                        "p_mode": str(processing_result.processing_mode)[:100] if processing_result.processing_mode else '',
                        "p_algorithm": "advanced_metrics",
                        "p_local_score": float(local_score) if local_score is not None else 0.0,
                        "p_api_score": float(api_score) if api_score is not None else 0.0,
                        "p_score_diff": float(score_diff) if score_diff is not None else 0.0,
                        "p_total_time": float(processing_result.processing_time * 1000) if processing_result.processing_time else 0.0,
                        "p_efficiency": 0.0,  # Default value instead of None
                        "p_timeout_used": 'Y' if timeout_handling_used else 'N',
                        "p_race_handled": 'Y' if race_condition_handled else 'N',
                        "p_fallback": 'Y' if fallback_triggered else 'N',
                        "p_context_bonus": float(context_aware_bonus) if context_aware_bonus is not None else 0.0
                    }
                )
                conn.commit()
                self.logger.info(f"Recorded selection decision {decision_id} for turn {turn_id}")
                return decision_id
                
        except Exception as e:
            self.logger.error(f"Failed to record selection decision for turn {turn_id}: {e}")
            return 0

    def record_performance_metric(self,
                                turn_id: int = None,
                                metric_type: str = "",
                                metric_name: str = "",
                                metric_value: float = 0.0,
                                metric_unit: str = "",
                                metric_context: Dict[str, Any] = None,
                                session_id: str = None,
                                request_id: str = None,
                                error_category: str = None):
        """
        Record performance metrics for system monitoring.
        
        Args:
            turn_id: Optional reference to AI_TURN table
            metric_type: Type of metric (query_processing, parallel_efficiency, etc.)
            metric_name: Specific metric name
            metric_value: Numeric value of the metric
            metric_unit: Unit of measurement (ms, percentage, count, etc.)
            metric_context: Additional context as JSON
            session_id: Session identifier
            request_id: Request identifier
            error_category: Category for error metrics
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO AI_PERFORMANCE_METRICS
                      (TURN_ID, METRIC_TYPE, METRIC_NAME, METRIC_VALUE, METRIC_UNIT,
                       METRIC_CONTEXT, SESSION_ID, REQUEST_ID, ERROR_CATEGORY)
                    VALUES
                      (:turn_id, :metric_type, :metric_name, :metric_value, :metric_unit,
                       :metric_context, :session_id, :request_id, :error_category)
                    """,
                    {
                        "turn_id": turn_id,
                        "metric_type": metric_type[:100] if metric_type else None,  # Ensure not too long
                        "metric_name": metric_name[:100] if metric_name else None,  # Ensure not too long
                        "metric_value": float(metric_value) if metric_value is not None else 0.0,
                        "metric_unit": metric_unit[:20] if metric_unit else None,  # Ensure not too long
                        "metric_context": _json_dumps(metric_context or {}),
                        "session_id": session_id[:100] if session_id else None,  # Ensure not too long
                        "request_id": request_id[:100] if request_id else None,  # Ensure not too long
                        "error_category": error_category[:100] if error_category else None  # Ensure not too long
                    }
                )
                conn.commit()
                # Ensure metric_value and metric_unit are not None to prevent format string errors
                safe_metric_value = metric_value if metric_value is not None else 0.0
                safe_metric_unit = metric_unit if metric_unit is not None else ""
                self.logger.debug(f"Recorded performance metric: {metric_type}.{metric_name} = {safe_metric_value}{safe_metric_unit}")
        except Exception as e:
            self.logger.error(f"Failed to record performance metric {metric_type}.{metric_name}: {e}")
    
    def record_user_interaction(self,
                              session_id: str,
                              client_ip: str,
                              user_agent: str,
                              interaction_type: str,
                              interaction_sequence: int,
                              query_length: int = None,
                              response_time_ms: float = None,
                              user_satisfaction: int = None,
                              retry_count: int = 0,
                              copy_count: int = 0,
                              time_spent_viewing_ms: float = None,
                              browser_tab_active: bool = True,
                              query_category: str = None,
                              business_hour: bool = True):
        """
        Record user interaction patterns for UX analysis.
        
        Args:
            session_id: Session identifier
            client_ip: Client IP address
            user_agent: Browser user agent
            interaction_type: Type of interaction (query, feedback, retry, copy, etc.)
            interaction_sequence: Order within session
            query_length: Character count of query
            response_time_ms: Time to respond
            user_satisfaction: 1-5 rating if available
            retry_count: Number of retries
            copy_count: Number of copy actions
            time_spent_viewing_ms: Time spent viewing response
            browser_tab_active: Whether browser tab was active
            query_category: Categorized query type
            business_hour: Whether during business hours
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO AI_USER_PATTERNS
                      (SESSION_ID, CLIENT_IP, USER_AGENT, INTERACTION_TYPE,
                       INTERACTION_SEQUENCE, QUERY_LENGTH, RESPONSE_TIME_MS,
                       USER_SATISFACTION, RETRY_COUNT, COPY_COUNT,
                       TIME_SPENT_VIEWING_MS, BROWSER_TAB_ACTIVE, QUERY_CATEGORY,
                       BUSINESS_HOUR)
                    VALUES
                      (:session_id, :client_ip, :user_agent, :interaction_type, 
                       :interaction_sequence, :query_length, :response_time_ms,
                       :user_satisfaction, :retry_count, :copy_count, 
                       :time_spent_viewing_ms, :browser_tab_active, :query_category,
                       :business_hour)
                    """,
                    {
                        "session_id": session_id[:100] if session_id else None,  # Ensure not too long
                        "client_ip": client_ip[:45] if client_ip else None,  # IP address max length
                        "user_agent": user_agent[:500] if user_agent else None,  # Truncate user agent
                        "interaction_type": interaction_type[:50] if interaction_type else None,
                        "interaction_sequence": interaction_sequence if interaction_sequence is not None else 1,
                        "query_length": query_length if query_length is not None else 0,
                        "response_time_ms": float(response_time_ms) if response_time_ms is not None else 0.0,
                        "user_satisfaction": user_satisfaction,
                        "retry_count": retry_count if retry_count is not None else 0,
                        "copy_count": copy_count if copy_count is not None else 0,
                        "time_spent_viewing_ms": float(time_spent_viewing_ms) if time_spent_viewing_ms is not None else 0.0,
                        "browser_tab_active": 'Y' if browser_tab_active else 'N',
                        "query_category": query_category[:100] if query_category else None,
                        "business_hour": 'Y' if business_hour else 'N'
                    }
                )
                conn.commit()
                # Ensure session_id is not None to prevent format string errors
                safe_session_id = session_id if session_id is not None else "unknown"
                self.logger.debug(f"Recorded user interaction: {interaction_type} for session {safe_session_id}")
                
        except Exception as e:
            # Ensure session_id is not None to prevent format string errors
            safe_session_id = session_id if session_id is not None else "unknown"
            self.logger.error(f"Failed to record user interaction for session {safe_session_id}: {e}")
    def record_api_usage(self,
                        turn_id: int = None,
                        api_provider: str = "",
                        model_name: str = "",
                        request_tokens: int = None,
                        response_tokens: int = None,
                        cost_usd: float = None,
                        rate_limit_remaining: int = None,
                        rate_limit_reset_at: _dt = None,
                        request_success: bool = True,
                        error_code: str = None,
                        response_time_ms: float = None,
                        daily_usage_count: int = None,
                        monthly_cost_usd: float = None):
        """
        Record API usage and rate limiting information.
        
        Args:
            turn_id: Optional reference to AI_TURN table
            api_provider: API provider name (openrouter, direct_deepseek, etc.)
            model_name: Name of the model used
            request_tokens: Number of tokens in request
            response_tokens: Number of tokens in response
            cost_usd: Cost in USD
            rate_limit_remaining: Remaining rate limit
            rate_limit_reset_at: When rate limit resets
            request_success: Whether request was successful
            error_code: Error code if any
            response_time_ms: Response time in milliseconds
            daily_usage_count: Daily usage count
            monthly_cost_usd: Monthly cost in USD
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO AI_API_USAGE_LOG
                      (TURN_ID, API_PROVIDER, MODEL_NAME, REQUEST_TOKENS, RESPONSE_TOKENS,
                       COST_USD, RATE_LIMIT_REMAINING, RATE_LIMIT_RESET_AT, REQUEST_SUCCESS,
                       ERROR_CODE, RESPONSE_TIME_MS, DAILY_USAGE_COUNT, MONTHLY_COST_USD)
                    VALUES
                      (:turn_id, :provider, :model, :req_tokens, :resp_tokens,
                       :cost, :rate_remaining, :rate_reset, :success, :error,
                       :resp_time, :daily_count, :monthly_cost)
                    """,
                    {
                        "turn_id": turn_id,
                        "provider": api_provider,
                        "model": model_name,
                        "req_tokens": request_tokens,
                        "resp_tokens": response_tokens,
                        "cost": cost_usd,
                        "rate_remaining": rate_limit_remaining,
                        "rate_reset": rate_limit_reset_at,
                        "success": 'Y' if request_success else 'N',
                        "error": error_code,
                        "resp_time": response_time_ms,
                        "daily_count": daily_usage_count,
                        "monthly_cost": monthly_cost_usd
                    }
                )
                conn.commit()
                # Ensure cost_usd is not None to prevent format string errors
                safe_cost_usd = cost_usd if cost_usd is not None else 0.0
                self.logger.debug(f"Recorded API usage: {api_provider}.{model_name} - {safe_cost_usd} USD")
                
        except Exception as e:
            self.logger.error(f"Failed to record API usage for {api_provider}.{model_name}: {e}")
    def get_quality_metrics(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Step 5.2: Get comprehensive quality metrics report.
        
        Args:
            time_window_hours: Time window for analysis (default: last 24 hours)
            
        Returns:
            Complete quality metrics report including success rates and user satisfaction
        """
        return self.quality_analyzer.generate_quality_report(time_window_hours)
    
    def get_success_rates(self, time_window_hours: int = 24) -> Dict[str, float]:
        """
        Get success rate metrics for query understanding and SQL execution.
        
        Args:
            time_window_hours: Time window for analysis
            
        Returns:
            Success rate metrics
        """
        return self.quality_analyzer.calculate_success_rates(time_window_hours)
    
    def get_user_satisfaction_metrics(self, time_window_hours: int = 24) -> Dict[str, float]:
        """
        Get user satisfaction indicators including acceptance rates and feedback.
        
        Args:
            time_window_hours: Time window for analysis
            
        Returns:
            User satisfaction metrics
        """
        return self.quality_analyzer.analyze_user_satisfaction(time_window_hours)

    def test_quality_metrics_system(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Test the quality metrics system end-to-end.
        
        Args:
            time_window_hours: Time window for testing
            
        Returns:
            Test results and diagnostics
        """
        test_results = {
            "timestamp": _dt.now(timezone.utc).isoformat(),
            "success_rates_test": {"status": "pending", "error": None, "data": None},
            "satisfaction_test": {"status": "pending", "error": None, "data": None},
            "quality_report_test": {"status": "pending", "error": None, "data": None},
            "overall_status": "pending"
        }
        
        # Test success rates calculation
        try:
            success_data = self.quality_analyzer.calculate_success_rates(time_window_hours)
            test_results["success_rates_test"] = {
                "status": "success" if success_data else "no_data",
                "error": None,
                "data": success_data,
                "metrics_count": len(success_data) if success_data else 0
            }
        except Exception as e:
            test_results["success_rates_test"] = {
                "status": "failed",
                "error": str(e),
                "data": None
            }
        
        # Test user satisfaction analysis
        try:
            satisfaction_data = self.quality_analyzer.analyze_user_satisfaction(time_window_hours)
            test_results["satisfaction_test"] = {
                "status": "success" if satisfaction_data else "no_data",
                "error": None,
                "data": satisfaction_data,
                "metrics_count": len(satisfaction_data) if satisfaction_data else 0
            }
        except Exception as e:
            test_results["satisfaction_test"] = {
                "status": "failed",
                "error": str(e),
                "data": None
            }
        
        # Test quality report generation
        try:
            quality_report = self.quality_analyzer.generate_quality_report(time_window_hours)
            test_results["quality_report_test"] = {
                "status": "success" if quality_report else "no_data",
                "error": None,
                "data": quality_report,
                "has_composite_scores": bool(quality_report.get("composite_scores")) if quality_report else False
            }
        except Exception as e:
            test_results["quality_report_test"] = {
                "status": "failed",
                "error": str(e),
                "data": None
            }
        
        # Determine overall status
        all_tests = [test_results["success_rates_test"], test_results["satisfaction_test"], test_results["quality_report_test"]]
        if all(test["status"] in ["success", "no_data"] for test in all_tests):
            test_results["overall_status"] = "success"
        elif any(test["status"] == "failed" for test in all_tests):
            test_results["overall_status"] = "failed"
        else:
            test_results["overall_status"] = "partial"
        
        self.logger.info(f"[QUALITY_METRICS] System test completed with status: {test_results['overall_status']}")
        return test_results

    def record_complete_hybrid_turn(self,
                                  turn_id: int,
                                  classification_result: QueryClassification,
                                  processing_result: ProcessingResult,
                                  entities: Dict[str, List[str]] = None,
                                  schema_tables_used: List[str] = None,
                                  business_context: str = "",
                                  sql_execution_success: bool = False,
                                  sql_execution_error: str = None,
                                  result_row_count: int = None,
                                  sql_execution_time_ms: float = None,
                                  classification_time_ms: float = 0.0,
                                  session_id: str = None,
                                  client_ip: str = None,
                                  user_agent: str = None) -> Dict[str, int]:
        """
        Record complete hybrid processing turn with comprehensive training data.
        
        Args:
            turn_id: Reference to AI_TURN table
            classification_result: QueryClassification object from query_classifier
            processing_result: ProcessingResult from hybrid processor
            entities: Extracted entities from query
            schema_tables_used: List of database tables referenced
            business_context: Manufacturing domain context
            sql_execution_success: Whether final SQL execution was successful
            sql_execution_error: SQL execution error details
            result_row_count: Number of rows returned
            sql_execution_time_ms: SQL execution time
            classification_time_ms: Time taken for query classification
            session_id: Session identifier for user pattern tracking
            client_ip: Client IP for user pattern tracking
            user_agent: User agent for user pattern tracking
            
        Returns:
            Dictionary with IDs of all created records
        """
        recorded_ids = {
            "hybrid_context_id": 0,
            "local_response_id": 0,
            "api_response_id": 0,
            "local_metrics_id": 0,
            "api_metrics_id": 0,
            "selection_decision_id": 0,
            "performance_metrics_count": 0
        }
        
        try:
            # 1. Record hybrid context (query classification and entities)
            recorded_ids["hybrid_context_id"] = self.record_hybrid_context(
                turn_id=turn_id,
                classification_result=classification_result,
                processing_strategy=processing_result.processing_mode,
                entities=entities or {},
                schema_tables_used=schema_tables_used or [],
                business_context=business_context,
                classification_time_ms=classification_time_ms
            )
            
            # 2. Record local model response if available
            if processing_result.local_response:
                recorded_ids["local_response_id"] = self.record_model_response(
                    turn_id=turn_id,
                    model_type="local",
                    model_name=processing_result.local_model_name or "ollama",
                    model_provider="ollama",
                    response_text=processing_result.local_response,
                    response_time_ms=processing_result.local_processing_time * 1000 if processing_result.local_processing_time else 0.0,
                    confidence_score=processing_result.local_confidence,
                    status="success" if processing_result.local_response else "failed"
                )
                
                # Record local response metrics
                if processing_result.local_metrics:
                    recorded_ids["local_metrics_id"] = self.record_response_metrics(
                        model_response_id=recorded_ids["local_response_id"],
                        metrics=processing_result.local_metrics,
                        execution_success=sql_execution_success and processing_result.model_used == "Local",
                        execution_error=sql_execution_error if processing_result.model_used == "Local" else None,
                        result_row_count=result_row_count if processing_result.model_used == "Local" else None,
                        execution_time_ms=sql_execution_time_ms if processing_result.model_used == "Local" else None
                    )
            
            # 3. Record API model response if available
            if processing_result.api_response:
                recorded_ids["api_response_id"] = self.record_model_response(
                    turn_id=turn_id,
                    model_type="api",
                    model_name=processing_result.api_model_name or "deepseek",
                    model_provider="openrouter",
                    response_text=processing_result.api_response,
                    response_time_ms=processing_result.api_processing_time * 1000 if processing_result.api_processing_time else 0.0,
                    confidence_score=processing_result.api_confidence,
                    api_cost_usd=getattr(processing_result, 'api_cost_usd', None),
                    token_count=getattr(processing_result, 'api_token_count', None),
                    status="success" if processing_result.api_response else "failed"
                )
                
                # Record API response metrics
                if processing_result.api_metrics:
                    recorded_ids["api_metrics_id"] = self.record_response_metrics(
                        model_response_id=recorded_ids["api_response_id"],
                        metrics=processing_result.api_metrics,
                        execution_success=sql_execution_success and processing_result.model_used == "API",
                        execution_error=sql_execution_error if processing_result.model_used == "API" else None,
                        result_row_count=result_row_count if processing_result.model_used == "API" else None,
                        execution_time_ms=sql_execution_time_ms if processing_result.model_used == "API" else None
                    )
            
            # 4. Record selection decision
            recorded_ids["selection_decision_id"] = self.record_selection_decision(
                turn_id=turn_id,
                processing_result=processing_result,
                local_response_id=recorded_ids["local_response_id"] if recorded_ids["local_response_id"] > 0 else None,
                api_response_id=recorded_ids["api_response_id"] if recorded_ids["api_response_id"] > 0 else None,
                timeout_handling_used=processing_result.processing_mode in ["timeout_local", "timeout_api"],
                race_condition_handled=processing_result.processing_mode == "parallel",
                fallback_triggered=processing_result.processing_mode in ["local_only", "api_only"]
            )
            
            # 5. Record performance metrics
            performance_metrics = [
                ("query_processing", "total_processing_time", processing_result.processing_time * 1000 if processing_result.processing_time else 0.0, "ms"),
                ("query_processing", "classification_time", classification_time_ms or 0.0, "ms"),
                ("parallel_efficiency", "local_processing_time", 
                 processing_result.local_processing_time * 1000 if processing_result.local_processing_time else 0.0, "ms"),
                ("parallel_efficiency", "api_processing_time", 
                 processing_result.api_processing_time * 1000 if processing_result.api_processing_time else 0.0, "ms"),
                ("model_confidence", "local_confidence", processing_result.local_confidence or 0.0, "score"),
                ("model_confidence", "api_confidence", processing_result.api_confidence or 0.0, "score")
            ]
            
            # Add SQL execution metrics if available
            if sql_execution_time_ms is not None:
                performance_metrics.append(("sql_execution", "execution_time", sql_execution_time_ms, "ms"))
            if result_row_count is not None:
                performance_metrics.append(("sql_execution", "result_row_count", float(result_row_count), "count"))
            
            # Record all performance metrics
            for metric_type, metric_name, metric_value, metric_unit in performance_metrics:
                if metric_value is not None and metric_value >= 0:
                    self.record_performance_metric(
                        turn_id=turn_id,
                        metric_type=metric_type,
                        metric_name=metric_name,
                        metric_value=metric_value,
                        metric_unit=metric_unit,
                        session_id=session_id
                    )
                    recorded_ids["performance_metrics_count"] += 1
            
            # 6. Record user interaction patterns if session data available
            if session_id and client_ip:
                try:
                    self.record_user_interaction(
                        session_id=session_id,
                        client_ip=client_ip,
                        user_agent=user_agent or "",
                        interaction_type="hybrid_query",
                        interaction_sequence=1,  # Could be enhanced with actual sequence tracking
                        query_length=len(getattr(classification_result, 'original_query', '')),
                        response_time_ms=processing_result.processing_time * 1000,
                        retry_count=0,  # Could be enhanced with retry tracking
                        query_category=classification_result.intent.value if hasattr(classification_result, 'intent') else "general",
                        business_hour=True  # Could be enhanced with actual business hour detection
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to record user interaction patterns: {e}")
            
            # 7. Record API usage if API was used
            if processing_result.api_response and getattr(processing_result, 'api_cost_usd', None):
                try:
                    self.record_api_usage(
                        turn_id=turn_id,
                        api_provider="openrouter",
                        model_name=processing_result.api_model_name or "deepseek",
                        cost_usd=getattr(processing_result, 'api_cost_usd', None),
                        request_tokens=getattr(processing_result, 'api_prompt_tokens', None),
                        response_tokens=getattr(processing_result, 'api_completion_tokens', None),
                        request_success=bool(processing_result.api_response),
                        response_time_ms=processing_result.api_processing_time * 1000 if processing_result.api_processing_time else None
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to record API usage: {e}")
            
            self.logger.info(f"Successfully recorded complete hybrid turn {turn_id} with {sum(1 for v in recorded_ids.values() if isinstance(v, int) and v > 0)} records")
            return recorded_ids
            
        except Exception as e:
            self.logger.error(f"Failed to record complete hybrid turn for turn {turn_id}: {e}")
            return recorded_ids

# Global instance for easy access
hybrid_data_recorder = HybridDataRecorder()

# Convenience functions for direct import
def record_hybrid_turn(turn_id: int, classification_result, processing_result: ProcessingResult, **kwargs) -> Dict[str, int]:
    """Convenience function to record complete hybrid turn."""
    return hybrid_data_recorder.record_complete_hybrid_turn(
        turn_id=turn_id,
        classification_result=classification_result,
        processing_result=processing_result,
        **kwargs
    )

def record_performance(metric_type: str, metric_name: str, metric_value: float, **kwargs):
    """Convenience function to record performance metrics."""
    hybrid_data_recorder.record_performance_metric(
        metric_type=metric_type,
        metric_name=metric_name,
        metric_value=metric_value,
        **kwargs
    )

def record_api_call(api_provider: str, model_name: str, **kwargs):
    """Convenience function to record API usage."""
    hybrid_data_recorder.record_api_usage(
        api_provider=api_provider,
        model_name=model_name,
        **kwargs
    )

def get_quality_dashboard(time_window_hours: int = 24) -> Dict[str, Any]:
    """
    Step 5.2: Get quality metrics dashboard data.
    
    Args:
        time_window_hours: Time window for analysis
        
    Returns:
        Dashboard-ready quality metrics
    """
    try:
        report = hybrid_data_recorder.get_quality_metrics(time_window_hours)
        
        # Extract key metrics for dashboard
        success_metrics = report.get("success_metrics", {})
        satisfaction_metrics = report.get("satisfaction_metrics", {})
        composite_scores = report.get("composite_scores", {})
        
        return {
            "system_health": composite_scores.get("system_health_status", "unknown"),
            "overall_score": round(composite_scores.get("overall_quality_score", 0.0), 3),
            "key_metrics": {
                "query_success_rate": round(success_metrics.get("query_understanding_accuracy", 0.0), 3),
                "sql_execution_rate": round(success_metrics.get("sql_execution_success_rate", 0.0), 3),
                "user_satisfaction": round(satisfaction_metrics.get("predicted_satisfaction_score", 0.0), 3),
                "response_acceptance": round(satisfaction_metrics.get("response_acceptance_rate", 0.0), 3)
            },
            "performance_indicators": {
                "avg_response_time": round(satisfaction_metrics.get("avg_response_time_ms", 0.0), 1),
                "retry_frequency": round(satisfaction_metrics.get("retry_frequency", 0.0), 3),
                "total_queries": success_metrics.get("total_queries_analyzed", 0),
                "security_issues": success_metrics.get("security_issues_count", 0)
            },
            "alerts": report.get("alerts", []),
            "recommendation": composite_scores.get("recommendation", "No specific recommendations"),
            "last_updated": report.get("report_timestamp"),
            "time_window_hours": time_window_hours
        }
        
    except Exception as e:
        logger.error(f"Failed to generate quality dashboard: {e}")
        return {
            "system_health": "error",
            "overall_score": 0.0,
            "error": str(e)
        }

def test_quality_metrics_system(time_window_hours: int = 24) -> Dict[str, Any]:
    """Convenience function to test the quality metrics system."""
    return hybrid_data_recorder.test_quality_metrics_system(time_window_hours)

def get_quality_system_status() -> Dict[str, Any]:
    """Get current status of the quality metrics system."""
    try:
        # Test with a short time window to minimize load
        test_results = hybrid_data_recorder.test_quality_metrics_system(1)
        
        return {
            "system_available": True,
            "overall_status": test_results["overall_status"],
            "last_test": test_results["timestamp"],
            "components": {
                "success_rates": test_results["success_rates_test"]["status"],
                "user_satisfaction": test_results["satisfaction_test"]["status"],
                "quality_reports": test_results["quality_report_test"]["status"]
            },
            "errors": [
                test["error"] for test in [
                    test_results["success_rates_test"],
                    test_results["satisfaction_test"], 
                    test_results["quality_report_test"]
                ] if test["error"]
            ]
        }
    except Exception as e:
        return {
            "system_available": False,
            "overall_status": "error",
            "error": str(e)
        }

def test_continuous_learning_system(time_window_hours: int = 24) -> Dict[str, Any]:
    """
    Test the continuous learning system end-to-end.
    
    Args:
        time_window_hours: Time window for testing
        
    Returns:
        Test results and diagnostics
    """
    try:
        # Initialize the recorder
        recorder = HybridDataRecorder()
        
        test_results = {
            "timestamp": _dt.now(timezone.utc).isoformat(),
            "performance_comparison_test": {"status": "pending", "error": None, "data": None},
            "model_strengths_test": {"status": "pending", "error": None, "data": None},
            "user_preferences_test": {"status": "pending", "error": None, "data": None},
            "learning_insights_test": {"status": "pending", "error": None, "data": None},
            "overall_status": "pending"
        }
        
        # Test performance comparison
        try:
            performance_comparison = recorder.quality_analyzer.analyze_performance_comparison(time_window_hours)
            test_results["performance_comparison_test"] = {
                "status": "success" if performance_comparison else "no_data",
                "error": None,
                "data": performance_comparison,
                "metrics_count": len(performance_comparison.get("performance_by_intent", {})) if performance_comparison else 0
            }
        except Exception as e:
            test_results["performance_comparison_test"] = {
                "status": "failed",
                "error": str(e),
                "data": None
            }
        
        # Test model strengths
        try:
            model_strengths = recorder.quality_analyzer.identify_model_strengths(time_window_hours)
            test_results["model_strengths_test"] = {
                "status": "success" if model_strengths else "no_data",
                "error": None,
                "data": model_strengths,
                "domains_analyzed": len(model_strengths.get("domain_strengths", {})) if model_strengths else 0
            }
        except Exception as e:
            test_results["model_strengths_test"] = {
                "status": "failed",
                "error": str(e),
                "data": None
            }
        
        # Test user preferences
        try:
            user_preferences = recorder.quality_analyzer.analyze_user_preference_patterns(time_window_hours)
            test_results["user_preferences_test"] = {
                "status": "success" if user_preferences else "no_data",
                "error": None,
                "data": user_preferences,
                "intents_analyzed": len(user_preferences.get("preference_patterns", {})) if user_preferences else 0
            }
        except Exception as e:
            test_results["user_preferences_test"] = {
                "status": "failed",
                "error": str(e),
                "data": None
            }
        
        # Test learning insights
        try:
            learning_insights = recorder.quality_analyzer.generate_learning_insights(time_window_hours)
            test_results["learning_insights_test"] = {
                "status": "success" if learning_insights else "no_data",
                "error": None,
                "data": learning_insights,
                "recommendations_count": len(learning_insights.get("recommendations", [])) if learning_insights else 0
            }
        except Exception as e:
            test_results["learning_insights_test"] = {
                "status": "failed",
                "error": str(e),
                "data": None
            }
        
        # Determine overall status
        all_tests = [
            test_results["performance_comparison_test"], 
            test_results["model_strengths_test"],
            test_results["user_preferences_test"],
            test_results["learning_insights_test"]
        ]
        if all(test["status"] in ["success", "no_data"] for test in all_tests):
            test_results["overall_status"] = "success"
        elif any(test["status"] == "failed" for test in all_tests):
            test_results["overall_status"] = "failed"
        else:
            test_results["overall_status"] = "partial"
        
        logger.info(f"[CONTINUOUS_LEARNING] System test completed with status: {test_results['overall_status']}")
        return test_results
        
    except Exception as e:
        logger.error(f"[CONTINUOUS_LEARNING] System test failed: {e}")
        return {
            "timestamp": _dt.now(timezone.utc).isoformat(),
            "overall_status": "error",
            "error": str(e)
        }

def get_performance_comparison(time_window_hours: int = 24) -> Dict[str, Any]:
    """Convenience function to get performance comparison."""
    try:
        recorder = HybridDataRecorder()
        return recorder.quality_analyzer.analyze_performance_comparison(time_window_hours)
    except Exception as e:
        logger.error(f"Failed to get performance comparison: {e}")
        return {}

def get_model_strengths(time_window_hours: int = 24) -> Dict[str, Any]:
    """Convenience function to get model strengths."""
    try:
        recorder = HybridDataRecorder()
        return recorder.quality_analyzer.identify_model_strengths(time_window_hours)
    except Exception as e:
        logger.error(f"Failed to get model strengths: {e}")
        return {}

def get_user_preferences(time_window_hours: int = 24) -> Dict[str, Any]:
    """Convenience function to get user preferences."""
    try:
        recorder = HybridDataRecorder()
        return recorder.quality_analyzer.analyze_user_preference_patterns(time_window_hours)
    except Exception as e:
        logger.error(f"Failed to get user preferences: {e}")
        return {}

def get_learning_insights(time_window_hours: int = 24) -> Dict[str, Any]:
    """Convenience function to get learning insights."""
    try:
        recorder = HybridDataRecorder()
        return recorder.quality_analyzer.generate_learning_insights(time_window_hours)
    except Exception as e:
        logger.error(f"Failed to get learning insights: {e}")
        return {}

def identify_high_quality_samples(time_window_hours: int = 168, min_quality_score: float = 0.8) -> Dict[str, Any]:
    """Convenience function to identify high-quality samples."""
    try:
        recorder = HybridDataRecorder()
        return recorder.quality_analyzer.identify_high_quality_samples(time_window_hours, min_quality_score)
    except Exception as e:
        logger.error(f"Failed to identify high-quality samples: {e}")
        return {}

def create_training_dataset(dataset_type: str = "manufacturing", time_window_hours: int = 720) -> Dict[str, Any]:
    """Convenience function to create training datasets."""
    try:
        recorder = HybridDataRecorder()
        return recorder.quality_analyzer.create_training_dataset(dataset_type, time_window_hours)
    except Exception as e:
        logger.error(f"Failed to create training dataset for {dataset_type}: {e}")
        return {}

# Export main classes and functions
__all__ = [
    'QualityMetricsAnalyzer',
    'HybridDataRecorder',
    'hybrid_data_recorder',
    'record_hybrid_turn',
    'record_performance',
    'record_api_call',
    'get_quality_dashboard',
    'test_quality_metrics_system',
    'get_quality_system_status',
    'test_continuous_learning_system',
    'get_performance_comparison',
    'get_model_strengths',
    'get_user_preferences',
    'get_learning_insights',
    'identify_high_quality_samples',
    'create_training_dataset'
]