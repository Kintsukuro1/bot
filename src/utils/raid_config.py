# ══════════════════════════════════════════════
# CONFIGURACIÓN CENTRALIZADA — SISTEMA DE RAIDS
# ══════════════════════════════════════════════

"""
15 bosses rotativos en un catálogo ampliado.
La dificultad escala según la suma de niveles de los participantes.
Recompensas: solo ítems de equipo (no monedas) y materiales de Poblado.
"""

# ──────────────────────────────────────────────
# CONSTANTES DE RAID
# ──────────────────────────────────────────────

RAID_MIN_PLAYERS = 2          # Mínimo de jugadores para iniciar
RAID_MAX_PLAYERS = 8          # Máximo de jugadores en una raid (ampliado a 8)
RAID_LOBBY_TIMEOUT = 90       # Segundos para el lobby de espera

RAID_TURN_TIMEOUT = 35        # Segundos por ronda de combate
RAID_MAX_TURNS = 35           # Máximo de turnos antes de que el boss gane

# ──────────────────────────────────────────────
# DROP RATES DE RAID
# ──────────────────────────────────────────────

RAID_DROP_RATE_VICTORY_ALIVE = 1.00    # Sobreviviente en victoria: 100%
RAID_DROP_RATE_VICTORY_DEAD = 0.70     # Caído en victoria: 70%
RAID_DROP_RATE_DEFEAT = 0.30           # Derrota total: 30%

RAID_RARITY_BONUS_VICTORY = 0.15       # +15% shift hacia rarezas superiores
RAID_RARITY_MALUS_DEFEAT = -0.10       # -10% shift (más comunes)

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

BOSS_SPECIAL_INTERVAL = 3  # Cada 3 turnos

BOSS_ABILITIES = {
    "raices_estranguladoras": {
        "name": "Raíces Estranguladoras",
        "emoji": "🌿",
        "desc": "Usa raíces venenosas para estrangular al jugador con más HP y envenenarlo.",
        "type": "single_target_dot",
        "damage_mult": 1.8,
        "dot_damage": 15,
        "dot_turns": 3,
    },
    "erupcion_volcanica": {
        "name": "Erupción Volcánica",
        "emoji": "🌋",
        "desc": "Explota en magma incandescente, quemando a todos los jugadores y regenerándose.",
        "type": "aoe_damage_heal",
        "damage_mult": 1.3,
        "heal_pct": 0.05,
    },
    "tempestad_relampago": {
        "name": "Tempestad de Relámpagos",
        "emoji": "⚡",
        "desc": "Lanza un rayo devastador y concentrado a un jugador aleatorio.",
        "type": "single_nuke",
        "damage_mult": 3.0,
    },
    "guadaña_vacio": {
        "name": "Guadaña del Vacío",
        "emoji": "💀",
        "desc": "Absorbe la fuerza vital de todos los jugadores para curarse.",
        "type": "aoe_drain",
        "drain_pct": 0.10,
    },
    "ventisca_glacial": {
        "name": "Ventisca Glacial",
        "emoji": "❄️",
        "desc": "Sopla una tormenta helada que reduce el ATK de todos los jugadores.",
        "type": "aoe_debuff",
        "damage_mult": 1.0,
        "atk_reduction_pct": 0.20,
        "debuff_turns": 2,
    },
    "juicio_sagrado": {
        "name": "Juicio Sagrado",
        "emoji": "👼",
        "desc": "Sacude la arena con luz celestial divina, causando daño a TODOS los jugadores.",
        "type": "aoe_damage",
        "damage_mult": 1.5,
    },
    "colapso_gravedad": {
        "name": "Colapso de Gravedad",
        "emoji": "🌀",
        "desc": "El devorador estelar altera el espacio, cambiando sus estadísticas de ataque y defensa.",
        "type": "self_buff",
        "stat_shuffle_range": (0.8, 1.3),
    },
    "inversion_temporal": {
        "name": "Inversión Temporal",
        "emoji": "⏳",
        "desc": "Rebobina el tiempo: revierte daño recibido y aplica Paradoja Temporal (+1 turno de cooldown al grupo).",
        "type": "aoe_debuff",
        "damage_mult": 1.4,
        "atk_reduction_pct": 0.25,
        "debuff_turns": 3,
    },
    "aliento_multielemental": {
        "name": "Aliento Multielemental",
        "emoji": "🐉",
        "desc": "Dispara ráfagas elementales rotativas que aplican estados alterados acumulativos.",
        "type": "aoe_damage_heal",
        "damage_mult": 1.6,
        "heal_pct": 0.04,
    },
    "protocolo_autoreparacion": {
        "name": "Protocolo de Auto-Reparación",
        "emoji": "🤖",
        "desc": "Gana un potente escudo de absorción e incrementa su defensa.",
        "type": "self_buff",
        "stat_shuffle_range": (1.1, 1.4),
    },
    "red_seda_alma": {
        "name": "Red de Seda de Alma",
        "emoji": "🕸️",
        "desc": "Encapulla al jugador con mayor HP reduciendo su curación recibida un 50%.",
        "type": "single_target_dot",
        "damage_mult": 1.9,
        "dot_damage": 20,
        "dot_turns": 3,
    },
    "congelacion_progresiva": {
        "name": "Congelación Progresiva",
        "emoji": "🧊",
        "desc": "Aplica Hipotermia reduciendo la DEF y anulando regeneraciones pasivas.",
        "type": "aoe_debuff",
        "damage_mult": 1.2,
        "atk_reduction_pct": 0.20,
        "debuff_turns": 3,
    },
    "pacto_sangre_inverso": {
        "name": "Pacto de Sangre Inverso",
        "emoji": "🩸",
        "desc": "Roba un porcentaje de las curaciones del grupo convirtiéndolas en escudo.",
        "type": "aoe_drain",
        "drain_pct": 0.12,
    },
    "locura_cosmica": {
        "name": "Locura Cósmica",
        "emoji": "👁️",
        "desc": "Daña la cordura del grupo infligiendo daño caótico directo.",
        "type": "aoe_damage",
        "damage_mult": 1.7,
    },
    "llamarada_solar_devastadora": {
        "name": "Llamarada Solar Devastadora",
        "emoji": "☀️",
        "desc": "Canaliza un ataque solar cataclísmico que inflige daño masivo a menos que el grupo defienda.",
        "type": "single_nuke",
        "damage_mult": 3.2,
    },
    "none": {
        "name": "Ataque Normal",
        "emoji": "⚔️",
        "desc": "El enemigo ataca normalmente sin usar habilidades especiales.",
        "type": "none",
    },
}

