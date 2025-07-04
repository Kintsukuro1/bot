import os
import sys
import asyncio
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv
from typing import Optional

# Agregar el directorio raíz al PYTHONPATH para permitir importaciones absolutas desde 'src'
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Configuración avanzada de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("discord_bot")

# Cargar variables de entorno
# Intenta cargar el archivo .env desde diferentes ubicaciones
env_paths = [
    os.path.join(os.path.dirname(__file__), '.env'),  # src/.env
    os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),  # discord-bot/.env
]

env_loaded = False
for env_path in env_paths:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info(f"[CONFIG] Cargando variables de entorno desde: {env_path}")
        env_loaded = True
        break

if not env_loaded:
    logger.warning("[CONFIG] No se encontró archivo .env. Intentando cargar variables de entorno del sistema.")
    load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('DISCORD_PREFIX', '!')
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Validar token inmediatamente
if TOKEN:
    if len(TOKEN) > 50:
        logger.info(f"[TOKEN] Token cargado: {TOKEN[:6]}...{TOKEN[-4:]}")
    else:
        logger.warning("[TOKEN] El token cargado parece ser demasiado corto, puede no ser válido")
else:
    logger.error("[TOKEN] No se pudo cargar el token de Discord del archivo .env")

if DEBUG:
    logger.setLevel(logging.DEBUG)
    logger.debug("Modo DEBUG activado")

# Configuración de intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Instancia del bot
bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None
)

async def load_cogs():
    """Carga automática de cogs con manejo de errores mejorado."""
    cogs_dir = os.path.join(os.path.dirname(__file__), 'commands')
    loaded_count = 0
    failed_count = 0
    
    # Archivos a excluir (módulos auxiliares)
    exclude_files = {
        '__init__.py',
        'hacker.py', 'chef.py', 'artista.py', 'mecanico.py',  # Módulos auxiliares de trabajo
        'black_market_items.py'  # Módulos de datos, no cogs
    }
    
    # Primero, intentar cargar todos los paquetes de categorías directamente
    category_dirs = [
        d for d in os.listdir(cogs_dir) 
        if os.path.isdir(os.path.join(cogs_dir, d)) and not d.startswith('__')
    ]
    
    for category in category_dirs:
        try:
            logger.info(f"[LOAD] Intentando cargar categoría: src.commands.{category}")
            await bot.load_extension(f"src.commands.{category}")
            loaded_count += 1
        except Exception as e:
            logger.debug(f"[INFO] Categoría {category} no tiene setup colectivo, cargando módulos individuales: {e}")
            
            # Si falla, cargar cogs individuales en esa categoría
            category_path = os.path.join(cogs_dir, category)
            for file in os.listdir(category_path):
                if file.endswith('.py') and file not in exclude_files and not file.startswith('__'):
                    cog_name = f"src.commands.{category}.{file[:-3]}"
                    try:
                        await bot.load_extension(cog_name)
                        loaded_count += 1
                        logger.info(f"[LOAD] Cog cargado: {cog_name}")
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"[ERROR] Error cargando {cog_name}: {e}")
                        if DEBUG:
                            import traceback
                            traceback.print_exc()
    
    logger.info(f"[STATUS] Cogs cargados: {loaded_count} | Fallidos: {failed_count}")

