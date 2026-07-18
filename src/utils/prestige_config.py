from src.db import get_user_prestige_level, get_balance, set_balance, set_user_prestige_db, registrar_transaccion, db_cursor

PRESTIGE_TIERS = [
    {"level": 1, "threshold": 100_000, "title": "Prestigio I"},
    {"level": 2, "threshold": 1_500_000, "title": "Prestigio II"},
    {"level": 3, "threshold": 22_500_000, "title": "Prestigio III"},
    {"level": 4, "threshold": 337_500_000, "title": "Prestigio IV"},
    {"level": 5, "threshold": 5_062_500_000, "title": "Prestigio V"},
    {"level": 6, "threshold": 75_937_500_000, "title": "Prestigio VI"},
    {"level": 7, "threshold": 1_139_062_500_000, "title": "Prestigio VII"},
]
PRESTIGE_RESET_SEED = 10_000  # Balance tras prestigiar, no queda en 0

def get_next_prestige_tier(user_id) -> dict | None:
    """Retorna el siguiente tier alcanzable según el balance actual del usuario
    (su PrestigeLevel actual + 1), o None si ya está en el nivel máximo."""
    lvl = get_user_prestige_level(user_id)
    next_lvl = lvl + 1
    for tier in PRESTIGE_TIERS:
        if tier["level"] == next_lvl:
            return tier
    return None

def can_prestige(user_id) -> tuple:
    """Compara Balance actual contra el umbral del siguiente tier. Retorna
    (True, tier) si alcanza, (False, None) si no o si ya está al máximo."""
    next_tier = get_next_prestige_tier(user_id)
    if not next_tier:
        return False, None
    
    balance = get_balance(user_id)
    if balance >= next_tier["threshold"]:
        return True, next_tier
    return False, None

def do_prestige(user_id) -> tuple:
    """Verifica can_prestige, y si es válido: set_balance(user_id, PRESTIGE_RESET_SEED),
    incrementa PrestigeLevel en 1, actualiza FechaUltimoPrestigio. Retorna (True, mensaje
    con el título obtenido) o (False, motivo si no alcanza el umbral)."""
    with db_cursor():
        ok, tier = can_prestige(user_id)
        if not ok or not tier:
            next_tier = get_next_prestige_tier(user_id)
            if not next_tier:
                return False, "❌ Ya has alcanzado el nivel máximo de prestigio."
            return False, f"❌ No alcanzas el umbral de **{next_tier['threshold']:,}** monedas para prestigiar."
        
        balance = get_balance(user_id)
        
        # Resetear saldo
        set_balance(user_id, PRESTIGE_RESET_SEED)
        
        # Subir nivel
        set_user_prestige_db(user_id, tier["level"])
        
        # Registrar transacción
        registrar_transaccion(user_id, PRESTIGE_RESET_SEED - balance, f"Prestigio alcanzado: {tier['title']}")
        
        return True, f"✨ ¡Has ascendido a **{tier['title']}**! Tu balance ha sido restablecido a {PRESTIGE_RESET_SEED:,} monedas."


def format_username_with_prestige(user_id, display_name: str) -> str:
    """Antepone la insignia 🌟 al nombre si el usuario tiene Prestigio I o superior.

    Función síncrona — llamar dentro de un hilo (asyncio.to_thread) o en código
    ya ejecutado fuera del event loop.
    """
    if get_user_prestige_level(user_id) >= 1:
        return f"🌟 {display_name}"
    return display_name

