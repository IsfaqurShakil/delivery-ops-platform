# scripts/check_db.py
# Quick check: can Python connect to our PostgreSQL database using the values in .env?
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()  # reads the .env file and puts its values into environment variables

conn = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)
with conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_user, current_database();")
        print(cur.fetchone())
conn.close()
print("Connection OK")
