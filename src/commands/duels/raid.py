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
)
from src.utils.raid_config import (
    RAID_MIN_PLAYERS, RAID_MAX_PLAYERS,
    RAID_LOBBY_TIMEOUT, RAID_TURN_TIMEOUT, RAID_MAX_TURNS,
    RAID_DROP_RATE_VICTORY_ALIVE, RAID_DROP_RATE_VICTORY_DEAD,
    RAID_DROP_RATE_DEFEAT,
    RAID_RARITY_BONUS_VICTORY, RAID_RARITY_MALUS_DEFEAT,
    BOSS_SPECIAL_INTERVAL, BOSS_ABILITIES,
    RAID_BOSSES, RAID_AFFIXES,
    get_today_boss, calc_boss_stats, generate_raid_loot,
)


# ══════════════════════════════════════════════
# BOSS EN COMBATE
# ══════════════════════════════════════════════

class RaidBoss:
    """Estado del boss durante el combate de raid."""

    def __init__(self, boss_config: dict, total_level: int):
        self.name = boss_config["name"]
        self.emoji = boss_config["emoji"]
        self.element = boss_config["element"]
        self.color = boss_config["color"]
        self.lore = boss_config["lore"]
        self.ability_id = boss_config["ability"]
        self.ability = BOSS_ABILITIES[self.ability_id]

        # Stats escalados
        stats = calc_boss_stats(boss_config, total_level)
        self.max_hp = stats["max_hp"]
        self.hp = stats["hp"]
        self.atk = stats["atk"]
        self.def_stat = stats["def_stat"]

        # Stats base guardados para mutación
        self._base_atk = self.atk
        self._base_def = self.def_stat


# ══════════════════════════════════════════════
# JUGADOR EN RAID
# ══════════════════════════════════════════════

