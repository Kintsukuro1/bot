
__all__ = ['duelo', 'raid']

async def setup(bot):
    from .duelo import setup as setup_duelo
    from .raid import setup as setup_raid
    await setup_duelo(bot)
    await setup_raid(bot)
