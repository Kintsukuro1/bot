"""Progresión de nivel y utilidades para el sistema de duelos PvP.

Sistema de 4 stats (ATK, MAG, DEF, HP), equipo con stats primarios y
secundarios, nombres procedurales y efectos pasivos de Legendario.
"""

import random
import math

# ──────────────────────────────────────────────
# CONSTANTES GLOBALES
# ──────────────────────────────────────────────

MAX_COMBAT_LEVEL = 100
COMBAT_XP_BASE = 400
COMBAT_XP_FACTOR = 1.18

DUEL_COOLDOWN_BASE_MINUTES = 5   # Cooldown base (nivel 1)
DUEL_COOLDOWN_MIN_MINUTES = 1    # Cooldown mínimo (niveles altos)
MAX_LEVEL_DIFFERENCE = 5         # Diferencia máxima de nivel para retarse
MIN_BET = 100                    # Apuesta mínima
MAX_TURNS = 25                   # Límite de turnos por duelo
TURN_TIMEOUT_SECONDS = 30        # Segundos por turno
CHALLENGE_TIMEOUT_SECONDS = 60   # Segundos para aceptar un reto
LOOT_TIMEOUT_SECONDS = 120       # Segundos para decidir sobre un drop
SPECIAL_UNLOCK_LEVEL = 1         # Nivel para desbloquear Especial
SPECIAL_COOLDOWN_TURNS = 3       # Turnos de enfriamiento del Especial
MAX_GEAR_BONUS_PCT = 0.40        # Tope de bonus de equipo (40%) por stat
SOFTCAP_TIER2_EFFICIENCY = 0.50   # 100%-200% del cap
SOFTCAP_TIER3_EFFICIENCY = 0.20   # 200%+ del cap


# Las 4 estadísticas del sistema de combate
ALL_STATS = ("atk", "mag", "def", "hp")

# ──────────────────────────────────────────────
# RANGOS DE COMBATE
# ──────────────────────────────────────────────

COMBAT_RANKS = (
    (1,   "Novato"),
    (10,  "Aprendiz de Duelo"),
    (20,  "Combatiente"),
    (30,  "Guerrero de Élite"),
    (40,  "Veterano de Arena"),
    (50,  "Campeón de la Trama"),
    (60,  "Maestro de Armas"),
    (70,  "Gladiador"),
    (80,  "Conquistador Astral"),
    (90,  "Divinidad del Combate"),
    (100, "Leyenda Suprema"),
)

COMBAT_RANK_EMOJIS = {
    "Novato": "🗡️",
    "Aprendiz de Duelo": "⚔️",
    "Combatiente": "🛡️",
    "Guerrero de Élite": "💪",
    "Veterano de Arena": "🏟️",
    "Campeón de la Trama": "🏆",
    "Maestro de Armas": "⚜️",
    "Gladiador": "👑",
    "Conquistador Astral": "🌌",
    "Divinidad del Combate": "✨",
    "Leyenda Suprema": "🌟",
}


def get_combat_rank(level):
    """Obtiene el nombre del rango según el nivel."""
    rank = "Novato"
    for min_level, name in COMBAT_RANKS:
        if level >= min_level:
            rank = name
    return rank


def get_combat_rank_emoji(level):
    """Obtiene el emoji del rango."""
    rank = get_combat_rank(level)
    return COMBAT_RANK_EMOJIS.get(rank, "🗡️")


# ──────────────────────────────────────────────
# CURVA DE XP
# ──────────────────────────────────────────────

def calc_combat_xp_needed(level):
    """XP necesaria para subir del nivel dado al siguiente."""
    if level >= MAX_COMBAT_LEVEL:
        return 0
    return int(COMBAT_XP_BASE * (COMBAT_XP_FACTOR ** (level - 1)))


def calc_duel_xp(winner, rival_level):
    """Calcula XP obtenida tras un duelo."""
    if winner:
        return 50 + (rival_level * 5)
    else:
        return 15 + (rival_level * 2)


def apply_combat_xp(current_level, current_xp, xp_gained):
    """Aplica XP ganada y gestiona subidas de nivel."""
    level = max(1, min(current_level, MAX_COMBAT_LEVEL))
    xp = current_xp + xp_gained
    previous_level = level
    leveled_up = False

    while level < MAX_COMBAT_LEVEL:
        needed = calc_combat_xp_needed(level)
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
        "previous_level": previous_level,
        "xp_gained": xp_gained,
        "xp_for_next": calc_combat_xp_needed(level),
        "rank": get_combat_rank(level),
    }


# ──────────────────────────────────────────────
# STATS BASE POR NIVEL (4 stats)
# ──────────────────────────────────────────────

def calc_base_stats(level):
    """Calcula HP, ATK, MAG y DEF base según el nivel de combate.

    - ATK: daño de Atacar
    - MAG: daño de Especial
    - DEF: reducción de daño + refuerza Defender
    - HP:  vida máxima
    """
    return {
        "hp":  100 + (level * 20),
        "atk": 10 + (level * 3),
        "mag": 8 + (level * 3),
        "def": 5 + (level * 2),
    }


# ──────────────────────────────────────────────
# COOLDOWN
# ──────────────────────────────────────────────

def get_duel_cooldown_minutes(level):
    """Cooldown post-duelo en minutos. A mayor nivel, menor espera."""
    return max(DUEL_COOLDOWN_MIN_MINUTES, DUEL_COOLDOWN_BASE_MINUTES - math.floor(level / 6))


