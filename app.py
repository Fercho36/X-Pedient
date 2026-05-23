from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import requests
import json
import werkzeug.utils
import time
import os
import shutil
import uuid
import smtplib
from email.message import EmailMessage
from apscheduler.schedulers.background import BackgroundScheduler
import pyotp
import qrcode
import io
from base64 import b64encode
import secrets
from itsdangerous import URLSafeTimedSerializer

from models import db, User, Patient, Consultation, Appointment, Record, Attachment, AuditLog, RemoteCareLink, RemoteMeasurement, CustomTemplate, PasswordResetToken, ConsultationAttachment
from utils import generate_consultation_pdf

load_dotenv()

app = Flask(__name__)
scheduler = BackgroundScheduler()
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler.start()

app.config['SECRET_KEY'] = 'ece_super_secret_mvp_key_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ece.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

def log_action(doctor_id, action):
    if doctor_id:
        ip = request.remote_addr
        new_log = AuditLog(doctor_id=doctor_id, accion_realizada=action, direccion_ip=ip)
        db.session.add(new_log)
        db.session.commit()

@app.before_request
def before_request():
    if current_user.is_authenticated and current_user.session_timeout > 0:
        session.permanent = True
        app.permanent_session_lifetime = timedelta(minutes=current_user.session_timeout)
    elif current_user.is_authenticated and current_user.session_timeout == 0:
        session.permanent = False
    else:
        session.permanent = True
        app.permanent_session_lifetime = timedelta(minutes=15)
    
    # 2FA Check
    allowed_endpoints = ['login', 'register', 'logout', 'static', 'setup_2fa', 'verify_2fa', 'forgot_password', 'reset_password_route']
    if current_user.is_authenticated and request.endpoint and request.endpoint not in allowed_endpoints:
        if not session.get('2fa_verified'):
            if not current_user.totp_secret:
                return redirect(url_for('setup_2fa'))
            return redirect(url_for('verify_2fa'))

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, inicia sesión para acceder a esta página."
login_manager.login_message_category = "info"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def send_appointment_reminder(patient_name, patient_email, doctor_name, doctor_email, date_str, appt_id=None, doctor_sexo=None):
    with app.app_context():
        if appt_id:
            from models import Appointment
            appt = Appointment.query.get(appt_id)
            if appt and appt.recordatorio_enviado:
                print(f"[DEBUG] Recordatorio ya fue enviado previamente para cita {appt_id}")
                return

    sender_email = "cuentaparainnova@gmail.com"
    sender_password = os.getenv('GMAIL_APP_PASSWORD', '') # Se requiere configurar en .env
    
    print(f"[DEBUG] Ejecutando tarea de correo para la cita a las {date_str} de {patient_name}...", flush=True)
    
    titulo_dr = "la Dra." if doctor_sexo == 'Femenino' else "el Dr."
    msg_text = f"Recordatorio: Tienes una cita médica programada para mañana a las {date_str} con {titulo_dr} {doctor_name}."
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f5; padding: 20px; text-align: center;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h2 style="color: #0284c7; margin-bottom: 20px;">Recordatorio de Cita Médica</h2>
            <p style="color: #475569; font-size: 16px;">Hola <strong>{patient_name}</strong>,</p>
            <p style="color: #475569; font-size: 16px;">Este es un recordatorio de tu cita médica programada para mañana con {titulo_dr} {doctor_name}.</p>
            <div style="background-color: #f0f9ff; border: 2px dashed #38bdf8; padding: 15px; font-size: 24px; font-weight: bold; color: #0369a1; letter-spacing: 2px; margin: 25px 0;">
                {date_str}
            </div>
            <p style="color: #64748b; font-size: 14px;">Por favor, procura llegar con unos minutos de anticipación.</p>
            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 25px 0;">
            <p style="color: #94a3b8; font-size: 12px;">X-PEDIENT - Plataforma de Expediente Clínico Electrónico</p>
        </div>
    </body>
    </html>
    """
    
    targets = [patient_email, doctor_email]
    
    for target in targets:
        if target:
            msg = EmailMessage()
            msg.set_content(msg_text)
            msg.add_alternative(html_content, subtype='html')
            msg['Subject'] = 'Recordatorio de Cita Médica - X-PEDIENT'
            msg['From'] = f"X-PEDIENT <{sender_email}>"
            msg['To'] = target
            
            try:
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                if sender_password:
                    server.login(sender_email, sender_password)
                    server.send_message(msg)
                    print(f"[SUCCESS] Email enviado a {target}")
                else:
                    print(f"[WARNING] No GMAIL_APP_PASSWORD for {target}")
                server.quit()
            except Exception as e:
                print(f"[FAILED] Error enviando a {target}: {e}")

    with app.app_context():
        if appt_id:
            from models import Appointment
            appt = Appointment.query.get(appt_id)
            if appt:
                appt.recordatorio_enviado = True
                db.session.commit()

# ================= PUBLIC ROUTES =================
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            log_action(user.id, "Login exitoso")
            return redirect(url_for('dashboard'))
        else:
            if user:
                log_action(user.id, "Intento fallido de Login")
            flash('Credenciales incorrectas. Intenta de nuevo.', 'error')
            
    return render_template('auth.html', form_type='login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        cedula = request.form.get('cedula', '')
        
        if User.query.filter_by(email=email).first():
            flash('El email ya está registrado.', 'error')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password)
        # Check if the cedula looks somewhat valid (basic length check for MVP)
        is_verified = len(cedula.strip()) > 5
        
        new_user = User(
            username=username, 
            email=email, 
            password=hashed_password,
            cedula_profesional=cedula.strip() if is_verified else None,
            is_verified=is_verified
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Cuenta creada correctamente. Por favor inicia sesión.', 'success')
        return redirect(url_for('login'))
        
    return render_template('auth.html', form_type='register')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('2fa_verified', None)
    return redirect(url_for('index'))

@app.route('/setup_2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    if current_user.totp_secret:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        secret = session.get('temp_totp_secret')
        token = request.form.get('token')
        totp = pyotp.TOTP(secret)
        if totp.verify(token):
            current_user.totp_secret = secret
            db.session.commit()
            session['2fa_verified'] = True
            log_action(current_user.id, "Configuró 2FA")
            flash('2FA configurado exitosamente.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Código inválido. Inténtalo de nuevo.', 'error')
            
    secret = pyotp.random_base32()
    session['temp_totp_secret'] = secret
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=current_user.email, issuer_name='X-Pedient')
    
    img = qrcode.make(totp_uri)
    buf = io.BytesIO()
    img.save(buf)
    qr_b64 = b64encode(buf.getvalue()).decode('utf-8')
    
    return render_template('2fa.html', mode='setup', qr_b64=qr_b64, secret=secret)
    
@app.route('/verify_2fa', methods=['GET', 'POST'])
@login_required
def verify_2fa():
    if session.get('2fa_verified'):
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        token = request.form.get('token')
        totp = pyotp.TOTP(current_user.totp_secret)
        if totp.verify(token):
            session['2fa_verified'] = True
            return redirect(url_for('dashboard'))
        else:
            flash('Código OTP inválido o expirado.', 'error')
            
    return render_template('2fa.html', mode='verify')

def send_recovery_email(to_email, code):
    sender = "cuentaparainnova@gmail.com"
    password = os.getenv('GMAIL_APP_PASSWORD')
    if not password:
        print("[EMAIL ERROR] No GMAIL_APP_PASSWORD found in .env")
        return False
        
    msg = EmailMessage()
    msg['Subject'] = 'Código de Recuperación de Contraseña - X-PEDIENT'
    msg['From'] = f"X-PEDIENT <{sender}>"
    msg['To'] = to_email
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f5; padding: 20px; text-align: center;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h2 style="color: #0284c7; margin-bottom: 20px;">Recuperación de Contraseña</h2>
            <p style="color: #475569; font-size: 16px;">Has solicitado restablecer tu contraseña. Utiliza el siguiente código PIN de 6 dígitos para continuar con el proceso:</p>
            <div style="background-color: #f0f9ff; border: 2px dashed #38bdf8; padding: 15px; font-size: 28px; font-weight: bold; color: #0369a1; letter-spacing: 5px; margin: 25px 0;">
                {code}
            </div>
            <p style="color: #64748b; font-size: 14px;">Este código expirará en 15 minutos.</p>
            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 25px 0;">
            <p style="color: #94a3b8; font-size: 12px;">Si no solicitaste este código, puedes ignorar este correo de forma segura.</p>
        </div>
    </body>
    </html>
    """
    msg.add_alternative(html_content, subtype='html')
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send email to {to_email}: {e}")
        return False

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            # Generate 6-digit code
            code = str(secrets.randbelow(1000000)).zfill(6)
            
            # Save or update token
            token = PasswordResetToken.query.filter_by(user_id=user.id).first()
            if not token:
                token = PasswordResetToken(user_id=user.id)
                db.session.add(token)
            
            token.code = code
            token.expires_at = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
            
            # Send Email
            success = send_recovery_email(user.email, code)
            if success:
                session['reset_email'] = user.email
                flash('Se ha enviado un código de 6 dígitos a tu correo.', 'info')
                return redirect(url_for('verify_reset_code'))
            else:
                flash('Ocurrió un error enviando el correo. Contacta soporte.', 'error')
                return redirect(url_for('forgot_password'))
        else:
            flash('Si el correo existe, se ha enviado un código.', 'info')
            return redirect(url_for('login'))
            
    return render_template('reset_password.html', mode='forgot')

