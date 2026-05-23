from app import db, app
from models import CustomTemplate

with app.app_context():
    templates_to_delete = [
        "Exploración Física Avanzada y Habitus Exterior",
        "Formato de Referencia y Contrarreferencia Médica",
        "Hoja de Indicaciones Médicas y Plan Terapéutico"
    ]
    deleted = db.session.query(CustomTemplate).filter(CustomTemplate.name.in_(templates_to_delete)).delete(synchronize_session=False)
    db.session.commit()
    print(f"Deleted {deleted} templates from the database.")
