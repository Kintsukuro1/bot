"""
Paquete central de utilidades y recursos de combate.
"""

from src.utils.combat.resources import ClassResource, CLASS_RESOURCE_CONFIGS
from src.utils.combat.entities import CombatEntity, EntityManager

__all__ = [
    "ClassResource",
    "CLASS_RESOURCE_CONFIGS",
    "CombatEntity",
    "EntityManager",
]