# ──────────────────────────────────────────────
# FÓRMULAS DE DAÑO (4 stats)
# ──────────────────────────────────────────────

def calc_attack_damage(atk, rival_def, is_defending=False, extra_crit_pct=0.0,
                       has_fury=False, fury_active=False):
    """Calcula daño de la acción Atacar (escala con ATK).

    Args:
        extra_crit_pct: bonus de probabilidad de crítico (ej: 0.10 del pasivo)
        has_fury: si tiene el pasivo Furia creciente
        fury_active: si el HP está por debajo del 30%
    """
    base = atk * random.uniform(0.85, 1.15)
    if has_fury and fury_active:
        base *= 1.10  # +10% ATK
    reduction = rival_def * 0.4
    if is_defending:
        reduction *= 2.5
    damage = base - reduction
    # Probabilidad de crítico
    crit = random.random() < (0.10 + extra_crit_pct)
    if crit:
        damage *= 1.5
    damage = max(1, int(damage))
    return damage, crit


def calc_special_damage(mag, rival_def, is_defending=False):
    """Calcula daño de la acción Especial (escala con MAG, no ATK)."""
    base = mag * 1.8 * random.uniform(0.9, 1.1)
    reduction = rival_def * 0.3
    if is_defending:
        reduction *= 2.0
    damage = base - reduction
    crit = random.random() < 0.10
    if crit:
        damage *= 1.5
    damage = max(1, int(damage))
    return damage, crit


def calc_defend_heal(max_hp):
    """Calcula la regeneración de HP al usar Defender (5% HP max)."""
    return max(1, int(max_hp * 0.05))


# ──────────────────────────────────────────────
# SISTEMA DE EQUIPO — DEFINICIONES
# ──────────────────────────────────────────────

EQUIPMENT_SLOTS = [
    "Cabeza", "Hombros", "Pecho", "Pantalones",
    "Botas", "Arma", "Escudo", "Bastón mágico",
]

SLOT_EMOJIS = {
    "Cabeza": "🪖",
    "Hombros": "🦾",
    "Pecho": "🛡️",
    "Pantalones": "👖",
    "Botas": "👢",
    "Arma": "⚔️",
    "Escudo": "🛡️",
    "Bastón mágico": "🪄",
}

# Stat principal por slot (doc sección 3)
SLOT_PRIMARY_STAT = {
    "Cabeza":        "hp",
    "Hombros":       "hp",
    "Pecho":         "hp",   # valor base mayor (pieza más "tanque")
    "Pantalones":    "hp",
    "Botas":         "hp",
    "Arma":          "atk",
    "Escudo":        "def",
    "Bastón mágico": "mag",
}

# Factor extra para Pecho (pieza más "tanque")
CHEST_BONUS_FACTOR = 1.20

# ──────────────────────────────────────────────
# RAREZAS (doc sección 4.1)
# ──────────────────────────────────────────────

RARITIES = [
    {"name": "Común",      "color": "⬜", "hex": 0x808080, "prob": 0.45,
     "mult": 1.0,  "secondaries": 0, "sec_weight": 0.00},
    {"name": "Poco Común", "color": "🟩", "hex": 0x00ff00, "prob": 0.30,
     "mult": 1.2,  "secondaries": 1, "sec_weight": 0.45},
    {"name": "Raro",       "color": "🟦", "hex": 0x0080ff, "prob": 0.18,
     "mult": 1.45, "secondaries": 1, "sec_weight": 0.45},
    {"name": "Épico",      "color": "🟪", "hex": 0x9900ff, "prob": 0.06,
     "mult": 1.75, "secondaries": 2, "sec_weight": 0.40},
    {"name": "Legendario", "color": "🟧", "hex": 0xff8800, "prob": 0.01,
     "mult": 2.15, "secondaries": 2, "sec_weight": 0.40},
]

RARITY_COLORS = {r["name"]: r["hex"] for r in RARITIES}
_RARITY_LOOKUP = {r["name"]: r for r in RARITIES}

# Drop rates
DROP_RATE_WINNER = 0.35
DROP_RATE_LOSER = 0.15

# ──────────────────────────────────────────────
# EFECTOS PASIVOS DE EQUIPAMIENTO
# ──────────────────────────────────────────────

