"""
Motor de Nodos Narrativos y Configuración de los 10 Capítulos de Aventura.
Gestiona el avance por nodos (Combate, Eventos Narrativos, Campamentos, Mercaderes y Bosses).
"""

from __future__ import annotations
import random
from typing import Dict, Any, List, Optional, Tuple

CHAPTERS_CONFIG: Dict[int, Dict[str, Any]] = {
    1: {
        "title": "Capítulo 1: El Incendio del Valle",
        "map_key": "bosque",
        "level_req": 1,
        "color_code": 0x2ECC71,  # Verde
        "desc": "El Poblado Comunitario sufre una emboscada de goblins y bandidos. Debes abrirte paso y rescatar al herrero.",
        "npc_rescue": {
            "name": "Herrero Garrek",
            "emoji": "🔨",
            "building": "Herrería de Combate",
            "dialogue": "¡Por la barba de mis ancestros, gracias viajero! Si me llevas al Poblado, abriré la **Herrería de Combate** para afilar tus armas."
        },
        "dungeon_unlock": {
            "name": "🏰 La Mina Abandonada",
            "boss": "Kragh el Minero Maldito",
            "desc": "Mazmorra narrativa desbloqueada tras completar el Capítulo 1."
        },
        "boss": {
            "name": "Kragh el Minero Maldito",
            "emoji": "🧌",
            "hp": 380,
            "atk": 32,
            "def_stat": 12,
            "reward_bronze": 350
        }
    },
    2: {
        "title": "Capítulo 2: Las Criptas del Juramento",
        "map_key": "cripta",
        "level_req": 11,
        "color_code": 0x7F8C8D,  # Gris oscuro
        "desc": "Sigue el rastro del culto oscuro bajo las ruinas catacumbales para recuperar manuscritos perdidos.",
        "npc_rescue": {
            "name": "Erudita Maelis",
            "emoji": "📚",
            "building": "Gran Biblioteca Arcana",
            "dialogue": "¡Pensé que mis conocimientos morirían en estas criptas! En el Poblado construiré la **Gran Biblioteca Arcana**."
        },
        "dungeon_unlock": {
            "name": "🪦 Catacumbas del Rey Descompuesto",
            "boss": "Rey Osario Malakar",
            "desc": "Mazmorra de la Cripta de la Trama."
        },
        "boss": {
            "name": "Rey Osario Malakar",
            "emoji": "💀",
            "hp": 750,
            "atk": 55,
            "def_stat": 22,
            "reward_bronze": 750
        }
    },
    3: {
        "title": "Capítulo 3: La Furia de las Tierras Ígneas",
        "map_key": "volcan",
        "level_req": 21,
        "color_code": 0xE67E22,  # Naranja
        "desc": "La tierra retumba con la ira del magma. Salva al gran comerciante atrapado en las laderas ardientes.",
        "npc_rescue": {
            "name": "Mercader Valerio",
            "emoji": "🏬",
            "building": "Gran Mercado del Servidor",
            "dialogue": "¡El fuego casi consume mis registros! Te recompensaré instalando el **Gran Mercado** en el Poblado."
        },
        "dungeon_unlock": {
            "name": "🌋 El Corazón de Magma",
            "boss": "Ígnis el Devorador de Cenizas",
            "desc": "Mazmorra volcánica de alto riesgo."
        },
        "boss": {
            "name": "Ígnis el Devorador de Cenizas",
            "emoji": "🔥",
            "hp": 1400,
            "atk": 95,
            "def_stat": 35,
            "reward_bronze": 1400
        }
    },
    4: {
        "title": "Capítulo 4: El Glaciar de los Lamentos",
        "map_key": "abismo",
        "level_req": 31,
        "color_code": 0x3498DB,  # Azul
        "desc": "Adéntrate en los picos eternos donde los antiguos sacerdotes resguardaban la luz sagrada.",
        "npc_rescue": {
            "name": "Sacerdotisa Elenora",
            "emoji": "⛪",
            "building": "Templo del Alba",
            "dialogue": "La helada no pudo apagar la fe. En el Poblado erigiré el **Templo del Alba** para bendecir a tus mascotas."
        },
        "dungeon_unlock": {
            "name": "🧊 Espelunca de Cristal Glacial",
            "boss": "Soberana Wyrm Frostfang",
            "desc": "Mazmorra de hielo y cristal."
        },
        "boss": {
            "name": "Soberana Wyrm Frostfang",
            "emoji": "❄️",
            "hp": 2300,
            "atk": 140,
            "def_stat": 50,
            "reward_bronze": 2200
        }
    },
    5: {
        "title": "Capítulo 5: La Fortaleza de la Tempestad",
        "map_key": "ciudadela",
        "level_req": 41,
        "color_code": 0x9B59B6,  # Morado
        "desc": "Rompe el cerco de la legión abisal en las cumbres tempestuosas y rescata al comandante defensivo.",
        "npc_rescue": {
            "name": "Comandante Vane",
            "emoji": "🏰",
            "building": "Bastión de Raids",
            "dialogue": "¡Bien luchado! Con mi experiencia militar, reforzaré el **Bastión de Raids** de tu servidor."
        },
        "dungeon_unlock": {
            "name": "⚡ La Espira de la Tempestad",
            "boss": "Archimago Abisal Xathos",
            "desc": "Mazmorra de la tempestad suprema."
        },
        "boss": {
            "name": "Archimago Abisal Xathos",
            "emoji": "🌩️",
            "hp": 3800,
            "atk": 210,
            "def_stat": 70,
            "reward_bronze": 3500
        }
    },
    6: {
        "title": "Capítulo 6: La Ciudadela de las Sombras",
        "map_key": "sombras",
        "level_req": 51,
        "color_code": 0x34495E,  # Gris morado oscuro
        "desc": "Penetra en el corazón del imperio oscuro y libera al viejo tabernero que conoce las rutas secretas.",
        "npc_rescue": {
            "name": "Tabernero Barnaby",
            "emoji": "🍺",
            "building": "Taberna del Aventurero",
            "dialogue": "¡Salud, héroe! Abriré la **Taberna del Aventurero** para que todo el servidor festeje y tome brebajes dobles."
        },
        "dungeon_unlock": {
            "name": "🏰 Fortaleza del Caos",
            "boss": "General Vor'ghul",
            "desc": "Mazmorra del bastión oscuro."
        },
        "boss": {
            "name": "General Vor'ghul",
            "emoji": "👿",
            "hp": 5500,
            "atk": 290,
            "def_stat": 90,
            "reward_bronze": 5000
        }
    },
    7: {
        "title": "Capítulo 7: Las Arenas del Olvido",
        "map_key": "desierto",
        "level_req": 61,
        "color_code": 0xF1C40F,  # Amarillo dorado
        "desc": "Cruza las dunas infinitas en busca de la alquimia perdida de los reyes estelares.",
        "npc_rescue": {
            "name": "Alquimista Zhur",
            "emoji": "🔮",
            "building": "Laboratorio de Alquimia",
            "dialogue": "Las arenas no pudieron sepultar mis secretos. Te enseñaré a transmutar elixires legendarios."
        },
        "dungeon_unlock": {
            "name": "🏜️ Tumba del Faraón Estelar",
            "boss": "Rah'Kesh el Inmortal",
            "desc": "Mazmorra ancestral del desierto."
        },
        "boss": {
            "name": "Rah'Kesh el Inmortal",
            "emoji": "🏺",
            "hp": 7800,
            "atk": 380,
            "def_stat": 120,
            "reward_bronze": 7500
        }
    },
    8: {
        "title": "Capítulo 8: Las Profundidades Abisales",
        "map_key": "oceano",
        "level_req": 71,
        "color_code": 0x1ABC9C,  # Turquesa oscuro
        "desc": "Desciende a la trinchera marina donde duermen las criaturas del lecho oceánico.",
        "npc_rescue": {
            "name": "Capitán Drake",
            "emoji": "⚓",
            "building": "Puerto Mercante",
            "dialogue": "¡Ahoy, camarada! Con mi navío abriremos las rutas comerciales del mar profundo."
        },
        "dungeon_unlock": {
            "name": "🌊 Trinchera de Leviatán",
            "boss": "Devorador del Mar Profundo",
            "desc": "Mazmorra de las profundidades."
        },
        "boss": {
            "name": "Devorador del Mar Profundo",
            "emoji": "🐙",
            "hp": 11000,
            "atk": 490,
            "def_stat": 160,
            "reward_bronze": 10000
        }
    },
    9: {
        "title": "Capítulo 9: La Falla Etérea",
        "map_key": "astral",
        "level_req": 81,
        "color_code": 0x8E44AD,  # Morado místico
        "desc": "El tejido de la realidad se desgarra. Explora la dimensión astral antes del colapso.",
        "npc_rescue": {
            "name": "Cronista Aethel",
            "emoji": "🌀",
            "building": "Observatorio Astral",
            "dialogue": "He contemplado las estrellas y el tiempo. En el Observatorio revelaré los presagios del reino."
        },
        "dungeon_unlock": {
            "name": "🌌 Santuario de las Estrellas",
            "boss": "Titán del Vacío Kronos",
            "desc": "Mazmorra del continuo etéreo."
        },
        "boss": {
            "name": "Titán del Vacío Kronos",
            "emoji": "👁️",
            "hp": 16000,
            "atk": 620,
            "def_stat": 210,
            "reward_bronze": 15000
        }
    },
    10: {
        "title": "Capítulo 10: El Juicio del Dios Dragón",
        "map_key": "celestial",
        "level_req": 91,
        "color_code": 0xD35400,  # Rojo dorado celestial
        "desc": "El enfrentamiento final en el Trono Celestial. Detén al Dios Dragón y salva el mundo.",
        "npc_rescue": {
            "name": "Rey de la Resistencia",
            "emoji": "👑",
            "building": "Palacio Real",
            "dialogue": "¡Has salvado a todo el reino! Serás coronado Gran Campeón del Servidor."
        },
        "dungeon_unlock": {
            "name": "🐉 Trono Celestial del Abismo",
            "boss": "Bahamut el Destruidor del Mundo",
            "desc": "Mazmorra End-Game Suprema."
        },
        "boss": {
            "name": "Bahamut el Destruidor del Mundo",
            "emoji": "🐉",
            "hp": 25000,
            "atk": 850,
            "def_stat": 300,
            "reward_bronze": 25000
        }
    }
}

