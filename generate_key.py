import os
from cryptography.fernet import Fernet

def generate_fernet_key():
    """Generates a secure Fernet key and instructs the user how to save it."""
    key = Fernet.generate_key().decode('utf-8')
    print("="*60)
    print("GENERADOR DE LLAVE MAESTRA (FERNET_KEY)")
    print("="*60)
    print("\nTu nueva llave maestra ha sido generada:")
    print(f"\n     {key}\n")
    print("INSTRUCCIONES CRÍTICAS DE SEGURIDAD:")
    print("1. Abre (o crea) el archivo '.env' en la raíz de tu proyecto.")
    print(f"2. Agrega la siguiente línea:")
    print(f"   FERNET_KEY={key}")
    print("3. ¡NUNCA compartas esta llave ni la subas a repositorios públicos como GitHub!")
    print("4. Guarda un respaldo físico o seguro de esta llave. Si la pierdes, TODOS tus")
    print("   registros médicos encriptados (diagnósticos, recetas, etc.) serán")
    print("   IRRECUPERABLES.\n")
    print("="*60)

if __name__ == "__main__":
    generate_fernet_key()
