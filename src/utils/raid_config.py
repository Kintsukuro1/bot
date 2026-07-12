# ══════════════════════════════════════════════
# CONFIGURACIÓN CENTRALIZADA — SISTEMA DE RAIDS
# ══════════════════════════════════════════════

"""
7 bosses rotativos (uno por día de la semana).
La dificultad escala según la suma de niveles de los participantes.
Recompensas: solo ítems de equipo (no monedas).
"""

# ──────────────────────────────────────────────
# CONSTANTES DE RAID
# ──────────────────────────────────────────────

RAID_MIN_PLAYERS = 2          # Mínimo de jugadores para iniciar
RAID_MAX_PLAYERS = 4          # Máximo de jugadores en una raid
RAID_LOBBY_TIMEOUT = 90       # Segundos para el lobby de espera
RAID_TURN_TIMEOUT = 35        # Segundos por ronda de combate
RAID_MAX_TURNS = 35           # Máximo de turnos antes de que el boss gane

# ──────────────────────────────────────────────
# DROP RATES DE RAID
# ──────────────────────────────────────────────

# Probabilidad de drop según resultado
RAID_DROP_RATE_VICTORY_ALIVE = 1.00    # Sobreviviente en victoria: 100%
RAID_DROP_RATE_VICTORY_DEAD = 0.70     # Caído en victoria: 70%
RAID_DROP_RATE_DEFEAT = 0.30           # Derrota total: 30%

# Modificadores de rareza (se aplican a las probabilidades base de RARITIES)
# Positivo = más chance de rarezas altas, negativo = menos
RAID_RARITY_BONUS_VICTORY = 0.15       # +15% shift hacia rarezas superiores
RAID_RARITY_MALUS_DEFEAT = -0.10       # -10% shift (más comunes)

# Configuración de Loot por Dificultad
RAID_LOOT_DIFFICULTY_CONFIG = {
    "normal":  {"ilvl_bonus": 0,  "rarity_floor_idx": 0, "rarity_bonus": 0.15, "unique_chance": 0.0},
    "dificil": {"ilvl_bonus": 5,  "rarity_floor_idx": 1, "rarity_bonus": 0.30, "unique_chance": 0.0},
    "mitica":  {"ilvl_bonus": 12, "rarity_floor_idx": 2, "rarity_bonus": 0.50, "unique_chance": 0.08},
}

# ──────────────────────────────────────────────
# XP DE RAID
# ──────────────────────────────────────────────

RAID_XP_BASE_VICTORY = 80     # XP base por victoria
RAID_XP_BASE_DEFEAT  = 30     # XP base por derrota (siempre se da)
RAID_XP_PER_TURN     = 2      # Bonus XP por cada turno jugado
RAID_XP_ALIVE_BONUS  = 20     # Bonus extra por sobrevivir la raid

# ──────────────────────────────────────────────
# HABILIDADES ESPECIALES DE BOSSES
# ──────────────────────────────────────────────

# Cada habilidad se dispara cada N turnos
BOSS_SPECIAL_INTERVAL = 3  # Cada 3 turnos

BOSS_ABILITIES = {
    "raices_estranguladoras": {
        "name": "Raíces Estranguladoras",
        "emoji": "🌿",
        "desc": "Usa raíces venenosas para estrangular al jugador con más HP y envenenarlo.",
        "type": "single_target_dot",   # Daño + veneno al de mayor HP
        "damage_mult": 1.8,
        "dot_damage": 15,              # Daño por turno de veneno
        "dot_turns": 3,
    },
    "erupcion_volcanica": {
        "name": "Erupción Volcánica",
        "emoji": "🌋",
        "desc": "Explota en magma incandescente, quemando a todos los jugadores y regenerándose.",
        "type": "aoe_damage_heal",     # Daño AoE + se cura el boss
        "damage_mult": 1.3,
        "heal_pct": 0.05,              # Se cura 5% de su HP máximo
    },
    "tempestad_relampago": {
        "name": "Tempestad de Relámpagos",
        "emoji": "⚡",
        "desc": "Lanza un rayo devastador y concentrado a un jugador aleatorio.",
        "type": "single_nuke",         # Daño masivo a 1
        "damage_mult": 3.0,
    },
    "guadaña_vacio": {
        "name": "Guadaña del Vacío",
        "emoji": "💀",
        "desc": "Absorbe la fuerza vital de todos los jugadores para curarse.",
        "type": "aoe_drain",           # Roba HP de todos
        "drain_pct": 0.10,             # Roba 10% del HP actual de cada jugador
    },
    "ventisca_glacial": {
        "name": "Ventisca Glacial",
        "emoji": "❄️",
        "desc": "Sopla una tormenta helada que reduce el ATK de todos los jugadores.",
        "type": "aoe_debuff",          # Reduce ATK de todos
        "damage_mult": 1.0,
        "atk_reduction_pct": 0.20,     # -20% ATK por 2 turnos
        "debuff_turns": 2,
    },
    "juicio_sagrado": {
        "name": "Juicio Sagrado",
        "emoji": "👼",
        "desc": "Sacude la arena con luz celestial divina, causando daño a TODOS los jugadores.",
        "type": "aoe_damage",          # Daño a todos
        "damage_mult": 1.5,            # Multiplicador sobre ATK del boss
    },
    "colapso_gravedad": {
        "name": "Colapso de Gravedad",
        "emoji": "🌀",
        "desc": "El devorador estelar altera el espacio, cambiando sus estadísticas de ataque y defensa.",
        "type": "self_buff",           # Cambia stats del boss
        "stat_shuffle_range": (0.8, 1.3),  # Rango de multiplicador aleatorio
    },
    "none": {
        "name": "Ataque Normal",
        "emoji": "⚔️",
        "desc": "El enemigo ataca normalmente sin usar habilidades especiales.",
        "type": "none",
    },
}