@app.route('/verify_reset_code', methods=['GET', 'POST'])
def verify_reset_code():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    email = session.get('reset_email')
    if not email:
        return redirect(url_for('forgot_password'))
        
    if request.method == 'POST':
        code = request.form.get('code')
        user = User.query.filter_by(email=email).first()
        if user:
            token = PasswordResetToken.query.filter_by(user_id=user.id, code=code).first()
            if token and token.expires_at > datetime.utcnow():
                # Correct code
                session['reset_code_verified'] = True
                return redirect(url_for('reset_password_route'))
            else:
                flash('El código es incorrecto o ha expirado.', 'error')
        
    return render_template('reset_password.html', mode='verify')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password_route():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    email = session.get('reset_email')
    if not email or not session.get('reset_code_verified'):
        return redirect(url_for('forgot_password'))
        
    if request.method == 'POST':
        new_password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_password)
            
            # Clean up token
            token = PasswordResetToken.query.filter_by(user_id=user.id).first()
            if token:
                db.session.delete(token)
                
            db.session.commit()
            log_action(user.id, "Recuperación de contraseña exitosa")
            
            # Clean session
            session.pop('reset_email', None)
            session.pop('reset_code_verified', None)
            
            flash('Tu contraseña ha sido actualizada. Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
            
    return render_template('reset_password.html', mode='reset')

# ================= PRIVATE ROUTES =================
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile_view():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user_exists = User.query.filter(User.email == email, User.id != current_user.id).first()
        if user_exists:
            flash('Ese email ya está en uso.', 'error')
        else:
            current_user.email = email
            
            direccion = request.form.get('direccion_consultorio')
            if direccion is not None:
                current_user.direccion_consultorio = direccion

            especialidad = request.form.get('especialidad_principal')
            if especialidad is not None:
                current_user.especialidad_principal = especialidad

            telefono = request.form.get('telefono')
            if telefono is not None:
                current_user.telefono = telefono

            sexo = request.form.get('sexo')
            if sexo is not None:
                current_user.sexo = sexo

            if password:
                current_user.password = generate_password_hash(password)
                
            timeout = request.form.get('session_timeout')
            if timeout is not None:
                current_user.session_timeout = int(timeout)
                
            if 'firma' in request.files:
                file = request.files['firma']
                if file.filename != '':
                    firma_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'signatures')
                    os.makedirs(firma_dir, exist_ok=True)
                    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'png'
                    fname = f"firma_{current_user.id}_{int(datetime.utcnow().timestamp())}.{ext}"
                    f_path = os.path.join(firma_dir, fname)
                    file.save(f_path)
                    current_user.firma_path = os.path.join('signatures', fname).replace('\\', '/')
                    
            db.session.commit()
            flash('Perfil actualizado con éxito.', 'success')
            
    return render_template('profile.html')

