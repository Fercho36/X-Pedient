import sqlite3

conn = sqlite3.connect('instance/ece.db')
cur = conn.cursor()

def add_col(t, c, d):
    try:
        cur.execute(f"ALTER TABLE {t} ADD COLUMN {c} {d}")
        print(f"Added {c} to {t}")
    except Exception as e:
        print(f"Skip {c}: {e}")

add_col("patient", "folio", "VARCHAR(50) UNIQUE")
add_col("patient", "apellido_paterno", "VARCHAR(150)")
add_col("patient", "apellido_materno", "VARCHAR(150)")

add_col("consultation", "presion_arterial", "VARCHAR(50)")
add_col("consultation", "frecuencia_cardiaca", "VARCHAR(50)")
add_col("consultation", "frecuencia_respiratoria", "VARCHAR(50)")
add_col("consultation", "temperatura", "VARCHAR(50)")
add_col("consultation", "saturacion_oxigeno", "VARCHAR(50)")
add_col("consultation", "evaluacion_dolor", "VARCHAR(50)")
add_col("consultation", "resumen_clinico", "TEXT")

add_col("appointment", "paciente_telefono", "VARCHAR(20)")

try:
    cur.execute("""
    CREATE TABLE consultation_attachment (
        id INTEGER NOT NULL PRIMARY KEY,
        consultation_id INTEGER NOT NULL,
        filename VARCHAR(255) NOT NULL,
        original_name VARCHAR(255) NOT NULL,
        uploaded_at DATETIME,
        FOREIGN KEY(consultation_id) REFERENCES consultation (id)
    )
    """)
    print("Created consultation_attachment")
except Exception as e:
    print("Skip create consultation_attachment:", e)

conn.commit()
conn.close()