ITEM_PASSIVES = [
    {
        "id": "dodge",
        "name": "Esquiva mejorada",
        "emoji": "💨",
        "desc": "+5% de probabilidad de esquivar un ataque",
    },
    {
        "id": "vampirism",
        "name": "Vampirismo",
        "emoji": "🧛",
        "desc": "Cura el 8% del daño infligido",
    },
    {
        "id": "second_wind",
        "name": "Segundo aliento",
        "emoji": "💫",
        "desc": "Al llegar a 0 HP por primera vez, sobrevive con 1 HP (una vez)",
    },
    {
        "id": "regen",
        "name": "Regeneración",
        "emoji": "💚",
        "desc": "Cura 3% del HP máximo al inicio de cada turno propio",
    },
    {
        "id": "fury",
        "name": "Furia creciente",
        "emoji": "🔥",
        "desc": "+10% de Ataque cuando el HP está por debajo del 30%",
    },
    {
        "id": "arcane_shield",
        "name": "Escudo arcano",
        "emoji": "🔮",
        "desc": "El primer golpe recibido en el duelo se reduce a la mitad",
    },
    {
        "id": "crit_boost",
        "name": "Golpe crítico",
        "emoji": "⚡",
        "desc": "+10% de probabilidad de crítico (x1.5 daño) en Atacar",
    },
    {
        "id": "mana_residual",
        "name": "Maná residual",
        "emoji": "✨",
        "desc": "La acción Especial tiene un turno menos de enfriamiento",
    },
    {
        "id": "parry",
        "name": "Parada y Contraataque",
        "emoji": "⚔️",
        "desc": "Al Defender, contraatacas por el 75% del daño recibido y te curas un 30% del mismo, pero no reduces daño ni te curas de forma normal.",
    },
    {
        "id": "bleed_on_hit",
        "name": "Filo Sangrante",
        "emoji": "🩸",
        "desc": "15% de probabilidad de aplicar Sangrado (3 turnos) al golpear con esta arma",
    },
    {
        "id": "windfury",
        "name": "Viento de Guerra",
        "emoji": "🌪️",
        "desc": "15% de probabilidad al Atacar de dar un golpe adicional por 50% del daño normal. (ICD: 2 turnos)",
    },
    {
        "id": "hawk_strike",
        "name": "Golpe de Halcón",
        "emoji": "🦅",
        "desc": "+8% de probabilidad de crítico, exclusivo en Atacar (no en Especial)",
    },
    {
        "id": "deathtouch",
        "name": "Toque Letal",
        "emoji": "💀",
        "desc": "Si tu golpe deja al objetivo por debajo de 15% HP sin matarlo, inflige 10% adicional del daño ya hecho como rebote",
    },
    {
        "id": "chain_lightning",
        "name": "Cadena de Tormenta",
        "emoji": "⛈️",
        "desc": "En raid, 10% de probabilidad al usar Especial de golpear también a un esbirro vivo por 30% del daño. (ICD: 3 turnos)",
    },
    {
        "id": "stoneskin",
        "name": "Piel de Piedra",
        "emoji": "🗿",
        "desc": "Reduce en 3 el daño plano de cada golpe físico recibido (después de mitigación)",
    },
    {
        "id": "erratic_ward",
        "name": "Absorción Errática",
        "emoji": "🛡️",
        "desc": "Al bajar de 25% HP, gana un escudo de 10% HP máximo. Una vez por combate.",
    },
    {
        "id": "bloodlust_proc",
        "name": "Sed de Batalla",
        "emoji": "💢",
        "desc": "10% de probabilidad al recibir daño de reducir en 1 turno tu cooldown actual de Especial. (ICD: 3 turnos)",
    },
    {
        "id": "blinding_edge",
        "name": "Filo Cegador",
        "emoji": "🌫️",
        "desc": "8% de probabilidad al Atacar de aplicar Ceguera (2 turnos) al objetivo. (ICD: 4 turnos)",
    },
    {
        "id": "glass_heart",
        "name": "Corazón Fragmentado",
        "emoji": "💔",
        "desc": "+12% ATK/MAG, pero -8% HP máximo",
    },
    {
        "id": "eternal_watch",
        "name": "Vigilancia Eterna",
        "emoji": "👁️",
        "desc": "Inmune al primer debuff de control (Aturdimiento/Congelación/Silencio/Ceguera) que recibas cada combate",
    },
]

PASSIVE_LOOKUP = {p["id"]: p for p in ITEM_PASSIVES}

MINI_AFFIXES = {
    "furia":     {"stat": "atk", "epico": 0.03, "legendario": 0.06, "name": "De la Furia"},
    "vacio":     {"stat": "mag", "epico": 0.03, "legendario": 0.06, "name": "Del Vacío"},
    "bastion":   {"stat": "def", "epico": 0.03, "legendario": 0.06, "name": "Del Bastión"},
    "vital":     {"stat": "hp",  "epico": 0.03, "legendario": 0.06, "name": "Vital"},
    "cazador":   {"stat": "crit", "epico": 0.02, "legendario": 0.04, "name": "Del Cazador"},
    "fantasma":  {"stat": "dodge", "epico": 0.02, "legendario": 0.04, "name": "Del Fantasma"},
}


def can_proc(combatant, passive_id, current_turn, icd_turns):
    """Verifica si un proc con Cooldown Interno (ICD) puede dispararse."""
    last = combatant.passive_icd.get(passive_id, -999)
    return current_turn - last >= icd_turns


def mark_proc(combatant, passive_id, current_turn):
    """Registra el turno en que se disparó un proc para calcular su ICD."""
    combatant.passive_icd[passive_id] = current_turn



# ──────────────────────────────────────────────
# SISTEMA PROCEDURAL DE NOMBRES (doc sección 6)
# ──────────────────────────────────────────────

# 6.1 — Nombres base por slot (6 por slot)
_SLOT_BASE_NAMES = {
    "Cabeza":        ["Yelmo", "Casco", "Corona", "Capucha", "Diadema", "Tocado"],
    "Hombros":       ["Hombreras", "Manto", "Espaldar", "Charreteras", "Guardahombros", "Hombreras de placas"],
    "Pecho":         ["Coraza", "Pechera", "Peto", "Armadura", "Túnica", "Loriga"],
    "Pantalones":    ["Grebas", "Pantalones", "Calzas", "Perneras", "Faldón", "Leggings de cuero"],
    "Botas":         ["Botas", "Botines", "Sandalias", "Grebas de pie", "Zapatos de combate", "Botas de marcha"],
    "Arma":          ["Espada", "Hacha", "Maza", "Daga", "Lanza", "Estoque"],
    "Escudo":        ["Escudo", "Broquel", "Rodela", "Pavés", "Égida", "Tarja"],
    "Bastón mágico": ["Bastón", "Cetro", "Vara", "Báculo", "Vara arcana", "Cayado"],
}

