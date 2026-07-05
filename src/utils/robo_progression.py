"""Progresión de nivel para el sistema de robar."""

MAX_THIEF_LEVEL = 25
THIEF_XP_BASE = 1000
THIEF_XP_FACTOR = 1.35
ROBO_COOLDOWN_MINUTES = 15
ROBO_COOLDOWN_MIN_MINUTES = 6

THIEF_RANKS = (
    (1, "Carterista"),
    (3, "Ladrón Callejero"),
    (5, "Bandido"),
    (8, "Asaltante"),
    (10, "Maestro del Hurto"),
    (15, "Sombra"),
    (20, "Fantasma"),
    (25, "Leyenda del Crimen"),
)

THIEF_MILESTONES = {
    2: "+3% probabilidad de éxito",
    5: "+10% botín extra y -2.5 min de cooldown",
    10: "+20% botín extra, +15% éxito y multas reducidas",
    15: "+30% botín extra y -7.5 min de cooldown",
    20: "+40% botín extra, +30% éxito y rango Fantasma",
    25: "Máximo poder: bonificaciones al tope",
}


def get_rank_name(level):
    rank = "Carterista"
    for min_level, name in THIEF_RANKS:
        if level >= min_level:
            rank = name
    return rank


def calc_xp_needed(level):
    if level >= MAX_THIEF_LEVEL:
        return 0
    return int(THIEF_XP_BASE * (THIEF_XP_FACTOR ** (level - 1)))


def calc_xp_from_robbery(stolen_amount):
    return max(1, int(stolen_amount * 0.10))


def get_thief_bonuses(level):
    level = max(1, min(level, MAX_THIEF_LEVEL))
    tier = level - 1
    return {
        "prob_bonus": min(30, int(tier * 1.5)),
        "loot_bonus_pct": min(0.40, tier * 0.02),
        "penalty_reduction": min(0.50, tier * 0.02),
        "cooldown_reduction_secs": min(540, tier * 30),
    }


def get_cooldown_minutes(level):
    bonuses = get_thief_bonuses(level)
    reduced_secs = bonuses["cooldown_reduction_secs"]
    cooldown_secs = max(ROBO_COOLDOWN_MIN_MINUTES * 60, ROBO_COOLDOWN_MINUTES * 60 - reduced_secs)
    return cooldown_secs / 60


def apply_thief_xp(current_level, current_xp, xp_gained):
    level = max(1, min(current_level, MAX_THIEF_LEVEL))
    xp = current_xp + xp_gained
    previous_level = level
    leveled_up = False

    while level < MAX_THIEF_LEVEL:
        needed = calc_xp_needed(level)
        if xp >= needed:
            xp -= needed
            level += 1
            leveled_up = True
        else:
            break

    return {
        "level": level,
        "xp": xp,
        "leveled_up": leveled_up,
        "leveled_down": False,
        "previous_level": previous_level,
        "xp_gained": xp_gained,
        "xp_lost": 0,
        "xp_for_next": calc_xp_needed(level),
        "rank": get_rank_name(level),
    }