@app.route('/profile/delete_signature', methods=['POST'])
@login_required
def delete_signature():
    if current_user.firma_path:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.firma_path)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error al eliminar la firma: {e}")
        current_user.firma_path = None
        db.session.commit()
        log_action(current_user.id, "Firma digital eliminada")
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
        return jsonify({"success": True})
        
    flash('Firma eliminada correctamente', 'success')
    return redirect(url_for('profile_view'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/consultation', methods=['GET', 'POST'])
@login_required
def consultation():
    consultation_id = request.args.get('id', type=int)
    consultation_obj = None
    attachments = []
    if consultation_id:
        consultation_obj = Consultation.query.get(consultation_id)
        if consultation_obj:
            from models import ConsultationAttachment
            attachments = ConsultationAttachment.query.filter_by(consultation_id=consultation_id).all()

    if request.method == 'POST':
        nombre = request.form.get('nombre_paciente')
        apellido_paterno = request.form.get('apellido_paterno')
        apellido_materno = request.form.get('apellido_materno')
        edad = request.form.get('edad')
        peso = request.form.get('peso')
        genero = request.form.get('genero')
        motivo = request.form.get('motivo')
        resumen_clinico = request.form.get('resumen_clinico')
        diagnostico = request.form.get('diagnostico')
        receta = request.form.get('receta')
        action = request.form.get('action') # 'save' or 'pdf'
        
        # Guardar / Encontrar paciente
        # Aquí permitimos buscar pero creamos uno nuevo si no coincide exacto, o deberíamos requerir Folio. 
        # Como es creación rápida, asumimos nuevo si difiere en algo.
        edad_val = int(edad) if edad and str(edad).strip() else 0
        peso_val = float(peso) if peso and str(peso).strip() else 0.0
        patient = Patient.query.filter_by(nombre=nombre, apellido_paterno=apellido_paterno, apellido_materno=apellido_materno).first()
        if not patient:
            patient = Patient(nombre=nombre, apellido_paterno=apellido_paterno, apellido_materno=apellido_materno, edad=edad_val, peso=peso_val, genero=genero)
            db.session.add(patient)
            db.session.commit()
            # Generar Folio
            patient.folio = f"EXP-{patient.id:06d}"
            db.session.commit()
            
        # Crear consulta
        new_consultation = Consultation(
            patient_id=patient.id,
            user_id=current_user.id,
            constantes_vitales="Deprecado", # Bypass para el error de NOT NULL en BD vieja
            presion_arterial=request.form.get('presion_arterial'),
            frecuencia_cardiaca=request.form.get('frecuencia_cardiaca'),
            frecuencia_respiratoria=request.form.get('frecuencia_respiratoria'),
            temperatura=request.form.get('temperatura'),
            saturacion_oxigeno=request.form.get('saturacion_oxigeno'),
            altura=request.form.get('altura'),
            imc=request.form.get('imc'),
            evaluacion_dolor=request.form.get('evaluacion_dolor'),
            motivo=motivo,
            resumen_clinico=resumen_clinico,
            diagnostico=diagnostico,
            receta=receta
        )
        db.session.add(new_consultation)
        db.session.commit()
        log_action(current_user.id, f"Creación de Consulta en Expediente {patient.folio}")
        flash('Consulta guardada exitosamente. Ahora puedes añadir documentos adjuntos o exportarla a PDF.', 'success')
        return redirect(url_for('consultation', id=new_consultation.id))
        
    return render_template('consultation.html', consultation=consultation_obj, attachments=attachments, datetime=datetime)

@app.route('/consultation_history', methods=['GET'])
@login_required
def consultation_history():
    return render_template('consultation_history.html')

@app.route('/api/consultations', methods=['GET'])
@login_required
def api_consultations():
    search = request.args.get('search', '').lower()
    query = Consultation.query.filter_by(user_id=current_user.id).order_by(Consultation.fecha.desc()).all()
    
    res = []
    for c in query:
        fullName = f"{c.patient.nombre} {c.patient.apellido_paterno or ''} {c.patient.apellido_materno or ''}".lower()
        fullFolio = (c.patient.folio or '').lower()
        if search and search not in fullName and search not in fullFolio:
            continue
        res.append({
            "id": c.id,
            "patient_name": f"{c.patient.nombre} {c.patient.apellido_paterno or ''} {c.patient.apellido_materno or ''}".strip(),
            "folio": c.patient.folio or 'SIN-FOLIO',
            "motivo": c.motivo,
            "fecha": c.fecha.strftime('%d/%m/%Y %H:%M')
        })
    return jsonify(res)

@app.route('/api/consultations/<int:id>', methods=['GET'])
@login_required
def api_consultation_details(id):
    c = Consultation.query.get_or_404(id)
    if c.user_id and c.user_id != current_user.id:
        return jsonify({"error": "Acceso denegado"}), 403
        
    atts = []
    for a in c.attachments:
        atts.append({"id": a.id, "filename": a.filename, "original_name": a.original_name})
        
    return jsonify({
        "id": c.id,
        "patient": {
            "id": c.patient.id,
            "nombre": c.patient.nombre,
            "apellido_paterno": c.patient.apellido_paterno,
            "apellido_materno": c.patient.apellido_materno,
            "edad": c.patient.edad,
            "peso": c.patient.peso,
            "genero": c.patient.genero,
            "folio": c.patient.folio
        },
        "consultation": {
            "fecha": c.fecha.strftime('%d/%m/%Y %H:%M'),
            "presion_arterial": c.presion_arterial,
            "frecuencia_cardiaca": c.frecuencia_cardiaca,
            "frecuencia_respiratoria": c.frecuencia_respiratoria,
            "temperatura": c.temperatura,
            "saturacion_oxigeno": c.saturacion_oxigeno,
            "altura": c.altura,
            "imc": c.imc,
            "evaluacion_dolor": c.evaluacion_dolor,
            "motivo": c.motivo,
            "resumen_clinico": c.resumen_clinico,
            "diagnostico": c.diagnostico,
            "receta": c.receta
        },
        "attachments": atts,
        "remote_link": {
            "token": c.remote_care_link.token,
            "url": url_for('remote_care_patient', token=c.remote_care_link.token, _external=True),
            "is_active": c.remote_care_link.is_active,
            "expires_at": c.remote_care_link.expires_at.strftime('%d/%m/%Y %H:%M')
        } if c.remote_care_link else None,
        "remote_measurements": [
            {
                k: v for k, v in {
                    "fecha_registro": m.fecha_registro.strftime('%d/%m/%Y %H:%M'),
                    "presion_arterial": m.presion_arterial,
                    "glucosa": m.glucosa,
                    "oxigeno_sangre": m.oxigeno_sangre,
                    "frecuencia_cardiaca": m.frecuencia_cardiaca,
                    "peso_actual": m.peso_actual,
                    "notas_paciente": m.notas_paciente
                }.items() if v is not None and v != ""
            } for m in RemoteMeasurement.query.filter_by(consultation_id=c.id).order_by(RemoteMeasurement.fecha_registro.asc()).all()
        ]
    })

@app.route('/api/export_consultation_pdf/<int:id>', methods=['GET'])
@login_required
def export_consultation_pdf_endpoint(id):
    c = Consultation.query.get_or_404(id)
    if c.user_id and c.user_id != current_user.id:
        return "Acceso denegado", 403
        
    log_action(current_user.id, f"Exportación de Consulta ID {id} a PDF")
    patient = c.patient
    patient_data = {
        'nombre': patient.nombre, 
        'apellido_paterno': patient.apellido_paterno,
        'apellido_materno': patient.apellido_materno,
        'edad': patient.edad, 
        'peso': patient.peso,
        'folio': patient.folio,
        'genero': patient.genero
    }
    cons_data = {
        'fecha': c.fecha.strftime('%d/%m/%Y %H:%M'), 
        'presion_arterial': c.presion_arterial,
        'frecuencia_cardiaca': c.frecuencia_cardiaca,
        'frecuencia_respiratoria': c.frecuencia_respiratoria,
        'temperatura': c.temperatura,
        'saturacion_oxigeno': c.saturacion_oxigeno,
        'altura': c.altura,
        'imc': c.imc,
        'evaluacion_dolor': c.evaluacion_dolor,
        'motivo': c.motivo,
        'resumen_clinico': c.resumen_clinico,
        'diagnostico': c.diagnostico,
        'receta': c.receta
    }
    firma_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.firma_path) if current_user.firma_path else None
    
    from models import ConsultationAttachment
    atts = ConsultationAttachment.query.filter_by(consultation_id=c.id).all()
    
    image_paths = []
    pdf_paths = []
    if atts:
        for att in atts:
            att_path = os.path.join(app.config['UPLOAD_FOLDER'], att.filename)
            if os.path.exists(att_path):
                if att.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    image_paths.append(att_path)
                elif att.filename.lower().endswith('.pdf'):
                    pdf_paths.append(att_path)

    from utils import generate_consultation_pdf
    pdf_buffer = generate_consultation_pdf(patient_data, cons_data, current_user.username, firma_path, image_attachments_paths=image_paths)
    
    if pdf_paths:
        try:
            from pypdf import PdfReader, PdfWriter
            merger = PdfWriter()
            pdf_buffer.seek(0)
            base_pdf = PdfReader(pdf_buffer)
            for page in base_pdf.pages:
                merger.add_page(page)
            
            for pdf_path in pdf_paths:
                with open(pdf_path, 'rb') as f:
                    att_pdf = PdfReader(f)
                    for page in att_pdf.pages:
                        merger.add_page(page)
                            
            import io
            new_buffer = io.BytesIO()
            merger.write(new_buffer)
            new_buffer.seek(0)
            pdf_buffer = new_buffer
        except Exception as e:
            print("Error merging pdfs:", e)
            
    return send_file(
        pdf_buffer, 
        as_attachment=True, 
        download_name=f'Consulta_{patient.nombre.replace(" ", "_")}.pdf', 
        mimetype='application/pdf'
    )

@app.route('/api/consultation_upload/<int:consultation_id>', methods=['POST'])
@login_required
def upload_consultation_attachment(consultation_id):
    from models import ConsultationAttachment
    cons = Consultation.query.get_or_404(consultation_id)
        
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file"}), 400
        
    original = werkzeug.utils.secure_filename(file.filename)
    unique_name = f"{int(datetime.utcnow().timestamp())}_cons_{original}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(filepath)
    
    new_att = ConsultationAttachment(consultation_id=cons.id, filename=unique_name, original_name=original)
    db.session.add(new_att)
    db.session.commit()
    
    return jsonify({"success": True, "attachment": {"id": new_att.id, "filename": unique_name, "original_name": original}})

@app.route('/api/consultations/<int:id>/delete', methods=['POST'])
@login_required
def delete_consultation(id):
    c = Consultation.query.get_or_404(id)
    if c.user_id and c.user_id != current_user.id:
        return jsonify({"success": False, "error": "Acceso denegado."}), 403
        
    pwd = request.json.get('password', '')
    if not check_password_hash(current_user.password, pwd):
        return jsonify({"success": False, "error": "Contraseña incorrecta."}), 401
        
    db.session.delete(c)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/agenda', methods=['GET'])
@login_required
def agenda():
    return render_template('agenda.html')
    
@app.route('/api/appointments', methods=['GET'])
@login_required
def get_appointments():
    appointments = Appointment.query.filter_by(user_id=current_user.id).all()
    results = [
        {
            "id": appt.id,
            "titulo": appt.titulo,
            "paciente_telefono": appt.paciente_telefono,
            "fecha_hora": appt.fecha_hora.strftime("%Y-%m-%dT%H:%M"),
            "notas": appt.notas
        } for appt in appointments
    ]
    return jsonify(results)

@app.route('/api/appointments', methods=['POST'])
@login_required
def add_appointment():
    data = request.json
    try:
        dt = datetime.strptime(data['fecha_hora'], "%Y-%m-%dT%H:%M")
        new_appt = Appointment(
            titulo=data['titulo'],
            paciente_nombre=data.get('paciente_nombre'),
            paciente_email=data.get('paciente_email'),
            paciente_telefono=data.get('paciente_telefono'),
            fecha_hora=dt,
            user_id=current_user.id,
            notas=data.get('notas', '')
        )
        db.session.add(new_appt)
        db.session.commit()
        
        # Programar recordatorio 24 horas antes
        reminder_time = dt - timedelta(hours=24)
        now = datetime.now()
        
        if reminder_time > now:
            run_time = reminder_time
        elif dt > now:
            # Si la cita es en el futuro pero falta menos de 24 horas, enviarlo de inmediato
            run_time = now + timedelta(seconds=5)
        else:
            run_time = None
            
        if run_time:
            scheduler.add_job(
                func=send_appointment_reminder, 
                trigger='date', 
                run_date=run_time,
                args=[new_appt.paciente_nombre, new_appt.paciente_email, current_user.username, current_user.email, dt.strftime("%H:%M"), new_appt.id, current_user.sexo]
            )
            print(f"[DEBUG] Programado recordatorio para agendar en {run_time}", flush=True)

        return jsonify({"success": True, "id": new_appt.id}), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/appointments/<int:id>', methods=['DELETE'])
@login_required
def delete_appointment(id):
    appt = Appointment.query.get_or_404(id)
    if appt.user_id != current_user.id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403
        
    pwd = request.json.get('password', '')
    if not check_password_hash(current_user.password, pwd):
        return jsonify({"success": False, "error": "Contraseña incorrecta"}), 401
        
    db.session.delete(appt)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/records', methods=['GET'])
@login_required
def records():
    return render_template('records.html')

@app.route('/api/generate_record_pdf', methods=['POST'])
@login_required
def generate_record_pdf():
    from utils import generate_master_record_pdf
    import io
    data = request.json
    pages = data.get('pages', [])
    record_id = data.get('record_id')
    
    pdf_buffer = generate_master_record_pdf(pages, current_user.username, current_user.cedula_profesional, firma_path=os.path.join(app.config['UPLOAD_FOLDER'], current_user.firma_path) if current_user.firma_path else None)
    
    # Merge attachments
    if record_id:
        record = Record.query.get(record_id)
        if record and record.user_id == current_user.id:
            pdf_attachments = Attachment.query.filter(
                Attachment.record_id == record.id,
                Attachment.filename.ilike('%.pdf')
            ).all()
            
            if pdf_attachments:
                try:
                    from pypdf import PdfReader, PdfWriter
                    merger = PdfWriter()
                    
                    pdf_buffer.seek(0)
                    base_pdf = PdfReader(pdf_buffer)
                    for page in base_pdf.pages:
                        merger.add_page(page)
                        
                    for att in pdf_attachments:
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], att.filename)
                        if os.path.exists(filepath):
                            with open(filepath, 'rb') as f:
                                att_pdf = PdfReader(f)
                                for page in att_pdf.pages:
                                    merger.add_page(page)
                    
                    new_buffer = io.BytesIO()
                    merger.write(new_buffer)
                    new_buffer.seek(0)
                    pdf_buffer = new_buffer
                except Exception as e:
                    print("Error merging attached PDFs:", e)
    
    # Determine dynamic download name
    patient_name = "Paciente_Desconocido"
    for page in pages:
        fields = page.get('fields', {})
        for name_field in ['hf_nombre', 'ni_nombre', 'nu_nombre', 'np_nombre', 'ci_paciente', 'rc_paciente']:
            if fields.get(name_field):
                raw_name = fields.get(name_field).strip()
                import re
                patient_name = re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s]', '', raw_name)
                patient_name = re.sub(r'\s+', '_', patient_name)
                break
        if patient_name != "Paciente_Desconocido":
            break

    download_filename = f"Expediente_{patient_name}"
    if record_id:
        download_filename += f"_ID_{record_id}"
    download_filename += ".pdf"

    return send_file(
        pdf_buffer, 
        as_attachment=True, 
        download_name=download_filename, 
        mimetype='application/pdf'
    )