@bot.event
async def on_ready():
    """Evento cuando el bot está listo, con información detallada."""
    try:
        # Método moderno para mostrar información del usuario (compatible con Discord nuevo)
        if bot.user:
            logger.info(f"[READY] ¡Bot conectado! Usuario: {bot.user.name} (ID: {bot.user.id})")
        else:
            logger.info("[READY] ¡Bot conectado! No se pudo obtener información del usuario.")
    except Exception as e:
        logger.info(f"[READY] ¡Bot conectado! ID: {bot.user.id if bot.user else 'Desconocido'}")
        if DEBUG:
            logger.debug(f"Error al obtener información del usuario: {e}")
    
    # Información de los servidores
    guild_count = len(bot.guilds)
    logger.info(f"[SERVERS] Conectado a {guild_count} servidores:")
    for guild in bot.guilds:
        logger.info(f"  - {guild.name} (ID: {guild.id}) | Miembros: {len(guild.members)}")

    # Contar usuarios únicos en todos los servidores
    unique_user_ids = set()
    for guild in bot.guilds:
        for member in guild.members:
            unique_user_ids.add(member.id)
    user_count = len(unique_user_ids)
    logger.info(f"[USERS] Sirviendo a {user_count} usuarios únicos")

    # Sincronizar comandos slash
    try:
        synced = await bot.tree.sync()
        logger.info(f"[SYNC] {len(synced)} comandos slash sincronizados")
    except Exception as e:
        logger.error(f"[ERROR] Error sincronizando slash commands: {e}")
        if DEBUG:
            import traceback
            logger.error(traceback.format_exc())
    
    # Inicializar wavelink después de que el bot esté listo
    try:
        import wavelink
        logger.info("[LAVALINK] Intentando conectar a Lavalink...")
        
        # Verificar si Lavalink está disponible antes de intentar conectar
        import socket
        lavalink_port = 2444
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', lavalink_port))
        s.close()
        
        if result != 0:
            logger.warning("[LAVALINK] Servidor Lavalink no detectado en puerto 2444. Las funciones musicales no estarán disponibles.")
            logger.warning("[LAVALINK] Para usar comandos de música, debes iniciar Lavalink primero.")
        else:
            # Usar el puerto correcto según application.yml
            node = wavelink.Node(uri='http://localhost:2444', password='youshallnotpass')
            await wavelink.Pool.connect(client=bot, nodes=[node])
            logger.info("[LAVALINK] Conectado exitosamente a servidor Lavalink")
    except ImportError:
        logger.info("[LAVALINK] wavelink no está instalado. Las funciones musicales no estarán disponibles.")
    except ConnectionRefusedError:
        logger.warning("[LAVALINK] No se pudo conectar al servidor Lavalink. Las funciones musicales no estarán disponibles.")
    except Exception as e:
        logger.warning(f"[LAVALINK] Error inicializando Wavelink: {e}")
        logger.warning("[LAVALINK] Las funciones musicales no estarán disponibles.")
    
    logger.info("=" * 50)
    logger.info("[STATUS] Bot listo y funcionando")

@bot.event
async def on_command_error(ctx, error):
    """Manejo mejorado de errores para comandos tradicionales."""
    if isinstance(error, commands.CommandNotFound):
        logger.debug(f"CommandNotFound: {error} (invoked by {ctx.author} in #{ctx.channel})")
        return
    
    error_messages = {
        commands.MissingRequiredArgument: f"Faltan argumentos. Usa: `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`",
        commands.BadArgument: f"Argumento inválido. Usa: `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`",
        commands.MissingPermissions: "No tienes permisos para este comando.",
        commands.BotMissingPermissions: "El bot no tiene los permisos necesarios."
    }
    
    for error_type, message in error_messages.items():
        if isinstance(error, error_type):
            await ctx.send(f"❌ **Error:** {message}")
            return
    
    # Manejo de errores de red
    if (
        isinstance(error, ConnectionResetError)
        or (isinstance(error, OSError) and getattr(error, "winerror", None) == 64)
    ):
        logger.error(f"[NETWORK] Error de conexión: {error}")
        await ctx.send("🌐 **Error de red:** Intenta de nuevo más tarde.")
        return
    
    # Error genérico
    logger.error(f"[ERROR] {type(error).__name__}: {error}")
    await ctx.send("❌ **Error inesperado:** Contacta al administrador.")

