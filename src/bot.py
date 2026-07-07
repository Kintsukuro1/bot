import os
import sys
import asyncio
import functools
import contextvars

# Polyfill para asyncio.to_thread (necesario para Python 3.8 o inferior)
if not hasattr(asyncio, 'to_thread'):
    async def to_thread(func, /, *args, **kwargs):
        loop = asyncio.get_running_loop()
        ctx = contextvars.copy_context()
        func_call = functools.partial(ctx.run, func, *args, **kwargs)
        return await loop.run_in_executor(None, func_call)
    asyncio.to_thread = to_thread

import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv
from typing import Optional
import configparser

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
        logger.info("[TOKEN] Token cargado correctamente")
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

# Leer configuración desde config.ini
config = configparser.ConfigParser()
config_file = os.path.join(BASE_DIR, 'config.ini')

# Si el archivo de configuración existe, leerlo
if os.path.exists(config_file):
    config.read(config_file)
    logger.info(f"[CONFIG] Cargando configuración desde: {config_file}")
else:
    logger.warning(f"[CONFIG] No se encontró el archivo de configuración: {config_file}")

# La configuración de módulos ahora se carga en load_cogs()

async def load_cogs():
    """Carga automática de cogs con manejo de errores mejorado."""
    cogs_dir = os.path.join(os.path.dirname(__file__), 'commands')
    loaded_count = 0
    failed_count = 0
    
    # Cargar configuración de módulos
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
    
    # Módulos activos por defecto
    enabled_modules = {
        "general": True,
        "economy": True, 
        "moderation": True,
        "music": False,  # Música desactivada por defecto
        "shop": True,
        "casino": True,
        "actions": True
    }
    
    # Intentar cargar la configuración
    try:
        if os.path.exists(config_path):
            config.read(config_path)
            if 'modules' in config:
                for module, enabled in config['modules'].items():
                    enabled_modules[module] = enabled.lower() in ('true', 'yes', '1')
                logger.info(f"[CONFIG] Módulos configurados desde {config_path}")
        else:
            logger.warning(f"[CONFIG] No se encontró el archivo {config_path}, usando configuración por defecto")
    except Exception as e:
        logger.error(f"[CONFIG] Error leyendo configuración: {e}")
    
    # Mostrar módulos activados/desactivados
    for module, enabled in enabled_modules.items():
        status = "✅ ACTIVADO" if enabled else "❌ DESACTIVADO"
        logger.info(f"[MODULES] Módulo '{module}': {status}")
    
    # Archivos a excluir (módulos auxiliares)
    exclude_files = {
        '__init__.py',
        'hacker.py', 'chef.py', 'artista.py', 'mecanico.py', 'minero.py', 'pescador.py',  # Módulos auxiliares de minijuegos
        'medico.py', 'piloto.py', 'cientifico.py', 'ladron.py', 'cazarrecompensas.py',
        'niveles_trabajo.py',  # Sistema de niveles
        'black_market_items.py'  # Módulos de datos, no cogs
    }
    
    # Primero, intentar cargar todos los paquetes de categorías directamente
    category_dirs = [
        d for d in os.listdir(cogs_dir) 
        if os.path.isdir(os.path.join(cogs_dir, d)) and not d.startswith('__')
        and d in enabled_modules and enabled_modules[d]  # Solo cargar módulos activados
    ]
    
    for category in category_dirs:
        # Cargar cogs individuales en esa categoría
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

    # Sincronizar comandos slash globalmente al arrancar
    try:
        logger.info("[SYNC] Sincronizando comandos slash globalmente...")
        synced = await bot.tree.sync()
        logger.info(f"[SYNC] ¡Sincronización global completada! {len(synced)} comandos registrados.")
    except Exception as e:
        logger.error(f"[SYNC] Error al sincronizar comandos globalmente: {e}")
    
    # No se inicializa Lavalink - Funcionalidad de música desactivada
    
    logger.info("=" * 50)
    logger.info("[STATUS] Bot listo y funcionando")

ALLOWED_CHANNEL_ID = 1519533661806923866

@bot.check
async def global_prefix_check(ctx):
    # Permitir libremente en el servidor de pruebas (Little paradise)
    if ctx.guild and ctx.guild.id == 1019371540908884090:
        return True
        
    # Si no es el canal designado, bloquear sin excepciones
    if not ctx.channel or ctx.channel.id != ALLOWED_CHANNEL_ID:
        await ctx.send("Aweonao estas en otro canal que no es <#1519533661806923866>")
        return False
    return True

@bot.tree.interaction_check
async def global_interaction_check(interaction: discord.Interaction) -> bool:
    # Permitir libremente en el servidor de pruebas (Little paradise)
    if interaction.guild and interaction.guild.id == 1019371540908884090:
        return True
        
    # Si no es el canal designado, bloquear sin excepciones
    if not interaction.channel or interaction.channel.id != ALLOWED_CHANNEL_ID:
        await interaction.response.send_message("Aweonao estas en otro canal que no es <#1519533661806923866>")
        return False
    return True

LOGS_CHANNEL_ID = 1519413696206737559

