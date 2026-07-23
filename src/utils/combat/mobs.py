"""
Módulo de Enemigos Normales y Élite para el Modo Aventura y Dungeons.
Define el catálogo de 80 mobs únicos distribuidos en los 10 Capítulos de la Trama,
sus arquetipos, habilidades especiales, stats y afijos.
"""

from __future__ import annotations
import random
from typing import Optional, Dict, Any, List, Tuple

# Afijos especiales para mobs élite
MOB_AFFIXES: Dict[str, Dict[str, Any]] = {
    "igneo": {
        "name": "Ígneo 🔥",
        "desc": "Devuelve 10% del daño recibido como Quemadura."
    },
    "bastion": {
        "name": "Bastión 🛡️",
        "desc": "Inicia con un Escudo de absorción del 25% de su HP."
    },
    "frenetico": {
        "name": "Frenético ⚡",
        "desc": "Gana +40% ATK cuando su HP cae por debajo del 30%."
    },
    "venenoso": {
        "name": "Venenoso 🧪",
        "desc": "Sus ataques asestan veneno (10 HP/t) por 2 turnos."
    },
    "vampirico": {
        "name": "Vampírico 🧛",
        "desc": "Se cura un 20% del daño infligido en cada ataque."
    }
}

# Catálogo completo de 8 Mobs por Capítulo (80 Mobs totales)
CHAPTER_MOBS_CATALOG: Dict[int, List[Dict[str, Any]]] = {
    # ── CAPÍTULO 1: El Incendio del Valle (Nv. 1-10) ──
    1: [
        {"name": "Goblin Silvestre", "emoji": "👺", "archetype": "guerrero", "base_hp": 70, "base_atk": 12, "base_def": 4, "skill": "Puñalada Rápida"},
        {"name": "Lobo de las Sombras", "emoji": "🐺", "archetype": "asesino", "base_hp": 55, "base_atk": 15, "base_def": 2, "skill": "Mordisco Sangriento"},
        {"name": "Bandido del Bosque", "emoji": "🗡️", "archetype": "guerrero", "base_hp": 80, "base_atk": 11, "base_def": 5, "skill": "Golpe Bajo"},
        {"name": "Chamán Goblin", "emoji": "🔮", "archetype": "mago", "base_hp": 50, "base_atk": 14, "base_def": 3, "skill": "Orbe de Fuego"},
        {"name": "Bruto Garrote", "emoji": "🧌", "archetype": "tanque", "base_hp": 110, "base_atk": 9, "base_def": 8, "skill": "Garrotazo Aplastante"},
        {"name": "Osabúho Feroz", "emoji": "🦉", "archetype": "guerrero", "base_hp": 95, "base_atk": 16, "base_def": 6, "skill": "Garras Desgarradoras"},
        {"name": "Silvano Corrupto", "emoji": "🌲", "archetype": "soporte", "base_hp": 85, "base_atk": 10, "base_def": 7, "skill": "Raíces Curativas"},
        {"name": "Asaltante de Caminos", "emoji": "🏹", "archetype": "asesino", "base_hp": 65, "base_atk": 17, "base_def": 3, "skill": "Flecha Envenenada"},
    ],
    # ── CAPÍTULO 2: Las Criptas del Juramento (Nv. 11-20) ──
    2: [
        {"name": "Esqueleto Guardián", "emoji": "💀", "archetype": "guerrero", "base_hp": 150, "base_atk": 24, "base_def": 10, "skill": "Tajo de Hueso"},
        {"name": "Espectro Hambriento", "emoji": "👻", "archetype": "asesino", "base_hp": 120, "base_atk": 30, "base_def": 6, "skill": "Lamento Gélido"},
        {"name": "Ghoul de las Ruinas", "emoji": "🧟", "archetype": "tanque", "base_hp": 220, "base_atk": 18, "base_def": 14, "skill": "Mordida Infectada"},
        {"name": "Cultista del Abismo", "emoji": "🔮", "archetype": "mago", "base_hp": 110, "base_atk": 32, "base_def": 7, "skill": "Rayo de Sombras"},
        {"name": "Sacerdote Necrótico", "emoji": "⚕️", "archetype": "soporte", "base_hp": 130, "base_atk": 20, "base_def": 9, "skill": "Reanimación Oscura"},
        {"name": "Gárgola de Tumba", "emoji": "🗿", "archetype": "tanque", "base_hp": 240, "base_atk": 22, "base_def": 18, "skill": "Piel de Granito"},
        {"name": "Esqueleto Arquero", "emoji": "🏹", "archetype": "asesino", "base_hp": 115, "base_atk": 34, "base_def": 5, "skill": "Disparo Perforante"},
        {"name": "Sombra Rencorosa", "emoji": "👤", "archetype": "mago", "base_hp": 105, "base_atk": 35, "base_def": 6, "skill": "Toque de la Muerte"},
    ],
    # ── CAPÍTULO 3: Furia de las Tierras Ígneas (Nv. 21-30) ──
    3: [
        {"name": "Elemental de Magma", "emoji": "🔥", "archetype": "mago", "base_hp": 320, "base_atk": 44, "base_def": 18, "skill": "Explosión Volcánica"},
        {"name": "Salamandra de Fuego", "emoji": "🦎", "archetype": "asesino", "base_hp": 260, "base_atk": 52, "base_def": 12, "skill": "Aliento de Ceniza"},
        {"name": "Enano Forjador Renegado", "emoji": "🔨", "archetype": "guerrero", "base_hp": 380, "base_atk": 38, "base_def": 22, "skill": "Martillazo de Forja"},
        {"name": "Basilisco de Piedra", "emoji": "🐍", "archetype": "tanque", "base_hp": 450, "base_atk": 30, "base_def": 30, "skill": "Mirada Petrificante"},
        {"name": "Imán del Caos", "emoji": "💥", "archetype": "mago", "base_hp": 280, "base_atk": 48, "base_def": 15, "skill": "Onda Expansiva"},
        {"name": "Draconiano Furia", "emoji": "🐲", "archetype": "guerrero", "base_hp": 360, "base_atk": 42, "base_def": 20, "skill": "Garra Ígnea"},
        {"name": "Perro de Caza Ígneo", "emoji": "🐕", "archetype": "asesino", "base_hp": 270, "base_atk": 50, "base_def": 14, "skill": "Dentellada Ardiente"},
        {"name": "Demonio de Ceniza", "emoji": "👿", "archetype": "mago", "base_hp": 300, "base_atk": 46, "base_def": 16, "skill": "Lluvia de Ascuas"},
    ],
    # ── CAPÍTULO 4: El Glaciar de los Lamentos (Nv. 31-40) ──
    4: [
        {"name": "Gólem Glacial", "emoji": "🧊", "archetype": "tanque", "base_hp": 700, "base_atk": 55, "base_def": 45, "skill": "Puño de Escarcha"},
        {"name": "Lobo de Nieves", "emoji": "🐺", "archetype": "asesino", "base_hp": 520, "base_atk": 78, "base_def": 22, "skill": "Colmillo Congelante"},
        {"name": "Sombra de Escarcha", "emoji": "❄️", "archetype": "mago", "base_hp": 480, "base_atk": 82, "base_def": 20, "skill": "Ventisca Helada"},
        {"name": "Wendigo Hambriento", "emoji": "👹", "archetype": "guerrero", "base_hp": 650, "base_atk": 70, "base_def": 28, "skill": "Frenesí Hambriento"},
        {"name": "Sacerdote del Frío", "emoji": "⚕️", "archetype": "soporte", "base_hp": 500, "base_atk": 60, "base_def": 25, "skill": "Aura Glacial"},
        {"name": "Yeti de las Nieves", "emoji": "🦍", "archetype": "tanque", "base_hp": 750, "base_atk": 62, "base_def": 40, "skill": "Pisotón Nival"},
        {"name": "Oso Glacial", "emoji": "🐻", "archetype": "guerrero", "base_hp": 680, "base_atk": 68, "base_def": 32, "skill": "Zarpazo Ártico"},
        {"name": "Guardián de Hielo", "emoji": "🛡️", "archetype": "tanque", "base_hp": 720, "base_atk": 58, "base_def": 48, "skill": "Escudo de Cristales"},
    ],
    # ── CAPÍTULO 5: Fortaleza de la Tempestad (Nv. 41-50) ──
    5: [
        {"name": "Caballero de las Tormentas", "emoji": "⚡", "archetype": "guerrero", "base_hp": 1100, "base_atk": 110, "base_def": 50, "skill": "Estocada Eléctrica"},
        {"name": "Gárgola de Rayos", "emoji": "🗿", "archetype": "tanque", "base_hp": 1400, "base_atk": 90, "base_def": 65, "skill": "Rayo Fulminante"},
        {"name": "Arcanista Inestable", "emoji": "🔮", "archetype": "mago", "base_hp": 850, "base_atk": 135, "base_def": 35, "skill": "Descarga Torrencial"},
        {"name": "Wyvern Celaje", "emoji": "🐉", "archetype": "asesino", "base_hp": 950, "base_atk": 125, "base_def": 40, "skill": "Aletazo de Tempestad"},
        {"name": "Elemental de Trueno", "emoji": "🌩️", "archetype": "mago", "base_hp": 900, "base_atk": 130, "base_def": 38, "skill": "Chispa Voltáica"},
        {"name": "Valkiria Caída", "emoji": "🪽", "archetype": "asesino", "base_hp": 920, "base_atk": 128, "base_def": 42, "skill": "Lanza Veloz"},
        {"name": "Guardián del Viento", "emoji": "🌪️", "archetype": "tanque", "base_hp": 1300, "base_atk": 95, "base_def": 60, "skill": "Tornado Defensivo"},
        {"name": "Rayo Viviente", "emoji": "💥", "archetype": "mago", "base_hp": 820, "base_atk": 140, "base_def": 30, "skill": "Sobrecarga de Trueno"},
    ],
    # ── CAPÍTULO 6: Ciudadela de las Sombras (Nv. 51-60) ──
    6: [
        {"name": "Caballero del Abismo", "emoji": "⚔️", "archetype": "guerrero", "base_hp": 1800, "base_atk": 160, "base_def": 75, "skill": "Corte de Tinieblas"},
        {"name": "Demonio Sombrío", "emoji": "👿", "archetype": "asesino", "base_hp": 1500, "base_atk": 185, "base_def": 55, "skill": "Garras Umbrías"},
        {"name": "Súcubo de Sangre", "emoji": "🩸", "archetype": "mago", "base_hp": 1400, "base_atk": 190, "base_def": 50, "skill": "Sedducción Mortal"},
        {"name": "Perro del Infierno", "emoji": "🐕‍🦺", "archetype": "guerrero", "base_hp": 1650, "base_atk": 170, "base_def": 60, "skill": "Fuego Infernal"},
        {"name": "Inquisidor Oscuro", "emoji": "✝️", "archetype": "soporte", "base_hp": 1700, "base_atk": 150, "base_def": 70, "skill": "Maldición de Fe"},
        {"name": "Ejecutor Abisal", "emoji": "🪓", "archetype": "guerrero", "base_hp": 1850, "base_atk": 175, "base_def": 72, "skill": "Hachazo Letal"},
        {"name": "Sombra de Guerra", "emoji": "👤", "archetype": "asesino", "base_hp": 1450, "base_atk": 195, "base_def": 52, "skill": "Paso Espectral"},
        {"name": "Beholder Menor", "emoji": "👁️", "archetype": "mago", "base_hp": 1380, "base_atk": 198, "base_def": 48, "skill": "Rayo Desintegrador"},
    ],
    # ── CAPÍTULO 7: Las Arenas del Olvido (Nv. 61-70) ──
    7: [
        {"name": "Momia Estelar", "emoji": "🏺", "archetype": "tanque", "base_hp": 2600, "base_atk": 210, "base_def": 110, "skill": "Vendaje Asfixiante"},
        {"name": "Escorpión Gigante", "emoji": "🦂", "archetype": "asesino", "base_hp": 2200, "base_atk": 250, "base_def": 85, "skill": "Aguijón Mortal"},
        {"name": "Djinn Arenoso", "emoji": "🧞", "archetype": "mago", "base_hp": 2000, "base_atk": 265, "base_def": 80, "skill": "Ráfaga de Dunas"},
        {"name": "Guardián de la Tumba", "emoji": "🛡️", "archetype": "guerrero", "base_hp": 2800, "base_atk": 220, "base_def": 120, "skill": "Muro del Faraón"},
        {"name": "Asesino del Desierto", "emoji": "🥷", "archetype": "asesino", "base_hp": 2100, "base_atk": 260, "base_def": 90, "skill": "Cimitarra Danzante"},
        {"name": "Devorador de Dunas", "emoji": "🐛", "archetype": "tanque", "base_hp": 2900, "base_atk": 205, "base_def": 125, "skill": "Sumergimiento"},
        {"name": "Serpiente Solar", "emoji": "🐍", "archetype": "mago", "base_hp": 2050, "base_atk": 270, "base_def": 78, "skill": "Destello Solar"},
        {"name": "Estatua Anubis", "emoji": "🐕", "archetype": "guerrero", "base_hp": 2750, "base_atk": 225, "base_def": 115, "skill": "Juicio de la Balanza"},
    ],
    # ── CAPÍTULO 8: Las Profundidades Abisales (Nv. 71-80) ──
    8: [
        {"name": "Sirenio Maldito", "emoji": "🧜", "archetype": "mago", "base_hp": 3200, "base_atk": 320, "base_def": 120, "skill": "Canto Voraz"},
        {"name": "Kraken Joven", "emoji": "🐙", "archetype": "tanque", "base_hp": 4200, "base_atk": 280, "base_def": 160, "skill": "Tentáculo Aplastante"},
        {"name": "Tiburón del Abismo", "emoji": "🦈", "archetype": "asesino", "base_hp": 3000, "base_atk": 360, "base_def": 110, "skill": "Frenesí de Sangre"},
        {"name": "Bruja Marina", "emoji": "🧙‍♀️", "archetype": "soporte", "base_hp": 3100, "base_atk": 310, "base_def": 130, "skill": "Maremoto Sombrío"},
        {"name": "Tritón de Acero", "emoji": "🔱", "archetype": "guerrero", "base_hp": 3600, "base_atk": 330, "base_def": 145, "skill": "Tridentazo Barredor"},
        {"name": "Anguila Eléctrica", "emoji": "🐍", "archetype": "mago", "base_hp": 2950, "base_atk": 370, "base_def": 105, "skill": "Voltaje Abisal"},
        {"name": "Devorador Coralino", "emoji": "🦀", "archetype": "tanque", "base_hp": 4350, "base_atk": 270, "base_def": 170, "skill": "Caparazón de Arrecife"},
        {"name": "Leviatán Menor", "emoji": "🐋", "archetype": "guerrero", "base_hp": 3800, "base_atk": 340, "base_def": 150, "skill": "Tsunami Submarino"},
    ],
    # ── CAPÍTULO 9: La Falla Etérea (Nv. 81-90) ──
    9: [
        {"name": "Cazador Astral", "emoji": "🌌", "archetype": "asesino", "base_hp": 4500, "base_atk": 460, "base_def": 160, "skill": "Disparo Dimensional"},
        {"name": "Elemental del Vacío", "emoji": "🌀", "archetype": "mago", "base_hp": 4200, "base_atk": 490, "base_def": 150, "skill": "Implosión Cósmica"},
        {"name": "Horror Dimensional", "emoji": "👁️", "archetype": "tanque", "base_hp": 5800, "base_atk": 410, "base_def": 220, "skill": "Mirada del Vacío"},
        {"name": "Guardián Estelar", "emoji": "⭐", "archetype": "guerrero", "base_hp": 5000, "base_atk": 440, "base_def": 190, "skill": "Filo Celestre"},
        {"name": "Fantasma Etéreo", "emoji": "👻", "archetype": "soporte", "base_hp": 4300, "base_atk": 420, "base_def": 170, "skill": "Desplazamiento Temporal"},
        {"name": "Caminante del Éter", "emoji": "🚶", "archetype": "asesino", "base_hp": 4400, "base_atk": 470, "base_def": 155, "skill": "Zancada Estelar"},
        {"name": "Espectro del Tiempo", "emoji": "⏳", "archetype": "mago", "base_hp": 4150, "base_atk": 500, "base_def": 145, "skill": "Distorsión de Turno"},
        {"name": "Entidad Oscura", "emoji": "🕳️", "archetype": "tanque", "base_hp": 6000, "base_atk": 400, "base_def": 230, "skill": "Gravedad Cero"},
    ],
    # ── CAPÍTULO 10: El Juicio del Dios Dragón (Nv. 91-100) ──
    10: [
        {"name": "Guardián Celestial", "emoji": "👼", "archetype": "tanque", "base_hp": 8000, "base_atk": 600, "base_def": 300, "skill": "Baluarte Divino"},
        {"name": "Dragón de Élite", "emoji": "🐉", "archetype": "guerrero", "base_hp": 7500, "base_atk": 680, "base_def": 260, "skill": "Aliento Apocalíptico"},
        {"name": "Campeón de la Luz Caída", "emoji": "⚔️", "archetype": "asesino", "base_hp": 6500, "base_atk": 740, "base_def": 220, "skill": "Sentencia Sagrada"},
        {"name": "Esbirro de Bahamut", "emoji": "🔥", "archetype": "mago", "base_hp": 6200, "base_atk": 760, "base_def": 200, "skill": "Llama Dracónica"},
        {"name": "Avatar de la Ruina", "emoji": "👑", "archetype": "soporte", "base_hp": 7000, "base_atk": 650, "base_def": 250, "skill": "Aura de Perdición"},
        {"name": "Dragón de Sombras", "emoji": "🐉", "archetype": "asesino", "base_hp": 6700, "base_atk": 730, "base_def": 230, "skill": "Garras Nocturnas"},
        {"name": "Arcángel Profanado", "emoji": "🗡️", "archetype": "guerrero", "base_hp": 7600, "base_atk": 670, "base_def": 270, "skill": "Espada de la Caída"},
        {"name": "Wyrm Ancestral", "emoji": "🐲", "archetype": "tanque", "base_hp": 8500, "base_atk": 580, "base_def": 320, "skill": "Escamas Impenetrables"},
    ]
}


