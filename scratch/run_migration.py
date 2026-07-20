import sys
import os

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import init_db

print("Ejecutando init_db()...")
try:
    init_db()
    print("¡Migración de base de datos ejecutada con éxito!")
except Exception as e:
    print(f"Error al ejecutar la migración: {e}")
