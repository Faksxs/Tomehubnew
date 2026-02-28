
import os
import re
import sys
import oracledb
from collections import Counter
from dotenv import load_dotenv

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
data_dir = os.path.join(backend_dir, 'data')
env_path = os.path.join(backend_dir, '.env')

load_dotenv(dotenv_path=env_path)

def get_database_connection():
    user = os.getenv("DB_USER", "ADMIN")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN")
    wallet_location = os.path.join(backend_dir, 'wallet')
    
    return oracledb.connect(
        user=user,
        password=password,
        dsn=dsn,
        config_dir=wallet_location,
        wallet_location=wallet_location,
        wallet_password=password
    )

def generate_dictionary():
    print("--- Generating Search Dictionary ---")
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        # Fetch normalized searchable text
        # This gives us a broad vocabulary of "searchable" forms
        print("Fetching content tokens...")
        sql = "SELECT normalized_content FROM TOMEHUB_CONTENT WHERE normalized_content IS NOT NULL"
        cursor.execute(sql)
        
        token_counter = Counter()
        row_count = 0
        
        # Simple regex for tokenization (alphanumeric only)
        # We assume normalized_content is already lowercased and cleanish
        tokenizer = re.compile(r'\w+') 
        
        while True:
            row = cursor.fetchone()
            if row is None:
                break
            
            text_clob = row[0]
            text = text_clob.read() if text_clob else ""
            
            # Find all words
            tokens = tokenizer.findall(text)
            
            # Filter tokens: len > 2 to avoid noise
            tokens = [t for t in tokens if len(t) > 2]
            
            token_counter.update(tokens)
            row_count += 1
            if row_count % 100 == 0:
                print(f"Processed {row_count} rows...")
        
        total_tokens = len(token_counter)
        print(f"Total unique tokens: {total_tokens}")
        
        # Write to dictionary.txt
        # Format: <term> <count>
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        dict_path = os.path.join(data_dir, 'dictionary.txt')
        
        print(f"Writing to {dict_path}...")
        with open(dict_path, 'w', encoding='utf-8') as f:
            for word, count in token_counter.most_common():
                f.write(f"{word} {count}\n")
                
        print("✅ Dictionary generation complete.")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    generate_dictionary()