_SLOT_BASE_NAMES_BY_MATERIAL = {
    "Cabeza": {
        "Tela": ["Capucha", "Diadema", "Tocado", "Sombrero arcano", "Corona de tela"],
        "Cuero": ["Capucha de cuero", "Casco de cuero", "Visera de cuero", "Tocado de cuero", "Máscara de cuero"],
        "Hierro": ["Yelmo de placas", "Casco de hierro", "Corona de hierro", "Gran yelmo", "Yelmo cerrado"]
    },
    "Hombros": {
        "Tela": ["Manto", "Estola", "Hombreras de seda", "Amparo arcano"],
        "Cuero": ["Hombreras de cuero", "Espaldar de cuero", "Guardahombros de cuero"],
        "Hierro": ["Hombreras de placas", "Espaldar de hierro", "Guardahombros de hierro", "Placas de hombro"]
    },
    "Pecho": {
        "Tela": ["Túnica", "Toga", "Vestiduras", "Hábito", "Seda de pecho"],
        "Cuero": ["Jubón", "Pechera de cuero", "Armadura de cuero", "Chaqueta de cuero"],
        "Hierro": ["Coraza", "Peto de placas", "Armadura de hierro", "Cota de malla"]
    },
    "Pantalones": {
        "Tela": ["Calzas", "Pantalones de lino", "Faldón de seda", "Falda arcana"],
        "Cuero": ["Pantalones de cuero", "Calzas de cuero", "Perneras de cuero"],
        "Hierro": ["Grebas", "Pantalones de placas", "Perneras de hierro", "Faldón de placas"]
    },
    "Botas": {
        "Tela": ["Botas de seda", "Zapatos de lino", "Sandalias arcanas", "Zapatillas"],
        "Cuero": ["Botas de cuero", "Botines de cuero", "Zapatos de cuero"],
        "Hierro": ["Escarpes de hierro", "Botas de placas", "Botas de hierro", "Grebas de pie"]
    }
}

# 6.2 — Sufijos por stat secundaria dominante
_STAT_SUFFIXES = {
    "atk": ["del Águila", "del Cazador"],
    "def": ["del Oso", "de la Fortaleza"],
    "mag": ["del Archimago", "del Vacío"],
    "hp":  ["del Fénix", "del Titán"],
}

_PASSIVE_VARIANT_WORDS = {
    "dodge": "Escurridizo", "vampirism": "Sediento", "second_wind": "Renacido",
    "regen": "Vital", "fury": "Furioso", "arcane_shield": "Protegido",
    "crit_boost": "Certero", "mana_residual": "del Éter", "parry": "del Duelista",
    "bleed_on_hit": "Sangriento", "windfury": "del Viento", "hawk_strike": "del Halcón",
    "deathtouch": "de la Muerte", "chain_lightning": "de la Tormenta", "stoneskin": "Pétreo",
    "erratic_ward": "del Vacío Errante", "bloodlust_proc": "del Frenesí",
    "blinding_edge": "Cegador", "glass_heart": "Quebrado", "eternal_watch": "Vigilante",
}

_MINI_AFFIX_WORDS = {
    "furia": "del Berserker", "vacio": "del Vacío", "bastion": "del Guardián",
    "vital": "del Coloso", "cazador": "del Verdugo", "fantasma": "del Espectro",
}

_WEAPON_SUBTYPE_BASE_NAMES = {
    "daga": ["Daga", "Estoque", "Puñal"],
    "espada": ["Espada", "Maza", "Estoque"],
    "lanza": ["Lanza", "Alabarda", "Pica"],
    "hacha": ["Hacha", "Hacha de guerra", "Hachuela"],
    "baston": ["Bastón", "Cayado"],
    "orbe": ["Orbe", "Esfera arcana"],
    "tomo": ["Tomo", "Grimorio"],
    "cetro": ["Cetro", "Vara real"],
}

# 6.3 — Prefijos por rareza (vacío para Común)
_RARITY_PREFIXES = {
    "Común":      ["", "", "gastado", "oxidado", "desgastado", "simple"],
    "Poco Común": ["", "reforzado", "templado", "pulido", "curtido"],
    "Raro":       ["", "certero", "afilado", "resonante", "grabado"],
    "Épico":      ["Refulgente", "Imponente", "Sagrado", "Vengador", "Tempestuoso"],
    "Legendario": ["Resplandeciente", "Ancestral", "Divino", "Eterno", "Inquebrantable"],
}


