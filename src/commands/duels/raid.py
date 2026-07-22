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
    db_cursor, add_combat_currency,
    get_consumable_catalog, get_user_consumables, use_consumable,
    get_gem_catalog, buy_consumable_discounted, insert_gem_discounted,
)
from src.utils.combat_progression import (
    calc_base_stats, calc_equipment_bonus, get_effective_bonus,
    calc_attack_damage, calc_defend_heal, calc_sell_price,
    generate_loot,
    format_hp_bar, format_stat_type,
    get_combat_rank, get_combat_rank_emoji,
    EQUIPMENT_SLOTS, SLOT_EMOJIS, RARITY_COLORS,
    LOOT_TIMEOUT_SECONDS, ALL_STATS, format_item_stats_display,
    apply_subclass_equipment_conversion, format_currency,
    get_equipped_set_pieces, EQUIPMENT_SETS_CACHE, load_equipment_sets_cache,
    can_proc, mark_proc,
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

EQUIPMENT_ULTIMATE_FILL_RATE = 0.15


# ══════════════════════════════════════════════
# BOSS EN COMBATE
# ══════════════════════════════════════════════

from src.commands.duels.raid.boss import RaidBoss
from src.commands.duels.raid.combatant import RaidCombatant
from src.commands.duels.raid.lobby_view import RaidLobbyView, get_combatant_available_skills
from src.commands.duels.raid.skill_views import PersonalSkillSelectView, PersonalRaidConsumableSelectView, RaidSilenceTargetSelectView
# ══════════════════════════════════════════════
# VISTA: COMBATE DE RAID
# ══════════════════════════════════════════════

def trigger_fury_phase(view, logs: list[str]):
    from src.utils.raid_config import MINION_ARCHETYPES
    view.boss.fury_phase_triggered = True

    # 1. Oleada de refuerzos (1 esbirro del pool, no 2)
    if view.boss.minion_pool:
        pool = view.boss.minion_pool if isinstance(view.boss.minion_pool, list) else list(MINION_ARCHETYPES.keys())
        key = random.choice(pool)
        new_minion = build_minions_from_pool({"minion_pool": [key]})[0]
        view.minions.append(new_minion)
        logs.append(f"\n👾 **¡Refuerzos de Furia!** Aparece **{new_minion['name']}** para proteger al jefe.")

    # 2. Dominación
    alive = view._alive_players()
    num_dominated = 2 if len(view.players) >= 4 else 1
    dominated = random.sample(alive, min(num_dominated, len(alive)))
    for p in dominated:
        p.dominated_turns = 1
        logs.append(f"😵 **¡Dominación!** {p.user.display_name} ha sido dominado por el abismo. ¡Su próximo ataque golpeará a un aliado!")

    # 3. Marcar el stun grupal pendiente para la próxima ronda
    for p in alive:
        p.fury_stun_pending = True
    logs.append("⚠️ **¡Advertencia!** El jefe acumula energía sísmica... El grupo será aturdido el próximo turno. ¡Prepárense!")


def get_raid_pkg():
    import sys
    return sys.modules["src.commands.duels.raid"]


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

        # Check Abyssus sets logs
        for p in self.players:
            if hasattr(p, "abyssus_log"):
                self.action_log.append(p.abyssus_log)

        # Nuevos estados de mecánicas dinámicas y estados
        self.minions: list[dict] = []
        self.minions_summoned = False
        self.boss_channeling = False
        self.boss_channeled_damage = 0
        self.boss_channeling_threshold = 0
        self.boss_poison_turns = 0
        self.boss_poison_damage = 0
        if not hasattr(self.boss, "silence_turns"):
            self.boss.silence_turns = 0
        self.equipment_ultimate_charge = 0.0

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
        # Ultimate de Equipo
        filled_blocks = int(self.equipment_ultimate_charge / 10)
        empty_blocks = 10 - filled_blocks
        bar_str = "█" * filled_blocks + "░" * empty_blocks
        ult_bar = f"[{bar_str}] {int(self.equipment_ultimate_charge)}%"

        # Actualizar estado del botón de Ultimate de Equipo
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label == "💥 Ultimate de Equipo":
                child.disabled = self.equipment_ultimate_charge < 100.0

        desc = (
            f"**Ronda {self.turn_count + 1}** · "
            f"Jugadores vivos: {total_alive}/{total_players}\n"
            f"**Afijo:** {affix_info['emoji']} **{self.affix}** — *{affix_info['desc']}*\n"
            f"Habilidad especial en: **{BOSS_SPECIAL_INTERVAL - (self.turn_count % BOSS_SPECIAL_INTERVAL)}** turnos\n"
            f"💥 **Ultimate de Equipo:** {ult_bar}"
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
            name=f"{self.boss.emoji} {self.boss.name} (Fase {self.boss.phase}/3) — Nv. ∞{boss_status}",
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

    @discord.ui.button(label="🧪 Usar Consumible", style=discord.ButtonStyle.success, row=1)
    async def consumable_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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

        if user_id in self.actions:
            await interaction.response.send_message("❌ Ya elegiste tu acción.", ephemeral=True)
            return

        user_consumables = await asyncio.to_thread(get_user_consumables, user_id)
        if not user_consumables:
            await interaction.response.send_message("❌ No tienes consumibles. Cómpralos con `/consumibles`.", ephemeral=True)
            return

        catalog = await asyncio.to_thread(get_consumable_catalog)
        options = []
        for key, qty in user_consumables.items():
            c_info = next((item for item in catalog if item['consumable_key'] == key), None)
            name = c_info['name'] if c_info else key
            desc = c_info['description'] if c_info else ""
            options.append(
                discord.SelectOption(
                    label=f"{name} (Tienes: {qty})",
                    value=key,
                    description=desc[:100]
                )
            )

        view = PersonalRaidConsumableSelectView(raid_view=self, player=player, options=options)
        await interaction.response.send_message("Elige tu consumible:", view=view, ephemeral=True)

    @discord.ui.button(label="💥 Ultimate de Equipo", style=discord.ButtonStyle.blurple, row=2, disabled=True)
    async def equipment_ultimate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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

        if self.equipment_ultimate_charge < 100.0:
            await interaction.response.send_message("❌ La barra de Ultimate de Equipo no está al 100%.", ephemeral=True)
            return

        if user_id in self.actions:
            await interaction.response.send_message("❌ Ya elegiste tu acción.", ephemeral=True)
            return

        # Consumir la barra inmediatamente para evitar que otros lo presionen
        self.equipment_ultimate_charge = 0.0
        button.disabled = True

        await self._register_action(interaction, 'ultimate_equipo')

    async def _register_action(self, interaction: discord.Interaction, action: str, is_ephemeral: bool = False):
        should_defer = not is_ephemeral

        if should_defer and not interaction.response.is_done():
            await interaction.response.defer()

        if self.game_over:
            if is_ephemeral:
                await interaction.followup.send("❌ La raid ya terminó.", ephemeral=True)
            else:
                await interaction.followup.send("❌ La raid ya terminó.", ephemeral=True)
            return

        user_id = interaction.user.id

        # Verificar que es un participante
        player = next((p for p in self.players if p.user.id == user_id), None)
        if player is None:
            if is_ephemeral:
                await interaction.followup.send("❌ No participas en esta raid.", ephemeral=True)
            else:
                await interaction.followup.send("❌ No participas en esta raid.", ephemeral=True)
            return

        if player.is_dead:
            if is_ephemeral:
                await interaction.followup.send("❌ Has caído en combate.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Has caído en combate.", ephemeral=True)
            return

        if user_id in self.actions:
            if is_ephemeral:
                await interaction.followup.send("❌ Ya elegiste tu acción.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Ya elegiste tu acción.", ephemeral=True)
            return

        self.actions[user_id] = action

        # ¿Ya todos eligieron?
        alive = self._alive_players()
        all_ready = all(p.user.id in self.actions for p in alive)

        if all_ready:
            if is_ephemeral:
                await self._resolve_round(None)
            else:
                await self._resolve_round(interaction)
        else:
            embed = self._build_embed()
            if is_ephemeral:
                if self.interaction_msg:
                    await self.interaction_msg.edit(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)

    # ──────────────────── RESOLUCIÓN ────────────────────

    async def _resolve_round(self, interaction=None):
        """Resuelve la ronda: acciones de jugadores → IA del boss."""
        logs = [f"🏁 **Ronda {self.turn_count + 1}:**"]

        # 0. Aplicar el stun grupal pendiente de Fase de Furia al inicio del turno
        for p in self._alive_players():
            if p.fury_stun_pending:
                p.fury_stun_pending = False
                p.stun_turns = max(p.stun_turns, 1)
                logs.append(f"😵 **Furia del Jefe:** ¡{p.user.display_name} es aturdido por la onda de choque!")
        
        # Configurar intangibilidad para Espíritu Errante (Ronda 2, 4, 6... -> turn_count % 2 == 1)
        if getattr(self.boss, "miniboss_key", None) == "espiritu_errante" and (self.turn_count % 2 == 1):
            self.boss.is_intangible = True
            logs.append("👻 **Espíritu Errante:** ¡El jefe se vuelve intangible este turno! Es inmune a todo el daño.")
        else:
            self.boss.is_intangible = False

        alive = self._alive_players()

        # Helper para aplicar daño a jugadores (con pasivos)
        def apply_damage_to_player(target, raw_dmg, is_boss_attack=False):
            self._apply_damage_to_player(target, raw_dmg, logs, is_boss_attack)

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
                    hot_heal = int(hot_heal * (1.0 + p.healing_bonus_pct))
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
                    regen_heal = int(regen_heal * (1.0 + p.healing_bonus_pct))
                    p.hp = min(p.max_hp, p.hp + regen_heal)
                    logs.append(f"💚 **Regeneración:** {p.user.display_name} recupera **{regen_heal}** HP.")

        # 2.6. Progresión de Fases del Boss
        hp_pct = self.boss.hp / self.boss.max_hp if self.boss.max_hp > 0 else 0
        new_phase = 3 if hp_pct <= 0.33 else (2 if hp_pct <= 0.66 else 1)

        if new_phase != self.boss.phase:
            self.boss.phase = new_phase
            if new_phase == 2 and self.boss.phase2_ability_id:
                self.boss.ability_id = self.boss.phase2_ability_id
                self.boss.ability = BOSS_ABILITIES[self.boss.ability_id]
                logs.append(f"\n⚡ **¡{self.boss.name} entra en su segunda fase!** Su patrón de ataque cambia.")
            elif new_phase == 3:
                if self.boss.phase3_ability_id:
                    self.boss.ability_id = self.boss.phase3_ability_id
                    self.boss.ability = BOSS_ABILITIES[self.boss.ability_id]
                logs.append(f"\n🔥 **¡{self.boss.name} entra en su fase final!**")
                if not self.boss.fury_phase_triggered:
                    trigger_fury_phase(self, logs)

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
                if m.get("silence_turns", 0) > 0:
                    logs.append(f"🤫 {m['name']} está silenciado y no puede debilitar este turno.")
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

        # --- IA Automática de Mascotas de Raid ---
        for p in alive:
            b_pct = (self.boss.hp / self.boss.max_hp) if self.boss.max_hp > 0 else 1.0
            pet_msg = p.execute_pet_raid_ai(b_pct, getattr(self.boss, "fury_phase_triggered", False))
            if pet_msg:
                logs.append(pet_msg)

        # 4. Procesar acciones de jugadores
        for pl in self.players:
            pl.pre_hit_hp = pl.hp
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
            if p.blinded_turns > 0 and action != "defend" and action != "timeout" and not action.startswith("consumable:"):
                if random.random() < 0.5:
                    logs.append(f"👁️ **Ceguera:** ¡{p.user.display_name} está cegado y falla su acción!")
                    continue

            if action.startswith("consumable:"):
                parts = action.split(":")
                ckey = parts[1]
                if ckey == "pocion_curacion":
                    if p.anti_heal_turns == 0:
                        heal_amt = int(p.max_hp * 0.25)
                        heal_amt = int(heal_amt * (1.0 + p.healing_bonus_pct))
                        p.hp = min(p.max_hp, p.hp + heal_amt)
                        logs.append(f"🧪 **Poción de Curación:** {p.user.display_name} usa una poción y se cura **{heal_amt}** HP. ({p.hp}/{p.max_hp} HP)")
                    else:
                        logs.append(f"🧪 **Poción de Curación:** {p.user.display_name} usa una poción, pero tiene anti-curación y no se cura.")
                elif ckey == "pergamino_purificacion":
                    # Limpiar todos los debuffs
                    p.poison_turns = 0
                    p.poison_damage = 0
                    p.atk_debuff_turns = 0
                    p.atk_debuff_pct = 0.0
                    p.stun_turns = 0
                    p.frozen_turns = 0
                    p.silence_turns = 0
                    p.bleed_turns = 0
                    p.anti_heal_turns = 0
                    p.weakness_turns = 0
                    p.weakness_pct = 0.0
                    p.fragility_turns = 0
                    p.fragility_pct = 0.0
                    p.vulnerability_turns = 0
                    p.vulnerability_pct = 0.0
                    p.enhanced_burn_turns = 0
                    p.burn_turns = 0
                    p.blinded_turns = 0
                    logs.append(f"📜 **Pergamino de Purificación:** {p.user.display_name} usa un pergamino y limpia todos sus estados alterados.")
                elif ckey == "bomba_humo":
                    p.guaranteed_dodge_next = True
                    logs.append(f"💨 **Bomba de Humo:** {p.user.display_name} lanza una bomba de humo y se oculta. ¡Garantiza esquivar el próximo golpe!")
                elif ckey == "pocion_curacion_colectiva":
                    for ally in self._alive_players():
                        if ally.anti_heal_turns == 0:
                            heal_amt = int(ally.max_hp * 0.30)
                            heal_amt = int(heal_amt * (1.0 + ally.healing_bonus_pct))
                            ally.hp = min(ally.max_hp, ally.hp + heal_amt)
                    logs.append(f"🧪 **Poción de Curación Colectiva:** {p.user.display_name} usa una poción mágica y cura **30% HP** a todo el equipo.")
                elif ckey == "totem_baluarte":
                    for ally in self._alive_players():
                        shield_val = int(ally.max_hp * 0.20)
                        ally.shield += shield_val
                    logs.append(f"🛡️ **Tótem de Baluarte:** {p.user.display_name} despliega un tótem que otorga un escudo de **20% HP** a todo el grupo.")
                elif ckey == "pergamino_purificacion_grupo":
                    for ally in self._alive_players():
                        ally.stun_turns = 0
                        ally.frozen_turns = 0
                        ally.silence_turns = 0
                        ally.weakness_turns = 0
                        ally.fragility_turns = 0
                        ally.vulnerability_turns = 0
                        ally.bleed_turns = 0
                        ally.anti_heal_turns = 0
                        ally.poison_turns = 0
                        ally.atk_debuff_turns = 0
                    logs.append(f"📜 **Pergamino de Purificación de Grupo:** {p.user.display_name} purifica todas las afecciones de todo el equipo.")
                elif ckey == "elixir_ultimate":
                    self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + 30.0)
                    logs.append(f"⚡ **Elixir de Carga de Ultimate:** {p.user.display_name} consume un elixir místico y recarga **+30%** la barra de Ultimate de Equipo.")
                elif ckey == "manjar_companero":
                    logs.append(f"🥩 **Manjar del Compañero:** {p.user.display_name} alimenta a su mascota, restaurando su lealtad al 100%.")
                elif ckey == "frasco_silencio":
                    target_type = parts[2] if len(parts) > 2 else "boss"
                    if target_type == "boss":
                        self.boss.silence_turns = 3
                        logs.append(f"🤫 **Frasco de Silencio:** {p.user.display_name} lanza un frasco a {self.boss.name}. ¡Lo silencia por 2 turnos!")
                    elif target_type == "minion" and len(parts) > 3:
                        m_idx = int(parts[3])
                        if m_idx < len(self.minions):
                            m = self.minions[m_idx]
                            m["silence_turns"] = 3
                            logs.append(f"🤫 **Frasco de Silencio:** {p.user.display_name} lanza un frasco a {m['name']}. ¡Lo silencia por 2 turnos!")
                    else:
                        self.boss.silence_turns = 3
                        logs.append(f"🤫 **Frasco de Silencio:** {p.user.display_name} lanza un frasco a {self.boss.name}. ¡Lo silencia por 2 turnos!")
                continue


            if action == "ultimate_equipo":
                alive_players = self._alive_players()
                total_power = sum(pl.atk + pl.mag for pl in alive_players)
                ultimate_damage = int(total_power * 0.40)

                # Reset de la barra de Ultimate (por seguridad)
                self.equipment_ultimate_charge = 0.0

                targets = [self.boss] + [m for m in self.minions if m.get("hp", 0) > 0]
                for target in targets:
                    if target == self.boss:
                        self.boss.hp = max(0, self.boss.hp - ultimate_damage)
                        total_damage_dealt_this_turn += ultimate_damage
                        if self.boss_channeling:
                            self.boss_channeled_damage += ultimate_damage
                    else:
                        target["hp"] = max(0, target["hp"] - ultimate_damage)
                        if target["hp"] <= 0:
                            logs.append(f"💀 **{target['name']}** ha sido destruido!")

                logs.append(f"💥 **¡Ultimate de Equipo!** {p.user.display_name} activa el poder combinado del grupo, infligiendo **{ultimate_damage}** de daño a todos los enemigos!")
                continue

            if action == 'attack':
                if p.dominated_turns > 0:
                    p.dominated_turns -= 1
                    ally_targets = [ally for ally in self._alive_players() if ally.user.id != p.user.id]
                    if ally_targets:
                        victim = random.choice(ally_targets)
                        effective_atk = p.atk
                        if p.atk_buff_turns > 0:
                            effective_atk = int(effective_atk * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            effective_atk = int(effective_atk * (1.0 - p.weakness_pct))

                        base_dmg = effective_atk * random.uniform(0.85, 1.15)
                        victim_def = victim.def_stat
                        if victim.fragility_turns > 0:
                            victim_def = int(victim_def * (1.0 - victim.fragility_pct))

                        damage_to_ally = max(1, int(base_dmg - victim_def * 0.35))
                        
                        # Modificadores de daño por subtipo de arma (Lanza +10% si rival defendió, Hacha +15%)
                        weapon_item = p.equipment.get("Arma")
                        if weapon_item and weapon_item.get("weapon_subtype"):
                            sub = weapon_item["weapon_subtype"]
                            if sub == "lanza":
                                if getattr(victim, "last_action", None) == "defend":
                                    damage_to_ally = int(damage_to_ally * 1.10)
                            elif sub == "hacha":
                                damage_to_ally = int(damage_to_ally * 1.15)

                        crit_chance = 0.10
                        if p.has_crit_boost:
                            crit_chance += 0.10
                        if any(pass_item['id'] == 'hawk_strike' for pass_item in p.passives):
                            crit_chance += 0.08
                        crit_chance += p.subclass_extras.get("crit_chance_bonus", 0.0)

                        crit = random.random() < crit_chance
                        if crit:
                            crit_mult = 1.5 + p.subclass_extras.get("crit_mult_bonus", 0.0)
                            damage_to_ally = int(damage_to_ally * crit_mult)
                            crit_text = " **¡CRÍTICO!**"
                        else:
                            crit_text = ""

                        logs.append(f"😵 **Dominado:** ¡{p.user.display_name} ataca a su aliado {victim.user.display_name} en vez del enemigo!{crit_text}")
                        apply_damage_to_player(victim, damage_to_ally)
                        damage = 0
                    else:
                        # Ataque normal si no hay aliados
                        effective_atk = p.atk
                        if p.atk_buff_turns > 0:
                            effective_atk = int(effective_atk * (1.0 + p.atk_buff_pct))
                        if p.weakness_turns > 0:
                            effective_atk = int(effective_atk * (1.0 - p.weakness_pct))

                        base_dmg = effective_atk * random.uniform(0.85, 1.15)
                        target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                        if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                            target_def = int(target_def * (1.0 - active_target.fragility_pct))
                        elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                            target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))

                        damage = max(1, int(base_dmg - target_def * 0.35))
                        
                        # Modificadores de daño por subtipo de arma (Lanza +10% si rival defendió, Hacha +15%)
                        weapon_item = p.equipment.get("Arma")
                        if weapon_item and weapon_item.get("weapon_subtype"):
                            sub = weapon_item["weapon_subtype"]
                            if sub == "lanza":
                                if getattr(active_target, "last_action", None) == "defend":
                                    damage = int(damage * 1.10)
                            elif sub == "hacha":
                                damage = int(damage * 1.15)

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
                else:
                    # Ataque normal sin dominación
                    effective_atk = p.atk
                    if p.atk_buff_turns > 0:
                        effective_atk = int(effective_atk * (1.0 + p.atk_buff_pct))
                    if p.weakness_turns > 0:
                        effective_atk = int(effective_atk * (1.0 - p.weakness_pct))

                    base_dmg = effective_atk * random.uniform(0.85, 1.15)
                    target_def = active_target.def_stat if hasattr(active_target, 'def_stat') else active_target.get("def_stat", 10)
                    if hasattr(active_target, 'fragility_turns') and active_target.fragility_turns > 0:
                        target_def = int(target_def * (1.0 - active_target.fragility_pct))
                    elif isinstance(active_target, dict) and active_target.get("fragility_turns", 0) > 0:
                        target_def = int(target_def * (1.0 - active_target.get("fragility_pct", 0.0)))

                    damage = max(1, int(base_dmg - target_def * 0.35))
                    
                    # Modificadores de daño por subtipo de arma (Lanza +10% si rival defendió, Hacha +15%)
                    weapon_item = p.equipment.get("Arma")
                    if weapon_item and weapon_item.get("weapon_subtype"):
                        sub = weapon_item["weapon_subtype"]
                        if sub == "lanza":
                            if getattr(active_target, "last_action", None) == "defend":
                                damage = int(damage * 1.10)
                        elif sub == "hacha":
                            damage = int(damage * 1.15)

                    crit_chance = 0.10
                    if p.has_crit_boost:
                        crit_chance += 0.10
                    if any(pass_item['id'] == 'hawk_strike' for pass_item in p.passives):
                        crit_chance += 0.08
                    crit_chance += p.subclass_extras.get("crit_chance_bonus", 0.0)

                    crit = random.random() < crit_chance
                    if crit:
                        crit_mult = 1.5 + p.subclass_extras.get("crit_mult_bonus", 0.0)
                        damage = int(damage * crit_mult)
                        crit_text = " **(¡CRÍTICO BRUTAL!)**" if p.subclass_extras.get("crit_mult_bonus", 0.0) > 0 else " **(¡CRÍTICO!)**"
                    else:
                        crit_text = ""

                    target_name = active_target.name if hasattr(active_target, 'name') else active_target['name']
                    logs.append(f"⚔️ **{p.user.display_name}** ataca a **{target_name}** infligiendo **{damage}** de daño{crit_text}!")


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
                    heal = int(heal * (1.0 + p.healing_bonus_pct))
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
                # Guardamos si era primer uso antes de marcarlo para el cálculo de daño posterior
                p.first_special_use_this_combat = not getattr(p, "special_used_this_combat", False)
                p.special_used_this_combat = True
                cfg = SKILLS_CONFIG.get(action)
                if cfg:
                    # Aplicar enfriamiento
                    skill_cd = cfg.get("cooldown", 3)
                    has_mana_residual = any(pass_item['id'] == 'mana_residual' for pass_item in p.passives)
                    if has_mana_residual:
                        skill_cd = max(1, skill_cd - 1)

                    # Modificador de cooldown por subtipo de arma (Orbe -1, Cetro +1)
                    weapon_item = p.equipment.get("Arma")
                    if weapon_item and weapon_item.get("weapon_subtype"):
                        sub = weapon_item["weapon_subtype"]
                        if sub == "orbe":
                            skill_cd = max(1, skill_cd - 1)
                        elif sub == "cetro":
                            skill_cd = skill_cd + 1

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
                        
                        if active_target == self.boss:
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
                        
                        burn_duration = cfg["turns"] + 1
                        if p.set_bonus_ignis_4pc:
                            burn_duration += 2
                        if hasattr(active_target, 'burn_turns'):
                            self.boss.burn_turns = burn_duration
                        else:
                            active_target["burn_turns"] = burn_duration
                        logs.append(f"🔥 **Tormenta de Fuego:** {p.user.display_name} usa Tormenta de Fuego y quema a {active_target.name if hasattr(active_target, 'name') else active_target['name']}!")
                    
                    elif action == "drenaje":
                        drain_pct = cfg["drain_pct"] + p.subclass_extras.get("extra_drain_pct", 0.0)
                        target_hp = active_target.hp if hasattr(active_target, 'hp') else active_target["hp"]
                        steal_amt = max(1, int(target_hp * drain_pct))
                        
                        if hasattr(active_target, 'hp'):
                            active_target.hp = max(0, active_target.hp - steal_amt)
                            self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + (steal_amt * EQUIPMENT_ULTIMATE_FILL_RATE))
                            if self.boss_channeling:
                                self.boss_channeled_damage += steal_amt
                            total_damage_dealt_this_turn += steal_amt
                        else:
                            active_target["hp"] = max(0, active_target["hp"] - steal_amt)
                            self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + (steal_amt * EQUIPMENT_ULTIMATE_FILL_RATE))
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
                                
                            burn_duration = cfg["burn_duration"] + 1
                            if p.set_bonus_ignis_4pc:
                                burn_duration += 2
                            if hasattr(enemy, 'hp'):
                                enemy.hp = max(0, enemy.hp - dmg)
                                total_damage_dealt_this_turn += dmg
                                if self.boss_channeling:
                                    self.boss_channeled_damage += dmg
                                enemy.burn_turns = burn_duration
                            else:
                                if isinstance(enemy, dict) and enemy.get("archetype") == "escudo":
                                    dmg = max(1, int(dmg * 0.5))
                                    logs.append(f"   🛡️ **Guardián de Escudo:** ¡{enemy['name']} reduce el daño recibido un 50%!")
                                enemy["hp"] = max(0, enemy["hp"] - dmg)
                                if enemy["hp"] <= 0:
                                    logs.append(f"💀 **{enemy['name']}** ha sido destruido!")
                                enemy["burn_turns"] = burn_duration
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
                        
                        burn_duration = cfg["burn_duration"] + 1
                        if p.set_bonus_ignis_4pc:
                            burn_duration += 2
                        if hasattr(active_target, 'burn_turns'):
                            active_target.burn_turns = burn_duration
                            active_target.enhanced_burn_turns = burn_duration
                        else:
                            active_target["burn_turns"] = burn_duration
                            active_target["enhanced_burn_turns"] = burn_duration
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
                        
                        burn_duration = cfg["burn_duration"] + 1
                        if p.set_bonus_ignis_4pc:
                            burn_duration += 2
                        if hasattr(active_target, 'burn_turns'):
                            active_target.burn_turns = burn_duration
                            if active_target.stun_turns > 0:
                                active_target.stun_turns += 1
                            else:
                                active_target.frozen_turns = cfg["freeze_turns"] + 1
                        else:
                            active_target["burn_turns"] = burn_duration
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
                            heal_val = int(heal_val * (1.0 + p.healing_bonus_pct + target_p.healing_bonus_pct))
                            target_p.hp = min(target_p.max_hp, target_p.hp + heal_val)
                            logs.append(f"💚 **Luz Curativa:** {p.user.display_name} cura a {target_p.user.display_name} por **{heal_val}** HP.")
                        damage = 0
                    
                    elif action == "resurreccion_parcial":
                        dead_players = [pl for pl in self.players if pl.is_dead]
                        if dead_players:
                            target_dead = dead_players[0]
                            target_dead.is_dead = False
                            revive_amt = int(target_dead.max_hp * cfg["revive_hp_pct"]) + p.subclass_extras.get("heal_power", 0)
                            revive_amt = int(revive_amt * (1.0 + p.healing_bonus_pct + target_dead.healing_bonus_pct))
                            target_dead.hp = revive_amt
                            logs.append(f"✝️ **Resurrección Parcial:** ¡{p.user.display_name} revive a {target_dead.user.display_name} con **{revive_amt}** HP!")
                        else:
                            if p.anti_heal_turns > 0:
                                logs.append(f"🚫 **Resurrección Parcial:** {p.user.display_name} se intentó curar, pero tiene anti-cura.")
                            else:
                                heal_val = int(p.max_hp * cfg["self_heal_in_duel_pct"]) + p.subclass_extras.get("heal_power", 0)
                                heal_val = int(heal_val * (1.0 + p.healing_bonus_pct))
                                p.hp = min(p.max_hp, p.hp + heal_val)
                                logs.append(f"✝️ **Resurrección Parcial:** No hay aliados caídos. ¡{p.user.display_name} se cura **{heal_val}** HP!")
                        damage = 0
                    
                    elif action == "pacto_sangre":
                        drain_pct = cfg["drain_pct"] + p.subclass_extras.get("extra_drain_pct", 0.0)
                        target_hp = active_target.hp if hasattr(active_target, 'hp') else active_target["hp"]
                        steal_amt = max(1, int(target_hp * drain_pct))
                        
                        if hasattr(active_target, 'hp'):
                            active_target.hp = max(0, active_target.hp - steal_amt)
                            self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + (steal_amt * EQUIPMENT_ULTIMATE_FILL_RATE))
                            if self.boss_channeling:
                                self.boss_channeled_damage += steal_amt
                            total_damage_dealt_this_turn += steal_amt
                        else:
                            active_target["hp"] = max(0, active_target["hp"] - steal_amt)
                            self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + (steal_amt * EQUIPMENT_ULTIMATE_FILL_RATE))
                            if active_target["hp"] <= 0:
                                logs.append(f"💀 **{active_target['name']}** ha sido destruido!")
                                
                        if p.anti_heal_turns == 0:
                            heal_amt = min(p.max_hp - p.hp, steal_amt)
                            heal_amt = int(heal_amt * (1.0 + p.healing_bonus_pct))
                            p.hp = min(p.max_hp, p.hp + heal_amt)
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
                            self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + (steal_amt * EQUIPMENT_ULTIMATE_FILL_RATE))
                            if self.boss_channeling:
                                self.boss_channeled_damage += steal_amt
                            total_damage_dealt_this_turn += steal_amt
                        else:
                            active_target["hp"] = max(0, active_target["hp"] - steal_amt)
                            self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + (steal_amt * EQUIPMENT_ULTIMATE_FILL_RATE))
                            if active_target["hp"] <= 0:
                                logs.append(f"💀 **{active_target['name']}** ha sido destruido!")
                                
                        if p.anti_heal_turns == 0:
                            heal_amt = min(p.max_hp - p.hp, steal_amt)
                            heal_amt = int(heal_amt * (1.0 + p.healing_bonus_pct))
                            p.hp = min(p.max_hp, p.hp + heal_amt)
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

            # Tomo / Cetro checks for Specials
            if action not in ('attack', 'defend', 'timeout') and damage > 0:
                weapon_item = p.equipment.get("Arma")
                if weapon_item and weapon_item.get("weapon_subtype"):
                    sub = weapon_item["weapon_subtype"]
                    if sub == "tomo":
                        if getattr(p, "first_special_use_this_combat", False):
                            damage = int(damage * 1.10)
                    elif sub == "cetro":
                        damage = int(damage * 1.15)

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
                    self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + (damage * EQUIPMENT_ULTIMATE_FILL_RATE))
                    if not is_magic:
                        target_minion["last_physical_damage_taken"] = damage
                    logs.append(f"   → Daño redirigido a {target_minion['name']}: **{damage}** daño.")
                    if target_minion["hp"] <= 0:
                        logs.append(f"💀 **{target_minion['name']}** ha sido destruido!")
                else:
                    # Daño al jefe
                    self.boss.hp = max(0, self.boss.hp - damage)
                    self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + (damage * EQUIPMENT_ULTIMATE_FILL_RATE))
                    if not is_magic:
                        self.boss.last_physical_damage_taken = damage
                    total_damage_dealt_this_turn += damage
                    # Acumular daño para la verificación de canalización
                    if self.boss_channeling:
                        self.boss_channeled_damage += damage


                # Procs de pasivos nuevos (windfury, blinding_edge, chain_lightning, deathtouch)
                if damage > 0:
                    # Pasivo: Viento de Guerra (windfury)
                    if action == 'attack':
                        if any(pass_item['id'] == 'windfury' for pass_item in p.passives) and can_proc(p, 'windfury', self.turn_count, 2):
                            if random.random() < 0.15:
                                mark_proc(p, 'windfury', self.turn_count)
                                wf_dmg = int(damage * 0.50)
                                if alive_minions:
                                    target_minion = alive_minions[0]
                                    target_minion["hp"] = max(0, target_minion["hp"] - wf_dmg)
                                    logs.append(f"🌪️ **Viento de Guerra:** ¡Un golpe adicional inflige **{wf_dmg}** de daño a {target_minion['name']}!")
                                    if target_minion["hp"] <= 0:
                                        logs.append(f"💀 **{target_minion['name']}** ha sido destruido por Viento de Guerra!")
                                else:
                                    self.boss.hp = max(0, self.boss.hp - wf_dmg)
                                    total_damage_dealt_this_turn += wf_dmg
                                    if self.boss_channeling:
                                        self.boss_channeled_damage += wf_dmg
                                    logs.append(f"🌪️ **Viento de Guerra:** ¡Un golpe adicional inflige **{wf_dmg}** de daño a {self.boss.name}!")

                    # Pasivo: Filo Cegador (blinding_edge)
                    if action == 'attack':
                        if any(pass_item['id'] == 'blinding_edge' for pass_item in p.passives) and can_proc(p, 'blinding_edge', self.turn_count, 4):
                            if random.random() < 0.08:
                                mark_proc(p, 'blinding_edge', self.turn_count)
                                if hasattr(active_target, 'blinded_turns'):
                                    active_target.blinded_turns = 3
                                    logs.append(f"🌫️ **Filo Cegador:** ¡Ceguera aplicada por 2 turnos a {active_target.name}!")
                                else:
                                    active_target["blinded_turns"] = 3
                                    logs.append(f"🌫️ **Filo Cegador:** ¡Ceguera aplicada por 2 turnos a {active_target['name']}!")

                    # Pasivo: Cadena de Tormenta (chain_lightning)
                    if action != 'attack' and action != 'defend' and action != 'timeout' and not action.startswith('consumable:') and not action == 'ultimate_equipo':
                        if alive_minions and any(pass_item['id'] == 'chain_lightning' for pass_item in p.passives) and can_proc(p, 'chain_lightning', self.turn_count, 3):
                            if random.random() < 0.10:
                                mark_proc(p, 'chain_lightning', self.turn_count)
                                cl_dmg = int(damage * 0.30)
                                cl_dmg = max(1, cl_dmg)
                                target_minion = random.choice(alive_minions)
                                target_minion["hp"] = max(0, target_minion["hp"] - cl_dmg)
                                logs.append(f"⛈️ **Cadena de Tormenta:** ¡Un rayo secundario golpea a {target_minion['name']} por **{cl_dmg}** de daño!")
                                if target_minion["hp"] <= 0:
                                    logs.append(f"💀 **{target_minion['name']}** ha sido destruido por Cadena de Tormenta!")

                    # Pasivo: Toque Letal (deathtouch)
                    target_hp = active_target.hp if hasattr(active_target, 'hp') else active_target["hp"]
                    target_max = active_target.max_hp if hasattr(active_target, 'max_hp') else active_target["max_hp"]
                    if target_hp > 0 and target_hp < target_max * 0.15:
                        if any(pass_item['id'] == 'deathtouch' for pass_item in p.passives):
                            dt_dmg = int(damage * 0.10)
                            dt_dmg = max(1, dt_dmg)
                            if hasattr(active_target, 'hp'):
                                active_target.hp = max(0, active_target.hp - dt_dmg)
                                logs.append(f"💀 **Toque Letal:** ¡{p.user.display_name} inflige **{dt_dmg}** de daño adicional de rebote a {active_target.name}!")
                                if active_target.hp <= 0:
                                    logs.append(f"🎉 **¡{active_target.name} ha sido derrotado por Toque Letal!**")
                            else:
                                active_target["hp"] = max(0, active_target["hp"] - dt_dmg)
                                logs.append(f"💀 **Toque Letal:** ¡{p.user.display_name} inflige **{dt_dmg}** de daño adicional de rebote a {active_target['name']}!")
                                if active_target["hp"] <= 0:
                                    logs.append(f"💀 **{active_target['name']}** ha sido destruido por Toque Letal!")

                # Pasivo: Vampirismo (e incluye bono de set de Thanatos)
                total_lifesteal = p.vampirism_pct + getattr(p, "next_hit_lifesteal_bonus", 0.0)
                if total_lifesteal > 0 and damage > 0:
                    if p.anti_heal_turns == 0:
                        vamp_heal = max(1, int(damage * total_lifesteal))
                        vamp_heal = int(vamp_heal * (1.0 + p.healing_bonus_pct))
                        p.hp = min(p.max_hp, p.hp + vamp_heal)
                        if getattr(p, "next_hit_lifesteal_bonus", 0.0) > 0:
                            logs.append(f"🧛 **Vampirismo (Thanatos):** {p.user.display_name} se cura **{vamp_heal}** HP (incluye +10% de Thanatos).")
                        else:
                            logs.append(f"🧛 **Vampirismo:** {p.user.display_name} se cura **{vamp_heal}** HP.")
                    p.next_hit_lifesteal_bonus = 0.0

                # Pasivo: Filo Sangrante
                if action == 'attack' and p.has_bleed_on_hit and not is_magic and damage > 0 and random.random() < 0.15:
                    active_target = alive_minions[0] if alive_minions else self.boss
                    if isinstance(active_target, dict):
                        active_target["bleed_turns"] = 3 + 1
                        active_target["bleed_source_pct"] = 0.06
                        logs.append(f"🩸 **Filo Sangrante:** ¡El ataque de {p.user.display_name} corta profundo aplicando Sangrado a {active_target['name']}!")
                    else:
                        active_target.bleed_turns = 3 + 1
                        active_target.bleed_source_pct = 0.06
                        logs.append(f"🩸 **Filo Sangrante:** ¡El ataque de {p.user.display_name} corta profundo aplicando Sangrado a {active_target.name}!")

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
                if getattr(self.boss, "silence_turns", 0) > 0:
                    logs.append(f"🤫 **Silencio:** ¡{self.boss.name} está silenciado y no puede usar su habilidad especial!")
                else:
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

        # Yggdrasil set bonus: Regeneración de grupo (cada 3 turnos)
        if self.turn_count % 3 == 0:
            ygg_healers = [p for p in self._alive_players() if p.set_bonus_yggdrasil_4pc]
            if ygg_healers:
                alive_players = self._alive_players()
                for healer in ygg_healers:
                    for target_p in alive_players:
                        if target_p.anti_heal_turns == 0:
                            heal_amt = max(1, int(target_p.max_hp * 0.03))
                            heal_amt = int(heal_amt * (1.0 + healer.healing_bonus_pct))
                            target_p.hp = min(target_p.max_hp, target_p.hp + heal_amt)
                            logs.append(f"💚 **Regeneración de Yggdrasil:** {target_p.user.display_name} se cura **{heal_amt}** HP gracias al set de {healer.user.display_name}.")

        # 8. Limpiar estados de ronda y reducir cooldowns
        for p in self.players:
            p.last_action = self.actions.get(p.user.id, 'timeout')
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

                # Aurelius 4pc low hp heal check after bleed
                if p.hp > 0 and p.hp < p.max_hp * 0.30 and p.set_bonus_aurelius_4pc and not p.low_hp_heal_used:
                    p.low_hp_heal_used = True
                    heal_amt = int(p.max_hp * 0.15)
                    heal_amt = int(heal_amt * (1.0 + p.healing_bonus_pct))
                    p.hp = min(p.max_hp, p.hp + heal_amt)
                    logs.append(f"☀️ **Set Aurelius:** ¡{p.user.display_name} baja del 30% HP y activa Destello Dorado, curándose **{heal_amt}** HP! ({p.hp}/{p.max_hp} HP)")

                if p.hp <= 0:
                    p.is_dead = True
                    logs.append(f"💀 **{p.user.display_name}** ha caído por sangrado!")
                    for ally in self.players:
                        if not ally.is_dead and ally.user.id != p.user.id and ally.set_bonus_thanatos_4pc:
                            ally.next_hit_lifesteal_bonus = 0.10
                            logs.append(f"💀 **Efecto Thanatos:** ¡La caída de un aliado otorga a {ally.user.display_name} +10% de robo de vida en su próximo golpe!")
            if not p.is_dead:
                p.turns_survived += 1

                # Pasivo: Absorción Errática (erratic_ward)
                if p.hp < p.max_hp * 0.25 and not p.used_erratic_ward and any(pass_item['id'] == 'erratic_ward' for pass_item in p.passives):
                    p.used_erratic_ward = True
                    shield_amt = int(p.max_hp * 0.10)
                    p.shield += shield_amt
                    logs.append(f"🛡️ **Absorción Errática:** ¡{p.user.display_name} baja del 25% HP y obtiene un escudo de **{shield_amt}** HP! ({p.hp}/{p.max_hp} HP)")

                # Pasivo: Sed de Batalla (bloodlust_proc)
                damage_received = p.pre_hit_hp - p.hp
                if damage_received > 0 and any(pass_item['id'] == 'bloodlust_proc' for pass_item in p.passives):
                    if can_proc(p, 'bloodlust_proc', self.turn_count, 3):
                        if random.random() < 0.10:
                            mark_proc(p, 'bloodlust_proc', self.turn_count)
                            if p.special_cooldown > 0:
                                p.special_cooldown -= 1
                                logs.append(f"💢 **Sed de Batalla:** ¡{p.user.display_name} reduce en 1 turno el cooldown de su Especial!")

            # Logs de Vigilancia Eterna
            if getattr(p, "eternal_watch_trigger_log", None):
                logs.append(p.eternal_watch_trigger_log)
                p.eternal_watch_trigger_log = None

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
                # Si está aturdido, congelado o silenciado, no actúa
                if m.get("stun_turns", 0) > 0 or m.get("frozen_turns", 0) > 0 or m.get("silence_turns", 0) > 0:
                    if m.get("silence_turns", 0) > 0:
                        logs.append(f"🤫 {m['name']} está silenciado y no puede actuar al final del turno.")
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
            new_view.equipment_ultimate_charge = self.equipment_ultimate_charge
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

    def _apply_damage_to_player(self, target, raw_dmg, logs: list[str], is_boss_attack=False):
        if target.is_dead:
            return

        # Evasión garantizada / paso fantasma / cota de malla / esquiva pasiva
        if is_boss_attack:
            if target.set_bonus_caelum_4pc and not target.first_strike_used and not target.guaranteed_dodge_next:
                target.first_strike_used = True
                if random.random() < 0.20:
                    logs.append(f"💨 **Efecto Caelum:** ¡{target.user.display_name} esquiva el primer golpe recibido en el combate!")
                    return

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

        # Pasivo: Piel de Piedra (stoneskin)
        if any(p['id'] == 'stoneskin' for p in target.passives):
            raw_dmg = max(1, raw_dmg - 3)

        # Daño de entrada registrado para Castigo Divino
        target.total_damage_taken += raw_dmg

        # Reflejo (Juicio Final)
        if target.juicio_final_turns > 0 and raw_dmg > 0:
            reflected = int(raw_dmg * target.juicio_final_reflect_pct)
            self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + (reflected * EQUIPMENT_ULTIMATE_FILL_RATE))
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
            parry_heal = int(parry_heal * (1.0 + target.healing_bonus_pct))
            final_dmg = max(0, raw_dmg - parry_heal)
            target.hp = max(0, target.hp - final_dmg)
            if is_boss_attack:
                target.last_physical_damage_taken = final_dmg
            logs.append(f"💥 {target.user.display_name} recibe **{final_dmg}** daño (tras curarse **{parry_heal}** por Parada). ({target.hp}/{target.max_hp} HP)")
            
            # Contraatacar al boss o esbirro
            counter_dmg = max(1, int(raw_dmg * 0.75))
            self.equipment_ultimate_charge = min(100.0, self.equipment_ultimate_charge + (counter_dmg * EQUIPMENT_ULTIMATE_FILL_RATE))
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

        # Aurelius 4pc low hp heal check
        if target.hp > 0 and target.hp < target.max_hp * 0.30 and target.set_bonus_aurelius_4pc and not target.low_hp_heal_used:
            target.low_hp_heal_used = True
            heal_amt = int(target.max_hp * 0.15)
            heal_amt = int(heal_amt * (1.0 + target.healing_bonus_pct))
            target.hp = min(target.max_hp, target.hp + heal_amt)
            logs.append(f"☀️ **Set Aurelius:** ¡{target.user.display_name} baja del 30% HP y activa Destello Dorado, curándose **{heal_amt}** HP! ({target.hp}/{target.max_hp} HP)")

        if target.hp <= 0:
            # Pasivo: Segundo aliento (sobrevive con 1 HP una vez)
            if not target.used_second_wind and any(p['id'] == 'second_wind' for p in target.passives):
                target.hp = 1
                target.used_second_wind = True
                logs.append(f"💫 **Segundo Aliento:** {target.user.display_name} sobrevive con **1 HP**!")
                return
            target.is_dead = True
            logs.append(f"💀 **{target.user.display_name}** ha caído en combate!")
            for ally in self.players:
                if not ally.is_dead and ally.user.id != target.user.id and ally.set_bonus_thanatos_4pc:
                    ally.next_hit_lifesteal_bonus = 0.10
                    logs.append(f"💀 **Efecto Thanatos:** ¡La caída de un aliado otorga a {ally.user.display_name} +10% de robo de vida en su próximo golpe!")
            if self.affix == "Sangriento":
                heal = int(self.boss.max_hp * 0.15)
                self.boss.hp = min(self.boss.max_hp, self.boss.hp + heal)
                logs.append(f"🩸 **Sangriento:** {self.boss.name} se cura **{heal}** HP debido a la caída de un jugador.")

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
            self._apply_damage_to_player(target, dmg, logs, is_boss_attack=True)

        elif ab_type == "aoe_damage":
            base = int(self.boss.atk * ability["damage_mult"])
            if self.boss.weakness_turns > 0:
                base = int(base * (1.0 - self.boss.weakness_pct))
            for p in alive:
                dmg = int(base * random.uniform(0.85, 1.15))
                self._apply_damage_to_player(p, dmg, logs, is_boss_attack=True)

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
            self._apply_damage_to_player(target, dmg, logs, is_boss_attack=True)
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
                self._apply_damage_to_player(p, dmg, logs, is_boss_attack=True)

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
                self._apply_damage_to_player(p, drain, logs, is_boss_attack=True)
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
                self._apply_damage_to_player(p, dmg, logs, is_boss_attack=True)
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
            self._apply_damage_to_player(target, dmg, logs, is_boss_attack=True)

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

        # Otorgamiento de monedas de combate al ganar
        if victory:
            RAID_CURRENCY_REWARD = {
                "normal":  (20, 40),
                "dificil": (80, 150),
                "mitica":  (400, 700),
            }
            currency_summary = []
            for p in self.players:
                if is_mimic:
                    bronze_reward = random.randint(60, 100)
                else:
                    reward_range = RAID_CURRENCY_REWARD.get(self.difficulty, (20, 40))
                    bronze_reward = random.randint(*reward_range)
                    if self.difficulty == "mitica" and random.random() < 0.05:
                        bronze_reward += 10_000  # +1 Oro extra (10.000 Bronce)
                
                await asyncio.to_thread(add_combat_currency, p.user.id, bronze_reward)
                currency_summary.append(f"• {p.user.mention}: {format_currency(bronze_reward)}")
            
            if channel and currency_summary:
                embed_currency = discord.Embed(
                    title="🪙 Recompensas de Monedas de Combate",
                    description="\n".join(currency_summary),
                    color=discord.Color.gold()
                )
                try:
                    await channel.send(embed=embed_currency)
                except Exception as exc:
                    logger.warning("No se pudo enviar el embed de recompensas de combate: %r", exc)

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
                loot = get_raid_pkg().generate_raid_loot(p.level, final_rarity_bonus, floor_idx=diff_cfg["rarity_floor_idx"], ilvl_bonus=diff_cfg["ilvl_bonus"])
                equipment = await asyncio.to_thread(get_raid_pkg().get_user_equipment, p.user.id)
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
                unique_loot = get_raid_pkg().roll_unique_item(self.boss.name)
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

