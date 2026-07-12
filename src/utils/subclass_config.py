# ══════════════════════════════════════════════
# CONFIGURACIÓN CENTRALIZADA — SISTEMA DE SUBCLASES
# ══════════════════════════════════════════════

"""
5 clases × 3 subclases = 15 subclases totales.

Cada subclase define:
  - equipment_conversion: cómo transforma los stats de equipo
  - has_taunt / taunt_*: si tiene taunt pasivo (tanques)
  - skill_10: habilidad desbloqueada a Nv.10
  - skill_15: ultimate desbloqueada a Nv.15

Niveles clave:
  Nv.1  = se elige la clase
  Nv.5  = habilidad compartida de clase (ya existe en SKILLS_CONFIG)
  Nv.10 = se elige subclase + primera habilidad diferenciada
  Nv.15 = ultimate individual de subclase
"""

SUBCLASS_UNLOCK_LEVEL = 10
ULTIMATE_UNLOCK_LEVEL = 15

# ──────────────────────────────────────────────
# MAPPING CLASE → SUBCLASES
# ──────────────────────────────────────────────

CLASS_SUBCLASSES = {
    "Guerrero": ["Centinela", "Berserker", "Duelista"],
    "Paladín":  ["Guardián Sagrado", "Vengador", "Cruzado"],
    "Pícaro":   ["Asesino", "Sombra", "Trampero"],
    "Mago":     ["Piromante", "Elementalista", "Arcanista"],
    "Clérigo":  ["Sanador", "Oscuro", "Guardián de la Fe"],
}

# Inverso: subclase → clase
SUBCLASS_TO_CLASS = {}
for _cls, _subs in CLASS_SUBCLASSES.items():
    for _sub in _subs:
        SUBCLASS_TO_CLASS[_sub] = _cls


# ──────────────────────────────────────────────
# TIPOS DE CONVERSIÓN DE EQUIPO
# ──────────────────────────────────────────────
# effectiveness_bonus : stats específicas del equipo rinden un % más
# convert_stat        : convierte un % de un stat de equipo en otro
# special             : efecto custom (se maneja en código)

# ══════════════════════════════════════════════
# DEFINICIONES DE SUBCLASES
# ══════════════════════════════════════════════

