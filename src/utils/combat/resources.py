"""
Módulo de Gestión de Recursos Únicos por Clase (Furia, Fe, Sombras, Maná Arcano, Luz Sagrada, etc.)
Soporta escalabilidad vertical (mecanismos profundos) y horizontal (nuevas clases).
"""

from __future__ import annotations
from typing import Optional, Tuple, Dict, Any

# Configuración de los recursos por clase
CLASS_RESOURCE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "Guerrero": {
        "name": "Furia",
        "emoji": "💥",
        "min": 0,
        "max": 100,
        "display_type": "bar",
        "desc": "Se genera al recibir (+15) o asestar (+10) daño físico. A 100 entra en Desenfreno."
    },
    "Paladín": {
        "name": "Fe",
        "emoji": "✝️",
        "min": 0,
        "max": 5,
        "display_type": "stacks",
        "desc": "Se genera al mitigar/defender daño (+1). Cada stack aumenta escudos y curas +5%."
    },
    "Pícaro": {
        "name": "Sombras",
        "emoji": "👤",
        "min": 0,
        "max": 3,
        "display_type": "stacks",
        "desc": "Se genera al esquivar (+1) o usar ceguera/paso fantasma. 3 stacks = Crítico Letal."
    },
    "Mago": {
        "name": "Maná Arcano",
        "emoji": "🔮",
        "min": 0,
        "max": 100,
        "display_type": "bar",
        "desc": "Se genera al lanzar hechizos (+25). A 100 activa Sobrecarga Arcana (-2 CD a hechizos)."
    },
    "Clérigo": {
        "name": "Luz Sagrada",
        "emoji": "✨",
        "min": 0,
        "max": 5,
        "display_type": "stacks",
        "desc": "Se genera al curar o disipar debuffs (+1). Amplifica curaciones y añade HoT."
    },
    # ── FUTURAS CLASES (Preparadas para escalabilidad) ──
    "Arquero": {
        "name": "Concentración",
        "emoji": "🏹",
        "min": 0,
        "max": 100,
        "display_type": "bar",
        "desc": "Se acumula +20 por turno sin recibir daño. Aumenta penetración de armadura."
    },
    "Monje": {
        "name": "Chi",
        "emoji": "☯️",
        "min": 0,
        "max": 5,
        "display_type": "stacks",
        "desc": "Gana +1 Chi por cada ataque físico. Se consume para combos y artes marciales."
    },
    "Alquimista": {
        "name": "Reactivos",
        "emoji": "🧪",
        "min": 0,
        "max": 10,
        "display_type": "stacks",
        "desc": "Se destilan por turno. Se consumen para preparar o potenciar brebajes."
    },
    "Invocador": {
        "name": "Esencia",
        "emoji": "👹",
        "min": 0,
        "max": 100,
        "display_type": "bar",
        "desc": "Se acumula al atacar o morir invocaciones (+20). Permite invocar criaturas superiores."
    },
    "Ingeniero": {
        "name": "Energía",
        "emoji": "⚙️",
        "min": 0,
        "max": 100,
        "display_type": "bar",
        "desc": "Se genera al atacar o reparar dispositivos (+25). Alimenta torretas y minas."
    },
    "Chamán": {
        "name": "Tótems",
        "emoji": "⭐",
        "min": 0,
        "max": 3,
        "display_type": "stacks",
        "desc": "Se acumula al sintonizarse con los elementos (+1). Permite invocar hasta 3 tótems activos."
    },
    "Bardo": {
        "name": "Inspiración",
        "emoji": "🎭",
        "min": 0,
        "max": 100,
        "display_type": "bar",
        "desc": "Se genera al mantener melodías activas (+20). Aumenta la efectividad de las auras de equipo."
    },
    "Brujo": {
        "name": "Maná Oscuro",
        "emoji": "🌑",
        "min": 0,
        "max": 100,
        "display_type": "bar",
        "desc": "Se obtiene al drenar HP propio (+25). Potencia hechicería de sombras y maldiciones."
    },
    "Cronomante": {
        "name": "Flujo Temporal",
        "emoji": "⏳",
        "min": 0,
        "max": 5,
        "display_type": "stacks",
        "desc": "Se genera con cada turno que pasa (+1). Permite alterar cooldowns y otorgar turnos extra."
    },
    "Vampiro": {
        "name": "Sangre",
        "emoji": "🩸",
        "min": 0,
        "max": 100,
        "display_type": "bar",
        "desc": "Se genera al infligir o drenar sangrado (+25). Desata la transformación en Señor Sangriento."
    },
}


