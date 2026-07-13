from src.utils.raid_config import BOSS_ABILITIES, calc_boss_stats

class RaidBoss:
    """Estado del boss durante el combate de raid."""

    def __init__(self, boss_config: dict, total_power: float = 0.0, difficulty: str = "normal", total_level: float | None = None, is_miniboss: bool = False):
        self.name = boss_config["name"]
        self.emoji = boss_config["emoji"]
        self.element = boss_config["element"]
        self.color = boss_config["color"]
        self.lore = boss_config["lore"]
        self.ability_id = boss_config["ability"]
        self.ability = BOSS_ABILITIES[self.ability_id]

        if total_level is not None:
            total_power = total_level

        self.is_intangible = False

        if is_miniboss:
            self.max_hp = boss_config["hp"]
            self._hp = boss_config["hp"]
            self.atk = boss_config["atk"]
            self.def_stat = boss_config["def_stat"]
        else:
            # Stats escalados
            stats = calc_boss_stats(boss_config, total_power, difficulty)
            self.max_hp = stats["max_hp"]
            self._hp = stats["hp"]
            self.atk = stats["atk"]
            self.def_stat = stats["def_stat"]

        self.miniboss_key = boss_config.get("miniboss_key")
        self.is_miniboss = is_miniboss
        self.minion_pool = boss_config.get("minion_pool")

        # Progresión de fases
        self.phase = 1
        self.phase2_ability_id = boss_config.get("phase2_ability")
        self.phase3_ability_id = boss_config.get("phase3_ability")
        self.fury_phase_triggered = False

        # Stats base guardados para mutación
        self._base_atk = self.atk
        self._base_def = self.def_stat

        # Debuffs/Estados del Boss
        self.stun_turns = 0
        self.weakness_turns = 0
        self.weakness_pct = 0.0
        self.fragility_turns = 0
        self.fragility_pct = 0.0
        self.vulnerability_turns = 0
        self.vulnerability_pct = 0.0
        self.burn_turns = 0
        self.enhanced_burn_turns = 0
        self.blinded_turns = 0
        self.frozen_turns = 0
        self.silence_turns = 0
        self.bleed_turns = 0
        self.bleed_source_pct = 0.06
        self.last_physical_damage_taken = 0

    @property
    def hp(self):
        return self._hp

    @hp.setter
    def hp(self, value):
        if getattr(self, "is_intangible", False) and value < self._hp:
            return
        self._hp = value
