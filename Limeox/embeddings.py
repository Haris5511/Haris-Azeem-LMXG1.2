"""
Sentence-Transformer Embeddings -> PostgreSQL
===============================================
Ye script preprocessed_articles.json ko load karti hai, har article ke liye
sentence-transformer embedding generate karti hai, aur PostgreSQL database
me save kar deti hai.

Embeddings 'clean_title' + 'clean_first_paragraph' (preprocessed/stemmed
text) pe banai ja rahi hain. Table me readability ke liye original
title/first_paragraph bhi save hote hain (display ke liye).

Installation (ek dafa terminal me chalayein):
    pip install sentence-transformers psycopg2-binary numpy

Usage:
    python generate_embeddings_and_save.py
"""

import json
import os
import numpy as np
from sentence_transformers import SentenceTransformer
import psycopg2
from psycopg2.extras import execute_values

# -------------------------------------------------------------------
# 1. CONFIGURATION -- apni values yahan fill karein
# -------------------------------------------------------------------
DB_CONFIG = {
    "host": "localhost",       # <-- apna DB host
    "port": 5432,               # <-- apna DB port
    "dbname": "Haris",  # <-- apna database naam
    "user": "new1",    # <-- apna username
    "password": "Haris" # <-- apna password
}

TABLE_NAME = "article_embeddings"
MODEL_NAME = "all-MiniLM-L6-v2"   # 384-dimension, chota aur fast model


# -------------------------------------------------------------------
# 2. LOAD PREPROCESSED DATA
# -------------------------------------------------------------------
def load_articles():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, "preprocessed_articles.json")

    if not os.path.exists(input_path):
        raise FileNotFoundError(
            f"'{input_path}' nahi mili. Is script ko preprocessed_articles.json "
            f"ke sath usi folder me rakhein."
        )

    with open(input_path, "r", encoding="utf-8") as f:
        return json.load(f)


# -------------------------------------------------------------------
# 3. GENERATE EMBEDDINGS
# -------------------------------------------------------------------
def generate_embeddings(articles, model):
    # Cleaned/preprocessed text combine kar rahe hain — title + paragraph
    texts = [
        f"{a.get('clean_title', '')} {a.get('clean_first_paragraph', '')}".strip()
        for a in articles
    ]

    print(f"Generating embeddings for {len(texts)} articles...")
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        convert_to_numpy=True
    )
    return embeddings


# -------------------------------------------------------------------
# 4. POSTGRESQL: TABLE CREATE + INSERT
# -------------------------------------------------------------------
def create_table(cur, embedding_dim):
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id SERIAL PRIMARY KEY,
            source TEXT,
            url TEXT UNIQUE,
            published_date_new_york TEXT,
            title TEXT,
            first_paragraph TEXT,
            embedding FLOAT4[{embedding_dim}],
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)


def insert_records(cur, articles, embeddings):
    rows = []
    for art, emb in zip(articles, embeddings):
        rows.append((
            art.get("source", ""),
            art.get("url", ""),
            art.get("published_date_new_york", ""),
            art.get("original_title", ""),
            art.get("original_first_paragraph", ""),
            emb.tolist(),  # numpy array -> python list for insertion
        ))

    query = f"""
        INSERT INTO {TABLE_NAME}
            (source, url, published_date_new_york, title, first_paragraph, embedding)
        VALUES %s
        ON CONFLICT (url) DO UPDATE SET
            embedding = EXCLUDED.embedding,
            title = EXCLUDED.title,
            first_paragraph = EXCLUDED.first_paragraph;
    """
    execute_values(cur, query, rows)


# -------------------------------------------------------------------
# 5. MAIN PIPELINE
# -------------------------------------------------------------------
def main():
    articles = load_articles()
    print(f"Loaded {len(articles)} articles.")

    # Load model (pehli baar internet se download hoga, phir cache ho jayega)
    print(f"Loading model: {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)

    embeddings = generate_embeddings(articles, model)
    embedding_dim = embeddings.shape[1]
    print(f"Embeddings shape: {embeddings.shape}")

    # Connect to PostgreSQL
    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        create_table(cur, embedding_dim)
        insert_records(cur, articles, embeddings)
        conn.commit()
        print(f"Saved {len(articles)} embeddings to table '{TABLE_NAME}'.")
    except Exception as e:
        conn.rollback()
        print("Error occurred, rolled back:", e)
        raise
    finally:
        cur.close()
        conn.close()

    # Optional: embeddings ko local file me bhi save kar dete hain (backup)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    np.save(os.path.join(script_dir, "embeddings.npy"), embeddings)
    print("Backup embeddings.npy bhi save ho gayi.")


if __name__ == "__main__":
    main()