class ClassResource:
    """Manejador del recurso único de combate para un jugador."""

    def __init__(self, combat_class: Optional[str]):
        self.combat_class = combat_class
        config = CLASS_RESOURCE_CONFIGS.get(combat_class, {}) if combat_class else {}
        
        self.name: str = config.get("name", "Energía")
        self.emoji: str = config.get("emoji", "⚡")
        self.min_val: int = config.get("min", 0)
        self.max_val: int = config.get("max", 100)
        self.display_type: str = config.get("display_type", "bar")
        self.value: int = 0
        
        # Estados especiales derivados del recurso
        self.is_overcharged: bool = False  # Mago (Sobrecarga) / Guerrero (Desenfreno)

    def add(self, amount: int) -> Tuple[int, Optional[str]]:
        """Suma puntos al recurso y retorna (cantidad_efectiva_añadida, mensaje_evento_opcional)."""
        if not self.combat_class or self.max_val <= 0:
            return 0, None
        
        old = self.value
        self.value = min(self.max_val, self.value + amount)
        added = self.value - old

        log_msg = None
        if self.value >= self.max_val and old < self.max_val:
            if self.combat_class == "Guerrero":
                self.is_overcharged = True
                log_msg = f"💥 **¡DESENFRENO!** La Furia de guerrero alcanza el 100% (+30% daño en la próxima habilidad)."
            elif self.combat_class == "Mago":
                self.is_overcharged = True
                log_msg = f"🔮 **¡SOBRECARGA ARCANA!** El Maná Arcano está al 100% (Próximo hechizo reduce CDs -2 turnos)."
            elif self.combat_class == "Pícaro":
                log_msg = f"👤 **¡SOMBRAS MÁXIMAS!** (3 Stacks) Próximo ataque asestará un Crítico Letal."
            elif self.combat_class == "Paladín":
                log_msg = f"✝️ **¡PLENITUD DE FE!** (5 Stacks) Escudos y curas potenciados un +25%."
            elif self.combat_class == "Clérigo":
                log_msg = f"✨ **¡LUZ DE GRACIA!** (5 Stacks) Próxima curación otorgará regeneración de grupo."

        return added, log_msg

    def consume(self, amount: int) -> bool:
        """Intenta consumir una cantidad del recurso. Retorna True si tuvo éxito."""
        if self.value >= amount:
            self.value -= amount
            if self.value < self.max_val:
                self.is_overcharged = False
            return True
        return False

    def reset(self):
        """Reinicia el recurso a 0."""
        self.value = 0
        self.is_overcharged = False

    def try_consume_and_boost(self) -> Tuple[float, Optional[str]]:
        """Intenta consumir el recurso acumulado al lanzar una habilidad activa.

        Returns:
            Tuple[multiplicador_de_poder, mensaje_de_log_si_hubo_potenciacion]
        """
        if not self.combat_class:
            return 1.0, None

        if self.combat_class == "Guerrero":
            if self.is_overcharged or self.value >= 50:
                mult = 1.30
                self.consume(50)
                return mult, f"💥 **[Consumo de Furia]** ¡Consume Furia para potenciar el golpe en **+30%**!"

        elif self.combat_class == "Paladín":
            if self.value >= 3:
                self.consume(3)
                return 1.25, f"✝️ **[Consumo de Fe]** ¡Consume 3 Stacks de Fe para potenciar escudos/curaciones un **+25%**!"

        elif self.combat_class == "Pícaro":
            if self.value >= 3:
                self.consume(3)
                return 1.35, f"👤 **[Consumo de Sombras]** ¡Consume 3 Stacks de Sombras para asestar un **Golpe Letal (+35%)**!"

        elif self.combat_class == "Mago":
            if self.is_overcharged or self.value >= 100:
                self.reset()
                return 1.30, f"🔮 **[Sobrecarga Arcana]** ¡Consume 100% de Maná Arcano (+30% daño mágico y reduce CDs -2t)!"

        elif self.combat_class == "Clérigo":
            if self.value >= 3:
                self.consume(3)
                return 1.25, f"✨ **[Consumo de Luz]** ¡Consume 3 Stacks de Luz Sagrada (+25% curación y otorga HoT de grupo)!"

        elif self.combat_class == "Arquero":
            if self.value >= 50:
                self.consume(50)
                return 1.30, f"🏹 **[Consumo de Concentración]** ¡Disparo de alta precisión con **+30% daño extra**!"

        elif self.combat_class == "Monje":
            if self.value >= 3:
                self.consume(3)
                return 1.35, f"☯️ **[Combo de Chi]** ¡Consume 3 Stacks de Chi para desatar un **Combo Devastador (+35% daño)**!"

        elif self.combat_class == "Alquimista":
            if self.value >= 4:
                self.consume(4)
                return 1.30, f"🧪 **[Destilación de Reactivos]** ¡Consume 4 Reactivos para potenciar el brebaje un **+30%**!"

        elif self.combat_class == "Invocador":
            if self.value >= 50:
                self.consume(50)
                return 1.35, f"👹 **[Consumo de Esencia]** ¡Sacrifica Esencia para potenciar sus Invocaciones (+35% poder)!"

        elif self.combat_class == "Ingeniero":
            if self.value >= 50:
                self.consume(50)
                return 1.30, f"⚙️ **[Sobrecarga de Energía]** ¡Sobrecarga los circuitos (+30% potencia de Torretas y Minas)!"

        elif self.combat_class == "Chamán":
            if self.value >= 2:
                self.consume(2)
                return 1.25, f"⭐ **[Sintonía Tótemica]** ¡Sintoniza 2 Tótems para amplificar las Auras de Grupo (+25%)!"

        elif self.combat_class == "Bardo":
            if self.value >= 50:
                self.consume(50)
                return 1.35, f"🎭 **[Crescendo de Inspiración]** ¡Eleva la melodía y otorga **+35% potencia a auras de equipo**!"

        elif self.combat_class == "Brujo":
            if self.value >= 50:
                self.consume(50)
                return 1.35, f"🌑 **[Maná Oscuro]** ¡Canaliza la magia de sombras para **+35% daño mágico masivo**!"

        elif self.combat_class == "Cronomante":
            if self.value >= 3:
                self.consume(3)
                return 1.30, f"⏳ **[Salto Temporal]** ¡Consume 3 Flujos Temporales para reducir cooldowns del equipo y potenciar el golpe!"

        elif self.combat_class == "Vampiro":
            if self.value >= 50:
                self.consume(50)
                return 1.40, f"🩸 **[Frenesí Sangriento]** ¡Consume Sangre acumulada (+40% robo de vida y amplifica Hemorragia)!"

        return 1.0, None

    # ── GANCHOS DE EVENTOS DE COMBATE ──

    def on_damage_taken(self, damage_amount: int) -> Optional[str]:
        """Evento al recibir daño."""
        if self.combat_class == "Guerrero":
            fury_gained = max(10, min(30, int(damage_amount * 0.15)))
            _, log = self.add(fury_gained)
            return log
        elif self.combat_class == "Paladín":
            _, log = self.add(1)
            return log
        return None

    def on_attack_dealt(self, damage_amount: int, is_crit: bool = False) -> Optional[str]:
        """Evento al asestar un ataque."""
        if self.combat_class == "Guerrero":
            gain = 15 if is_crit else 10
            _, log = self.add(gain)
            return log
        elif self.combat_class == "Monje":
            _, log = self.add(1)
            return log
        return None

    def on_dodge(self) -> Optional[str]:
        """Evento al esquivar un ataque."""
        if self.combat_class == "Pícaro":
            _, log = self.add(1)
            return log
        return None

    def on_spell_cast(self) -> Optional[str]:
        """Evento al lanzar un hechizo o habilidad especial."""
        if self.combat_class == "Mago":
            _, log = self.add(25)
            return log
        return None

    def on_heal_or_dispel(self) -> Optional[str]:
        """Evento al realizar curación o disipación."""
        if self.combat_class == "Clérigo":
            _, log = self.add(1)
            return log
        return None

    def format_display(self) -> str:
        """Devuelve representación formateada para el Embed del combate."""
        if not self.combat_class or self.max_val <= 0:
            return ""

        if self.display_type == "stacks":
            filled = self.emoji * self.value
            empty = "⚪" * (self.max_val - self.value)
            return f"{self.name}: {filled}{empty} ({self.value}/{self.max_val})"
        else:
            pct = int((self.value / self.max_val) * 10)
            bar = "█" * pct + "░" * (10 - pct)
            state_tag = " 🔥" if self.is_overcharged else ""
            return f"{self.emoji} {self.name}: `[{bar}]` {self.value}/{self.max_val}{state_tag}"
