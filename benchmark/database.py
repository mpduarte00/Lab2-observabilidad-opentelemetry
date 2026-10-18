import sqlite3

def get_connection():
    return sqlite3.connect("service_b.db")

def init_db():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL
        )
    """)

    connection.commit()
    connection.close()