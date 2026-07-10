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

# ──────────────────────────────────────────────
# HABILIDADES ESPECIALES DE BOSSES
# ──────────────────────────────────────────────

# Cada habilidad se dispara cada N turnos
BOSS_SPECIAL_INTERVAL = 3  # Cada 3 turnos

BOSS_ABILITIES = {
    "terremoto": {
        "name": "Terremoto",
        "emoji": "🌍",
        "desc": "Sacude la tierra, causando daño a TODOS los jugadores.",
        "type": "aoe_damage",          # Daño a todos
        "damage_mult": 1.5,            # Multiplicador sobre ATK del boss
    },
    "mordisco_toxico": {
        "name": "Mordisco Tóxico",
        "emoji": "🧪",
        "desc": "Muerde al jugador con más HP y lo envenena.",
        "type": "single_target_dot",   # Daño + veneno al de mayor HP
        "damage_mult": 1.8,
        "dot_damage": 15,              # Daño por turno de veneno
        "dot_turns": 3,
    },
    "nova_fuego": {
        "name": "Nova de Fuego",
        "emoji": "🔥",
        "desc": "Explota en llamas, quemando a todos y regenerándose.",
        "type": "aoe_damage_heal",     # Daño AoE + se cura el boss
        "damage_mult": 1.3,
        "heal_pct": 0.05,              # Se cura 5% de su HP máximo
    },
    "drenar_vida": {
        "name": "Drenar Vida",
        "emoji": "💜",
        "desc": "Absorbe la fuerza vital del grupo para curarse.",
        "type": "aoe_drain",           # Roba HP de todos
        "drain_pct": 0.10,             # Roba 10% del HP actual de cada jugador
    },
    "aliento_helado": {
        "name": "Aliento Helado",
        "emoji": "❄️",
        "desc": "Sopla hielo que reduce el ATK de todos los jugadores.",
        "type": "aoe_debuff",          # Reduce ATK de todos
        "damage_mult": 1.0,
        "atk_reduction_pct": 0.20,     # -20% ATK por 2 turnos
        "debuff_turns": 2,
    },
    "rayo_devastador": {
        "name": "Rayo Devastador",
        "emoji": "⚡",
        "desc": "Lanza un rayo devastador a un jugador aleatorio.",
        "type": "single_nuke",         # Daño masivo a 1
        "damage_mult": 3.0,
    },
    "mutacion": {
        "name": "Mutación Caótica",
        "emoji": "🌀",
        "desc": "El boss muta, cambiando sus stats aleatoriamente.",
        "type": "self_buff",           # Cambia stats del boss
        "stat_shuffle_range": (0.8, 1.3),  # Rango de multiplicador aleatorio
    },
}

# ──────────────────────────────────────────────
# DEFINICIÓN DE LOS 7 BOSSES
# ──────────────────────────────────────────────
# weekday(): 0=Lunes, 1=Martes, ..., 6=Domingo

RAID_BOSSES = {
    0: {  # Lunes
        "name": "Golem de Piedra",
        "emoji": "🪨",
        "element": "Tierra",
        "color": 0x8B7355,
        "base_hp": 400,
        "base_atk": 25,
        "base_def": 18,
        "ability": "terremoto",
        "lore": "Un coloso de roca antigua que despierta cada semana para proteger las minas.",
    },
    1: {  # Martes
        "name": "Hidra Venenosa",
        "emoji": "🐍",
        "element": "Veneno",
        "color": 0x00CC66,
        "base_hp": 350,
        "base_atk": 28,
        "base_def": 12,
        "ability": "mordisco_toxico",
        "lore": "Una serpiente de tres cabezas que infesta los pantanos con su veneno mortal.",
    },
    2: {  # Miércoles
        "name": "Fénix Infernal",
        "emoji": "🔥",
        "element": "Fuego",
        "color": 0xFF4500,
        "base_hp": 380,
        "base_atk": 30,
        "base_def": 10,
        "ability": "nova_fuego",
        "lore": "Un ave de fuego eterno que renace de sus cenizas, más fuerte cada vez.",
    },
    3: {  # Jueves
        "name": "Liche Sombrío",
        "emoji": "💀",
        "element": "Oscuridad",
        "color": 0x4B0082,
        "base_hp": 320,
        "base_atk": 22,
        "base_def": 15,
        "ability": "drenar_vida",
        "lore": "Un hechicero no-muerto que se alimenta de las almas de los vivos.",
    },
    4: {  # Viernes
        "name": "Dragón Glacial",
        "emoji": "🐉",
        "element": "Hielo",
        "color": 0x00BFFF,
        "base_hp": 450,
        "base_atk": 26,
        "base_def": 16,
        "ability": "aliento_helado",
        "lore": "Un dragón ancestral que habita las montañas heladas del norte.",
    },
    5: {  # Sábado
        "name": "Titán Ancestral",
        "emoji": "⚡",
        "element": "Rayo",
        "color": 0xFFD700,
        "base_hp": 500,
        "base_atk": 32,
        "base_def": 14,
        "ability": "rayo_devastador",
        "lore": "Un gigante milenario que controla las tormentas con sus puños.",
    },
    6: {  # Domingo
        "name": "Quimera Caótica",
        "emoji": "👹",
        "element": "Caos",
        "color": 0x9400D3,
        "base_hp": 420,
        "base_atk": 27,
        "base_def": 13,
        "ability": "mutacion",
        "lore": "Una criatura imposible, fusión de bestias que muta sin cesar.",
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


def calc_boss_stats(boss_config: dict, total_level: int) -> dict:
    """Calcula los stats del boss escalados según la suma de niveles.

    Args:
        boss_config: dict del boss desde RAID_BOSSES
        total_level: suma de niveles de combate de todos los participantes

    Returns:
        dict con hp, max_hp, atk, def_stat (escalados)
    """
    # El escalado usa (total_level - 2) para que con 2 jugadores de nivel 1
    # el boss tenga exactamente sus stats base
    scale_factor = max(0, total_level - 2)

    hp = int(boss_config["base_hp"] * (1 + 0.15 * scale_factor))
    atk = int(boss_config["base_atk"] * (1 + 0.10 * scale_factor))
    def_stat = int(boss_config["base_def"] * (1 + 0.08 * scale_factor))

    return {
        "hp": hp,
        "max_hp": hp,
        "atk": atk,
        "def_stat": def_stat,
    }


def generate_raid_loot(player_level: int, rarity_bonus: float = 0.0):
    """Genera loot de raid con modificador de rareza.

    Reutiliza generate_loot() de combat_progression pero modifica
    las probabilidades de rareza temporalmente.

    Args:
        player_level: nivel de combate del jugador
        rarity_bonus: float entre -1.0 y 1.0. Positivo = más chance
                      de rarezas altas.
    """
    from src.utils.combat_progression import (
        generate_loot, RARITIES
    )
    import random

    if abs(rarity_bonus) < 0.001:
        return generate_loot(player_level)

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

        return generate_loot(player_level)
    finally:
        # Restaurar siempre las probabilidades originales
        for i, r in enumerate(RARITIES):
            r["prob"] = original_probs[i]