@app.route('/api/records', methods=['GET'])
@login_required
def get_records():
    search = request.args.get('search', '').lower()
    query = Record.query.filter_by(user_id=current_user.id)
    records = query.order_by(Record.updated_at.desc()).all()
    
    if search:
        records = [r for r in records if search in r.patient_name.lower() or search in str(r.id)]
        
    res = []
    for r in records:
        attach_count = Attachment.query.filter_by(record_id=r.id).count()
        res.append({
            "id": r.id,
            "patient_name": r.patient_name,
            "title": r.title,
            "updated_at": r.updated_at.strftime("%d/%m/%Y %H:%M"),
            "attachments_count": attach_count
        })
    return jsonify(res)

@app.route('/api/records', methods=['POST'])
@login_required
def save_record():
    data = request.json
    record_id = data.get('id')
    patient_name = data.get('patient_name', 'Desconocido')
    title = data.get('title', 'Expediente Sin Título')
    pages = data.get('pages', [])
    
    if record_id:
        rec = Record.query.get(record_id)
        if rec and rec.user_id == current_user.id:
            if rec.title != title:
                return jsonify({"success": False, "error": "El nombre del expediente no puede ser alterado."}), 400
            
            try:
                existing_pages = json.loads(rec.data_json)
                old_len = len(existing_pages)
                
                if len(pages) < old_len:
                    return jsonify({"success": False, "error": "No se pueden eliminar o alterar secciones históricas."}), 400
                
                added_pages = pages[old_len:]
                if added_pages:
                    now_iso = datetime.utcnow().isoformat()
                    for p in added_pages:
                        if 'timestamp' not in p:
                            p['timestamp'] = now_iso
                        # Evaluar firma médica
                        if 'fields' in p:
                            for k, v in list(p['fields'].items()):
                                if k.endswith('_tipo') and v == 'precargada':
                                    base_key = k.replace('_tipo', '')
                                    if current_user.firma_path:
                                        p['fields'][base_key] = current_user.firma_path
                    existing_pages.extend(added_pages)
                    rec.data_json = json.dumps(existing_pages)
                    db.session.commit()
                
                return jsonify({"success": True, "id": rec.id})
            except Exception as e:
                print(f"Error procesando el expediente: {e}")
                return jsonify({"success": False, "error": "Error procesando el expediente."}), 500

    now_iso = datetime.utcnow().isoformat()
    for p in pages:
        if 'timestamp' not in p:
            p['timestamp'] = now_iso
        # Evaluar firma médica
        if 'fields' in p:
            for k, v in list(p['fields'].items()):
                if k.endswith('_tipo') and v == 'precargada':
                    base_key = k.replace('_tipo', '')
                    if current_user.firma_path:
                        p['fields'][base_key] = current_user.firma_path
            
    new_rec = Record(
        user_id=current_user.id,
        patient_name=patient_name,
        title=title,
        data_json=json.dumps(pages)
    )
    db.session.add(new_rec)
    db.session.commit()
    return jsonify({"success": True, "id": new_rec.id})