# ──────────────────────────────────────────────
# DEFINICIÓN DE LOS 7 BOSSES
# ──────────────────────────────────────────────
# weekday(): 0=Lunes, 1=Martes, ..., 6=Domingo

RAID_BOSSES = {
    0: {  # Lunes
        "name": "Yggdrasil Corrupto",
        "emoji": "🌲",
        "element": "Tierra/Planta",
        "color": 0x2E8B57,
        "base_hp": 400,
        "base_atk": 25,
        "base_def": 18,
        "ability": "raices_estranguladoras",
        "phase2_ability": None,
        "phase3_ability": None,
        "lore": "El ancestral brote del árbol del mundo ha sido infectado por parásitos del abismo, volviéndolo hostil.",
        "minion_pool": ["curandero", "debilitador"],
    },
    1: {  # Martes
        "name": "Ignis, el Coloso de Magma",
        "emoji": "🌋",
        "element": "Fuego",
        "color": 0xFF4500,
        "base_hp": 380,
        "base_atk": 30,
        "base_def": 10,
        "ability": "erupcion_volcanica",
        "phase2_ability": "juicio_sagrado",
        "phase3_ability": "tempestad_relampago",
        "lore": "Un gigante durmiente que emerge del núcleo terrestre cuando la presión volcánica se descontrola.",
        "minion_pool": ["escudo", "explosivo"],
    },
    2: {  # Miércoles
        "name": "Caelum, la Tempestad Viviente",
        "emoji": "🌪️",
        "element": "Rayo",
        "color": 0x00FFFF,
        "base_hp": 500,
        "base_atk": 32,
        "base_def": 14,
        "ability": "tempestad_relampago",
        "phase2_ability": None,
        "phase3_ability": None,
        "lore": "Un elemental de viento gigante atrapado en el ojo de un huracán eterno cargado de electricidad.",
        "minion_pool": ["debilitador", "explosivo"],
    },
    3: {  # Jueves
        "name": "Thanatos, el Segador de Almas",
        "emoji": "💀",
        "element": "Oscuridad",
        "color": 0x4B0082,
        "base_hp": 320,
        "base_atk": 22,
        "base_def": 15,
        "ability": "guadaña_vacio",
        "phase2_ability": None,
        "phase3_ability": "raices_estranguladoras",
        "lore": "El guardián espectral del inframundo que busca arrastrar a los intrusos hacia las sombras eternas.",
        "minion_pool": ["curandero", "escudo"],
    },
    4: {  # Viernes
        "name": "Leviathán de la Fosa Glacial",
        "emoji": "🌊",
        "element": "Hielo",
        "color": 0x1E90FF,
        "base_hp": 450,
        "base_atk": 26,
        "base_def": 16,
        "ability": "ventisca_glacial",
        "phase2_ability": None,
        "phase3_ability": None,
        "lore": "Una colosal serpiente marina que acecha bajo los glaciares eternos del norte.",
        "minion_pool": ["escudo", "debilitador"],
    },
    5: {  # Sábado
        "name": "Aurelius, el Arcángel Caído",
        "emoji": "👼",
        "element": "Luz",
        "color": 0xFFD700,
        "base_hp": 350,
        "base_atk": 28,
        "base_def": 12,
        "ability": "juicio_sagrado",
        "phase2_ability": None,
        "phase3_ability": None,
        "lore": "Un antiguo protector celestial que fue desterrado por su soberbia y ahora juzga a los mortales con ira divina.",
        "minion_pool": ["curandero", "explosivo"],
    },
    6: {  # Domingo
        "name": "Abyssus, el Devorador Estelar",
        "emoji": "👾",
        "element": "Caos",
        "color": 0x9400D3,
        "base_hp": 420,
        "base_atk": 27,
        "base_def": 13,
        "ability": "colapso_gravedad",
        "phase2_ability": None,
        "phase3_ability": None,
        "lore": "Un ente cósmico amorfo hecho de materia oscura que colapsa la física a su paso.",
        "minion_pool": None,
    },
}