def remove_thief_xp(current_level, current_xp, xp_lost):
    """Reduce XP al fallar un robo.
    - Solo se pierde el 50% de la XP que se habría ganado.
    - NUNCA se baja de nivel: la XP se reduce hasta 0 en el nivel actual.
    """
    level = max(1, min(current_level, MAX_THIEF_LEVEL))
    previous_level = level
    # Solo perder la mitad de la XP
    effective_loss = max(1, xp_lost // 2)
    xp = max(0, current_xp - effective_loss)

    return {
        "level": level,
        "xp": xp,
        "leveled_up": False,
        "leveled_down": False,  # Nunca se baja de nivel
        "previous_level": previous_level,
        "xp_gained": 0,
        "xp_lost": effective_loss,
        "xp_for_next": calc_xp_needed(level),
        "rank": get_rank_name(level),
    }


def get_protection_hours(victim_balance):
    """Calcula las horas de protección post-robo según el saldo de la víctima.
    Los ricos reciben más protección (robos son más raros pero más lucrativos).
    Los pobres reciben menos protección (no vale la pena robarles de todas formas).
    """
    if victim_balance >= 100_000:
        return 6.0
    elif victim_balance >= 25_000:
        return 4.0
    elif victim_balance >= 5_000:
        return 2.0
    else:
        return 1.0


def calcular_robo_dinamico(saldo_ladron, saldo_victima, thief_level):
    """Calcula dinámicamente los parámetros del robo basándose en la diferencia
    de riqueza entre ladrón y víctima.

    Filosofía:
    - Robar a ricos → alto riesgo, alta recompensa, baja penalización al fallar
    - Robar a similares → riesgo medio, recompensa media
    - Robar a pobres → bajo riesgo, baja recompensa, alta penalización al fallar

    Returns:
        dict con: porcentaje_robo, prob_exito, penalizacion_pct, tier_nombre, tier_emoji, tier_desc
    """
    import random

    ratio = saldo_victima / max(saldo_ladron, 1)
    bonuses = get_thief_bonuses(thief_level)

    if ratio > 3.0:
        # Víctima MUCHO más rica — "Golpe al Magnate"
        pct_min, pct_max = 10, 15
        prob_min, prob_max = 35, 50
        penal_min, penal_max = 3, 6
        tier_nombre = "Golpe al Magnate"
        tier_emoji = "💎"
        tier_desc = "Objetivo blindado. Alto botín si lo logras."
    elif ratio > 1.5:
        # Víctima más rica — "Asalto Táctico"
        pct_min, pct_max = 7, 10
        prob_min, prob_max = 45, 58
        penal_min, penal_max = 6, 10
        tier_nombre = "Asalto Táctico"
        tier_emoji = "🎯"
        tier_desc = "Objetivo con buena seguridad. Riesgo calculado."
    elif ratio > 0.5:
        # Riqueza similar — "Robo Callejero"
        pct_min, pct_max = 5, 8
        prob_min, prob_max = 48, 58
        penal_min, penal_max = 8, 12
        tier_nombre = "Robo Callejero"
        tier_emoji = "🔪"
        tier_desc = "Están parejos. El que se descuide pierde."
    else:
        # Víctima más pobre — "Hurto Menor"
        pct_min, pct_max = 2, 5
        prob_min, prob_max = 60, 72
        penal_min, penal_max = 12, 18
        tier_nombre = "Hurto Menor"
        tier_emoji = "🐀"
        tier_desc = "Objetivo fácil pero poco botín. ¿Vale la pena el riesgo?"

    # Calcular valores con algo de varianza
    porcentaje_robo = random.uniform(pct_min, pct_max)
    prob_exito = random.uniform(prob_min, prob_max)
    penalizacion_pct = random.uniform(penal_min, penal_max)

    # Aplicar bonificaciones del nivel de ladrón
    porcentaje_robo += bonuses["loot_bonus_pct"] * 5  # Máx +2% extra al porcentaje
    prob_exito += bonuses["prob_bonus"]  # Máx +30% extra a la probabilidad
    penalizacion_pct *= (1 - bonuses["penalty_reduction"])  # Reducir penalización

    # Clampear valores
    porcentaje_robo = max(1.0, min(20.0, porcentaje_robo))
    prob_exito = max(15.0, min(85.0, prob_exito))
    penalizacion_pct = max(2.0, min(25.0, penalizacion_pct))

    return {
        "porcentaje_robo": round(porcentaje_robo, 1),
        "prob_exito": round(prob_exito, 1),
        "penalizacion_pct": round(penalizacion_pct, 1),
        "tier_nombre": tier_nombre,
        "tier_emoji": tier_emoji,
        "tier_desc": tier_desc,
    }


def format_progress_bar(current_xp, needed_xp, size=10):
    if needed_xp <= 0:
        return "█" * size + " MAX"
    filled = min(size, int((current_xp / needed_xp) * size))
    return "█" * filled + "░" * (size - filled)


def get_bad_luck_bonus(fallos_consecutivos):
    """Calcula bonificaciones por racha de mala suerte.
    Incentiva a seguir intentando después de varios fallos seguidos.

    Returns:
        dict con: prob_bonus (int), penalty_mult (float), descripcion (str|None)
    """
    if fallos_consecutivos >= 4:
        return {
            "prob_bonus": 15,
            "penalty_mult": 0.50,  # multa reducida al 50%
            "descripcion": f"💫 Racha de mala suerte ({fallos_consecutivos} fallos): +15% prob, multas -50%",
        }
    elif fallos_consecutivos >= 3:
        return {
            "prob_bonus": 10,
            "penalty_mult": 0.75,  # multa reducida al 75%
            "descripcion": f"💫 Racha de mala suerte ({fallos_consecutivos} fallos): +10% prob, multas -25%",
        }
    elif fallos_consecutivos >= 2:
        return {
            "prob_bonus": 5,
            "penalty_mult": 1.0,
            "descripcion": f"💫 Mala racha ({fallos_consecutivos} fallos): +5% prob",
        }
    return {"prob_bonus": 0, "penalty_mult": 1.0, "descripcion": None}