async def send_command_log(ctx_or_interaction, success: bool, error_msg: Optional[str] = None):
    """Envía un log de éxito o error al canal centralizado de logs."""
    try:
        from datetime import datetime
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        
        if is_interaction:
            interaction = ctx_or_interaction
            user = interaction.user
            command_name = f"/{interaction.command.name}" if interaction.command else "desconocido"
            
            # Construir la acción: si es un comando con opciones, incluirlas en el log
            options = []
            if hasattr(interaction, "namespace") and interaction.namespace:
                for name, value in interaction.namespace:
                    options.append(f"{name}: {value}")
            options_str = f" ({', '.join(options)})" if options else ""
            action = f"Ejecución{options_str}"
            guild = interaction.guild
            channel_invoked = interaction.channel
        else:
            ctx = ctx_or_interaction
            user = ctx.author
            command_name = f"{ctx.prefix or ''}{ctx.command.name}" if ctx.command else "desconocido"
            action = f"Ejecución ({ctx.message.content})"
            guild = ctx.guild
            channel_invoked = ctx.channel

        # Formato de estado / error requerido por el usuario
        status_text = "Funcionó" if success else f"Error: {error_msg}"
        
        # Formato exacto requerido: Comando - Accion - Error
        log_message_literal = f"{command_name} - {action} - {status_text}"
            
        color = discord.Color.green() if success else discord.Color.red()
        
        embed = discord.Embed(
            title="📋 Registro de Comando",
            description=f"**Log:** `{log_message_literal}`",
            color=color,
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )
        embed.add_field(name="Usuario", value=f"{user.mention} (ID: {user.id})", inline=True)
        embed.add_field(name="Ubicación", value=f"{channel_invoked.mention if hasattr(channel_invoked, 'mention') else 'DMs'} (Server: {guild.name if guild else 'DMs'})", inline=True)

        logs_channel = bot.get_channel(LOGS_CHANNEL_ID)
        if not logs_channel:
            logs_channel = await bot.fetch_channel(LOGS_CHANNEL_ID)
            
        if logs_channel:
            await logs_channel.send(content=log_message_literal, embed=embed)
    except Exception as e:
        logger.error(f"Error al enviar log de comando al canal de Discord {LOGS_CHANNEL_ID}: {e}")

@bot.event
async def on_app_command_completion(interaction: discord.Interaction, command):
    """Loguea la finalización exitosa de comandos slash."""
    await send_command_log(interaction, success=True)

@bot.event
async def on_command_completion(ctx):
    """Loguea la finalización exitosa de comandos tradicionales."""
    await send_command_log(ctx, success=True)

@bot.event
async def on_command_error(ctx, error):
    """Manejo mejorado de errores para comandos tradicionales."""
    if isinstance(error, commands.CommandNotFound):
        logger.debug(f"CommandNotFound: {error} (invoked by {ctx.author} in #{ctx.channel})")
        return
        
    if type(error) is commands.CheckFailure:
        return
    
    # Enviar log de error al canal
    await send_command_log(ctx, success=False, error_msg=str(error))
    
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
        ext_name = None
        for ext in list(bot.extensions.keys()):
            if ext.endswith(f".{cog}") or ext.endswith(f"commands.{cog}"):
                ext_name = ext
                break
                
        if not ext_name:
            # Si no está cargada, intentamos buscar en todas las subcarpetas de src.commands
            cogs_dir = os.path.join(os.path.dirname(__file__), 'commands')
            for category in os.listdir(cogs_dir):
                if os.path.isdir(os.path.join(cogs_dir, category)) and not category.startswith('__'):
                    if os.path.exists(os.path.join(cogs_dir, category, f"{cog}.py")):
                        ext_name = f"src.commands.{category}.{cog}"
                        break
            
            if not ext_name:
                # Fallback por defecto si no lo encuentra en subcarpetas
                ext_name = f"src.commands.{cog}"
            
        try:
            # Si no estaba cargada previamente, usamos load_extension
            if ext_name not in bot.extensions:
                await bot.load_extension(ext_name)
                await ctx.send(f"✅ **Cargado (nuevo):** `{ext_name}`")
                logger.info(f"[LOAD] Cog cargado: {ext_name}")
            else:
                await bot.reload_extension(ext_name)
                await ctx.send(f"✅ **Recargado:** `{ext_name}`")
                logger.info(f"[RELOAD] Cog recargado: {ext_name}")
        except Exception as e:
            await ctx.send(f"❌ **Error:** {e}")
            logger.error(f"[ERROR] Error recargando/cargando {ext_name}: {e}")
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
    if type(error) is discord.app_commands.CheckFailure:
        return
        
    # Enviar log de error al canal
    await send_command_log(interaction, success=False, error_msg=str(error))
    
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

    if isinstance(error, discord.app_commands.BotMissingPermissions):
        missing = ", ".join(error.missing_permissions)
        await interaction.response.send_message(
            f"❌ **Error:** El bot no tiene los permisos necesarios para ejecutar este comando. Requiere: `{missing}`", 
            ephemeral=True
        )
        return
    
    logger.error(f"[SLASH ERROR] {command}: {type(error).__name__} - {error}")
    if DEBUG:
        import traceback
        logger.error("".join(traceback.format_exception(type(error), error, error.__traceback__)))
    try:
        if interaction.response.is_done():
            await interaction.followup.send("❌ **Error inesperado**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ **Error inesperado**", ephemeral=True)
    except Exception:
        pass

# No se necesita inicialización de wavelink ya que no usaremos funciones de música

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
    
    # Inicializar base de datos y crear tablas si no existen
    try:
        logger.info("[DB] Iniciando verificación/creación de la base de datos...")
        from src.db import init_db
        init_db()
    except Exception as e:
        logger.critical(f"[DB] Error crítico al inicializar la base de datos: {e}")
        return
    
    # No verificamos Lavalink ya que no lo usaremos
    
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