# Eventos narrativos de ejemplo para nodos de opción
NARRATIVE_EVENTS = [
    {
        "title": "📜 La Altar de Runas Antiguas",
        "desc": "Encuentras un altar de piedra grabado con runas brillantes. La energía emana de él.",
        "options": [
            {
                "label": "🔵 Meditar en la runa",
                "effect_type": "resource",
                "val": 50,
                "msg": "Meditas pacíficamente. Ganas **+50 de Recurso de Clase** y te sientes renovado."
            },
            {
                "label": "🟢 Ofrecer gotas de sangre",
                "effect_type": "buff_atk",
                "val": 0.20,
                "msg": "Sufres 10% auto-daño, pero las runas brillan intensamente. **+20% ATK** por el resto de la aventura."
            },
            {
                "label": "🟡 Extraer cristales del altar",
                "effect_type": "materials",
                "val": 25,
                "msg": "Extraes materiales valiosos. Ganas **+25 Cristales de Sombras** para el Poblado."
            }
        ]
    },
    {
        "title": "🏕️ El Refugio del Viajero Abandonado",
        "desc": "Descubres las ruinas de un viejo campamento con suministros bien conservados.",
        "options": [
            {
                "label": "💚 Beber el elixir de salud",
                "effect_type": "heal",
                "val": 0.35,
                "msg": "Recuperas **+35% de tu HP máximo**."
            },
            {
                "label": "🪵 Recoger suministros de madera",
                "effect_type": "materials_wood",
                "val": 30,
                "msg": "Recoges **+30 Madera Ancestral** para el Poblado de tu servidor."
            }
        ]
    }
]