# ──────────────────────────────────────────────
# CATÁLOGO DE LOS 15 BOSSES DE RAID
# ──────────────────────────────────────────────

RAID_BOSSES = {
    0: {
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
        "lore": "El ancestral brote del árbol del mundo ha sido infectado por parásitos del abismo.",
        "minion_pool": ["curandero", "debilitador"],
        "poblado_recurso": "madera"
    },
    1: {
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
        "lore": "Un gigante durmiente que emerge del núcleo terrestre cuando la presión volcánica desborda.",
        "minion_pool": ["escudo", "explosivo"],
        "poblado_recurso": "piedra"
    },
    2: {
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
        "lore": "Un elemental de viento gigante atrapado en el ojo de un huracán eterno.",
        "minion_pool": ["debilitador", "explosivo"],
        "poblado_recurso": "cristal"
    },
    3: {
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
        "lore": "El guardián espectral del inframundo que arrastra a los intrusos hacia las sombras.",
        "minion_pool": ["curandero", "escudo"],
        "poblado_recurso": "cristal"
    },
    4: {
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
        "poblado_recurso": "madera"
    },
    5: {
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
        "lore": "Un antiguo protector celestial que fue desterrado por su soberbia y ahora juzga con ira divina.",
        "minion_pool": ["curandero", "explosivo"],
        "poblado_recurso": "solar"
    },
    6: {
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
        "poblado_recurso": "cristal"
    },
    7: {
        "name": "Ouroboros, el Tirano del Tiempo",
        "emoji": "⏳",
        "element": "Tiempo/Vacío",
        "color": 0x8A2BE2,
        "base_hp": 480,
        "base_atk": 29,
        "base_def": 15,
        "ability": "inversion_temporal",
        "phase2_ability": "guadaña_vacio",
        "phase3_ability": None,
        "lore": "Un dragón infinito que devora los segundos y manipula las líneas temporales de los mortales.",
        "minion_pool": ["debilitador", "escudo"],
        "poblado_recurso": "cristal"
    },
    8: {
        "name": "Tiamat, la Reina de las Cinco Cabezas",
        "emoji": "🐉",
        "element": "Multi-Elemental",
        "color": 0xDC143C,
        "base_hp": 520,
        "base_atk": 31,
        "base_def": 16,
        "ability": "aliento_multielemental",
        "phase2_ability": "erupcion_volcanica",
        "phase3_ability": "ventisca_glacial",
        "lore": "Una hidra ancestral cuyas cabezas despiertan alternadamente liberando cataclismos.",
        "minion_pool": ["explosivo", "curandero"],
        "poblado_recurso": "piedra"
    },
    9: {
        "name": "Aethelgard, el Autómata Creador",
        "emoji": "🤖",
        "element": "Arcana/Metal",
        "color": 0x708090,
        "base_hp": 550,
        "base_atk": 28,
        "base_def": 22,
        "ability": "protocolo_autoreparacion",
        "phase2_ability": None,
        "phase3_ability": "colapso_gravedad",
        "lore": "Una titánica máquina de guerra abandonada por una civilización extinta.",
        "minion_pool": ["escudo", "explosivo"],
        "poblado_recurso": "solar"
    },
    10: {
        "name": "Arachne, la Tejedora de Almas",
        "emoji": "🕸️",
        "element": "Veneno/Sombras",
        "color": 0x483D8B,
        "base_hp": 410,
        "base_atk": 26,
        "base_def": 14,
        "ability": "red_seda_alma",
        "phase2_ability": "raices_estranguladoras",
        "phase3_ability": None,
        "lore": "Una deidad arácnida que atrapa las almas de los guerreros en hilos de seda mística.",
        "minion_pool": ["debilitador", "curandero"],
        "poblado_recurso": "madera"
    },
    11: {
        "name": "Helheim, el Titán de la Muerte Glacial",
        "emoji": "🧊",
        "element": "Hielo/Muerte",
        "color": 0x00BFFF,
        "base_hp": 490,
        "base_atk": 30,
        "base_def": 17,
        "ability": "congelacion_progresiva",
        "phase2_ability": "ventisca_glacial",
        "phase3_ability": None,
        "lore": "Un gigante de escarcha resucitado que convierte la sangre de sus víctimas en hielo puro.",
        "minion_pool": ["escudo", "debilitador"],
        "poblado_recurso": "piedra"
    },
    12: {
        "name": "Baphomet, el Señor de las Plegarias Caídas",
        "emoji": "🩸",
        "element": "Fuego Infernal",
        "color": 0x800000,
        "base_hp": 460,
        "base_atk": 33,
        "base_def": 13,
        "ability": "pacto_sangre_inverso",
        "phase2_ability": "guadaña_vacio",
        "phase3_ability": None,
        "lore": "Un demonio mayor que pervierte la fe de los sacerdotes y absorbe las plegarias.",
        "minion_pool": ["explosivo", "debilitador"],
        "poblado_recurso": "cristal"
    },
    13: {
        "name": "Cthulhu, el Azote de las Profundidades",
        "emoji": "🐙",
        "element": "Agua/Caos",
        "color": 0x20B2AA,
        "base_hp": 530,
        "base_atk": 30,
        "base_def": 15,
        "ability": "locura_cosmica",
        "phase2_ability": "colapso_gravedad",
        "phase3_ability": None,
        "lore": "Una entidad primigenia sumergida que distorsiona la mente de quienes osan mirarlo.",
        "minion_pool": ["escudo", "curandero"],
        "poblado_recurso": "solar"
    },
    14: {
        "name": "Helios, el Emperador del Sol Radiante",
        "emoji": "☀️",
        "element": "Luz/Fuego",
        "color": 0xFF8C00,
        "base_hp": 470,
        "base_atk": 34,
        "base_def": 12,
        "ability": "llamarada_solar_devastadora",
        "phase2_ability": "juicio_sagrado",
        "phase3_ability": None,
        "lore": "Un antiguo monarca solar imbuido de llamas sagradas capaz de calcinar reinos enteros.",
        "minion_pool": ["explosivo", "escudo"],
        "poblado_recurso": "solar"
    }
}

