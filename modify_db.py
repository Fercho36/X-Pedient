import sqlite3

db_path = "instance/ece.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE appointment ADD COLUMN paciente_nombre VARCHAR(150)")
except Exception as e:
    print(f"Error adding paciente_nombre: {e}")

try:
    cur.execute("ALTER TABLE appointment ADD COLUMN paciente_email VARCHAR(150)")
except Exception as e:
    print(f"Error adding paciente_email: {e}")

conn.commit()
conn.close()
print("Database schema successfully altered.")