class AdventureNode:
    """Representa un nodo individual en la ruta de 10 rondas de la aventura."""

    def __init__(self, node_index: int, node_type: str, title: str, description: str, emoji: str):
        self.node_index = node_index
        self.node_type = node_type  # 'combat', 'event', 'camp', 'boss'
        self.title = title
        self.description = description
        self.emoji = emoji
        self.completed = False

def generate_chapter_nodes(chapter_id: int) -> List[AdventureNode]:
    """Genera la lista fija de 10 Nodos para el Capítulo especificado."""
    cfg = CHAPTERS_CONFIG.get(chapter_id, CHAPTERS_CONFIG[1])
    
    nodes = [
        AdventureNode(1, "combat", "Nodo 1: Frontera Peligrosa", "Un grupo de patrulla enemiga bloquea el paso.", "⚔️"),
        AdventureNode(2, "event", "Nodo 2: Encrucijada de Runas", "Un hallazgo místico en el camino.", "📜"),
        AdventureNode(3, "combat", "Nodo 3: Emboscada en las Sombras", "Enemigos acechan entre la vegetación/ruinas.", "⚔️"),
        AdventureNode(4, "camp", "Nodo 4: Campamento del Viajero", "Un lugar seguro para descansar o afilar armas.", "🏕️"),
        AdventureNode(5, "combat_elite", "Nodo 5: Guardián Élite", "Un formidable enemigo Élite custodia el puente.", "⭐"),
        AdventureNode(6, "event", "Nodo 6: Suministros Abandonados", "Cajas de provisiones de antiguas expediciones.", "🏺"),
        AdventureNode(7, "combat", "Nodo 7: Asalto a la Guarnición", "Tropa enemiga fortificada.", "⚔️"),
        AdventureNode(8, "camp", "Nodo 8: Santuario de la Paz", "Un momento de calma antes de la batalla final.", "🕊️"),
        AdventureNode(9, "combat_elite", "Nodo 9: Teniente del Abismo", "El campeón personal del Jefe de Capítulo.", "💀"),
        AdventureNode(10, "boss", f"Nodo 10: {cfg['boss']['name']}", f"La batalla final del capítulo. Rescata al **{cfg['npc_rescue']['name']}**.", "👑"),
    ]
    return nodes
