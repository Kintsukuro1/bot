
__all__ = ['blackjack', 'coinflip', 'crash', 'higher_lower', 'slots']

# Esta función permite cargar todos los cogs del módulo de una vez
async def setup(bot):
    from .blackjack import setup as setup_blackjack
    from .coinflip import setup as setup_coinflip
    from .crash import setup as setup_crash
    from .higher_lower import setup as setup_higher_lower
    from .slots import setup as setup_slots
    
    await setup_blackjack(bot)
    await setup_coinflip(bot)
    await setup_crash(bot)
    await setup_higher_lower(bot)
    await setup_slots(bot)
