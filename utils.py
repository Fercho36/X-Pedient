import io
import os
import base64
import requests
from flask import render_template

def get_base64_image(image_path):
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            extension = image_path.split('.')[-1].lower()
            if extension == 'jpg': extension = 'jpeg'
            return f"data:image/{extension};base64,{encoded_string}"
    except Exception as e:
        print(f"Error procesando imagen para PDF: {e}")
        return None

def call_api2pdf(html_content):
    api_key = os.getenv('API2PDF_KEY')
    if not api_key:
        raise ValueError("[CRÍTICO] API2PDF_KEY no configurado en variables de entorno.")

    # 1. LECTURA E INYECCIÓN DEL CSS LOCAL (Diseño Premium)
    css_path = os.path.join(os.path.dirname(__file__), 'static', 'css', 'style.css')
    if os.path.exists(css_path):
        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()
            if '</head>' in html_content:
                html_content = html_content.replace('</head>', f'<style>\n{css_content}\n</style>\n</head>')
            else:
                html_content = f"<style>\n{css_content}\n</style>\n" + html_content

    # 2. CONFIGURACIÓN DEL PAYLOAD (Api2Pdf)
    payload = {
        "html": html_content,
        "inline": True,
        "options": {
            "marginTop": "2cm",
            "marginBottom": "2cm",
            "marginLeft": "2cm",
            "marginRight": "2cm",
            "printBackground": True # Obligatorio para que respete los colores CSS
        }
    }

    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }

    # 3. LLAMADA A LA NUBE
    try:
        response = requests.post(
            'https://v2.api2pdf.com/chrome/pdf/html',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"[ERROR] Api2Pdf falló. Código HTTP: {response.status_code}. Detalles: {response.text}")
            raise Exception("Error de conexión con Api2Pdf.")
            
        # Api2Pdf devuelve un JSON con la URL de descarga del PDF generado
        pdf_url = response.json().get('FileUrl')
        
        if not pdf_url:
            raise Exception("La API no devolvió el archivo.")
            
        # Descargamos el binario del PDF desde la nube a tu servidor Flask
        pdf_response = requests.get(pdf_url)
        return io.BytesIO(pdf_response.content)
        
    except Exception as e:
        print(f"[EXCEPCIÓN CRÍTICA] en la conexión: {str(e)}")
        raise e

def generate_consultation_pdf(patient_data, consultation_data, doctor_name, firma_path=None, image_attachments_paths=None):
    firma_base64 = get_base64_image(firma_path)
    
    image_attachments = []
    if image_attachments_paths:
        for path in image_attachments_paths:
            b64 = get_base64_image(path)
            if b64:
                image_attachments.append(b64)

    html_content = render_template('pdf_consultation.html', 
                                   patient=patient_data, 
                                   cons=consultation_data, 
                                   doctor_name=doctor_name, 
                                   firma_base64=firma_base64,
                                   image_attachments=image_attachments)

    return call_api2pdf(html_content)

def generate_master_record_pdf(pages_data, doc_name, cedula, firma_path=None):
    from models import CustomTemplate
    from flask import current_app
    import json
    
    firma_base64 = get_base64_image(firma_path)

    def resolve_image_to_base64(val):
        if not val:
            return ""
        if val.startswith('data:image/'):
            return val
        # Clean up path/filename
        filename = os.path.basename(val)
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            return get_base64_image(file_path)
        return val

    enriched_pages = []
    for page in pages_data:
        ptype = page.get('type')
        fields = page.get('fields', {})
        
        # Clone fields to avoid in-place modification of caller data
        new_fields = fields.copy()
        
        # 1. Resolve precargada signatures automatically
        keys_to_resolve = [k[:-5] for k in new_fields.keys() if k.endswith('_tipo') and new_fields[k] == 'precargada']
        for name in keys_to_resolve:
            path_key = f"{name}_path"
            if path_key in new_fields:
                new_fields[name] = new_fields[path_key]
                
        # 2. Resolve signatures and upload images in standard pages
        for k, v in list(new_fields.items()):
            if 'firma' in k or k in ['rc_firma', 'im_firma_medico', 'rm_firma_medico']:
                new_fields[k] = resolve_image_to_base64(v)
            if k == 'ci_ine_url' and v:
                new_fields['ci_ine_base64'] = resolve_image_to_base64(v)
                
        enriched_page = {
            'type': ptype,
            'fields': new_fields
        }
        
        # 3. Process custom templates
        if ptype and ptype.startswith('custom_'):
            try:
                template_id = int(ptype.split('_')[1])
                template = CustomTemplate.query.get(template_id)
                if template:
                    enriched_page['custom_name'] = template.name
                    schema = json.loads(template.fields_schema)
                    campos_personalizados = []
                    
                    for idx, field in enumerate(schema):
                        fname = f"custom_{template_id}_f{idx}"
                        raw_val = new_fields.get(fname, "")
                        
                        field_type = field.get('type')
                        processed_val = raw_val
                        img_base64 = None
                        
                        if field_type == 'signature_pad':
                            processed_val = resolve_image_to_base64(raw_val)
                        elif field_type == 'image_field':
                            img_filename = field.get('image_url')
                            if img_filename:
                                img_path = os.path.join(current_app.config['UPLOAD_FOLDER'], img_filename)
                                img_base64 = get_base64_image(img_path)
                                
                        campos_personalizados.append({
                            'label': field.get('label', ''),
                            'type': field_type,
                            'value': processed_val,
                            'image_base64': img_base64
                        })
                    enriched_page['campos_personalizados'] = campos_personalizados
            except Exception as e:
                print(f"Error enriqueciendo plantilla personalizada {ptype} para PDF: {e}")
                
        enriched_pages.append(enriched_page)

    html_content = render_template('pdf_master_record.html',
                                   pages_data=enriched_pages,
                                   doc_name=doc_name,
                                   cedula=cedula,
                                   firma_base64=firma_base64)
                                   
    return call_api2pdf(html_content)

