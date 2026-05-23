import json
from app import app, db
from models import CustomTemplate, User

def seed_templates():
    with app.app_context():
        # 1. Ensure a SYSTEM_TEMPLATES user exists to own these global templates
        system_user = User.query.filter_by(username="SYSTEM_TEMPLATES").first()
        if not system_user:
            system_user = User(
                username="SYSTEM_TEMPLATES",
                email="system@xpedient.com",
                password="NO_LOGIN_ALLOWED"
            )
            db.session.add(system_user)
            db.session.commit()
            print("[INFO] Usuario del sistema creado.")

        templates_data = [
            {
                "name": "Hoja de Indicaciones Médicas y Plan Terapéutico",
                "description": "Formato estandarizado para el registro de dosis, dietas, cuidados generales e instrucciones de tratamiento para el paciente.",
                "fields_schema": [
                    {"label": "Dieta y Régimen Nutricional", "type": "textarea"},
                    {"label": "Medidas Generales y Cuidados de Enfermería", "type": "textarea"},
                    {"label": "Soluciones Parenterales (si aplica)", "type": "text"},
                    {"label": "Medicamentos (Nombre, Dosis, Vía y Frecuencia)", "type": "textarea"},
                    {"label": "Signos de Alarma explicados al paciente", "type": "textarea"},
                    {"label": "Fecha de Próxima Valoración", "type": "text"}
                ]
            },
            {
                "name": "Formato de Referencia y Contrarreferencia Médica",
                "description": "Formato institucional para el traslado formal e interconsulta de pacientes entre unidades médicas o especialistas.",
                "fields_schema": [
                    {"label": "Establecimiento / Unidad Médica de Origen", "type": "text"},
                    {"label": "Servicio / Especialidad que Refiere", "type": "text"},
                    {"label": "Establecimiento / Especialidad a la que se Envía", "type": "text"},
                    {"label": "Motivo de la Referencia (Interconsulta, Hospitalización, Auxiliar de diagnóstico)", "type": "text"},
                    {"label": "Resumen Clínico (Padecimiento actual y Evolución)", "type": "textarea"},
                    {"label": "Impresión Diagnóstica / Diagnóstico Probable", "type": "textarea"},
                    {"label": "Estudios de Laboratorio y Gabinete Anexados", "type": "textarea"},
                    {"label": "Tratamiento o Recomendaciones Iniciales para el Manejo", "type": "textarea"},
                    {"label": "Pronóstico Clínico", "type": "text"}
                ]
            },
            {
                "name": "Exploración Física Avanzada y Habitus Exterior",
                "description": "Examen clínico estructurado por segmentos corporales y somatometría detallada del paciente.",
                "fields_schema": [
                    {"label": "Habitus Exterior (Inspección general: edad aparente, alerta, marcha, facies, actitud)", "type": "textarea"},
                    {"label": "Frecuencia Cardíaca (FC - lpm)", "type": "number"},
                    {"label": "Frecuencia Respiratoria (FR - rpm)", "type": "number"},
                    {"label": "Temperatura Corporal (°C)", "type": "number"},
                    {"label": "Presión Arterial (TA - mm Hg)", "type": "text"},
                    {"label": "Exploración de Cabeza (Cráneo, Cara, Ojos, Oídos, Nariz, Boca)", "type": "textarea"},
                    {"label": "Exploración de Cuello", "type": "textarea"},
                    {"label": "Exploración de Tórax y Región Precordial (Campos pulmonares y ruidos cardíacos)", "type": "textarea"},
                    {"label": "Exploración de Abdomen (Inspección, auscultación, palpación, percusión)", "type": "textarea"},
                    {"label": "Exploración de Extremidades (Simetría, pulsos, reflejos, movilidad)", "type": "textarea"},
                    {"label": "Exploración Neurológica / Estado Mental", "type": "textarea"}
                ]
            }
        ]

        # 2. Inject templates
        for t_data in templates_data:
            existing = CustomTemplate.query.filter_by(name=t_data["name"]).first()
            if not existing:
                new_template = CustomTemplate(
                    user_id=system_user.id,
                    name=t_data["name"],
                    description=t_data["description"],
                    fields_schema=json.dumps(t_data["fields_schema"], ensure_ascii=False)
                )
                db.session.add(new_template)
                print(f"[SUCCESS] Plantilla insertada: {t_data['name']}")
            else:
                print(f"[SKIP] Plantilla ya existe: {t_data['name']}")

        db.session.commit()
        print("\n[INFO] Inicialización de plantillas del sistema completada exitosamente.")

if __name__ == "__main__":
    seed_templates()
