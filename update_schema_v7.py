from app import app, db
from sqlalchemy import text

with app.app_context():
    # Aseguramos que las nuevas tablas se creen primero (ej. audit_log)
    db.create_all()
    print("Tablas verificadas/creadas por db.create_all()")
    
    # Agregar columnas si no existen
    try:
        db.session.execute(text('ALTER TABLE user ADD COLUMN totp_secret VARCHAR(32)'))
        print("Añadido totp_secret a user")
    except Exception as e:
        pass
        
    try:
        db.session.execute(text('ALTER TABLE consultation ADD COLUMN diagnostico VARCHAR(1000)'))
        print("Añadido diagnostico a consultation")
    except Exception as e:
        pass
        
    try:
        db.session.execute(text('ALTER TABLE consultation ADD COLUMN receta VARCHAR(2000)'))
        print("Añadido receta a consultation")
    except Exception as e:
        pass
        
    db.session.commit()
    print("Migración a V7 (Fase de Seguridad) completada con éxito.")
