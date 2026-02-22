"""
TomeHub Daily Search Analytics DAG

Analyzes search logs, intent distribution, strategy effectiveness, and query performance.
Generates daily analytics report and stores insights in analytics tables.

Schedule: Daily at 2 AM UTC
Owner: data-team
Tags: analytics, search, tomehub
"""

from datetime import datetime, timedelta
from airflow.decorators import dag, task
from airflow.models import Variable
import pandas as pd
import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# Default args for all tasks
default_args = {
    "owner": "data-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
    "execution_timeout": timedelta(hours=2),
}

# DAG configuration
DAG_CONFIG = {
    "dag_id": "tomehub_search_analytics",
    "description": "Daily analytics for TomeHub search logs and intent distribution",
    "schedule_interval": "0 2 * * *",  # 2 AM UTC daily
    "start_date": datetime(2026, 2, 1),
    "catchup": False,
    "max_active_runs": 1,
    "default_args": default_args,
    "tags": ["analytics", "search", "tomehub", "daily"],
}


@dag(**DAG_CONFIG)
def tomehub_search_analytics():
    """
    Main DAG function for TomeHub search analytics pipeline.
    
    Tasks:
    1. extract_search_logs: Fetch logs from TOMEHUB_SEARCH_LOGS (past 24h)
    2. analyze_intent: Classify intent distribution
    3. analyze_strategy: Evaluate strategy effectiveness
    4. analyze_performance: Calculate latency metrics
    5. generate_report: Create markdown report
    6. notify_completion: Log completion
    """
    
    @task
    def extract_search_logs(ds: str = None, **context) -> Dict[str, Any]:
        """
        Extract search logs from TOMEHUB_SEARCH_LOGS for the past 24 hours.
        
        Returns:
            Dictionary with logs dataframe (JSON serialized) and metadata
        """
        from infrastructure.db_manager import DatabaseManager
        import datetime as dt
        
        try:
            # Get read pool connection
            DatabaseManager.init_pool()
            conn = DatabaseManager._read_pool.acquire()
            cursor = conn.cursor()
            
            # Query: Past 24 hours of logs (or less if first run)
            query = """
            SELECT 
                ID,
                FIREBASE_UID,
                QUERY_TEXT,
                INTENT,
                STRATEGY_WEIGHTS,
                EXECUTION_TIME_MS,
                RRF_SCORE,
                RESULT_COUNT,
                CREATED_AT
            FROM TOMEHUB_SEARCH_LOGS
            WHERE CREATED_AT >= TRUNC(SYSDATE - 1)
            ORDER BY CREATED_AT DESC
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description]
            
            df = pd.DataFrame(rows, columns=col_names)
            
            # Serialize dataframe for XCom
            logs_json = df.to_json(orient='records', date_format='iso')
            
            metadata = {
                "total_logs": len(df),
                "date_range": f"{df['CREATED_AT'].min()} to {df['CREATED_AT'].max()}",
                "unique_users": df['FIREBASE_UID'].nunique() if len(df) > 0 else 0,
                "execution_time": f"{datetime.now().isoformat()}",
            }
            
            logger.info(f"✅ Extracted {len(df)} search logs")
            logger.info(f"   Metadata: {metadata}")
            
            conn.close()
            
            return {
                "logs_json": logs_json,
                "metadata": metadata,
                "row_count": len(df),
            }
        
        except Exception as e:
            logger.error(f"❌ Error extracting search logs: {str(e)}")
            raise
    
    
    @task
    def analyze_intent(extracted_data: Dict = None, **context) -> Dict[str, Any]:
        """
        Analyze intent distribution from search logs.
        
        Classifies searches by intent type:
        - SEMANTIC_SEARCH: Vector similarity
        - EXACT_MATCH: Token matching
        - LEMMA_MATCH: Normalized lemma
        - HYBRID: Multiple strategies
        
        Returns:
            Intent distribution statistics
        """
        try:
            logs_json = extracted_data['logs_json']
            df = pd.read_json(logs_json)
            
            if len(df) == 0:
                logger.warning("⚠️ No search logs to analyze")
                return {"intent_distribution": {}, "row_count": 0}
            
            # Parse INTENT column
            intent_counts = df['INTENT'].value_counts().to_dict()
            intent_pct = (df['INTENT'].value_counts(normalize=True) * 100).round(2).to_dict()
            
            analysis = {
                "intent_distribution": intent_counts,
                "intent_percentage": intent_pct,
                "most_common_intent": df['INTENT'].mode()[0] if len(df) > 0 else None,
                "row_count": len(df),
            }
            
            logger.info(f"✅ Intent Analysis Complete")
            logger.info(f"   Distribution: {intent_counts}")
            
            return analysis
        
        except Exception as e:
            logger.error(f"❌ Error analyzing intent: {str(e)}")
            raise
    
    
    @task
    def analyze_strategy(extracted_data: Dict = None, **context) -> Dict[str, Any]:
        """
        Analyze strategy effectiveness from STRATEGY_WEIGHTS.
        
        Extracts strategy performance:
        - RRF score distribution
        - Strategy weight patterns
        - Performance percentiles
        
        Returns:
            Strategy effectiveness metrics
        """
        try:
            logs_json = extracted_data['logs_json']
            df = pd.read_json(logs_json)
            
            if len(df) == 0:
                return {"strategy_stats": {}, "row_count": 0}
            
            # Analysis on RRF_SCORE and execution time
            strategy_stats = {
                "avg_rrf_score": float(df['RRF_SCORE'].mean()) if 'RRF_SCORE' in df.columns else None,
                "median_execution_time_ms": float(df['EXECUTION_TIME_MS'].median()) if 'EXECUTION_TIME_MS' in df.columns else None,
                "p95_execution_time_ms": float(df['EXECUTION_TIME_MS'].quantile(0.95)) if 'EXECUTION_TIME_MS' in df.columns else None,
                "p99_execution_time_ms": float(df['EXECUTION_TIME_MS'].quantile(0.99)) if 'EXECUTION_TIME_MS' in df.columns else None,
                "avg_result_count": float(df['RESULT_COUNT'].mean()) if 'RESULT_COUNT' in df.columns else None,
            }
            
            logger.info(f"✅ Strategy Analysis Complete")
            logger.info(f"   Avg RRF Score: {strategy_stats['avg_rrf_score']:.2f}")
            logger.info(f"   Median Latency: {strategy_stats['median_execution_time_ms']:.0f}ms")
            
            return {
                "strategy_stats": strategy_stats,
                "row_count": len(df),
            }
        
        except Exception as e:
            logger.error(f"❌ Error analyzing strategy: {str(e)}")
            raise
    
    
    @task
    def analyze_performance(extracted_data: Dict = None, **context) -> Dict[str, Any]:
        """
        Analyze query performance metrics.
        
        Calculates:
        - Execution time distribution
        - Result count distribution
        - Performance by intent
        - Slow queries (>2s)
        
        Returns:
            Performance insights
        """
        try:
            logs_json = extracted_data['logs_json']
            df = pd.read_json(logs_json)
            
            if len(df) == 0:
                return {"performance_stats": {}, "row_count": 0}
            
            # Identify slow queries
            slow_queries = df[df['EXECUTION_TIME_MS'] > 2000] if 'EXECUTION_TIME_MS' in df.columns else pd.DataFrame()
            
            performance_stats = {
                "total_queries": len(df),
                "avg_execution_time_ms": float(df['EXECUTION_TIME_MS'].mean()) if 'EXECUTION_TIME_MS' in df.columns else None,
                "slow_queries_count": len(slow_queries),
                "slow_queries_pct": float(len(slow_queries) / len(df) * 100) if len(df) > 0 else 0,
                "execution_time_buckets": {
                    "under_200ms": len(df[df['EXECUTION_TIME_MS'] < 200]) if 'EXECUTION_TIME_MS' in df.columns else 0,
                    "200_500ms": len(df[(df['EXECUTION_TIME_MS'] >= 200) & (df['EXECUTION_TIME_MS'] < 500)]) if 'EXECUTION_TIME_MS' in df.columns else 0,
                    "500_1000ms": len(df[(df['EXECUTION_TIME_MS'] >= 500) & (df['EXECUTION_TIME_MS'] < 1000)]) if 'EXECUTION_TIME_MS' in df.columns else 0,
                    "1000_2000ms": len(df[(df['EXECUTION_TIME_MS'] >= 1000) & (df['EXECUTION_TIME_MS'] < 2000)]) if 'EXECUTION_TIME_MS' in df.columns else 0,
                    "over_2000ms": len(slow_queries),
                },
            }
            
            logger.info(f"✅ Performance Analysis Complete")
            logger.info(f"   Total Queries: {performance_stats['total_queries']}")
            logger.info(f"   Slow Queries (>2s): {performance_stats['slow_queries_count']} ({performance_stats['slow_queries_pct']:.1f}%)")
            
            return {
                "performance_stats": performance_stats,
                "row_count": len(df),
            }
        
        except Exception as e:
            logger.error(f"❌ Error analyzing performance: {str(e)}")
            raise
    
    
    @task
    def generate_report(
        extracted_data: Dict = None,
        intent_analysis: Dict = None,
        strategy_analysis: Dict = None,
        performance_analysis: Dict = None,
        **context
    ) -> str:
        """
        Generate comprehensive markdown report of daily analytics.
        
        Returns:
            Report content as string
        """
        try:
            report = f"""# TomeHub Search Analytics Report