@app.route('/api/records/<int:id>', methods=['GET'])
@login_required
def load_record(id):
    r = Record.query.get_or_404(id)
    if r.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
        
    attachments = Attachment.query.filter_by(record_id=r.id).all()
    atts = [{"id": a.id, "filename": a.filename, "original_name": a.original_name} for a in attachments]
        
    return jsonify({
        "id": r.id, 
        "patient_name": r.patient_name, 
        "title": r.title, 
        "pages": json.loads(r.data_json),
        "attachments": atts
    })

@app.route('/api/records/delete_expedient/<int:record_id>', methods=['POST'])
@login_required
def delete_record_hard(record_id):
    rec = Record.query.get_or_404(record_id)
    if rec.user_id != current_user.id:
        return jsonify({"status": "error", "message": "No tienes permiso para eliminar este expediente"}), 403
        
    data = request.json or {}
    password = data.get('password', '')
    if not check_password_hash(current_user.password, password):
        return jsonify({"status": "error", "message": "Contraseña incorrecta"}), 401
        
    try:
        # Cascade delete physical files
        for att in rec.attachments:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], att.filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                
        db.session.delete(rec)
        db.session.commit()
        log_action(current_user.id, f"Expediente eliminado definitivamente (Hard Delete): {rec.patient_name}")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        print(f"Error al eliminar expediente: {e}")
        return jsonify({"status": "error", "message": "Error interno al eliminar expediente."}), 500

