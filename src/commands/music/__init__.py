
__all__ = ['play', 'stop', 'pause', 'resume', 'skip', 'leave', 'clear']

# Esta función permite cargar todos los cogs del módulo de una vez
async def setup(bot):
    import logging
    logger = logging.getLogger("discord_bot")
    logger.info("[MUSIC] Intentando cargar módulos de música")
    
    # Importar wavelink para comprobar si está disponible
    try:
        import wavelink
        logger.info(f"[MUSIC] Wavelink detectado (versión {wavelink.__version__})")
    except ImportError:
        logger.error("[MUSIC] Wavelink no está instalado. Las funciones de música no estarán disponibles.")
        logger.info("[MUSIC] Para instalar wavelink: pip install wavelink==2.6.2")
        print("❌ Los comandos de música requieren wavelink. Instala con: pip install wavelink==2.6.2")
        return
    
    # Comprobar si Lavalink está disponible
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        if s.connect_ex(('localhost', 2444)) != 0:
            logger.warning("[MUSIC] Lavalink no está en ejecución en el puerto 2444")
            logger.warning("[MUSIC] Los comandos de música estarán disponibles pero podrían fallar")
            print("⚠️ Lavalink no detectado. Los comandos de música podrían no funcionar correctamente.")
    
    # Importar módulos de música
    from .play import setup as setup_play
    from .stop import setup as setup_stop
    from .pause import setup as setup_pause
    from .resume import setup as setup_resume
    from .skip import setup as setup_skip
    
    # Importar también los módulos adicionales mencionados en __all__
    try:
        from .leave import setup as setup_leave
    except ImportError:
        setup_leave = None
        
    try:
        from .clear import setup as setup_clear
    except ImportError:
        setup_clear = None
    
    # Cargar solo los comandos que ya están implementados
    cogs_loaded = 0
    
    # Función para cargar un módulo específico
    async def load_music_module(setup_func, name):
        nonlocal cogs_loaded
        try:
            await setup_func(bot)
            print(f"✅ Music {name} cog loaded successfully")
            logger.info(f"[MUSIC] Cog {name} cargado correctamente")
            cogs_loaded += 1
            return True
        except Exception as e:
            print(f"❌ Error loading music {name} cog: {e}")
            logger.error(f"[MUSIC] Error cargando módulo {name}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    # Cargar los módulos principales
    await load_music_module(setup_play, "play")
    await load_music_module(setup_stop, "stop")
    await load_music_module(setup_pause, "pause")
    await load_music_module(setup_resume, "resume")
    await load_music_module(setup_skip, "skip")
    
    # Cargar los módulos adicionales si están disponibles
    if 'setup_leave' in locals() and setup_leave:
        await load_music_module(setup_leave, "leave")
    
    if 'setup_clear' in locals() and setup_clear:
        await load_music_module(setup_clear, "clear")
        
    # Crear los archivos faltantes si es necesario
    if cogs_loaded < 5:
        logger.warning(f"[MUSIC] Solo se cargaron {cogs_loaded}/7 módulos de música")
        print(f"⚠️ Solo se cargaron {cogs_loaded}/7 módulos de música. Algunos comandos podrían no estar disponibles.")