**Date:** {context['ds']}
**Generated:** {datetime.now().isoformat()}

---

## Executive Summary

- **Total Search Queries Analyzed:** {extracted_data['metadata']['total_logs']}
- **Unique Users:** {extracted_data['metadata']['unique_users']}
- **Date Range:** {extracted_data['metadata']['date_range']}

---

## Intent Distribution

{intent_analysis['intent_distribution']}

**Most Common Intent:** {intent_analysis['most_common_intent']}

### Breakdown by Percentage
"""
            for intent, pct in intent_analysis['intent_percentage'].items():
                report += f"\n- **{intent}:** {pct}%"
            
            report += f"""

---

## Strategy Effectiveness

| Metric | Value |
|--------|-------|
| Avg RRF Score | {strategy_analysis['strategy_stats']['avg_rrf_score']:.2f} |
| Median Latency | {strategy_analysis['strategy_stats']['median_execution_time_ms']:.0f}ms |
| P95 Latency | {strategy_analysis['strategy_stats']['p95_execution_time_ms']:.0f}ms |
| P99 Latency | {strategy_analysis['strategy_stats']['p99_execution_time_ms']:.0f}ms |
| Avg Result Count | {strategy_analysis['strategy_stats']['avg_result_count']:.1f} |

---

## Performance Metrics

