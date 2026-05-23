import sqlite3

def upgrade_db():
    conn = sqlite3.connect('instance/ece.db')
    cur = conn.cursor()

    try:
        cur.execute("ALTER TABLE user ADD COLUMN firma_path VARCHAR(255)")
        print("Success: added firma_path to user table.")
    except Exception as e:
        print("Skip/Error adding firma_path:", e)

    conn.commit()
    conn.close()

if __name__ == '__main__':
    upgrade_db()