from src.commands.duels.raid.loot_views import (
    RaidLootView, RaidLootRollView, log_raid, count_mythic_raids_today,
    build_minions_from_pool, build_miniboss_config, roll_unique_item
)
from src.commands.duels.raid.merchant_views import PhantomMerchantSlotSelectView, PhantomMerchantView


class RaidsCog(commands.Cog):
    """Sistema de Raids PvE cooperativas."""

    def __init__(self, bot):
        self.bot = bot
        self.active_raids: set[int] = set()

    @app_commands.command(name="raid", description="Abre el Panel Hub Central de Combate y Raids")
    async def raid_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        user_id = user.id

        await asyncio.to_thread(ensure_user, user_id, user.name)
        stats = await asyncio.to_thread(get_combat_stats, user_id)
        equip = await asyncio.to_thread(get_user_equipment, user_id)
        boss_config = get_today_boss()

        rank_emoji = get_combat_rank_emoji(stats['level'])
        rank_name = get_combat_rank(stats['level'])

        embed = discord.Embed(
            title=f"⚔️ Panel Central de Combate — {user.display_name}",
            description=(
                f"*{boss_config['emoji']} **Boss del Día:** {boss_config['name']} ({boss_config['element']})*\n"
                f"*{boss_config['lore']}*\n\n"
                f"{rank_emoji} **Rango:** {rank_name} (Nivel **{stats['level']}**)\n"
                f"📊 **Victorias:** {stats['wins']} | **Derrotas:** {stats['losses']}\n"
                f"🔮 **Habilidad Especial:** {BOSS_ABILITIES[boss_config['ability']]['emoji']} {BOSS_ABILITIES[boss_config['ability']]['name']}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Selecciona una opción del menú interactivo para acceder:"
            ),
            color=boss_config["color"]
        )
        embed.set_footer(text="Panel Efímero Privado · Únicamente tú ves este menú")

        from src.commands.duels.raid.hub_view import RaidHubView
        hub_view = RaidHubView(user, self)
        await interaction.followup.send(embed=embed, view=hub_view, ephemeral=True)

    async def start_raid_lobby_from_hub(self, interaction: discord.Interaction):
        user = interaction.user
        user_id = user.id

        if user_id in self.active_raids:
            await interaction.followup.send("❌ Ya tienes una raid en curso.", ephemeral=True)
            return

        stats = await asyncio.to_thread(get_combat_stats, user_id)
        equip = await asyncio.to_thread(get_user_equipment, user_id)
        boss_config = get_today_boss()

        import random
        from src.utils.raid_config import MINIBOSS_CHANCE, MINIBOSSES
        if random.random() < MINIBOSS_CHANCE:
            miniboss_key = random.choice(list(MINIBOSSES.keys()))
            boss_config = build_miniboss_config(miniboss_key, MINIBOSSES[miniboss_key])

        self.active_raids.add(user_id)

        lobby = RaidLobbyView(user, boss_config, self)
        lobby.player_stats[user_id] = stats
        lobby.player_equipments[user_id] = equip

        embed = lobby._build_lobby_embed()
        msg = await interaction.channel.send(embed=embed, view=lobby)
        lobby.message = msg

        await lobby.wait()

        if not lobby.started:
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

        if boss_config.get("is_shop"):
            merchant_view = PhantomMerchantView(lobby.players, self)
            embed = merchant_view._build_embed()
            await interaction.channel.send(embed=embed, view=merchant_view)
            return

        await asyncio.sleep(1)

        combatants = []
        for p in lobby.players:
            p_stats = lobby.player_stats.get(p.id, await asyncio.to_thread(get_combat_stats, p.id))
            p_equip = lobby.player_equipments.get(p.id, await asyncio.to_thread(get_user_equipment, p.id))
            combatants.append(RaidCombatant(
                p, p_stats['level'], p_equip,
                combat_class=p_stats.get('combat_class'),
                combat_subclass=p_stats.get('combat_subclass')
            ))

        from src.utils.combat_progression import calc_power_level
        total_power = sum(calc_power_level(c.level, lobby.player_equipments.get(c.user.id, {}), c.combat_subclass) for c in combatants)
        boss = RaidBoss(boss_config, total_power, lobby.difficulty, is_miniboss=boss_config.get("is_miniboss", False), num_players=len(combatants))

        affix_name = random.choice(list(RAID_AFFIXES.keys()))
        combat_view = RaidCombatView(combatants, boss, self, affix=affix_name, difficulty=lobby.difficulty)
        combat_embed = combat_view._build_embed()

        combat_msg = await interaction.channel.send(embed=combat_embed, view=combat_view)
        combat_view.interaction_msg = combat_msg


    async def open_tienda_raid(self, interaction: discord.Interaction):
        catalog = await asyncio.to_thread(get_consumable_catalog)

        embed = discord.Embed(
            title="⚔️ Tienda de Raids y Aventura",
            description="Consumibles y brebajes de utilidad diseñados para proteger al equipo y potenciar tus expediciones PvE.",
            color=discord.Color.dark_purple()
        )

        for item in catalog:
            key = item["consumable_key"]
            name = item["name"]
            desc = item["description"]
            price = item["price"]
            embed.add_field(
                name=f"🧪 {name} — {format_currency(price)}",
                value=f"*{desc}*",
                inline=False
            )

        from src.commands.duels.pvp.loot_views import ConsumableShopView
        view = ConsumableShopView(interaction.user, catalog)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)



async def setup(bot):
    await bot.add_cog(RaidsCog(bot))
    logger.info("Raids cog loaded successfully.")

