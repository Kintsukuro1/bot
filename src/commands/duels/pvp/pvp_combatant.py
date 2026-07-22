import discord
import random
from src.utils.combat_progression import (
    calc_base_stats, calc_equipment_bonus, get_effective_bonus,
    apply_subclass_equipment_conversion, get_equipped_set_pieces,
    EQUIPMENT_SETS_CACHE, load_equipment_sets_cache
)

class Combatant:
    """Estado de un jugador durante el combate PvP."""

    def __init__(self, user: discord.Member, level: int, equipment: dict,
                 combat_class: str = None, combat_subclass: str = None):
        self.user = user
        self.level = level
        self.combat_class = combat_class
        self.combat_subclass = combat_subclass
        self.equipment = equipment

        base = calc_base_stats(level)
        bonus, passives, secondary_bonus = calc_equipment_bonus(equipment)

        bonus, self.subclass_extras = apply_subclass_equipment_conversion(bonus, combat_subclass)

        dodge_bonus_from_gem = secondary_bonus.get("dodge", 0.0)
        subclass_dodge = self.subclass_extras.get("dodge_chance_bonus", 0.0)
        self.subclass_extras["dodge_chance_bonus"] = min(0.30, subclass_dodge + dodge_bonus_from_gem)

        crit_bonus_from_gem = secondary_bonus.get("crit", 0.0)
        subclass_crit = self.subclass_extras.get("crit_chance_bonus", 0.0)

        weapon_item = equipment.get("Arma")
        weapon_crit_mod = 0.0
        if weapon_item and weapon_item.get("weapon_subtype"):
            sub = weapon_item["weapon_subtype"]
            if sub == "daga":
                weapon_crit_mod = 0.05
            elif sub == "hacha":
                weapon_crit_mod = -0.05

        self.subclass_extras["crit_chance_bonus"] = min(0.25, subclass_crit + crit_bonus_from_gem + weapon_crit_mod)

        effective, _, _ = get_effective_bonus(bonus, level)

        self.max_hp = base["hp"] + int(round(effective.get("hp", 0)))
        self.hp = self.max_hp
        self.pre_hit_hp = self.hp
        self.atk = base["atk"] + int(round(effective.get("atk", 0)))
        self.base_atk = self.atk
        self.mag = base["mag"] + int(round(effective.get("mag", 0)))
        self.def_stat = base["def"] + int(round(effective.get("def", 0)))

        if any(p['id'] == 'glass_heart' for p in passives):
            self.max_hp = int(self.max_hp * 0.92)
            self.hp = self.max_hp
            self.pre_hit_hp = self.hp
            self.atk = int(self.atk * 1.12)
            self.base_atk = self.atk
            self.mag = int(self.mag * 1.12)

        self.vampirism_pct = 0.08 if any(p['id'] == 'vampirism' for p in passives) else 0.0
        if any(p['id'] == 'vampirism_improved' for p in passives):
            self.vampirism_pct += 0.15
        self.healing_bonus_pct = 0.0
        self.set_bonus_yggdrasil_4pc = False
        self.set_bonus_ignis_4pc = False
        self.set_bonus_caelum_4pc = False
        self.set_bonus_thanatos_4pc = False
        self.set_bonus_leviathan_4pc = False
        self.set_bonus_aurelius_4pc = False
        self.set_bonus_abyssus_4pc = False
        self.first_strike_used = False
        self.low_hp_heal_used = False
        self.next_hit_lifesteal_bonus = 0.0

        if not EQUIPMENT_SETS_CACHE:
            load_equipment_sets_cache()

        set_pieces = get_equipped_set_pieces(equipment)
        for set_key, count in set_pieces.items():
            set_config = EQUIPMENT_SETS_CACHE.get(set_key)
            if not set_config:
                continue
            if count >= 2:
                if set_key == "set_yggdrasil":
                    self.max_hp = int(self.max_hp * 1.08)
                    self.hp = self.max_hp
                elif set_key == "set_ignis":
                    self.atk = int(self.atk * 1.08)
                    self.base_atk = self.atk
                elif set_key == "set_caelum":
                    self.subclass_extras["crit_chance_bonus"] = min(0.25, self.subclass_extras.get("crit_chance_bonus", 0.0) + 0.08)
                elif set_key == "set_thanatos":
                    self.vampirism_pct += 0.08
                elif set_key == "set_leviathan":
                    self.def_stat = int(self.def_stat * 1.08)
                elif set_key == "set_aurelius":
                    self.healing_bonus_pct += 0.08
                elif set_key == "set_abyssus":
                    ab_stat = random.choice(["hp", "atk", "crit", "vamp", "def"])
                    if ab_stat == "hp":
                        self.max_hp = int(self.max_hp * 1.08)
                        self.hp = self.max_hp
                    elif ab_stat == "atk":
                        self.atk = int(self.atk * 1.08)
                        self.base_atk = self.atk
                    elif ab_stat == "crit":
                        self.subclass_extras["crit_chance_bonus"] = min(0.25, self.subclass_extras.get("crit_chance_bonus", 0.0) + 0.08)
                    elif ab_stat == "vamp":
                        self.vampirism_pct += 0.08
                    elif ab_stat == "def":
                        self.def_stat = int(self.def_stat * 1.08)

            if count >= 4:
                if set_key == "set_yggdrasil":
                    self.set_bonus_yggdrasil_4pc = True
                elif set_key == "set_ignis":
                    self.set_bonus_ignis_4pc = True
                elif set_key == "set_caelum":
                    self.set_bonus_caelum_4pc = True
                elif set_key == "set_thanatos":
                    self.set_bonus_thanatos_4pc = True
                elif set_key == "set_leviathan":
                    self.set_bonus_leviathan_4pc = True
                elif set_key == "set_aurelius":
                    self.set_bonus_aurelius_4pc = True
                elif set_key == "set_abyssus":
                    self.set_bonus_abyssus_4pc = True
                    possible_effects = [
                        "yggdrasil_group_regen",
                        "ignis_burn_extension",
                        "caelum_first_strike_dodge",
                        "thanatos_ally_death_lifesteal",
                        "leviathan_cc_reduction",
                        "aurelius_low_hp_heal",
                    ]
                    self.abyssus_rolled_4pc_effect = random.choice(possible_effects)

        if getattr(self, "set_bonus_abyssus_4pc", False):
            effect_map = {
                "yggdrasil_group_regen": ("set_bonus_yggdrasil_4pc", "Regeneración de Grupo (Yggdrasil)"),
                "ignis_burn_extension": ("set_bonus_ignis_4pc", "Extensión de Quemadura (Ignis)"),
                "caelum_first_strike_dodge": ("set_bonus_caelum_4pc", "Esquiva Inicial (Caelum)"),
                "thanatos_ally_death_lifesteal": ("set_bonus_thanatos_4pc", "Robo de Vida por Aliado Caído (Thanatos)"),
                "leviathan_cc_reduction": ("set_bonus_leviathan_4pc", "Reducción de CC (Leviathán)"),
                "aurelius_low_hp_heal": ("set_bonus_aurelius_4pc", "Curación al HP Crítico (Aurelius)"),
            }
            effect_id = getattr(self, "abyssus_rolled_4pc_effect", None)
            if effect_id in effect_map:
                flag, name = effect_map[effect_id]
                setattr(self, flag, True)
                self.abyssus_log = f"🌀 **Efecto Abyssus:** ¡{self.user.display_name} obtiene el bonus del set **{name}**!"

        ma_pcts = {"atk": 0.0, "mag": 0.0, "def": 0.0, "hp": 0.0}
        for slot, item in equipment.items():
            ma_key = item.get("mini_affix_key")
            ma_val = item.get("mini_affix_value")
            if ma_key and ma_val is not None:
                if ma_key == "furia": ma_pcts["atk"] += ma_val
                elif ma_key == "vacio": ma_pcts["mag"] += ma_val
                elif ma_key == "bastion": ma_pcts["def"] += ma_val
                elif ma_key == "vital": ma_pcts["hp"] += ma_val

        if ma_pcts["hp"] > 0:
            self.max_hp = int(self.max_hp * (1.0 + ma_pcts["hp"]))
            self.hp = self.max_hp
        if ma_pcts["atk"] > 0:
            self.atk = int(self.atk * (1.0 + ma_pcts["atk"]))
            self.base_atk = self.atk
        if ma_pcts["mag"] > 0:
            self.mag = int(self.mag * (1.0 + ma_pcts["mag"]))
        if ma_pcts["def"] > 0:
            self.def_stat = int(self.def_stat * (1.0 + ma_pcts["def"]))

        self.pre_hit_hp = self.hp
        self.last_action = None
        self.special_used_this_combat = False
        self.shield = self.subclass_extras.get("shield_pool", 0)

        self.is_defending = False
        self.special_cooldown = 0
        self.skill10_cooldown = 0
        self.skill15_cooldown = 0
        self.taunt_cooldown = 0
        self.consecutive_timeouts = 0

        self._stun_turns = 0
        self._frozen_turns = 0
        self._silence_turns = 0
        self._blinded_turns = 0
        self.bleed_turns = 0
        self.bleed_source_pct = 0.06
        self.last_physical_damage_taken = 0
        self.damage_reduction_turns = 0
        self.damage_reduction_pct = 0.0
        self.atk_buff_turns = 0
        self.atk_buff_pct = 0.0
        self.juicio_final_turns = 0
        self.juicio_final_reflect_pct = 0.0
        self.evasion_buff_turns = 0
        self.evasion_buff_pct = 0.0
        self.guaranteed_dodge_next = False
        self.anti_heal_turns = 0
        self.weakness_turns = 0
        self.weakness_pct = 0.0
        self.fragility_turns = 0
        self.fragility_pct = 0.0
        self.vulnerability_turns = 0
        self.vulnerability_pct = 0.0
        self.hot_turns = 0
        self.hot_pct = 0.0
        self.total_damage_taken = 0
        self.enhanced_burn_pct = 0.0
        self.enhanced_burn_turns = 0

        self.passives = passives
        self.used_second_wind = False
        self.arcane_shield_active = any(p['id'] == 'arcane_shield' for p in passives)
        self.has_bleed_on_hit = any(p['id'] == 'bleed_on_hit' for p in passives)

        self.passive_icd = {}
        self.used_erratic_ward = False
        self.used_eternal_watch = False
        self.eternal_watch_trigger_log = None

    def has_eternal_watch_active(self) -> bool:
        return any(p['id'] == 'eternal_watch' for p in self.passives) and not getattr(self, "used_eternal_watch", False)

    def trigger_eternal_watch(self, debuff_name: str):
        self.used_eternal_watch = True
        self.eternal_watch_trigger_log = f"👁️ **Vigilancia Eterna:** ¡{self.user.display_name} resiste el debuff de {debuff_name}!"

    @property
    def stun_turns(self) -> int:
        return self._stun_turns

    @stun_turns.setter
    def stun_turns(self, value: int):
        if value > getattr(self, "_stun_turns", 0):
            if self.has_eternal_watch_active():
                self.trigger_eternal_watch("Aturdimiento")
                return
        if value > getattr(self, "_stun_turns", 0) and getattr(self, "set_bonus_leviathan_4pc", False):
            value = max(1, int(value * 0.85))
        self._stun_turns = value

    @property
    def frozen_turns(self) -> int:
        return self._frozen_turns

    @frozen_turns.setter
    def frozen_turns(self, value: int):
        if value > getattr(self, "_frozen_turns", 0):
            if self.has_eternal_watch_active():
                self.trigger_eternal_watch("Congelación")
                return
        if value > getattr(self, "_frozen_turns", 0) and getattr(self, "set_bonus_leviathan_4pc", False):
            value = max(1, int(value * 0.85))
        self._frozen_turns = value

    @property
    def silence_turns(self) -> int:
        return self._silence_turns

    @silence_turns.setter
    def silence_turns(self, value: int):
        if value > getattr(self, "_silence_turns", 0):
            if self.has_eternal_watch_active():
                self.trigger_eternal_watch("Silencio")
                return
        if value > getattr(self, "_silence_turns", 0) and getattr(self, "set_bonus_leviathan_4pc", False):
            value = max(1, int(value * 0.85))
        self._silence_turns = value

    @property
    def blinded_turns(self) -> int:
        return getattr(self, "_blinded_turns", 0)

    @blinded_turns.setter
    def blinded_turns(self, value: int):
        if value > getattr(self, "_blinded_turns", 0):
            if self.has_eternal_watch_active():
                self.trigger_eternal_watch("Ceguera")
                return
        self._blinded_turns = value
