
import logging

logger = logging.getLogger(__name__)

__all__ = ['banco', 'bolsa', 'energia', 'flex', 'pets', 'plata', 'prestigio', 'trabajo']

async def setup(bot):
    from .niveles_trabajo import setup_db
    from src.db import init_energia_db
    try:
        setup_db()
        logger.info("Job levels database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing job levels database: {e}")
        
    try:
        init_energia_db()
        logger.info("Energy database columns initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing energy database: {e}")

    from .banco import setup as setup_banco
    from .bolsa import setup as setup_bolsa
    from .energia import setup as setup_energia
    from .flex import setup as setup_flex
    from .pets import setup as setup_pets
    from .plata import setup as setup_plata
    from .prestigio import setup as setup_prestigio
    from .trabajo import setup as setup_trabajo

    await setup_banco(bot)
    await setup_bolsa(bot)
    await setup_energia(bot)
    await setup_flex(bot)
    await setup_pets(bot)
    await setup_plata(bot)
    await setup_prestigio(bot)
    await setup_trabajo(bot)


