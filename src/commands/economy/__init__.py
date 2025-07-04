
__all__ = ['plata', 'trabajo', 'energia', 'artista', 'chef', 'hacker', 'mecanico']

# Esta función permite cargar todos los cogs del módulo de una vez
async def setup(bot):
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
