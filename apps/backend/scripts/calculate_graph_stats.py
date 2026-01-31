#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Graph Metrics Calculation Script
=================================
Calculates Betweenness Centrality for concepts in TOMEHUB_CONCEPTS.
This should be run as a nightly job or after significant graph updates.

Usage:
    python scripts/calculate_graph_stats.py
    
Output:
    Updates TOMEHUB_CONCEPTS.centrality_score column (adds if not exists).
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from infrastructure.db_manager import DatabaseManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ensure_centrality_column():
    """
    Ensure the CENTRALITY_SCORE column exists in TOMEHUB_CONCEPTS.
    """
    logger.info("Checking for CENTRALITY_SCORE column...")
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Check if column exists
                cursor.execute("""
                    SELECT column_name FROM user_tab_columns 
                    WHERE table_name = 'TOMEHUB_CONCEPTS' 
                    AND column_name = 'CENTRALITY_SCORE'
                """)
                
                if cursor.fetchone() is None:
                    logger.info("Adding CENTRALITY_SCORE column...")
                    cursor.execute("""
                        ALTER TABLE TOMEHUB_CONCEPTS 
                        ADD CENTRALITY_SCORE NUMBER DEFAULT 0
                    """)
                    conn.commit()
                    logger.info("Column added successfully.")
                else:
                    logger.info("Column already exists.")
                    
    except Exception as e:
        logger.error(f"Failed to ensure column: {e}")
        raise


def calculate_betweenness_centrality():
    """
    Calculate approximate betweenness centrality for all concepts.
    
    Uses a simplified approach:
    - Nodes that connect many other nodes have higher centrality
    - BC ≈ (in_degree × out_degree) / total_edges
    
    For true betweenness, we would need to run shortest path algorithms,
    which is expensive. This approximation is sufficient for discovery ranking.
    """
    logger.info("Calculating betweenness centrality (approximate)...")
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Get total edge count
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_RELATIONS")
                total_edges = cursor.fetchone()[0]
                
                if total_edges == 0:
                    logger.warning("No edges in graph. Skipping centrality calculation.")
                    return
                
                logger.info(f"Total edges in graph: {total_edges}")
                
                # Calculate degree-based centrality approximation
                # Score = (in_degree * out_degree) / total_edges
                # This captures "bridge" nodes that connect different clusters
                
                cursor.execute("""
                    UPDATE TOMEHUB_CONCEPTS c
                    SET centrality_score = (
                        SELECT 
                            COALESCE(
                                (in_deg.cnt * out_deg.cnt) / :total_edges,
                                0
                            )
                        FROM 
                            (SELECT COUNT(*) as cnt FROM TOMEHUB_RELATIONS WHERE dst_id = c.id) in_deg,
                            (SELECT COUNT(*) as cnt FROM TOMEHUB_RELATIONS WHERE src_id = c.id) out_deg
                    )
                """, {"total_edges": total_edges})
                
                updated = cursor.rowcount
                conn.commit()
                
                logger.info(f"Updated centrality for {updated} concepts.")
                
                # Log top 10 bridge nodes
                cursor.execute("""
                    SELECT name, centrality_score 
                    FROM TOMEHUB_CONCEPTS 
                    WHERE centrality_score > 0
                    ORDER BY centrality_score DESC
                    FETCH FIRST 10 ROWS ONLY
                """)
                
                top_nodes = cursor.fetchall()
                if top_nodes:
                    logger.info("Top 10 Bridge Nodes:")
                    for name, score in top_nodes:
                        logger.info(f"  - {name}: {score:.4f}")
                        
    except Exception as e:
        logger.error(f"Centrality calculation failed: {e}")
        import traceback
        traceback.print_exc()
        raise


def calculate_shared_neighbor_score():
    """
    Calculate shared neighbor score for concept pairs.
    
    This identifies concepts that share many neighbors (indicative of bridges).
    Stored in a separate table for efficient querying.
    """
    logger.info("Calculating shared neighbor scores...")
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Create table if not exists
                cursor.execute("""
                    BEGIN
                        EXECUTE IMMEDIATE '
                            CREATE TABLE TOMEHUB_CONCEPT_BRIDGES (
                                concept_a_id NUMBER,
                                concept_b_id NUMBER,
                                shared_neighbor_count NUMBER,
                                bridge_score NUMBER,
                                PRIMARY KEY (concept_a_id, concept_b_id)
                            )
                        ';
                    EXCEPTION
                        WHEN OTHERS THEN
                            IF SQLCODE != -955 THEN RAISE; END IF;
                    END;
                """)
                
                # Clear old data
                cursor.execute("DELETE FROM TOMEHUB_CONCEPT_BRIDGES")
                
                # Find concept pairs that share neighbors
                # (A -> X <- B means A and B share neighbor X)
                cursor.execute("""
                    INSERT INTO TOMEHUB_CONCEPT_BRIDGES (concept_a_id, concept_b_id, shared_neighbor_count, bridge_score)
                    SELECT 
                        r1.src_id as concept_a,
                        r2.src_id as concept_b,
                        COUNT(DISTINCT r1.dst_id) as shared_count,
                        COUNT(DISTINCT r1.dst_id) * 0.1 as bridge_score
                    FROM TOMEHUB_RELATIONS r1
                    JOIN TOMEHUB_RELATIONS r2 ON r1.dst_id = r2.dst_id
                    WHERE r1.src_id < r2.src_id
                    GROUP BY r1.src_id, r2.src_id
                    HAVING COUNT(DISTINCT r1.dst_id) >= 2
                """)
                
                inserted = cursor.rowcount
                conn.commit()
                
                logger.info(f"Found {inserted} concept bridge pairs.")
                
    except Exception as e:
        logger.error(f"Shared neighbor calculation failed: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point."""
    start_time = datetime.now()
    logger.info(f"=== Graph Metrics Calculation Started: {start_time} ===")
    
    try:
        ensure_centrality_column()
        calculate_betweenness_centrality()
        calculate_shared_neighbor_score()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"=== Completed in {duration:.2f} seconds ===")
        
    except Exception as e:
        logger.error(f"Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
