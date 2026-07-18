
__all__ = ['plata', 'trabajo', 'energia', 'artista', 'chef', 'hacker', 'mecanico', 'banco', 'prestigio']

# Esta función permite cargar todos los cogs del módulo de una vez
async def setup(bot):
    from .niveles_trabajo import setup_db
    from src.db import init_energia_db
    try:
        setup_db()
        print("Job levels database tables initialized successfully")
    except Exception as e:
        print(f"Error initializing job levels database: {e}")
        
    try:
        init_energia_db()
        print("Energy database columns initialized successfully")
    except Exception as e:
        print(f"Error initializing energy database: {e}")

    from .plata import setup as setup_plata
    from .trabajo import setup as setup_trabajo
    from .energia import setup as setup_energia
    
    try:
        await setup_plata(bot)
        print("Economy plata cog loaded successfully")
    except Exception as e:
        print(f"Error loading economy plata cog: {e}")
    
    try:
        await setup_trabajo(bot)
        print("Economy trabajo cog loaded successfully")
    except Exception as e:
        print(f"Error loading economy trabajo cog: {e}")
    
    try:
        await setup_energia(bot)
        print("Economy energia cog loaded successfully")
    except Exception as e:
        print(f"Error loading economy energia cog: {e}")

    from .banco import setup as setup_banco
    try:
        await setup_banco(bot)
        print("Banco Central cog loaded successfully")
    except Exception as e:
        print(f"Error loading Banco Central cog: {e}")

    from .prestigio import setup as setup_prestigio
    try:
        await setup_prestigio(bot)
        print("Prestigio cog loaded successfully")
    except Exception as e:
        print(f"Error loading Prestigio cog: {e}")

    from .flex import setup as setup_flex
    try:
        await setup_flex(bot)
        print("Flex cog loaded successfully")
    except Exception as e:
        print(f"Error loading Flex cog: {e}")

