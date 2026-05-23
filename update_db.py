from app import app, db

with app.app_context():
    # Esto creará las tablas RemoteCareLink y RemoteMeasurement si no existen.
    db.create_all()
    print("Base de datos actualizada con los nuevos modelos.")
