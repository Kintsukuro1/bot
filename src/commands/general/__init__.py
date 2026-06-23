
__all__ = ['serverinfo', 'userinfo', 'avatar', 'botinfo', 'sync', 'difficulty_stats', 'historial', 'top']

# Esta función permite cargar todos los cogs del módulo de una vez
async def setup(bot):
    from .serverinfo import setup as setup_serverinfo
    from .userinfo import setup as setup_userinfo
    from .avatar import setup as setup_avatar
    from .botinfo import setup as setup_botinfo
    from .sync import setup as setup_sync
    from .difficulty_stats import setup as setup_difficulty_stats
    from .historial import setup as setup_historial
    from .top import setup as setup_top
    
    try:
        await setup_serverinfo(bot)
        print("General serverinfo cog loaded successfully")
    except Exception as e:
        print(f"Error loading general serverinfo cog: {e}")
    
    try:
        await setup_userinfo(bot)
        print("General userinfo cog loaded successfully")
    except Exception as e:
        print(f"Error loading general userinfo cog: {e}")
        
    try:
        await setup_avatar(bot)
        print("General avatar cog loaded successfully")
    except Exception as e:
        print(f"Error loading general avatar cog: {e}")
        
    try:
        await setup_botinfo(bot)
        print("General botinfo cog loaded successfully")
    except Exception as e:
        print(f"Error loading general botinfo cog: {e}")
        
    try:
        await setup_sync(bot)
        print("General sync cog loaded successfully")
    except Exception as e:
        print(f"Error loading general sync cog: {e}")
        
    try:
        await setup_difficulty_stats(bot)
        print("General difficulty_stats cog loaded successfully")
    except Exception as e:
        print(f"Error loading general difficulty_stats cog: {e}")
        
    try:
        await setup_historial(bot)
        print("General historial cog loaded successfully")
    except Exception as e:
        print(f"Error loading general historial cog: {e}")

    try:
        await setup_top(bot)
        print("General top cog loaded successfully")
    except Exception as e:
        print(f"Error loading top sync cog: {e}")