@app.route('/api/upload/<int:record_id>', methods=['POST'])
@login_required
def upload_attachment(record_id):
    rec = Record.query.get_or_404(record_id)
    if rec.user_id != current_user.id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403
        
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file"}), 400
        
    original = werkzeug.utils.secure_filename(file.filename)
    unique_name = f"{int(datetime.utcnow().timestamp())}_{original}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(filepath)
    
    new_att = Attachment(record_id=rec.id, filename=unique_name, original_name=original)
    db.session.add(new_att)
    db.session.commit()
    
    return jsonify({"success": True, "attachment": {"id": new_att.id, "filename": unique_name, "original_name": original}})

@app.route('/api/attachments/<int:att_id>', methods=['DELETE'])
@login_required
def delete_attachment(att_id):
    att = Attachment.query.get_or_404(att_id)
    if att.record.user_id != current_user.id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403
        
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], att.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print("File deletion error:", e)
        
    db.session.delete(att)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/api/records/<int:record_id>/share', methods=['POST'])
@login_required
def share_record(record_id):
    rec = Record.query.get_or_404(record_id)
    if rec.user_id != current_user.id:
        return jsonify({"success": False, "error": "No tienes permiso para compartir este expediente."}), 403

    data = request.json
    target_username = data.get('target_username')
    target_cedula = data.get('target_cedula')

    if not target_username or not target_cedula:
        return jsonify({"success": False, "error": "Datos incompletos del médico destino."}), 400

    target_user = User.query.filter_by(username=target_username, cedula_profesional=target_cedula).first()
    if not target_user:
        return jsonify({"success": False, "error": "Médico o Cédula no encontrada, inténtelo de nuevo."}), 404

    if target_user.id == current_user.id:
        return jsonify({"success": False, "error": "No puedes compartir un expediente contigo mismo."}), 400

    try:
        new_rec = Record(
            user_id=target_user.id,
            patient_name=f"{rec.patient_name} (Compartido por {current_user.username})",
            title=rec.title,
            data_json=rec.data_json
        )
        db.session.add(new_rec)
        db.session.flush()

        for a in rec.attachments:
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], a.filename)
            new_filename = a.filename
            
            if os.path.exists(old_path):
                new_filename = f"{uuid.uuid4().hex}_{a.original_name}"
                new_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                shutil.copy2(old_path, new_path)

            new_att = Attachment(
                record_id=new_rec.id,
                filename=new_filename,
                original_name=a.original_name
            )
            db.session.add(new_att)

        db.session.commit()
        log_action(current_user.id, f"Registro de {rec.patient_name} compartido con {target_user.username}")
        
        return jsonify({"success": True, "message": f"Expediente transferido exitosamente a la {'Dra.' if target_user.sexo == 'Femenino' else 'Dr.'} {target_user.username}"})

    except Exception as e:
        db.session.rollback()
        print(f"Error al transferir expediente: {e}")
        return jsonify({"success": False, "error": "Error interno al transferir expediente."}), 500

