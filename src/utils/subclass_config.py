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
    "Guerrero":   ["Centinela", "Berserker", "Duelista"],
    "Paladín":    ["Guardián Sagrado", "Vengador", "Cruzado"],
    "Pícaro":     ["Asesino", "Sombra", "Trampero"],
    "Mago":       ["Piromante", "Elementalista", "Arcanista"],
    "Clérigo":    ["Sanador", "Oscuro", "Guardián de la Fe"],
    "Arquero":    ["Francotirador", "Cazador", "Explorador"],
    "Monje":      ["Puño de Hierro", "Maestro del Chi", "Caminante del Viento"],
    "Alquimista": ["Toxicólogo", "Quimista", "Loco Experimental"],
    "Invocador":  ["Nigromante", "Bestiario", "Demonólogo"],
    "Ingeniero":  ["Artillero", "Mecánico", "Saboteador"],
    "Chamán":     ["Chamán Mareas", "Chamán Tierra", "Chamán Tormenta"],
    "Bardo":      ["Director", "Inspirador", "Caótico"],
    "Brujo":      ["Pacto Oscuro", "Maldiciente", "Atador de Almas"],
    "Cronomante": ["Cronos", "Manipulador", "Anomalía"],
    "Vampiro":    ["Señor de la Sangre", "Caminante de la Noche", "Sanguinario"],
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

    # ─────────────── 🏹 ARQUERO ───────────────

    "Francotirador": {
        "class": "Arquero",
        "emoji": "🎯",
        "role": "dps_pvp",
        "desc": "Especialista en duelos PvP. +15% daño a enemigos con HP > 70%, marca objetivos para daño amplificado.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["atk"],
            "bonus_pct": 0.15,
        },
        "skill_10": {
            "id": "marca_mortal",
            "name": "Marca Mortal",
            "emoji": "🎯",
            "cooldown": 3,
            "damage_mult": 1.2,
            "damage_stat": "atk",
            "mark_vulnerability_pct": 0.20,
            "duration": 3,
            "desc": "Daño 1.2×ATK + marca al objetivo (+20% daño recibido por 3 turnos).",
        },
        "skill_15": {
            "id": "disparo_letal",
            "name": "Disparo Letal",
            "emoji": "🏹",
            "cooldown": 5,
            "damage_mult": 3.0,
            "damage_stat": "atk",
            "reset_cd_on_kill": True,
            "desc": "Daño masivo (3.0×ATK). Si liquida al objetivo, reinicia inmediatamente su enfriamiento.",
        },
    },

    "Cazador": {
        "class": "Arquero",
        "emoji": "🐺",
        "role": "dps_raids",
        "desc": "Especialista en Raids. +25% daño a enemigos sufriendo debuffs, ralentiza y lanza lluvia de flechas AoE.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["atk", "hp"],
            "bonus_pct": 0.10,
        },
        "skill_10": {
            "id": "flecha_enredadora",
            "name": "Flecha Enredadora",
            "emoji": "🕸️",
            "cooldown": 3,
            "damage_mult": 1.2,
            "damage_stat": "atk",
            "stun_turns": 1,
            "desc": "Daño 1.2×ATK y enreda al rival impidiéndole actuar 1 turno.",
        },
        "skill_15": {
            "id": "lluvia_flechas",
            "name": "Lluvia de Flechas",
            "emoji": "🌧️",
            "cooldown": 5,
            "damage_mult": 1.8,
            "damage_stat": "atk",
            "aoe_in_raid": True,
            "desc": "Dispara una ráfaga a todos los enemigos infligiendo 1.8×ATK en área.",
        },
    },

    "Explorador": {
        "class": "Arquero",
        "emoji": "🌿",
        "role": "evasion_crit",
        "desc": "Maestro del sigilo y la supervivencia. +20% evasión base y emboscadas críticas.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["dodge"],
            "bonus_pct": 0.10,
        },
        "skill_10": {
            "id": "retirada_estrategica",
            "name": "Retirada Estratégica",
            "emoji": "🏃",
            "cooldown": 4,
            "damage_mult": 1.1,
            "damage_stat": "atk",
            "guaranteed_dodge_turns": 1,
            "desc": "Daño 1.1×ATK y se esquiva con éxito el próximo ataque recibido.",
        },
        "skill_15": {
            "id": "emboscada",
            "name": "Emboscada",
            "emoji": "🗡️",
            "cooldown": 5,
            "damage_mult": 2.5,
            "damage_stat": "atk",
            "guaranteed_crit": True,
            "bleed_turns": 3,
            "desc": "Daño devastador (2.5×ATK) con Crítico Garantizado y aplica Sangrado por 3 turnos.",
        },
    },

    # ─────────────── 🐉 MONJE ───────────────

    "Puño de Hierro": {
        "class": "Monje",
        "emoji": "👊",
        "role": "combos_dps",
        "desc": "Especialista en encadenar combos devastadores consumiendo Chi acumulado.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["atk", "def"],
            "bonus_pct": 0.10,
        },
        "skill_10": {
            "id": "barrido_dragon",
            "name": "Barrido del Dragón",
            "emoji": "🐉",
            "cooldown": 3,
            "damage_mult": 2.2,
            "damage_stat": "atk",
            "chi_cost": 3,
            "desc": "Consume 3 Stacks de Chi para infligir 2.2×ATK y aturdir 1 turno.",
        },
        "skill_15": {
            "id": "puno_ciento_patadas",
            "name": "Puño de las Ciento Patadas",
            "emoji": "🥋",
            "cooldown": 5,
            "damage_mult": 4.0,
            "damage_stat": "atk",
            "chi_cost": 5,
            "desc": "Ultimate Devastadora: Consume 5 Chi para infligir 4.0×ATK en una ráfaga de 5 golpes.",
        },
    },

    "Maestro del Chi": {
        "class": "Monje",
        "emoji": "☯️",
        "role": "soporte_tanque",
        "desc": "Equilibrio entre cuerpo y mente. Medita para regenerar vida y sana al equipo.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["hp", "def"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "meditacion_interior",
            "name": "Meditación Interior",
            "emoji": "🧘",
            "cooldown": 3,
            "heal_max_hp_pct": 0.25,
            "chi_gain": 2,
            "desc": "Cura 25% del HP máximo y otorga +2 Stacks de Chi de inmediato.",
        },
        "skill_15": {
            "id": "palma_nirvana",
            "name": "Palma de Nirvana",
            "emoji": "✨",
            "cooldown": 5,
            "damage_mult": 3.0,
            "damage_stat": "mag",
            "group_heal_pct": 0.20,
            "aoe_in_raid": True,
            "desc": "Daño mágico 3.0×MAG + cura a todo el grupo un 20% de su HP máximo.",
        },
    },

    "Caminante del Viento": {
        "class": "Monje",
        "emoji": "🌪️",
        "role": "evasion_dps",
        "desc": "Ágil como la brisa. Alta probabilidad de esquivar y ataques giratorios.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["dodge"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "paso_etereo_monje",
            "name": "Paso Etéreo",
            "emoji": "💨",
            "cooldown": 3,
            "damage_mult": 1.4,
            "damage_stat": "atk",
            "dodge_next": True,
            "desc": "Daño 1.4×ATK y esquiva el siguiente golpe enemigo.",
        },
        "skill_15": {
            "id": "torbellino_celestial",
            "name": "Torbellino Celestial",
            "emoji": "🌀",
            "cooldown": 5,
            "damage_mult": 2.8,
            "damage_stat": "atk",
            "aoe_in_raid": True,
            "chi_gain": 3,
            "desc": "Gira en área infligiendo 2.8×ATK a todos los enemigos y regenera +3 Chi.",
        },
    },

    # ─────────────── 🧪 ALQUIMISTA ───────────────

    "Toxicólogo": {
        "class": "Alquimista",
        "emoji": "☠️",
        "role": "veneno_dot",
        "desc": "Especialista en toxinas fatales y propagación de venenos.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["mag"],
            "bonus_pct": 0.15,
        },
        "skill_10": {
            "id": "bomba_acida",
            "name": "Bomba Ácida",
            "emoji": "🧪",
            "cooldown": 3,
            "damage_mult": 1.3,
            "damage_stat": "mag",
            "def_shred_pct": 0.35,
            "duration": 3,
            "desc": "Daño 1.3×MAG y reduce la DEF enemiga en 35% por 3 turnos.",
        },
        "skill_15": {
            "id": "pandemia",
            "name": "Pandemia",
            "emoji": "☣️",
            "cooldown": 5,
            "damage_mult": 2.5,
            "damage_stat": "mag",
            "double_poison_stack": True,
            "desc": "Daño 2.5×MAG + duplica y extiende todos los efectos de veneno en el objetivo.",
        },
    },

    "Quimista": {
        "class": "Alquimista",
        "emoji": "⚗️",
        "role": "buffs_apoyo",
        "desc": "Maestro de brebajes y pócimas que potencian a los aliados.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["hp", "def"],
            "bonus_pct": 0.10,
        },
        "skill_10": {
            "id": "brebaje_fortificante",
            "name": "Brebaje Fortificante",
            "emoji": "🍷",
            "cooldown": 4,
            "stat_buff_pct": 0.30,
            "duration": 3,
            "desc": "Otorga +30% ATK y +30% DEF por 3 turnos al usuario.",
        },
        "skill_15": {
            "id": "elixir_vida",
            "name": "Elixir de Vida",
            "emoji": "💚",
            "cooldown": 5,
            "heal_max_hp_pct": 0.35,
            "cleanse_debuffs": True,
            "desc": "Restaura 35% del HP Máximo y remueve todos los estados alterados.",
        },
    },

    "Loco Experimental": {
        "class": "Alquimista",
        "emoji": "🧬",
        "role": "caos_riesgo",
        "desc": "Mezclas impredecibles. Alto riesgo y potencia caótica descomunal.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["mag", "atk"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "pocion_inestable",
            "name": "Poción Inestable",
            "emoji": "💥",
            "cooldown": 3,
            "damage_mult": 2.0,
            "damage_stat": "mag",
            "random_effect": True,
            "desc": "Efecto impredecible: Daño masivo, cura sorpresiva o estado alterado al azar.",
        },
        "skill_15": {
            "id": "reaccion_cadena",
            "name": "Reacción en Cadena",
            "emoji": "⚛️",
            "cooldown": 5,
            "damage_mult": 3.5,
            "damage_stat": "mag",
            "apply_2_random_debuffs": True,
            "desc": "Explosión química (3.5×MAG) y aplica 2 debuffs aleatorios al enemigo.",
        },
    },

    # ─────────────── 👹 INVOCADOR ───────────────

    "Nigromante": {
        "class": "Invocador",
        "emoji": "💀",
        "role": "invocaciones_horda",
        "desc": "Señor de los muertos. Invoca esqueletos guerreros que atacan automáticamente cada turno.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["mag", "hp"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "invocar_esqueletos",
            "name": "Levantar Esqueletos",
            "emoji": "🦴",
            "cooldown": 3,
            "summon_type": "esqueleto",
            "summon_count": 2,
            "desc": "Invoca 2 Esqueletos Guerreros que atacan cada turno infligiendo daño automático.",
        },
        "skill_15": {
            "id": "ejercito_de_las_sombras",
            "name": "Ejército de las Sombras",
            "emoji": "👑",
            "cooldown": 5,
            "damage_mult": 3.2,
            "damage_stat": "mag",
            "summon_type": "esqueleto",
            "summon_count": 3,
            "desc": "Daño mágico 3.2×MAG e invoca 3 Esqueletos adicionales al campo de batalla.",
        },
    },

    "Bestiario": {
        "class": "Invocador",
        "emoji": "🐺",
        "role": "invocaciones_tanque",
        "desc": "Compañero de la naturaleza. Invoca un Lobo de Caza que absorbe daño por su amo.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["hp", "def"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "invocar_lobo",
            "name": "Llamar Compañero Lobo",
            "emoji": "🐺",
            "cooldown": 4,
            "summon_type": "lobo",
            "taunt_enemy": True,
            "desc": "Invoca un Lobo Guardián con Taunt que redirige los ataques enemigos hacia él.",
        },
        "skill_15": {
            "id": "furia_alfa",
            "name": "Furia Alfa",
            "emoji": "🐾",
            "cooldown": 5,
            "damage_mult": 2.8,
            "damage_stat": "atk",
            "buff_summon_atk_pct": 0.40,
            "desc": "Ataque combinado (2.8×ATK) y aumenta el ataque del Lobo un +40% por 3 turnos.",
        },
    },

    "Demonólogo": {
        "class": "Invocador",
        "emoji": "😈",
        "role": "invocaciones_dps_riesgo",
        "desc": "Pactos infernales. Invoca un Demonio Abisal que inflige daño masivo a costa de HP propio.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["mag"],
            "bonus_pct": 0.15,
        },
        "skill_10": {
            "id": "pacto_demoniaco",
            "name": "Invocar Demonio",
            "emoji": "🔥",
            "cooldown": 4,
            "self_hp_drain_pct": 0.10,
            "summon_type": "demonio",
            "desc": "Drena 10% del HP propio para invocar un Demonio de Alto Daño Mágico.",
        },
        "skill_15": {
            "id": "apocalipsis_infernal",
            "name": "Apocalipsis Infernal",
            "emoji": "🌋",
            "cooldown": 5,
            "damage_mult": 3.8,
            "damage_stat": "mag",
            "aoe_in_raid": True,
            "desc": "Devastación abisal en área (3.8×MAG) que achicharra a todos los enemigos.",
        },
    },

    # ─────────────── ⚙️ INGENIERO ───────────────

    "Artillero": {
        "class": "Ingeniero",
        "emoji": "💥",
        "role": "torretas_dps",
        "desc": "Especialista en potencia de fuego. Despliega Torretas de Artillería que disparan cada turno.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["atk", "mag"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "desplegar_torreta",
            "name": "Desplegar Torreta de Artillería",
            "emoji": "🔫",
            "cooldown": 3,
            "summon_type": "torreta",
            "desc": "Despliega una Torreta que realiza un disparo autoguiado (0.8×ATK) cada turno.",
        },
        "skill_15": {
            "id": "rafaga_artillera",
            "name": "Ráfaga de Artillería Pesada",
            "emoji": "💣",
            "cooldown": 5,
            "damage_mult": 3.2,
            "damage_stat": "atk",
            "aoe_in_raid": True,
            "desc": "Bombardeo pesado (3.2×ATK) y sobrecarga las torretas para que disparen dos veces.",
        },
    },

    "Mecánico": {
        "class": "Ingeniero",
        "emoji": "🛠️",
        "role": "reparacion_escudos",
        "desc": "Ingeniería de apoyo. Repara escudos, curaciones de blindaje y sobrecarga defensas.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["def", "hp"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "reparacion_blindaje",
            "name": "Reparación de Blindaje",
            "emoji": "🛡️",
            "cooldown": 3,
            "shield_max_hp_pct": 0.20,
            "heal_max_hp_pct": 0.10,
            "desc": "Crea un escudo del 20% HP Máximo y restaura 10% de HP por reparación.",
        },
        "skill_15": {
            "id": "campo_fuerza_nano",
            "name": "Campo de Fuerza Nanotécnico",
            "emoji": "🔮",
            "cooldown": 5,
            "shield_all_raid_pct": 0.25,
            "cleanse_debuffs": True,
            "desc": "Otorga un Escudo Nanotécnico del 25% HP a todo el equipo y purifica debuffs.",
        },
    },

    "Saboteador": {
        "class": "Ingeniero",
        "emoji": "💣",
        "role": "minas_trampas",
        "desc": "Guerra táctica. Coloca Minas Terrestres y Trampas de Gas que detonan al recibir daño.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["atk"],
            "bonus_pct": 0.15,
        },
        "skill_10": {
            "id": "plantar_mina",
            "name": "Plantar Mina Táctica",
            "emoji": "💣",
            "cooldown": 3,
            "summon_type": "mina",
            "desc": "Planta una Mina Táctica en el campo que explota al 2.0×ATK cuando el enemigo ataca.",
        },
        "skill_15": {
            "id": "detonacion_en_cadena",
            "name": "Detonación en Cadena",
            "emoji": "💥",
            "cooldown": 5,
            "damage_mult": 3.4,
            "damage_stat": "atk",
            "stun_turns": 1,
            "desc": "Detona todos los dispositivos e inflige 3.4×ATK con Aturdimiento garantizado.",
        },
    },

    # ─────────────── ⭐ CHAMÁN ───────────────

    "Chamán Mareas": {
        "class": "Chamán",
        "emoji": "🌊",
        "role": "totem_curacion",
        "desc": "Espíritu de las aguas sanadoras. Plante Tótems de Curación que regeneran HP cada turno.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["mag", "hp"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "totem_curacion",
            "name": "Tótem de las Mareas",
            "emoji": "🌊",
            "cooldown": 3,
            "summon_type": "totem_curacion",
            "desc": "Invoca un Tótem de Curación que restaura 8% HP a todo el equipo cada turno.",
        },
        "skill_15": {
            "id": "tsunami_ancestral",
            "name": "Tsunami Ancestral",
            "emoji": "🌊",
            "cooldown": 5,
            "damage_mult": 2.8,
            "damage_stat": "mag",
            "group_heal_pct": 0.20,
            "aoe_in_raid": True,
            "desc": "Onda elemental de agua (2.8×MAG) que daña enemigos y sana 20% HP a los aliados.",
        },
    },

    "Chamán Tierra": {
        "class": "Chamán",
        "emoji": "🗿",
        "role": "totem_defensa",
        "desc": "Fuerza de la roca inamovible. Coloca Tótems de Bastión que reducen el daño recibido.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["def", "hp"],
            "bonus_pct": 0.14,
        },
        "skill_10": {
            "id": "totem_bastion",
            "name": "Tótem de Bastión Pétreo",
            "emoji": "🗿",
            "cooldown": 3,
            "summon_type": "totem_bastion",
            "desc": "Planta un Tótem de Bastión que reduce el daño recibido por el grupo en un 20%.",
        },
        "skill_15": {
            "id": "terremoto_primordial",
            "name": "Terremoto Primordial",
            "emoji": "🌋",
            "cooldown": 5,
            "damage_mult": 3.0,
            "damage_stat": "def",
            "stun_turns": 1,
            "aoe_in_raid": True,
            "desc": "Sacudida de la tierra (3.0×DEF) que aturde a todos los objetivos por 1 turno.",
        },
    },

    "Chamán Tormenta": {
        "class": "Chamán",
        "emoji": "⚡",
        "role": "totem_ira_dps",
        "desc": "Poder del trueno. Coloca Tótems de Ira que aumentan el ATK del grupo y lanzan rayos.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["atk", "mag"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "totem_ira",
            "name": "Tótem de Ira de la Tormenta",
            "emoji": "⚡",
            "cooldown": 3,
            "summon_type": "totem_ira",
            "desc": "Invoca un Tótem de Ira que aumenta el ATK del grupo un +25% por 3 turnos.",
        },
        "skill_15": {
            "id": "tormenta_de_rayos_ancestral",
            "name": "Tormenta de Rayos Ancestral",
            "emoji": "🌩️",
            "cooldown": 5,
            "damage_mult": 3.5,
            "damage_stat": "mag",
            "aoe_in_raid": True,
            "desc": "Carga de truenos masiva (3.5×MAG) que electrocuta a todo el campo enemigo.",
        },
    },

    # ─────────────── 🎭 BARDO ───────────────

    "Director": {
        "class": "Bardo",
        "emoji": "🎼",
        "role": "buffs_daño",
        "desc": "Maestro de armonías ofensivas. Aumenta drásticamente el ATK y daño crítico del equipo.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["atk", "mag"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "marcha_de_guerra",
            "name": "Marcha de Guerra",
            "emoji": "🎺",
            "cooldown": 3,
            "group_atk_buff_pct": 0.30,
            "duration": 3,
            "desc": "Aumenta el ATK de todo el grupo en un +30% por 3 turnos.",
        },
        "skill_15": {
            "id": "crescendo_maestro",
            "name": "Crescendo Maestro",
            "emoji": "🎶",
            "cooldown": 5,
            "damage_mult": 2.5,
            "damage_stat": "mag",
            "group_crit_boost_pct": 0.25,
            "aoe_in_raid": True,
            "desc": "Daño mágico 2.5×MAG + otorga +25% probabilidad de crítico a todo el equipo.",
        },
    },

    "Inspirador": {
        "class": "Bardo",
        "emoji": "✨",
        "role": "buffs_curacion",
        "desc": "Melodías sanadoras de esperanza. Aumenta la eficacia de curación y otorga regene ración continua.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["hp", "def"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "himno_de_sanacion",
            "name": "Himno de Sanación",
            "emoji": "🎵",
            "cooldown": 3,
            "group_heal_pct": 0.18,
            "hot_turns": 2,
            "desc": "Sana 18% HP a todo el equipo y otorga Regeneración por 2 turnos.",
        },
        "skill_15": {
            "id": "requiem_de_proteccion",
            "name": "Réquiem de Protección",
            "emoji": "🛡️",
            "cooldown": 5,
            "shield_all_raid_pct": 0.30,
            "cleanse_debuffs": True,
            "desc": "Crea un Escudo Armónico del 30% HP para todo el grupo y disipa estados alterados.",
        },
    },

    "Caótico": {
        "class": "Bardo",
        "emoji": "🪕",
        "role": "debuffs_desorientacion",
        "desc": "Ritmos disonantes. Confunde y desorienta a los enemigos reduciendo su velocidad y precisión.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["mag"],
            "bonus_pct": 0.15,
        },
        "skill_10": {
            "id": "nota_disonante",
            "name": "Nota Disonante",
            "emoji": "💥",
            "cooldown": 3,
            "damage_mult": 1.4,
            "damage_stat": "mag",
            "enemy_atk_debuff_pct": 0.25,
            "duration": 3,
            "desc": "Daño 1.4×MAG y reduce el ATK del enemigo en 25% por 3 turnos.",
        },
        "skill_15": {
            "id": "sinfonia_del_caos",
            "name": "Sinfonía del Caos",
            "emoji": "🌪️",
            "cooldown": 5,
            "damage_mult": 3.2,
            "damage_stat": "mag",
            "stun_turns": 1,
            "apply_2_random_debuffs": True,
            "desc": "Sinfonía devastadora (3.2×MAG) con Aturdimiento garantizado y 2 debuffs aleatorios.",
        },
    },

    # ─────────────── 🌑 BRUJO ───────────────

    "Pacto Oscuro": {
        "class": "Brujo",
        "emoji": "🔮",
        "role": "sacrificio_hp_dps",
        "desc": "Sacrifica su propia vida para canalizar la magia destructiva de sombras más potente.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["mag"],
            "bonus_pct": 0.15,
        },
        "skill_10": {
            "id": "ofrenda_de_sangre",
            "name": "Ofrenda de Sangre",
            "emoji": "🩸",
            "cooldown": 3,
            "self_hp_drain_pct": 0.12,
            "damage_mult": 2.4,
            "damage_stat": "mag",
            "desc": "Drena 12% del HP propio para asestar un golpe mágico directo de 2.4×MAG.",
        },
        "skill_15": {
            "id": "cataclismo_de_sombras",
            "name": "Cataclismo de Sombras",
            "emoji": "🌌",
            "cooldown": 5,
            "self_hp_drain_pct": 0.20,
            "damage_mult": 4.2,
            "damage_stat": "mag",
            "aoe_in_raid": True,
            "desc": "Sacrifica 20% HP para desatar una tormenta de sombras devastadora (4.2×MAG en área).",
        },
    },

    "Maldiciente": {
        "class": "Brujo",
        "emoji": "📜",
        "role": "debuffs_vulnerabilidad",
        "desc": "Especialista en maldiciones de agonía que reducen stats e impiden la curación enemiga.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["mag", "hp"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "maldicion_de_agonia",
            "name": "Maldición de Agonía",
            "emoji": "☠️",
            "cooldown": 3,
            "damage_mult": 1.2,
            "damage_stat": "mag",
            "curse_vulnerability_pct": 0.30,
            "duration": 3,
            "desc": "Daño 1.2×MAG y aplica Agonía (+30% vulnerabilidad a todo el daño recibido por 3 turnos).",
        },
        "skill_15": {
            "id": "ruina_eterea",
            "name": "Ruina Etérea",
            "emoji": "🕳️",
            "cooldown": 5,
            "damage_mult": 3.0,
            "damage_stat": "mag",
            "curse_heal_reduction_pct": 0.60,
            "desc": "Daño 3.0×MAG y reduce en 60% la capacidad de curación enemiga por 3 turnos.",
        },
    },

    "Atador de Almas": {
        "class": "Brujo",
        "emoji": "⛓️",
        "role": "sanguijuela_escudos",
        "desc": "Sanguijuela de almas. Convierte el daño infligido en escudos de sombras y robo de vida.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["hp", "def"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "drenar_alma",
            "name": "Drenar Alma",
            "emoji": "👻",
            "cooldown": 3,
            "damage_mult": 1.6,
            "damage_stat": "mag",
            "lifesteal_pct": 0.35,
            "desc": "Daño 1.6×MAG y cura al usuario el 35% del daño infligido.",
        },
        "skill_15": {
            "id": "prision_de_almas",
            "name": "Prisión de Almas",
            "emoji": "⛓️",
            "cooldown": 5,
            "damage_mult": 3.2,
            "damage_stat": "mag",
            "soul_shield_pct": 0.25,
            "desc": "Daño 3.2×MAG y genera un Escudo de Almas equivalente al 25% del HP Máximo.",
        },
    },

    # ─────────────── ⏳ CRONOMANTE ───────────────

    "Cronos": {
        "class": "Cronomante",
        "emoji": "⌛",
        "role": "control_cooldowns",
        "desc": "Señor del tiempo. Reduce los enfriamientos del equipo y reinicia habilidades.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["mag"],
            "bonus_pct": 0.15,
        },
        "skill_10": {
            "id": "aceleracion_temporal",
            "name": "Aceleración Temporal",
            "emoji": "⚡",
            "cooldown": 3,
            "reduce_cooldowns_turns": 2,
            "desc": "Reduce en -2 turnos los enfriamientos de todas las habilidades activas del equipo.",
        },
        "skill_15": {
            "id": "reinicio_cronologico",
            "name": "Reinicio Cronológico",
            "emoji": "🌌",
            "cooldown": 6,
            "damage_mult": 3.0,
            "damage_stat": "mag",
            "reset_all_cooldowns": True,
            "desc": "Daño 3.0×MAG y reinicia instantáneamente los enfriamientos del aliado objetivo.",
        },
    },

    "Manipulador": {
        "class": "Cronomante",
        "emoji": "🌀",
        "role": "turnos_extra",
        "desc": "Manipulación de la línea temporal. Otorga turnos adicionales y frena a los enemigos.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["atk", "mag"],
            "bonus_pct": 0.12,
        },
        "skill_10": {
            "id": "distorsion_temporal",
            "name": "Distorsión Temporal",
            "emoji": "🌀",
            "cooldown": 4,
            "grant_extra_turn": True,
            "desc": "Otorga inmediatamente 1 Turno Adicional al usuario.",
        },
        "skill_15": {
            "id": "congelacion_del_tiempo",
            "name": "Congelación del Tiempo",
            "emoji": "❄️",
            "cooldown": 5,
            "damage_mult": 3.4,
            "damage_stat": "mag",
            "stun_turns": 2,
            "desc": "Daño mágico 3.4×MAG y paraliza completamente al enemigo por 2 turnos.",
        },
    },

    "Anomalía": {
        "class": "Cronomante",
        "emoji": "⏳",
        "role": "reversion_daño",
        "desc": "Paradoja temporal. Reconvierte el daño recibido o retrocede la salud en el tiempo.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["hp", "def"],
            "bonus_pct": 0.14,
        },
        "skill_10": {
            "id": "retroceso_de_salud",
            "name": "Retroceso de Salud",
            "emoji": "💚",
            "cooldown": 4,
            "heal_max_hp_pct": 0.30,
            "cleanse_debuffs": True,
            "desc": "Retrocede el tiempo personal restaurando 30% HP y borrando debuffs.",
        },
        "skill_15": {
            "id": "paradoja_destructiva",
            "name": "Paradoja Destructiva",
            "emoji": "💥",
            "cooldown": 5,
            "damage_mult": 3.6,
            "damage_stat": "mag",
            "reflect_past_damage_pct": 0.40,
            "desc": "Daño masivo (3.6×MAG) + refleja el 40% del daño recibido en el último turno.",
        },
    },

    # ─────────────── 🩸 VAMPIRO ───────────────

    "Señor de la Sangre": {
        "class": "Vampiro",
        "emoji": "🩸",
        "role": "hemorragia_dot",
        "desc": "Especialista en la mecánica de Hemorragia Acumulativa. Más fuerte entre más dura el combate.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["atk", "hp"],
            "bonus_pct": 0.14,
        },
        "skill_10": {
            "id": "filo_desgarrador",
            "name": "Filo Desgarrador",
            "emoji": "🗡️",
            "cooldown": 3,
            "damage_mult": 1.5,
            "damage_stat": "atk",
            "bleed_stacks": 2,
            "desc": "Daño 1.5×ATK y aplica 2 Stacks de Hemorragia Acumulativa al objetivo.",
        },
        "skill_15": {
            "id": "estallido_sanguineo",
            "name": "Estallido Sanguíneo",
            "emoji": "💥",
            "cooldown": 5,
            "damage_mult": 3.8,
            "damage_stat": "atk",
            "detonate_bleed_stacks": True,
            "desc": "Daño masivo (3.8×ATK) que detona instantáneamente todos los Stacks de Hemorragia en el rival.",
        },
    },

    "Caminante de la Noche": {
        "class": "Vampiro",
        "emoji": "🦇",
        "role": "evasion_vampirismo",
        "desc": "Forma de murciélago y sombras. Alta probabilidad de esquivar y robo de vida salvaje.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["dodge"],
            "bonus_pct": 0.15,
        },
        "skill_10": {
            "id": "forma_de_murcielago",
            "name": "Forma de Murciélago",
            "emoji": "🦇",
            "cooldown": 3,
            "damage_mult": 1.3,
            "damage_stat": "atk",
            "dodge_next": True,
            "lifesteal_pct": 0.30,
            "desc": "Daño 1.3×ATK con 30% Robo de Vida y esquiva garantizada del próximo golpe.",
        },
        "skill_15": {
            "id": "festin_de_la_noche",
            "name": "Festín de la Noche",
            "emoji": "🍷",
            "cooldown": 5,
            "damage_mult": 3.2,
            "damage_stat": "atk",
            "lifesteal_pct": 0.50,
            "aoe_in_raid": True,
            "desc": "Ataque en área 3.2×ATK recuperando un 50% del daño total infligido como salud.",
        },
    },

    "Sanguinario": {
        "class": "Vampiro",
        "emoji": "👑",
        "role": "tanque_escudo_sangre",
        "desc": "Transforma el sangrado enemigo en escudos de sangre impenetrable y resistencia.",
        "equipment_conversion": {
            "type": "effectiveness_bonus",
            "stats": ["hp", "def"],
            "bonus_pct": 0.14,
        },
        "skill_10": {
            "id": "escudo_de_sangre",
            "name": "Escudo de Sangre",
            "emoji": "🛡️",
            "cooldown": 3,
            "shield_max_hp_pct": 0.25,
            "desc": "Crea un Escudo Sanguíneo equivalente al 25% del HP Máximo.",
        },
        "skill_15": {
            "id": "dominio_vampirico",
            "name": "Dominio Vampírico",
            "emoji": "👑",
            "cooldown": 5,
            "damage_mult": 3.5,
            "damage_stat": "hp",
            "buff_all_stats_pct": 0.20,
            "desc": "Golpe definitivo basado en vida (3.5×HP) y aumenta todos los stats un +20% por 3 turnos.",
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
