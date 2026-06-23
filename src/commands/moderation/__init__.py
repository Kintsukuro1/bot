"""
Módulo de comandos de moderación para el bot de Discord.
Proporciona herramientas para administrar y moderar servidores.

Comandos principales:
- purge: Elimina mensajes en masa
- mute: Silencia a un usuario
- unmute: Remueve el silencio a un usuario
- mensaje: Envía un mensaje a través del bot
- poll: Crea encuestas
- slowmode: Configura el modo lento en un canal
- specialmute: Silencio temporal con opciones avanzadas
"""

__all__ = ['purge', 'mute', 'unmute', 'mensaje', 'poll', 'slowmode', 'specialmute']

# Esta función permite cargar todos los cogs del módulo de una vez
async def setup(bot):
    from .purge import setup as setup_purge
    from .mute import setup as setup_mute
    from .unmute import setup as setup_unmute
    from .mensaje import setup as setup_mensaje
    from .poll import setup as setup_poll
    from .slowmode import setup as setup_slowmode
    from .specialmute import setup as setup_specialmute
    
    try:
        await setup_purge(bot)
        print("Moderation purge cog loaded successfully")
    except Exception as e:
        print(f"Error loading moderation purge cog: {e}")
    
    try:
        await setup_mute(bot)
        print("Moderation mute cog loaded successfully")
    except Exception as e:
        print(f"Error loading moderation mute cog: {e}")
        
    try:
        await setup_unmute(bot)
        print("Moderation unmute cog loaded successfully")
    except Exception as e:
        print(f"Error loading moderation unmute cog: {e}")
        
    try:
        await setup_mensaje(bot)
        print("Moderation mensaje cog loaded successfully")
    except Exception as e:
        print(f"Error loading moderation mensaje cog: {e}")
        
    try:
        await setup_poll(bot)
        print("Moderation poll cog loaded successfully")
    except Exception as e:
        print(f"Error loading moderation poll cog: {e}")
        
    try:
        await setup_slowmode(bot)
        print("Moderation slowmode cog loaded successfully")
    except Exception as e:
        print(f"Error loading moderation slowmode cog: {e}")
        
    try:
        await setup_specialmute(bot)
        print("Moderation specialmute cog loaded successfully")
    except Exception as e:
        print(f"Error loading moderation specialmute cog: {e}")