SUBCLASSES = {

    # ─────────────── ⚔️ GUERRERO ───────────────

    "Centinela": {
        "class": "Guerrero",
        "emoji": "🛡️",
        "role": "tanque",
        "desc": "Tanque puro. Equipo defensivo rinde más, taunt pasivo al Defender, aturde con Golpe de Escudo.",

        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["def", "hp"],
            "bonus_pct": 0.12,
        },

        "has_taunt": True,
        "taunt_duration": 2,
        "taunt_cooldown": 3,

        "skill_10": {
            "id": "golpe_escudo",
            "name": "Golpe de Escudo",
            "emoji": "🛡️",
            "cooldown": 3,
            "damage_mult": 0.8,
            "damage_stat": "atk",
            "def_mitigation_factor": 0.35,
            "stun_turns": 1,
            "desc": "Daño moderado (0.8×ATK) + aturde al rival 1 turno.",
        },
        "skill_15": {
            "id": "muralla_inquebrantable",
            "name": "Muralla Inquebrantable",
            "emoji": "🏰",
            "cooldown": 6,
            "damage_reduction_pct": 0.50,
            "duration": 3,
            "aoe_in_raid": True,
            "desc": "Reduce daño recibido 50% por 3 turnos (todo el equipo en raid, solo él en duelo).",
        },
    },

    "Berserker": {
        "class": "Guerrero",
        "emoji": "🔥",
        "role": "dps_riesgo",
        "desc": "DPS de alto riesgo. Sacrifica DEF por ATK, más daño cuanto menos HP tiene.",

        "equipment_conversion": {
            "type": "convert_stat",
            "from_stat": "def",
            "to_stat": "atk",
            "convert_pct": 0.40,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "golpe_desesperado",
            "name": "Golpe Desesperado",
            "emoji": "💢",
            "cooldown": 3,
            "damage_stat": "atk",
            "base_damage_mult": 1.0,
            "def_mitigation_factor": 0.30,
            "hp_scaling": True,
            "desc": "Daño que escala inversamente al % HP actual. A menor vida, mayor daño (sin techo).",
        },
        "skill_15": {
            "id": "sed_sangre",
            "name": "Sed de Sangre",
            "emoji": "🩸",
            "cooldown": 6,
            "hp_sacrifice_pct": 0.25,
            "atk_buff_pct": 0.60,
            "buff_duration": 3,
            "desc": "Sacrifica 25% HP actual → +60% ATK por 3 turnos. Todo o nada.",
        },
    },

    "Duelista": {
        "class": "Guerrero",
        "emoji": "🎯",
        "role": "dps_precision",
        "desc": "DPS de precisión. Convierte ATK en crit%, golpe garantizado de crítico y ejecución.",

        "equipment_conversion": {
            "type": "special",
            "effect": "atk_to_crit_chance",
            "conversion_rate": 0.003,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "estocada_precisa",
            "name": "Estocada Precisa",
            "emoji": "🎯",
            "cooldown": 3,
            "damage_mult": 1.2,
            "damage_stat": "atk",
            "def_mitigation_factor": 0.30,
            "guaranteed_crit": True,
            "ignores_evasion_pct": 0.50,
            "desc": "Crítico garantizado + ignora 50% de evasión del rival.",
        },
        "skill_15": {
            "id": "ejecucion",
            "name": "Ejecución",
            "emoji": "⚔️",
            "cooldown": 6,
            "damage_mult": 1.5,
            "damage_stat": "atk",
            "def_mitigation_factor": 0.25,
            "execute_threshold_pct": 0.30,
            "execute_bonus_mult": 2.0,
            "desc": "Daño bonificado ×2.0 si el objetivo está por debajo del 30% HP.",
        },
    },

    # ─────────────── ✝️ PALADÍN ───────────────

    "Guardián Sagrado": {
        "class": "Paladín",
        "emoji": "✨",
        "role": "tanque_hibrido",
        "desc": "Tanque híbrido. DEF genera escudos, taunt protector, escudo compartido y aura de salvación.",

        "equipment_conversion": {
            "type": "convert_stat",
            "from_stat": "def",
            "to_stat": "shield_pool",
            "convert_pct": 0.30,
        },

        "has_taunt": True,
        "taunt_duration": 2,
        "taunt_cooldown": 3,
        "taunt_grants_ally_shield_pct": 0.05,

        "skill_10": {
            "id": "escudo_compartido",
            "name": "Escudo Compartido",
            "emoji": "🛡️",
            "cooldown": 3,
            "shield_pct_of_max_hp": 0.20,
            "target": "lowest_hp_pct",
            "desc": "Otorga escudo (20% HP max) al aliado con menor % HP (raid) o a sí mismo (duelo).",
        },
        "skill_15": {
            "id": "aura_salvacion",
            "name": "Aura de Salvación",
            "emoji": "💛",
            "cooldown": 6,
            "shield_pct": 0.15,
            "hot_pct": 0.05,
            "duration": 3,
            "aoe_in_raid": True,
            "desc": "Escudo (15% HP max) + curación gradual (5% HP max/t) para todo el equipo por 3 turnos.",
        },
    },

    "Vengador": {
        "class": "Paladín",
        "emoji": "⚔️",
        "role": "dps_contraataque",
        "desc": "DPS de contraataque. Mejora Represalia, daño proporcional a daño recibido, reflejo brutal.",

        "equipment_conversion": {
            "type": "special",
            "effect": "improve_represalia",
            "extra_reflect_pct": 0.25,
            "less_mitigation_pct": 0.15,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "castigo_divino",
            "name": "Castigo Divino",
            "emoji": "⚡",
            "cooldown": 3,
            "damage_stat": "atk",
            "base_damage_mult": 0.5,
            "def_mitigation_factor": 0.30,
            "scales_with_damage_taken": True,
            "scaling_factor": 0.10,
            "desc": "Daño base + 10% de todo el daño recibido en el combate. Recompensa aguantar.",
        },
        "skill_15": {
            "id": "juicio_final",
            "name": "Juicio Final",
            "emoji": "⚖️",
            "cooldown": 6,
            "reflect_pct": 1.50,
            "duration": 2,
            "desc": "Refleja 150% del daño recibido durante 2 turnos. Ventana de contragolpe brutal.",
        },
    },

    "Cruzado": {
        "class": "Paladín",
        "emoji": "🚩",
        "role": "soporte_ofensivo",
        "desc": "Soporte ofensivo. Aura de buff para el equipo, estandarte de guerra y carga sagrada.",

        "equipment_conversion": {
            "type": "special",
            "effect": "atk_to_aura",
            "aura_pct": 0.08,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "estandarte_guerra",
            "name": "Estandarte de Guerra",
            "emoji": "🚩",
            "cooldown": 3,
            "atk_buff_pct": 0.20,
            "duration": 3,
            "aoe_in_raid": True,
            "desc": "Buff +20% ATK para todo el equipo (raid) o a sí mismo (duelo) por 3 turnos.",
        },
        "skill_15": {
            "id": "carga_sagrada",
            "name": "Carga Sagrada",
            "emoji": "⚔️",
            "cooldown": 6,
            "damage_mult": 1.8,
            "damage_stat": "atk",
            "def_mitigation_factor": 0.25,
            "aoe_extra_hit_in_raid": True,
            "desc": "El equipo entero lanza un golpe extra fuera de turno (raid) o golpe ×1.8 ATK (duelo).",
        },
    },

    # ─────────────── 🥷 PÍCARO ───────────────

    "Asesino": {
        "class": "Pícaro",
        "emoji": "🗡️",
        "role": "dps_burst",
        "desc": "DPS de burst puro. Multiplicador de crítico mejorado, golpe doble con veneno, ejecución sombría.",

        "equipment_conversion": {
            "type": "special",
            "effect": "atk_to_crit_multiplier",
            "extra_crit_mult": 0.30,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "golpe_sombras",
            "name": "Golpe en las Sombras",
            "emoji": "🗡️",
            "cooldown": 3,
            "damage_mult": 1.0,
            "damage_stat": "atk",
            "def_mitigation_factor": 0.30,
            "double_if_poisoned": True,
            "desc": "Golpe doble si el objetivo ya está envenenado (sinergia con Daga Envenenada).",
        },
        "skill_15": {
            "id": "ejecucion_sombria",
            "name": "Ejecución Sombría",
            "emoji": "💀",
            "cooldown": 6,
            "damage_mult": 2.5,
            "damage_stat": "atk",
            "def_mitigation_factor": 0.20,
            "desc": "Burst de daño muy alto (2.5×ATK). Cooldown largo — todo o nada.",
        },
    },

    "Sombra": {
        "class": "Pícaro",
        "emoji": "👤",
        "role": "evasion",
        "desc": "Evasión pura. DEF se convierte en esquiva, paso fantasma garantiza evadir, danza de cuchillas.",

        "equipment_conversion": {
            "type": "convert_stat",
            "from_stat": "def",
            "to_stat": "dodge_chance",
            "convert_pct": 0.35,
            "conversion_rate": 0.004,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "paso_fantasma",
            "name": "Paso Fantasma",
            "emoji": "👻",
            "cooldown": 3,
            "guaranteed_dodge_next": True,
            "removes_taunt": True,
            "desc": "Esquiva el próximo ataque garantizado. En raid también puede salir de un taunt.",
        },
        "skill_15": {
            "id": "danza_cuchillas",
            "name": "Danza de Cuchillas",
            "emoji": "💃",
            "cooldown": 6,
            "hits": 3,
            "damage_mult_per_hit": 0.7,
            "damage_stat": "atk",
            "def_mitigation_factor": 0.30,
            "evasion_buff_pct": 0.30,
            "evasion_buff_duration": 2,
            "desc": "3 golpes (0.7×ATK c/u) + evasión +30% durante 2 turnos. Ofensivo y defensivo.",
        },
    },

    "Trampero": {
        "class": "Pícaro",
        "emoji": "🕸️",
        "role": "control",
        "desc": "Control de debuffs. Equipo extiende debuffs, aplica estados adicionales, enjambre de trampas.",

        "equipment_conversion": {
            "type": "special",
            "effect": "extend_debuffs",
            "extra_turns": 1,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "trampa_aconito",
            "name": "Trampa de Acónito",
            "emoji": "🕸️",
            "cooldown": 3,
            "damage_mult": 0.6,
            "damage_stat": "atk",
            "def_mitigation_factor": 0.35,
            "debuff_type": "weakness",
            "debuff_value": 0.20,
            "debuff_duration": 3,
            "desc": "Daño leve + aplica Debilidad (-20% ATK) por 3 turnos.",
        },
        "skill_15": {
            "id": "enjambre_trampas",
            "name": "Enjambre de Trampas",
            "emoji": "🕸️",
            "cooldown": 6,
            "damage_mult": 0.8,
            "damage_stat": "atk",
            "def_mitigation_factor": 0.30,
            "debuffs": [
                {"type": "weakness", "value": 0.20, "duration": 3},
                {"type": "fragility", "value": 0.20, "duration": 3},
                {"type": "poison", "dot_damage": 10, "duration": 3},
            ],
            "desc": "Aplica Debilidad (-20% ATK), Fragilidad (-20% DEF) y Veneno de golpe.",
        },
    },

    # ─────────────── 🔮 MAGO ───────────────

    "Piromante": {
        "class": "Mago",
        "emoji": "🔥",
        "role": "dps_dot",
        "desc": "Especialista en DOT de fuego. MAG aumenta daño por turno de quemadura, nuke + quemadura prolongada.",

        "equipment_conversion": {
            "type": "special",
            "effect": "mag_boosts_burn_dot",
            "bonus_per_mag": 0.15,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "llamarada",
            "name": "Llamarada",
            "emoji": "🔥",
            "cooldown": 3,
            "damage_mult": 1.8,
            "damage_stat": "mag",
            "def_mitigation_factor": 0.20,
            "burn_duration": 4,
            "aoe_in_raid": True,
            "desc": "Quemadura reforzada de 4 turnos (duelo) o quemadura AoE (raid).",
        },
        "skill_15": {
            "id": "cataclismo_fuego",
            "name": "Cataclismo de Fuego",
            "emoji": "☄️",
            "cooldown": 6,
            "damage_mult": 2.8,
            "damage_stat": "mag",
            "def_mitigation_factor": 0.15,
            "burn_duration": 5,
            "enhanced_burn_pct": 0.08,
            "desc": "Nuke fuerte (2.8×MAG) + quemadura prolongada de 5 turnos (8% HP max/t).",
        },
    },

    "Elementalista": {
        "class": "Mago",
        "emoji": "❄️",
        "role": "control_versatil",
        "desc": "Control versátil. MAG reduce cooldowns de control, onda de escarcha, tormenta elemental combinada.",

        "equipment_conversion": {
            "type": "special",
            "effect": "mag_reduces_control_cooldowns",
            "cooldown_reduction": 1,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "onda_escarcha",
            "name": "Onda de Escarcha",
            "emoji": "❄️",
            "cooldown": 3,
            "damage_mult": 0.8,
            "damage_stat": "mag",
            "def_mitigation_factor": 0.25,
            "freeze_turns": 1,
            "desc": "Daño leve + congela al rival 1 turno (pierde su próximo turno).",
        },
        "skill_15": {
            "id": "tormenta_elemental",
            "name": "Tormenta Elemental",
            "emoji": "🌪️",
            "cooldown": 6,
            "damage_mult": 1.5,
            "damage_stat": "mag",
            "def_mitigation_factor": 0.20,
            "burn_duration": 2,
            "freeze_turns": 1,
            "desc": "Quemadura 2t + congelación 1t + golpe de rayo (1.5×MAG). Versátil pero no el más fuerte.",
        },
    },

    "Arcanista": {
        "class": "Mago",
        "emoji": "💥",
        "role": "glass_cannon",
        "desc": "Glass cannon. DEF se convierte en MAG, sobrecarga arcana con coste, singularidad devastadora.",

        "equipment_conversion": {
            "type": "convert_stat",
            "from_stat": "def",
            "to_stat": "mag",
            "convert_pct": 0.50,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "sobrecarga_arcana",
            "name": "Sobrecarga Arcana",
            "emoji": "💥",
            "cooldown": 3,
            "damage_mult": 2.5,
            "damage_stat": "mag",
            "def_mitigation_factor": 0.15,
            "self_damage_pct": 0.10,
            "desc": "Nuke a un solo objetivo (2.5×MAG) pero sufre 10% de su HP max como coste.",
        },
        "skill_15": {
            "id": "singularidad",
            "name": "Singularidad",
            "emoji": "🌌",
            "cooldown": 8,
            "damage_mult": 4.0,
            "damage_stat": "mag",
            "def_mitigation_factor": 0.10,
            "self_damage_pct": 0.15,
            "vulnerability_after_turns": 1,
            "vulnerability_pct": 0.30,
            "desc": "El golpe más devastador del juego (4.0×MAG). CD largo, 15% auto-daño, +30% vulnerable 1 turno.",
        },
    },

    # ─────────────── ⚕️ CLÉRIGO ───────────────

    "Sanador": {
        "class": "Clérigo",
        "emoji": "💚",
        "role": "soporte_puro",
        "desc": "Soporte de curación puro. ATK se convierte en poder de curación, curación directa, resurrección.",

        "equipment_conversion": {
            "type": "convert_stat",
            "from_stat": "atk",
            "to_stat": "heal_power",
            "convert_pct": 0.40,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "luz_curativa",
            "name": "Luz Curativa",
            "emoji": "💚",
            "cooldown": 3,
            "heal_pct_of_max_hp": 0.25,
            "target": "lowest_hp_pct",
            "desc": "Cura 25% HP max a un aliado (raid) o a sí mismo (duelo). Curación directa.",
        },
        "skill_15": {
            "id": "resurreccion_parcial",
            "name": "Resurrección Parcial",
            "emoji": "✝️",
            "cooldown": 8,
            "revive_hp_pct": 0.30,
            "self_heal_in_duel_pct": 0.40,
            "desc": "Revive aliado caído con 30% HP (raid). En duelo: auto-curación de 40% HP max.",
        },
    },

    "Oscuro": {
        "class": "Clérigo",
        "emoji": "🖤",
        "role": "dps_drenaje",
        "desc": "DPS de drenaje de vida. Aumenta robo de vida, pacto de sangre anti-curación, consumir alma.",

        "equipment_conversion": {
            "type": "special",
            "effect": "boost_lifesteal",
            "extra_drain_pct": 0.08,
        },

        "has_taunt": False,

        "skill_10": {
            "id": "pacto_sangre",
            "name": "Pacto de Sangre",
            "emoji": "🖤",
            "cooldown": 3,
            "drain_pct": 0.20,
            "anti_heal_duration": 2,
            "desc": "Drena 20% HP actual del rival + impide curación por 2 turnos.",
        },
        "skill_15": {
            "id": "consumir_alma",
            "name": "Consumir Alma",
            "emoji": "👁️",
            "cooldown": 6,
            "base_drain_pct": 0.15,
            "execute_threshold_pct": 0.30,
            "execute_drain_pct": 0.35,
            "desc": "Drenaje masivo: 15% HP actual, o 35% si el objetivo está por debajo del 30% HP.",
        },
    },

    "Guardián de la Fe": {
        "class": "Clérigo",
        "emoji": "🛡️",
        "role": "tanque_hibrido",
        "desc": "Tanque híbrido de soporte. DEF genera escudos repartibles, taunt reducido, santuario de emergencia.",

        "equipment_conversion": {
            "type": "convert_stat",
            "from_stat": "def",
            "to_stat": "shield_pool",
            "convert_pct": 0.25,
        },

        "has_taunt": True,
        "taunt_duration": 2,
        "taunt_cooldown": 4,

        "skill_10": {
            "id": "bendicion_hierro",
            "name": "Bendición de Hierro",
            "emoji": "🛡️",
            "cooldown": 3,
            "shield_pct_of_max_hp": 0.18,
            "target": "specific_ally",
            "desc": "Otorga escudo (18% HP max) a un aliado específico (raid) o a sí mismo (duelo).",
        },
        "skill_15": {
            "id": "santuario",
            "name": "Santuario",
            "emoji": "🏛️",
            "cooldown": 6,
            "shield_pct": 0.15,
            "cleanse_all_debuffs": True,
            "aoe_in_raid": True,
            "self_shield_in_duel_pct": 0.25,
            "desc": "Escudo grupal (15% HP max) + limpia TODOS los debuffs del equipo (raid). Escudo propio mejorado en duelo.",
        },
    },
}


