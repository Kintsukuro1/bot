import discord
import random
from src.utils.combat_config import SKILLS_CONFIG
from src.utils.combat import ClassResource
from src.utils.combat_progression import (
    calc_base_stats, calc_equipment_bonus, get_effective_bonus,
    apply_subclass_equipment_conversion, get_equipped_set_pieces,
    EQUIPMENT_SETS_CACHE, load_equipment_sets_cache
)

class RaidCombatant:
    """Estado de un jugador durante la raid."""

    def __init__(self, user: discord.Member, level: int, equipment: dict, combat_class: str = None, combat_subclass: str = None):
        self.user = user
        self.level = level
        self.combat_class = combat_class
        self.combat_subclass = combat_subclass
        self.equipment = equipment
        self.resource = ClassResource(combat_class)

        # Stats base + equipo
        base = calc_base_stats(level)
        bonus, passives, secondary_bonus = calc_equipment_bonus(equipment)

        # Aplicar conversión de equipo por subclase (antes del cap)
        bonus, self.subclass_extras = apply_subclass_equipment_conversion(bonus, combat_subclass)

        # Sumar secondary_bonus a dodge_chance_bonus/crit_chance_bonus antes de aplicar el tope
        dodge_bonus_from_gem = secondary_bonus.get("dodge", 0.0)
        subclass_dodge = self.subclass_extras.get("dodge_chance_bonus", 0.0)
        self.subclass_extras["dodge_chance_bonus"] = min(0.30, subclass_dodge + dodge_bonus_from_gem)

        crit_bonus_from_gem = secondary_bonus.get("crit", 0.0)
        subclass_crit = self.subclass_extras.get("crit_chance_bonus", 0.0)

        # Modificador de crítico por subtipo de arma (Daga +5%, Hacha -5%)
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
        self.atk = base["atk"] + int(round(effective.get("atk", 0)))
        self.base_atk = self.atk  # Para restaurar después de debuffs
        self.mag = base["mag"] + int(round(effective.get("mag", 0)))
        self.def_stat = base["def"] + int(round(effective.get("def", 0)))

        # Pasivo: Corazón Fragmentado (glass_heart)
        if any(p['id'] == 'glass_heart' for p in passives):
            self.max_hp = int(self.max_hp * 0.92)
            self.hp = self.max_hp
            self.atk = int(self.atk * 1.12)
            self.base_atk = self.atk
            self.mag = int(self.mag * 1.12)

        # Inicializar variables de bonus de sets
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

        # Cargar cache de sets si está vacío
        if not EQUIPMENT_SETS_CACHE:
            load_equipment_sets_cache()

        # Detección de piezas de set
        set_pieces = get_equipped_set_pieces(equipment)
        for set_key, count in set_pieces.items():
            set_config = EQUIPMENT_SETS_CACHE.get(set_key)
            if not set_config:
                continue
            if count >= 2:
                # Aplicar Bonus 2pc
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
                    possible_abyssus_stats = ["hp", "atk", "crit", "vamp", "def"]
                    ab_stat = random.choice(possible_abyssus_stats)
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
                # Activar Flags de 4pc
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

        # Abyssus random set effect activation
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

        # Aplicar mini-afijos porcentuales (furia, vacio, bastion, vital)
        ma_pcts = {"atk": 0.0, "mag": 0.0, "def": 0.0, "hp": 0.0}
        for slot, item in equipment.items():
            ma_key = item.get("mini_affix_key")
            ma_val = item.get("mini_affix_value")
            if ma_key and ma_val is not None:
                if ma_key == "furia":
                    ma_pcts["atk"] += ma_val
                elif ma_key == "vacio":
                    ma_pcts["mag"] += ma_val
                elif ma_key == "bastion":
                    ma_pcts["def"] += ma_val
                elif ma_key == "vital":
                    ma_pcts["hp"] += ma_val

        # Aplicar los porcentajes acumulados
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

        # Pasivos de equipo (Legendario)
        self.passives = passives
        self.last_action = None
        self.special_used_this_combat = False
        self.used_second_wind = False
        self.arcane_shield_active = any(p['id'] == 'arcane_shield' for p in passives)
        self.has_crit_boost = any(p['id'] == 'crit_boost' for p in passives)
        self.has_vampirism = any(p['id'] == 'vampirism' for p in passives)
        self.has_regen = any(p['id'] == 'regen' for p in passives)
        self.has_fury = any(p['id'] == 'fury' for p in passives)
        self.has_dodge = any(p['id'] == 'dodge' for p in passives)
        self.has_parry = any(p['id'] == 'parry' for p in passives)
        self.has_bleed_on_hit = any(p['id'] == 'bleed_on_hit' for p in passives)

        # Estado de combate
        self.is_defending = False
        self.is_dead = False
        self.is_taunting = False
        self.poison_turns = 0      # Turnos de veneno restantes
        self.poison_damage = 0     # Daño por turno de veneno
        self.atk_debuff_turns = 0  # Turnos de reducción de ATK
        self.atk_debuff_pct = 0.0  # Porcentaje de reducción

        # Escudo de absorción de subclase (Guardián Sagrado, Guardián de la Fe)
        self.shield = self.subclass_extras.get("shield_pool", 0)

        # Cooldowns de habilidades
        self.class_ability_cooldown = 0 # Enfriamiento de habilidad de clase (legacy)
        self.special_cooldown = 0       # Cooldown de especial (nivel 5)
        self.skill10_cooldown = 0       # Cooldown de habilidad Nv. 10
        self.skill15_cooldown = 0       # Cooldown de habilidad Nv. 15 (ultimate)
        self.taunt_cooldown = 0         # Cooldown de taunt pasivo

        # Estados de subclase
        self.taunt_turns = 0                # Duración del taunt (tanques)
        self._stun_turns = 0                 # Turnos aturdido (Golpe de Escudo, Onda Escarcha)
        self._frozen_turns = 0               # Turnos congelado
        self._silence_turns = 0              # Turnos silenciado
        self.bleed_turns = 0                # Turnos sangrado
        self.bleed_source_pct = 0.06        # 6% del último daño físico
        self.last_physical_damage_taken = 0  # Para sangrado
        self.damage_reduction_turns = 0     # Turnos de -X% daño recibido (Muralla)
        self.damage_reduction_pct = 0.0
        self.atk_buff_turns = 0             # Turnos de +X% ATK (Sed de Sangre, Estandarte)
        self.atk_buff_pct = 0.0
        self.juicio_final_turns = 0         # Reflejo 150% (Vengador ult)
        self.juicio_final_reflect_pct = 0.0
        self.evasion_buff_turns = 0         # Evasión extra (Danza de Cuchillas)
        self.evasion_buff_pct = 0.0
        self.guaranteed_dodge_next = False   # Paso Fantasma
        self.anti_heal_turns = 0            # Impide curación (Pacto de Sangre)
        self.weakness_turns = 0             # Debilidad: -ATK (Trampa de Acónito)
        self.weakness_pct = 0.0
        self.fragility_turns = 0            # Fragilidad: -DEF (Enjambre)
        self.fragility_pct = 0.0
        self.vulnerability_turns = 0        # Vulnerabilidad +daño recibido (Singularidad)
        self.vulnerability_pct = 0.0
        self.hot_turns = 0                  # Heal over time (Aura de Salvación)
        self.hot_pct = 0.0
        self.total_damage_taken = 0         # Acumulador para Castigo Divino (Vengador)
        self.enhanced_burn_pct = 0.0        # Quemadura mejorada (Cataclismo)
        self.enhanced_burn_turns = 0
        self.burn_turns = 0                 # Turnos de quemadura
        self.frenzy_turns = 0               # Turnos de Frenesí

        # Mecánicas de Fase de Furia
        self.dominated_turns = 0
        self.fury_stun_pending = False
        self.retribution_active = False     # Postura de Represalia activa
        self._blinded_turns = 0              # Ceguera
        self.turns_survived = 0    # Turnos sobrevividos (para XP)

        # Infraestructura de ICD e Inmunidades de Control
        self.passive_icd = {}
        self.used_erratic_ward = False
        self.used_eternal_watch = False
        self.eternal_watch_trigger_log = None
        self.group_stance = "Normal"  # Postura de grupo: Normal, Defensiva, Ofensiva, Canalizacion

    def execute_pet_raid_ai(self, boss_hp_pct: float, is_boss_fury: bool) -> str:
        """
        Analiza la situación del combate en la Raid y ejecuta la acción automática
        de la mascota equipada en el Slot 'raid'.
        """
        # Buscar la mascota activa en slot 'raid'
        from src.db import db_cursor
        user_id = self.user.id
        with db_cursor() as c:
            c.execute("""
                SELECT p.Name, p.Emoji, p.Family, up.Level, up.Loyalty, up.Nickname
                FROM UserPets up
                JOIN PetsCatalog p ON up.PetID = p.PetID
                WHERE up.UserID = %s AND up.EquippedSlot = 'raid' AND up.Status != 'Escapó'
                LIMIT 1
            """, (user_id,))
            pet_row = c.fetchone()

        if not pet_row:
            return ""

        p_name, p_emoji, family, level, loyalty, nickname = pet_row
        pet_display = nickname if nickname and nickname.strip() else p_name
        hp_pct = (self.hp / self.max_hp) if self.max_hp > 0 else 1.0

        # Nivel escala la potencia (Nv 1 a 15)
        power_mult = 1.0 + ((level - 1) * 0.05)

        # 1. ARQUETIPO GUARDIÁN (Tanque / Protección)
        if family in ["Gólem", "Tortuga", "Guardián", "Piedra"]:
            if hp_pct < 0.40:
                shield_val = int(self.max_hp * 0.15 * power_mult)
                self.shield += shield_val
                return f"🛡️ **[Mascota {p_emoji} {pet_display}]** detectó peligro crítico y activó *Piel de Granito* (Otorgó +{shield_val} de Escudo)."
            elif is_boss_fury:
                self.damage_reduction_turns = 1
                self.damage_reduction_pct = 0.20 * power_mult
                return f"🛡️ **[Mascota {p_emoji} {pet_display}]** usó *Provocación Leal* (-{int(self.damage_reduction_pct*100)}% daño recibido esta ronda)."

        # 2. ARQUETIPO VITALIS / SOPORTE (Curación / Dispel)
        elif family in ["Fénix", "Hada", "Luz", "Sagrado"]:
            if self.poison_turns > 0 or self.bleed_turns > 0 or self.burn_turns > 0:
                self.poison_turns = max(0, self.poison_turns - 1)
                self.bleed_turns = max(0, self.bleed_turns - 1)
                self.burn_turns = max(0, self.burn_turns - 1)
                return f"✨ **[Mascota {p_emoji} {pet_display}]** usó *Purificación Astral* (Disipó 1 estado alterado del jugador)."
            elif hp_pct < 0.60:
                heal_val = int(self.max_hp * 0.12 * power_mult)
                self.hp = min(self.max_hp, self.hp + heal_val)
                return f"💚 **[Mascota {p_emoji} {pet_display}]** usó *Aliento Curativo* (Restauró +{heal_val} HP)."

        # 3. ARQUETIPO DEPREDADOR / DAÑO (Burst)
        elif family in ["Lobo", "Tigre", "Grifo", "Sombra", "Furia"]:
            if is_boss_fury or boss_hp_pct < 0.30:
                bonus_atk = int(self.atk * 0.15 * power_mult)
                self.atk_buff_turns = 1
                self.atk_buff_pct = 0.15 * power_mult
                return f"⚔️ **[Mascota {p_emoji} {pet_display}]** usó *Garra Crítica* en la Fase de Furia (+{int(self.atk_buff_pct*100)}% ATK esta ronda)."

        # 4. ARQUETIPO TÁCTICO / MÍSTICO (Default / Buff)
        crit_bonus = 0.08 * power_mult
        self.subclass_extras["crit_chance_bonus"] = min(0.35, self.subclass_extras.get("crit_chance_bonus", 0.0) + crit_bonus)
        return f"🔮 **[Mascota {p_emoji} {pet_display}]** usó *Ojo Avizor* (+{int(crit_bonus*100)}% Prob. Crítico esta ronda)."

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