@app.route('/transcriber', methods=['GET'])
@login_required
def transcriber():
    return render_template('transcriber.html')
    
@app.route('/api/assemblyai/transcribe', methods=['POST'])
@login_required
def transcribe_audio():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file"}), 400
        
    audio_file = request.files['audio']
    API_KEY = "009f58d6f69041dd93299139809e7742"
    headers = {"authorization": API_KEY}
    
    # 1. Upload
    upload_url = "https://api.assemblyai.com/v2/upload"
    upload_res = requests.post(upload_url, headers=headers, data=audio_file)
    if upload_res.status_code != 200:
        return jsonify({"error": f"Upload failed: {upload_res.text}"}), 500
        
    audio_url = upload_res.json()['upload_url']
    
    # 2. Transcribe
    tx_url = "https://api.assemblyai.com/v2/transcript"
    tx_data = {
        "audio_url": audio_url, 
        "language_code": "es", 
        "speech_models": ["universal-2"]
    }
    tx_res = requests.post(tx_url, headers={"authorization": API_KEY, "content-type": "application/json"}, json=tx_data)
    
    if tx_res.status_code != 200:
        return jsonify({"error": f"Transcript start failed: {tx_res.text}"}), 500
        
    tx_id = tx_res.json()['id']
    
    # 3. Poll
    poll_url = f"https://api.assemblyai.com/v2/transcript/{tx_id}"
    while True:
        poll_res = requests.get(poll_url, headers=headers)
        status = poll_res.json()['status']
        if status == 'completed':
            return jsonify({"text": poll_res.json()['text']})
        elif status == 'error':
            return jsonify({"error": poll_res.json()['error']}), 500
            
        time.sleep(1.5)

# ================= REMOTE CARE ROUTES =================
@app.route('/api/remote_care/generate/<int:consultation_id>', methods=['POST'])
@login_required
def generate_remote_care_link(consultation_id):
    c = Consultation.query.get_or_404(consultation_id)
    if c.user_id and c.user_id != current_user.id:
        return jsonify({"success": False, "error": "Acceso denegado"}), 403

    existing_link = RemoteCareLink.query.filter_by(consultation_id=c.id).first()
    
    # Patrón Singleton: Si ya hay un link activo (o simplemente ya existe), devolvemos el mismo.
    if existing_link and existing_link.is_active and existing_link.expires_at > datetime.utcnow():
        return jsonify({
            "success": True,
            "token": existing_link.token,
            "url": url_for('remote_care_patient', token=existing_link.token, _external=True),
            "expires_at": existing_link.expires_at.strftime('%d/%m/%Y %H:%M')
        })

    # Si existe pero expiró/desactivó, lo actualizamos, o creamos uno nuevo
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=30)
    
    if existing_link:
        existing_link.token = token
        existing_link.expires_at = expires_at
        existing_link.is_active = True
    else:
        new_link = RemoteCareLink(token=token, consultation_id=c.id, expires_at=expires_at, is_active=True)
        db.session.add(new_link)
        
    db.session.commit()
    log_action(current_user.id, f"Generación de Enlace Remoto para Consulta {c.id}")
    
    return jsonify({
        "success": True,
        "token": token,
        "url": url_for('remote_care_patient', token=token, _external=True),
        "expires_at": expires_at.strftime('%d/%m/%Y %H:%M')
    })

@app.route('/cuidado-remoto/<token>', methods=['GET'])
def remote_care_patient(token):
    link = RemoteCareLink.query.filter_by(token=token).first()
    if not link or not link.is_active or link.expires_at < datetime.utcnow():
        return "El enlace ha expirado o no es válido. Consulte con su médico.", 404
        
    return render_template('remote_care_patient.html', token=token, patient_name=link.consultation.patient.nombre)

@app.route('/api/remote_care/submit/<token>', methods=['POST'])
def submit_remote_care(token):
    link = RemoteCareLink.query.filter_by(token=token).first()
    if not link or not link.is_active or link.expires_at < datetime.utcnow():
        return jsonify({"success": False, "error": "Enlace inválido o expirado"}), 400

    data = request.json
    measurement = RemoteMeasurement(
        consultation_id=link.consultation_id,
        presion_arterial=data.get('presion_arterial'),
        glucosa=data.get('glucosa'),
        oxigeno_sangre=data.get('oxigeno_sangre'),
        frecuencia_cardiaca=data.get('frecuencia_cardiaca'),
        peso_actual=data.get('peso_actual'),
        notas_paciente=data.get('notas_paciente')
    )
    db.session.add(measurement)
    
    # NO desactivamos el token, permitiendo múltiples registros durante 30 días
    db.session.commit()
    
    return jsonify({"success": True})

# ================= CUSTOM TEMPLATES API =================
@app.route('/api/templates', methods=['GET'])
@login_required
def get_templates():
    system_user = User.query.filter_by(username="SYSTEM_TEMPLATES").first()
    sys_id = system_user.id if system_user else -1

    templates = CustomTemplate.query.filter(
        db.or_(CustomTemplate.user_id == current_user.id, CustomTemplate.user_id == sys_id)
    ).order_by(CustomTemplate.created_at.desc()).all()
    
    res = []
    for t in templates:
        res.append({
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "fields_schema": json.loads(t.fields_schema)
        })
    return jsonify(res)