class Mob:
    """Instancia de un enemigo normal o élite en combate."""

    def __init__(self, name: str, emoji: str, archetype: str, level: int,
                 hp: int, atk: int, def_stat: int, skill: str = "Ataque Normal",
                 is_elite: bool = False, affix: Optional[str] = None):
        self.name = name
        self.emoji = emoji
        self.archetype = archetype
        self.level = level
        self.skill = skill
        
        mult = 1.35 if is_elite else 1.0
        self.max_hp = int(hp * mult)
        self.hp = self.max_hp
        self.atk = int(atk * mult)
        self.def_stat = int(def_stat * mult)
        self.is_elite = is_elite
        self.affix = affix
        
        # Escudo de bastión si aplica
        self.shield = int(self.max_hp * 0.25) if affix == "bastion" else 0
        self.is_frenzied = False

    def take_damage(self, raw_damage: int, is_magic: bool = False) -> Tuple[int, Optional[str]]:
        """Aplica daño al mob considerando su DEF y Escudo. Retorna (daño_efectivo, log_evento)."""
        def_factor = 0.20 if is_magic else 0.35
        mitigated = max(1, raw_damage - int(self.def_stat * def_factor))
        
        # Absorción por escudo
        if self.shield > 0:
            if self.shield >= mitigated:
                self.shield -= mitigated
                actual_hp_dmg = 0
            else:
                actual_hp_dmg = mitigated - self.shield
                self.shield = 0
        else:
            actual_hp_dmg = mitigated

        self.hp = max(0, self.hp - actual_hp_dmg)
        
        event_log = None
        # Efecto Ígneo
        if self.affix == "igneo" and actual_hp_dmg > 0:
            reflect_burn = max(1, int(actual_hp_dmg * 0.10))
            event_log = f"🔥 **[Afijo Ígneo]** ¡{self.emoji} {self.name} refleja **{reflect_burn}** de daño en quemadura!"

        # Efecto Frenético
        if self.affix == "frenetico" and not self.is_frenzied and (self.hp / self.max_hp) <= 0.30:
            self.is_frenzied = True
            self.atk = int(self.atk * 1.40)
            event_log = f"⚡ **[Afijo Frenético]** ¡{self.emoji} {self.name} entra en rabia (+40% ATK)!"

        return mitigated, event_log

    def perform_action(self, target_combatant) -> str:
        """Ejecuta el turno del mob contra un jugador según su arquetipo y su habilidad única."""
        base_dmg = max(1, self.atk - target_combatant.def_stat)
        use_special = random.random() < 0.30  # 30% probabilidad de usar habilidad única

        # Acción por Vampírico
        lifesteal_log = ""

        if use_special:
            dmg = int(base_dmg * 1.35)
            target_combatant.hp = max(0, target_combatant.hp - dmg)
            log = f"✨ {self.emoji} **{self.name}** usa su habilidad **[{self.skill}]** asestando **{dmg}** daño a {target_combatant.user.display_name}."
        else:
            if self.archetype == "asesino":
                is_crit = random.random() < 0.30
                dmg = int(base_dmg * 1.5) if is_crit else base_dmg
                target_combatant.hp = max(0, target_combatant.hp - dmg)
                crit_text = " **¡GOLPE CRÍTICO!**" if is_crit else ""
                log = f"⚔️ {self.emoji} **{self.name}** usó *Ataque Furtivo*{crit_text} infligiendo **{dmg}** daño."
            elif self.archetype == "mago":
                dmg = max(1, int(self.atk * 1.2) - int(target_combatant.def_stat * 0.2))
                target_combatant.hp = max(0, target_combatant.hp - dmg)
                log = f"🔮 {self.emoji} **{self.name}** lanzó *Descarga Arcana* infligiendo **{dmg}** daño mágico."
            elif self.archetype == "tanque":
                dmg = max(1, int(base_dmg * 0.8))
                target_combatant.hp = max(0, target_combatant.hp - dmg)
                self.shield += int(self.max_hp * 0.05)
                log = f"🛡️ {self.emoji} **{self.name}** embiste provocando **{dmg}** daño y ganando escudo."
            elif self.archetype == "soporte":
                heal_amt = int(self.max_hp * 0.15)
                self.hp = min(self.max_hp, self.hp + heal_amt)
                log = f"✨ {self.emoji} **{self.name}** canaliza *Luz Sombría* y se cura **{heal_amt}** HP."
            else:
                dmg = base_dmg
                target_combatant.hp = max(0, target_combatant.hp - dmg)
                log = f"⚔️ {self.emoji} **{self.name}** ataca infligiendo **{dmg}** daño físico."

        # Procesar Afijo Vampírico si aplica
        if self.affix == "vampirico" and 'dmg' in locals() and dmg > 0:
            vamp_heal = max(1, int(dmg * 0.20))
            self.hp = min(self.max_hp, self.hp + vamp_heal)
            log += f" 🧛 (Drena +{vamp_heal} HP)"

        # Procesar Afijo Venenoso
        if self.affix == "venenoso":
            target_combatant.poison_turns = 2
            target_combatant.poison_damage = 10
            log += " 🧪 (Aplica Veneno)"

        return log