# ──────────────────────────────────────────────
# FUNCIONES DE ESCALADO
# ──────────────────────────────────────────────

def get_today_boss():
    """Retorna la configuración del boss del día actual."""
    from datetime import datetime
    weekday = datetime.now().weekday()  # 0=Lunes ... 6=Domingo
    return RAID_BOSSES[weekday]


RAID_LOW_LEVEL_FLOOR_THRESHOLD = 10  # Poder total combinado bajo el cual el boss no escala

RAID_DIFFICULTY_COEFS = {
    "normal":  {"hp": 0.45, "atk": 0.28, "def": 0.22, "flat_mult": 1.0, "hp_flat_mult": 1.0},
    "dificil": {"hp": 0.65, "atk": 0.40, "def": 0.32, "flat_mult": 1.0, "hp_flat_mult": 1.0},
    "mitica":  {"hp": 0.90, "atk": 0.55, "def": 0.42, "flat_mult": 1.0, "hp_flat_mult": 1.0},
}


def calc_boss_stats(boss_config: dict, total_power: float = 0.0, difficulty: str = "normal", total_level: float | None = None) -> dict:
    """Calcula los stats del boss escalados según el Poder de Combate total y la dificultad.

    Args:
        boss_config: dict del boss desde RAID_BOSSES
        total_power: suma de niveles equivalentes de combate de todos los participantes
        difficulty: dificultad elegida ("normal", "dificil", "mitica")
        total_level: parámetro legacy para retrocompatibilidad con tests y llamadas antiguas

    Returns:
        dict con hp, max_hp, atk, def_stat (escalados)
    """
    import math

    if total_level is not None:
        total_power = total_level

    coefs = RAID_DIFFICULTY_COEFS.get(difficulty, RAID_DIFFICULTY_COEFS["normal"])

    # Piso: grupos con poder total bajo el umbral quedan casi en stats base
    if total_power < RAID_LOW_LEVEL_FLOOR_THRESHOLD:
        scale_factor = 0
    else:
        scale_factor = max(0, total_power - 2)

    hp = int(round(boss_config["base_hp"] * (1 + coefs["hp"] * math.sqrt(scale_factor)) * coefs["hp_flat_mult"]))
    atk = int(round(boss_config["base_atk"] * (1 + coefs["atk"] * math.sqrt(scale_factor)) * coefs["flat_mult"]))
    def_stat = int(round(boss_config["base_def"] * (1 + coefs["def"] * math.sqrt(scale_factor)) * coefs["flat_mult"]))

    return {
        "hp": hp,
        "max_hp": hp,
        "atk": atk,
        "def_stat": def_stat,
    }


def generate_raid_loot(player_level: int, rarity_bonus: float = 0.0, floor_idx: int = 0, ilvl_bonus: int = 0):
    """Genera loot de raid con modificador de rareza.

    Reutiliza generate_loot() de combat_progression pero modifica
    las probabilidades de rareza temporalmente.

    Args:
        player_level: nivel de combate del jugador
        rarity_bonus: float entre -1.0 y 1.0. Positivo = más chance
                      de rarezas altas.
        floor_idx: índice mínimo de la rareza permitida
        ilvl_bonus: bono al nivel de objeto
    """
    from src.utils.combat_progression import (
        generate_loot, RARITIES
    )
    import random

    if abs(rarity_bonus) < 0.001:
        return generate_loot(player_level, ilvl=player_level + ilvl_bonus, floor_idx=floor_idx)

    # Guardar probabilidades originales
    original_probs = [r["prob"] for r in RARITIES]

    try:
        # Ajustar probabilidades: mover peso de comunes a raros
        if rarity_bonus > 0:
            # Reducir Común, aumentar Raro+
            shift = rarity_bonus * original_probs[0] * 0.5  # Tomar de Común
            RARITIES[0]["prob"] = max(0.10, original_probs[0] - shift)
            # Repartir entre Raro, Épico, Legendario
            RARITIES[2]["prob"] = original_probs[2] + shift * 0.50
            RARITIES[3]["prob"] = original_probs[3] + shift * 0.30
            RARITIES[4]["prob"] = original_probs[4] + shift * 0.20
        else:
            # Aumentar Común, reducir raros
            shift = abs(rarity_bonus) * 0.10
            RARITIES[0]["prob"] = min(0.70, original_probs[0] + shift)
            RARITIES[2]["prob"] = max(0.05, original_probs[2] - shift * 0.50)
            RARITIES[3]["prob"] = max(0.02, original_probs[3] - shift * 0.30)
            RARITIES[4]["prob"] = max(0.005, original_probs[4] - shift * 0.20)

        # Normalizar para que sumen 1.0
        total = sum(r["prob"] for r in RARITIES)
        for r in RARITIES:
            r["prob"] /= total

        return generate_loot(player_level, ilvl=player_level + ilvl_bonus, floor_idx=floor_idx)
    finally:
        # Restaurar siempre las probabilidades originales
        for i, r in enumerate(RARITIES):
            r["prob"] = original_probs[i]


