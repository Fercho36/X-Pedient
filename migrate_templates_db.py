import sqlite3

def upgrade():
    conn = sqlite3.connect('ece.db')
    cursor = conn.cursor()
    
    try:
        # Create CustomTemplate table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_template (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name VARCHAR(150) NOT NULL,
                description VARCHAR(255),
                fields_schema TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user(id)
            )
        ''')
        print("Tabla 'custom_template' creada con éxito.")
        
        conn.commit()
    except Exception as e:
        print("Error durante la migración:", e)
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    upgrade()
