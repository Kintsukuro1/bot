"""
Sistema de Raids PvE Cooperativas — Cog principal.
Combate por turnos de 2-4 jugadores contra un Boss diario.
Solo otorga ítems de equipo como recompensa (no monedas).
"""

from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

from src.db import (
    ensure_user, get_combat_stats, get_user_equipment,
    add_balance, registrar_transaccion, equip_item,
    db_cursor,
)
from src.utils.combat_progression import (
    calc_base_stats, calc_equipment_bonus, get_effective_bonus,
    calc_attack_damage, calc_defend_heal, calc_sell_price,
    generate_loot,
    format_hp_bar, format_stat_type,
    get_combat_rank, get_combat_rank_emoji,
    EQUIPMENT_SLOTS, SLOT_EMOJIS, RARITY_COLORS,
    LOOT_TIMEOUT_SECONDS, ALL_STATS, format_item_stats_display,
    apply_subclass_equipment_conversion,
)
from src.utils.combat_config import SKILLS_CONFIG
from src.utils.subclass_config import (
    SUBCLASSES, SUBCLASS_TO_CLASS, CLASS_SUBCLASSES,
    SUBCLASS_UNLOCK_LEVEL, ULTIMATE_UNLOCK_LEVEL,
    get_subclass_config, get_subclass_skills, get_available_subclasses,
    get_all_subclass_info_for_display,
)
from src.utils.raid_config import (
    RAID_MIN_PLAYERS, RAID_MAX_PLAYERS,
    RAID_LOBBY_TIMEOUT, RAID_TURN_TIMEOUT, RAID_MAX_TURNS,
    RAID_DROP_RATE_VICTORY_ALIVE, RAID_DROP_RATE_VICTORY_DEAD,
    RAID_DROP_RATE_DEFEAT,
    RAID_RARITY_BONUS_VICTORY, RAID_RARITY_MALUS_DEFEAT,
    RAID_XP_BASE_VICTORY, RAID_XP_BASE_DEFEAT,
    RAID_XP_PER_TURN, RAID_XP_ALIVE_BONUS,
    BOSS_SPECIAL_INTERVAL, BOSS_ABILITIES,
    RAID_BOSSES, RAID_AFFIXES,
    get_today_boss, calc_boss_stats, generate_raid_loot,
)
from src.db import update_combat_stats_after_duel


# ══════════════════════════════════════════════
# BOSS EN COMBATE
# ══════════════════════════════════════════════

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


# ══════════════════════════════════════════════
# JUGADOR EN RAID
# ══════════════════════════════════════════════

class RaidCombatant:
    """Estado de un jugador durante la raid."""

    def __init__(self, user: discord.Member, level: int, equipment: dict, combat_class: str = None, combat_subclass: str = None):
        self.user = user
        self.level = level
        self.combat_class = combat_class
        self.combat_subclass = combat_subclass

        # Stats base + equipo
        base = calc_base_stats(level)
        bonus, passives = calc_equipment_bonus(equipment)

        # Aplicar conversión de equipo por subclase (antes del cap)
        bonus, self.subclass_extras = apply_subclass_equipment_conversion(bonus, combat_subclass)

        effective, _, _ = get_effective_bonus(bonus, level)

        self.max_hp = base["hp"] + int(round(effective.get("hp", 0)))
        self.hp = self.max_hp
        self.atk = base["atk"] + int(round(effective.get("atk", 0)))
        self.base_atk = self.atk  # Para restaurar después de debuffs
        self.mag = base["mag"] + int(round(effective.get("mag", 0)))
        self.def_stat = base["def"] + int(round(effective.get("def", 0)))

        # Pasivos de equipo (Legendario)
        self.passives = passives
        self.used_second_wind = False
        self.arcane_shield_active = any(p['id'] == 'arcane_shield' for p in passives)
        self.has_crit_boost = any(p['id'] == 'crit_boost' for p in passives)
        self.has_vampirism = any(p['id'] == 'vampirism' for p in passives)
        self.has_regen = any(p['id'] == 'regen' for p in passives)
        self.has_fury = any(p['id'] == 'fury' for p in passives)
        self.has_dodge = any(p['id'] == 'dodge' for p in passives)
        self.has_parry = any(p['id'] == 'parry' for p in passives)

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
        self.stun_turns = 0                 # Turnos aturdido (Golpe de Escudo, Onda Escarcha)
        self.frozen_turns = 0               # Turnos congelado
        self.silence_turns = 0              # Turnos silenciado
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
        self.retribution_active = False     # Postura de Represalia activa
        self.blinded_turns = 0              # Ceguera
        self.turns_survived = 0    # Turnos sobrevividos (para XP)


# ══════════════════════════════════════════════
# VISTA: LOBBY DE RAID
# ══════════════════════════════════════════════

