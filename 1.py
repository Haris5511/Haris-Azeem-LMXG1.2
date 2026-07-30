import json
import psycopg2
from email.utils import parsedate_to_datetime

# ==========================
# Database Configuration
# ==========================
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "Haris"
DB_USER = "new1"
DB_PASSWORD = "Haris"

JSON_FILE = "data/combined_news.json"

# ==========================
# Connect to PostgreSQL
# ==========================
conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)

cursor = conn.cursor()

print("Connected to PostgreSQL")

# ==========================
# Create Table
# ==========================
cursor.execute("""
CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    title TEXT,
    first_paragraph TEXT,
    url TEXT UNIQUE,
    published_time TIMESTAMP,
    category VARCHAR(100),
    source_name VARCHAR(255),
    source_url TEXT
);
""")

conn.commit()

print("Table ready")

# ==========================
# Load JSON
# ==========================
with open(JSON_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

articles = data["news_articles"]

print(f"Found {len(articles)} articles")

# ==========================
# Insert Query
# ==========================
query = """
INSERT INTO articles (
    title,
    first_paragraph,
    url,
    published_time,
    category,
    source_name,
    source_url
)
VALUES (%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (url) DO NOTHING;
"""

count = 0

for article in articles:

    published = article.get("published_time")

    # Convert
    if published:
        try:
            published = parsedate_to_datetime(published)
        except:
            published = None

    source = article.get("source", {})

    cursor.execute(
        query,
        (
            article.get("title"),
            article.get("first_paragraph"),
            article.get("url"),
            published,
            article.get("category"),
            source.get("name"),
            source.get("url"),
        ),
    )

    count += 1

conn.commit()

cursor.close()
conn.close()

print("=" * 40)
print(f"Inserted {count} articles successfully!")
print("=" * 40)