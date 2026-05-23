import sqlite3

def upgrade():
    conn = sqlite3.connect('instance/ece.db')
    c = conn.cursor()
    
    try:
        c.execute('ALTER TABLE user ADD COLUMN sexo VARCHAR(20)')
        print("Añadida columna sexo.")
    except sqlite3.OperationalError as e:
        print(f"Error o ya existe: {e}")
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    upgrade()
