"""
Script para iniciar el bot de Discord.
"""

import os
import asyncio
import logging

# Asegurarse de que estamos en el directorio raíz del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Configuración básica de logging para este script
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """
    Función principal que inicia el bot
    """
    try:
        logger.info("=== Iniciando bot de Discord ===")
        
        logger.info("Cargando módulos del bot...")
        # Importar bot como un módulo
        from src import bot
        
        # La función main del bot hará todo el trabajo
        await bot.main()
    except Exception as e:
        logger.error(f"Error iniciando el sistema: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    try:
        # Ejecutar el bot
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot detenido manualmente.")
    except Exception as e:
        print(f"Error fatal: {e}")