def _generate_item_name(slot, rarity_name, first_secondary_stat, material=None, passive_id=None, mini_affix_key=None, weapon_subtype=None):
    """Genera un nombre en 4 capas."""
    # Subvariante (base)
    if weapon_subtype and weapon_subtype in _WEAPON_SUBTYPE_BASE_NAMES:
        base_name = random.choice(_WEAPON_SUBTYPE_BASE_NAMES[weapon_subtype])
    elif material and slot in _SLOT_BASE_NAMES_BY_MATERIAL:
        base_name = random.choice(_SLOT_BASE_NAMES_BY_MATERIAL[slot][material])
    else:
        base_name = random.choice(_SLOT_BASE_NAMES.get(slot, ["Objeto"]))

    # Variante (ligada al pasivo, si tiene)
    variant = ""
    if passive_id and passive_id in _PASSIVE_VARIANT_WORDS:
        variant = " " + _PASSIVE_VARIANT_WORDS[passive_id]
    elif not passive_id and not mini_affix_key and first_secondary_stat and first_secondary_stat in _STAT_SUFFIXES:
        variant = " " + random.choice(_STAT_SUFFIXES[first_secondary_stat])

    # Mini afijo (solo Épico/Legendario)
    mini_affix_word = ""
    if mini_affix_key and mini_affix_key in _MINI_AFFIX_WORDS:
        mini_affix_word = " " + _MINI_AFFIX_WORDS[mini_affix_key]

    # Afijo (prefijo de rareza, como ya existía)
    prefix_pool = _RARITY_PREFIXES.get(rarity_name, [""])
    if rarity_name in ("Épico", "Legendario"):
        prefix = random.choice(prefix_pool)
    elif rarity_name in ("Poco Común", "Raro"):
        prefix = random.choice(prefix_pool) if random.random() < 0.5 else ""
    else:
        prefix = random.choice(prefix_pool) if random.random() < 0.3 else ""

    parts = [p for p in [prefix, base_name.strip() + variant, mini_affix_word.strip()] if p]
    return " ".join(parts)


# ──────────────────────────────────────────────
# GENERACIÓN DE ÍTEMS (doc sección 4)
# ──────────────────────────────────────────────

def _calc_primary_value(ilvl, rarity_mult, is_chest=False):
    """valor_base(ilvl) = 2 + ilvl × 1.1, luego × rarity_mult."""
    base = 2 + ilvl * 1.1
    value = base * rarity_mult
    if is_chest:
        value *= CHEST_BONUS_FACTOR
    return max(1, int(value))


def _calc_secondary_value(primary_value, sec_weight):
    """El secundario es un % del valor principal."""
    return max(1, int(primary_value * sec_weight))


def _pick_secondary_stats(primary_stat, count, material=None):
    """Elige `count` stats secundarias de las 3 restantes (nunca repite principal) con sesgo de material."""
    pool = [s for s in ALL_STATS if s != primary_stat]
    if material == "Hierro":
        weights = {"hp": 5, "def": 5, "atk": 2, "mag": 0.1}
    elif material == "Cuero":
        weights = {"atk": 5, "hp": 4, "def": 2, "mag": 0.5}
    elif material == "Tela":
        weights = {"mag": 6, "hp": 4, "def": 0.5, "atk": 0.5}
    else:
        random.shuffle(pool)
        return pool[:count]

    filtered_pool = [s for s in pool if s in weights]
    filtered_weights = [weights[s] for s in filtered_pool]
    chosen = []
    for _ in range(min(count, len(filtered_pool))):
        total_w = sum(filtered_weights)
        if total_w <= 0:
            break
        roll = random.random() * total_w
        cum = 0.0
        for idx, s in enumerate(filtered_pool):
            cum += filtered_weights[idx]
            if roll <= cum:
                chosen.append(s)
                filtered_pool.pop(idx)
                filtered_weights.pop(idx)
                break
    return chosen


def generate_loot(player_level, ilvl=None, floor_idx=0):
    """Genera un ítem de loot aleatorio con el sistema completo.

    Returns:
        dict con: slot, name, rarity, rarity_color, rarity_hex, item_level,
                  primary_stat, primary_value, secondaries (list of {stat, value}),
                  passive (dict or None), sell_price, stats_summary (dict), material
    """
    slot = random.choice(EQUIPMENT_SLOTS)
    rarity = _roll_rarity(floor_idx=floor_idx)
    if ilvl is None:
        ilvl = player_level
    
    is_armor = slot in ("Cabeza", "Hombros", "Pecho", "Pantalones", "Botas")
    material = None
    
    if is_armor:
        material = random.choice(["Tela", "Cuero", "Hierro"])
        if material == "Hierro":
            primary_stat = random.choice(["hp", "def"])
        elif material == "Cuero":
            primary_stat = random.choice(["hp", "atk"])
        else: # Tela
            primary_stat = random.choice(["hp", "mag"])
    else:
        primary_stat = SLOT_PRIMARY_STAT[slot]
        
    # Determinar subtipo de arma si corresponde
    weapon_subtype = None
    if slot == "Arma":
        weapon_subtype = random.choice(["daga", "espada", "lanza", "hacha"])
    elif slot == "Bastón mágico":
        weapon_subtype = random.choice(["baston", "orbe", "tomo", "cetro"])

    is_chest = (slot == "Pecho")

    # Stat principal
    primary_value = _calc_primary_value(ilvl, rarity["mult"], is_chest)
    if weapon_subtype in ("daga", "orbe"):
        primary_value = int(primary_value * 0.92)

    # Stats secundarias
    sec_count = rarity["secondaries"]
    sec_weight = rarity["sec_weight"]
    secondary_stats = _pick_secondary_stats(primary_stat, sec_count, material)
    secondaries = []
    for sec_stat in secondary_stats:
        sec_value = _calc_secondary_value(primary_value, sec_weight)
        secondaries.append({"stat": sec_stat, "value": sec_value})

    # Pasivos: se otorgan a partir de rareza "Raro" en adelante
    passive = None
    if rarity["name"] in ("Raro", "Épico", "Legendario"):
        candidates = ITEM_PASSIVES
        if slot != "Arma" or primary_stat != "atk":
            candidates = [p for p in ITEM_PASSIVES if p["id"] != "bleed_on_hit"]
        passive = random.choice(candidates).copy()

    # Mini-afijos: para Épico o Legendario
    mini_affix = None
    if rarity["name"] in ("Épico", "Legendario"):
        key = random.choice(list(MINI_AFFIXES.keys()))
        tier = "epico" if rarity["name"] == "Épico" else "legendario"
        mini_affix = {
            "key": key,
            "stat": MINI_AFFIXES[key]["stat"],
            "value": MINI_AFFIXES[key][tier],
            "name": MINI_AFFIXES[key]["name"]
        }

    # Nombre procedural
    first_sec = secondaries[0]["stat"] if secondaries else None
    name = _generate_item_name(
        slot, rarity["name"], first_sec, material,
        passive_id=passive["id"] if passive else None,
        mini_affix_key=mini_affix["key"] if mini_affix else None,
        weapon_subtype=weapon_subtype
    )

    # Precio de venta
    sell_price = calc_sell_price(rarity["name"], ilvl)

    # Resumen de stats como dict (para bonus de equipo)
    stats_summary = {primary_stat: primary_value}
    for sec in secondaries:
        stats_summary[sec["stat"]] = stats_summary.get(sec["stat"], 0) + sec["value"]

    return {
        "slot": slot,
        "name": name,
        "rarity": rarity["name"],
        "rarity_color": rarity["color"],
        "rarity_hex": rarity["hex"],
        "item_level": ilvl,
        "primary_stat": primary_stat,
        "primary_value": primary_value,
        "secondaries": secondaries,
        "passive": passive,
        "mini_affix": mini_affix,
        "weapon_subtype": weapon_subtype,
        "sell_price": sell_price,
        "stats_summary": stats_summary,
        "material": material,
    }


