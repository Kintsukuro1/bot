"""
Módulo de comandos de tienda para el bot de Discord.
Proporciona sistema de compras y tiendas con la moneda virtual del servidor.

Comandos principales:
- tienda: Muestra los productos disponibles para comprar
- comprar_mejora: Compra mejoras para los juegos y trabajos
- blackmarket: Tienda de mercado negro con productos especiales
"""

__all__ = ['tienda', 'comprar_mejora', 'blackmarket']

# Esta función permite cargar todos los cogs del módulo de una vez
async def setup(bot):
    from .tienda import setup as setup_tienda
    from .comprar_mejora import setup as setup_comprar_mejora
    from .blackmarket import setup as setup_blackmarket
    
    try:
        await setup_tienda(bot)
        print("Shop tienda cog loaded successfully")
    except Exception as e:
        print(f"Error loading shop tienda cog: {e}")
    
    try:
        await setup_comprar_mejora(bot)
        print("Shop comprar_mejora cog loaded successfully")
    except Exception as e:
        print(f"Error loading shop comprar_mejora cog: {e}")
        
    try:
        await setup_blackmarket(bot)
        print("Shop blackmarket cog loaded successfully")
    except Exception as e:
        print(f"Error loading shop blackmarket cog: {e}")