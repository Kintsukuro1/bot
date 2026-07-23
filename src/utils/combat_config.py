# ══════════════════════════════════════════════
# CONFIGURACIÓN CENTRALIZADA DE HABILIDADES COMBATE
# ══════════════════════════════════════════════

SKILLS_CONFIG = {
    "ceguera": {
        "id": "ceguera",
        "name": "Tierra a los ojos",
        "emoji": "👁️",
        "class": None,
        "min_level": 1,
        "cooldown": 3,
        "turns": 3,              # Duración de ceguera (3 turnos)
        "fail_chance": 0.65,      # Probabilidad de fallar ataques
        "desc": "Reduce precisión del rival por 3 turnos (65% de fallar)."
    },
    "frenesi": {
        "id": "frenesi",
        "name": "Frenesí de Batalla",
        "emoji": "⚔️",
        "class": "Guerrero",
        "min_level": 5,
        "cooldown": 3,
        "turns": 2,              # Duración del buff de frenesí (2 turnos)
        "atk_boost": 0.35,        # +35% de ataque infligido
        "damage_received_boost": 0.15,  # +15% daño recibido
        "desc": "Guerrero: +35% ATK y +15% daño recibido por 2 turnos."
    },
    "represalia": {
        "id": "represalia",
        "name": "Postura de Represalia",
        "emoji": "🛡️",
        "class": "Paladín",
        "min_level": 5,
        "cooldown": 3,
        "mitigation": 0.50,       # Mitiga el 50% de daño recibido en la ronda
        "reflect": 1.00,          # Refleja el 100% del daño bruto
        "desc": "Paladín: Mitiga 50% y refleja 100% del daño recibido esta ronda."
    },
    "veneno": {
        "id": "veneno",
        "name": "Daga Envenenada",
        "emoji": "🥷",
        "class": "Pícaro",
        "min_level": 5,
        "cooldown": 3,
        "turns": 3,              # Veneno dura 3 turnos
        "dot_damage": 10,         # 10 HP fijos por turno
        "damage_mult": 1.4,       # Daño inicial: 1.4 * ATK
        "def_mitigation_factor": 0.3, # Mitiga con 0.3 * DEF del rival
        "desc": "Pícaro: Daño físico (1.4*ATK) y aplica veneno (10 HP/t) por 3 turnos."
    },
    "quemadura": {
        "id": "quemadura",
        "name": "Tormenta de Fuego",
        "emoji": "🔥",
        "class": "Mago",
        "min_level": 5,
        "cooldown": 3,
        "turns": 3,              # Quemadura dura 3 turnos
        "dot_max_hp_pct": 0.05,   # Daño: 5% del HP máximo del rival por turno
        "damage_mult": 2.2,       # Daño inicial: 2.2 * MAG
        "def_mitigation_factor": 0.2, # Mitiga con 0.2 * DEF del rival
        "desc": "Mago: Daño mágico (2.2*MAG) y aplica quemadura (-5% HP max/t) por 3 turnos."
    },
    "drenaje": {
        "id": "drenaje",
        "name": "Drenaje Sagrado",
        "emoji": "⚕️",
        "class": "Clérigo",
        "min_level": 5,
        "cooldown": 3,
        "drain_pct": 0.15,        # Roba el 15% del HP actual del oponente
        "desc": "Clérigo: Roba 15% HP actual y disipa debuffs propios."
    },
    "disparo_certero_base": {
        "id": "disparo_certero_base",
        "name": "Disparo Certero",
        "emoji": "🏹",
        "class": "Arquero",
        "min_level": 5,
        "cooldown": 3,
        "damage_mult": 1.8,
        "damage_stat": "atk",
        "desc": "Arquero: Daño 1.8×ATK e ignora 30% DEF enemiga."
    },
    "palma_chi_base": {
        "id": "palma_chi_base",
        "name": "Palma del Chi",
        "emoji": "☯️",
        "class": "Monje",
        "min_level": 5,
        "cooldown": 3,
        "damage_mult": 1.7,
        "damage_stat": "atk",
        "desc": "Monje: Golpe marcial de 1.7×ATK que genera +2 Chi."
    },
    "bomba_acida_base": {
        "id": "bomba_acida_base",
        "name": "Bomba Ácida",
        "emoji": "🧪",
        "class": "Alquimista",
        "min_level": 5,
        "cooldown": 3,
        "damage_mult": 1.8,
        "damage_stat": "mag",
        "desc": "Alquimista: Explosión química de 1.8×MAG que reduce DEF."
    },
    "invocar_espectro_base": {
        "id": "invocar_espectro_base",
        "name": "Invocar Espectro",
        "emoji": "👹",
        "class": "Invocador",
        "min_level": 5,
        "cooldown": 3,
        "damage_mult": 1.7,
        "damage_stat": "mag",
        "desc": "Invocador: Daño 1.7×MAG y genera +25 Esencia."
    },
    "descarga_electrica_base": {
        "id": "descarga_electrica_base",
        "name": "Descarga Eléctrica",
        "emoji": "⚙️",
        "class": "Ingeniero",
        "min_level": 5,
        "cooldown": 3,
        "damage_mult": 1.7,
        "damage_stat": "atk",
        "desc": "Ingeniero: Impacto electrostático de 1.7×ATK y genera +25 Energía."
    },
    "choque_elemental_base": {
        "id": "choque_elemental_base",
        "name": "Choque Elemental",
        "emoji": "⭐",
        "class": "Chamán",
        "min_level": 5,
        "cooldown": 3,
        "damage_mult": 1.7,
        "damage_stat": "mag",
        "desc": "Chamán: Golpe elemental 1.7×MAG y genera +1 Tótem."
    },
    "cancion_combate_base": {
        "id": "cancion_combate_base",
        "name": "Canción de Combate",
        "emoji": "🎭",
        "class": "Bardo",
        "min_level": 5,
        "cooldown": 3,
        "damage_mult": 1.6,
        "damage_stat": "mag",
        "desc": "Bardo: Armonía de guerra 1.6×MAG y genera +25 Inspiración."
    },
    "orbe_sombras_base": {
        "id": "orbe_sombras_base",
        "name": "Orbe de Sombras",
        "emoji": "🌑",
        "class": "Brujo",
        "min_level": 5,
        "cooldown": 3,
        "damage_mult": 1.9,
        "damage_stat": "mag",
        "desc": "Brujo: Hechicería de 1.9×MAG drenando 5% HP propio."
    },
    "pulso_temporal_base": {
        "id": "pulso_temporal_base",
        "name": "Pulso Temporal",
        "emoji": "⏳",
        "class": "Cronomante",
        "min_level": 5,
        "cooldown": 3,
        "damage_mult": 1.7,
        "damage_stat": "mag",
        "desc": "Cronomante: Onda temporal de 1.7×MAG y genera +1 Flujo Temporal."
    },
    "mordisco_sanguineo_base": {
        "id": "mordisco_sanguineo_base",
        "name": "Mordisco Sanguíneo",
        "emoji": "🩸",
        "class": "Vampiro",
        "min_level": 5,
        "cooldown": 3,
        "damage_mult": 1.7,
        "damage_stat": "atk",
        "desc": "Vampiro: Estocada 1.7×ATK con 25% Robo de Vida."
    },

    # ══════════════════════════════════════════════
    # HABILIDADES DE SUBCLASE — Nv.10
    # ══════════════════════════════════════════════

    # ⚔️ Guerrero
    "golpe_escudo": {
        "id": "golpe_escudo",
        "name": "Golpe de Escudo",
        "emoji": "🛡️",
        "class": "Guerrero",
        "subclass": "Centinela",
        "min_level": 10,
        "cooldown": 3,
        "damage_mult": 0.8,
        "damage_stat": "atk",
        "def_mitigation_factor": 0.35,
        "stun_turns": 1,
        "desc": "Centinela: Daño moderado + aturde 1 turno."
    },
    "golpe_desesperado": {
        "id": "golpe_desesperado",
        "name": "Golpe Desesperado",
        "emoji": "💢",
        "class": "Guerrero",
        "subclass": "Berserker",
        "min_level": 10,
        "cooldown": 3,
        "damage_stat": "atk",
        "base_damage_mult": 1.0,
        "def_mitigation_factor": 0.30,
        "hp_scaling": True,
        "desc": "Berserker: Daño escala inversamente a tu % HP. Menos vida = más daño."
    },
    "estocada_precisa": {
        "id": "estocada_precisa",
        "name": "Estocada Precisa",
        "emoji": "🎯",
        "class": "Guerrero",
        "subclass": "Duelista",
        "min_level": 10,
        "cooldown": 3,
        "damage_mult": 1.2,
        "damage_stat": "atk",
        "def_mitigation_factor": 0.30,
        "guaranteed_crit": True,
        "ignores_evasion_pct": 0.50,
        "desc": "Duelista: Crítico garantizado + ignora 50% de evasión."
    },

    # ✝️ Paladín
    "escudo_compartido": {
        "id": "escudo_compartido",
        "name": "Escudo Compartido",
        "emoji": "🛡️",
        "class": "Paladín",
        "subclass": "Guardián Sagrado",
        "min_level": 10,
        "cooldown": 3,
        "shield_pct_of_max_hp": 0.20,
        "desc": "Guardián Sagrado: Escudo (20% HP max) al aliado con menor HP o a sí mismo."
    },
    "castigo_divino": {
        "id": "castigo_divino",
        "name": "Castigo Divino",
        "emoji": "⚡",
        "class": "Paladín",
        "subclass": "Vengador",
        "min_level": 10,
        "cooldown": 3,
        "damage_stat": "atk",
        "base_damage_mult": 0.5,
        "def_mitigation_factor": 0.30,
        "scales_with_damage_taken": True,
        "scaling_factor": 0.10,
        "desc": "Vengador: Daño base + 10% del daño total recibido en el combate."
    },
    "estandarte_guerra": {
        "id": "estandarte_guerra",
        "name": "Estandarte de Guerra",
        "emoji": "🚩",
        "class": "Paladín",
        "subclass": "Cruzado",
        "min_level": 10,
        "cooldown": 3,
        "atk_buff_pct": 0.20,
        "duration": 3,
        "desc": "Cruzado: +20% ATK al equipo (raid) o a sí mismo (duelo) por 3 turnos."
    },

    # 🥷 Pícaro
    "golpe_sombras": {
        "id": "golpe_sombras",
        "name": "Golpe en las Sombras",
        "emoji": "🗡️",
        "class": "Pícaro",
        "subclass": "Asesino",
        "min_level": 10,
        "cooldown": 3,
        "damage_mult": 1.0,
        "damage_stat": "atk",
        "def_mitigation_factor": 0.30,
        "double_if_poisoned": True,
        "desc": "Asesino: Golpe doble si el objetivo ya está envenenado."
    },
    "paso_fantasma": {
        "id": "paso_fantasma",
        "name": "Paso Fantasma",
        "emoji": "👻",
        "class": "Pícaro",
        "subclass": "Sombra",
        "min_level": 10,
        "cooldown": 3,
        "guaranteed_dodge_next": True,
        "desc": "Sombra: Esquiva garantizada del próximo ataque."
    },
    "trampa_aconito": {
        "id": "trampa_aconito",
        "name": "Trampa de Acónito",
        "emoji": "🕸️",
        "class": "Pícaro",
        "subclass": "Trampero",
        "min_level": 10,
        "cooldown": 3,
        "damage_mult": 0.6,
        "damage_stat": "atk",
        "def_mitigation_factor": 0.35,
        "debuff_type": "weakness",
        "debuff_value": 0.20,
        "debuff_duration": 3,
        "desc": "Trampero: Daño leve + Debilidad (-20% ATK rival) 3 turnos."
    },

    # 🔮 Mago
    "llamarada": {
        "id": "llamarada",
        "name": "Llamarada",
        "emoji": "🔥",
        "class": "Mago",
        "subclass": "Piromante",
        "min_level": 10,
        "cooldown": 3,
        "damage_mult": 1.8,
        "damage_stat": "mag",
        "def_mitigation_factor": 0.20,
        "burn_duration": 4,
        "desc": "Piromante: Quemadura reforzada de 4 turnos."
    },
    "onda_escarcha": {
        "id": "onda_escarcha",
        "name": "Onda de Escarcha",
        "emoji": "❄️",
        "class": "Mago",
        "subclass": "Elementalista",
        "min_level": 10,
        "cooldown": 3,
        "damage_mult": 0.8,
        "damage_stat": "mag",
        "def_mitigation_factor": 0.25,
        "freeze_turns": 1,
        "desc": "Elementalista: Daño leve + congela al rival 1 turno."
    },
    "sobrecarga_arcana": {
        "id": "sobrecarga_arcana",
        "name": "Sobrecarga Arcana",
        "emoji": "💥",
        "class": "Mago",
        "subclass": "Arcanista",
        "min_level": 10,
        "cooldown": 3,
        "damage_mult": 2.5,
        "damage_stat": "mag",
        "def_mitigation_factor": 0.15,
        "self_damage_pct": 0.10,
        "desc": "Arcanista: Nuke (2.5×MAG) pero sufre 10% HP max como coste."
    },

    # ⚕️ Clérigo
    "luz_curativa": {
        "id": "luz_curativa",
        "name": "Luz Curativa",
        "emoji": "💚",
        "class": "Clérigo",
        "subclass": "Sanador",
        "min_level": 10,
        "cooldown": 3,
        "heal_pct_of_max_hp": 0.25,
        "desc": "Sanador: Cura 25% HP max a sí mismo (duelo) o al aliado con menor HP (raid)."
    },
    "pacto_sangre": {
        "id": "pacto_sangre",
        "name": "Pacto de Sangre",
        "emoji": "🖤",
        "class": "Clérigo",
        "subclass": "Oscuro",
        "min_level": 10,
        "cooldown": 3,
        "drain_pct": 0.20,
        "anti_heal_duration": 2,
        "desc": "Oscuro: Drena 20% HP actual + impide curación 2 turnos."
    },
    "bendicion_hierro": {
        "id": "bendicion_hierro",
        "name": "Bendición de Hierro",
        "emoji": "🛡️",
        "class": "Clérigo",
        "subclass": "Guardián de la Fe",
        "min_level": 10,
        "cooldown": 3,
        "shield_pct_of_max_hp": 0.18,
        "desc": "Guardián de la Fe: Escudo (18% HP max) a sí mismo (duelo) o a un aliado (raid)."
    },

    # ══════════════════════════════════════════════
    # HABILIDADES DE SUBCLASE — Nv.15 (Ultimates)
    # ══════════════════════════════════════════════

    # ⚔️ Guerrero
    "muralla_inquebrantable": {
        "id": "muralla_inquebrantable",
        "name": "Muralla Inquebrantable",
        "emoji": "🏰",
        "class": "Guerrero",
        "subclass": "Centinela",
        "min_level": 15,
        "cooldown": 6,
        "damage_reduction_pct": 0.50,
        "duration": 3,
        "desc": "Centinela ULT: -50% daño recibido por 3t (equipo en raid)."
    },
    "sed_sangre": {
        "id": "sed_sangre",
        "name": "Sed de Sangre",
        "emoji": "🩸",
        "class": "Guerrero",
        "subclass": "Berserker",
        "min_level": 15,
        "cooldown": 6,
        "hp_sacrifice_pct": 0.25,
        "atk_buff_pct": 0.60,
        "buff_duration": 3,
        "desc": "Berserker ULT: Sacrifica 25% HP → +60% ATK por 3 turnos."
    },
    "ejecucion": {
        "id": "ejecucion",
        "name": "Ejecución",
        "emoji": "⚔️",
        "class": "Guerrero",
        "subclass": "Duelista",
        "min_level": 15,
        "cooldown": 6,
        "damage_mult": 1.5,
        "damage_stat": "atk",
        "def_mitigation_factor": 0.25,
        "execute_threshold_pct": 0.30,
        "execute_bonus_mult": 2.0,
        "desc": "Duelista ULT: ×2.0 daño si objetivo <30% HP."
    },

    # ✝️ Paladín
    "aura_salvacion": {
        "id": "aura_salvacion",
        "name": "Aura de Salvación",
        "emoji": "💛",
        "class": "Paladín",
        "subclass": "Guardián Sagrado",
        "min_level": 15,
        "cooldown": 6,
        "shield_pct": 0.15,
        "hot_pct": 0.05,
        "duration": 3,
        "desc": "G. Sagrado ULT: Escudo + curación gradual para todo el equipo 3t."
    },
    "juicio_final": {
        "id": "juicio_final",
        "name": "Juicio Final",
        "emoji": "⚖️",
        "class": "Paladín",
        "subclass": "Vengador",
        "min_level": 15,
        "cooldown": 6,
        "reflect_pct": 1.50,
        "duration": 2,
        "desc": "Vengador ULT: Refleja 150% del daño recibido durante 2 turnos."
    },
    "carga_sagrada": {
        "id": "carga_sagrada",
        "name": "Carga Sagrada",
        "emoji": "⚔️",
        "class": "Paladín",
        "subclass": "Cruzado",
        "min_level": 15,
        "cooldown": 6,
        "damage_mult": 1.8,
        "damage_stat": "atk",
        "def_mitigation_factor": 0.25,
        "desc": "Cruzado ULT: Golpe extra fuera de turno para todo el equipo (raid) o ×1.8 ATK (duelo)."
    },

    # 🥷 Pícaro
    "ejecucion_sombria": {
        "id": "ejecucion_sombria",
        "name": "Ejecución Sombría",
        "emoji": "💀",
        "class": "Pícaro",
        "subclass": "Asesino",
        "min_level": 15,
        "cooldown": 6,
        "damage_mult": 2.5,
        "damage_stat": "atk",
        "def_mitigation_factor": 0.20,
        "desc": "Asesino ULT: Burst muy alto (2.5×ATK). Todo o nada."
    },
    "danza_cuchillas": {
        "id": "danza_cuchillas",
        "name": "Danza de Cuchillas",
        "emoji": "💃",
        "class": "Pícaro",
        "subclass": "Sombra",
        "min_level": 15,
        "cooldown": 6,
        "hits": 3,
        "damage_mult_per_hit": 0.7,
        "damage_stat": "atk",
        "def_mitigation_factor": 0.30,
        "evasion_buff_pct": 0.30,
        "evasion_buff_duration": 2,
        "desc": "Sombra ULT: 3 golpes (0.7×ATK) + evasión +30% por 2 turnos."
    },
    "enjambre_trampas": {
        "id": "enjambre_trampas",
        "name": "Enjambre de Trampas",
        "emoji": "🕸️",
        "class": "Pícaro",
        "subclass": "Trampero",
        "min_level": 15,
        "cooldown": 6,
        "damage_mult": 0.8,
        "damage_stat": "atk",
        "def_mitigation_factor": 0.30,
        "desc": "Trampero ULT: Aplica Debilidad, Fragilidad y Veneno de golpe."
    },

    # 🔮 Mago
    "cataclismo_fuego": {
        "id": "cataclismo_fuego",
        "name": "Cataclismo de Fuego",
        "emoji": "☄️",
        "class": "Mago",
        "subclass": "Piromante",
        "min_level": 15,
        "cooldown": 6,
        "damage_mult": 2.8,
        "damage_stat": "mag",
        "def_mitigation_factor": 0.15,
        "burn_duration": 5,
        "enhanced_burn_pct": 0.08,
        "desc": "Piromante ULT: Nuke (2.8×MAG) + quemadura 5t (8% HP max/t)."
    },
    "tormenta_elemental": {
        "id": "tormenta_elemental",
        "name": "Tormenta Elemental",
        "emoji": "🌪️",
        "class": "Mago",
        "subclass": "Elementalista",
        "min_level": 15,
        "cooldown": 6,
        "damage_mult": 1.5,
        "damage_stat": "mag",
        "def_mitigation_factor": 0.20,
        "burn_duration": 2,
        "freeze_turns": 1,
        "desc": "Elementalista ULT: Quemadura 2t + congelación 1t + golpe (1.5×MAG)."
    },
    "singularidad": {
        "id": "singularidad",
        "name": "Singularidad",
        "emoji": "🌌",
        "class": "Mago",
        "subclass": "Arcanista",
        "min_level": 15,
        "cooldown": 8,
        "damage_mult": 4.0,
        "damage_stat": "mag",
        "def_mitigation_factor": 0.10,
        "self_damage_pct": 0.15,
        "vulnerability_after_turns": 1,
        "vulnerability_pct": 0.30,
        "desc": "Arcanista ULT: El golpe más devastador (4.0×MAG). CD largo, auto-daño, vulnerable 1t."
    },

    # ⚕️ Clérigo
    "resurreccion_parcial": {
        "id": "resurreccion_parcial",
        "name": "Resurrección Parcial",
        "emoji": "✝️",
        "class": "Clérigo",
        "subclass": "Sanador",
        "min_level": 15,
        "cooldown": 8,
        "revive_hp_pct": 0.30,
        "self_heal_in_duel_pct": 0.40,
        "desc": "Sanador ULT: Revive aliado con 30% HP (raid). Auto-cura 40% HP (duelo)."
    },
    "consumir_alma": {
        "id": "consumir_alma",
        "name": "Consumir Alma",
        "emoji": "👁️",
        "class": "Clérigo",
        "subclass": "Oscuro",
        "min_level": 15,
        "cooldown": 6,
        "base_drain_pct": 0.15,
        "execute_threshold_pct": 0.30,
        "execute_drain_pct": 0.35,
        "desc": "Oscuro ULT: Drena 15% HP, o 35% si objetivo <30% HP."
    },
    "santuario": {
        "id": "santuario",
        "name": "Santuario",
        "emoji": "🏛️",
        "class": "Clérigo",
        "subclass": "Guardián de la Fe",
        "min_level": 15,
        "cooldown": 6,
        "shield_pct": 0.15,
        "cleanse_all_debuffs": True,
        "desc": "G. de la Fe ULT: Escudo grupal + limpia todos los debuffs (raid)."
    },
}