def _roll_rarity(floor_idx=0):
    """Elige rareza basándose en las probabilidades definidas."""
    roll = random.random()
    cumulative = 0.0
    rolled = None
    for rarity in RARITIES:
        cumulative += rarity["prob"]
        if roll <= cumulative:
            rolled = rarity
            break
    if rolled is None:
        rolled = RARITIES[0]

    # Enforce rarity floor by name comparison index
    rarity_names = [r["name"] for r in RARITIES]
    rolled_idx = rarity_names.index(rolled["name"])
    if rolled_idx < floor_idx:
        rolled = RARITIES[floor_idx]
    return rolled


def calc_sell_price(rarity_name, item_level):
    """Calcula el precio de venta de un ítem."""
    rarity_multipliers = {
        "Común": 1.0,
        "Poco Común": 2.0,
        "Raro": 4.0,
        "Épico": 8.0,
        "Legendario": 15.0,
    }
    mult = rarity_multipliers.get(rarity_name, 1.0)
    return max(10, int(50 * mult * (1 + item_level * 0.1)))


# ──────────────────────────────────────────────
# BONUS DE EQUIPO (4 stats + pasivos)
# ──────────────────────────────────────────────

def calc_equipment_bonus(equipment_dict):
    """Calcula el bonus total de equipo a partir del dict slot→item.

    Args:
        equipment_dict: dict de slot -> {
            'primary_stat', 'primary_value',
            'secondaries': [{'stat', 'value'}, ...],
            'passive': {...} or None,
            'gem': {...} or None
        }

    Returns:
        tuple (bonus_dict, passives_list, secondary_bonus_dict)
        bonus_dict: {'atk': N, 'mag': N, 'def': N, 'hp': N}
        passives_list: lista de dicts de pasivos activos
        secondary_bonus_dict: {'dodge': F, 'crit': F}
    """
    bonus = {"atk": 0, "mag": 0, "def": 0, "hp": 0}
    secondary_bonus = {"dodge": 0.0, "crit": 0.0}
    passives = []

    for slot, item in equipment_dict.items():
        # Stat principal
        ps = item.get("primary_stat", "hp")
        pv = item.get("primary_value", 0)
        if ps in bonus:
            bonus[ps] += pv

        # Stats secundarias
        for sec in item.get("secondaries", []):
            ss = sec.get("stat", "hp")
            sv = sec.get("value", 0)
            if ss in bonus:
                bonus[ss] += sv

        # Pasivos
        passive = item.get("passive")
        if passive:
            passives.append(passive)

        # Gema equipada
        gem = item.get("gem")  # dict con stat_target/bonus_value/is_percentage, o None
        if gem:
            if gem["is_percentage"]:
                if gem["stat_target"] in secondary_bonus:
                    secondary_bonus[gem["stat_target"]] += gem["bonus_value"]
            else:
                if gem["stat_target"] in bonus:
                    bonus[gem["stat_target"]] += gem["bonus_value"]

        # Mini-afijo (crítico y esquiva)
        ma_key = item.get("mini_affix_key")
        ma_val = item.get("mini_affix_value")
        if ma_key and ma_val is not None:
            if ma_key in ("cazador", "fantasma"):
                stat_target = "crit" if ma_key == "cazador" else "dodge"
                secondary_bonus[stat_target] += ma_val

    return bonus, passives, secondary_bonus


