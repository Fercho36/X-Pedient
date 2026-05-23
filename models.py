from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import os
import sqlalchemy.types as types
from cryptography.fernet import Fernet

db = SQLAlchemy()

class EncryptedString(types.TypeDecorator):
    """Transparently encrypts and decrypts strings using Fernet."""
    impl = types.String
    cache_ok = True

    def __init__(self, *args, **kwargs):
         super(EncryptedString, self).__init__(*args, **kwargs)

    def process_bind_param(self, value, dialect):
        if value is not None:
             key = os.getenv('FERNET_KEY')
             if key:
                 f = Fernet(key.encode('utf-8'))
                 return f.encrypt(value.encode('utf-8')).decode('utf-8')
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
             key = os.getenv('FERNET_KEY')
             if key:
                 f = Fernet(key.encode('utf-8'))
                 try:
                     return f.decrypt(value.encode('utf-8')).decode('utf-8')
                 except Exception:
                     return value # In case of raw data mapping backwards
        return value

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    sexo = db.Column(db.String(20), nullable=True) # Masculino o Femenino
    cedula_profesional = db.Column(db.String(50), nullable=True) # Required for specific templates (Recetas)
    especialidad_principal = db.Column(db.String(255), nullable=True)
    telefono = db.Column(db.String(50), nullable=True)
    direccion_consultorio = db.Column(db.String(255), nullable=True) # Address of the clinic/consultation room
    is_verified = db.Column(db.Boolean, default=False) # True if cedula is validated
    firma_path = db.Column(db.String(255), nullable=True) # For signature image uploads
    totp_secret = db.Column(db.String(32), nullable=True)
    session_timeout = db.Column(db.Integer, default=0) # 0 = until browser closes
    
class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    hora = db.Column(db.Time, default=lambda: datetime.utcnow().time())
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    accion_realizada = db.Column(db.String(255), nullable=False)
    direccion_ip = db.Column(db.String(50), nullable=True)
    

class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    folio = db.Column(db.String(50), nullable=True, unique=True)
    nombre = db.Column(db.String(150), nullable=False)
    apellido_paterno = db.Column(db.String(150), nullable=True)
    apellido_materno = db.Column(db.String(150), nullable=True)
    edad = db.Column(db.Integer, nullable=False)
    peso = db.Column(db.Float, nullable=False)
    genero = db.Column(db.String(20), nullable=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    consultations = db.relationship('Consultation', backref='patient', lazy=True)

class Consultation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    constantes_vitales = db.Column(db.String(250), nullable=True) # deprecated
    presion_arterial = db.Column(db.String(50), nullable=True)
    frecuencia_cardiaca = db.Column(db.String(50), nullable=True)
    frecuencia_respiratoria = db.Column(db.String(50), nullable=True)
    temperatura = db.Column(db.String(50), nullable=True)
    saturacion_oxigeno = db.Column(db.String(50), nullable=True)
    altura = db.Column(db.String(50), nullable=True)
    imc = db.Column(db.String(50), nullable=True)
    evaluacion_dolor = db.Column(db.String(50), nullable=True)
    motivo = db.Column(EncryptedString(500), nullable=False)
    resumen_clinico = db.Column(EncryptedString(2000), nullable=True)
    diagnostico = db.Column(EncryptedString(1000), nullable=True)
    receta = db.Column(EncryptedString(2000), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    attachments = db.relationship('ConsultationAttachment', backref='consultation', lazy=True, cascade="all, delete-orphan")
    
class ConsultationAttachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey('consultation.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=False)
    fecha_hora = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notas = db.Column(db.Text, nullable=True)
    paciente_nombre = db.Column(db.String(150), nullable=True)
    paciente_email = db.Column(db.String(150), nullable=True)
    paciente_telefono = db.Column(db.String(20), nullable=True)
    recordatorio_enviado = db.Column(db.Boolean, default=False)

class CustomTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    fields_schema = db.Column(db.Text, nullable=False) # JSON schema
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    patient_name = db.Column(db.String(150), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    data_json = db.Column(db.Text, nullable=False) # Store blocks data
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    attachments = db.relationship('Attachment', backref='record', lazy=True, cascade="all, delete-orphan")

class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('record.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class RemoteCareLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    consultation_id = db.Column(db.Integer, db.ForeignKey('consultation.id'), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    consultation = db.relationship('Consultation', backref=db.backref('remote_care_link', uselist=False, cascade="all, delete-orphan"))

class RemoteMeasurement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey('consultation.id'), nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    presion_arterial = db.Column(db.String(50), nullable=True)
    glucosa = db.Column(db.String(50), nullable=True)
    oxigeno_sangre = db.Column(db.String(50), nullable=True)
    frecuencia_cardiaca = db.Column(db.String(50), nullable=True)
    peso_actual = db.Column(db.String(50), nullable=True)
    notas_paciente = db.Column(db.Text, nullable=True)
    
    consultation = db.relationship('Consultation', backref=db.backref('remote_measurements', lazy=True, cascade="all, delete-orphan"))