# ──────────────────────────────────────────────
# AFIJOS DE RAID
# ──────────────────────────────────────────────

RAID_AFFIXES = {
    "Sangriento": {
        "name": "Sangriento",
        "emoji": "🩸",
        "desc": "Si un jugador cae en combate, el jefe se cura el 15% de su HP máximo.",
    },
    "Inestabilidad Mágica": {
        "name": "Inestabilidad Mágica",
        "emoji": "🌀",
        "desc": "El daño de ataques físicos se reduce un 30%, pero el de habilidades mágicas aumenta un 40%.",
    },
    "Enfurecido": {
        "name": "Enfurecido",
        "emoji": "⚡",
        "desc": "Cuando el jefe tiene menos del 35% de vida, su daño aumenta un 30%.",
    },
    "Niebla Venenosa": {
        "name": "Niebla Venenosa",
        "emoji": "🧪",
        "desc": "Todos los jugadores reciben 5 de daño al inicio de cada ronda.",
    },
}

# ──────────────────────────────────────────────
# ESBIRROS: ARQUETIPOS
# ──────────────────────────────────────────────

MINION_ARCHETYPES = {
    "escudo": {
        "name": "Guardián de Escudo", "emoji": "🛡️",
        "hp": 30, "def_stat": 15,
        "role": "shield",  # Reduce 50% el daño que recibe él mismo
    },
    "curandero": {
        "name": "Espíritu Curandero", "emoji": "💚",
        "hp": 25, "def_stat": 8,
        "role": "healer",  # Cura 4% HP máx del boss cada turno que sobreviva
        "heal_pct": 0.04,
    },
    "explosivo": {
        "name": "Núcleo Inestable", "emoji": "💣",
        "hp": 20, "def_stat": 5,
        "role": "explosive",  # Detona a los 3 turnos si sigue vivo
        "fuse_turns": 3,
        "explosion_pct_of_boss_atk": 0.15,
    },
    "debilitador": {
        "name": "Espectro Debilitante", "emoji": "🌀",
        "hp": 35, "def_stat": 12,
        "role": "debuffer",  # Aplica debuff aleatorio a un jugador cada turno vivo
    },
}

# ──────────────────────────────────────────────
# MINIBOSSES ALEATORIOS
# ──────────────────────────────────────────────

MINIBOSS_CHANCE = 0.12  # 12% de probabilidad al usar /raid
MINIBOSS_LOOT_RARITY_BONUS = 0.10

MINIBOSSES = {
    "cofre_mimetico": {
        "name": "Cofre Mimético", "emoji": "🎁",
        "element": "Físico",
        "color": 0x8B4513,
        "hp": 150, "atk": 15, "def_stat": 8,
        "lore": "Un cofre que parpadea con un brillo sospechoso... ¡tiene dientes!",
        "ability": "none",
        "guaranteed_loot": True,
    },
    "espiritu_errante": {
        "name": "Espíritu Errante", "emoji": "👻",
        "element": "Espectral",
        "color": 0xE0FFFF,
        "hp": 200, "atk": 20, "def_stat": 10,
        "lore": "Una presencia parpadeante que va y viene entre este mundo y el siguiente.",
        "ability": "none",
        "invisibility_pattern": True,  # Invisible cada 2do turno (tangible en turnos impares, intangible en pares)
        "guaranteed_loot": False,
    },
    "mercader_fantasma": {
        "name": "Mercader Fantasma", "emoji": "🛒",
        "lore": "Una figura encapuchada que aparece entre la niebla, ofreciendo tratos... por un precio.",
        "is_shop": True,  # Distingue este evento de los de combate (cofre_mimetico, espiritu_errante)
    },
}
