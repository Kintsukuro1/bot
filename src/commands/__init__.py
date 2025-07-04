
# Añadir el directorio principal al PYTHONPATH para poder importar 'src'
import sys
import os
# Obtener la ruta al directorio 'discord-bot'
base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if base_path not in sys.path:
    sys.path.insert(0, base_path)

__all__ = ['music', 'economy', 'casino', 'general', 'actions', 'moderation', 'shop']

# Esta función permite cargar todos los módulos de comandos de una vez
async def setup(bot):
    from .music import setup as setup_music
    from .economy import setup as setup_economy
    from .casino import setup as setup_casino
    from .general import setup as setup_general
    from .actions import setup as setup_actions
    from .moderation import setup as setup_moderation
    from .shop import setup as setup_shop
    
    try:
        await setup_music(bot)
        print("Music module loaded successfully")
    except Exception as e:
        print(f"Error loading music module: {e}")
    
    try:
        await setup_economy(bot)
        print("Economy module loaded successfully")
    except Exception as e:
        print(f"Error loading economy module: {e}")
        
    try:
        await setup_casino(bot)
        print("Casino module loaded successfully")
    except Exception as e:
        print(f"Error loading casino module: {e}")
        
    try:
        await setup_general(bot)
        print("General module loaded successfully")
    except Exception as e:
        print(f"Error loading general module: {e}")
        
    try:
        await setup_actions(bot)
        print("Actions module loaded successfully")
    except Exception as e:
        print(f"Error loading actions module: {e}")
        
    try:
        await setup_moderation(bot)
        print("Moderation module loaded successfully")
    except Exception as e:
        print(f"Error loading moderation module: {e}")
        
    try:
        await setup_shop(bot)
        print("Shop module loaded successfully")
    except Exception as e:
        print(f"Error loading shop module: {e}")
