import sqlite3

def upgrade_db():
    conn = sqlite3.connect('instance/ece.db')
    cur = conn.cursor()

    try:
        cur.execute("ALTER TABLE consultation ADD COLUMN user_id INTEGER REFERENCES user(id)")
        # Update existing consultations to a default user constraint (user 1 if exists, or just null)
        # Assuming the currently active user has id=1 since it's a test environment.
        cur.execute("UPDATE consultation SET user_id = 1 WHERE user_id IS NULL")
        print("Success: added user_id to consultation table and assigned old data to user 1.")
    except Exception as e:
        print("Error or already added:", e)

    conn.commit()
    conn.close()

if __name__ == '__main__':
    upgrade_db()
