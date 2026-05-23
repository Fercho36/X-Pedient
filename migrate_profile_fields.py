import sqlite3

def upgrade():
    conn = sqlite3.connect('instance/ece.db')
    c = conn.cursor()
    
    try:
        c.execute('ALTER TABLE user ADD COLUMN especialidad_principal VARCHAR(255)')
        print("Añadida columna especialidad_principal.")
    except sqlite3.OperationalError as e:
        print(f"Error o ya existe: {e}")
        
    try:
        c.execute('ALTER TABLE user ADD COLUMN telefono VARCHAR(50)')
        print("Añadida columna telefono.")
    except sqlite3.OperationalError as e:
        print(f"Error o ya existe: {e}")
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    upgrade()
