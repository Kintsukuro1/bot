"""
Sistema de Duelos PvP — Cog principal.
Combate por turnos entre dos usuarios con apuesta de monedas,
progresión de nivel propia y sistema de equipo con drops estilo WoW.
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
    ensure_user, get_balance, deduct_balance, add_balance,
    registrar_transaccion, transfer_balance, db_cursor,
    get_combat_stats, update_combat_stats_after_duel,
    log_duel, get_user_equipment, equip_item, get_duel_leaderboard,
)
from src.utils.combat_progression import (
    calc_base_stats, calc_duel_xp, get_duel_cooldown_minutes,
    calc_attack_damage, calc_special_damage, calc_defend_heal,
    calc_equipment_bonus, get_effective_bonus,
    generate_loot, calc_sell_price,
    format_progress_bar, format_hp_bar, format_stat_type,
    get_combat_rank, get_combat_rank_emoji, calc_combat_xp_needed,
    EQUIPMENT_SLOTS, SLOT_EMOJIS, RARITY_COLORS,
    MAX_LEVEL_DIFFERENCE, MIN_BET, MAX_TURNS,
    TURN_TIMEOUT_SECONDS, CHALLENGE_TIMEOUT_SECONDS, LOOT_TIMEOUT_SECONDS,
    SPECIAL_UNLOCK_LEVEL, SPECIAL_COOLDOWN_TURNS, MAX_GEAR_BONUS_PCT,
    DROP_RATE_WINNER, DROP_RATE_LOSER,
    ALL_STATS, format_item_stats_display,
)
from src.utils.combat_config import SKILLS_CONFIG


# ══════════════════════════════════════════════
# ESTADO DE UN JUGADOR EN COMBATE
# ══════════════════════════════════════════════

class Combatant:
    """Estado de un jugador durante el combate."""

    def __init__(self, user: discord.Member, level: int, equipment: dict, combat_class: str = None):
        self.user = user
        self.level = level
        self.combat_class = combat_class

        # Stats base
        base = calc_base_stats(level)
        bonus, passives = calc_equipment_bonus(equipment)
        effective, _, pct_per_stat = get_effective_bonus(bonus, level)

        self.max_hp = base["hp"] + effective.get("hp", 0)
        self.hp = self.max_hp
        self.pre_hit_hp = self.hp
        self.atk = base["atk"] + effective.get("atk", 0)
        self.mag = base["mag"] + effective.get("mag", 0)
        self.def_stat = base["def"] + effective.get("def", 0)

        # Estado de combate
        self.is_defending = False
        self.special_cooldown = 0  # Turnos restantes de cooldown del Especial
        self.consecutive_timeouts = 0
        
        # Efectos pasivos de Legendario
        self.passives = passives
        self.used_second_wind = False
        self.arcane_shield_active = any(p['id'] == 'arcane_shield' for p in passives)


# ══════════════════════════════════════════════
# VISTA: RETO INICIAL (Aceptar / Rechazar)
# ══════════════════════════════════════════════

class ChallengeView(discord.ui.View):
    """Botones para que el rival acepte o rechace el duelo."""

    def __init__(self, challenger: discord.Member, rival: discord.Member, bet: int,
                 cog: 'DuelsCog'):
        super().__init__(timeout=CHALLENGE_TIMEOUT_SECONDS)
        self.challenger = challenger
        self.rival = rival
        self.bet = bet
        self.cog = cog
        self.accepted = None  # None = pendiente, True = aceptado, False = rechazado

    @discord.ui.button(label="✅ Aceptar", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.rival.id:
            await interaction.response.send_message("❌ Solo el retado puede responder.", ephemeral=True)
            return

        await interaction.response.defer()

        # Cobrar apuesta al rival
        success, _ = await asyncio.to_thread(deduct_balance, self.rival.id, self.bet)
        if not success:
            self.accepted = False
            for item in self.children:
                item.disabled = True
            embed = discord.Embed(
                title="❌ Duelo Cancelado",
                description=f"{self.rival.mention} no tiene suficiente saldo ({self.bet:,} monedas).",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=self)
            self._cleanup()
            self.stop()
            return

        self.accepted = True
        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title="⚔️ ¡Duelo Aceptado!",
            description=f"{self.rival.mention} acepta el reto de {self.challenger.mention}.\n"
                        f"Preparando la arena...",
            color=discord.Color.gold()
        )
        await interaction.edit_original_response(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="❌ Rechazar", style=discord.ButtonStyle.danger)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.rival.id:
            await interaction.response.send_message("❌ Solo el retado puede responder.", ephemeral=True)
            return

        self.accepted = False
        for item in self.children:
            item.disabled = True

        await interaction.response.defer()
        # Devolver apuesta al retador
        await asyncio.to_thread(add_balance, self.challenger.id, self.bet)

        embed = discord.Embed(
            title="🚫 Duelo Rechazado",
            description=f"{self.rival.mention} rechazó el reto. Apuesta devuelta.",
            color=discord.Color.red()
        )
        await interaction.edit_original_response(embed=embed, view=self)
        self._cleanup()
        self.stop()

    async def on_timeout(self):
        if self.accepted is None:
            self.accepted = False
            # Devolver apuesta al retador
            await asyncio.to_thread(add_balance, self.challenger.id, self.bet)
            for item in self.children:
                item.disabled = True
            self._cleanup()

    def _cleanup(self):
        """Libera a los jugadores del set de duelos activos."""
        self.cog.active_duels.discard(self.challenger.id)
        self.cog.active_duels.discard(self.rival.id)


# ══════════════════════════════════════════════
# VISTA: COMBATE POR TURNOS
# ══════════════════════════════════════════════

class DuelView(discord.ui.View):
    """Vista principal del combate PvP por turnos simultáneos."""

    def __init__(self, p1: Combatant, p2: Combatant, bet: int, cog: 'DuelsCog'):
        super().__init__(timeout=TURN_TIMEOUT_SECONDS)
        self.p1 = p1
        self.p2 = p2
        self.bet = bet
        self.cog = cog
        
        # Elecciones de acción de cada jugador en la ronda actual
        self.p1_action = None  # 'attack', 'defend', 'special', 'timeout' o None
        self.p2_action = None
        self.p1_special_id = None
        self.p2_special_id = None

        # Turnos restantes del debuff de ceguera (Tierra a los ojos)
        self.p1_blinded_turns = 0
        self.p2_blinded_turns = 0

        # Estados especiales de clases
        self.p1_frenzy_turns = 0
        self.p2_frenzy_turns = 0
        self.p1_poison_turns = 0
        self.p2_poison_turns = 0
        self.p1_burn_turns = 0
        self.p2_burn_turns = 0
        self.p1_retribution_active = False
        self.p2_retribution_active = False
        
        self.turn_count = 0
        self.game_over = False
        self._payout_done = False
        self.action_log = []  # Registro de acciones recientes
        self.interaction_msg = None  # Referencia al mensaje del duelo

    def _build_embed(self):
        """Construye el embed de estado del combate."""
        status_p1 = "🟢 ¡Listo!" if self.p1_action else "🔴 Eligiendo..."
        status_p2 = "🟢 ¡Listo!" if self.p2_action else "🔴 Eligiendo..."

        embed = discord.Embed(
            title="⚔️ Duelo PvP Simultáneo",
            description=f"**Ronda {self.turn_count + 1}**\n"
                        f"{self.p1.user.mention}: {status_p1}\n"
                        f"{self.p2.user.mention}: {status_p2}",
            color=discord.Color.dark_gold()
        )

        # Barras de HP
        for p in (self.p1, self.p2):
            rank_emoji = get_combat_rank_emoji(p.level)
            hp_bar = format_hp_bar(p.hp, p.max_hp)
            
            # Comprobar estados
            blind_turns = self.p1_blinded_turns if p == self.p1 else self.p2_blinded_turns
            frenzy_turns = self.p1_frenzy_turns if p == self.p1 else self.p2_frenzy_turns
            poison_turns = self.p1_poison_turns if p == self.p1 else self.p2_poison_turns
            burn_turns = self.p1_burn_turns if p == self.p1 else self.p2_burn_turns
            
            status_icons = ""
            if blind_turns > 0:
                status_icons += f" 👁️(Cegado {blind_turns}t)"
            if frenzy_turns > 0:
                status_icons += f" ⚔️(Frenesí {frenzy_turns}t)"
            if poison_turns > 0:
                status_icons += f" 🧪(Envenenado {poison_turns}t)"
            if burn_turns > 0:
                status_icons += f" 🔥(Quemado {burn_turns}t)"
            if p.special_cooldown > 0:
                status_icons += f" ⏳({p.special_cooldown}t)"
            
            passive_icons = ""
            for pass_item in p.passives:
                passive_icons += f" {pass_item.get('emoji', '✨')}"

            class_tag = f" [{p.combat_class}]" if p.combat_class else ""
            embed.add_field(
                name=f"{rank_emoji} {p.user.display_name}{class_tag} (Nv.{p.level}){status_icons}{passive_icons}",
                value=f"{hp_bar}\n⚔️ {p.atk} ATK · 🔮 {p.mag} MAG · 🛡️ {p.def_stat} DEF",
                inline=False
            )

        # Log de acciones
        if self.action_log:
            log_text = "\n".join(self.action_log[-5:])
            embed.add_field(name="📜 Registro", value=log_text, inline=False)

        embed.add_field(
            name="💰 Apuesta",
            value=f"{self.bet:,} monedas",
            inline=True
        )

        # Indicar acciones disponibles
        actions = ["⚔️ Atacar", "🛡️ Defender", "👁️ Tierra a los ojos"]
        embed.set_footer(text=f"Acciones: {' · '.join(actions)} · Tiempo por ronda: {TURN_TIMEOUT_SECONDS}s")

        return embed

    # ──────────────────── BOTONES ────────────────────

    @discord.ui.button(label="⚔️ Atacar", style=discord.ButtonStyle.danger, row=0)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over:
            await interaction.response.send_message("❌ El duelo ya terminó.", ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id == self.p1.user.id:
            if self.p1_action is not None:
                await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
                return
            self.p1_action = 'attack'
            self.p1.consecutive_timeouts = 0
        elif user_id == self.p2.user.id:
            if self.p2_action is not None:
                await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
                return
            self.p2_action = 'attack'
            self.p2.consecutive_timeouts = 0
        else:
            await interaction.response.send_message("❌ No estás participando en este duelo.", ephemeral=True)
            return

        await self._check_and_resolve(interaction)

    @discord.ui.button(label="🛡️ Defender", style=discord.ButtonStyle.primary, row=0)
    async def defend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over:
            await interaction.response.send_message("❌ El duelo ya terminó.", ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id == self.p1.user.id:
            if self.p1_action is not None:
                await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
                return
            self.p1_action = 'defend'
            self.p1.consecutive_timeouts = 0
        elif user_id == self.p2.user.id:
            if self.p2_action is not None:
                await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
                return
            self.p2_action = 'defend'
            self.p2.consecutive_timeouts = 0
        else:
            await interaction.response.send_message("❌ No estás participando en este duelo.", ephemeral=True)
            return

        await self._check_and_resolve(interaction)

    @discord.ui.select(
        placeholder="✨ Lanzar Habilidad Especial...",
        min_values=1,
        max_values=1,
        row=1,
        options=[
            discord.SelectOption(
                label=f"{skill['name']} (Nvl. {skill['min_level']})",
                value=skill_id,
                emoji=skill['emoji'],
                description=skill['desc'][:100]
            ) for skill_id, skill in SKILLS_CONFIG.items()
        ]
    )
    async def select_special(self, interaction: discord.Interaction, select: discord.ui.Select):
        if self.game_over:
            await interaction.response.send_message("❌ El duelo ya terminó.", ephemeral=True)
            return

        user_id = interaction.user.id
        cp = self.p1 if user_id == self.p1.user.id else self.p2 if user_id == self.p2.user.id else None

        if cp is None:
            await interaction.response.send_message("❌ No estás participando en este duelo.", ephemeral=True)
            return

        if cp.special_cooldown > 0:
            await interaction.response.send_message(
                f"❌ Habilidad Especial en enfriamiento ({cp.special_cooldown} turnos restantes).",
                ephemeral=True
            )
            # Re-edit para quitar la selección visual
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass
            return

        selected_value = select.values[0]
        
        # Validar si el especial seleccionado corresponde a su clase y nivel
        req = SKILLS_CONFIG.get(selected_value)
        if not req:
            await interaction.response.send_message("❌ Habilidad desconocida.", ephemeral=True)
            return
            
        if req["class"] is not None:
            if cp.level < req["min_level"] or cp.combat_class != req["class"]:
                await interaction.response.send_message(
                    f"❌ Solo los **{req['class']}** de nivel **{req['min_level']}+** pueden usar esta habilidad.",
                    ephemeral=True
                )
                try:
                    await interaction.message.edit(view=self)
                except Exception:
                    pass
                return
        else:
            if cp.level >= 5 and cp.combat_class is not None:
                await interaction.response.send_message(
                    "❌ Ya tienes una clase asignada. Debes usar la habilidad especial de tu clase.",
                    ephemeral=True
                )
                try:
                    await interaction.message.edit(view=self)
                except Exception:
                    pass
                return

        # Registrar la acción
        if user_id == self.p1.user.id:
            if self.p1_action is not None:
                await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
                return
            self.p1_action = 'special'
            self.p1_special_id = selected_value
            self.p1.consecutive_timeouts = 0
        else:
            if self.p2_action is not None:
                await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
                return
            self.p2_action = 'special'
            self.p2_special_id = selected_value
            self.p2.consecutive_timeouts = 0

        await self._check_and_resolve(interaction)

    async def _check_and_resolve(self, interaction: discord.Interaction):
        """Verifica si ambos jugadores han votado y resuelve el turno."""
        if self.p1_action is not None and self.p2_action is not None:
            await interaction.response.defer()
            await self._resolve_round(interaction)
        else:
            # Actualizar embed de forma silenciosa para mostrar quién está listo
            embed = self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    # ──────────────────── RESOLUCIÓN SIMULTÁNEA ────────────────────

    async def _resolve_round(self, interaction: discord.Interaction = None):
        """Procesa y resuelve las acciones elegidas por ambos jugadores simultáneamente."""
        # Resetear retribución de ronda anterior
        self.p1_retribution_active = False
        self.p2_retribution_active = False

        # Verificar pasiva de parry
        p1_has_parry = any(p_item['id'] == 'parry' for p_item in self.p1.passives)
        p2_has_parry = any(p_item['id'] == 'parry' for p_item in self.p2.passives)

        # Respaldar HPs iniciales para el cálculo de daño simultáneo
        self.p1.pre_hit_hp = self.p1.hp
        self.p2.pre_hit_hp = self.p2.hp

        p1_act = self.p1_action
        p2_act = self.p2_action

        # Establecer estado defensivo temporal
        self.p1.is_defending = (p1_act == 'defend')
        self.p2.is_defending = (p2_act == 'defend')

        logs = []
        logs.append(f"🏁 **Ronda {self.turn_count + 1}:**")

        # 1. Aplicar regeneraciones pasivas de inicio de turno
        for p in (self.p1, self.p2):
            if any(p_item['id'] == 'regen' for p_item in p.passives) and p.hp > 0 and p.hp < p.max_hp:
                heal = max(1, int(p.max_hp * 0.03))
                p.hp = min(p.max_hp, p.hp + heal)
                logs.append(f"💚 **Regen:** {p.user.display_name} se cura **{heal}** HP.")

        # 1.5 Aplicar DOTs de clases (Quemadura, Veneno)
        for defender in (self.p1, self.p2):
            if defender.hp <= 0:
                continue
            
            p_turns = self.p1_poison_turns if defender == self.p1 else self.p2_poison_turns
            b_turns = self.p1_burn_turns if defender == self.p1 else self.p2_burn_turns
            
            if p_turns > 0:
                dot_val = SKILLS_CONFIG["veneno"]["dot_damage"]
                p_dmg = min(defender.hp, dot_val)
                defender.hp = max(0, defender.hp - p_dmg)
                logs.append(f"🧪 **Veneno:** {defender.user.display_name} sufre **{p_dmg}** HP de daño por veneno.")
                
            if b_turns > 0:
                dot_pct = SKILLS_CONFIG["quemadura"]["dot_max_hp_pct"]
                b_dmg = min(defender.hp, max(1, int(defender.max_hp * dot_pct)))
                defender.hp = max(0, defender.hp - b_dmg)
                logs.append(f"🔥 **Quemadura:** {defender.user.display_name} sufre **{b_dmg}** HP de daño por quemadura.")

        # 2. Aplicar curación/defensa activa si eligieron Defender
        if self.p1.is_defending:
            if p1_has_parry:
                logs.append(f"🛡️ {self.p1.user.display_name} se prepara para hacer un **Parry**.")
            else:
                heal = calc_defend_heal(self.p1.max_hp)
                self.p1.hp = min(self.p1.max_hp, self.p1.hp + heal)
                logs.append(f"🛡️ {self.p1.user.display_name} se defiende y recupera **{heal}** HP.")
        if self.p2.is_defending:
            if p2_has_parry:
                logs.append(f"🛡️ {self.p2.user.display_name} se prepara para hacer un **Parry**.")
            else:
                heal = calc_defend_heal(self.p2.max_hp)
                self.p2.hp = min(self.p2.max_hp, self.p2.hp + heal)
                logs.append(f"🛡️ {self.p2.user.display_name} se defiende y recupera **{heal}** HP.")

        # 2.5 Procesar lanzamientos de Habilidades Especiales (Buffs/Debuffs)
        for caster, target, act in ((self.p1, self.p2, p1_act), (self.p2, self.p1, p2_act)):
            if act == 'special':
                # Aplicar cooldown de Especial
                has_mana_residual = any(p['id'] == 'mana_residual' for p in caster.passives)
                cooldown = (SPECIAL_COOLDOWN_TURNS - 1) if has_mana_residual else SPECIAL_COOLDOWN_TURNS
                caster.special_cooldown = cooldown + 1 # +1 porque se decrementa al final de esta ronda
                
                special_id = self.p1_special_id if caster == self.p1 else self.p2_special_id
                if not special_id or special_id == "ceguera":
                    if target == self.p1:
                        self.p1_blinded_turns = 4 # 3 turnos + 1
                    else:
                        self.p2_blinded_turns = 4
                    logs.append(f"👁️ **Tierra a los ojos:** {caster.user.display_name} lanza tierra a los ojos de {target.user.display_name}!")
                elif special_id == "frenesi":
                    if caster == self.p1:
                        self.p1_frenzy_turns = 3 # 2 turnos + 1
                    else:
                        self.p2_frenzy_turns = 3
                    logs.append(f"⚔️ **Frenesí de Batalla:** {caster.user.display_name} entra en Frenesí (+ATK, -DEF)!")
                elif special_id == "represalia":
                    if caster == self.p1:
                        self.p1_retribution_active = True
                    else:
                        self.p2_retribution_active = True
                    logs.append(f"🛡️ **Postura de Represalia:** {caster.user.display_name} prepara un contraataque total para esta ronda!")
                elif special_id == "drenaje":
                    steal_amt = max(1, int(target.hp * 0.15))
                    target.hp = max(0, target.hp - steal_amt)
                    caster.hp = min(caster.max_hp, caster.hp + steal_amt)
                    # Limpiar debuffs propios
                    if caster == self.p1:
                        self.p1_blinded_turns = 0
                        self.p1_poison_turns = 0
                        self.p1_burn_turns = 0
                    else:
                        self.p2_blinded_turns = 0
                        self.p2_poison_turns = 0
                        self.p2_burn_turns = 0
                    logs.append(f"⚕️ **Drenaje Sagrado:** {caster.user.display_name} roba **{steal_amt}** HP a {target.user.display_name} y purifica todas sus condiciones!")

        # 3. Calcular ataque de P1 a P2
        p1_dmg = 0
        p1_log = ""
        if p1_act in ('attack', 'special'):
            p1_dmg, p1_log = self._calculate_action_result(self.p1, self.p2, p1_act)

        # 4. Calcular ataque de P2 a P1
        p2_dmg = 0
        p2_log = ""
        if p2_act in ('attack', 'special'):
            p2_dmg, p2_log = self._calculate_action_result(self.p2, self.p1, p2_act)

        # 5. Aplicar daño simultáneamente
        # P1 a P2
        if p1_dmg > 0:
            if self.p2_retribution_active:
                cfg_rep = SKILLS_CONFIG["represalia"]
                mitigated = max(1, int(p1_dmg * cfg_rep["mitigation"]))
                reflect_dmg = int(p1_dmg * cfg_rep["reflect"])
                self.p2.hp = max(0, self.p2.hp - mitigated)
                self.p1.hp = max(0, self.p1.hp - reflect_dmg) # Reflejo
                logs.append(f"🛡️ **Represalia:** {self.p2.user.display_name} mitiga una parte del golpe ({mitigated}) y refleja **{reflect_dmg}** de daño a {self.p1.user.display_name}!")
            elif self.p2.is_defending and p2_has_parry:
                self.p2.hp = max(0, self.p2.hp - p1_dmg)
                parry_dmg = int(p1_dmg * 0.75)
                parry_heal = int(p1_dmg * 0.30)
                self.p1.hp = max(0, self.p1.hp - parry_dmg)
                self.p2.hp = min(self.p2.max_hp, self.p2.hp + parry_heal)
                logs.append(f"⚡ **¡PARRY!** {self.p2.user.display_name} recibe el golpe pero contraataca por **{parry_dmg}** de daño y se cura **{parry_heal}** HP!")
            else:
                self.p2.hp = max(0, self.p2.hp - p1_dmg)
        if p1_log:
            logs.append(p1_log)

        # P2 a P1
        if p2_dmg > 0:
            if self.p1_retribution_active:
                cfg_rep = SKILLS_CONFIG["represalia"]
                mitigated = max(1, int(p2_dmg * cfg_rep["mitigation"]))
                reflect_dmg = int(p2_dmg * cfg_rep["reflect"])
                self.p1.hp = max(0, self.p1.hp - mitigated)
                self.p2.hp = max(0, self.p2.hp - reflect_dmg) # Reflejo
                logs.append(f"🛡️ **Represalia:** {self.p1.user.display_name} mitiga una parte del golpe ({mitigated}) y refleja **{reflect_dmg}** de daño a {self.p2.user.display_name}!")
            elif self.p1.is_defending and p1_has_parry:
                self.p1.hp = max(0, self.p1.hp - p2_dmg)
                parry_dmg = int(p2_dmg * 0.75)
                parry_heal = int(p2_dmg * 0.30)
                self.p2.hp = max(0, self.p2.hp - parry_dmg)
                self.p1.hp = min(self.p1.max_hp, self.p1.hp + parry_heal)
                logs.append(f"⚡ **¡PARRY!** {self.p1.user.display_name} recibe el golpe pero contraataca por **{parry_dmg}** de daño y se cura **{parry_heal}** HP!")
            else:
                self.p1.hp = max(0, self.p1.hp - p2_dmg)
        if p2_log:
            logs.append(p2_log)

        # 6. Procesar pasivos post-daño (como Segundo Aliento)
        for attacker, defender in ((self.p1, self.p2), (self.p2, self.p1)):
            if defender.hp <= 0 and any(p['id'] == 'second_wind' for p in defender.passives) and not defender.used_second_wind:
                defender.hp = 1
                defender.used_second_wind = True
                logs.append(f"💫 **Segundo Aliento:** {defender.user.display_name} sobrevive con 1 HP.")

        # 7. Si hubo timeouts
        if p1_act == 'timeout':
            logs.append(f"⏰ {self.p1.user.display_name} no respondió a tiempo.")
        if p2_act == 'timeout':
            logs.append(f"⏰ {self.p2.user.display_name} no respondió a tiempo.")

        # Decrementar cooldowns de especial y turnos de buffs/debuffs
        for p in (self.p1, self.p2):
            if p.special_cooldown > 0:
                p.special_cooldown -= 1

        if self.p1_blinded_turns > 0:
            self.p1_blinded_turns -= 1
        if self.p2_blinded_turns > 0:
            self.p2_blinded_turns -= 1
            
        if self.p1_frenzy_turns > 0:
            self.p1_frenzy_turns -= 1
        if self.p2_frenzy_turns > 0:
            self.p2_frenzy_turns -= 1
            
        if self.p1_poison_turns > 0:
            self.p1_poison_turns -= 1
        if self.p2_poison_turns > 0:
            self.p2_poison_turns -= 1
            
        if self.p1_burn_turns > 0:
            self.p1_burn_turns -= 1
        if self.p2_burn_turns > 0:
            self.p2_burn_turns -= 1

        # Limpiar acciones y estados para la próxima ronda
        self.p1_action = None
        self.p2_action = None
        self.p1_special_id = None
        self.p2_special_id = None
        self.p1.is_defending = False
        self.p2.is_defending = False

        self.turn_count += 1

        # Agregar los logs de este turno al registro de acciones
        for log_line in logs:
            self.action_log.append(log_line)

        # Mantener un registro razonable (últimas 6 líneas)
        if len(self.action_log) > 6:
            self.action_log = self.action_log[-6:]

        # Comprobar si el juego ha terminado
        if self.p1.hp <= 0 or self.p2.hp <= 0:
            self.game_over = True
            if self.p1.hp <= 0 and self.p2.hp <= 0:
                self.action_log.append("💥 ¡Doble K.O.! Ambos guerreros han caído.")
            elif self.p1.hp <= 0:
                self.action_log.append(f"💀 **{self.p1.user.display_name}** ha caído.")
            elif self.p2.hp <= 0:
                self.action_log.append(f"💀 **{self.p2.user.display_name}** ha caído.")
            
            if interaction:
                await self._finish_duel(interaction)
            else:
                await self._finish_duel_from_timeout()
            return

        # Siguiente ronda
        self.reset_timeout()
        embed = self._build_embed()
        
        # Si la ronda se resolvió desde timeout, esta vista se ha detenido.
        # Debemos crear una nueva vista para la siguiente ronda para que los botones sigan activos.
        if interaction is None:
            new_view = DuelView(self.p1, self.p2, self.bet, self.cog)
            new_view.turn_count = self.turn_count
            new_view.action_log = self.action_log
            new_view.p1_blinded_turns = self.p1_blinded_turns
            new_view.p2_blinded_turns = self.p2_blinded_turns
            new_view.p1_frenzy_turns = self.p1_frenzy_turns
            new_view.p2_frenzy_turns = self.p2_frenzy_turns
            new_view.p1_poison_turns = self.p1_poison_turns
            new_view.p2_poison_turns = self.p2_poison_turns
            new_view.p1_burn_turns = self.p1_burn_turns
            new_view.p2_burn_turns = self.p2_burn_turns
            new_view.p1_special_id = self.p1_special_id
            new_view.p2_special_id = self.p2_special_id
            new_view.interaction_msg = self.interaction_msg
            
            try:
                if self.interaction_msg:
                    await self.interaction_msg.edit(embed=embed, view=new_view)
            except Exception:
                pass
            self.stop()
            return

        if interaction:
            await interaction.message.edit(embed=embed, view=self)

    def _calculate_action_result(self, attacker: Combatant, defender: Combatant, action_type: str) -> tuple[int, str]:
        """Calcula el daño y genera la línea de log para una acción ofensiva individual."""
        import random

        # Verificar si el atacante está cegado
        blind_turns = self.p1_blinded_turns if attacker == self.p1 else self.p2_blinded_turns
        if blind_turns > 0 and random.random() < SKILLS_CONFIG["ceguera"]["fail_chance"]:
            log_line = f"💨 {attacker.user.display_name} tiene los ojos llenos de tierra y **FALLÓ** su ataque!"
            return 0, log_line

        # Si el atacante tiene Frenesí activo: +35% ATK
        atk_val = attacker.atk
        if (self.p1_frenzy_turns > 0 and attacker == self.p1) or (self.p2_frenzy_turns > 0 and attacker == self.p2):
            atk_boost = SKILLS_CONFIG["frenesi"]["atk_boost"]
            atk_val = int(atk_val * (1.0 + atk_boost))

        # Si tiene pasiva de parry, no recibe reducción de daño de defender (pero sí cuenta para contraataque en el loop principal)
        defender_has_parry = any(p['id'] == 'parry' for p in defender.passives)
        is_defending_for_damage = defender.is_defending and not defender_has_parry

        # Pasivo: Golpe crítico
        extra_crit = 0.10 if any(p['id'] == 'crit_boost' for p in attacker.passives) else 0.0
        
        # Pasivo: Furia creciente
        has_fury = any(p['id'] == 'fury' for p in attacker.passives)
        fury_active = (attacker.hp / attacker.max_hp) < 0.30

        # Pasivo: Esquiva mejorada
        has_dodge = any(p['id'] == 'dodge' for p in defender.passives)
        if has_dodge and random.random() < 0.05:
            log_line = f"💨 {defender.user.display_name} **ESQUIVÓ** el ataque de {attacker.user.display_name}!"
            return 0, log_line

        if action_type == 'attack':
            damage, crit = calc_attack_damage(atk_val, defender.def_stat, is_defending_for_damage, extra_crit, has_fury, fury_active)
            
            # Si el defensor tiene Frenesí activo: recibe +15% de daño
            if (self.p1_frenzy_turns > 0 and defender == self.p1) or (self.p2_frenzy_turns > 0 and defender == self.p2):
                def_boost = SKILLS_CONFIG["frenesi"]["damage_received_boost"]
                damage = int(damage * (1.0 + def_boost))
            
            # Pasivo: Escudo arcano
            shield_log = ""
            if defender.arcane_shield_active:
                damage = max(1, int(damage / 2))
                defender.arcane_shield_active = False
                shield_log = " 🔮*(Escudo arcano reduce daño)*"
                
            crit_text = " **¡CRÍTICO!**" if crit else ""
            defend_text = " *(bloqueado parcialmente)*" if is_defending_for_damage else ""
            log_line = f"⚔️ {attacker.user.display_name} ataca → **{damage}** daño{crit_text}{defend_text}{shield_log}"
            
            # Pasivo: Vampirismo
            if any(p['id'] == 'vampirism' for p in attacker.passives) and damage > 0:
                heal = max(1, int(damage * 0.08))
                attacker.hp = min(attacker.max_hp, attacker.hp + heal)
                log_line += f"\n🧛 Vampirismo: {attacker.user.display_name} se cura **{heal}** HP."
                
            return damage, log_line

        elif action_type == 'special':
            special_id = self.p1_special_id if attacker == self.p1 else self.p2_special_id
            cfg = SKILLS_CONFIG.get(special_id) if special_id else SKILLS_CONFIG["ceguera"]
            
            if not special_id or special_id == "ceguera":
                log_line = f"{cfg['emoji']} {attacker.user.display_name} lanzó **{cfg['name']}** a {defender.user.display_name}."
                return 0, log_line
            
            elif special_id == "frenesi":
                log_line = f"{cfg['emoji']} {attacker.user.display_name} activa **{cfg['name']}**."
                return 0, log_line
                
            elif special_id == "represalia":
                log_line = f"{cfg['emoji']} {attacker.user.display_name} adopta la **{cfg['name']}**."
                return 0, log_line
                
            elif special_id == "drenaje":
                log_line = f"{cfg['emoji']} {attacker.user.display_name} usa **{cfg['name']}**."
                return 0, log_line
                
            elif special_id == "veneno":
                turns = cfg["turns"] + 1
                if defender == self.p1:
                    self.p1_poison_turns = turns
                else:
                    self.p2_poison_turns = turns
                
                raw_dmg = int(atk_val * cfg["damage_mult"])
                def_mitig = int(defender.def_stat * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender.def_stat * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                
                # Si el defensor tiene Frenesí activo: recibe +15% de daño
                if (self.p1_frenzy_turns > 0 and defender == self.p1) or (self.p2_frenzy_turns > 0 and defender == self.p2):
                    def_boost = SKILLS_CONFIG["frenesi"]["damage_received_boost"]
                    damage = int(damage * (1.0 + def_boost))
                
                # Pasivo: Escudo arcano
                shield_log = ""
                if defender.arcane_shield_active:
                    damage = max(1, int(damage / 2))
                    defender.arcane_shield_active = False
                    shield_log = " 🔮*(Escudo arcano reduce daño)*"
                
                log_line = f"{cfg['emoji']} {attacker.user.display_name} usa **{cfg['name']}** → **{damage}** daño y envenena a {defender.user.display_name}!{shield_log}"
                return damage, log_line
                
            elif special_id == "quemadura":
                turns = cfg["turns"] + 1
                if defender == self.p1:
                    self.p1_burn_turns = turns
                else:
                    self.p2_burn_turns = turns
                
                raw_dmg = int(attacker.mag * cfg["damage_mult"])
                def_mitig = int(defender.def_stat * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender.def_stat * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                
                # Si el defensor tiene Frenesí activo: recibe +15% de daño
                if (self.p1_frenzy_turns > 0 and defender == self.p1) or (self.p2_frenzy_turns > 0 and defender == self.p2):
                    def_boost = SKILLS_CONFIG["frenesi"]["damage_received_boost"]
                    damage = int(damage * (1.0 + def_boost))
                
                # Pasivo: Escudo arcano
                shield_log = ""
                if defender.arcane_shield_active:
                    damage = max(1, int(damage / 2))
                    defender.arcane_shield_active = False
                    shield_log = " 🔮*(Escudo arcano reduce daño)*"
                
                log_line = f"{cfg['emoji']} {attacker.user.display_name} lanza **{cfg['name']}** → **{damage}** daño mágico y quema a {defender.user.display_name}!{shield_log}"
                return damage, log_line

        return 0, ""

    # ──────────────────── TIMEOUT (TURNO PERDIDO) ────────────────────

    def reset_timeout(self):
        """Reinicia el timeout para la siguiente ronda."""
        self.timeout = TURN_TIMEOUT_SECONDS

    async def on_timeout(self):
        """Se ejecuta cuando expira el tiempo de la ronda."""
        if self.game_over:
            return

        # Marcar como 'timeout' a quienes no hayan elegido acción
        if self.p1_action is None:
            self.p1_action = 'timeout'
            self.p1.consecutive_timeouts += 1
        
        if self.p2_action is None:
            self.p2_action = 'timeout'
            self.p2.consecutive_timeouts += 1

        # Comprobar derrotas automáticas por inactividad
        if self.p1.consecutive_timeouts >= 2 or self.p2.consecutive_timeouts >= 2:
            self.game_over = True
            if self.p1.consecutive_timeouts >= 2 and self.p2.consecutive_timeouts >= 2:
                self.action_log.append("⏰ Ambos jugadores no respondieron 2 veces → **Derrota por inactividad**")
                self.p1.hp = 0
                self.p2.hp = 0
            elif self.p1.consecutive_timeouts >= 2:
                self.action_log.append(f"⏰ {self.p1.user.display_name} no respondió 2 veces → **Derrota automática**")
                self.p1.hp = 0
            else:
                self.action_log.append(f"⏰ {self.p2.user.display_name} no respondió 2 veces → **Derrota automática**")
                self.p2.hp = 0
            await self._finish_duel_from_timeout()
            return

        # Resolver la ronda con el timeout
        await self._resolve_round(interaction=None)

    # ──────────────────── FIN DEL DUELO ────────────────────

    async def _finish_duel(self, interaction: discord.Interaction):
        """Finaliza el duelo desde una interacción de botón."""
        if self._payout_done:
            return
        self._payout_done = True

        try:
            embed = await self._resolve_duel()
        finally:
            self.cog.active_duels.discard(self.p1.user.id)
            self.cog.active_duels.discard(self.p2.user.id)

        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True

        await interaction.message.edit(embed=embed, view=self)
        self.stop()

    async def _finish_duel_from_timeout(self):
        """Finaliza el duelo desde un timeout (sin interacción disponible)."""
        if self._payout_done:
            return
        self._payout_done = True

        try:
            embed = await self._resolve_duel()
        finally:
            self.cog.active_duels.discard(self.p1.user.id)
            self.cog.active_duels.discard(self.p2.user.id)

        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True

        try:
            if self.interaction_msg:
                await self.interaction_msg.edit(embed=embed, view=self)
        except Exception:
            pass
        self.stop()

    async def _resolve_duel(self):
        """Lógica de resolución: decidir ganador, pagar, dar XP, resolver drops."""
        # Determinar ganador
        if self.p1.hp <= 0 and self.p2.hp <= 0:
            # Ambos murieron (edge case) → gana el que tenía más % HP antes
            p1_pct = self.p1.pre_hit_hp / self.p1.max_hp
            p2_pct = self.p2.pre_hit_hp / self.p2.max_hp
            if p1_pct > p2_pct:
                winner, loser = self.p1, self.p2
            elif p2_pct > p1_pct:
                winner, loser = self.p2, self.p1
            else:
                if random.random() < 0.5:
                    winner, loser = self.p1, self.p2
                else:
                    winner, loser = self.p2, self.p1
        elif self.p1.hp <= 0:
            winner, loser = self.p2, self.p1
        elif self.p2.hp <= 0:
            winner, loser = self.p1, self.p2
        else:
            winner, loser = self.p1, self.p2

        # ── Transferencia de apuesta ──
        await asyncio.to_thread(add_balance, winner.user.id, self.bet * 2)
        await asyncio.to_thread(registrar_transaccion, winner.user.id, self.bet, "Duelo PvP: victoria")
        await asyncio.to_thread(registrar_transaccion, loser.user.id, -self.bet, "Duelo PvP: derrota")

        # ── XP ──
        winner_xp = calc_duel_xp(True, loser.level)
        loser_xp = calc_duel_xp(False, winner.level)

        w_result = await asyncio.to_thread(
            update_combat_stats_after_duel, winner.user.id, winner_xp, True, self.bet
        )
        l_result = await asyncio.to_thread(
            update_combat_stats_after_duel, loser.user.id, loser_xp, False, -self.bet
        )

        # ── Log ──
        try:
            await asyncio.to_thread(
                log_duel, self.p1.user.id, self.p2.user.id, winner.user.id,
                self.bet, self.turn_count, self.p1.level, self.p2.level
            )
        except Exception as e:
            logger.error(f"Error al registrar log de duelo en DB: {e}", exc_info=True)

        # ── Construir embed de resultado ──
        embed = discord.Embed(
            title="⚔️ Duelo PvP — Resultado Final",
            description=f"🏆 **{winner.user.display_name}** vence a **{loser.user.display_name}**!",
            color=discord.Color.gold()
        )

        # HP final
        for p in (self.p1, self.p2):
            hp_bar = format_hp_bar(max(0, p.hp), p.max_hp)
            icon = "🏆" if p == winner else "💀"
            embed.add_field(
                name=f"{icon} {p.user.display_name}",
                value=hp_bar,
                inline=True
            )

        # Registro final
        if self.action_log:
            embed.add_field(
                name="📜 Últimas acciones",
                value="\n".join(self.action_log[-3:]),
                inline=False
            )

        # Ganancia
        embed.add_field(
            name="💰 Recompensa",
            value=f"{winner.user.display_name} gana **{self.bet:,}** monedas",
            inline=False
        )

        # XP del ganador
        w_bar = format_progress_bar(w_result['xp'], w_result['xp_for_next'])
        w_rank = get_combat_rank_emoji(w_result['level'])
        w_xp_text = f"+{winner_xp} XP · `{w_bar}` {w_result['xp']:,}/{w_result['xp_for_next']:,}"
        if w_result.get('leveled_up'):
            w_xp_text += f"\n🎉 **¡Subió al nivel {w_result['level']}!** ({w_result['rank']})"
        embed.add_field(
            name=f"{w_rank} {winner.user.display_name} — XP",
            value=w_xp_text,
            inline=False
        )

        # XP del perdedor
        l_bar = format_progress_bar(l_result['xp'], l_result['xp_for_next'])
        l_rank = get_combat_rank_emoji(l_result['level'])
        l_xp_text = f"+{loser_xp} XP · `{l_bar}` {l_result['xp']:,}/{l_result['xp_for_next']:,}"
        if l_result.get('leveled_up'):
            l_xp_text += f"\n🎉 **¡Subió al nivel {l_result['level']}!** ({l_result['rank']})"
        embed.add_field(
            name=f"{l_rank} {loser.user.display_name} — XP",
            value=l_xp_text,
            inline=False
        )

        embed.set_footer(text=f"Duración: {self.turn_count} turnos · Apuesta: {self.bet:,} monedas")

        # ── Resolver drops ──
        # Se hace en un mensaje separado para no sobrecargar el embed
        await self._resolve_drops(winner, loser)

        # ── Limpiar duelos activos ──
        self.cog.active_duels.discard(self.p1.user.id)
        self.cog.active_duels.discard(self.p2.user.id)

        return embed

    async def _resolve_drops(self, winner: Combatant, loser: Combatant):
        """Resuelve la probabilidad de drop para ambos jugadores."""
        channel = None
        if self.interaction_msg:
            channel = self.interaction_msg.channel

        for player, rate, label in [
            (winner, DROP_RATE_WINNER, "Ganador"),
            (loser, DROP_RATE_LOSER, "Perdedor"),
        ]:
            if random.random() < rate:
                loot = generate_loot(player.level)
                equipment = await asyncio.to_thread(get_user_equipment, player.user.id)
                current_piece = equipment.get(loot["slot"])

                # Fallback: si no hay canal, intentamos DM al jugador
                effective_channel = channel
                if effective_channel is None:
                    try:
                        # Aseguramos que exista el DM channel
                        if player.user.dm_channel is None:
                            await player.user.create_dm()
                        effective_channel = player.user.dm_channel
                    except Exception as exc:
                        # Como último recurso, registramos un warning y no perdemos la excepción
                        logger.warning(
                            "No se pudo resolver canal para enviar drop a %s (id=%s): %r",
                            getattr(player.user, "name", "desconocido"),
                            getattr(player.user, "id", "desconocido"),
                            exc,
                        )
                        effective_channel = None

                if effective_channel is None:
                    # No tenemos forma de entregar el drop visualmente; lo registramos en logs
                    logger.warning(
                        "Drop generado para %s (id=%s) pero no se encontró canal para enviarlo. Loot: %s",
                        getattr(player.user, "name", "desconocido"),
                        getattr(player.user, "id", "desconocido"),
                        loot,
                    )
                    continue

                view = LootView(player.user, loot, current_piece)
                embed = view.build_embed()
                msg = await effective_channel.send(
                    content=f"🎁 {player.user.mention} — ¡Te ha caído un drop! ({label})",
                    embed=embed,
                    view=view,
                )
                view.message = msg


# ══════════════════════════════════════════════
# VISTA: DROP DE LOOT (Equipar / Vender)
# ══════════════════════════════════════════════

class LootView(discord.ui.View):
    """Vista de comparación para decidir si equipar o vender un drop."""

    def __init__(self, user: discord.Member, loot: dict, current_piece: dict | None):
        super().__init__(timeout=LOOT_TIMEOUT_SECONDS)
        self.user = user
        self.loot = loot
        self.current_piece = current_piece
        self.message = None
        self.resolved = False

    def build_embed(self):
        """Construye el embed de comparación."""
        loot = self.loot
        embed = discord.Embed(
            title=f"{loot['rarity_color']} {loot['name']}",
            description=f"**{loot['rarity']}** · Nivel {loot['item_level']} · {SLOT_EMOJIS.get(loot['slot'], '🔹')} {loot['slot']}",
            color=loot['rarity_hex']
        )

        # Nuevo ítem
        new_stats_text = format_item_stats_display(loot)
        embed.add_field(
            name="🆕 Nuevo",
            value=new_stats_text,
            inline=True
        )

        # Pieza actual
        if self.current_piece:
            cp = self.current_piece
            curr_stats_text = format_item_stats_display(cp)
            embed.add_field(
                name="📦 Actual",
                value=curr_stats_text,
                inline=True
            )
            
            # Diferencia por cada una de las stats
            diff_lines = []
            for stat in ALL_STATS:
                loot_val = loot['stats_summary'].get(stat, 0)
                
                # Obtener summary de la pieza actual
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
                embed.add_field(
                    name="📊 Diferencia",
                    value="\n".join(diff_lines),
                    inline=True
                )
            else:
                embed.add_field(
                    name="📊 Diferencia",
                    value="Stats idénticas",
                    inline=True
                )
        else:
            embed.add_field(
                name="📦 Actual",
                value="— Vacío —",
                inline=True
            )

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

        # Obtener stats del jugador
        c_stats = await asyncio.to_thread(get_combat_stats, self.user.id)
        player_level = c_stats['level']
        combat_class = c_stats.get('combat_class')
        
        # Validar equipamiento según clase y material a partir de nivel 5
        if player_level >= 5 and combat_class:
            slot = loot['slot']
            material = loot.get('material')
            
            # Restricciones de Armadura (Cabeza, Hombros, Pecho, Pantalones, Botas)
            is_armor = slot in ("Cabeza", "Hombros", "Pecho", "Pantalones", "Botas")
            if is_armor and material:
                class_materials = {
                    "Guerrero": ["Hierro"],
                    "Paladín": ["Hierro"],
                    "Pícaro": ["Cuero"],
                    "Mago": ["Tela"],
                    "Clérigo": ["Tela"]
                }
                allowed = class_materials.get(combat_class, [])
                if material not in allowed:
                    await interaction.response.send_message(
                        f"❌ Como **{combat_class}**, solo puedes equipar armaduras de **{', '.join(allowed)}** (este objeto es de {material}).",
                        ephemeral=True
                    )
                    return
            
            # Restricciones de Arma/Secundario
            if slot in ("Arma", "Escudo", "Bastón mágico"):
                class_weapons = {
                    "Guerrero": ["Arma", "Escudo"],
                    "Paladín": ["Arma", "Escudo"],
                    "Pícaro": ["Arma"],
                    "Mago": ["Bastón mágico"],
                    "Clérigo": ["Bastón mágico"]
                }
                allowed_w = class_weapons.get(combat_class, [])
                if slot not in allowed_w:
                    await interaction.response.send_message(
                        f"❌ Como **{combat_class}**, no puedes equipar un **{slot}** (permitidos: {', '.join(allowed_w)}).",
                        ephemeral=True
                    )
                    return

        self.resolved = True
        await interaction.response.defer()

        loot = self.loot
        # Equipar el ítem
        old = await asyncio.to_thread(
            equip_item, self.user.id,
            loot['slot'], loot['name'], loot['rarity'],
            loot['item_level'], loot['primary_stat'], loot['primary_value'],
            loot['secondaries'], loot['passive']
        )

        # Vender la pieza anterior si existía
        sell_msg = ""
        if old:
            old_sell = calc_sell_price(old['rarity'], old['item_level'])
            await asyncio.to_thread(add_balance, self.user.id, old_sell)
            await asyncio.to_thread(registrar_transaccion, self.user.id, old_sell,
                                    f"Venta equipo: {old['item_name']}")
            sell_msg = f"\n💰 Vendiste **{old['item_name']}** por **{old_sell:,}** monedas."

        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title=f"✅ ¡Equipado!",
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
        """Vende el drop."""
        loot = self.loot
        await asyncio.to_thread(add_balance, self.user.id, loot['sell_price'])
        await asyncio.to_thread(registrar_transaccion, self.user.id, loot['sell_price'],
                                f"Venta drop: {loot['name']}")

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
        """Auto-vender si no responde."""
        if not self.resolved:
            self.resolved = True
            await self._sell()


# ══════════════════════════════════════════════
# VISTA: SELECCIÓN DE CLASES (Nivel 5+)
# ══════════════════════════════════════════════

class ClassSelectionView(discord.ui.View):
    """Vista para que un jugador seleccione su clase de combate."""
    def __init__(self, user: discord.Member, current_class: str | None):
        super().__init__(timeout=60)
        self.user = user
        self.selected_class = None
        
        options = [
            discord.SelectOption(label="Guerrero ⚔️", value="Guerrero", description="Frenesí (+ATK, -DEF). Armadura: Hierro. Armas: Arma, Escudo."),
            discord.SelectOption(label="Paladín 🛡️", value="Paladín", description="Represalia (Mitiga y refleja). Armadura: Hierro. Armas: Arma, Escudo."),
            discord.SelectOption(label="Pícaro 🥷", value="Pícaro", description="Veneno (Daño continuo y debuff). Armadura: Cuero. Armas: Arma."),
            discord.SelectOption(label="Mago 🔥", value="Mago", description="Fuego (Daño mágico y quemadura). Armadura: Tela. Armas: Bastón."),
            discord.SelectOption(label="Clérigo ⚕️", value="Clérigo", description="Sanación (Roba vida y limpia estados). Armadura: Tela. Armas: Bastón.")
        ]
        
        placeholder = f"Clase actual: {current_class or 'Ninguna'}"
        self.select = discord.ui.Select(placeholder=placeholder, options=options, min_values=1, max_values=1)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este selector.", ephemeral=True)
            return

        self.selected_class = self.select.values[0]
        await interaction.response.defer()
        self.stop()


# ══════════════════════════════════════════════
# COG: DUELOS
# ══════════════════════════════════════════════

class DuelsCog(commands.Cog):
    """Sistema de Duelos PvP."""

    def __init__(self, bot):
        self.bot = bot
        self.active_duels: set[int] = set()  # IDs de usuarios en duelo activo

    # ──────────────────── /duelo ────────────────────

    @app_commands.command(name="duelo", description="Reta a otro usuario a un duelo PvP con apuesta de monedas")
    @app_commands.describe(
        rival="Usuario al que quieres retar",
        apuesta="Cantidad de monedas a apostar"
    )
    async def duelo_cmd(self, interaction: discord.Interaction, rival: discord.Member, apuesta: int):
        challenger = interaction.user
        challenger_id = challenger.id
        rival_id = rival.id

        # ── Validaciones ──

        if rival.bot:
            await interaction.response.send_message("❌ No puedes retar a un bot.", ephemeral=True)
            return

        if challenger_id == rival_id:
            await interaction.response.send_message("❌ No puedes retarte a ti mismo.", ephemeral=True)
            return

        if apuesta < MIN_BET:
            await interaction.response.send_message(
                f"❌ La apuesta mínima es **{MIN_BET:,}** monedas.", ephemeral=True
            )
            return

        if challenger_id in self.active_duels or rival_id in self.active_duels:
            await interaction.response.send_message(
                "❌ Uno de los jugadores ya tiene un duelo en curso.", ephemeral=True
            )
            return

        # Asegurar usuarios en DB
        await asyncio.to_thread(ensure_user, challenger_id, challenger.name)
        await asyncio.to_thread(ensure_user, rival_id, rival.name)

        # Verificar saldo de ambos
        c_balance = await asyncio.to_thread(get_balance, challenger_id)
        r_balance = await asyncio.to_thread(get_balance, rival_id)

        if c_balance < apuesta:
            await interaction.response.send_message(
                f"❌ No tienes suficiente saldo ({c_balance:,}/{apuesta:,} monedas).", ephemeral=True
            )
            return

        if r_balance < apuesta:
            await interaction.response.send_message(
                f"❌ {rival.mention} no tiene suficiente saldo para la apuesta.", ephemeral=True
            )
            return

        # Verificar stats de combate
        c_stats = await asyncio.to_thread(get_combat_stats, challenger_id)
        r_stats = await asyncio.to_thread(get_combat_stats, rival_id)



        # Diferencia de nivel
        level_diff = abs(c_stats['level'] - r_stats['level'])
        if level_diff > MAX_LEVEL_DIFFERENCE:
            await interaction.response.send_message(
                f"❌ La diferencia de nivel es demasiado grande "
                f"(Nv.{c_stats['level']} vs Nv.{r_stats['level']}, máx {MAX_LEVEL_DIFFERENCE}).",
                ephemeral=True
            )
            return

        # ── Cobrar apuesta al retador ──
        success, _ = await asyncio.to_thread(deduct_balance, challenger_id, apuesta)
        if not success:
            await interaction.response.send_message("❌ No se pudo cobrar la apuesta.", ephemeral=True)
            return

        # Marcar como activos
        self.active_duels.add(challenger_id)
        self.active_duels.add(rival_id)

        # ── Crear reto ──
        c_rank = get_combat_rank(c_stats['level'])
        r_rank = get_combat_rank(r_stats['level'])
        c_emoji = get_combat_rank_emoji(c_stats['level'])
        r_emoji = get_combat_rank_emoji(r_stats['level'])

        embed = discord.Embed(
            title="⚔️ ¡Reto a Duelo!",
            description=f"{challenger.mention} reta a {rival.mention} por **{apuesta:,}** monedas.",
            color=discord.Color.orange()
        )
        embed.add_field(
            name=f"{c_emoji} {challenger.display_name}",
            value=f"**{c_rank}** · Nv. {c_stats['level']}\n"
                  f"Victorias: {c_stats['wins']} · Derrotas: {c_stats['losses']}",
            inline=True
        )
        embed.add_field(
            name=f"{r_emoji} {rival.display_name}",
            value=f"**{r_rank}** · Nv. {r_stats['level']}\n"
                  f"Victorias: {r_stats['wins']} · Derrotas: {r_stats['losses']}",
            inline=True
        )
        embed.set_footer(text=f"El reto expira en {CHALLENGE_TIMEOUT_SECONDS}s · Solo {rival.display_name} puede responder")

        challenge_view = ChallengeView(challenger, rival, apuesta, self)
        await interaction.response.send_message(embed=embed, view=challenge_view)
        msg = await interaction.original_response()

        # Esperar respuesta
        await challenge_view.wait()

        if not challenge_view.accepted:
            return

        # ── Iniciar combate ──
        await asyncio.sleep(1)

        c_equip = await asyncio.to_thread(get_user_equipment, challenger_id)
        r_equip = await asyncio.to_thread(get_user_equipment, rival_id)

        p1 = Combatant(challenger, c_stats['level'], c_equip, c_stats.get('combat_class'))
        p2 = Combatant(rival, r_stats['level'], r_equip, r_stats.get('combat_class'))

        duel_view = DuelView(p1, p2, apuesta, self)
        embed = duel_view._build_embed()

        duel_msg = await interaction.followup.send(embed=embed, view=duel_view)
        duel_view.interaction_msg = duel_msg

    # ──────────────────── /clase ────────────────────

    @app_commands.command(name="clase", description="Elige o cambia tu clase de combate (requiere nivel 5)")
    async def clase_cmd(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        c_stats = await asyncio.to_thread(get_combat_stats, user_id)
        
        if c_stats['level'] < 5:
            await interaction.response.send_message(
                f"❌ Necesitas nivel de combate **5** para elegir una clase (nivel actual: {c_stats['level']}).",
                ephemeral=True
            )
            return

        current_class = c_stats.get('combat_class')
        
        embed = discord.Embed(
            title="🎭 Elige tu Clase de Combate",
            description="Al elegir una clase, tu Habilidad Especial en los duelos cambiará y solo podrás equipar armaduras de ciertos materiales y ciertas armas.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⚔️ Guerrero",
            value="**Especial:** `Frenesí de Batalla` (+35% ATK, +15% daño recibido por 2 turnos).\n"
                  "**Armadura:** Hierro (Placas) · **Armas:** Arma, Escudo",
            inline=False
        )
        embed.add_field(
            name="🛡️ Paladín",
            value="**Especial:** `Postura de Represalia` (mitiga 50% de daño y refleja 100% esa ronda).\n"
                  "**Armadura:** Hierro (Placas) · **Armas:** Arma, Escudo",
            inline=False
        )
        embed.add_field(
            name="🥷 Pícaro",
            value="**Especial:** `Daga Envenenada` (daño físico, -25% daño rival y 10 HP/t veneno por 3 turnos).\n"
                  "**Armadura:** Cuero · **Armas:** Arma",
            inline=False
        )
        embed.add_field(
            name="🔥 Mago",
            value="**Especial:** `Tormenta de Fuego` (daño mágico, quemadura de -5% HP max por 3 turnos).\n"
                  "**Armadura:** Tela · **Armas:** Bastón Mágico",
            inline=False
        )
        embed.add_field(
            name="⚕️ Clérigo",
            value="**Especial:** `Drenaje Sagrado` (roba 15% HP actual, limpia debuffs propios).\n"
                  "**Armadura:** Tela · **Armas:** Bastón Mágico",
            inline=False
        )
        
        if current_class:
            embed.set_footer(text=f"Tu clase actual es {current_class}. Si la cambias, tus piezas equipadas que no coincidan serán ignoradas en combate o deberás cambiarlas.")

        view = ClassSelectionView(interaction.user, current_class)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        await view.wait()
        
        if view.selected_class:
            success = await asyncio.to_thread(update_user_class, user_id, view.selected_class)
            if success:
                await interaction.followup.send(
                    f"✅ ¡Felicidades! Has elegido la clase **{view.selected_class}**. Tu habilidad especial en duelos ha sido actualizada.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("❌ Hubo un error al guardar tu clase en la base de datos.", ephemeral=True)

    # ──────────────────── /perfil_combate ────────────────────

    @app_commands.command(name="perfil_combate", description="Muestra tu nivel, rango, XP y estadísticas de combate")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def perfil_combate_cmd(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer(ephemeral=True)

        target = usuario or interaction.user
        await asyncio.to_thread(ensure_user, target.id, target.name)

        stats = await asyncio.to_thread(get_combat_stats, target.id)
        equipment = await asyncio.to_thread(get_user_equipment, target.id)

        rank = get_combat_rank(stats['level'])
        rank_emoji = get_combat_rank_emoji(stats['level'])
        base = calc_base_stats(stats['level'])

        bonus, passives = calc_equipment_bonus(equipment)
        effective, pct_used, pct_per_stat = get_effective_bonus(bonus, stats['level'])

        class_text = f" · Clase: **{stats['combat_class']}**" if stats.get('combat_class') else ""
        embed = discord.Embed(
            title=f"{rank_emoji} Perfil de Combate — {target.display_name}",
            description=f"**{rank}** · Nivel **{stats['level']}**{class_text}",
            color=discord.Color.dark_gold()
        )

        # XP
        xp_needed = calc_combat_xp_needed(stats['level'])
        if xp_needed > 0:
            bar = format_progress_bar(stats['xp'], xp_needed)
            embed.add_field(
                name="Experiencia",
                value=f"`{bar}` {stats['xp']:,}/{xp_needed:,} XP",
                inline=False
            )
        else:
            embed.add_field(name="Experiencia", value="✨ Nivel máximo alcanzado", inline=False)

        # Stats (4 stats)
        embed.add_field(
            name="📊 Estadísticas Base (+ Equipo)",
            value=(
                f"❤️ HP: {base['hp']} (+{effective.get('hp', 0)})\n"
                f"⚔️ ATK: {base['atk']} (+{effective.get('atk', 0)})\n"
                f"🔮 MAG: {base['mag']} (+{effective.get('mag', 0)})\n"
                f"🛡️ DEF: {base['def']} (+{effective.get('def', 0)})"
            ),
            inline=True
        )

        # W/L
        total = stats['wins'] + stats['losses']
        win_rate = (stats['wins'] / total * 100) if total > 0 else 0
        embed.add_field(
            name="⚔️ Combates",
            value=(
                f"Victorias: **{stats['wins']}**\n"
                f"Derrotas: **{stats['losses']}**\n"
                f"Winrate: **{win_rate:.1f}%**\n"
                f"Racha actual: **{stats['win_streak']}** 🔥\n"
                f"Mejor racha: **{stats['best_win_streak']}**"
            ),
            inline=True
        )

        # Economía
        net = stats['total_money_won'] - stats['total_money_lost']
        net_sign = "+" if net >= 0 else ""
        embed.add_field(
            name="💰 Economía de Duelos",
            value=(
                f"Ganado: {stats['total_money_won']:,}\n"
                f"Perdido: {stats['total_money_lost']:,}\n"
                f"Neto: **{net_sign}{net:,}**"
            ),
            inline=False
        )

        # Efectos Pasivos Legendarios
        if passives:
            passives_text = "\n".join([f"{p.get('emoji', '✨')} **{p['name']}**: {p['desc']}" for p in passives])
            embed.add_field(
                name="✨ Efectos Pasivos Legendarios",
                value=passives_text,
                inline=False
            )

        # Bonus de equipo
        gear_bar = format_progress_bar(int(pct_used), 100, size=10)
        embed.add_field(
            name="🎒 Bonus de Equipo",
            value=f"Tope usado: `{gear_bar}` {pct_used:.0f}%/{int(MAX_GEAR_BONUS_PCT * 100)}% (promedio)",
            inline=False
        )

        # Cooldown
        cooldown = get_duel_cooldown_minutes(stats['level'])
        embed.set_footer(text=f"Cooldown entre duelos: {cooldown:.0f} min")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ──────────────────── /duelo_inventario ────────────────────

    @app_commands.command(name="duelo_inventario", description="Muestra tu equipo de combate actual")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def duelo_inventario_cmd(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer(ephemeral=True)

        target = usuario or interaction.user
        await asyncio.to_thread(ensure_user, target.id, target.name)

        equipment = await asyncio.to_thread(get_user_equipment, target.id)
        stats = await asyncio.to_thread(get_combat_stats, target.id)

        bonus, passives = calc_equipment_bonus(equipment)
        effective, pct_used, pct_per_stat = get_effective_bonus(bonus, stats['level'])

        embed = discord.Embed(
            title=f"🎒 Equipo de Combate — {target.display_name}",
            description=f"Nivel de combate: **{stats['level']}**",
            color=discord.Color.dark_teal()
        )

        for slot in EQUIPMENT_SLOTS:
            emoji = SLOT_EMOJIS.get(slot, "🔹")
            piece = equipment.get(slot)
            if piece:
                rarity_color = ""
                for r in [("Común", "⬜"), ("Poco Común", "🟩"), ("Raro", "🟦"),
                          ("Épico", "🟪"), ("Legendario", "🟧")]:
                    if piece['rarity'] == r[0]:
                        rarity_color = r[1]
                        break
                
                # Formatear estadísticas
                stats_text = format_item_stats_display(piece)

                embed.add_field(
                    name=f"{emoji} {slot}",
                    value=f"{rarity_color} **{piece['item_name']}**\n"
                          f"{piece['rarity']} · iLvl {piece['item_level']}\n"
                          f"{stats_text}",
                    inline=True
                )
            else:
                embed.add_field(
                    name=f"{emoji} {slot}",
                    value="— Vacío —",
                    inline=True
                )

        # Bonus total
        bonus_text = (
            f"⚔️ ATK: +{effective.get('atk', 0)} · "
            f"🔮 MAG: +{effective.get('mag', 0)} · "
            f"🛡️ DEF: +{effective.get('def', 0)} · "
            f"❤️ HP: +{effective.get('hp', 0)}"
        )
        gear_bar = format_progress_bar(int(pct_used), 100, size=15)
        embed.add_field(
            name="📊 Bonus Total de Equipo",
            value=f"{bonus_text}\nTope: `{gear_bar}` {pct_used:.0f}%/{int(MAX_GEAR_BONUS_PCT * 100)}%",
            inline=False
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ──────────────────── /ranking_duelos ────────────────────

    @app_commands.command(name="ranking_duelos", description="Muestra el ranking de duelos PvP")
    @app_commands.describe(criterio="Ordenar por victorias o nivel")
    @app_commands.choices(criterio=[
        app_commands.Choice(name="Victorias", value="wins"),
        app_commands.Choice(name="Nivel", value="level"),
    ])
    async def ranking_duelos_cmd(self, interaction: discord.Interaction,
                                  criterio: app_commands.Choice[str] = None):
        await interaction.response.defer()

        order = criterio.value if criterio else "wins"
        rows = await asyncio.to_thread(get_duel_leaderboard, order, 10)

        if not rows:
            await interaction.followup.send("📊 Aún no hay duelos registrados.", ephemeral=True)
            return

        title_map = {"wins": "Victorias", "level": "Nivel"}
        embed = discord.Embed(
            title=f"🏆 Ranking de Duelos — {title_map.get(order, 'Victorias')}",
            color=discord.Color.gold()
        )

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows):
            user_id, level, wins, losses, streak, best_streak = row
            rank_emoji = get_combat_rank_emoji(level)
            medal = medals[i] if i < 3 else f"`{i+1}.`"

            # Intentar obtener nombre del usuario
            try:
                member = self.bot.get_user(user_id)
                name = member.display_name if member else f"User {user_id}"
            except Exception:
                name = f"User {user_id}"

            total = wins + losses
            wr = (wins / total * 100) if total > 0 else 0

            lines.append(
                f"{medal} {rank_emoji} **{name}** · Nv.{level}\n"
                f"   {wins}W/{losses}L ({wr:.0f}%) · Mejor racha: {best_streak} 🔥"
            )

        embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(DuelsCog(bot))
    logger.info("Duels cog loaded successfully.")
