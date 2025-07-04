"""
Script para iniciar Lavalink y el bot de Discord.
"""

import os
import asyncio
import logging
import subprocess
import time
import signal
import sys
import platform

# Asegurarse de que estamos en el directorio raíz del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Configuración básica de logging para este script
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Variable global para el proceso de Lavalink
lavalink_process = None

def check_java():
    """Comprueba si Java está instalado"""
    try:
        process = subprocess.run(['java', '-version'], capture_output=True, text=True)
        if process.returncode != 0:
            logger.error("Java no está instalado o no se encuentra en el PATH")
            logger.error("Por favor, instala Java 11 o superior")
            return False
        
        # Mostrar versión de Java
        version_output = process.stderr  # La versión se envía a stderr
        logger.info(f"Versión de Java detectada: {version_output.splitlines()[0]}")
        return True
    except Exception as e:
        logger.error(f"Error comprobando Java: {e}")
        return False

def start_lavalink():
    """Inicia el servidor Lavalink"""
    global lavalink_process

    logger.info("Iniciando servidor Lavalink...")
    
    # Verificar si ya hay un proceso Lavalink en ejecución
    if is_port_in_use(2444):
        logger.info("Lavalink ya parece estar en ejecución en el puerto 2444")
        return True
    
    # Ruta al archivo JAR de Lavalink
    lavalink_jar = os.path.join(BASE_DIR, "src", "utils", "Lavalink.jar")
    application_yml = os.path.join(BASE_DIR, "src", "utils", "application.yml")
    
    # Verificar que el archivo Lavalink.jar existe
    if not os.path.exists(lavalink_jar):
        logger.error(f"No se encontró el archivo Lavalink.jar en {lavalink_jar}")
        return False
    
    # Verificar que el archivo application.yml existe
    if not os.path.exists(application_yml):
        logger.error(f"No se encontró el archivo application.yml en {application_yml}")
        return False
    
    # Comando para iniciar Lavalink
    cmd = ['java', '-jar', lavalink_jar]

    try:
        # Iniciar Lavalink en un nuevo proceso
        logger.info(f"Ejecutando: {' '.join(cmd)}")
        
        # En Windows, utilizamos creationflags=subprocess.CREATE_NEW_PROCESS_GROUP para evitar que Ctrl+C afecte a Lavalink
        if platform.system() == "Windows":
            lavalink_process = subprocess.Popen(
                cmd,
                cwd=os.path.join(BASE_DIR, "src", "utils"),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            lavalink_process = subprocess.Popen(
                cmd,
                cwd=os.path.join(BASE_DIR, "src", "utils")
            )

        logger.info("Esperando a que Lavalink se inicie (15 segundos)...")
        
        # Esperar un tiempo para que Lavalink se inicie
        for i in range(15):
            if is_port_in_use(2444):
                logger.info("¡Lavalink está listo!")
                return True
            time.sleep(1)
            print(".", end="", flush=True)
            
        logger.warning("Lavalink puede no haberse iniciado correctamente, pero continuaremos...")
        return True
        
    except Exception as e:
        logger.error(f"Error iniciando Lavalink: {e}")
        return False

def is_port_in_use(port):
    """Comprueba si un puerto está en uso"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('localhost', port)) == 0

def stop_lavalink():
    """Detiene el servidor Lavalink"""
    global lavalink_process
    
    if lavalink_process is not None:
        logger.info("Deteniendo servidor Lavalink...")
        try:
            if platform.system() == "Windows":
                lavalink_process.terminate()
            else:
                lavalink_process.send_signal(signal.SIGTERM)
            
            # Esperar a que el proceso termine
            lavalink_process.wait(timeout=5)
            logger.info("Servidor Lavalink detenido correctamente")
        except Exception as e:
            logger.error(f"Error deteniendo Lavalink: {e}")
            # Forzar la terminación si es necesario
            try:
                lavalink_process.kill()
            except:
                pass

async def main():
    """
    Función principal que inicia Lavalink y el bot
    """
    try:
        logger.info("=== Iniciando sistema de música para Discord ===")
        
        # Comprobar si Java está instalado
        if not check_java():
            logger.error("No se puede iniciar Lavalink sin Java")
            return
        
        # Iniciar Lavalink
        if not start_lavalink():
            logger.error("Error iniciando Lavalink, el bot se iniciará sin funcionalidad de música")
        
        logger.info("Iniciando el bot de Discord...")
        # Importar bot como un módulo
        from src import bot
        
        # La función main del bot hará todo el trabajo
        await bot.main()
    except Exception as e:
        logger.error(f"Error iniciando el sistema: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # Detener Lavalink al salir
        stop_lavalink()

if __name__ == "__main__":
    try:
        # Ejecutar el bot
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSistema detenido manualmente.")
        # Asegurarse de detener Lavalink
        stop_lavalink()
    except Exception as e:
        print(f"Error fatal: {e}")
        # Asegurarse de detener Lavalink
        stop_lavalink()