# ──────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────

def get_subclass_config(subclass_name: str) -> dict | None:
    """Retorna la configuración completa de una subclase, o None."""
    return SUBCLASSES.get(subclass_name)


def get_subclass_class(subclass_name: str) -> str | None:
    """Retorna la clase padre de una subclase."""
    return SUBCLASS_TO_CLASS.get(subclass_name)


def get_available_subclasses(class_name: str) -> list[str]:
    """Retorna la lista de subclases disponibles para una clase."""
    return CLASS_SUBCLASSES.get(class_name, [])


def get_subclass_skills(subclass_name: str, player_level: int) -> list[dict]:
    """Retorna las habilidades disponibles de una subclase según el nivel.

    Returns:
        Lista de dicts con info de cada skill disponible.
    """
    config = SUBCLASSES.get(subclass_name)
    if not config:
        return []

    skills = []
    if player_level >= SUBCLASS_UNLOCK_LEVEL and "skill_10" in config:
        skills.append(config["skill_10"])
    if player_level >= ULTIMATE_UNLOCK_LEVEL and "skill_15" in config:
        skills.append(config["skill_15"])
    return skills


def get_all_subclass_info_for_display(class_name: str) -> list[dict]:
    """Retorna info formateada de las 3 subclases de una clase para mostrar al jugador."""
    subclasses = get_available_subclasses(class_name)
    result = []
    for sub_name in subclasses:
        cfg = SUBCLASSES[sub_name]
        result.append({
            "name": sub_name,
            "emoji": cfg["emoji"],
            "role": cfg["role"],
            "desc": cfg["desc"],
            "skill_10_name": cfg["skill_10"]["name"],
            "skill_10_desc": cfg["skill_10"]["desc"],
            "skill_15_name": cfg["skill_15"]["name"],
            "skill_15_desc": cfg["skill_15"]["desc"],
        })
    return result
