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
    RAID_BOSSES,
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

    def __init__(self, players: list[RaidCombatant], boss: RaidBoss, cog: 'RaidsCog'):
        super().__init__(timeout=RAID_TURN_TIMEOUT)
        self.players = players
        self.boss = boss
        self.cog = cog

        # Acciones elegidas por cada jugador (user_id -> action)
        self.actions: dict[int, str] = {}

        self.turn_count = 0
        self.game_over = False
        self._rewards_done = False
        self.action_log: list[str] = []
        self.interaction_msg = None

    def _alive_players(self) -> list[RaidCombatant]:
        """Retorna los jugadores que siguen vivos."""
        return [p for p in self.players if not p.is_dead]

    def _build_embed(self):
        alive = self._alive_players()
        total_alive = len(alive)
        total_players = len(self.players)

        # Boss HP bar
        boss_hp_bar = format_hp_bar(max(0, self.boss.hp), self.boss.max_hp, size=20)

        embed = discord.Embed(
            title=f"{self.boss.emoji} Raid — {self.boss.name}",
            description=(
                f"**Ronda {self.turn_count + 1}** · "
                f"Jugadores vivos: {total_alive}/{total_players}\n"
                f"Habilidad especial en: **{BOSS_SPECIAL_INTERVAL - (self.turn_count % BOSS_SPECIAL_INTERVAL)}** turnos"
            ),
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

            # Acción elegida
            action_status = ""
            if not p.is_dead:
                if p.user.id in self.actions:
                    action_status = " · 🟢 ¡Listo!"
                else:
                    action_status = " · 🔴 Eligiendo..."

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

        embed.set_footer(text=f"Acciones: ⚔️ Atacar · 🛡️ Defender · Tiempo por ronda: {RAID_TURN_TIMEOUT}s")
        return embed

    # ──────────────────── BOTONES ────────────────────

    @discord.ui.button(label="⚔️ Atacar", style=discord.ButtonStyle.danger, row=0)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._register_action(interaction, 'attack')

    @discord.ui.button(label="🛡️ Defender", style=discord.ButtonStyle.primary, row=0)
    async def defend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._register_action(interaction, 'defend')

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

        # 1. Aplicar DOTs (veneno) a jugadores
        for p in alive:
            if p.poison_turns > 0:
                dmg = min(p.hp, p.poison_damage)
                p.hp = max(0, p.hp - dmg)
                p.poison_turns -= 1
                logs.append(f"🧪 **Veneno:** {p.user.display_name} sufre **{dmg}** daño.")
                if p.hp <= 0:
                    p.is_dead = True
                    logs.append(f"💀 **{p.user.display_name}** ha caído por veneno!")

        # Decrementar debuffs
        for p in alive:
            if p.atk_debuff_turns > 0:
                p.atk_debuff_turns -= 1
                if p.atk_debuff_turns <= 0:
                    p.atk = p.base_atk  # Restaurar ATK
                    logs.append(f"❄️ El debuff de ATK de {p.user.display_name} ha terminado.")

        # 2. Procesar acciones de jugadores
        alive = self._alive_players()  # Refrescar por si murieron por DOT
        total_damage_to_boss = 0

        for p in alive:
            action = self.actions.get(p.user.id, 'timeout')

            if action == 'attack':
                # Calcular daño al boss
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

                total_damage_to_boss += damage
                crit_text = " **¡CRÍTICO!**" if crit else ""
                logs.append(f"⚔️ {p.user.display_name} ataca al boss → **{damage}** daño{crit_text}")

            elif action == 'defend':
                p.is_defending = True
                heal = calc_defend_heal(p.max_hp)
                p.hp = min(p.max_hp, p.hp + heal)
                logs.append(f"🛡️ {p.user.display_name} se defiende y recupera **{heal}** HP.")

            elif action == 'timeout':
                logs.append(f"⏰ {p.user.display_name} no respondió a tiempo.")

        # Aplicar daño al boss
        self.boss.hp = max(0, self.boss.hp - total_damage_to_boss)

        # 3. ¿Boss derrotado?
        if self.boss.hp <= 0:
            self.game_over = True
            logs.append(f"🎉 **¡{self.boss.name} ha sido derrotado!**")
            self.action_log.extend(logs)
            if len(self.action_log) > 8:
                self.action_log = self.action_log[-8:]
            await self._finish_raid(interaction, victory=True)
            return

        # 4. Ataque del Boss
        alive = self._alive_players()
        if not alive:
            self.game_over = True
            logs.append(f"💀 **Todos los jugadores han caído. {self.boss.name} es victorioso.**")
            self.action_log.extend(logs)
            if len(self.action_log) > 8:
                self.action_log = self.action_log[-8:]
            await self._finish_raid(interaction, victory=False)
            return

        # Ataque normal del boss a un jugador aleatorio
        target = random.choice(alive)
        boss_dmg = int(self.boss.atk * random.uniform(0.85, 1.15))
        if target.is_defending:
            boss_dmg = max(1, int(boss_dmg * 0.4))
            logs.append(
                f"{self.boss.emoji} {self.boss.name} ataca a {target.user.display_name} → "
                f"**{boss_dmg}** daño *(bloqueado parcialmente)*"
            )
        else:
            logs.append(
                f"{self.boss.emoji} {self.boss.name} ataca a {target.user.display_name} → "
                f"**{boss_dmg}** daño"
            )
        target.hp = max(0, target.hp - boss_dmg)
        if target.hp <= 0:
            target.is_dead = True
            logs.append(f"💀 **{target.user.display_name}** ha caído!")

        # 5. Habilidad especial del boss (cada N turnos)
        if (self.turn_count + 1) % BOSS_SPECIAL_INTERVAL == 0:
            special_logs = self._execute_boss_ability()
            logs.extend(special_logs)

        # 6. Limpiar estados
        for p in self.players:
            p.is_defending = False
        self.actions.clear()

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
            new_view = RaidCombatView(self.players, self.boss, self.cog)
            new_view.turn_count = self.turn_count
            new_view.action_log = self.action_log
            new_view.interaction_msg = self.interaction_msg
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

        # Crear vista de combate
        combat_view = RaidCombatView(combatants, boss, self)
        combat_embed = combat_view._build_embed()

        combat_msg = await interaction.followup.send(embed=combat_embed, view=combat_view)
        combat_view.interaction_msg = combat_msg


async def setup(bot):
    await bot.add_cog(RaidsCog(bot))
    logger.info("Raids cog loaded successfully.")
