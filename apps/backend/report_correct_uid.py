import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from infrastructure.db_manager import DatabaseManager

CORRECT_UID = "vpq1p0UzcCSLAh1d18WgZZWPBE63"

def full_report():
    lines = []
    lines.append("=" * 70)
    lines.append(f"FULL DB REPORT - UID: {CORRECT_UID}")
    lines.append("=" * 70)

    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                lines.append("\n--- ORACLE: TOMEHUB_BOOKS ---")
                cursor.execute(
                    "SELECT id, title, author FROM TOMEHUB_BOOKS WHERE firebase_uid = :p_uid AND (title LIKE '%Klasik%' OR title LIKE '%Sosyoloji%')",
                    {"p_uid": CORRECT_UID}
                )
                oracle_books = cursor.fetchall()
                for b in oracle_books:
                    lines.append(f"  ID: {b[0]} | Title: {b[1]} | Author: {b[2]}")
                if not oracle_books:
                    lines.append("  No records found.")

                lines.append("\n--- ORACLE: TOMEHUB_CONTENT ---")
                cursor.execute(
                    "SELECT book_id, title, count(*), sum(case when vec_embedding is not null then 1 else 0 end) FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid AND (title LIKE '%Klasik%' OR title LIKE '%Sosyoloji%') GROUP BY book_id, title",
                    {"p_uid": CORRECT_UID}
                )
                oracle_content = cursor.fetchall()
                for c in oracle_content:
                    lines.append(f"  BookID: {c[0]} | Title: {c[1]} | Chunks: {c[2]} | Embeds: {c[3]}")
                if not oracle_content:
                    lines.append("  No records found.")

                lines.append("\n--- ORACLE: TOMEHUB_INGESTED_FILES ---")
                cursor.execute(
                    "SELECT book_id, source_file_name, status, chunk_count, embedding_count, updated_at FROM TOMEHUB_INGESTED_FILES WHERE firebase_uid = :p_uid AND (source_file_name LIKE '%Klasik%' OR source_file_name LIKE '%Sosyoloji%')",
                    {"p_uid": CORRECT_UID}
                )
                oracle_files = cursor.fetchall()
                for f in oracle_files:
                    lines.append(f"  BookID: {f[0]} | File: {f[1]} | Status: {f[2]} | Chunks: {f[3]} | Embeds: {f[4]} | Updated: {f[5]}")
                if not oracle_files:
                    lines.append("  No records found.")
    finally:
        DatabaseManager.close_pool()

    lines.append("\n--- FIRESTORE: users/{uid}/items ---")
    if not settings.FIREBASE_READY:
        lines.append("  Firebase Admin SDK not ready.")
    else:
        from firebase_admin import firestore
        fdb = firestore.client()
        docs = fdb.collection("users").document(CORRECT_UID).collection("items").stream()
        found = False
        for doc in docs:
            data = doc.to_dict()
            title = (data.get("title") or "").lower()
            if "klasik" in title or "sosyoloji" in title:
                lines.append(f"  ID: {doc.id} | Title: {data.get('title')} | Author: {data.get('author')} | Type: {data.get('type')}")
                hl_count = len(data.get("highlights", []))
                lines.append(f"    Highlights: {hl_count}")
                found = True
        if not found:
            lines.append("  No matching items found in Firestore.")

    # Write to file
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "klasik_report.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report written to: {output_path}")

if __name__ == "__main__":
    full_report()