def get_today_boss():
    """Retorna la configuración del boss del día actual en rotación de 15 bosses."""
    from datetime import datetime
    day_of_year = datetime.now().timetuple().tm_yday
    boss_idx = day_of_year % len(RAID_BOSSES)
    return RAID_BOSSES[boss_idx]

RAID_LOW_LEVEL_FLOOR_THRESHOLD = 10

RAID_DIFFICULTY_COEFS = {
    "normal":  {"hp_mult": 1.00, "atk_mult": 1.00, "def_mult": 1.00},
    "dificil": {"hp_mult": 1.45, "atk_mult": 1.30, "def_mult": 1.20},
    "mitica":  {"hp_mult": 2.10, "atk_mult": 1.65, "def_mult": 1.45},
}

def calc_boss_stats(boss_config: dict, total_power: float = 0.0, difficulty: str = "normal", total_level: float | None = None, num_players: int = 1) -> dict:
    """Calcula los stats del boss ajustados dinámicamente según el número de participantes, su poder total y la dificultad."""
    import math

    if total_level is not None:
        total_power = total_level

    coefs = RAID_DIFFICULTY_COEFS.get(difficulty, RAID_DIFFICULTY_COEFS["normal"])

    # Escalado por tamaño de la party (1 a 8 jugadores)
    party_size = max(1, num_players)
    party_scale = 1.0 + (party_size - 1) * 0.65

    # Escalado por poder de combate acumulado
    power_scale = math.sqrt(max(1.0, total_power))

    base_hp = boss_config.get("base_hp", 400)
    base_atk = boss_config.get("base_atk", 25)
    base_def = boss_config.get("base_def", 15)

    hp = int(round(base_hp * (1.0 + 0.35 * power_scale) * party_scale * coefs["hp_mult"]))
    atk = int(round(base_atk * (1.0 + 0.20 * power_scale) * (1.0 + (party_size - 1) * 0.08) * coefs["atk_mult"]))
    def_stat = int(round(base_def * (1.0 + 0.18 * power_scale) * coefs["def_mult"]))

    return {
        "hp": hp,
        "max_hp": hp,
        "atk": atk,
        "def_stat": def_stat,
    }


