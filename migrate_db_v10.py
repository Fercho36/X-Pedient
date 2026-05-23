import sqlite3
import os

DB_PATH = 'instance/ece.db'

def migrate_db():
    print(f"Migrating {DB_PATH}...")
    if not os.path.exists(DB_PATH):
        print("Database file not found!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Add session_timeout to user
        print("Adding session_timeout to user table...")
        cursor.execute("ALTER TABLE user ADD COLUMN session_timeout INTEGER DEFAULT 0")
        print("Success.")
    except sqlite3.OperationalError as e:
        print(f"Skipping session_timeout (might already exist): {e}")

    try:
        # Add altura to consultation
        print("Adding altura to consultation table...")
        cursor.execute("ALTER TABLE consultation ADD COLUMN altura VARCHAR(50)")
        print("Success.")
    except sqlite3.OperationalError as e:
        print(f"Skipping altura (might already exist): {e}")

    try:
        # Add imc to consultation
        print("Adding imc to consultation table...")
        cursor.execute("ALTER TABLE consultation ADD COLUMN imc VARCHAR(50)")
        print("Success.")
    except sqlite3.OperationalError as e:
        print(f"Skipping imc (might already exist): {e}")

    conn.commit()
    conn.close()
    print("Migration completed successfully.")

if __name__ == '__main__':
    migrate_db()
