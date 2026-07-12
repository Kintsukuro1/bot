"""Progresión de nivel y utilidades para el sistema de duelos PvP.

Sistema de 4 stats (ATK, MAG, DEF, HP), equipo con stats primarios y
secundarios, nombres procedurales y efectos pasivos de Legendario.
"""

import random
import math

# ──────────────────────────────────────────────
# CONSTANTES GLOBALES
# ──────────────────────────────────────────────

MAX_COMBAT_LEVEL = 30
COMBAT_XP_BASE = 500
COMBAT_XP_FACTOR = 1.25

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
    (1,  "Novato"),
    (3,  "Aprendiz de Duelo"),
    (6,  "Combatiente"),
    (9,  "Guerrero"),
    (13, "Veterano de Arena"),
    (17, "Campeón"),
    (21, "Maestro de Armas"),
    (25, "Gladiador"),
    (29, "Leyenda del Combate"),
)

COMBAT_RANK_EMOJIS = {
    "Novato": "🗡️",
    "Aprendiz de Duelo": "⚔️",
    "Combatiente": "🛡️",
    "Guerrero": "💪",
    "Veterano de Arena": "🏟️",
    "Campeón": "🏆",
    "Maestro de Armas": "⚜️",
    "Gladiador": "👑",
    "Leyenda del Combate": "🌟",
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
]

PASSIVE_LOOKUP = {p["id"]: p for p in ITEM_PASSIVES}


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

# 6.3 — Prefijos por rareza (vacío para Común)
_RARITY_PREFIXES = {
    "Común":      ["", "gastado", "oxidado"],
    "Poco Común": ["", "reforzado", "templado"],
    "Raro":       ["", "certero", "afilado"],
    "Épico":      ["Refulgente", "Imponente", "Sagrado"],
    "Legendario": ["Resplandeciente", "Ancestral", "Divino"],
}


def _generate_item_name(slot, rarity_name, first_secondary_stat, material=None):
    """Genera un nombre procedural: [Prefijo rareza] [Base slot] [Sufijo secondary].

    - Común sin secundario: no lleva sufijo.
    - Épico / Legendario: siempre llevan prefijo de rareza.
    - Poco Común / Raro: prefijo opcional (50%).
    """
    if material and slot in _SLOT_BASE_NAMES_BY_MATERIAL:
        base_name = random.choice(_SLOT_BASE_NAMES_BY_MATERIAL[slot][material])
    else:
        base_name = random.choice(_SLOT_BASE_NAMES.get(slot, ["Objeto"]))

    # Sufijo (basado en primera stat secundaria)
    suffix = ""
    if first_secondary_stat and first_secondary_stat in _STAT_SUFFIXES:
        suffix = " " + random.choice(_STAT_SUFFIXES[first_secondary_stat])

    # Prefijo
    prefix_pool = _RARITY_PREFIXES.get(rarity_name, [""])
    if rarity_name in ("Épico", "Legendario"):
        # Siempre lleva prefijo
        prefix = random.choice(prefix_pool)
    elif rarity_name in ("Poco Común", "Raro"):
        # 50% de probabilidad de prefijo
        prefix = random.choice(prefix_pool) if random.random() < 0.5 else ""
    else:
        # Común: 30% de tener prefijo descriptivo
        prefix = random.choice(prefix_pool) if random.random() < 0.3 else ""

    if prefix:
        return f"{prefix} {base_name}{suffix}"
    else:
        return f"{base_name}{suffix}"


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


def generate_loot(player_level):
    """Genera un ítem de loot aleatorio con el sistema completo.

    Returns:
        dict con: slot, name, rarity, rarity_color, rarity_hex, item_level,
                  primary_stat, primary_value, secondaries (list of {stat, value}),
                  passive (dict or None), sell_price, stats_summary (dict), material
    """
    slot = random.choice(EQUIPMENT_SLOTS)
    rarity = _roll_rarity()
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
        
    is_chest = (slot == "Pecho")

    # Stat principal
    primary_value = _calc_primary_value(ilvl, rarity["mult"], is_chest)

    # Stats secundarias
    sec_count = rarity["secondaries"]
    sec_weight = rarity["sec_weight"]
    secondary_stats = _pick_secondary_stats(primary_stat, sec_count, material)
    secondaries = []
    for sec_stat in secondary_stats:
        sec_value = _calc_secondary_value(primary_value, sec_weight)
        secondaries.append({"stat": sec_stat, "value": sec_value})

    # Nombre procedural
    first_sec = secondaries[0]["stat"] if secondaries else None
    name = _generate_item_name(slot, rarity["name"], first_sec, material)

    # Pasivos: se otorgan a partir de rareza "Raro" en adelante
    passive = None
    if rarity["name"] in ("Raro", "Épico", "Legendario"):
        passive = random.choice(ITEM_PASSIVES).copy()

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
        "sell_price": sell_price,
        "stats_summary": stats_summary,
        "material": material,
    }


def _roll_rarity():
    """Elige rareza basándose en las probabilidades definidas."""
    roll = random.random()
    cumulative = 0.0
    for rarity in RARITIES:
        cumulative += rarity["prob"]
        if roll <= cumulative:
            return rarity
    return RARITIES[0]


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
            'passive': {...} or None
        }

    Returns:
        tuple (bonus_dict, passives_list)
        bonus_dict: {'atk': N, 'mag': N, 'def': N, 'hp': N}
        passives_list: lista de dicts de pasivos activos
    """
    bonus = {"atk": 0, "mag": 0, "def": 0, "hp": 0}
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

    return bonus, passives


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
    bonus, passives = calc_equipment_bonus(equipment)
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
    return "\n".join(lines)