class RaidLobbyView(discord.ui.View):
    """Vista de sala de espera para que los jugadores se unan antes de iniciar la raid."""

    def __init__(self, creator: discord.Member, boss_config: dict, cog: 'RaidsCog'):
        super().__init__(timeout=RAID_LOBBY_TIMEOUT)
        self.creator = creator
        self.boss_config = boss_config
        self.cog = cog
        self.players: list[discord.Member] = [creator]  # El creador se une automáticamente
        self.player_stats: dict[int, dict] = {}  # user_id -> combat_stats
        self.player_equipments: dict[int, dict] = {}  # user_id -> equipment
        self.difficulty = "normal"
        self.started = False
        self.cancelled = False

    def _build_lobby_embed(self):
        from src.utils.combat_progression import calc_power_level

        boss = self.boss_config
        
        player_powers = {}
        for p in self.players:
            level = self.player_stats.get(p.id, {}).get("level", 1)
            equip = self.player_equipments.get(p.id, {})
            subclass = self.player_stats.get(p.id, {}).get("combat_subclass")
            power = calc_power_level(level, equip, subclass)
            player_powers[p.id] = power

        player_list = "\n".join(
            f"{get_combat_rank_emoji(self.player_stats.get(p.id, {}).get('level', 1))} "
            f"**{p.display_name}** — Nv. {self.player_stats.get(p.id, {}).get('level', 1)} "
            f"(Poder: **{player_powers[p.id]:.1f}**)"
            for p in self.players
        )

        total_power = sum(player_powers[p.id] for p in self.players)
        if boss.get("is_miniboss", False):
            scaled_stats = {
                "hp": boss["hp"],
                "max_hp": boss["hp"],
                "atk": boss["atk"],
                "def_stat": boss["def_stat"],
            }
            stats_label = "**Stats del Miniboss** (Fijos):"
        else:
            scaled_stats = calc_boss_stats(boss, total_power, self.difficulty)
            stats_label = f"**Stats del Boss** (escalado a Poder total {total_power:.1f}):"

        embed = discord.Embed(
            title=f"{boss['emoji']} Raid — {boss['name']} ({self.difficulty.capitalize()})",
            description=(
                f"*{boss['lore']}*\n\n"
                f"**Elemento:** {boss['element']}\n"
                f"**Dificultad:** {self.difficulty.upper()}\n"
                f"**Habilidad Especial:** {BOSS_ABILITIES[boss['ability']]['emoji']} "
                f"{BOSS_ABILITIES[boss['ability']]['name']}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"**Jugadores ({len(self.players)}/{RAID_MAX_PLAYERS}):**\n{player_list}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{stats_label}\n"
                f"❤️ HP: {scaled_stats['hp']:,} · ⚔️ ATK: {scaled_stats['atk']} · 🛡️ DEF: {scaled_stats['def_stat']}"
            ),
            color=boss["color"]
        )
        embed.set_footer(
            text=f"Mínimo {RAID_MIN_PLAYERS} jugadores para iniciar · "
                 f"Solo {self.creator.display_name} puede iniciar · "
                 f"Lobby expira en {RAID_LOBBY_TIMEOUT}s"
        )
        return embed

    @discord.ui.button(label="✅ Unirse a la Raid", style=discord.ButtonStyle.success, row=0)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        if user.id in [p.id for p in self.players]:
            await interaction.response.send_message("❌ Ya estás en la raid.", ephemeral=True)
            return

        if len(self.players) >= RAID_MAX_PLAYERS:
            await interaction.response.send_message("❌ La raid está llena.", ephemeral=True)
            return

        # Verificar que no esté en otra raid
        if user.id in self.cog.active_raids:
            await interaction.response.send_message("❌ Ya tienes una raid en curso.", ephemeral=True)
            return

        # Si la dificultad es mítica, verificar intentos diarios del que se une
        if self.difficulty == "mitica":
            attempts = await asyncio.to_thread(count_mythic_raids_today, user.id)
            if attempts >= 2:
                await interaction.response.send_message("❌ Ya usaste tus 2 intentos de raid Mítica de hoy. Vuelve mañana.", ephemeral=True)
                return

        # Cargar stats y equipo
        await asyncio.to_thread(ensure_user, user.id, user.name)
        stats = await asyncio.to_thread(get_combat_stats, user.id)
        equip = await asyncio.to_thread(get_user_equipment, user.id)
        
        self.player_stats[user.id] = stats
        self.player_equipments[user.id] = equip

        self.players.append(user)
        self.cog.active_raids.add(user.id)

        embed = self._build_lobby_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶️ Iniciar Raid", style=discord.ButtonStyle.primary, row=0)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.creator.id:
            await interaction.response.send_message(
                "❌ Solo el creador de la raid puede iniciarla.", ephemeral=True
            )
            return

        if len(self.players) < RAID_MIN_PLAYERS:
            await interaction.response.send_message(
                f"❌ Se necesitan al menos **{RAID_MIN_PLAYERS}** jugadores para iniciar.",
                ephemeral=True
            )
            return

        # Si es dificultad Mítica, verificar de nuevo a todos los participantes antes de iniciar
        if self.difficulty == "mitica":
            locked_players = []
            for p in self.players:
                attempts = await asyncio.to_thread(count_mythic_raids_today, p.id)
                if attempts >= 2:
                    locked_players.append(p.display_name)
            if locked_players:
                await interaction.response.send_message(
                    f"❌ No se puede iniciar la raid Mítica: los siguientes jugadores ya usaron sus 2 intentos diarios: {', '.join(locked_players)}.",
                    ephemeral=True
                )
                return

        self.started = True
        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title=f"{self.boss_config['emoji']} ¡Raid Iniciando!",
            description="Preparando la arena de combate...",
            color=self.boss_config["color"]
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, row=0)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.creator.id:
            await interaction.response.send_message(
                "❌ Solo el creador puede cancelar la raid.", ephemeral=True
            )
            return

        self.cancelled = True
        for item in self.children:
            item.disabled = True

        # Liberar jugadores
        for p in self.players:
            self.cog.active_raids.discard(p.id)

        embed = discord.Embed(
            title="❌ Raid Cancelada",
            description=f"{self.creator.display_name} ha cancelado la raid.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.select(
        placeholder="Seleccionar Dificultad",
        options=[
            discord.SelectOption(label="Normal", value="normal", description="Escalado estándar", default=True),
            discord.SelectOption(label="Difícil", value="dificil", description="Enemigo +45% HP y +40% ATK/DEF"),
            discord.SelectOption(label="Mítica", value="mitica", description="¡Desafío extremo! Límite de 2 intentos diarios"),
        ],
        row=1
    )
    async def select_difficulty(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.creator.id:
            await interaction.response.send_message("❌ Solo el creador de la raid puede cambiar la dificultad.", ephemeral=True)
            return

        selected_diff = select.values[0]

        # Validar Mítica
        if selected_diff == "mitica":
            # Verificar intentos del creador
            creator_attempts = await asyncio.to_thread(count_mythic_raids_today, self.creator.id)
            if creator_attempts >= 2:
                await interaction.response.send_message("❌ No puedes seleccionar dificultad Mítica: has alcanzado el límite de 2 intentos diarios.", ephemeral=True)
                return
            # Verificar otros jugadores ya en el lobby
            locked_players = []
            for p in self.players:
                if p.id != self.creator.id:
                    attempts = await asyncio.to_thread(count_mythic_raids_today, p.id)
                    if attempts >= 2:
                        locked_players.append(p.display_name)
            if locked_players:
                await interaction.response.send_message(f"❌ No puedes seleccionar dificultad Mítica: los siguientes jugadores ya usaron sus 2 intentos diarios: {', '.join(locked_players)}.", ephemeral=True)
                return

        # Actualizar opciones por defecto
        for opt in select.options:
            opt.default = (opt.value == selected_diff)

        self.difficulty = selected_diff
        embed = self._build_lobby_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if not self.started and not self.cancelled:
            self.cancelled = True
            for p in self.players:
                self.cog.active_raids.discard(p.id)


def get_combatant_available_skills(combatant: RaidCombatant) -> list[tuple[str, dict]]:
    available = []
    for skill_id, skill in SKILLS_CONFIG.items():
        if skill.get("class") is None:
            # ceguera is only for classless
            if combatant.combat_class is None:
                available.append((skill_id, skill))
        else:
            # Class-specific skill
            if combatant.combat_class == skill["class"]:
                req_subclass = skill.get("subclass")
                if req_subclass:
                    # Subclass skill
                    if combatant.combat_subclass == req_subclass and combatant.level >= skill["min_level"]:
                        available.append((skill_id, skill))
                else:
                    # Base class skill
                    if combatant.level >= skill["min_level"]:
                        available.append((skill_id, skill))
    return available


class PersonalSkillSelectView(discord.ui.View):
    """Menú efímero de un solo select para que un jugador elija su habilidad especial en la raid."""

    def __init__(self, raid_view, player, options: list[discord.SelectOption]):
        super().__init__(timeout=60)
        self.raid_view = raid_view
        self.player = player

        # Crear el select dinámicamente con las opciones del jugador
        select = discord.ui.Select(
            placeholder="✨ Seleccionar Habilidad Especial...",
            min_values=1,
            max_values=1,
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        # Deshabilitar el select para evitar dobles clics, pero NO respondemos todavía —
        # esperamos a saber el resultado final para editar una sola vez.
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True

        # 1. Comprobar condiciones (defensa en profundidad)
        if self.raid_view.game_over:
            await interaction.response.edit_message(content="❌ La raid ya terminó.", view=self)
            return

        user_id = self.player.user.id
        if user_id in self.raid_view.actions:
            await interaction.response.edit_message(content="❌ Ya elegiste tu acción.", view=self)
            return

        selected_value = interaction.data["values"][0]
        if selected_value == "none":
            await interaction.response.edit_message(content="❌ No tienes habilidades especiales disponibles.", view=self)
            return

        # 2. Validar cooldown, clase, nivel y subclase
        from src.utils.combat_config import SKILLS_CONFIG
        req = SKILLS_CONFIG.get(selected_value)
        if not req:
            await interaction.response.edit_message(content="❌ Habilidad desconocida.", view=self)
            return

        if req.get("min_level") == 10:
            cd = self.player.skill10_cooldown
        elif req.get("min_level") == 15:
            cd = self.player.skill15_cooldown
        else:
            cd = self.player.special_cooldown

        if cd > 0:
            await interaction.response.edit_message(
                content=f"❌ Habilidad en enfriamiento ({cd} turnos restantes).", view=self
            )
            return

        if req["class"] is not None:
            if self.player.level < req["min_level"] or self.player.combat_class != req["class"]:
                await interaction.response.edit_message(
                    content=f"❌ Solo los **{req['class']}** de nivel **{req['min_level']}+** pueden usar esta habilidad.",
                    view=self
                )
                return

        if req.get("subclass") is not None:
            if self.player.combat_subclass != req["subclass"]:
                await interaction.response.edit_message(
                    content=f"❌ Solo la subclase **{req['subclass']}** puede usar esta habilidad.", view=self
                )
                return

        # 3. Todo válido — editar el mismo mensaje con la confirmación final
        await interaction.response.edit_message(content=f"✅ Habilidad especial registrada: **{req['name']}**", view=self)

        # 4. Registrar la acción
        await self.raid_view._register_action(interaction, selected_value, is_ephemeral=True)


# ══════════════════════════════════════════════
# VISTA: COMBATE DE RAID
# ══════════════════════════════════════════════

class RaidCombatView(discord.ui.View):
    """Vista principal del combate cooperativo contra el boss."""

    def __init__(self, players: list[RaidCombatant], boss: RaidBoss, cog: 'RaidsCog', affix: str = "Ninguno", difficulty: str = "normal"):
        super().__init__(timeout=RAID_TURN_TIMEOUT)
        self.players = players
        self.boss = boss
        self.cog = cog
        self.affix = affix
        self.difficulty = difficulty

        # Acciones elegidas por cada jugador (user_id -> action)
        self.actions: dict[int, str] = {}

        self.turn_count = 0
        self.game_over = False
        self._rewards_done = False
        self.action_log: list[str] = []
        self.interaction_msg = None

        # Nuevos estados de mecánicas dinámicas y estados
        self.minions: list[dict] = []
        self.minions_summoned = False
        self.boss_channeling = False
        self.boss_channeled_damage = 0
        self.boss_channeling_threshold = 0
        self.boss_poison_turns = 0
        self.boss_poison_damage = 0

        # Habilidades especiales se manejan de forma efímera por botón

    def _alive_players(self) -> list[RaidCombatant]:
        """Retorna los jugadores que siguen vivos."""
        return [p for p in self.players if not p.is_dead]

    def _build_embed(self):
        alive = self._alive_players()
        total_alive = len(alive)
        total_players = len(self.players)

        # Afijo activo
        affix_info = RAID_AFFIXES.get(self.affix, {"emoji": "⚪", "desc": "Ninguno"})
        desc = (
            f"**Ronda {self.turn_count + 1}** · "
            f"Jugadores vivos: {total_alive}/{total_players}\n"
            f"**Afijo:** {affix_info['emoji']} **{self.affix}** — *{affix_info['desc']}*\n"
            f"Habilidad especial en: **{BOSS_SPECIAL_INTERVAL - (self.turn_count % BOSS_SPECIAL_INTERVAL)}** turnos"
        )
        if self.boss_channeling:
            desc += f"\n⚠️ **¡{self.boss.name} está canalizando su ataque definitivo!** Daño acumulado: **{self.boss_channeled_damage}/{self.boss_channeling_threshold}**"

        # Boss HP bar
        boss_hp_bar = format_hp_bar(max(0, self.boss.hp), self.boss.max_hp, size=20)

        embed = discord.Embed(
            title=f"{self.boss.emoji} Raid — {self.boss.name}",
            description=desc,
            color=self.boss.color
        )

        # Boss field
        ability_emoji = self.boss.ability["emoji"]
        boss_status = ""
        if self.boss.stun_turns > 0:
            boss_status += f" 💫(Aturdido {self.boss.stun_turns}t)"
        if self.boss.weakness_turns > 0:
            boss_status += f" ❄️(Debil {self.boss.weakness_turns}t)"
        if self.boss.fragility_turns > 0:
            boss_status += f" 💔(Frágil {self.boss.fragility_turns}t)"
        if self.boss.vulnerability_turns > 0:
            boss_status += f" ⚠️(Vulner. {self.boss.vulnerability_turns}t)"
        if self.boss.burn_turns > 0:
            boss_status += f" 🔥(Quemadura {self.boss.burn_turns}t)"
        if self.boss_poison_turns > 0:
            boss_status += f" 🧪(Veneno {self.boss_poison_turns}t)"

        embed.add_field(
            name=f"{self.boss.emoji} {self.boss.name} — Nv. ∞{boss_status}",
            value=(
                f"{boss_hp_bar}\n"
                f"⚔️ {self.boss.atk} ATK · 🛡️ {self.boss.def_stat} DEF\n"
                f"Especial: {ability_emoji} {self.boss.ability['name']}"
            ),
            inline=False
        )

        # Minions field if any are alive
        alive_minions = [m for m in self.minions if m["hp"] > 0]
        if alive_minions:
            minions_lines = []
            for m in alive_minions:
                m_status = ""
                if m.get("stun_turns", 0) > 0:
                    m_status += f" 💫(Aturdido {m['stun_turns']}t)"
                if m.get("weakness_turns", 0) > 0:
                    m_status += f" ❄️(Debil {m['weakness_turns']}t)"
                if m.get("fragility_turns", 0) > 0:
                    m_status += f" 💔(Frágil {m['fragility_turns']}t)"
                if m.get("vulnerability_turns", 0) > 0:
                    m_status += f" ⚠️(Vulner. {m['vulnerability_turns']}t)"
                if m.get("burn_turns", 0) > 0:
                    m_status += f" 🔥(Quemadura {m['burn_turns']}t)"
                minions_lines.append(f"👾 **{m['name']}**{m_status}: {format_hp_bar(m['hp'], m['max_hp'])}")
            embed.add_field(name="👾 Esbirros del Jefe", value="\n".join(minions_lines), inline=False)

        # Player fields
        for p in self.players:
            rank_emoji = get_combat_rank_emoji(p.level)
            status = ""
            if p.is_dead:
                status = " 💀"
                hp_bar = "💀 **CAÍDO**"
            else:
                hp_bar = format_hp_bar(p.hp, p.max_hp)
                if p.poison_turns > 0:
                    status += f" 🧪({p.poison_turns}t)"
                if p.atk_debuff_turns > 0:
                    status += f" ❄️({p.atk_debuff_turns}t)"
                if p.stun_turns > 0:
                    status += f" 💫(Aturdido {p.stun_turns}t)"
                if p.damage_reduction_turns > 0:
                    status += f" 🏰(-{int(p.damage_reduction_pct*100)}% daño {p.damage_reduction_turns}t)"
                if p.atk_buff_turns > 0:
                    status += f" 💪(+{int(p.atk_buff_pct*100)}% ATK {p.atk_buff_turns}t)"
                if p.juicio_final_turns > 0:
                    status += f" ⚖️(Reflejo {p.juicio_final_turns}t)"
                if p.evasion_buff_turns > 0:
                    status += f" 💨(Evasión+ {p.evasion_buff_turns}t)"
                if p.guaranteed_dodge_next:
                    status += " 👻(Esquiva)"
                if p.anti_heal_turns > 0:
                    status += f" 🚫(Anti-cura {p.anti_heal_turns}t)"
                if p.weakness_turns > 0:
                    status += f" ❄️(Debil {p.weakness_turns}t)"
                if p.fragility_turns > 0:
                    status += f" 💔(Frágil {p.fragility_turns}t)"
                if p.vulnerability_turns > 0:
                    status += f" ⚠️(Vulner. {p.vulnerability_turns}t)"
                if p.shield > 0:
                    status += f" 🛡️({p.shield})"
                if p.taunt_turns > 0:
                    status += " 📣(Taunt)"

            # Acción elegida
            action_status = ""
            if not p.is_dead:
                if p.user.id in self.actions:
                    action_status = " · 🟢 ¡Listo!"
                else:
                    action_status = " · 🔴 Eligiendo..."
                
                # Mostrar cooldowns activos
                cds = []
                if p.special_cooldown > 0:
                    cds.append(f"ESP:{p.special_cooldown}t")
                if p.skill10_cooldown > 0:
                    cds.append(f"S10:{p.skill10_cooldown}t")
                if p.skill15_cooldown > 0:
                    cds.append(f"ULT:{p.skill15_cooldown}t")
                if cds:
                    action_status += f" ⏳({', '.join(cds)})"

            # Mostrar subclase si la tiene, sino clase
            if p.combat_subclass:
                class_tag = f" [{p.combat_subclass}]"
            elif p.combat_class:
                class_tag = f" [{p.combat_class}]"
            else:
                class_tag = ""
            embed.add_field(
                name=f"{rank_emoji} {p.user.display_name}{class_tag} (Nv.{p.level}){status}{action_status}",
                value=f"{hp_bar}\n⚔️ {p.atk} ATK · 🛡️ {p.def_stat} DEF",
                inline=True
            )

        # Log
        if self.action_log:
            log_text = "\n".join(self.action_log[-6:])
            embed.add_field(name="📜 Registro", value=log_text, inline=False)

        embed.set_footer(text=f"Acciones: ⚔️ Atacar · 🛡️ Defender · ✨ Habilidad Especial · Tiempo por ronda: {RAID_TURN_TIMEOUT}s")
        return embed

    # ──────────────────── BOTONES ────────────────────

    @discord.ui.button(label="⚔️ Atacar", style=discord.ButtonStyle.danger, row=0)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._register_action(interaction, 'attack')

    @discord.ui.button(label="🛡️ Defender", style=discord.ButtonStyle.primary, row=0)
    async def defend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._register_action(interaction, 'defend')

    @discord.ui.button(label="✨ Habilidad Especial", style=discord.ButtonStyle.secondary, row=1)
    async def special_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over:
            await interaction.response.send_message("❌ La raid ya terminó.", ephemeral=True)
            return

        user_id = interaction.user.id
        player = next((p for p in self.players if p.user.id == user_id), None)
        if player is None:
            await interaction.response.send_message("❌ No participas en esta raid.", ephemeral=True)
            return

        if player.is_dead:
            await interaction.response.send_message("❌ Has caído en combate.", ephemeral=True)
            return

        if player.stun_turns > 0:
            await interaction.response.send_message("❌ Estás aturdido y no puedes actuar este turno.", ephemeral=True)
            return

        if player.silence_turns > 0:
            await interaction.response.send_message("❌ Estás silenciado y no puedes usar habilidades especiales.", ephemeral=True)
            return

        if user_id in self.actions:
            await interaction.response.send_message("❌ Ya elegiste tu acción.", ephemeral=True)
            return

        player_skills = get_combatant_available_skills(player)
        if not player_skills:
            await interaction.response.send_message("❌ No tienes habilidades especiales disponibles.", ephemeral=True)
            return

        options = [
            discord.SelectOption(
                label=f"{skill['name']} (Nvl. {skill['min_level']})",
                value=skill_id,
                emoji=skill['emoji'],
                description=skill['desc'][:100]
            ) for skill_id, skill in player_skills
        ]

        view = PersonalSkillSelectView(raid_view=self, player=player, options=options)
        await interaction.response.send_message("Elige tu habilidad especial:", view=view, ephemeral=True)

    async def _register_action(self, interaction: discord.Interaction, action: str, is_ephemeral: bool = False):
        if self.game_over:
            if is_ephemeral:
                await interaction.followup.send("❌ La raid ya terminó.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ La raid ya terminó.", ephemeral=True)
            return

        user_id = interaction.user.id

        # Verificar que es un participante
        player = next((p for p in self.players if p.user.id == user_id), None)
        if player is None:
            if is_ephemeral:
                await interaction.followup.send("❌ No participas en esta raid.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ No participas en esta raid.", ephemeral=True)
            return

        if player.is_dead:
            if is_ephemeral:
                await interaction.followup.send("❌ Has caído en combate.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Has caído en combate.", ephemeral=True)
            return

        if user_id in self.actions:
            if is_ephemeral:
                await interaction.followup.send("❌ Ya elegiste tu acción.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Ya elegiste tu acción.", ephemeral=True)
            return

        self.actions[user_id] = action

        # ¿Ya todos eligieron?
        alive = self._alive_players()
        all_ready = all(p.user.id in self.actions for p in alive)

        if all_ready:
            if is_ephemeral:
                await self._resolve_round(None)
            else:
                await interaction.response.defer()
                await self._resolve_round(interaction)
        else:
            embed = self._build_embed()
            if is_ephemeral:
                if self.interaction_msg:
                    await self.interaction_msg.edit(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)

    # ──────────────────── RESOLUCIÓN ────────────────────

    async def _resolve_round(self, interaction=None):
        """Resuelve la ronda: acciones de jugadores → IA del boss."""
        logs = [f"🏁 **Ronda {self.turn_count + 1}:**"]
        
        # Configurar intangibilidad para Espíritu Errante (Ronda 2, 4, 6... -> turn_count % 2 == 1)
        if getattr(self.boss, "miniboss_key", None) == "espiritu_errante" and (self.turn_count % 2 == 1):
            self.boss.is_intangible = True
            logs.append("👻 **Espíritu Errante:** ¡El jefe se vuelve intangible este turno! Es inmune a todo el daño.")
        else:
            self.boss.is_intangible = False

        alive = self._alive_players()

        # Helper para aplicar daño a jugadores (con pasivos)
        def apply_damage_to_player(target, raw_dmg, is_boss_attack=False):
            if target.is_dead:
                return

            # Evasión garantizada / paso fantasma / cota de malla / esquiva pasiva
            if is_boss_attack:
                if target.guaranteed_dodge_next:
                    target.guaranteed_dodge_next = False
                    logs.append(f"👥 **Paso Fantasma:** {target.user.display_name} **ESQUIVÓ** el ataque!")
                    return
                if target.evasion_buff_turns > 0 and random.random() < target.evasion_buff_pct:
                    logs.append(f"💨 **Evasión:** ¡{target.user.display_name} esquiva el ataque gracias a su agilidad!")
                    return
                if target.has_dodge and random.random() < 0.05:
                    logs.append(f"💨 **Esquiva:** {target.user.display_name} **ESQUIVÓ** el ataque!")
                    return

            # Amplificación de daño combinada (Frenesí + Vulnerabilidad)
            amp_pct = 0.0
            if target.frenzy_turns > 0:
                amp_pct += SKILLS_CONFIG["frenesi"]["damage_received_boost"]
            if target.vulnerability_turns > 0:
                amp_pct += target.vulnerability_pct
            
            amp_pct = min(0.75, amp_pct)
            raw_dmg = int(raw_dmg * (1.0 + amp_pct))

            # Reducción de daño activa (e.g. Muralla Inquebrantable)
            if target.damage_reduction_turns > 0:
                raw_dmg = int(raw_dmg * (1.0 - target.damage_reduction_pct))
                logs.append(f"🏰 **Mitigación:** Daño recibido reducido a **{raw_dmg}** por Muralla Inquebrantable.")

            # Daño de entrada registrado para Castigo Divino
            target.total_damage_taken += raw_dmg

            # Reflejo (Juicio Final)
            if target.juicio_final_turns > 0 and raw_dmg > 0:
                reflected = int(raw_dmg * target.juicio_final_reflect_pct)
                alive_minions = [m for m in self.minions if m["hp"] > 0]
                if alive_minions:
                    target_minion = alive_minions[0]
                    target_minion["hp"] = max(0, target_minion["hp"] - reflected)
                    logs.append(f"⚖️ **Juicio Final:** ¡Se reflejan **{reflected}** daño de vuelta a {target_minion['name']}!")
                    if target_minion["hp"] <= 0:
                        logs.append(f"💀 **{target_minion['name']}** ha sido destruido por el reflejo!")
                else:
                    self.boss.hp = max(0, self.boss.hp - reflected)
                    logs.append(f"⚖️ **Juicio Final:** ¡Se reflejan **{reflected}** daño de vuelta a {self.boss.name}!")

            absorbed = 0
            if target.shield > 0:
                absorbed = min(target.shield, raw_dmg)
                raw_dmg -= absorbed
                target.shield -= absorbed
                logs.append(f"🛡️ **Escudo:** Se absorbieron **{absorbed}** de daño. Queda {target.shield} de escudo en {target.user.display_name}.")

            # Pasivo: Escudo arcano (primer golpe recibido se reduce a la mitad)
            if is_boss_attack and target.arcane_shield_active:
                raw_dmg = max(1, int(raw_dmg / 2))
                target.arcane_shield_active = False
                logs.append(f"🔮 **Escudo Arcano:** Se redujo el daño a la mitad para {target.user.display_name}.")
            
            if target.is_defending and target.has_parry:
                # No se reduce el daño recibido, pero se cura un 30% del mismo
                parry_heal = max(1, int(raw_dmg * 0.30))
                final_dmg = max(0, raw_dmg - parry_heal)
                target.hp = max(0, target.hp - final_dmg)
                if is_boss_attack:
                    target.last_physical_damage_taken = final_dmg
                logs.append(f"💥 {target.user.display_name} recibe **{final_dmg}** daño (tras curarse **{parry_heal}** por Parada). ({target.hp}/{target.max_hp} HP)")
                
                # Contraatacar al boss o esbirro
                counter_dmg = max(1, int(raw_dmg * 0.75))
                alive_minions = [m for m in self.minions if m["hp"] > 0]
                if alive_minions:
                    target_minion = alive_minions[0]
                    target_minion["hp"] = max(0, target_minion["hp"] - counter_dmg)
                    logs.append(f"⚔️ **Parada:** Contraataca a {target_minion['name']} por **{counter_dmg}** daño.")
                    if target_minion["hp"] <= 0:
                        logs.append(f"💀 **{target_minion['name']}** ha sido destruido!")
                else:
                    self.boss.hp = max(0, self.boss.hp - counter_dmg)
                    logs.append(f"⚔️ **Parada:** Contraataca a {self.boss.name} por **{counter_dmg}** daño.")
            else:
                if target.is_defending:
                    raw_dmg = max(1, int(raw_dmg * 0.4))
                target.hp = max(0, target.hp - raw_dmg)
                if is_boss_attack:
                    target.last_physical_damage_taken = raw_dmg
                logs.append(f"💥 {target.user.display_name} recibe **{raw_dmg}** daño. ({target.hp}/{target.max_hp} HP)")

            if target.hp <= 0:
                # Pasivo: Segundo aliento (sobrevive con 1 HP una vez)
                if not target.used_second_wind and any(p['id'] == 'second_wind' for p in target.passives):
                    target.hp = 1
                    target.used_second_wind = True
                    logs.append(f"💫 **Segundo Aliento:** {target.user.display_name} sobrevive con **1 HP**!")
                    return
                target.is_dead = True
                logs.append(f"💀 **{target.user.display_name}** ha caído en combate!")
                if self.affix == "Sangriento":
                    heal = int(self.boss.max_hp * 0.15)
                    self.boss.hp = min(self.boss.max_hp, self.boss.hp + heal)
                    logs.append(f"🩸 **Sangriento:** {self.boss.name} se cura **{heal}** HP debido a la caída de un jugador.")

        # 1. Aplicar afijo "Niebla Venenosa"
        if self.affix == "Niebla Venenosa":
            logs.append("🧪 **Niebla Venenosa:** La niebla asfixiante daña a todos los jugadores.")
            for p in alive:
                apply_damage_to_player(p, 5)

        # Refrescar vivos
        alive = self._alive_players()
        if not alive:
            self.game_over = True
            logs.append(f"💀 **Todos los jugadores han caído. {self.boss.name} es victorioso.**")
            self.action_log.extend(logs)
            await self._finish_raid(interaction, victory=False)
            return

        # 1.5 HoT Heal (Aura de Salvación) en jugadores
        for p in alive:
            if p.hot_turns > 0:
                if p.anti_heal_turns == 0:
                    hot_heal = int(p.max_hp * p.hot_pct)
                    p.hp = min(p.max_hp, p.hp + hot_heal)
                    logs.append(f"💚 **Aura de Salvación:** {p.user.display_name} se cura **{hot_heal}** HP por efecto gradual.")

        # 2. Aplicar DOTs (veneno y quemadura) a jugadores
        for p in alive:
            if p.poison_turns > 0:
                dmg = min(p.hp, p.poison_damage)
                p.poison_turns -= 1
                if p.poison_turns == 0:
                    p.poison_damage = 0
                logs.append(f"🧪 **Veneno:** {p.user.display_name} sufre **{dmg}** daño por veneno.")
                apply_damage_to_player(p, dmg)

        # Refrescar vivos
        alive = self._alive_players()
        
        for p in alive:
            if p.burn_turns > 0:
                dot_pct = 0.08 if p.enhanced_burn_turns > 0 else 0.05
                b_dmg = min(p.hp, max(1, int(p.max_hp * dot_pct)))
                p.burn_turns -= 1
                logs.append(f"🔥 **Quemadura:** {p.user.display_name} sufre **{b_dmg}** daño por quemadura.")
                apply_damage_to_player(p, b_dmg)

        # Refrescar vivos
        alive = self._alive_players()
        if not alive:
            self.game_over = True
            logs.append(f"💀 **Todos los jugadores han caído. {self.boss.name} es victorioso.**")
            self.action_log.extend(logs)
            await self._finish_raid(interaction, victory=False)
            return

        # 2.2 Aplicar DOT de quemadura al Boss
        if self.boss.burn_turns > 0:
            dot_pct = 0.08 if self.boss.enhanced_burn_turns > 0 else 0.05
            b_dmg = max(1, int(self.boss.max_hp * dot_pct))
            
            # Buscar si hay algún Piromante en la raid para sumar bonus de MAG
            piromantes = [pl for pl in self.players if pl.combat_subclass == "Piromante" and not pl.is_dead]
            if piromantes:
                b_dmg += int(max(pl.mag for pl in piromantes) * 0.15)
                
            self.boss.hp = max(0, self.boss.hp - b_dmg)
            self.boss.burn_turns -= 1
            logs.append(f"🔥 **Quemadura del Boss:** {self.boss.name} sufre **{b_dmg}** daño por quemadura.")
            
            if self.boss.hp <= 0:
                self.game_over = True
                logs.append(f"🎉 **¡{self.boss.name} ha caído por quemaduras!**")
                self.action_log.extend(logs)
                await self._finish_raid(interaction, victory=True)
                return

        # 2.3 Aplicar DOT de quemadura a Esbirros
        alive_minions = [m for m in self.minions if m["hp"] > 0]
        for m in alive_minions:
            if m.get("burn_turns", 0) > 0:
                b_dmg = max(1, int(m["max_hp"] * 0.05))
                m["hp"] = max(0, m["hp"] - b_dmg)
                m["burn_turns"] -= 1
                logs.append(f"🔥 **Quemadura:** {m['name']} sufre **{b_dmg}** daño por quemadura.")
                if m["hp"] <= 0:
                    logs.append(f"💀 **{m['name']}** ha sido destruido por quemaduras!")

        # 2.4 Aplicar DOT de veneno a Esbirros
        alive_minions = [m for m in self.minions if m["hp"] > 0]
        for m in alive_minions:
            if m.get("poison_turns", 0) > 0:
                p_dmg = min(m["hp"], m.get("poison_damage", 10))
                m["hp"] = max(0, m["hp"] - p_dmg)
                m["poison_turns"] -= 1
                if m["poison_turns"] == 0:
                    m["poison_damage"] = 0
                logs.append(f"🧪 **Veneno:** {m['name']} sufre **{p_dmg}** daño por veneno.")
                if m["hp"] <= 0:
                    logs.append(f"💀 **{m['name']}** ha sido destruido por veneno!")

        # Decrementar debuffs en jugadores
        for p in alive:
            if p.atk_debuff_turns > 0:
                p.atk_debuff_turns -= 1
                if p.atk_debuff_turns <= 0:
                    p.atk = p.base_atk  # Restaurar ATK
                    logs.append(f"❄️ El debuff de ATK de {p.user.display_name} ha terminado.")

        # 2.5. Pasivo: Regeneración (+3% HP máximo al inicio de ronda)
        for p in alive:
            if p.has_regen and p.hp < p.max_hp:
                if p.anti_heal_turns == 0:
                    regen_heal = max(1, int(p.max_hp * 0.03))
                    p.hp = min(p.max_hp, p.hp + regen_heal)
                    logs.append(f"💚 **Regeneración:** {p.user.display_name} recupera **{regen_heal}** HP.")

        # 3. Comprobar si esbirros deben aparecer por primera vez (< 50% HP)
        if self.boss.hp < (self.boss.max_hp * 0.5) and not self.minions_summoned:
            self.minions_summoned = True
            self.minions = build_minions_from_pool(self.boss)
            minion_names = ", ".join(f"**{m['name']}**" for m in self.minions)
            logs.append(f"\n👾 **¡El jefe invoca esbirros: {minion_names}!** Los ataques se redirigirán a ellos hasta destruirlos.")

        # 3.1. Acción de Esbirro Debilitador (al inicio de cada turno)
        alive_minions = [m for m in self.minions if m["hp"] > 0]
        for m in alive_minions:
            if m.get("archetype") == "debilitador":
                if m.get("stun_turns", 0) > 0 or m.get("frozen_turns", 0) > 0:
                    logs.append(f"🌀 {m['name']} está incapacitado y no puede debilitar este turno.")
                    continue
                if alive:
                    target_player = random.choice(alive)
                    debuff_type = random.choice(["weakness", "fragility", "ceguera"])
                    if debuff_type == "weakness":
                        target_player.weakness_turns = 2
                        target_player.weakness_pct = 0.25
                        logs.append(f"🌀 **Espectro Debilitante:** Aplica Debilidad (-25% daño infligido) a {target_player.user.display_name} por 2 turnos.")
                    elif debuff_type == "fragility":
                        target_player.fragility_turns = 2
                        target_player.fragility_pct = 0.25
                        logs.append(f"🌀 **Espectro Debilitante:** Aplica Fragilidad (-25% DEF) a {target_player.user.display_name} por 2 turnos.")
                    elif debuff_type == "ceguera":
                        target_player.blinded_turns = 2
                        logs.append(f"🌀 **Espectro Debilitante:** Aplica Ceguera (50% probabilidad de fallo) a {target_player.user.display_name} por 2 turnos.")

        # 4. Procesar acciones de jugadores
        total_damage_dealt_this_turn = 0

        for p in alive:
            action = self.actions.get(p.user.id, 'timeout')
            damage = 0
            is_magic = False
            crit = False

            # Resolver el objetivo activo
            alive_minions = [m for m in self.minions if m["hp"] > 0]
            if alive_minions:
                active_target = alive_minions[0]
            else:
                active_target = self.boss

            # Verificación de ceguera (50% de probabilidad de fallo)
            if p.blinded_turns > 0 and action != "defend" and action != "timeout":
                if random.random() < 0.5:
                    logs.append(f"👁️ **Ceguera:** ¡{p.user.display_name} está cegado y falla su acción!")
                    continue

            if action == 'attack':
                # Ataque normal (daño físico)
                effective_atk = p.atk
                if p.atk_buff_turns > 0:
                    effective_atk = int(effective_atk * (1.0 + p.atk_buff_pct))
                if p.weakness_turns > 0:
                    effective_atk = int(effective_atk * (1.0 - p.weakness_pct))

                base_dmg = effective_atk * random.uniform(0.85, 1.15)
                
                # Obtener la defensa del objetivo y aplicar Fragilidad si tiene
                target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                    target_def = int(target_def * (1.0 - active_target.fragility_pct))
                elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                    target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))

                damage = max(1, int(base_dmg - target_def * 0.35))

                # Crítico 10% (o más con crit_boost y crit_chance_bonus de Duelista)
                crit_chance = 0.10
                if p.has_crit_boost:
                    crit_chance += 0.10
                crit_chance += p.subclass_extras.get("crit_chance_bonus", 0.0)
                
                crit = random.random() < crit_chance
                if crit:
                    crit_mult = 1.5 + p.subclass_extras.get("crit_mult_bonus", 0.0)
                    damage = int(damage * crit_mult)
                    crit_text = " **¡CRÍTICO BRUTAL!**" if p.subclass_extras.get("crit_mult_bonus", 0.0) > 0 else " **¡CRÍTICO!**"
                else:
                    crit_text = ""

            elif action == 'defend':
                p.is_defending = True
                
                # Taunt pasivo al Defender
                has_taunt_subclass = p.combat_subclass in ["Centinela", "Guardián Sagrado", "Guardián de la Fe"]
                if has_taunt_subclass and p.taunt_cooldown == 0:
                    p.taunt_cooldown = 4 if p.combat_subclass == "Guardián de la Fe" else 3
                    p.taunt_turns = 3  # Dura 2 turnos activos
                    if p.combat_subclass == "Guardián Sagrado":
                        shield_amt = int(p.max_hp * 0.05)
                        p.shield += shield_amt
                        logs.append(f"🛡️ **Taunt Pasivo:** {p.user.display_name} activa Taunt y obtiene un escudo de **{shield_amt}** HP.")
                    else:
                        logs.append(f"🛡️ **Taunt Pasivo:** {p.user.display_name} activa Taunt!")

                # Curación de defensa
                if not p.has_parry:
                    heal = calc_defend_heal(p.max_hp)
                    if p.anti_heal_turns == 0:
                        p.hp = min(p.max_hp, p.hp + heal)
                        logs.append(f"🛡️ {p.user.display_name} se defiende y recupera **{heal}** HP.")
                    else:
                        logs.append(f"🛡️ {p.user.display_name} se defiende pero no puede curarse debido a la anti-curación.")
                else:
                    logs.append(f"🛡️ {p.user.display_name} se prepara para parar y contraatacar.")

            elif action == 'timeout':
                logs.append(f"⏰ {p.user.display_name} no respondió a tiempo.")

            else:
                # Es un lanzamiento de habilidad especial
                cfg = SKILLS_CONFIG.get(action)
                if cfg:
                    # Aplicar enfriamiento
                    skill_cd = cfg.get("cooldown", 3)
                    has_mana_residual = any(pass_item['id'] == 'mana_residual' for pass_item in p.passives)
                    if has_mana_residual:
                        skill_cd = max(1, skill_cd - 1)

                    if cfg.get("min_level") == 10:
                        p.skill10_cooldown = skill_cd
                    elif cfg.get("min_level") == 15:
                        p.skill15_cooldown = skill_cd
                    else:
                        p.special_cooldown = skill_cd

                    # Procesar cada habilidad específica
                    if action == "ceguera":
                        if hasattr(active_target, 'blinded_turns'):
                            active_target.blinded_turns = cfg["turns"] + 1
                        else:
                            active_target["blinded_turns"] = cfg["turns"] + 1
                        logs.append(f"👁️ **Tierra a los ojos:** {p.user.display_name} lanza tierra a los ojos de {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                    
                    elif action == "frenesi":
                        p.frenzy_turns = cfg["turns"] + 1
                        logs.append(f"⚔️ **Frenesí de Batalla:** {p.user.display_name} entra en Frenesí (+ATK, -DEF)!")
                    
                    elif action == "represalia":
                        p.retribution_active = True
                        logs.append(f"🛡️ **Postura de Represalia:** {p.user.display_name} adopta la Postura de Represalia!")
                    
                    elif action == "veneno":
                        raw_dmg = int(p.atk * cfg["damage_mult"])
                        if p.atk_buff_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                        
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        
                        if hasattr(active_target, 'poison_turns'):
                            if self.boss_poison_turns == 0:
                                self.boss_poison_damage = 10
                            else:
                                self.boss_poison_damage = min(30, self.boss_poison_damage + 10)
                            self.boss_poison_turns = cfg["turns"] + 1
                        else:
                            if active_target.get("poison_turns", 0) == 0:
                                active_target["poison_damage"] = 10
                            else:
                                active_target["poison_damage"] = min(30, active_target.get("poison_damage", 0) + 10)
                            active_target["poison_turns"] = cfg["turns"] + 1
                        logs.append(f"🧪 **Daga Envenenada:** {p.user.display_name} usa Daga Envenenada e inflige veneno a {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                    
                    elif action == "quemadura":
                        raw_dmg = int(p.mag * cfg["damage_mult"])
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        is_magic = True
                        
                        if hasattr(active_target, 'burn_turns'):
                            self.boss.burn_turns = cfg["turns"] + 1
                        else:
                            active_target["burn_turns"] = cfg["turns"] + 1
                        logs.append(f"🔥 **Tormenta de Fuego:** {p.user.display_name} usa Tormenta de Fuego y quema a {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                    
                    elif action == "drenaje":
                        drain_pct = cfg["drain_pct"] + p.subclass_extras.get("extra_drain_pct", 0.0)
                        target_hp = active_target.hp if hasattr(active_target, 'hp') else active_target["hp"]
                        steal_amt = max(1, int(target_hp * drain_pct))
                        
                        if hasattr(active_target, 'hp'):
                            active_target.hp = max(0, active_target.hp - steal_amt)
                            if self.boss_channeling:
                                self.boss_channeled_damage += steal_amt
                            total_damage_dealt_this_turn += steal_amt
                        else:
                            active_target["hp"] = max(0, active_target["hp"] - steal_amt)
                            if active_target["hp"] <= 0:
                                logs.append(f"💀 **{active_target['name']}** ha sido destruido!")
                                
                        if p.anti_heal_turns == 0:
                            heal_amt = min(p.max_hp - p.hp, steal_amt)
                            p.hp += heal_amt
                            logs.append(f"⚕️ **Drenaje Sagrado:** {p.user.display_name} drena **{steal_amt}** HP y se cura **{heal_amt}** HP.")
                        else:
                            logs.append(f"⚕️ **Drenaje Sagrado:** {p.user.display_name} drena **{steal_amt}** HP, pero no puede curarse.")
                            
                        # Limpiar debuffs propios
                        p.poison_turns = 0
                        p.atk_debuff_turns = 0
                        p.atk = p.base_atk
                        p.stun_turns = 0
                        p.weakness_turns = 0
                        p.fragility_turns = 0
                        p.vulnerability_turns = 0
                        p.anti_heal_turns = 0
                        
                    # Habilidades de Subclase Nivel 10 / 15
                    elif action == "golpe_escudo":
                        raw_dmg = int(p.atk * cfg["damage_mult"])
                        if p.atk_buff_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                        
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        
                        if hasattr(active_target, 'stun_turns'):
                            if active_target.frozen_turns > 0:
                                active_target.frozen_turns += 1
                            else:
                                active_target.stun_turns = cfg["stun_turns"] + 1
                        else:
                            if active_target.get("frozen_turns", 0) > 0:
                                active_target["frozen_turns"] += 1
                            else:
                                active_target["stun_turns"] = cfg["stun_turns"] + 1
                        logs.append(f"🛡️ **Golpe de Escudo:** {p.user.display_name} aturde a {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                    
                    elif action == "muralla_inquebrantable":
                        logs.append(f"🏰 **Muralla Inquebrantable:** ¡{p.user.display_name} protege a todo el grupo, reduciendo el daño recibido un 50%!")
                        for target_p in alive:
                            target_p.damage_reduction_turns = cfg["duration"] + 1
                            target_p.damage_reduction_pct = cfg["damage_reduction_pct"]
                        damage = 0
                    
                    elif action == "golpe_desesperado":
                        raw_dmg = int(p.atk * cfg["base_damage_mult"])
                        if p.atk_buff_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                        
                        hp_ratio = p.hp / p.max_hp
                        hp_mult = 1.0 / max(0.01, hp_ratio)
                        raw_dmg = int(raw_dmg * hp_mult)
                        
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        logs.append(f"💢 **Golpe Desesperado:** {p.user.display_name} causa daño desesperado (HP mult: {hp_mult:.2f}x)!")
                    
                    elif action == "sed_sangre":
                        sacrifice = int(p.hp * cfg["hp_sacrifice_pct"])
                        p.hp = max(1, p.hp - sacrifice)
                        p.atk_buff_turns = cfg["buff_duration"] + 1
                        p.atk_buff_pct = cfg["atk_buff_pct"]
                        logs.append(f"🩸 **Sed de Sangre:** {p.user.display_name} sacrifica **{sacrifice}** HP a cambio de +60% ATK por 3 turnos!")
                        damage = 0
                    
                    elif action == "estocada_precisa":
                        raw_dmg = int(p.atk * cfg["damage_mult"])
                        if p.atk_buff_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                        raw_dmg = int(raw_dmg * 1.5)  # Crítico garantizado
                        
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        logs.append(f"🎯 **Estocada Precisa:** {p.user.display_name} asesta un crítico directo!")
                    
                    elif action == "ejecucion":
                        raw_dmg = int(p.atk * cfg["damage_mult"])
                        if p.atk_buff_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                        
                        target_hp = active_target.hp if hasattr(active_target, 'hp') else active_target["hp"]
                        target_max = active_target.max_hp if hasattr(active_target, 'max_hp') else active_target["max_hp"]
                        is_low = (target_hp / target_max) < cfg["execute_threshold_pct"]
                        if is_low:
                            raw_dmg = int(raw_dmg * cfg["execute_bonus_mult"])
                            detail = " **(¡Ejecución!)**"
                        else:
                            detail = ""
                            
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        logs.append(f"⚔️ **Ejecución:** {p.user.display_name} causa daño físico{detail}!")
                    
                    elif action == "escudo_compartido":
                        target_p = min(alive, key=lambda x: x.hp / x.max_hp)
                        shield_val = int(p.max_hp * cfg["shield_pct_of_max_hp"])
                        target_p.shield += shield_val
                        logs.append(f"🛡️ **Escudo Compartido:** {p.user.display_name} otorga un escudo de **{shield_val}** HP a {target_p.user.display_name}.")
                        damage = 0
                    
                    elif action == "aura_salvacion":
                        logs.append(f"💛 **Aura de Salvación:** {p.user.display_name} desata un aura protectora y curativa para todo el grupo!")
                        for target_p in alive:
                            target_p.shield += int(p.max_hp * cfg["shield_pct"])
                            target_p.hot_turns = cfg["duration"] + 1
                            target_p.hot_pct = cfg["hot_pct"]
                        damage = 0
                    
                    elif action == "castigo_divino":
                        raw_dmg = int(p.atk * cfg["base_damage_mult"]) + int(p.total_damage_taken * cfg["scaling_factor"])
                        if p.atk_buff_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                            
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        logs.append(f"⚡ **Castigo Divino:** {p.user.display_name} causa **{damage}** daño (daño acumulado: +{int(p.total_damage_taken * cfg['scaling_factor'])}).")
                    
                    elif action == "juicio_final":
                        p.juicio_final_turns = cfg["duration"] + 1
                        p.juicio_final_reflect_pct = cfg["reflect_pct"]
                        logs.append(f"⚖️ **Juicio Final:** {p.user.display_name} reflejará el 150% del daño recibido por 2 turnos.")
                        damage = 0
                    
                    elif action == "estandarte_guerra":
                        logs.append(f"🚩 **Estandarte de Guerra:** ¡{p.user.display_name} coloca un estandarte de guerra que aumenta el ATK de todo el grupo en 20% por 3 turnos!")
                        for target_p in alive:
                            target_p.atk_buff_turns = cfg["duration"] + 1
                            target_p.atk_buff_pct = cfg["atk_buff_pct"]
                        damage = 0
                    
                    elif action == "carga_sagrada":
                        logs.append(f"⚔️ **Carga Sagrada:** ¡Todo el grupo realiza una carga ofensiva de ataques físicos!")
                        for ally in alive:
                            ally_atk = ally.atk
                            if ally.atk_buff_turns > 0:
                                ally_atk = int(ally_atk * (1.0 + ally.atk_buff_pct))
                            if ally.weakness_turns > 0:
                                ally_atk = int(ally_atk * (1.0 - ally.weakness_pct))
                            
                            base_dmg = ally_atk * random.uniform(0.85, 1.15)
                            target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                            if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                                target_def = int(target_def * (1.0 - active_target.fragility_pct))
                            elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                                target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                                
                            dmg = max(1, int(base_dmg - target_def * 0.35))
                            
                            # Modificador afijo
                            if self.affix == "Inestabilidad Mágica":
                                dmg = int(dmg * 0.7)
                                
                            if hasattr(active_target, 'hp'):
                                active_target.hp = max(0, active_target.hp - dmg)
                                total_damage_dealt_this_turn += dmg
                                if self.boss_channeling:
                                    self.boss_channeled_damage += dmg
                            else:
                                active_target["hp"] = max(0, active_target["hp"] - dmg)
                                if active_target["hp"] <= 0:
                                    logs.append(f"💀 **{active_target['name']}** ha sido destruido!")
                            logs.append(f"   → {ally.user.display_name} ataca por **{dmg}** daño.")
                        damage = 0
                        
                    elif action == "golpe_sombras":
                        raw_dmg = int(p.atk * cfg["damage_mult"])
                        if p.atk_buff_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                        
                        # Daño doble si está envenenado
                        is_poisoned = False
                        if hasattr(active_target, 'hp'):
                            is_poisoned = (self.boss_poison_turns > 0)
                        else:
                            is_poisoned = (active_target.get("poison_turns", 0) > 0)
                            
                        if is_poisoned:
                            raw_dmg = int(raw_dmg * 2.0)
                            detail = " **(¡Daño Duplicado por Veneno!)**"
                        else:
                            detail = ""
                            
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        logs.append(f"🗡️ **Golpe en las Sombras:** {p.user.display_name} causa **{damage}** daño{detail}!")
                    
                    elif action == "ejecucion_sombria":
                        raw_dmg = int(p.atk * cfg["damage_mult"])
                        if p.atk_buff_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                        
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        
                        extra_crit = 0.10 if p.has_crit_boost else 0.0
                        extra_crit += p.subclass_extras.get("crit_chance_bonus", 0.0)
                        crit = random.random() < (0.10 + extra_crit)
                        if crit:
                            crit_mult = 1.5 + p.subclass_extras.get("crit_mult_bonus", 0.0)
                            damage = int(damage * crit_mult)
                            logs.append(f"💀 **Ejecución Sombría:** ¡Crítico brutal! **{damage}** daño a {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                        else:
                            logs.append(f"💀 **Ejecución Sombría:** {p.user.display_name} causa **{damage}** daño.")
                    
                    elif action == "paso_fantasma":
                        p.guaranteed_dodge_next = True
                        p.taunt_turns = 0
                        logs.append(f"👥 **Paso Fantasma:** {p.user.display_name} se desvanece y esquivará el próximo golpe.")
                        damage = 0
                    
                    elif action == "danza_cuchillas":
                        total_dmg = 0
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        for _ in range(cfg["hits"]):
                            raw_dmg = int(p.atk * cfg["damage_mult_per_hit"])
                            if p.atk_buff_turns > 0:
                                raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                            if p.weakness_turns > 0:
                                raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                            total_dmg += max(1, raw_dmg - int(target_def * cfg["def_mitigation_factor"]))
                        
                        p.evasion_buff_turns = cfg["evasion_buff_duration"] + 1
                        p.evasion_buff_pct = cfg["evasion_buff_pct"]
                        damage = total_dmg
                        logs.append(f"💃 **Danza de Cuchillas:** {p.user.display_name} ataca 3 veces causando **{damage}** daño y aumenta su Evasión.")
                    
                    elif action == "trampa_aconito":
                        raw_dmg = int(p.atk * cfg["damage_mult"])
                        if p.atk_buff_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                        
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        
                        if hasattr(active_target, 'weakness_turns'):
                            active_target.weakness_turns = cfg["debuff_duration"] + 1
                            active_target.weakness_pct = cfg["debuff_value"]
                        else:
                            active_target["weakness_turns"] = cfg["debuff_duration"] + 1
                            active_target["weakness_pct"] = cfg["debuff_value"]
                        logs.append(f"🕸️ **Trampa de Acónito:** {p.user.display_name} causa **{damage}** daño y debilita a {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                    
                    elif action == "enjambre_trampas":
                        raw_dmg = int(p.atk * cfg["damage_mult"])
                        if p.atk_buff_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            raw_dmg = int(raw_dmg * (1.0 - p.weakness_pct))
                        
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        
                        # Aplicar debuffs
                        if hasattr(active_target, 'weakness_turns'):
                            active_target.weakness_turns = 4
                            active_target.weakness_pct = 0.20
                            active_target.fragility_turns = 4
                            active_target.fragility_pct = 0.20
                            if self.boss_poison_turns == 0:
                                self.boss_poison_damage = 10
                            else:
                                self.boss_poison_damage = min(30, self.boss_poison_damage + 10)
                            self.boss_poison_turns = 4
                        else:
                            active_target["weakness_turns"] = 4
                            active_target["weakness_pct"] = 0.20
                            active_target["fragility_turns"] = 4
                            active_target["fragility_pct"] = 0.20
                            if active_target.get("poison_turns", 0) == 0:
                                active_target["poison_damage"] = 10
                            else:
                                active_target["poison_damage"] = min(30, active_target.get("poison_damage", 0) + 10)
                            active_target["poison_turns"] = 4
                        logs.append(f"🕸️ **Enjambre de Trampas:** {p.user.display_name} causa **{damage}** daño e inflige Veneno, Debilidad y Fragilidad a {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                    
                    elif action == "llamarada":
                        logs.append(f"🔥 **Llamarada:** ¡{p.user.display_name} lanza fuego en área a los enemigos!")
                        is_magic = True
                        all_enemies = [self.boss] + [m for m in self.minions if m["hp"] > 0]
                        for enemy in all_enemies:
                            raw_dmg = int(p.mag * cfg["damage_mult"])
                            enemy_def = enemy.def_stat if hasattr(enemy, 'def_stat') else enemy.get("def_stat", 10)
                            if hasattr(enemy, 'fragility_turns') and enemy.fragility_turns > 0:
                                enemy_def = int(enemy_def * (1.0 - enemy.fragility_pct))
                            elif isinstance(enemy, dict) and enemy.get("fragility_turns", 0) > 0:
                                enemy_def = int(enemy_def * (1.0 - enemy.get("fragility_pct", 0.0)))
                                
                            dmg = max(1, raw_dmg - int(enemy_def * cfg["def_mitigation_factor"]))
                            
                            # Modificador afijo
                            if self.affix == "Inestabilidad Mágica":
                                dmg = int(dmg * 1.4)
                                
                            if hasattr(enemy, 'hp'):
                                enemy.hp = max(0, enemy.hp - dmg)
                                total_damage_dealt_this_turn += dmg
                                if self.boss_channeling:
                                    self.boss_channeled_damage += dmg
                                enemy.burn_turns = cfg["burn_duration"] + 1
                            else:
                                if isinstance(enemy, dict) and enemy.get("archetype") == "escudo":
                                    dmg = max(1, int(dmg * 0.5))
                                    logs.append(f"   🛡️ **Guardián de Escudo:** ¡{enemy['name']} reduce el daño recibido un 50%!")
                                enemy["hp"] = max(0, enemy["hp"] - dmg)
                                if enemy["hp"] <= 0:
                                    logs.append(f"💀 **{enemy['name']}** ha sido destruido!")
                                enemy["burn_turns"] = cfg["burn_duration"] + 1
                            logs.append(f"   → {enemy.name if hasattr(enemy, 'name') else enemy['name']}: **{dmg}** daño + Quemadura.")
                        damage = 0
                        
                    elif action == "cataclismo_fuego":
                        raw_dmg = int(p.mag * cfg["damage_mult"])
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        is_magic = True
                        
                        if hasattr(active_target, 'burn_turns'):
                            active_target.burn_turns = cfg["burn_duration"] + 1
                            active_target.enhanced_burn_turns = cfg["burn_duration"] + 1
                        else:
                            active_target["burn_turns"] = cfg["burn_duration"] + 1
                            active_target["enhanced_burn_turns"] = cfg["burn_duration"] + 1
                        logs.append(f"☄️ **Cataclismo de Fuego:** {p.user.display_name} causa **{damage}** daño e inflige Quemadura Reforzada a {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                    
                    elif action == "onda_escarcha":
                        raw_dmg = int(p.mag * cfg["damage_mult"])
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        is_magic = True
                        
                        if hasattr(active_target, 'stun_turns'):
                            if active_target.stun_turns > 0:
                                active_target.stun_turns += 1
                            else:
                                active_target.frozen_turns = cfg["freeze_turns"] + 1
                        else:
                            if active_target.get("stun_turns", 0) > 0:
                                active_target["stun_turns"] += 1
                            else:
                                active_target["frozen_turns"] = cfg["freeze_turns"] + 1
                        logs.append(f"❄️ **Onda de Escarcha:** {p.user.display_name} causa **{damage}** daño y congela a {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                    
                    elif action == "tormenta_elemental":
                        raw_dmg = int(p.mag * cfg["damage_mult"])
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        is_magic = True
                        
                        if hasattr(active_target, 'burn_turns'):
                            active_target.burn_turns = cfg["burn_duration"] + 1
                            if active_target.stun_turns > 0:
                                active_target.stun_turns += 1
                            else:
                                active_target.frozen_turns = cfg["freeze_turns"] + 1
                        else:
                            active_target["burn_turns"] = cfg["burn_duration"] + 1
                            if active_target.get("stun_turns", 0) > 0:
                                active_target["stun_turns"] += 1
                            else:
                                active_target["frozen_turns"] = cfg["freeze_turns"] + 1
                        logs.append(f"🌪️ **Tormenta Elemental:** {p.user.display_name} causa **{damage}** daño, quema y congela a {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                    
                    elif action == "sobrecarga_arcana":
                        raw_dmg = int(p.mag * cfg["damage_mult"])
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        is_magic = True
                        
                        self_dmg = int(p.hp * cfg["self_damage_pct"])
                        p.hp = max(1, p.hp - self_dmg)
                        logs.append(f"💥 **Sobrecarga Arcana:** {p.user.display_name} causa **{damage}** daño y sufre **{self_dmg}** HP autodaño.")
                    
                    elif action == "singularidad":
                        raw_dmg = int(p.mag * cfg["damage_mult"])
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))
                            
                        def_mitig = int(target_def * cfg["def_mitigation_factor"])
                        damage = max(1, raw_dmg - def_mitig)
                        is_magic = True
                        
                        self_dmg = int(p.hp * cfg["self_damage_pct"])
                        p.hp = max(1, p.hp - self_dmg)
                        p.vulnerability_turns = cfg["vulnerability_after_turns"] + 1
                        p.vulnerability_pct = cfg["vulnerability_pct"]
                        logs.append(f"🌌 **Singularidad:** {p.user.display_name} causa **{damage}** daño, sufre **{self_dmg}** HP autodaño y se vuelve vulnerable.")
                    
                    elif action == "luz_curativa":
                        target_p = min(alive, key=lambda x: x.hp / x.max_hp)
                        if target_p.anti_heal_turns > 0:
                            logs.append(f"🚫 **Luz Curativa:** {p.user.display_name} intenta curar a {target_p.user.display_name}, pero tiene anti-cura.")
                        else:
                            heal_val = int(target_p.max_hp * cfg["heal_pct_of_max_hp"]) + p.subclass_extras.get("heal_power", 0)
                            target_p.hp = min(target_p.max_hp, target_p.hp + heal_val)
                            logs.append(f"💚 **Luz Curativa:** {p.user.display_name} cura a {target_p.user.display_name} por **{heal_val}** HP.")
                        damage = 0
                    
                    elif action == "resurreccion_parcial":
                        dead_players = [pl for pl in self.players if pl.is_dead]
                        if dead_players:
                            target_dead = dead_players[0]
                            target_dead.is_dead = False
                            revive_amt = int(target_dead.max_hp * cfg["revive_hp_pct"]) + p.subclass_extras.get("heal_power", 0)
                            target_dead.hp = revive_amt
                            logs.append(f"✝️ **Resurrección Parcial:** ¡{p.user.display_name} revive a {target_dead.user.display_name} con **{revive_amt}** HP!")
                        else:
                            if p.anti_heal_turns > 0:
                                logs.append(f"🚫 **Resurrección Parcial:** {p.user.display_name} se intentó curar, pero tiene anti-cura.")
                            else:
                                heal_val = int(p.max_hp * cfg["self_heal_in_duel_pct"]) + p.subclass_extras.get("heal_power", 0)
                                p.hp = min(p.max_hp, p.hp + heal_val)
                                logs.append(f"✝️ **Resurrección Parcial:** No hay aliados caídos. ¡{p.user.display_name} se cura **{heal_val}** HP!")
                        damage = 0
                    
                    elif action == "pacto_sangre":
                        drain_pct = cfg["drain_pct"] + p.subclass_extras.get("extra_drain_pct", 0.0)
                        target_hp = active_target.hp if hasattr(active_target, 'hp') else active_target["hp"]
                        steal_amt = max(1, int(target_hp * drain_pct))
                        
                        if hasattr(active_target, 'hp'):
                            active_target.hp = max(0, active_target.hp - steal_amt)
                            if self.boss_channeling:
                                self.boss_channeled_damage += steal_amt
                            total_damage_dealt_this_turn += steal_amt
                        else:
                            active_target["hp"] = max(0, active_target["hp"] - steal_amt)
                            if active_target["hp"] <= 0:
                                logs.append(f"💀 **{active_target['name']}** ha sido destruido!")
                                
                        if p.anti_heal_turns == 0:
                            heal_amt = min(p.max_hp - p.hp, steal_amt)
                            p.hp += heal_amt
                            logs.append(f"🖤 **Pacto de Sangre:** {p.user.display_name} drena **{steal_amt}** HP de {active_target.name if hasattr(active_target, 'name') else active_target['name']} y se cura **{heal_amt}** HP.")
                        else:
                            logs.append(f"🖤 **Pacto de Sangre:** {p.user.display_name} drena **{steal_amt}** HP, pero no puede curarse.")
                            
                        if hasattr(active_target, 'anti_heal_turns'):
                            active_target.anti_heal_turns = cfg["anti_heal_duration"] + 1
                        else:
                            active_target["anti_heal_turns"] = cfg["anti_heal_duration"] + 1
                        damage = 0
                    
                    elif action == "consumir_alma":
                        target_hp = active_target.hp if hasattr(active_target, 'hp') else active_target["hp"]
                        target_max = active_target.max_hp if hasattr(active_target, 'max_hp') else active_target["max_hp"]
                        is_low = (target_hp / target_max) < cfg["execute_threshold_pct"]
                        drain_pct = cfg["execute_drain_pct"] if is_low else cfg["base_drain_pct"]
                        drain_pct += p.subclass_extras.get("extra_drain_pct", 0.0)
                        steal_amt = max(1, int(target_hp * drain_pct))
                        
                        if hasattr(active_target, 'hp'):
                            active_target.hp = max(0, active_target.hp - steal_amt)
                            if self.boss_channeling:
                                self.boss_channeled_damage += steal_amt
                            total_damage_dealt_this_turn += steal_amt
                        else:
                            active_target["hp"] = max(0, active_target["hp"] - steal_amt)
                            if active_target["hp"] <= 0:
                                logs.append(f"💀 **{active_target['name']}** ha sido destruido!")
                                
                        if p.anti_heal_turns == 0:
                            heal_amt = min(p.max_hp - p.hp, steal_amt)
                            p.hp += heal_amt
                            detail = " **(¡Ejecución!)**" if is_low else ""
                            logs.append(f"👁️ **Consumir Alma:** {p.user.display_name} drena **{steal_amt}** HP de {active_target.name if hasattr(active_target, 'name') else active_target['name']}{detail} y se cura **{heal_amt}** HP.")
                        else:
                            detail = " **(¡Ejecución!)**" if is_low else ""
                            logs.append(f"👁️ **Consumir Alma:** {p.user.display_name} drena **{steal_amt}** HP de {active_target.name if hasattr(active_target, 'name') else active_target['name']}{detail}, pero no puede curarse.")
                        damage = 0
                    
                    elif action == "bendicion_hierro":
                        target_p = min(alive, key=lambda x: x.hp / x.max_hp)
                        shield_val = int(p.max_hp * cfg["shield_pct_of_max_hp"])
                        target_p.shield += shield_val
                        logs.append(f"🛡️ **Bendición de Hierro:** {p.user.display_name} otorga un escudo de **{shield_val}** HP a {target_p.user.display_name}.")
                        damage = 0
                    
                    elif action == "santuario":
                        logs.append(f"🏛️ **Santuario:** ¡{p.user.display_name} purifica a todo el grupo y les otorga un escudo!")
                        for target_p in alive:
                            target_p.shield += int(p.max_hp * cfg["shield_pct"])
                            target_p.poison_turns = 0
                            target_p.atk_debuff_turns = 0
                            target_p.atk = target_p.base_atk
                            target_p.stun_turns = 0
                            target_p.weakness_turns = 0
                            target_p.fragility_turns = 0
                            target_p.vulnerability_turns = 0
                            target_p.anti_heal_turns = 0
                        damage = 0

            # Pasivo: Furia creciente (+10% daño cuando HP < 30%)
            if p.has_fury and (p.hp / p.max_hp) < 0.30 and damage > 0:
                damage = int(damage * 1.10)
                logs.append(f"🔥 **Furia Creciente:** ¡{p.user.display_name} inflige un 10% más de daño!")

            # Aplicar modificadores de afijo "Inestabilidad Mágica" y Vulnerability combinados
            if damage > 0:
                amp_pct = 0.0
                if is_magic and self.affix == "Inestabilidad Mágica":
                    amp_pct += 0.40
                    logs.append("🌀 **Inestabilidad Mágica:** Daño mágico aumentado un 40% (base).")
                
                # Check target vulnerability
                active_target = alive_minions[0] if alive_minions else self.boss
                if isinstance(active_target, dict):
                    if active_target.get("vulnerability_turns", 0) > 0:
                        amp_pct += active_target.get("vulnerability_pct", 0.0)
                else:
                    if active_target.vulnerability_turns > 0:
                        amp_pct += active_target.vulnerability_pct
                
                amp_pct = min(0.75, amp_pct)
                damage = int(damage * (1.0 + amp_pct))
                
                if not is_magic and self.affix == "Inestabilidad Mágica":
                    damage = int(damage * 0.7)
                    logs.append("🌀 **Inestabilidad Mágica:** Daño físico reducido un 30%.")

                # Redirigir a esbirros si están activos
                if alive_minions:
                    target_minion = alive_minions[0]
                    if target_minion.get("archetype") == "escudo":
                        damage = max(1, int(damage * 0.5))
                        logs.append(f"🛡️ **Guardián de Escudo:** ¡{target_minion['name']} reduce el daño recibido un 50%!")
                    target_minion["hp"] = max(0, target_minion["hp"] - damage)
                    if not is_magic:
                        target_minion["last_physical_damage_taken"] = damage
                    logs.append(f"   → Daño redirigido a {target_minion['name']}: **{damage}** daño.")
                    if target_minion["hp"] <= 0:
                        logs.append(f"💀 **{target_minion['name']}** ha sido destruido!")
                else:
                    # Daño al jefe
                    self.boss.hp = max(0, self.boss.hp - damage)
                    if not is_magic:
                        self.boss.last_physical_damage_taken = damage
                    total_damage_dealt_this_turn += damage
                    # Acumular daño para la verificación de canalización
                    if self.boss_channeling:
                        self.boss_channeled_damage += damage
                    
                    crit_str = crit_text if 'crit_text' in locals() else ""
                    logs.append(f"   → Daño al jefe: **{damage}** daño{crit_str}.")

                # Pasivo: Vampirismo (cura 8% del daño infligido)
                if p.has_vampirism:
                    if p.anti_heal_turns == 0:
                        vamp_heal = max(1, int(damage * 0.08))
                        p.hp = min(p.max_hp, p.hp + vamp_heal)
                        logs.append(f"🧛 **Vampirismo:** {p.user.display_name} se cura **{vamp_heal}** HP.")

        # 5. ¿Boss derrotado?
        if self.boss.hp <= 0:
            self.game_over = True
            logs.append(f"🎉 **¡{self.boss.name} ha sido derrotado!**")
            self.action_log.extend(logs)
            if len(self.action_log) > 8:
                self.action_log = self.action_log[-8:]
            await self._finish_raid(interaction, victory=True)
            return

        # 6. Turno del Boss: Ataques y mecánicas
        alive = self._alive_players()
        if not alive:
            self.game_over = True
            logs.append(f"💀 **Todos los jugadores han caído. {self.boss.name} es victorioso.**")
            self.action_log.extend(logs)
            await self._finish_raid(interaction, victory=False)
            return

        boss_attacked = False
        boss_stunned = False

        if getattr(self.boss, "is_intangible", False):
            logs.append(f"👻 **Espíritu Errante:** {self.boss.name} flota de forma fantasmal y no ataca este turno.")
            boss_attacked = True

        # Comprobar si el boss está aturdido
        elif self.boss.stun_turns > 0:
            self.boss.stun_turns -= 1
            logs.append(f"💫 **¡{self.boss.name} está aturdido y no puede actuar este turno!**")
            if self.boss_channeling:
                self.boss_channeling = False
                logs.append(f"✨ **¡INTERRUMPIDO!** El aturdimiento de {self.boss.name} interrumpe su ataque definitivo.")
            boss_attacked = True
            boss_stunned = True

        # Si el boss estaba canalizando su Ultimate, resolver la canalización
        if not boss_attacked and self.boss_channeling:
            self.boss_channeling = False
            # Registrar daño acumulado
            if self.boss_channeled_damage >= self.boss_channeling_threshold:
                logs.append(f"✨ **¡INTERRUMPIDO!** El grupo infligió {self.boss_channeled_damage} daño, aturdiendo a {self.boss.name} y cancelando su ataque definitivo.")
            else:
                logs.append(f"💥 **¡FALLIDO!** El grupo solo infligió {self.boss_channeled_damage}/{self.boss_channeling_threshold} daño. {self.boss.name} desata su golpe definitivo!")
                ult_dmg = int(self.boss.atk * 2.5)
                # Weakness on Boss
                if self.boss.weakness_turns > 0:
                    ult_dmg = int(ult_dmg * (1.0 - self.boss.weakness_pct))
                # Daño en área masivo a todos los jugadores
                for target_p in alive:
                    apply_damage_to_player(target_p, ult_dmg, is_boss_attack=True)
            boss_attacked = True

        # Si no atacó con su Ultimate, realizar su ataque normal / especial
        if not boss_attacked:
            # Comprobar provocación (taunt) activa
            taunters = [p for p in alive if p.taunt_turns > 0 or p.is_taunting]
            if taunters:
                target = random.choice(taunters)
            else:
                target = random.choice(alive)

            # Comprobar ceguera en Boss
            if self.boss.blinded_turns > 0:
                self.boss.blinded_turns -= 1
                if random.random() < 0.40:
                    logs.append(f"👁️ **Ceguera:** ¡{self.boss.name} está cegado y falla su ataque!")
                    boss_attacked = True

            if not boss_attacked:
                # Modificador del afijo "Enfurecido"
                boss_atk_val = self.boss.atk
                if self.affix == "Enfurecido" and (self.boss.hp / self.boss.max_hp) < 0.35:
                    boss_atk_val = int(boss_atk_val * 1.30)
                    logs.append(f"⚡ **Enfurecido:** ¡{self.boss.name} ruge con furia, aumentando su ATK!")

                # Weakness on Boss
                if self.boss.weakness_turns > 0:
                    boss_atk_val = int(boss_atk_val * (1.0 - self.boss.weakness_pct))

                boss_dmg = int(boss_atk_val * random.uniform(0.85, 1.15))
                logs.append(f"{self.boss.emoji} {self.boss.name} ataca a {target.user.display_name}:")
                apply_damage_to_player(target, boss_dmg, is_boss_attack=True)

            # Habilidad especial del boss (cada 3 turnos, si no está aturdido ni intangible)
            if (self.turn_count + 1) % BOSS_SPECIAL_INTERVAL == 0 and not boss_stunned and not getattr(self.boss, "is_intangible", False):
                special_logs = self._execute_boss_ability()
                logs.extend(special_logs)

        # 7. Aplicar veneno de Rogue (Pícaro) al jefe
        if self.boss_poison_turns > 0:
            self.boss.hp = max(0, self.boss.hp - self.boss_poison_damage)
            self.boss_poison_turns -= 1
            if self.boss_poison_turns == 0:
                self.boss_poison_damage = 0
            logs.append(f"🧪 **Veneno del Pícaro:** {self.boss.name} sufre **{self.boss_poison_damage}** daño por veneno.")
            if self.boss.hp <= 0:
                self.game_over = True
                logs.append(f"🎉 **¡{self.boss.name} ha caído por el veneno del Pícaro!**")
                self.action_log.extend(logs)
                if len(self.action_log) > 8:
                    self.action_log = self.action_log[-8:]
                await self._finish_raid(interaction, victory=True)
                return

        # 8. Limpiar estados de ronda y reducir cooldowns
        for p in self.players:
            p.is_defending = False
            p.is_taunting = False
            if p.frozen_turns > 0:
                # Si está congelado, los cooldowns no se reducen
                pass
            else:
                if p.class_ability_cooldown > 0:
                    p.class_ability_cooldown -= 1
                if p.special_cooldown > 0:
                    p.special_cooldown -= 1
                if p.skill10_cooldown > 0:
                    p.skill10_cooldown -= 1
                if p.skill15_cooldown > 0:
                    p.skill15_cooldown -= 1
            if p.taunt_cooldown > 0:
                p.taunt_cooldown -= 1
            if p.taunt_turns > 0:
                p.taunt_turns -= 1
            if p.damage_reduction_turns > 0:
                p.damage_reduction_turns -= 1
            if p.atk_buff_turns > 0:
                p.atk_buff_turns -= 1
            if p.juicio_final_turns > 0:
                p.juicio_final_turns -= 1
            if p.evasion_buff_turns > 0:
                p.evasion_buff_turns -= 1
            if p.anti_heal_turns > 0:
                p.anti_heal_turns -= 1
            if p.weakness_turns > 0:
                p.weakness_turns -= 1
            if p.fragility_turns > 0:
                p.fragility_turns -= 1
            if p.vulnerability_turns > 0:
                p.vulnerability_turns -= 1
            if p.blinded_turns > 0:
                p.blinded_turns -= 1
            if p.hot_turns > 0:
                p.hot_turns -= 1
            if p.stun_turns > 0:
                p.stun_turns -= 1
            if p.frozen_turns > 0:
                p.frozen_turns -= 1
            if p.silence_turns > 0:
                p.silence_turns -= 1
            if p.frenzy_turns > 0:
                p.frenzy_turns -= 1
            if p.bleed_turns > 0 and not p.is_dead:
                b_dmg = max(1, int(p.last_physical_damage_taken * p.bleed_source_pct))
                p.hp = max(0, p.hp - b_dmg)
                p.bleed_turns -= 1
                logs.append(f"🩸 **Sangrado:** {p.user.display_name} sufre **{b_dmg}** HP de daño por sangrado.")
                if p.hp <= 0:
                    p.is_dead = True
                    logs.append(f"💀 **{p.user.display_name}** ha caído por sangrado!")
            if not p.is_dead:
                p.turns_survived += 1

        # Decrementar debuffs del Boss
        if self.boss.weakness_turns > 0:
            self.boss.weakness_turns -= 1
        if self.boss.fragility_turns > 0:
            self.boss.fragility_turns -= 1
        if self.boss.vulnerability_turns > 0:
            self.boss.vulnerability_turns -= 1
        if self.boss.frozen_turns > 0:
            self.boss.frozen_turns -= 1
        if self.boss.silence_turns > 0:
            self.boss.silence_turns -= 1
        if self.boss.bleed_turns > 0 and self.boss.hp > 0:
            b_dmg = max(1, int(self.boss.last_physical_damage_taken * self.boss.bleed_source_pct))
            self.boss.hp = max(0, self.boss.hp - b_dmg)
            self.boss.bleed_turns -= 1
            logs.append(f"🩸 **Sangrado del Boss:** {self.boss.name} sufre **{b_dmg}** HP de daño por sangrado.")
            if self.boss.hp <= 0:
                self.game_over = True
                logs.append(f"🎉 **¡{self.boss.name} ha caído por sangrado!**")
                self.action_log.extend(logs)
                await self._finish_raid(interaction, victory=True)
                return

        # Decrementar debuffs de los Esbirros
        for m in self.minions:
            if m.get("hp", 0) > 0:
                if m.get("weakness_turns", 0) > 0:
                    m["weakness_turns"] -= 1
                if m.get("fragility_turns", 0) > 0:
                    m["fragility_turns"] -= 1
                if m.get("vulnerability_turns", 0) > 0:
                    m["vulnerability_turns"] -= 1
                if m.get("stun_turns", 0) > 0:
                    m["stun_turns"] -= 1
                if m.get("frozen_turns", 0) > 0:
                    m["frozen_turns"] -= 1
                if m.get("silence_turns", 0) > 0:
                    m["silence_turns"] -= 1
                if m.get("bleed_turns", 0) > 0:
                    b_dmg = max(1, int(m.get("last_physical_damage_taken", 0) * m.get("bleed_source_pct", 0.06)))
                    m["hp"] = max(0, m["hp"] - b_dmg)
                    m["bleed_turns"] -= 1
                    logs.append(f"🩸 **Sangrado:** {m['name']} sufre **{b_dmg}** HP de daño por sangrado.")
                    if m["hp"] <= 0:
                        logs.append(f"💀 **{m['name']}** ha sido destruido por sangrado!")

        # Procesar comportamientos de esbirros al final del turno (healer, explosive)
        for m in self.minions:
            if m.get("hp", 0) > 0:
                # Si está aturdido o congelado, no actúa
                if m.get("stun_turns", 0) > 0 or m.get("frozen_turns", 0) > 0:
                    continue

                arch_type = m.get("archetype")
                if arch_type == "curandero" and self.boss.hp > 0:
                    # Cura 4% del HP máx del boss
                    heal_amt = int(self.boss.max_hp * 0.04)
                    self.boss.hp = min(self.boss.max_hp, self.boss.hp + heal_amt)
                    logs.append(f"💚 **Espíritu Curandero:** Cura a **{self.boss.name}** por **{heal_amt}** HP.")
                elif arch_type == "explosivo":
                    # Incrementar contador
                    m["fuse_counter"] = m.get("fuse_counter", 0) + 1
                    if m["fuse_counter"] == 2:
                        logs.append(f"💣 **¡{m['name']} va a detonar el próximo turno!** ¡Destrúyelo rápido!")
                    elif m["fuse_counter"] >= 3:
                        logs.append(f"💥 **¡{m['name']} ha detonado!**")
                        # Daño: 15% del atk del boss a todos los jugadores
                        raw_dmg = int(self.boss.atk * 0.15)
                        alive_players = self._alive_players()
                        for p in alive_players:
                            apply_damage_to_player(p, raw_dmg, is_boss_attack=True)
                            logs.append(f"   → {p.user.display_name} recibe daño por la explosión.")
                        # Auto-destrucción
                        m["hp"] = 0
                        logs.append(f"💀 **{m['name']}** se ha auto-destruido con la explosión!")

        self.actions.clear()

        # Comprobar si el próximo turno es de canalización (rondas 5, 10, 15...)
        if (self.turn_count + 2) % 5 == 0:
            self.boss_channeling = True
            self.boss_channeled_damage = 0
            self.boss_channeling_threshold = 30 * len(self.players)
            logs.append(f"\n⚠️ **¡{self.boss.name} empieza a canalizar un ataque definitivo!** ¡Inflige al menos **{self.boss_channeling_threshold}** de daño en la siguiente ronda para interrumpirlo!")

        self.turn_count += 1

        # Actualizar logs
        self.action_log.extend(logs)
        if len(self.action_log) > 8:
            self.action_log = self.action_log[-8:]

        # ¿Todos muertos?
        alive = self._alive_players()
        if not alive:
            self.game_over = True
            self.action_log.append(f"💀 **Todos los jugadores han caído. {self.boss.name} es victorioso.**")
            await self._finish_raid(interaction, victory=False)
            return

        # ¿Máximo de turnos?
        if self.turn_count >= RAID_MAX_TURNS:
            self.game_over = True
            self.action_log.append(f"⏰ **Se acabó el tiempo. {self.boss.name} se retira victorioso.**")
            await self._finish_raid(interaction, victory=False)
            return

        # Siguiente ronda
        self.reset_timeout()
        embed = self._build_embed()

        if interaction is None:
            # Timeout — recrear vista
            new_view = RaidCombatView(self.players, self.boss, self.cog, self.affix, difficulty=self.difficulty)
            new_view.turn_count = self.turn_count
            new_view.action_log = self.action_log
            new_view.interaction_msg = self.interaction_msg
            new_view.minions = self.minions
            new_view.minions_summoned = self.minions_summoned
            new_view.boss_channeling = self.boss_channeling
            new_view.boss_channeled_damage = self.boss_channeled_damage
            new_view.boss_channeling_threshold = self.boss_channeling_threshold
            new_view.boss_poison_turns = self.boss_poison_turns
            new_view.boss_poison_damage = self.boss_poison_damage
            new_view._rewards_done = self._rewards_done
            try:
                if self.interaction_msg:
                    await self.interaction_msg.edit(embed=embed, view=new_view)
            except Exception:
                pass
            self.stop()
            return

        try:
            if interaction and getattr(interaction, "message", None):
                await interaction.message.edit(embed=embed, view=self)
            elif self.interaction_msg:
                await self.interaction_msg.edit(embed=embed, view=self)
        except Exception:
            if self.interaction_msg:
                try:
                    await self.interaction_msg.edit(embed=embed, view=self)
                except Exception:
                    pass

    def _execute_boss_ability(self) -> list[str]:
        """Ejecuta la habilidad especial del boss. Retorna líneas de log."""
        logs = []
        ability = self.boss.ability
        alive = self._alive_players()

        if not alive:
            return logs

        ab_type = ability["type"]
        logs.append(f"\n{ability['emoji']} **¡{self.boss.name} usa {ability['name']}!**")

        if ab_type == "none":
            target = random.choice(alive)
            base = int(self.boss.atk)
            if self.boss.weakness_turns > 0:
                base = int(base * (1.0 - self.boss.weakness_pct))
            dmg = int(base * random.uniform(0.85, 1.15))
            logs.append(f"   → Dirigido a {target.user.display_name}:")
            apply_damage_to_player(target, dmg, is_boss_attack=True)

        elif ab_type == "aoe_damage":
            base = int(self.boss.atk * ability["damage_mult"])
            if self.boss.weakness_turns > 0:
                base = int(base * (1.0 - self.boss.weakness_pct))
            for p in alive:
                dmg = int(base * random.uniform(0.85, 1.15))
                apply_damage_to_player(p, dmg, is_boss_attack=True)

        elif ab_type == "single_target_dot":
            taunters = [p for p in alive if p.taunt_turns > 0 or p.is_taunting]
            if taunters:
                target = random.choice(taunters)
            else:
                target = max(alive, key=lambda p: p.hp)
            base = int(self.boss.atk * ability["damage_mult"])
            if self.boss.weakness_turns > 0:
                base = int(base * (1.0 - self.boss.weakness_pct))
            dmg = int(base * random.uniform(0.85, 1.15))
            logs.append(f"   → Dirigido a {target.user.display_name}:")
            apply_damage_to_player(target, dmg, is_boss_attack=True)
            if not target.is_dead:
                if target.poison_turns == 0:
                    target.poison_damage = 10
                else:
                    target.poison_damage = min(30, target.poison_damage + 10)
                target.poison_turns = ability["dot_turns"]
                logs.append(f"   🧪 {target.user.display_name} queda envenenado ({ability['dot_damage']}/t por {ability['dot_turns']} turnos).")

        elif ab_type == "aoe_damage_heal":
            base = int(self.boss.atk * ability["damage_mult"])
            if self.boss.weakness_turns > 0:
                base = int(base * (1.0 - self.boss.weakness_pct))
            for p in alive:
                dmg = int(base * random.uniform(0.85, 1.15))
                apply_damage_to_player(p, dmg, is_boss_attack=True)

            heal = int(self.boss.max_hp * ability["heal_pct"])
            self.boss.hp = min(self.boss.max_hp, self.boss.hp + heal)
            logs.append(f"   💚 {self.boss.name} se regenera **{heal}** HP.")

        elif ab_type == "aoe_drain":
            total_drained = 0
            for p in alive:
                drain = max(1, int(p.hp * ability["drain_pct"]))
                if p.is_defending:
                    drain = max(1, int(drain * 0.5))
                old_hp = p.hp
                apply_damage_to_player(p, drain, is_boss_attack=True)
                actual_lost = max(0, old_hp - p.hp)
                total_drained += actual_lost
            self.boss.hp = min(self.boss.max_hp, self.boss.hp + total_drained)
            logs.append(f"   💜 {self.boss.name} se cura **{total_drained}** HP con la energía robada.")

        elif ab_type == "aoe_debuff":
            base = int(self.boss.atk * ability["damage_mult"])
            if self.boss.weakness_turns > 0:
                base = int(base * (1.0 - self.boss.weakness_pct))
            for p in alive:
                dmg = int(base * random.uniform(0.85, 1.15))
                apply_damage_to_player(p, dmg, is_boss_attack=True)
                if not p.is_dead:
                    p.atk_debuff_turns = ability["debuff_turns"]
                    p.atk_debuff_pct = ability["atk_reduction_pct"]
                    logs.append(f"   → ❄️ {p.user.display_name} sufre reducción de ATK -{int(ability['atk_reduction_pct']*100)}% por {ability['debuff_turns']} turnos.")

        elif ab_type == "single_nuke":
            taunters = [p for p in alive if p.taunt_turns > 0 or p.is_taunting]
            if taunters:
                target = random.choice(taunters)
            else:
                target = random.choice(alive)
            base = int(self.boss.atk * ability["damage_mult"])
            if self.boss.weakness_turns > 0:
                base = int(base * (1.0 - self.boss.weakness_pct))
            dmg = int(base * random.uniform(0.90, 1.10))
            logs.append(f"   ⚡ ¡{self.boss.name} lanza un rayo devastador a {target.user.display_name}!")
            apply_damage_to_player(target, dmg, is_boss_attack=True)

        elif ab_type == "self_buff":
            low, high = ability["stat_shuffle_range"]
            atk_mult = random.uniform(low, high)
            def_mult = random.uniform(low, high)
            self.boss.atk = max(1, int(self.boss._base_atk * atk_mult))
            self.boss.def_stat = max(1, int(self.boss._base_def * def_mult))
            atk_change = "↑" if atk_mult > 1.0 else "↓"
            def_change = "↑" if def_mult > 1.0 else "↓"
            logs.append(
                f"   🌀 ¡{self.boss.name} muta! "
                f"ATK {atk_change} ({self.boss.atk}) · DEF {def_change} ({self.boss.def_stat})"
            )

        return logs

    # ──────────────────── TIMEOUT ────────────────────

    def reset_timeout(self):
        self.timeout = RAID_TURN_TIMEOUT

    async def on_timeout(self):
        if self.game_over:
            return

        # Marcar timeout para quienes no eligieron
        alive = self._alive_players()
        for p in alive:
            if p.user.id not in self.actions:
                self.actions[p.user.id] = 'timeout'

        await self._resolve_round(interaction=None)

    # ──────────────────── FIN DE LA RAID ────────────────────

    async def _finish_raid(self, interaction, victory: bool):
        """Finaliza la raid, da recompensas y limpia estado."""
        if self._rewards_done:
            return
        self._rewards_done = True

        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True

        # Construir embed de resultado
        if victory:
            embed = discord.Embed(
                title=f"🏆 ¡Raid Completada — {self.boss.name} Derrotado!",
                description=f"**¡Los héroes han triunfado sobre {self.boss.emoji} {self.boss.name}!**",
                color=discord.Color.gold()
            )
        else:
            embed = discord.Embed(
                title=f"💀 Raid Fallida — {self.boss.name} Victorious",
                description=f"**{self.boss.emoji} {self.boss.name} ha derrotado al grupo...**",
                color=discord.Color.dark_red()
            )

        # HP final del boss
        boss_hp_bar = format_hp_bar(max(0, self.boss.hp), self.boss.max_hp, size=15)
        embed.add_field(
            name=f"{self.boss.emoji} {self.boss.name}",
            value=boss_hp_bar,
            inline=False
        )

        # Estado de cada jugador y ganancia de XP
        for p in self.players:
            icon = "🟢" if not p.is_dead else "💀"
            hp_text = f"{p.hp}/{p.max_hp} HP" if not p.is_dead else "CAÍDO"
            
            # Calcular y aplicar XP
            base_xp = RAID_XP_BASE_VICTORY if victory else RAID_XP_BASE_DEFEAT
            turn_xp = p.turns_survived * RAID_XP_PER_TURN
            alive_bonus = RAID_XP_ALIVE_BONUS if not p.is_dead else 0
            xp_gained = base_xp + turn_xp + alive_bonus
            
            xp_res = await asyncio.to_thread(update_combat_stats_after_duel, p.user.id, xp_gained, victory, 0)
            
            xp_msg = f"+{xp_gained} XP"
            if xp_res.get("leveled_up"):
                xp_msg += f"\n🌟 **¡SUBE DE NIVEL! Nv. {xp_res['level']}**"
            else:
                xp_msg += f"\n({xp_res['xp']}/{xp_res['xp_for_next']} XP)"
                
            embed.add_field(
                name=f"{icon} {p.user.display_name}",
                value=f"{hp_text}\n{xp_msg}",
                inline=True
            )

        # Log final
        if self.action_log:
            embed.add_field(
                name="📜 Últimas acciones",
                value="\n".join(self.action_log[-4:]),
                inline=False
            )

        embed.set_footer(text=f"Duración: {self.turn_count} rondas · Jugadores: {len(self.players)}")

        # Registrar raid en DB
        participants_data = [
            {"user_id": p.user.id, "level": p.level, "survived": not p.is_dead}
            for p in self.players
        ]
        total_level = sum(p.level for p in self.players)
        try:
            await asyncio.to_thread(
                log_raid, self.boss.name, participants_data,
                "victory" if victory else "defeat",
                self.turn_count, total_level, self.difficulty
            )
        except Exception as e:
            logger.error(f"Error al registrar log de raid: {e}", exc_info=True)

        # Mostrar resultado
        if interaction:
            try:
                await interaction.message.edit(embed=embed, view=self)
            except Exception:
                pass
        elif self.interaction_msg:
            try:
                await self.interaction_msg.edit(embed=embed, view=self)
            except Exception:
                pass

        # Drops de ítems
        await self._resolve_drops(victory)

        # Limpiar
        for p in self.players:
            self.cog.active_raids.discard(p.user.id)

        self.stop()

    async def _resolve_drops(self, victory: bool):
        """Resuelve los drops de ítems para cada participante."""
        from src.utils.raid_config import RAID_LOOT_DIFFICULTY_CONFIG
        diff_cfg = RAID_LOOT_DIFFICULTY_CONFIG.get(self.difficulty, RAID_LOOT_DIFFICULTY_CONFIG["normal"])

        channel = None
        if self.interaction_msg:
            channel = self.interaction_msg.channel

        is_mimic = (victory and getattr(self.boss, "miniboss_key", None) == "cofre_mimetico")

        for p in self.players:
            # Determinar tasa de drop y bonus de rareza
            if is_mimic:
                from src.utils.raid_config import MINIBOSS_LOOT_RARITY_BONUS
                drop_rate = 1.0
                rarity_bonus = MINIBOSS_LOOT_RARITY_BONUS
                label = "Victoria (Miniboss)"
            elif victory:
                if not p.is_dead:
                    drop_rate = RAID_DROP_RATE_VICTORY_ALIVE
                    rarity_bonus = RAID_RARITY_BONUS_VICTORY
                    label = "Victoria (Sobreviviente)"
                else:
                    drop_rate = RAID_DROP_RATE_VICTORY_DEAD
                    rarity_bonus = 0.0
                    label = "Victoria (Caído)"
            else:
                drop_rate = RAID_DROP_RATE_DEFEAT
                rarity_bonus = RAID_RARITY_MALUS_DEFEAT
                label = "Derrota"

            if random.random() < drop_rate:
                final_rarity_bonus = min(0.75, rarity_bonus + diff_cfg["rarity_bonus"])
                loot = generate_raid_loot(p.level, final_rarity_bonus, floor_idx=diff_cfg["rarity_floor_idx"], ilvl_bonus=diff_cfg["ilvl_bonus"])
                equipment = await asyncio.to_thread(get_user_equipment, p.user.id)
                current_piece = equipment.get(loot["slot"])

                effective_channel = channel
                if effective_channel is None:
                    try:
                        if p.user.dm_channel is None:
                            await p.user.create_dm()
                        effective_channel = p.user.dm_channel
                    except Exception as exc:
                        logger.warning(
                            "No se pudo resolver canal para enviar drop de raid a %s: %r",
                            getattr(p.user, "name", "desconocido"), exc,
                        )
                        effective_channel = None

                if effective_channel is not None:
                    # Épico / Legendario → Sistema de Loot Roll grupal
                    if loot["rarity"] in ("Épico", "Legendario") and len(self.players) > 1:
                        alive_players = [pl for pl in self.players if not pl.is_dead]
                        eligible = alive_players if alive_players else self.players
                        roll_view = RaidLootRollView(loot, eligible, effective_channel)
                        roll_embed = roll_view.build_embed()
                        msg = await effective_channel.send(
                            content=(
                                f"🎲 **¡Drop {loot['rarity']}!** "
                                f"{loot['rarity_color']} **{loot['name']}** — "
                                f"¡Todos los sobrevivientes pueden tirar los dados!"
                            ),
                            embed=roll_embed,
                            view=roll_view,
                        )
                        roll_view.message = msg
                    else:
                        # Drop individual normal
                        view = RaidLootView(p.user, loot, current_piece)
                        loot_embed = view.build_embed()
                        msg = await effective_channel.send(
                            content=f"🎁 {p.user.mention} — ¡Drop de Raid! ({label})",
                            embed=loot_embed,
                            view=view,
                        )
                        view.message = msg

            # Roll para item único en Mítica (sólo en victorias de raids míticas)
            if victory and self.difficulty == "mitica" and random.random() < diff_cfg["unique_chance"]:
                unique_loot = roll_unique_item(self.boss.name)
                if unique_loot:
                    effective_channel = channel
                    if effective_channel is None:
                        try:
                            if p.user.dm_channel is None:
                                await p.user.create_dm()
                            effective_channel = p.user.dm_channel
                        except Exception as exc:
                            logger.warning(
                                "No se pudo resolver canal para enviar drop único de raid a %s: %r",
                                getattr(p.user, "name", "desconocido"), exc,
                            )
                            effective_channel = None

                    if effective_channel is not None:
                        equipment = await asyncio.to_thread(get_user_equipment, p.user.id)
                        unique_current_piece = equipment.get(unique_loot["slot"])

                        if unique_loot["rarity"] in ("Épico", "Legendario") and len(self.players) > 1:
                            alive_players = [pl for pl in self.players if not pl.is_dead]
                            eligible = alive_players if alive_players else self.players
                            roll_view = RaidLootRollView(unique_loot, eligible, effective_channel)
                            roll_embed = roll_view.build_embed()
                            msg = await effective_channel.send(
                                content=(
                                    f"⭐ **¡Drop ÚNICO!** "
                                    f"{unique_loot['rarity_color']} **{unique_loot['name']}** — "
                                    f"¡Todos los sobrevivientes pueden tirar los dados!"
                                ),
                                embed=roll_embed,
                                view=roll_view,
                            )
                            roll_view.message = msg
                        else:
                            view = RaidLootView(p.user, unique_loot, unique_current_piece)
                            loot_embed = view.build_embed()
                            msg = await effective_channel.send(
                                content=f"⭐ {p.user.mention} — ¡Has obtenido un Ítem Único de Raid! ({label})",
                                embed=loot_embed,
                                view=view,
                            )
                            view.message = msg


# ══════════════════════════════════════════════
# VISTA: DROP DE LOOT DE RAID
# ══════════════════════════════════════════════

class RaidLootView(discord.ui.View):
    """Vista de comparación para decidir si equipar o vender un drop de raid."""

    def __init__(self, user: discord.Member, loot: dict, current_piece: dict | None):
        super().__init__(timeout=LOOT_TIMEOUT_SECONDS)
        self.user = user
        self.loot = loot
        self.current_piece = current_piece
        self.message = None
        self.resolved = False

    def build_embed(self):
        loot = self.loot
        embed = discord.Embed(
            title=f"{loot['rarity_color']} {loot['name']}",
            description=(
                f"**{loot['rarity']}** · Nivel {loot['item_level']} · "
                f"{SLOT_EMOJIS.get(loot['slot'], '🔹')} {loot['slot']}\n"
                f"*Drop de Raid*"
            ),
            color=loot['rarity_hex']
        )

        new_stats_text = format_item_stats_display(loot)
        embed.add_field(name="🆕 Nuevo", value=new_stats_text, inline=True)

        if self.current_piece:
            cp = self.current_piece
            curr_stats_text = format_item_stats_display(cp)
            embed.add_field(name="📦 Actual", value=curr_stats_text, inline=True)

            diff_lines = []
            for stat in ALL_STATS:
                loot_val = loot['stats_summary'].get(stat, 0)
                cp_summary = {cp['primary_stat']: cp['primary_value']}
                for sec in cp.get('secondaries', []):
                    cp_summary[sec['stat']] = cp_summary.get(sec['stat'], 0) + sec['value']
                cp_val = cp_summary.get(stat, 0)

                if loot_val > 0 or cp_val > 0:
                    diff = loot_val - cp_val
                    if diff != 0:
                        sign = "+" if diff > 0 else ""
                        color = "🟢" if diff > 0 else "🔴"
                        diff_lines.append(f"{color} {sign}{diff} {format_stat_type(stat)}")

            if diff_lines:
                embed.add_field(name="📊 Diferencia", value="\n".join(diff_lines), inline=True)
            else:
                embed.add_field(name="📊 Diferencia", value="Stats idénticas", inline=True)
        else:
            embed.add_field(name="📦 Actual", value="— Vacío —", inline=True)

        embed.add_field(
            name="💰 Precio de venta",
            value=f"{loot['sell_price']:,} monedas",
            inline=False
        )
        embed.set_footer(text=f"Si no respondes en {LOOT_TIMEOUT_SECONDS}s, se vende automáticamente.")
        return embed

    @discord.ui.button(label="🔧 Equipar", style=discord.ButtonStyle.success)
    async def equip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Este drop no es para ti.", ephemeral=True)
            return
        if self.resolved:
            return

        loot = self.loot

        # Validar restricciones de clase
        c_stats = await asyncio.to_thread(get_combat_stats, self.user.id)
        player_level = c_stats['level']
        combat_class = c_stats.get('combat_class')

        if player_level >= 5 and combat_class:
            slot = loot['slot']
            material = loot.get('material')

            is_armor = slot in ("Cabeza", "Hombros", "Pecho", "Pantalones", "Botas")
            if is_armor and material:
                class_materials = {
                    "Guerrero": ["Hierro"], "Paladín": ["Hierro"],
                    "Pícaro": ["Cuero"], "Mago": ["Tela"], "Clérigo": ["Tela"]
                }
                allowed = class_materials.get(combat_class, [])
                if material not in allowed:
                    await interaction.response.send_message(
                        f"❌ Como **{combat_class}**, solo puedes equipar armaduras de **{', '.join(allowed)}** "
                        f"(este objeto es de {material}).",
                        ephemeral=True
                    )
                    return

            if slot in ("Arma", "Escudo", "Bastón mágico"):
                class_weapons = {
                    "Guerrero": ["Arma", "Escudo"], "Paladín": ["Arma", "Escudo"],
                    "Pícaro": ["Arma"], "Mago": ["Bastón mágico"], "Clérigo": ["Bastón mágico"]
                }
                allowed_w = class_weapons.get(combat_class, [])
                if slot not in allowed_w:
                    await interaction.response.send_message(
                        f"❌ Como **{combat_class}**, no puedes equipar un **{slot}** "
                        f"(permitidos: {', '.join(allowed_w)}).",
                        ephemeral=True
                    )
                    return

        self.resolved = True
        await interaction.response.defer()

        old = await asyncio.to_thread(
            equip_item, self.user.id,
            loot['slot'], loot['name'], loot['rarity'],
            loot['item_level'], loot['primary_stat'], loot['primary_value'],
            loot['secondaries'], loot['passive']
        )

        sell_msg = ""
        if old:
            old_sell = calc_sell_price(old['rarity'], old['item_level'])
            await asyncio.to_thread(add_balance, self.user.id, old_sell)
            await asyncio.to_thread(registrar_transaccion, self.user.id, old_sell,
                                    f"Venta equipo (raid): {old['item_name']}")
            sell_msg = f"\n💰 Vendiste **{old['item_name']}** por **{old_sell:,}** monedas."

        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title="✅ ¡Equipado!",
            description=f"Equipaste **{loot['name']}** en {loot['slot']}.{sell_msg}",
            color=loot['rarity_hex']
        )
        await interaction.edit_original_response(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="💰 Vender", style=discord.ButtonStyle.secondary)
    async def sell_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Este drop no es para ti.", ephemeral=True)
            return
        if self.resolved:
            return

        self.resolved = True
        await interaction.response.defer()
        await self._sell(interaction)

    async def _sell(self, interaction=None):
        loot = self.loot
        await asyncio.to_thread(add_balance, self.user.id, loot['sell_price'])
        await asyncio.to_thread(registrar_transaccion, self.user.id, loot['sell_price'],
                                f"Venta drop raid: {loot['name']}")

        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title="💰 Vendido",
            description=f"Vendiste **{loot['name']}** por **{loot['sell_price']:,}** monedas.",
            color=discord.Color.light_grey()
        )

        if interaction:
            await interaction.edit_original_response(embed=embed, view=self)
        elif self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass
        self.stop()

    async def on_timeout(self):
        if not self.resolved:
            self.resolved = True
            await self._sell()


# ══════════════════════════════════════════════
# VISTA: LOOT ROLL GRUPAL (Need/Greed/Pass)
# ══════════════════════════════════════════════

LOOT_ROLL_TIMEOUT = 45  # Segundos para decidir


class RaidLootRollView(discord.ui.View):
    """Vista de tirada de dados grupal para drops Épico/Legendario.

    Cada jugador elegible puede:
      🎯 Need  – Necesito este objeto (tira 1-100, +20 bonus).
      💰 Greed – Lo quiero para vender (tira 1-100).
      ❌ Pass  – No lo quiero.

    Al finalizar, el jugador con la tirada más alta gana el item.
    Si nadie tira, se vende y el oro se reparte.
    """

    def __init__(self, loot: dict, eligible_players: list['RaidCombatant'], channel):
        super().__init__(timeout=LOOT_ROLL_TIMEOUT)
        self.loot = loot
        self.eligible_players = eligible_players
        self.eligible_ids = {p.user.id for p in eligible_players}
        self.channel = channel
        self.message = None
        self.resolved = False

        # Almacenar decisiones: user_id -> {"choice": "need"/"greed"/"pass", "roll": int}
        self.rolls: dict[int, dict] = {}

    def build_embed(self) -> discord.Embed:
        loot = self.loot
        embed = discord.Embed(
            title=f"🎲 ¡Loot Roll! — {loot['rarity_color']} {loot['name']}",
            description=(
                f"**{loot['rarity']}** · Nivel {loot['item_level']} · "
                f"{SLOT_EMOJIS.get(loot['slot'], '🔹')} {loot['slot']}\n\n"
                f"Elige tu opción:\n"
                f"🎯 **Need** — Lo necesito (+20 bonus a la tirada)\n"
                f"💰 **Greed** — Lo quiero para vender\n"
                f"❌ **Pass** — No lo quiero\n"
            ),
            color=loot['rarity_hex']
        )

        new_stats_text = format_item_stats_display(loot)
        embed.add_field(name="📊 Stats", value=new_stats_text, inline=False)

        # Mostrar quiénes ya tiraron
        status_lines = []
        for p in self.eligible_players:
            if p.user.id in self.rolls:
                r = self.rolls[p.user.id]
                choice_emoji = {"need": "🎯", "greed": "💰", "pass": "❌"}
                status_lines.append(
                    f"{choice_emoji.get(r['choice'], '❓')} **{p.user.display_name}** — "
                    f"{r['choice'].capitalize()}"
                    + (f" (🎲 {r['roll']})" if r['choice'] != 'pass' else "")
                )
            else:
                status_lines.append(f"⏳ **{p.user.display_name}** — Decidiendo...")

        embed.add_field(name="🎲 Tiradas", value="\n".join(status_lines) or "—", inline=False)
        embed.set_footer(text=f"Tiempo: {LOOT_ROLL_TIMEOUT}s · Si nadie tira, se vende y se reparte el oro.")
        return embed

    async def _check_all_rolled(self, interaction: discord.Interaction):
        """Verifica si todos ya tiraron y resuelve si es así."""
        if len(self.rolls) >= len(self.eligible_players):
            await self._resolve(interaction)

    @discord.ui.button(label="🎯 Need", style=discord.ButtonStyle.success, row=0)
    async def need_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_roll(interaction, "need")

    @discord.ui.button(label="💰 Greed", style=discord.ButtonStyle.primary, row=0)
    async def greed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_roll(interaction, "greed")

    @discord.ui.button(label="❌ Pass", style=discord.ButtonStyle.secondary, row=0)
    async def pass_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_roll(interaction, "pass")

    async def _handle_roll(self, interaction: discord.Interaction, choice: str):
        user_id = interaction.user.id

        if user_id not in self.eligible_ids:
            await interaction.response.send_message("❌ No participaste en esta raid.", ephemeral=True)
            return

        if user_id in self.rolls:
            await interaction.response.send_message("❌ Ya elegiste tu opción.", ephemeral=True)
            return

        if self.resolved:
            await interaction.response.send_message("❌ Este loot roll ya terminó.", ephemeral=True)
            return

        if choice == "pass":
            roll_val = 0
        elif choice == "need":
            roll_val = random.randint(1, 100) + 20  # Bonus de +20
        else:  # greed
            roll_val = random.randint(1, 100)

        self.rolls[user_id] = {"choice": choice, "roll": roll_val}

        # Actualizar el embed
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

        # Verificar si todos votaron
        await self._check_all_rolled(interaction)

    async def _resolve(self, interaction: discord.Interaction = None):
        if self.resolved:
            return
        self.resolved = True

        loot = self.loot

        # Filtrar los que NO hicieron pass
        active_rolls = {
            uid: data for uid, data in self.rolls.items()
            if data["choice"] != "pass"
        }

        # Desactivar botones
        for item in self.children:
            item.disabled = True

        if not active_rolls:
            # Nadie quiso el item → vender y repartir
            sell_price = loot['sell_price']
            share = sell_price // len(self.eligible_players)
            for p in self.eligible_players:
                await asyncio.to_thread(add_balance, p.user.id, share)
                await asyncio.to_thread(registrar_transaccion, p.user.id, share,
                                        f"Venta grupal raid: {loot['name']}")

            embed = discord.Embed(
                title="💰 Nadie reclamó el loot",
                description=(
                    f"**{loot['rarity_color']} {loot['name']}** se vendió automáticamente por "
                    f"**{sell_price:,}** monedas.\n"
                    f"Cada jugador recibió **{share:,}** monedas."
                ),
                color=discord.Color.light_grey()
            )
        else:
            # El de mayor tirada gana
            winner_id = max(active_rolls, key=lambda uid: active_rolls[uid]["roll"])
            winner_data = active_rolls[winner_id]
            winner_player = next(p for p in self.eligible_players if p.user.id == winner_id)

            # Equipar o dar el item al ganador
            equipment = await asyncio.to_thread(get_user_equipment, winner_id)
            current_piece = equipment.get(loot["slot"])

            # Enviar vista individual al ganador para decidir equipar/vender
            try:
                loot_view = RaidLootView(winner_player.user, loot, current_piece)
                loot_embed = loot_view.build_embed()
                await self.channel.send(
                    content=f"🎁 {winner_player.user.mention} — ¡Ganaste la tirada! Decide qué hacer:",
                    embed=loot_embed,
                    view=loot_view,
                )
            except Exception as exc:
                logger.warning("Error al enviar loot al ganador del roll: %r", exc)

            # Construir resultado
            result_lines = []
            for p in self.eligible_players:
                if p.user.id in self.rolls:
                    r = self.rolls[p.user.id]
                    choice_emoji = {"need": "🎯", "greed": "💰", "pass": "❌"}
                    is_winner = " 👑" if p.user.id == winner_id else ""
                    result_lines.append(
                        f"{choice_emoji.get(r['choice'], '❓')} **{p.user.display_name}** — "
                        f"{r['choice'].capitalize()}"
                        + (f" (🎲 {r['roll']})" if r['choice'] != 'pass' else "")
                        + is_winner
                    )
                else:
                    result_lines.append(f"❌ **{p.user.display_name}** — No respondió (Pass)")

            embed = discord.Embed(
                title=f"🎲 Loot Roll — Resultado",
                description=(
                    f"**{loot['rarity_color']} {loot['name']}**\n\n"
                    f"🏆 **¡{winner_player.user.display_name}** gana con una tirada de "
                    f"**{winner_data['roll']}** ({winner_data['choice'].capitalize()})!\n\n"
                    + "\n".join(result_lines)
                ),
                color=loot['rarity_hex']
            )

        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass
        self.stop()

    async def on_timeout(self):
        """Cuando expira el tiempo, los que no votaron se marcan como Pass."""
        if self.resolved:
            return

        # Marcar como Pass a los que no votaron
        for p in self.eligible_players:
            if p.user.id not in self.rolls:
                self.rolls[p.user.id] = {"choice": "pass", "roll": 0}

        await self._resolve()


def log_raid(boss_name: str, participants: list, result: str, turns: int, total_level: int, difficulty: str = "normal"):
    """Registra una raid completada en la base de datos."""
    import psycopg2.extras
    with db_cursor() as cursor:
        # Crear tabla si no existe
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS RaidLog (
                ID SERIAL PRIMARY KEY,
                BossName VARCHAR(50),
                Participants JSONB,
                Result VARCHAR(10),
                Turns INT,
                TotalLevel INT,
                Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                Difficulty VARCHAR(10) DEFAULT 'normal'
            )
        """)
        cursor.execute("ALTER TABLE RaidLog ADD COLUMN IF NOT EXISTS Difficulty VARCHAR(10) DEFAULT 'normal'")
        cursor.execute("""
            INSERT INTO RaidLog (BossName, Participants, Result, Turns, TotalLevel, Difficulty)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (boss_name, psycopg2.extras.Json(participants), result, turns, total_level, difficulty))


def count_mythic_raids_today(user_id: int) -> int:
    """Cuenta cuántas raids Míticas ha iniciado o participado un usuario hoy (hora del servidor/DB)."""
    import psycopg2.extras
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM RaidLog
            WHERE Difficulty = 'mitica'
              AND Timestamp::date = CURRENT_DATE
              AND Participants @> %s
        """, (psycopg2.extras.Json([{"user_id": user_id}]),))
        return cursor.fetchone()[0]


def build_minions_from_pool(boss_config) -> list[dict]:
    import random
    from src.utils.raid_config import MINION_ARCHETYPES

    if isinstance(boss_config, dict):
        pool = boss_config.get("minion_pool")
    else:
        pool = getattr(boss_config, "minion_pool", None)
    if pool is None:  # Caso Abyssus: 2 random
        pool = random.sample(list(MINION_ARCHETYPES.keys()), 2)
    minions = []
    for key in pool:
        arch = MINION_ARCHETYPES[key]
        minions.append({
            "name": arch["name"], "archetype": key, "hp": arch["hp"], "max_hp": arch["hp"],
            "def_stat": arch["def_stat"],
            "stun_turns": 0, "weakness_turns": 0, "weakness_pct": 0.0,
            "fragility_turns": 0, "fragility_pct": 0.0, "vulnerability_turns": 0, "vulnerability_pct": 0.0,
            "burn_turns": 0, "poison_turns": 0, "poison_damage": 0,
            "frozen_turns": 0, "silence_turns": 0, "bleed_turns": 0, "bleed_source_pct": 0.06,
            "last_physical_damage_taken": 0,
            "fuse_counter": 0,  # Solo usado por Explosivo
        })
    return minions


def build_miniboss_config(miniboss_key: str, miniboss_dict: dict) -> dict:
    return {
        "name": miniboss_dict["name"],
        "emoji": miniboss_dict["emoji"],
        "element": miniboss_dict.get("element", "Neutral"),
        "color": miniboss_dict.get("color", 0x8B4513),
        "base_hp": miniboss_dict["hp"],
        "base_atk": miniboss_dict["atk"],
        "base_def": miniboss_dict["def_stat"],
        "hp": miniboss_dict["hp"],
        "atk": miniboss_dict["atk"],
        "def_stat": miniboss_dict["def_stat"],
        "ability": miniboss_dict["ability"],
        "lore": miniboss_dict["lore"],
        "minion_pool": [],
        "is_miniboss": True,
        "miniboss_key": miniboss_key,
        "guaranteed_loot": miniboss_dict.get("guaranteed_loot", False),
        "invisibility_pattern": miniboss_dict.get("invisibility_pattern", False),
    }



def roll_unique_item(boss_name: str) -> dict | None:
    """8% de probabilidad ya se evalúa antes de llamar esto. Retorna un ítem del catálogo o None."""
    import random
    from src.db import db_cursor
    from src.utils.combat_progression import RARITY_COLORS, calc_sell_price

    with db_cursor() as cursor:
        cursor.execute("""
            SELECT ItemKey, Name, Slot, Rarity, PrimaryStat, PrimaryValue, Secondaries, Passive, Lore
            FROM UniqueItemCatalog
            WHERE BossSource = %s OR BossSource IS NULL
        """, (boss_name,))
        rows = cursor.fetchall()
    if not rows:
        return None

    # Seleccionar uno al azar
    row = random.choice(rows)
    item_key, name, slot, rarity, primary_stat, primary_value, secondaries, passive, lore = row

    # Armar stats_summary para que coincida con generate_loot()
    stats_summary = {primary_stat: primary_value}
    for sec in secondaries:
        stats_summary[sec["stat"]] = stats_summary.get(sec["stat"], 0) + sec["value"]

    rarity_hex = RARITY_COLORS.get(rarity, 0xff8800)
    sell_price = calc_sell_price(rarity, 35)

    return {
        "slot": slot,
        "name": name,
        "rarity": rarity,
        "rarity_color": "🟧",  # Color de Legendario
        "rarity_hex": rarity_hex,
        "item_level": 35,
        "primary_stat": primary_stat,
        "primary_value": primary_value,
        "secondaries": secondaries,
        "passive": passive,
        "sell_price": sell_price,
        "stats_summary": stats_summary,
        "item_key": item_key,  # Guardar referencia
        "lore": lore
    }


# ══════════════════════════════════════════════
# COG: RAIDS
# ══════════════════════════════════════════════

class RaidsCog(commands.Cog):
    """Sistema de Raids PvE cooperativas."""

    def __init__(self, bot):
        self.bot = bot
        self.active_raids: set[int] = set()

    @app_commands.command(name="raid", description="Inicia una raid cooperativa contra el boss del día")
    async def raid_cmd(self, interaction: discord.Interaction):
        user = interaction.user
        user_id = user.id

        # Verificar que no esté en otra raid
        if user_id in self.active_raids:
            await interaction.response.send_message(
                "❌ Ya tienes una raid en curso.", ephemeral=True
            )
            return

        # Asegurar usuario
        await asyncio.to_thread(ensure_user, user_id, user.name)

        # Cargar stats
        stats = await asyncio.to_thread(get_combat_stats, user_id)
        equip = await asyncio.to_thread(get_user_equipment, user_id)

        # Obtener boss del día
        boss_config = get_today_boss()

        # Roll miniboss
        import random
        from src.utils.raid_config import MINIBOSS_CHANCE, MINIBOSSES
        if random.random() < MINIBOSS_CHANCE:
            miniboss_key = random.choice(list(MINIBOSSES.keys()))
            boss_config = build_miniboss_config(miniboss_key, MINIBOSSES[miniboss_key])

        # Marcar como activo
        self.active_raids.add(user_id)

        # Crear lobby
        lobby = RaidLobbyView(user, boss_config, self)
        lobby.player_stats[user_id] = stats
        lobby.player_equipments[user_id] = equip

        embed = lobby._build_lobby_embed()
        await interaction.response.send_message(embed=embed, view=lobby)
        msg = await interaction.original_response()

        # Esperar
        await lobby.wait()

        if not lobby.started:
            # Cancelada o timeout
            for p in lobby.players:
                self.active_raids.discard(p.id)
            if not lobby.cancelled:
                for item in lobby.children:
                    item.disabled = True
                cancel_embed = discord.Embed(
                    title="❌ Raid Expirada",
                    description="No se inició a tiempo. Intenta de nuevo.",
                    color=discord.Color.red()
                )
                try:
                    await msg.edit(embed=cancel_embed, view=lobby)
                except Exception:
                    pass
            return

        # Iniciar combate
        await asyncio.sleep(1)

        # Cargar equipo de todos los jugadores
        combatants = []
        for p in lobby.players:
            p_stats = lobby.player_stats.get(p.id, await asyncio.to_thread(get_combat_stats, p.id))
            p_equip = lobby.player_equipments.get(p.id, await asyncio.to_thread(get_user_equipment, p.id))
            combatants.append(RaidCombatant(
                p, p_stats['level'], p_equip,
                combat_class=p_stats.get('combat_class'),
                combat_subclass=p_stats.get('combat_subclass')
            ))

        # Calcular stats del boss
        from src.utils.combat_progression import calc_power_level
        total_power = sum(calc_power_level(c.level, lobby.player_equipments.get(c.user.id, {}), c.combat_subclass) for c in combatants)
        boss = RaidBoss(boss_config, total_power, lobby.difficulty, is_miniboss=boss_config.get("is_miniboss", False))

        # Seleccionar afijo aleatorio de la arena
        affix_name = random.choice(list(RAID_AFFIXES.keys()))

        # Crear vista de combate con afijo
        combat_view = RaidCombatView(combatants, boss, self, affix=affix_name, difficulty=lobby.difficulty)
        combat_embed = combat_view._build_embed()

        combat_msg = await interaction.followup.send(embed=combat_embed, view=combat_view)
        combat_view.interaction_msg = combat_msg


async def setup(bot):
    await bot.add_cog(RaidsCog(bot))
    logger.info("Raids cog loaded successfully.")
