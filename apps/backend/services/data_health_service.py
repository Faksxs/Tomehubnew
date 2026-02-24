
import logging
from typing import Dict, List, Any
from infrastructure.db_manager import DatabaseManager
from services.flow_service import safe_read_clob

logger = logging.getLogger("data_health_service")

class DataHealthService:
    """
    Centralized service for maintaining database integrity, quality, and hygiene.
    Acts as the 'Janitor' and 'Gatekeeper' for the system.
    """
    
    MIN_CONTENT_LENGTH = 12
    VALID_SOURCE_TYPES = ['PDF', 'EPUB', 'PDF_CHUNK', 'BOOK', 'HIGHLIGHT', 'INSIGHT', 'NOTES', 'ARTICLE', 'WEBSITE', 'PERSONAL_NOTE']

    @staticmethod
    def validate_content(text: str) -> bool:
        """
        Gatekeeper: Check if text is valid for ingestion.
        """
        if not text:
            return False
        if len(text.strip()) < DataHealthService.MIN_CONTENT_LENGTH:
            return False
        return True

    def audit_database(self) -> Dict[str, Any]:
        """
        Run a comprehensive health check on the database.
        """
        report = {
            "counts_by_type": {},
            "ghost_items": 0,
            "mislabelled_items": 0,
            "status": "HEALTHY"
        }
        
        DatabaseManager.init_pool()
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Counts
                cursor.execute("SELECT content_type, COUNT(*) FROM TOMEHUB_CONTENT_V2 GROUP BY content_type")
                for row in cursor.fetchall():
                    report["counts_by_type"][row[0]] = row[1]
                
                # 2. Ghost Items (Too short)
                cursor.execute(f"SELECT COUNT(*) FROM TOMEHUB_CONTENT_V2 WHERE DBMS_LOB.GETLENGTH(content_chunk) < {self.MIN_CONTENT_LENGTH} OR content_chunk IS NULL")
                report["ghost_items"] = cursor.fetchone()[0]
                
                # 3. Mislabelled Personal Notes
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT_V2 WHERE title LIKE '% - Self' AND content_type != 'PERSONAL_NOTE'")
                report["mislabelled_items"] = cursor.fetchone()[0]

        if report["ghost_items"] > 0 or report["mislabelled_items"] > 0:
            report["status"] = "ACTION_REQUIRED"
            
        return report

    def cleanup_database(self) -> Dict[str, int]:
        """
        Perform maintenance actions: delete ghosts, fix labels.
        """
        results = {"deleted_ghosts": 0, "fixed_labels": 0}
        
        DatabaseManager.init_pool()
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Delete Ghosts
                cursor.execute(f"DELETE FROM TOMEHUB_CONTENT_V2 WHERE DBMS_LOB.GETLENGTH(content_chunk) < {self.MIN_CONTENT_LENGTH} OR content_chunk IS NULL")
                results["deleted_ghosts"] = cursor.rowcount
                
                # 2. Fix Personal Note Labels
                cursor.execute("UPDATE TOMEHUB_CONTENT_V2 SET content_type = 'PERSONAL_NOTE' WHERE title LIKE '% - Self' AND content_type != 'PERSONAL_NOTE'")
                results["fixed_labels"] = cursor.rowcount
                
                conn.commit()
                
        return results
