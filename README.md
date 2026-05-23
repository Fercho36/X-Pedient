# MediCare ECE - MVP (Expediente Clínico Electrónico)

Plataforma de gestión de Expedientes Clínicos Electrónicos (ECE) diseñada bajo metodologías "Soft Mode" (Eye-Care) para reducir la fatiga visual. Incluye herramientas de agenda médica, creación de expedientes modulares, dictado por IA y exportación a PDF.

## 1. Guía de Instalación y Ejecución

*Requisitos previos: Python 3.8 o superior.*

1. **Abrir el terminal** en la carpeta base del proyecto (`Proyecto_ECE`).
2. **Crear el Entorno Virtual**:
   ```bash
   python -m venv venv
   ```
3. **Activar el Entorno Virtual**:
   - En Windows: `venv\Scripts\activate`
   - En macOS/Linux: `source venv/bin/activate`
4. **Instalar Dependencias**:
   ```bash
   pip install -r requirements.txt
   ```
5. **Ejecutar la Aplicación**:
   ```bash
   python app.py
   ```
   La aplicación estará disponible en `http://127.0.0.1:5000`. La base de datos local SQLite (`ece.db`) se generará y configurará automáticamente al iniciar por primera vez.

---

## 2. Flujo de Datos: Consulta y Expediente Modelo Canva

El sistema está diseñado para evitar la redundancia y facilitar la consolidación de documentos:

* **Módulo de Consulta Rápida:** Funciona como el primer nivel de atención (Triaje o Nota Rápida). Llenando el formulario se crea un registro del paciente (nombre, edad, peso) y su motivo de visita de forma rápida, exportando un PDF simple.
* **Gestor de Expedientes Maestro:** Es el constructor de documentos oficiales. Si requieres emitir una hoja frontal o una receta, entras a este módulo y arrastras la plantilla al "lienzo" central.
* **Generación Robusta:** Al hacer clic en exportar, la interfaz extrae organizadamente los datos de todos los bloques en pantalla (como un JSON estructurado). Esto se manda al endpoint `/api/generate_record_pdf` donde `reportlab` toma el control de manera puramente síncrona en el backend para trazar un PDF perfecto y devolverlo como descarga directa.

---

## 3. Instrucciones de Adaptación

### Sustituir Clave API de AssemblyAI (IA Transcriptora)
El módulo de voz en tiempo real usa la clave `009f...`. Para actualizarla:
1. Abre el archivo `app.py`.
2. Navega hasta el decorador de ruta `@app.route('/api/assemblyai/token')`.
3. Actualiza el valor de `API_KEY`. (Nota: En un entorno de producción, esto debería cargarse desde el archivo `.env`).

### Actualizar Videos Tutoriales (Ayuda)
1. Abre el archivo `templates/dashboard.html`.
2. Verás contenedores con etiquetas `<iframe>`.
3. Sólo debes cambiar el URL dentro del atributo `src` con tu propio link de YouTube (asegúrate de que usa la estructura `youtube.com/embed/IdDelVideo`).

### Escalar Sistema de Plantillas (>26 Hojas)
Si necesitas desarrollar los otros 23+ formatos, el sistema es modular y fácilmente escalable:
1. En el frontend (`templates/records.html`), agrega el nombre del nuevo bloque al sidebar con un `data-type="nueva_plantilla"`.
2. En la función `addBlockToCanvas(type)`, inyecta tu HTML libremente. Usa la clase `cnv-input` para inputs de texto.
3. En el backend (`utils.py`), añade una condicional `elif type == 'nueva_plantilla':` en la función constructora del PDF. Todos los datos escritos en tus inputs HTML llegarán automáticamente dentro del diccionario `fields`.