@app.route('/api/upload_template_image', methods=['POST'])
@login_required
def upload_template_image():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400
    if file and file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
        original = werkzeug.utils.secure_filename(file.filename)
        filename = f"template_{current_user.id}_{int(datetime.utcnow().timestamp())}_{original}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        return jsonify({"success": True, "filename": filename})
    return jsonify({"success": False, "error": "Invalid file type. Only images allowed."}), 400

@app.route('/api/upload_ine', methods=['POST'])
@login_required
def upload_ine():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400
    if file and file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.pdf')):
        original = werkzeug.utils.secure_filename(file.filename)
        filename = f"ine_{current_user.id}_{int(datetime.utcnow().timestamp())}_{original}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        return jsonify({"success": True, "filename": filename})
    return jsonify({"success": False, "error": "Invalid file type. Only PDF and images allowed."}), 400

@app.route('/api/templates/create', methods=['POST'])
@login_required
def create_template():
    data = request.json
    name = data.get('name')
    fields = data.get('fields', [])
    
    if not name or not fields:
        return jsonify({"success": False, "error": "Nombre y campos son requeridos."}), 400
        
    new_template = CustomTemplate(
        user_id=current_user.id,
        name=name,
        description=data.get('description', ''),
        fields_schema=json.dumps(fields)
    )
    db.session.add(new_template)
    db.session.commit()
    
    return jsonify({"success": True, "id": new_template.id})

@app.route('/api/templates/delete/<int:template_id>', methods=['POST'])
@login_required
def delete_template(template_id):
    template = CustomTemplate.query.get_or_404(template_id)
    if template.user_id != current_user.id:
        return jsonify({"status": "error", "message": "No se pueden eliminar plantillas del sistema"}), 403
        
    data = request.json or {}
    password = data.get('password', '')
    if not check_password_hash(current_user.password, password):
        return jsonify({"status": "error", "message": "Contraseña incorrecta"}), 401
        
    db.session.delete(template)
    db.session.commit()
    log_action(current_user.id, f"Plantilla eliminada: {template.name}")
    
    return jsonify({"success": True})

@app.route('/api/patients/<int:patient_id>/share', methods=['POST'])
@login_required
def share_patient(patient_id):
    # Validar que el paciente pertenece a alguna consulta del usuario actual
    # (En nuestro modelo simplificado, validamos que exista y que el usuario actual tenga una consulta de este paciente)
    patient = Patient.query.get_or_404(patient_id)
    has_access = Consultation.query.filter_by(patient_id=patient.id, user_id=current_user.id).first()
    if not has_access:
        return jsonify({"success": False, "error": "No tienes permiso para compartir este expediente."}), 403

    data = request.json
    target_username = data.get('target_username')
    target_cedula = data.get('target_cedula')

    if not target_username or not target_cedula:
        return jsonify({"success": False, "error": "Datos incompletos del médico destino."}), 400

    target_user = User.query.filter_by(username=target_username, cedula_profesional=target_cedula).first()
    if not target_user:
        return jsonify({"success": False, "error": "Médico o Cédula no encontrada, inténtelo de nuevo."}), 404

    if target_user.id == current_user.id:
        return jsonify({"success": False, "error": "No puedes compartir un expediente contigo mismo."}), 400

    try:
        # 1. Clonar Paciente
        new_patient = Patient(
            folio=f"CLONE-{patient.folio}-{target_user.id}" if patient.folio else None,
            nombre=patient.nombre,
            apellido_paterno=patient.apellido_paterno,
            apellido_materno=patient.apellido_materno,
            edad=patient.edad,
            peso=patient.peso,
            genero=patient.genero
        )
        db.session.add(new_patient)
        db.session.flush() # Para obtener new_patient.id

        # 2. Clonar Consultas
        consultations = Consultation.query.filter_by(patient_id=patient.id).all()
        for c in consultations:
            new_consultation = Consultation(
                patient_id=new_patient.id,
                user_id=target_user.id,
                constantes_vitales=c.constantes_vitales,
                presion_arterial=c.presion_arterial,
                frecuencia_cardiaca=c.frecuencia_cardiaca,
                frecuencia_respiratoria=c.frecuencia_respiratoria,
                temperatura=c.temperatura,
                saturacion_oxigeno=c.saturacion_oxigeno,
                altura=c.altura,
                imc=c.imc,
                evaluacion_dolor=c.evaluacion_dolor,
                motivo=c.motivo,
                resumen_clinico=c.resumen_clinico,
                diagnostico=c.diagnostico,
                receta=c.receta,
                fecha=c.fecha # Mantenemos la fecha original
            )
            db.session.add(new_consultation)
            db.session.flush()

            for a in c.attachments:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], a.filename)
                new_filename = a.filename
                
                if os.path.exists(old_path):
                    new_filename = f"{uuid.uuid4().hex}_{a.original_name}"
                    new_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                    shutil.copy2(old_path, new_path)

                new_att = ConsultationAttachment(
                    consultation_id=new_consultation.id,
                    filename=new_filename,
                    original_name=a.original_name
                )
                db.session.add(new_att)
        
        db.session.commit()
        log_action(current_user.id, f"Expediente de {patient.nombre} compartido con {target_user.username}")
        
        return jsonify({"success": True, "message": f"Expediente transferido exitosamente a la {'Dra.' if target_user.sexo == 'Femenino' else 'Dr.'} {target_user.username}"})

    except Exception as e:
        db.session.rollback()
        print(f"Error al transferir consulta: {e}")
        return jsonify({"success": False, "error": "Error interno al transferir expediente."}), 500

# ================= INITIALIZATION =================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(host='0.0.0.0', port=port, debug=True)
