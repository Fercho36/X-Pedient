import sqlite3

def upgrade():
    conn = sqlite3.connect('instance/ece.db')
    c = conn.cursor()
    try:
        c.execute('ALTER TABLE appointment ADD COLUMN recordatorio_enviado BOOLEAN DEFAULT 0')
        print("Añadida columna recordatorio_enviado a appointment.")
    except sqlite3.OperationalError as e:
        print(f"Error o ya existe: {e}")
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    upgrade()
