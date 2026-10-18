
import sqlite3
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent / "service_b.db"


def get_connection():
    return sqlite3.connect(str(DATABASE_PATH))


def init_db():
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL
            )
        """)

        connection.commit()
    finally:
        connection.close()
