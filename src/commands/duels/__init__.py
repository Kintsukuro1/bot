
__all__ = ['duelo']

async def setup(bot):
    from .duelo import setup as setup_duelo
    await setup_duelo(bot)
