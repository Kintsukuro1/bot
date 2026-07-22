__all__ = ['duelo', 'raid', 'aventura', 'poblado']

async def setup(bot):
    from .duelo import setup as setup_duelo
    from .raid import setup as setup_raid
    from .aventura import setup as setup_aventura
    from .poblado import setup as setup_poblado

    await setup_duelo(bot)
    await setup_raid(bot)
    await setup_aventura(bot)
    await setup_poblado(bot)
