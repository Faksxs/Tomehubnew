
import sys
import os
import oracledb
import re

# Add apps/backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.getcwd(), 'apps', 'backend', '.env'))

from infrastructure.db_manager import DatabaseManager

def profile_sql(name, sql, params=None):
    print(f"\n{'='*70}")
    print(f"PROFILING: {name}")
    print(f"{'='*70}")
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Explain Plan
                # We use a randomized ID to avoid plan table collisions if multiple people run this
                cursor.execute(f"EXPLAIN PLAN FOR {sql}", params or {})
                
                # 2. Fetch Plan
                cursor.execute("SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY())")
                for row in cursor.fetchall():
                    print(row[0])
    except Exception as e:
        print(f"Error profiling {name}: {e}")

def check_indexes():
    print(f"\n{'='*70}")
    print("EXISTING INDEXES")
    print(f"{'='*70}")
    
    sql = """
    SELECT table_name, index_name, column_name, column_position
    FROM user_ind_columns
    WHERE table_name IN ('TOMEHUB_CONTENT', 'TOMEHUB_CONCEPTS', 'TOMEHUB_RELATIONS', 'TOMEHUB_CONCEPT_CHUNKS')
    ORDER BY table_name, index_name, column_position
    """
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                if not rows:
                    print("No indexes found for target tables.")
                for row in rows:
                    print(f"Table: {row[0]:20} Index: {row[1]:25} Column: {row[2]}")
    except Exception as e:
        print(f"Error checking indexes: {e}")

if __name__ == "__main__":
    try:
        DatabaseManager.init_pool()
        
        check_indexes()
        
        # 1. Vector Search (Main Content)
        vector_sql = """
        SELECT content_chunk, page_number, title, source_type,
               VECTOR_DISTANCE(vec_embedding, :p_vec, COSINE) as dist
        FROM TOMEHUB_CONTENT
        WHERE firebase_uid = :p_uid
        ORDER BY dist
        FETCH FIRST 20 ROWS ONLY
        """
        # Note: 1024 is the standard vector size used in TomeHub (Gemini)
        dummy_vec = [0.1] * 1024 
        profile_sql("Vector Search (TOMEHUB_CONTENT)", vector_sql, {"p_vec": dummy_vec, "p_uid": "dummy_uid"})
        
        # 2. Graph Traversal (The Big Join)
        graph_sql = """
        SELECT DISTINCT 
            ct.content_chunk, ct.page_number, ct.title, ct.source_type,
            c_neighbor.name as related_concept,
            r.rel_type,
            r.weight
        FROM TOMEHUB_RELATIONS r
        JOIN TOMEHUB_CONCEPTS c_neighbor ON (r.dst_id = c_neighbor.id OR r.src_id = c_neighbor.id)
        JOIN TOMEHUB_CONCEPT_CHUNKS cc ON c_neighbor.id = cc.concept_id
        JOIN TOMEHUB_CONTENT ct ON cc.content_id = ct.id
        WHERE (r.src_id IN (1, 2, 3) OR r.dst_id IN (1, 2, 3))
        AND ct.firebase_uid = 'dummy_uid'
        FETCH FIRST 15 ROWS ONLY
        """
        profile_sql("Graph Traversal Query", graph_sql)
        
        # 3. Concept Lookup (Fuzzy)
        concept_lookup = """
        SELECT id FROM TOMEHUB_CONCEPTS 
        WHERE LOWER(name) LIKE :term
        FETCH FIRST 5 ROWS ONLY
        """
        profile_sql("Concept Lookup (LOWER + LIKE)", concept_lookup, {"term": "%test%"})

        DatabaseManager.close_pool()
    except Exception as e:
        print(f"Fatal error: {e}")
