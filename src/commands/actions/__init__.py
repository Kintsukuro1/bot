
__all__ = ['daily', 'regalar', 'robar']

# Esta función permite cargar todos los cogs del módulo de una vez
async def setup(bot):
    from .daily import setup as setup_daily
    from .regalar import setup as setup_regalar
    from .robar import setup as setup_robar
    
    try:
        await setup_daily(bot)
        print("Actions daily cog loaded successfully")
    except Exception as e:
        print(f"Error loading actions daily cog: {e}")
    
    try:
        await setup_regalar(bot)
        print("Actions regalar cog loaded successfully")
    except Exception as e:
        print(f"Error loading actions regalar cog: {e}")

    try:
        await setup_robar(bot)
        print("Actions robar cog loaded successfully")
    except Exception as e:
        print(f"Error loading actions robar cog: {e}")