def apply_subclass_equipment_conversion(bonus: dict, subclass_name: str | None) -> tuple[dict, dict]:
    """Aplica la conversión de equipo de la subclase al bonus base.

    Modifica el dict de bonus in-place según las reglas de la subclase.
    Retorna (bonus_modificado, extra_attributes) donde extra_attributes
    contiene stats derivadas como crit_bonus, dodge_chance, heal_power, etc.

    Args:
        bonus: dict {'atk': N, 'mag': N, 'def': N, 'hp': N} del equipo
        subclass_name: nombre de la subclase o None

    Returns:
        tuple (bonus_dict modificado, extra_attrs dict)
        extra_attrs puede contener: crit_chance_bonus, crit_mult_bonus,
        dodge_chance_bonus, heal_power, shield_pool, etc.
    """
    extra = {}
    if not subclass_name:
        return bonus, extra

    from src.utils.subclass_config import SUBCLASSES
    config = SUBCLASSES.get(subclass_name)
    if not config:
        return bonus, extra

    conv = config.get("equipment_conversion")
    if not conv:
        return bonus, extra

    conv_type = conv.get("type")

    if conv_type == "effectiveness_bonus":
        # Stats específicas del equipo rinden un % más
        # Ej: Centinela → DEF y HP de equipo +12%
        pct = conv.get("bonus_pct", 0.0)
        for stat in conv.get("stats", []):
            if stat in bonus:
                bonus[stat] = int(bonus[stat] * (1.0 + pct))

    elif conv_type == "convert_stat":
        # Convierte un % de un stat de equipo en otro
        from_stat = conv.get("from_stat", "")
        to_stat = conv.get("to_stat", "")
        pct = conv.get("convert_pct", 0.0)

        if from_stat in bonus:
            converted_amount = int(bonus[from_stat] * pct)
            bonus[from_stat] -= converted_amount

            # Stats normales (atk, mag, def, hp)
            if to_stat in bonus:
                bonus[to_stat] += converted_amount
            # Stats especiales que no van al bonus normal
            elif to_stat == "shield_pool":
                extra["shield_pool"] = converted_amount
            elif to_stat == "dodge_chance":
                rate = conv.get("conversion_rate", 0.003)
                extra["dodge_chance_bonus"] = min(0.30, converted_amount * rate)
            elif to_stat == "heal_power":
                extra["heal_power"] = converted_amount

    elif conv_type == "special":
        effect = conv.get("effect", "")

        if effect == "atk_to_crit_chance":
            # Duelista: ATK de equipo otorga % de probabilidad de crit
            rate = conv.get("conversion_rate", 0.003)
            extra["crit_chance_bonus"] = min(0.25, bonus.get("atk", 0) * rate)

        elif effect == "atk_to_crit_multiplier":
            # Asesino: ATK de equipo mejora multiplicador de crit
            extra["crit_mult_bonus"] = conv.get("extra_crit_mult", 0.30)

        elif effect == "improve_represalia":
            # Vengador: mejora Represalia
            extra["extra_reflect_pct"] = conv.get("extra_reflect_pct", 0.25)
            extra["less_mitigation_pct"] = conv.get("less_mitigation_pct", 0.15)

        elif effect == "atk_to_aura":
            # Cruzado: parte del ATK se convierte en aura de buff
            aura_pct = conv.get("aura_pct", 0.08)
            extra["aura_atk_buff_pct"] = aura_pct

        elif effect == "extend_debuffs":
            # Trampero: equipo extiende la duración de debuffs
            extra["debuff_extension_turns"] = conv.get("extra_turns", 1)

        elif effect == "mag_boosts_burn_dot":
            # Piromante: MAG de equipo aumenta daño por turno de quemadura
            bonus_per_mag = conv.get("bonus_per_mag", 0.15)
            extra["burn_dot_bonus"] = int(bonus.get("mag", 0) * bonus_per_mag)

        elif effect == "mag_reduces_control_cooldowns":
            # Elementalista: reduce cooldowns de sus habilidades de control
            extra["cooldown_reduction"] = conv.get("cooldown_reduction", 1)

        elif effect == "boost_lifesteal":
            # Oscuro: aumenta % de robo de vida
            extra["extra_drain_pct"] = conv.get("extra_drain_pct", 0.08)

    return bonus, extra


def apply_softcap(raw, cap):
    """Convierte un stat crudo en su valor efectivo aplicando eficiencia decreciente por tramos."""
    if cap <= 0:
        return raw
    if raw <= cap:
        return raw
    effective = cap
    tramo2 = min(raw, cap * 2) - cap
    effective += tramo2 * SOFTCAP_TIER2_EFFICIENCY
    if raw > cap * 2:
        tramo3 = raw - cap * 2
        effective += tramo3 * SOFTCAP_TIER3_EFFICIENCY
    return effective


def get_effective_bonus(bonus, level):
    """Aplica el softcap por tramos a cada stat. Retorna bonus efectivo y pct de eficiencia por stat."""
    base = calc_base_stats(level)
    max_bonus = {stat: int(base[stat] * MAX_GEAR_BONUS_PCT) for stat in ALL_STATS}
    effective = {}
    pct_per_stat = {}

    for stat in ALL_STATS:
        raw = bonus.get(stat, 0)
        cap = max_bonus[stat]
        effective[stat] = apply_softcap(raw, cap)
        pct_per_stat[stat] = (effective[stat] / raw * 100) if raw > 0 else 100.0

    # Porcentaje promedio global para la barra de resumen (eficiencia promedio)
    avg_pct = sum(pct_per_stat.values()) / len(ALL_STATS) if ALL_STATS else 100.0

    return effective, avg_pct, pct_per_stat


LEVEL_STAT_WEIGHT = 11  # 3 (atk) + 3 (mag) + 2*1.5 (def) + 20/10 (hp) — mismo ritmo que calc_base_stats

