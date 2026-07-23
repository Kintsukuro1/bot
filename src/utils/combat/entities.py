"""
Módulo de Gestión de Entidades Auxiliares de Combate (Invocaciones, Torretas, Tótems, Mascotas).
Proporciona la infraestructura base para las mecánicas de la Fase 3 (Invocador, Ingeniero, Chamán).
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any

class CombatEntity:
    """Representa una entidad invocada o desplegada en el terreno de combate."""

    def __init__(self, name: str, emoji: str, owner_id: int, entity_type: str,
                 hp: int, duration_turns: int = 3, atk: int = 0, def_stat: int = 0):
        self.name = name
        self.emoji = emoji
        self.owner_id = owner_id
        self.entity_type = entity_type  # 'minion', 'turret', 'totem'
        self.max_hp = hp
        self.hp = hp
        self.duration_turns = duration_turns
        self.atk = atk
        self.def_stat = def_stat
        self.is_active = True

    def take_damage(self, amount: int) -> int:
        """Aplica daño a la entidad."""
        mitigated = max(1, amount - int(self.def_stat * 0.3))
        self.hp = max(0, self.hp - mitigated)
        if self.hp == 0:
            self.is_active = False
        return mitigated

    def on_turn_end(self) -> Tuple[bool, str]:
        """Reduce la duración restante y determina si expira."""
        self.duration_turns -= 1
        if self.duration_turns <= 0 or self.hp <= 0:
            self.is_active = False
            return False, f"💨 **[{self.emoji} {self.name}]** ha expirado o sido destruido."
        return True, ""


class EntityManager:
    """Manejador de entidades activas por jugador durante la batalla."""

    def __init__(self):
        self.entities: List[CombatEntity] = []

    def spawn(self, entity: CombatEntity) -> str:
        """Despliega una nueva entidad en el combate."""
        self.entities.append(entity)
        return f"✨ **[Invocación]** ¡{entity.emoji} **{entity.name}** ha entrado al campo de batalla! ({entity.hp} HP, {entity.duration_turns}t)"

    def get_active_entities(self) -> List[CombatEntity]:
        """Retorna las entidades activas."""
        return [e for e in self.entities if e.is_active]

    def process_turn_end(self) -> List[str]:
        """Procesa el final de turno para todas las entidades."""
        logs = []
        for e in list(self.entities):
            if e.is_active:
                still_active, msg = e.on_turn_end()
                if msg:
                    logs.append(msg)
        self.entities = [e for e in self.entities if e.is_active]
        return logs