class RaidCombatant:
    """Estado de un jugador durante la raid."""

    def __init__(self, user: discord.Member, level: int, equipment: dict, combat_class: str = None):
        self.user = user
        self.level = level
        self.combat_class = combat_class

        # Stats base + equipo
        base = calc_base_stats(level)
        bonus, passives = calc_equipment_bonus(equipment)
        effective, _, _ = get_effective_bonus(bonus, level)

        self.max_hp = base["hp"] + effective.get("hp", 0)
        self.hp = self.max_hp
        self.atk = base["atk"] + effective.get("atk", 0)
        self.base_atk = self.atk  # Para restaurar después de debuffs
        self.mag = base["mag"] + effective.get("mag", 0)
        self.def_stat = base["def"] + effective.get("def", 0)

        # Estado de combate
        self.is_defending = False
        self.is_dead = False
        self.poison_turns = 0      # Turnos de veneno restantes
        self.poison_damage = 0     # Daño por turno de veneno
        self.atk_debuff_turns = 0  # Turnos de reducción de ATK
        self.atk_debuff_pct = 0.0  # Porcentaje de reducción
        
        # Nuevos estados para habilidades activas y mecánicas
        self.shield = 0            # Escudo de absorción (Paladín)
        self.is_taunting = False   # Provocación activa (Guerrero)
        self.class_ability_cooldown = 0 # Enfriamiento de habilidad de clase


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
        self.started = False
        self.cancelled = False

    def _build_lobby_embed(self):
        boss = self.boss_config
        player_list = "\n".join(
            f"{get_combat_rank_emoji(self.player_stats.get(p.id, {}).get('level', 1))} "
            f"**{p.display_name}** — Nv. {self.player_stats.get(p.id, {}).get('level', 1)}"
            for p in self.players
        )

        total_level = sum(self.player_stats.get(p.id, {}).get('level', 1) for p in self.players)
        scaled_stats = calc_boss_stats(boss, total_level)

        embed = discord.Embed(
            title=f"{boss['emoji']} Raid — {boss['name']}",
            description=(
                f"*{boss['lore']}*\n\n"
                f"**Elemento:** {boss['element']}\n"
                f"**Habilidad Especial:** {BOSS_ABILITIES[boss['ability']]['emoji']} "
                f"{BOSS_ABILITIES[boss['ability']]['name']}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"**Jugadores ({len(self.players)}/{RAID_MAX_PLAYERS}):**\n{player_list}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"**Stats del Boss** (escalado a Nv. total {total_level}):\n"
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

        # Cargar stats
        await asyncio.to_thread(ensure_user, user.id, user.name)
        stats = await asyncio.to_thread(get_combat_stats, user.id)
        self.player_stats[user.id] = stats

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

    async def on_timeout(self):
        if not self.started and not self.cancelled:
            self.cancelled = True
            for p in self.players:
                self.cog.active_raids.discard(p.id)


# ══════════════════════════════════════════════
# VISTA: COMBATE DE RAID
# ══════════════════════════════════════════════

class RaidCombatView(discord.ui.View):
    """Vista principal del combate cooperativo contra el boss."""

    def __init__(self, players: list[RaidCombatant], boss: RaidBoss, cog: 'RaidsCog', affix: str = "Ninguno"):
        super().__init__(timeout=RAID_TURN_TIMEOUT)
        self.players = players
        self.boss = boss
        self.cog = cog
        self.affix = affix

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
        embed.add_field(
            name=f"{self.boss.emoji} {self.boss.name} — Nv. ∞",
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
            minions_text = "\n".join(f"👾 **{m['name']}**: {format_hp_bar(m['hp'], m['max_hp'])}" for m in alive_minions)
            embed.add_field(name="👾 Esbirros del Jefe", value=minions_text, inline=False)

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
                if p.shield > 0:
                    status += f" 🛡️(Escudo: {p.shield})"
                if p.is_taunting:
                    status += " 📣(Taunt)"

            # Acción elegida
            action_status = ""
            if not p.is_dead:
                if p.user.id in self.actions:
                    action_status = " · 🟢 ¡Listo!"
                else:
                    action_status = " · 🔴 Eligiendo..."
                if p.class_ability_cooldown > 0:
                    action_status += f" ⏳({p.class_ability_cooldown}t)"

            class_tag = f" [{p.combat_class}]" if p.combat_class else ""
            embed.add_field(
                name=f"{rank_emoji} {p.user.display_name}{class_tag} (Nv.{p.level}){status}{action_status}",
                value=f"{hp_bar}\n⚔️ {p.atk} ATK · 🛡️ {p.def_stat} DEF",
                inline=True
            )

        # Log
        if self.action_log:
            log_text = "\n".join(self.action_log[-6:])
            embed.add_field(name="📜 Registro", value=log_text, inline=False)

        embed.set_footer(text=f"Acciones: ⚔️ Atacar · 🛡️ Defender · ✨ Especial de Clase · Tiempo por ronda: {RAID_TURN_TIMEOUT}s")
        return embed

    # ──────────────────── BOTONES ────────────────────

    @discord.ui.button(label="⚔️ Atacar", style=discord.ButtonStyle.danger, row=0)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._register_action(interaction, 'attack')

    @discord.ui.button(label="🛡️ Defender", style=discord.ButtonStyle.primary, row=0)
    async def defend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._register_action(interaction, 'defend')

    @discord.ui.button(label="✨ Especial de Clase", style=discord.ButtonStyle.secondary, row=0)
    async def class_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        player = next((p for p in self.players if p.user.id == user_id), None)
        if player is None:
            await interaction.response.send_message("❌ No participas en esta raid.", ephemeral=True)
            return
        if player.is_dead:
            await interaction.response.send_message("❌ Has caído en combate.", ephemeral=True)
            return
        if not player.combat_class:
            await interaction.response.send_message("❌ No tienes una clase (requiere Nv. 5+).", ephemeral=True)
            return
        if player.class_ability_cooldown > 0:
            await interaction.response.send_message(
                f"⏳ Tu habilidad de clase está en enfriamiento ({player.class_ability_cooldown} turnos).",
                ephemeral=True
            )
            return

        await self._register_action(interaction, 'class_special')

    async def _register_action(self, interaction: discord.Interaction, action: str):
        if self.game_over:
            await interaction.response.send_message("❌ La raid ya terminó.", ephemeral=True)
            return

        user_id = interaction.user.id

        # Verificar que es un participante
        player = next((p for p in self.players if p.user.id == user_id), None)
        if player is None:
            await interaction.response.send_message("❌ No participas en esta raid.", ephemeral=True)
            return

        if player.is_dead:
            await interaction.response.send_message("❌ Has caído en combate.", ephemeral=True)
            return

        if user_id in self.actions:
            await interaction.response.send_message("❌ Ya elegiste tu acción.", ephemeral=True)
            return

        self.actions[user_id] = action

        # ¿Ya todos eligieron?
        alive = self._alive_players()
        all_ready = all(p.user.id in self.actions for p in alive)

        if all_ready:
            await interaction.response.defer()
            await self._resolve_round(interaction)
        else:
            embed = self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    # ──────────────────── RESOLUCIÓN ────────────────────

    async def _resolve_round(self, interaction=None):
        """Resuelve la ronda: acciones de jugadores → IA del boss."""
        logs = [f"🏁 **Ronda {self.turn_count + 1}:**"]
        alive = self._alive_players()

        # Helper para aplicar daño a jugadores
        def apply_damage_to_player(target, raw_dmg):
            if target.is_dead:
                return
            absorbed = 0
            if target.shield > 0:
                absorbed = min(target.shield, raw_dmg)
                raw_dmg -= absorbed
                target.shield -= absorbed
                logs.append(f"🛡️ **Escudo:** Se absorbieron **{absorbed}** de daño. Queda {target.shield} de escudo en {target.user.display_name}.")
            if target.is_defending:
                raw_dmg = max(1, int(raw_dmg * 0.4))
            target.hp = max(0, target.hp - raw_dmg)
            logs.append(f"💥 {target.user.display_name} recibe **{raw_dmg}** daño. ({target.hp}/{target.max_hp} HP)")
            if target.hp <= 0:
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

        # 2. Aplicar DOTs (veneno) a jugadores
        for p in alive:
            if p.poison_turns > 0:
                dmg = min(p.hp, p.poison_damage)
                p.poison_turns -= 1
                logs.append(f"🧪 **Veneno:** {p.user.display_name} sufre **{dmg}** daño por veneno.")
                apply_damage_to_player(p, dmg)

        # Refrescar vivos
        alive = self._alive_players()
        if not alive:
            self.game_over = True
            logs.append(f"💀 **Todos los jugadores han caído. {self.boss.name} es victorioso.**")
            self.action_log.extend(logs)
            await self._finish_raid(interaction, victory=False)
            return

        # Decrementar debuffs
        for p in alive:
            if p.atk_debuff_turns > 0:
                p.atk_debuff_turns -= 1
                if p.atk_debuff_turns <= 0:
                    p.atk = p.base_atk  # Restaurar ATK
                    logs.append(f"❄️ El debuff de ATK de {p.user.display_name} ha terminado.")

        # 3. Comprobar si esbirros deben aparecer por primera vez (< 50% HP)
        if self.boss.hp < (self.boss.max_hp * 0.5) and not self.minions_summoned:
            self.minions_summoned = True
            self.minions = [
                {"name": "Esbirro de Sombras A", "hp": 40, "max_hp": 40},
                {"name": "Esbirro de Sombras B", "hp": 40, "max_hp": 40}
            ]
            logs.append("\n👾 **¡El jefe invoca 2 Esbirros de Sombras!** Los ataques se redirigirán a ellos hasta destruirlos.")

        # 4. Procesar acciones de jugadores
        total_damage_dealt_this_turn = 0

        for p in alive:
            action = self.actions.get(p.user.id, 'timeout')
            damage = 0
            is_magic = False
            crit = False

            if action == 'attack':
                # Ataque normal (daño físico)
                effective_atk = p.atk
                if p.atk_debuff_turns > 0:
                    effective_atk = int(p.atk * (1.0 - p.atk_debuff_pct))

                base_dmg = effective_atk * random.uniform(0.85, 1.15)
                reduction = self.boss.def_stat * 0.35
                damage = max(1, int(base_dmg - reduction))

                # Crítico 10%
                crit = random.random() < 0.10
                if crit:
                    damage = int(damage * 1.5)

            elif action == 'class_special':
                # Habilidad especial de clase
                if p.combat_class == 'Guerrero':
                    # Daño físico 50% y taunt
                    damage = max(1, int(p.atk * 0.5 * random.uniform(0.9, 1.1) - self.boss.def_stat * 0.35))
                    p.is_taunting = True
                    p.class_ability_cooldown = 3
                    logs.append(f"🛡️ **{p.user.display_name}** usa **Provocación**.")
                elif p.combat_class == 'Mago':
                    # Daño mágico masivo
                    damage = max(1, int(p.mag * 2.2 * random.uniform(0.85, 1.15) - self.boss.def_stat * 0.20))
                    is_magic = True
                    p.class_ability_cooldown = 3
                    logs.append(f"🔮 **{p.user.display_name}** usa **Explosión Arcana**.")
                elif p.combat_class == 'Pícaro':
                    # Daño físico y veneno al jefe
                    damage = max(1, int(p.atk * 1.5 * random.uniform(0.9, 1.1) - self.boss.def_stat * 0.35))
                    self.boss_poison_turns = 3
                    self.boss_poison_damage = 20
                    p.class_ability_cooldown = 3
                    logs.append(f"🗡️ **{p.user.display_name}** usa **Emboscada** e inflige veneno.")
                elif p.combat_class == 'Clérigo':
                    # Curación grupal (mágica)
                    heal = int(p.mag * 1.0)
                    for target_p in self.players:
                        if not target_p.is_dead:
                            target_p.hp = min(target_p.max_hp, target_p.hp + heal)
                    p.class_ability_cooldown = 4
                    logs.append(f"💚 **{p.user.display_name}** usa **Plegaria Celestial** y cura **{heal}** HP a todo el grupo.")
                elif p.combat_class == 'Paladín':
                    # Escuda al aliado con menor porcentaje de HP
                    target_p = min([target for target in self.players if not target.is_dead], key=lambda x: x.hp / x.max_hp)
                    shield_val = int(p.max_hp * 0.2)
                    target_p.shield = shield_val
                    p.class_ability_cooldown = 4
                    logs.append(f"✨ **{p.user.display_name}** usa **Baluarte Sagrado** escudando a {target_p.user.display_name} por **{shield_val}**.")

            elif action == 'defend':
                p.is_defending = True
                heal = calc_defend_heal(p.max_hp)
                p.hp = min(p.max_hp, p.hp + heal)
                logs.append(f"🛡️ {p.user.display_name} se defiende y recupera **{heal}** HP.")

            elif action == 'timeout':
                logs.append(f"⏰ {p.user.display_name} no respondió a tiempo.")

            # Aplicar modificadores de afijo "Inestabilidad Mágica"
            if damage > 0:
                if is_magic:
                    if self.affix == "Inestabilidad Mágica":
                        damage = int(damage * 1.4)
                        logs.append("🌀 **Inestabilidad Mágica:** Daño mágico aumentado un 40%.")
                else:
                    if self.affix == "Inestabilidad Mágica":
                        damage = int(damage * 0.7)
                        logs.append("🌀 **Inestabilidad Mágica:** Daño físico reducido un 30%.")

                # Redirigir a esbirros si están activos
                alive_minions = [m for m in self.minions if m["hp"] > 0]
                if alive_minions:
                    target_minion = alive_minions[0]
                    target_minion["hp"] = max(0, target_minion["hp"] - damage)
                    logs.append(f"   → Daño redirigido a {target_minion['name']}: **{damage}** daño.")
                    if target_minion["hp"] <= 0:
                        logs.append(f"💀 **{target_minion['name']}** ha sido destruido!")
                else:
                    # Daño al jefe
                    self.boss.hp = max(0, self.boss.hp - damage)
                    total_damage_dealt_this_turn += damage
                    # Acumular daño para la verificación de canalización
                    if self.boss_channeling:
                        self.boss_channeled_damage += damage
                    crit_text = " **¡CRÍTICO!**" if crit else ""
                    logs.append(f"   → Daño al jefe: **{damage}** daño{crit_text}.")

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

        # Si el boss estaba canalizando su Ultimate, resolver la canalización
        if self.boss_channeling:
            self.boss_channeling = False
            # Registrar daño acumulado
            if self.boss_channeled_damage >= self.boss_channeling_threshold:
                logs.append(f"✨ **¡INTERRUMPIDO!** El grupo infligió {self.boss_channeled_damage} daño, aturdiendo a {self.boss.name} y cancelando su ataque definitivo.")
            else:
                logs.append(f"💥 **¡FALLIDO!** El grupo solo infligió {self.boss_channeled_damage}/{self.boss_channeling_threshold} daño. {self.boss.name} desata su golpe definitivo!")
                ult_dmg = int(self.boss.atk * 2.5)
                # Daño en área masivo a todos los jugadores
                for target_p in alive:
                    apply_damage_to_player(target_p, ult_dmg)
            boss_attacked = True

        # Si no atacó con su Ultimate, realizar su ataque normal / especial
        if not boss_attacked:
            # Comprobar provocación (taunt)
            taunters = [p for p in alive if p.is_taunting]
            if taunters:
                target = random.choice(taunters)
            else:
                target = random.choice(alive)

            # Modificador del afijo "Enfurecido"
            boss_atk_val = self.boss.atk
            if self.affix == "Enfurecido" and (self.boss.hp / self.boss.max_hp) < 0.35:
                boss_atk_val = int(boss_atk_val * 1.30)
                logs.append(f"⚡ **Enfurecido:** ¡{self.boss.name} ruge con furia, aumentando su ATK!")

            boss_dmg = int(boss_atk_val * random.uniform(0.85, 1.15))
            logs.append(f"{self.boss.emoji} {self.boss.name} ataca a {target.user.display_name}:")
            apply_damage_to_player(target, boss_dmg)

            # Habilidad especial del boss (cada 3 turnos, si no está aturdido)
            if (self.turn_count + 1) % BOSS_SPECIAL_INTERVAL == 0:
                special_logs = self._execute_boss_ability()
                logs.extend(special_logs)

        # 7. Aplicar veneno de Rogue (Pícaro) al jefe
        if self.boss_poison_turns > 0:
            self.boss.hp = max(0, self.boss.hp - self.boss_poison_damage)
            self.boss_poison_turns -= 1
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
            if p.class_ability_cooldown > 0:
                p.class_ability_cooldown -= 1
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
            new_view = RaidCombatView(self.players, self.boss, self.cog, self.affix)
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
            try:
                if self.interaction_msg:
                    await self.interaction_msg.edit(embed=embed, view=new_view)
            except Exception:
                pass
            self.stop()
            return

        await interaction.message.edit(embed=embed, view=self)

    def _execute_boss_ability(self) -> list[str]:
        """Ejecuta la habilidad especial del boss. Retorna líneas de log."""
        logs = []
        ability = self.boss.ability
        alive = self._alive_players()

        if not alive:
            return logs

        ab_type = ability["type"]
        logs.append(f"\n{ability['emoji']} **¡{self.boss.name} usa {ability['name']}!**")

        if ab_type == "aoe_damage":
            # Daño a todos los jugadores
            base = int(self.boss.atk * ability["damage_mult"])
            for p in alive:
                dmg = int(base * random.uniform(0.85, 1.15))
                if p.is_defending:
                    dmg = max(1, int(dmg * 0.4))
                p.hp = max(0, p.hp - dmg)
                logs.append(f"   → {p.user.display_name}: **{dmg}** daño")
                if p.hp <= 0:
                    p.is_dead = True
                    logs.append(f"   💀 **{p.user.display_name}** ha caído!")

        elif ab_type == "single_target_dot":
            # Daño + veneno al jugador con más HP
            target = max(alive, key=lambda p: p.hp)
            base = int(self.boss.atk * ability["damage_mult"])
            dmg = int(base * random.uniform(0.85, 1.15))
            if target.is_defending:
                dmg = max(1, int(dmg * 0.4))
            target.hp = max(0, target.hp - dmg)
            target.poison_turns = ability["dot_turns"]
            target.poison_damage = ability["dot_damage"]
            logs.append(
                f"   → Muerde a {target.user.display_name}: **{dmg}** daño "
                f"+ 🧪 Envenenado ({ability['dot_damage']}/t por {ability['dot_turns']} turnos)"
            )
            if target.hp <= 0:
                target.is_dead = True
                logs.append(f"   💀 **{target.user.display_name}** ha caído!")

        elif ab_type == "aoe_damage_heal":
            # Daño a todos + boss se cura
            base = int(self.boss.atk * ability["damage_mult"])
            for p in alive:
                dmg = int(base * random.uniform(0.85, 1.15))
                if p.is_defending:
                    dmg = max(1, int(dmg * 0.4))
                p.hp = max(0, p.hp - dmg)
                logs.append(f"   → {p.user.display_name}: **{dmg}** daño")
                if p.hp <= 0:
                    p.is_dead = True
                    logs.append(f"   💀 **{p.user.display_name}** ha caído!")

            heal = int(self.boss.max_hp * ability["heal_pct"])
            self.boss.hp = min(self.boss.max_hp, self.boss.hp + heal)
            logs.append(f"   💚 {self.boss.name} se regenera **{heal}** HP.")

        elif ab_type == "aoe_drain":
            # Roba HP de todos
            total_drained = 0
            for p in alive:
                drain = max(1, int(p.hp * ability["drain_pct"]))
                if p.is_defending:
                    drain = max(1, int(drain * 0.5))
                p.hp = max(0, p.hp - drain)
                total_drained += drain
                logs.append(f"   → Drena {p.user.display_name}: **{drain}** HP robado")
                if p.hp <= 0:
                    p.is_dead = True
                    logs.append(f"   💀 **{p.user.display_name}** ha caído!")
            self.boss.hp = min(self.boss.max_hp, self.boss.hp + total_drained)
            logs.append(f"   💜 {self.boss.name} se cura **{total_drained}** HP con la energía robada.")

        elif ab_type == "aoe_debuff":
            # Daño + reduce ATK de todos
            base = int(self.boss.atk * ability["damage_mult"])
            for p in alive:
                dmg = int(base * random.uniform(0.85, 1.15))
                if p.is_defending:
                    dmg = max(1, int(dmg * 0.4))
                p.hp = max(0, p.hp - dmg)
                p.atk_debuff_turns = ability["debuff_turns"]
                p.atk_debuff_pct = ability["atk_reduction_pct"]
                logs.append(
                    f"   → {p.user.display_name}: **{dmg}** daño + ❄️ ATK -{int(ability['atk_reduction_pct']*100)}% "
                    f"por {ability['debuff_turns']} turnos"
                )
                if p.hp <= 0:
                    p.is_dead = True
                    logs.append(f"   💀 **{p.user.display_name}** ha caído!")

        elif ab_type == "single_nuke":
            # Daño masivo a 1 jugador aleatorio
            target = random.choice(alive)
            base = int(self.boss.atk * ability["damage_mult"])
            dmg = int(base * random.uniform(0.90, 1.10))
            if target.is_defending:
                dmg = max(1, int(dmg * 0.4))
            target.hp = max(0, target.hp - dmg)
            logs.append(f"   ⚡ ¡{self.boss.name} lanza un rayo devastador a {target.user.display_name}! **{dmg}** daño")
            if target.hp <= 0:
                target.is_dead = True
                logs.append(f"   💀 **{target.user.display_name}** ha caído!")

        elif ab_type == "self_buff":
            # Muta stats del boss aleatoriamente
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

        # Estado de cada jugador
        for p in self.players:
            icon = "🟢" if not p.is_dead else "💀"
            hp_text = f"{p.hp}/{p.max_hp} HP" if not p.is_dead else "CAÍDO"
            embed.add_field(
                name=f"{icon} {p.user.display_name}",
                value=hp_text,
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
                self.turn_count, total_level
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
        channel = None
        if self.interaction_msg:
            channel = self.interaction_msg.channel

        for p in self.players:
            # Determinar tasa de drop y bonus de rareza
            if victory:
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
                loot = generate_raid_loot(p.level, rarity_bonus)
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

                if effective_channel is None:
                    logger.warning(
                        "Drop de raid generado para %s pero no hay canal. Loot: %s",
                        getattr(p.user, "name", "desconocido"), loot,
                    )
                    continue

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


def log_raid(boss_name: str, participants: list, result: str, turns: int, total_level: int):
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
                Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT INTO RaidLog (BossName, Participants, Result, Turns, TotalLevel)
            VALUES (%s, %s, %s, %s, %s)
        """, (boss_name, psycopg2.extras.Json(participants), result, turns, total_level))


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

        # Obtener boss del día
        boss_config = get_today_boss()

        # Marcar como activo
        self.active_raids.add(user_id)

        # Crear lobby
        lobby = RaidLobbyView(user, boss_config, self)
        lobby.player_stats[user_id] = stats

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
            p_equip = await asyncio.to_thread(get_user_equipment, p.id)
            combatants.append(RaidCombatant(
                p, p_stats['level'], p_equip, p_stats.get('combat_class')
            ))

        # Calcular stats del boss
        total_level = sum(c.level for c in combatants)
        boss = RaidBoss(boss_config, total_level)

        # Seleccionar afijo aleatorio de la arena
        affix_name = random.choice(list(RAID_AFFIXES.keys()))

        # Crear vista de combate con afijo
        combat_view = RaidCombatView(combatants, boss, self, affix=affix_name)
        combat_embed = combat_view._build_embed()

        combat_msg = await interaction.followup.send(embed=combat_embed, view=combat_view)
        combat_view.interaction_msg = combat_msg


async def setup(bot):
    await bot.add_cog(RaidsCog(bot))
    logger.info("Raids cog loaded successfully.")