### Execution Time Distribution

"""
            buckets = performance_analysis['performance_stats']['execution_time_buckets']
            for bucket, count in buckets.items():
                pct = (count / performance_analysis['performance_stats']['total_queries'] * 100) if performance_analysis['performance_stats']['total_queries'] > 0 else 0
                report += f"- **{bucket}:** {count} queries ({pct:.1f}%)\n"
            
            report += f"""

### Slow Query Analysis

- **Queries >2 seconds:** {performance_analysis['performance_stats']['slow_queries_count']}
- **Slow Query Percentage:** {performance_analysis['performance_stats']['slow_queries_pct']:.2f}%

---

## Recommendations

"""
            
            # Smart recommendations based on data
            slow_pct = performance_analysis['performance_stats']['slow_queries_pct']
            if slow_pct > 5:
                report += "⚠️ **High slow query rate detected** - Consider query optimization or index tuning\n"
            else:
                report += "✅ **Query performance is healthy** - Below 5% slow query threshold\n"
            
            intent_dist = intent_analysis['intent_distribution']
            dominant = max(intent_dist.items(), key=lambda x: x[1]) if intent_dist else (None, 0)
            if dominant[1] > 0.6 * sum(intent_dist.values()):
                report += f"⚠️ **Intent skew detected** - {dominant[0]} dominates {dominant[1]/sum(intent_dist.values())*100:.1f}% of queries\n"
            
            report += """
---

**Report Generated by:** TomeHub Analytics System  
**Next Report:** Daily at 2 AM UTC
"""
            
            logger.info(f"✅ Report Generated ({len(report)} chars)")
            return report
        
        except Exception as e:
            logger.error(f"❌ Error generating report: {str(e)}")
            raise
    
    
    @task
    def notify_completion(report: str, **context) -> None:
        """
        Log completion of analytics run.
        
        In production, this could send Slack/email notifications.
        """
        log_date = context['ds']
        logger.info(f"""
╔════════════════════════════════════════════════════════════════╗
║  ✅ TomeHub Search Analytics Complete                          ║
╠════════════════════════════════════════════════════════════════╣
║  Date: {log_date}                                          ║
║  Runtime: {context.get('dag_run').duration if hasattr(context.get('dag_run'), 'duration') else 'N/A'} seconds                                      ║
║  Status: SUCCESS                                               ║
╠════════════════════════════════════════════════════════════════╣
║  Report Preview:                                               ║
╚════════════════════════════════════════════════════════════════╝
""")
        logger.info(report[:500] + "..." if len(report) > 500 else report)
    
    
    # Task dependencies
    extracted = extract_search_logs()
    intent_result = analyze_intent(extracted)
    strategy_result = analyze_strategy(extracted)
    perf_result = analyze_performance(extracted)
    report = generate_report(extracted, intent_result, strategy_result, perf_result)
    notify = notify_completion(report)
    
    # Dependency chain
    extracted >> [intent_result, strategy_result, perf_result] >> report >> notify


# Instantiate DAG
tomehub_analytics_dag = tomehub_search_analytics()
