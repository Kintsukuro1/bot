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
    }
}
