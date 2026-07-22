
__all__ = [
    'blackjack',
    'casino_info',
    'casino_war',
    'coinflip',
    'crash',
    'higher_lower',
    'horse_race',
    'liars_dice',
    'loto',
    'mines',
    'plinko',
    'provably_fair_cmd',
    'roulette',
    'rps_bet',
    'russian_roulette',
    'slots',
]

async def setup(bot):
    from .blackjack import setup as setup_blackjack
    from .casino_info import setup as setup_casino_info
    from .casino_war import setup as setup_casino_war
    from .coinflip import setup as setup_coinflip
    from .crash import setup as setup_crash
    from .higher_lower import setup as setup_higher_lower
    from .horse_race import setup as setup_horse_race
    from .liars_dice import setup as setup_liars_dice
    from .loto import setup as setup_loto
    from .mines import setup as setup_mines
    from .plinko import setup as setup_plinko
    from .provably_fair_cmd import setup as setup_provably_fair
    from .roulette import setup as setup_roulette
    from .rps_bet import setup as setup_rps_bet
    from .russian_roulette import setup as setup_russian_roulette
    from .slots import setup as setup_slots

    await setup_blackjack(bot)
    await setup_casino_info(bot)
    await setup_casino_war(bot)
    await setup_coinflip(bot)
    await setup_crash(bot)
    await setup_higher_lower(bot)
    await setup_horse_race(bot)
    await setup_liars_dice(bot)
    await setup_loto(bot)
    await setup_mines(bot)
    await setup_plinko(bot)
    await setup_provably_fair(bot)
    await setup_roulette(bot)
    await setup_rps_bet(bot)
    await setup_russian_roulette(bot)
    await setup_slots(bot)