def calc_power_level(level: int, equipment: dict, subclass_name: str | None = None) -> float:
    """Retorna el 'nivel equivalente' de un jugador: nivel real + bonus de equipo
    convertido a niveles usando la misma tasa de crecimiento que los stats base."""
    bonus, passives, _ = calc_equipment_bonus(equipment)
    # Copiar bonus para evitar modificar el original in-place
    bonus = bonus.copy()
    bonus, _ = apply_subclass_equipment_conversion(bonus, subclass_name)
    effective, _, _ = get_effective_bonus(bonus, level)
    bonus_levels = (
        effective.get("atk", 0)
        + effective.get("mag", 0)
        + effective.get("def", 0) * 1.5
        + effective.get("hp", 0) / 10
    ) / LEVEL_STAT_WEIGHT
    return level + bonus_levels


# ──────────────────────────────────────────────
# UTILIDADES DE FORMATO
# ──────────────────────────────────────────────

def format_progress_bar(current_xp, needed_xp, size=10):
    """Barra de progreso visual."""
    if needed_xp <= 0:
        return "█" * size + " MAX"
    filled = min(size, int((current_xp / needed_xp) * size))
    return "█" * filled + "░" * (size - filled)


def format_hp_bar(current_hp, max_hp, size=15):
    """Barra de HP con colores."""
    pct = current_hp / max_hp if max_hp > 0 else 0
    filled = max(0, min(size, int(pct * size)))
    empty = size - filled

    if pct > 0.5:
        bar = "🟩" * filled + "⬛" * empty
    elif pct > 0.25:
        bar = "🟨" * filled + "⬛" * empty
    else:
        bar = "🟥" * filled + "⬛" * empty

    return f"{bar} {current_hp}/{max_hp}"


def format_stat_type(stat_type):
    """Formatea el nombre del stat para display."""
    names = {
        "hp":  "❤️ HP",
        "atk": "⚔️ ATK",
        "mag": "🔮 MAG",
        "def": "🛡️ DEF",
        "dodge": "💨 Evasión",
        "crit": "⚡ Crítico",
    }
    return names.get(stat_type, stat_type.upper())


def format_passive_short(passive):
    """Formatea un pasivo para display breve."""
    if not passive:
        return ""
    return f"{passive.get('emoji', '✨')} {passive['name']}"


def format_item_stats_display(item):
    """Formatea todas las stats de un ítem para display."""
    lines = [f"{format_stat_type(item['primary_stat'])}: **+{item['primary_value']}**"]
    for sec in item.get("secondaries", []):
        lines.append(f"{format_stat_type(sec['stat'])}: +{sec['value']}")
    if item.get("passive"):
        p = item["passive"]
        lines.append(f"{p.get('emoji', '✨')} *{p['name']}*")

    # Mini-afijo
    ma_key = None
    ma_val = None
    ma_name = None
    if "mini_affix" in item and item["mini_affix"]:
        ma_key = item["mini_affix"]["key"]
        ma_val = item["mini_affix"]["value"]
        ma_name = item["mini_affix"]["name"]
    elif "mini_affix_key" in item and item["mini_affix_key"]:
        ma_key = item["mini_affix_key"]
        ma_val = item["mini_affix_value"]
        ma_name = MINI_AFFIXES.get(ma_key, {}).get("name", "")

    if ma_key and ma_val is not None:
        stat_map = {"hp": "HP", "atk": "ATK", "mag": "MAG", "def": "DEF", "crit": "crítico", "dodge": "esquiva"}
        stat_lbl = stat_map.get(MINI_AFFIXES.get(ma_key, {}).get("stat", "hp"), "")
        val_lbl = f"+{int(round(ma_val * 100))}%"
        lines.append(f"✨ *{ma_name} ({val_lbl} {stat_lbl})*")

    if item.get("gem"):
        g = item["gem"]
        val_str = f"+{int(g['bonus_value'])}" if not g["is_percentage"] else f"+{int(g['bonus_value'] * 100)}%"
        lines.append(f"💎 *Gema: {g['name']} ({format_stat_type(g['stat_target'])} {val_str})*")
    return "\n".join(lines)


def format_currency(total_bronze: int) -> str:
    """Formatea la moneda de combate en Oro, Plata y Bronce."""
    oro, resto = divmod(total_bronze, 10_000)
    plata, bronce = divmod(resto, 100)
    partes = []
    if oro:
        partes.append(f"🥇{oro}")
    if plata:
        partes.append(f"🥈{plata}")
    if bronce or not partes:
        partes.append(f"🥉{bronce}")
    return " ".join(partes)


# ──────────────────────────────────────────────
# SISTEMA DE SETS DE EQUIPO
# ──────────────────────────────────────────────

EQUIPMENT_SETS_CACHE = {}

def load_equipment_sets_cache():
    """Carga los bonus de los sets de equipo desde la base de datos a la memoria."""
    global EQUIPMENT_SETS_CACHE
    from src.db import db_cursor
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                SELECT SetKey, SetName, Bonus2pc, Bonus4pc
                FROM EquipmentSets
            """)
            for row in cursor.fetchall():
                EQUIPMENT_SETS_CACHE[row[0]] = {
                    "set_key": row[0],
                    "set_name": row[1],
                    "bonus_2pc": row[2],
                    "bonus_4pc": row[3],
                }
    except Exception:
        pass

def get_equipped_set_pieces(equipment_dict: dict) -> dict:
    """Retorna {SetKey: cantidad_de_piezas_equipadas} a partir del equipo del jugador."""
    counts = {}
    if not equipment_dict:
        return counts
    for slot, item in equipment_dict.items():
        if not item:
            continue
        set_key = item.get("set_key")
        if set_key:
            counts[set_key] = counts.get(set_key, 0) + 1
    return counts