@bot.command(name='reload')
@commands.is_owner()
async def reload_cog(ctx, cog: Optional[str] = None):
    """Recarga un cog específico o todos los cogs."""
    if cog:
        try:
            await bot.reload_extension(f"commands.{cog}")
            await ctx.send(f"✅ **Recargado:** `{cog}`")
            logger.info(f"[RELOAD] Cog recargado: {cog}")
        except Exception as e:
            await ctx.send(f"❌ **Error:** {e}")
            logger.error(f"[ERROR] Error recargando {cog}: {e}")
    else:
        reloaded = failed = 0
        for ext in list(bot.extensions.keys()):
            try:
                await bot.reload_extension(ext)
                reloaded += 1
                logger.info(f"[RELOAD] Recargado: {ext}")
            except Exception as e:
                failed += 1
                logger.error(f"[ERROR] Error recargando {ext}: {e}")
        
        await ctx.send(f"✅ **Reload completado:** {reloaded} correctos, {failed} fallidos")

@bot.tree.error
async def on_slash_error(interaction: discord.Interaction, error):
    """Manejo de errores para comandos slash."""
    command = interaction.command.name if interaction.command else "desconocido"
    
    if isinstance(error, discord.app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ **Enfriamiento:** Espera {error.retry_after:.1f}s", 
            ephemeral=True
        )
        return
    
    if isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ **Error:** Permisos insuficientes.", 
            ephemeral=True
        )
        return
    
    logger.error(f"[SLASH ERROR] {command}: {type(error).__name__} - {error}")
    await interaction.response.send_message(
        "❌ **Error inesperado**", 
        ephemeral=True
    )

# Eliminar el setup_hook que podría estar causando problemas
# Manejaremos la inicialización de wavelink en el evento on_ready

async def main():
    """Función principal con manejo de reconexión."""
    if not TOKEN:
        logger.error("[FATAL] No se encontró TOKEN en .env")
        return
    
    # Verificar que el token tenga el formato correcto
    if len(TOKEN) < 50 or "." not in TOKEN:
        logger.error("[FATAL] El token de Discord parece no ser válido. Verifique su formato en el archivo .env")
        return
        
    logger.info(f"[CONFIG] Prefix: {PREFIX}, Debug: {DEBUG}")
    
    # Verificar si Lavalink está disponible
    try:
        import socket
        lavalink_port = 2444  # Puerto según application.yml
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', lavalink_port))
        s.close()
        if result == 0:
            logger.info("[LAVALINK] Servidor Lavalink detectado en puerto 2444")
        else:
            logger.warning("[LAVALINK] Servidor Lavalink no detectado en puerto 2444. Las funciones musicales pueden no estar disponibles.")
    except Exception as e:
        logger.warning(f"[LAVALINK] No se pudo verificar el estado del servidor Lavalink: {e}")
    
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[INIT] Iniciando bot (Intento {attempt}/{max_retries})")
            await load_cogs()
            logger.info("[CONNECT] Intentando conectar a Discord...")
            # Ejecutar sin cerrar automáticamente al final
            await bot.start(TOKEN)
            # Si llegamos aquí, es porque el bot se desconectó normalmente
            logger.info("[SHUTDOWN] Bot desconectado normalmente")
            break
        except discord.LoginFailure as e:
            logger.error(f"[FATAL] Token inválido: {e}")
            logger.error("[HINT] Verifique que su token en .env sea correcto y esté actualizado")
            break
        except KeyboardInterrupt:
            logger.error("[FATAL] Interrupción manual")
            break
        except (ConnectionResetError, discord.ConnectionClosed) as e:
            logger.error(f"[NETWORK] Error de conexión: {e}")
            logger.error("[HINT] Verifique su conexión a Internet")
            if attempt < max_retries:
                logger.info(f"[RETRY] Reintentando en {retry_delay * attempt} segundos...")
                await asyncio.sleep(retry_delay * attempt)
            else:
                logger.error("[FATAL] Máximo de reintentos alcanzado")
        except Exception as e:
            logger.error(f"[FATAL] Error inesperado: {e}")
            if DEBUG:
                import traceback
                logger.error("[DEBUG] Detalles del error:")
                logger.error(traceback.format_exc())
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[SHUTDOWN] Bot detenido manualmente")
    except Exception as e:
        logger.error(f"[FATAL] Error en la ejecución: {e}")