def generate_mob(chapter_id: int, round_num: int = 1, is_elite: bool = False, mob_key: Optional[str] = None) -> Mob:
    """Genera una instancia de Mob balanceada según el Capítulo y la ronda actual."""
    mobs_pool = CHAPTER_MOBS_CATALOG.get(chapter_id, CHAPTER_MOBS_CATALOG[1])
    
    if mob_key:
        mob_data = next((m for m in mobs_pool if m["name"] == mob_key), random.choice(mobs_pool))
    else:
        mob_data = random.choice(mobs_pool)

    # Multiplicador de escala por ronda dentro del capítulo
    round_mult = 1.0 + ((round_num - 1) * 0.12)
    
    hp = int(mob_data["base_hp"] * round_mult)
    atk = int(mob_data["base_atk"] * round_mult)
    def_stat = int(mob_data["base_def"] * round_mult)
    skill = mob_data.get("skill", "Ataque Especial")
    
    affix = None
    if is_elite:
        affix = random.choice(list(MOB_AFFIXES.keys()))

    name_prefix = "⭐ Élite " if is_elite else ""
    return Mob(
        name=f"{name_prefix}{mob_data['name']}",
        emoji=mob_data["emoji"],
        archetype=mob_data["archetype"],
        level=chapter_id * 10,
        hp=hp,
        atk=atk,
        def_stat=def_stat,
        skill=skill,
        is_elite=is_elite,
        affix=affix
    )