def generate_raid_loot(player_level: int, rarity_bonus: float = 0.0, floor_idx: int = 0, ilvl_bonus: int = 0):
    from src.utils.combat_progression import generate_loot, RARITIES
    import random

    if abs(rarity_bonus) < 0.001:
        return generate_loot(player_level, ilvl=player_level + ilvl_bonus, floor_idx=floor_idx)

    original_probs = [r["prob"] for r in RARITIES]

    try:
        if rarity_bonus > 0:
            shift = rarity_bonus * original_probs[0] * 0.5
            RARITIES[0]["prob"] = max(0.10, original_probs[0] - shift)
            RARITIES[2]["prob"] = original_probs[2] + shift * 0.50
            RARITIES[3]["prob"] = original_probs[3] + shift * 0.30
            RARITIES[4]["prob"] = original_probs[4] + shift * 0.20
        else:
            shift = abs(rarity_bonus) * 0.10
            RARITIES[0]["prob"] = min(0.70, original_probs[0] + shift)
            RARITIES[2]["prob"] = max(0.05, original_probs[2] - shift * 0.50)
            RARITIES[3]["prob"] = max(0.02, original_probs[3] - shift * 0.30)
            RARITIES[4]["prob"] = max(0.005, original_probs[4] - shift * 0.20)

        total = sum(r["prob"] for r in RARITIES)
        for r in RARITIES:
            r["prob"] /= total

        return generate_loot(player_level, ilvl=player_level + ilvl_bonus, floor_idx=floor_idx)
    finally:
        for i, r in enumerate(RARITIES):
            r["prob"] = original_probs[i]

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

MINION_ARCHETYPES = {
    "escudo": {
        "name": "Guardián de Escudo", "emoji": "🛡️",
        "hp": 30, "def_stat": 15,
        "role": "shield",
    },
    "curandero": {
        "name": "Espíritu Curandero", "emoji": "💚",
        "hp": 25, "def_stat": 8,
        "role": "healer",
        "heal_pct": 0.04,
    },
    "explosivo": {
        "name": "Núcleo Inestable", "emoji": "💣",
        "hp": 20, "def_stat": 5,
        "role": "explosive",
        "fuse_turns": 3,
        "explosion_pct_of_boss_atk": 0.15,
    },
    "debilitador": {
        "name": "Espectro Debilitante", "emoji": "🌀",
        "hp": 35, "def_stat": 12,
        "role": "debuffer",
    },
}

MINIBOSS_CHANCE = 0.12
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
        "invisibility_pattern": True,
        "guaranteed_loot": False,
    },
    "mercader_fantasma": {
        "name": "Mercader Fantasma", "emoji": "🛒",
        "lore": "Una figura encapuchada que aparece entre la niebla, ofreciendo tratos... por un precio.",
        "is_shop": True,
    },
}
