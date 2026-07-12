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
    update_user_class, update_user_subclass, update_user_class_and_subclass,
)
from src.utils.combat_progression import (
    calc_base_stats, calc_duel_xp, get_duel_cooldown_minutes,
    calc_attack_damage, calc_special_damage, calc_defend_heal,
    calc_equipment_bonus, get_effective_bonus,
    apply_subclass_equipment_conversion,
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
from src.utils.subclass_config import (
    SUBCLASSES, SUBCLASS_TO_CLASS, CLASS_SUBCLASSES,
    SUBCLASS_UNLOCK_LEVEL, ULTIMATE_UNLOCK_LEVEL,
    get_subclass_config, get_subclass_skills, get_available_subclasses,
    get_all_subclass_info_for_display,
)


# ══════════════════════════════════════════════
# ESTADO DE UN JUGADOR EN COMBATE
# ══════════════════════════════════════════════

class Combatant:
    """Estado de un jugador durante el combate."""

    def __init__(self, user: discord.Member, level: int, equipment: dict,
                 combat_class: str = None, combat_subclass: str = None):
        self.user = user
        self.level = level
        self.combat_class = combat_class
        self.combat_subclass = combat_subclass

        # Stats base
        base = calc_base_stats(level)
        bonus, passives = calc_equipment_bonus(equipment)

        # Aplicar conversión de equipo por subclase (antes del cap)
        bonus, self.subclass_extras = apply_subclass_equipment_conversion(bonus, combat_subclass)

        effective, _, pct_per_stat = get_effective_bonus(bonus, level)

        self.max_hp = base["hp"] + int(round(effective.get("hp", 0)))
        self.hp = self.max_hp
        self.pre_hit_hp = self.hp
        self.atk = base["atk"] + int(round(effective.get("atk", 0)))
        self.base_atk = self.atk  # Para restaurar tras debuffs
        self.mag = base["mag"] + int(round(effective.get("mag", 0)))
        self.def_stat = base["def"] + int(round(effective.get("def", 0)))

        # Escudo de absorción de subclase (Guardián Sagrado, Guardián de la Fe)
        self.shield = self.subclass_extras.get("shield_pool", 0)

        # Estado de combate
        self.is_defending = False
        self.special_cooldown = 0  # Turnos restantes de cooldown del Especial
        self.skill10_cooldown = 0  # Cooldown de habilidad Nv.10
        self.skill15_cooldown = 0  # Cooldown de habilidad Nv.15 (ultimate)
        self.consecutive_timeouts = 0

        # Estados de subclase (duelos)
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
        self.total_damage_taken = 0         # Acumulador para Castigo Divino
        self.enhanced_burn_pct = 0.0        # Quemadura mejorada (Cataclismo)
        self.enhanced_burn_turns = 0

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

def get_combatant_available_skills(combatant):
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


class PersonalDuelSkillSelectView(discord.ui.View):
    """Menú efímero de un solo select para que un jugador elija su habilidad especial en un duelo."""

    def __init__(self, duel_view, player, options: list[discord.SelectOption]):
        super().__init__(timeout=60)
        self.duel_view = duel_view
        self.player = player

        select = discord.ui.Select(
            placeholder="✨ Seleccionar Habilidad Especial...",
            min_values=1,
            max_values=1,
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True
        await interaction.response.edit_message(view=self)

        if self.duel_view.game_over:
            await interaction.followup.send("❌ El duelo ya terminó.", ephemeral=True)
            return

        current_action = self.duel_view.p1_action if self.player == self.duel_view.p1 else self.duel_view.p2_action
        if current_action is not None:
            await interaction.followup.send("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
            return

        selected_value = interaction.data["values"][0]

        # Validaciones de defensa en profundidad
        from src.utils.combat_config import SKILLS_CONFIG
        req = SKILLS_CONFIG.get(selected_value)
        if not req:
            await interaction.followup.send("❌ Habilidad desconocida.", ephemeral=True)
            return

        if req.get("min_level") == 10:
            cd = self.player.skill10_cooldown
        elif req.get("min_level") == 15:
            cd = self.player.skill15_cooldown
        else:
            cd = self.player.special_cooldown

        if cd > 0:
            await interaction.followup.send(
                f"❌ Habilidad en enfriamiento ({cd} turnos restantes).",
                ephemeral=True
            )
            return

        if req["class"] is not None:
            if self.player.level < req["min_level"] or self.player.combat_class != req["class"]:
                await interaction.followup.send(
                    f"❌ Solo los **{req['class']}** de nivel **{req['min_level']}+** pueden usar esta habilidad.",
                    ephemeral=True
                )
                return
        else:
            if self.player.level >= 5 and self.player.combat_class is not None:
                await interaction.followup.send(
                    "❌ Ya tienes una clase asignada. Debes usar la habilidad especial de tu clase.",
                    ephemeral=True
                )
                return

        if req.get("subclass") is not None:
            if self.player.combat_subclass != req["subclass"]:
                await interaction.followup.send(
                    f"❌ Solo la subclase **{req['subclass']}** puede usar esta habilidad.",
                    ephemeral=True
                )
                return

        # Registrar la acción
        if self.player == self.duel_view.p1:
            self.duel_view.p1_action = 'special'
            self.duel_view.p1_special_id = selected_value
            self.duel_view.p1.consecutive_timeouts = 0
        else:
            self.duel_view.p2_action = 'special'
            self.duel_view.p2_special_id = selected_value
            self.duel_view.p2.consecutive_timeouts = 0

        await interaction.followup.send(f"✅ Habilidad especial registrada: **{req['name']}**", ephemeral=True)
        await self.duel_view._check_and_resolve(interaction, is_ephemeral=True)


class DuelView(discord.ui.View):
    """Vista principal del combate PvP por turnos simultáneos."""

    def __init__(self, p1: Combatant, p2: Combatant, bet: int, cog: 'DuelsCog'):
        super().__init__(timeout=TURN_TIMEOUT_SECONDS)
        self.p1 = p1
        self.p2 = p2
        self.bet = bet
        self.cog = cog

        # Habilidades especiales se manejan de forma efímera por botón

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
        self.p1_poison_damage = 0
        self.p2_poison_damage = 0
        
        self.turn_count = 0
        self.game_over = False
        self._payout_done = False
        self.action_log = []  # Registro de acciones recientes
        self.interaction_msg = None  # Referencia al mensaje del duelo

    def _build_embed(self):
        """Construye el embed de estado del combate."""
        status_p1 = "🟢 ¡Listo!" if self.p1_action else "🔴 Eligiendo..."
        status_p2 = "🟢 ¡Listo!" if self.p2_action else "🔴 Eligiendo..."

        is_sudden_death = (self.turn_count + 1) >= 50
        title_text = "⚔️ Duelo PvP Simultáneo (¡MUERTE SÚBITA!)" if is_sudden_death else "⚔️ Duelo PvP Simultáneo"
        embed_color = discord.Color.red() if is_sudden_death else discord.Color.dark_gold()

        desc_lines = [f"**Ronda {self.turn_count + 1}**"]
        if is_sudden_death:
            desc_lines.append("⚠️ **¡MUERTE SÚBITA ACTIVA! Daño aumentado +100%** ⚠️\n")
        desc_lines.append(f"{self.p1.user.mention}: {status_p1}")
        desc_lines.append(f"{self.p2.user.mention}: {status_p2}")

        embed = discord.Embed(
            title=title_text,
            description="\n".join(desc_lines),
            color=embed_color
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
                status_icons += f" 👁️({blind_turns}t)"
            if frenzy_turns > 0:
                status_icons += f" ⚔️(Frenesí {frenzy_turns}t)"
            if poison_turns > 0:
                status_icons += f" 🧪({poison_turns}t)"
            if burn_turns > 0:
                status_icons += f" 🔥({burn_turns}t)"
            if p.stun_turns > 0:
                status_icons += f" 💫(Aturdido {p.stun_turns}t)"
            if p.damage_reduction_turns > 0:
                status_icons += f" 🏰(-{int(p.damage_reduction_pct*100)}% daño {p.damage_reduction_turns}t)"
            if p.atk_buff_turns > 0:
                status_icons += f" 💪(+{int(p.atk_buff_pct*100)}% ATK {p.atk_buff_turns}t)"
            if p.juicio_final_turns > 0:
                status_icons += f" ⚖️(Reflejo {p.juicio_final_turns}t)"
            if p.evasion_buff_turns > 0:
                status_icons += f" 💨(Evasión+ {p.evasion_buff_turns}t)"
            if p.guaranteed_dodge_next:
                status_icons += " 👻(Esquiva)"
            if p.anti_heal_turns > 0:
                status_icons += f" 🚫(Anti-cura {p.anti_heal_turns}t)"
            if p.weakness_turns > 0:
                status_icons += f" ❄️(Debil {p.weakness_turns}t)"
            if p.fragility_turns > 0:
                status_icons += f" 💔(Frágil {p.fragility_turns}t)"
            if p.vulnerability_turns > 0:
                status_icons += f" ⚠️(Vulner. {p.vulnerability_turns}t)"
            if p.shield > 0:
                status_icons += f" 🛡️({p.shield})"
            if p.special_cooldown > 0:
                status_icons += f" ⏳({p.special_cooldown}t)"
            if p.skill10_cooldown > 0:
                status_icons += f" ⏳S10({p.skill10_cooldown}t)"
            if p.skill15_cooldown > 0:
                status_icons += f" ⏳ULT({p.skill15_cooldown}t)"
            
            passive_icons = ""
            for pass_item in p.passives:
                passive_icons += f" {pass_item.get('emoji', '✨')}"

            # Mostrar subclase si la tiene, sino clase
            if p.combat_subclass:
                class_tag = f" [{p.combat_subclass}]"
            elif p.combat_class:
                class_tag = f" [{p.combat_class}]"
            else:
                class_tag = ""
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
        footer_text = f"Acciones: {' · '.join(actions)} · Tiempo por ronda: {TURN_TIMEOUT_SECONDS}s"
        if is_sudden_death:
            footer_text += " · ⚠️ Daño aumentado un 100%"
        embed.set_footer(text=footer_text)

        return embed

    # ──────────────────── BOTONES ────────────────────

    @discord.ui.button(label="⚔️ Atacar", style=discord.ButtonStyle.danger, row=0)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over:
            await interaction.response.send_message("❌ El duelo ya terminó.", ephemeral=True)
            return

        user_id = interaction.user.id
        cp = self.p1 if user_id == self.p1.user.id else self.p2 if user_id == self.p2.user.id else None
        if cp is None:
            await interaction.response.send_message("❌ No estás participando en este duelo.", ephemeral=True)
            return

        if cp.stun_turns > 0:
            await interaction.response.send_message("❌ Estás aturdido y no puedes actuar este turno.", ephemeral=True)
            return

        if user_id == self.p1.user.id:
            if self.p1_action is not None:
                await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
                return
            self.p1_action = 'attack'
            self.p1.consecutive_timeouts = 0
        else:
            if self.p2_action is not None:
                await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
                return
            self.p2_action = 'attack'
            self.p2.consecutive_timeouts = 0

        await self._check_and_resolve(interaction)

    @discord.ui.button(label="🛡️ Defender", style=discord.ButtonStyle.primary, row=0)
    async def defend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over:
            await interaction.response.send_message("❌ El duelo ya terminó.", ephemeral=True)
            return

        user_id = interaction.user.id
        cp = self.p1 if user_id == self.p1.user.id else self.p2 if user_id == self.p2.user.id else None
        if cp is None:
            await interaction.response.send_message("❌ No estás participando en este duelo.", ephemeral=True)
            return

        if cp.stun_turns > 0:
            await interaction.response.send_message("❌ Estás aturdido y no puedes actuar este turno.", ephemeral=True)
            return

        if user_id == self.p1.user.id:
            if self.p1_action is not None:
                await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
                return
            self.p1_action = 'defend'
            self.p1.consecutive_timeouts = 0
        else:
            if self.p2_action is not None:
                await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
                return
            self.p2_action = 'defend'
            self.p2.consecutive_timeouts = 0

        await self._check_and_resolve(interaction)

    @discord.ui.button(label="✨ Habilidad Especial", style=discord.ButtonStyle.secondary, row=1)
    async def special_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over:
            await interaction.response.send_message("❌ El duelo ya terminó.", ephemeral=True)
            return

        user_id = interaction.user.id
        cp = self.p1 if user_id == self.p1.user.id else self.p2 if user_id == self.p2.user.id else None
        if cp is None:
            await interaction.response.send_message("❌ No estás participando en este duelo.", ephemeral=True)
            return

        if cp.stun_turns > 0:
            await interaction.response.send_message("❌ Estás aturdido y no puedes actuar este turno.", ephemeral=True)
            return

        if cp.silence_turns > 0:
            await interaction.response.send_message("❌ Estás silenciado y no puedes usar habilidades especiales.", ephemeral=True)
            return

        current_action = self.p1_action if cp == self.p1 else self.p2_action
        if current_action is not None:
            await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
            return

        player_skills = get_combatant_available_skills(cp)
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

        view = PersonalDuelSkillSelectView(duel_view=self, player=cp, options=options)
        await interaction.response.send_message("Elige tu habilidad especial:", view=view, ephemeral=True)

    async def _check_and_resolve(self, interaction: discord.Interaction, is_ephemeral: bool = False):
        """Verifica si ambos jugadores han votado y resuelve el turno."""
        if self.p1_action is not None and self.p2_action is not None:
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

        # HoT Heal (Aura de Salvación)
        for p in (self.p1, self.p2):
            if p.hot_turns > 0 and p.hp > 0:
                if p.anti_heal_turns == 0:
                    hot_heal = int(p.max_hp * p.hot_pct)
                    p.hp = min(p.max_hp, p.hp + hot_heal)
                    logs.append(f"💚 **Aura de Salvación:** {p.user.display_name} se cura **{hot_heal}** HP por efecto gradual.")

        # 1. Aplicar regeneraciones pasivas de inicio de turno
        for p in (self.p1, self.p2):
            if any(p_item['id'] == 'regen' for p_item in p.passives) and p.hp > 0 and p.hp < p.max_hp:
                heal = max(1, int(p.max_hp * 0.03))
                p.hp = min(p.max_hp, p.hp + heal)
                logs.append(f"💚 **Regen:** {p.user.display_name} se cura **{heal}** HP.")

        # 1.5 Aplicar Fatiga si es el turno 50 en adelante
        is_sudden_death = (self.turn_count + 1) >= 50
        if is_sudden_death:
            fatigue_level = (self.turn_count + 1) - 50 + 1
            fatigue_pct = 0.05 * fatigue_level
            for defender in (self.p1, self.p2):
                if defender.hp <= 0:
                    continue
                fatigue_dmg = min(defender.hp, max(1, int(defender.max_hp * fatigue_pct)))
                defender.hp = max(0, defender.hp - fatigue_dmg)
                logs.append(f"💀 **Fatiga:** {defender.user.display_name} sufre **{fatigue_dmg}** HP de daño por fatiga ({int(fatigue_pct*100)}%).")

        # 1.6 Aplicar DOTs de clases (Quemadura, Veneno)
        for defender in (self.p1, self.p2):
            if defender.hp <= 0:
                continue
            
            p_turns = self.p1_poison_turns if defender == self.p1 else self.p2_poison_turns
            b_turns = self.p1_burn_turns if defender == self.p1 else self.p2_burn_turns
            
            sudden_death_tag = " ⚠️*(Muerte Súbita)*" if is_sudden_death else ""
            
            if p_turns > 0:
                dot_val = self.p1_poison_damage if defender == self.p1 else self.p2_poison_damage
                if dot_val == 0:
                    dot_val = SKILLS_CONFIG["veneno"]["dot_damage"]
                if is_sudden_death:
                    dot_val = dot_val * 2
                p_dmg = min(defender.hp, dot_val)
                defender.hp = max(0, defender.hp - p_dmg)
                logs.append(f"🧪 **Veneno:** {defender.user.display_name} sufre **{p_dmg}** HP de daño por veneno.{sudden_death_tag}")
                
            if b_turns > 0:
                caster = self.p2 if defender == self.p1 else self.p1
                dot_pct = 0.08 if defender.enhanced_burn_turns > 0 else SKILLS_CONFIG["quemadura"]["dot_max_hp_pct"]
                b_dmg_base = max(1, int(defender.max_hp * dot_pct))
                if caster.combat_subclass == "Piromante":
                    b_dmg_base += int(caster.mag * 0.15)
                if is_sudden_death:
                    b_dmg_base = b_dmg_base * 2
                b_dmg = min(defender.hp, b_dmg_base)
                defender.hp = max(0, defender.hp - b_dmg)
                logs.append(f"🔥 **Quemadura:** {defender.user.display_name} sufre **{b_dmg}** HP de daño por quemadura.{sudden_death_tag}")

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

        # Comprobar taunt pasivo de tanques al Defender
        for p in (self.p1, self.p2):
            if p.is_defending:
                has_taunt_subclass = p.combat_subclass in ["Centinela", "Guardián Sagrado", "Guardián de la Fe"]
                if has_taunt_subclass and p.taunt_cooldown == 0:
                    p.taunt_cooldown = 4 if p.combat_subclass == "Guardián de la Fe" else 3
                    if p.combat_subclass == "Guardián Sagrado":
                        shield_amt = int(p.max_hp * 0.05)
                        p.shield += shield_amt
                        logs.append(f"🛡️ **Taunt Pasivo:** {p.user.display_name} activa Taunt y obtiene un escudo de **{shield_amt}** HP.")
                    else:
                        logs.append(f"🛡️ **Taunt Pasivo:** {p.user.display_name} activa Taunt!")

        # 2.5 Procesar lanzamientos de Habilidades Especiales (Buffs/Debuffs)
        for caster, target, act in ((self.p1, self.p2, p1_act), (self.p2, self.p1, p2_act)):
            if act == 'special':
                special_id = self.p1_special_id if caster == self.p1 else self.p2_special_id
                cfg = SKILLS_CONFIG.get(special_id) if special_id else SKILLS_CONFIG["ceguera"]
                
                # Cooldown calculations
                has_mana_residual = any(p['id'] == 'mana_residual' for p in caster.passives)
                skill_cd = cfg.get("cooldown", 3)
                if has_mana_residual:
                    skill_cd = max(1, skill_cd - 1)
                
                if cfg.get("min_level") == 10:
                    caster.skill10_cooldown = skill_cd + 1  # +1 porque se decrementa al final de esta ronda
                elif cfg.get("min_level") == 15:
                    caster.skill15_cooldown = skill_cd + 1
                else:
                    caster.special_cooldown = skill_cd + 1
                
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
                    drain_pct = 0.15
                    is_sudden_death = (self.turn_count + 1) >= 50
                    if is_sudden_death:
                        drain_pct = 0.30
                    steal_amt = max(1, int(target.hp * drain_pct))
                    target.hp = max(0, target.hp - steal_amt)
                    caster.hp = min(caster.max_hp, caster.hp + steal_amt)
                    # Limpiar debuffs propios
                    if caster == self.p1:
                        self.p1_blinded_turns = 0
                        self.p1_poison_turns = 0
                        self.p1_poison_damage = 0
                        self.p1_burn_turns = 0
                    else:
                        self.p2_blinded_turns = 0
                        self.p2_poison_turns = 0
                        self.p2_poison_damage = 0
                        self.p2_burn_turns = 0
                    sudden_death_tag = " ⚠️*(Muerte Súbita)*" if is_sudden_death else ""
                    logs.append(f"⚕️ **Drenaje Sagrado:** {caster.user.display_name} roba **{steal_amt}** HP a {target.user.display_name} y purifica todas sus condiciones!{sudden_death_tag}")
                
                # Habilidades Especiales de Subclase (Soporte / Instantáneas)
                elif special_id == "sed_sangre":
                    sacrifice = int(caster.hp * 0.25)
                    caster.hp = max(1, caster.hp - sacrifice)
                    caster.atk_buff_turns = 4
                    caster.atk_buff_pct = 0.60
                    logs.append(f"🩸 **Sed de Sangre:** {caster.user.display_name} sacrifica **{sacrifice}** HP y gana +60% ATK por 3 turnos.")
                elif special_id == "estandarte_guerra":
                    caster.atk_buff_turns = 4
                    caster.atk_buff_pct = 0.20
                    logs.append(f"🚩 **Estandarte de Guerra:** {caster.user.display_name} coloca un estandarte. ¡Gana +20% ATK por 3 turnos!")
                elif special_id == "escudo_compartido":
                    shield_val = int(caster.max_hp * 0.20)
                    caster.shield += shield_val
                    logs.append(f"🛡️ **Escudo Compartido:** {caster.user.display_name} obtiene un escudo de **{shield_val}** HP.")
                elif special_id == "bendicion_hierro":
                    shield_val = int(caster.max_hp * 0.18)
                    caster.shield += shield_val
                    logs.append(f"🛡️ **Bendición de Hierro:** {caster.user.display_name} se protege con un escudo de **{shield_val}** HP.")
                elif special_id == "paso_fantasma":
                    caster.guaranteed_dodge_next = True
                    logs.append(f"👥 **Paso Fantasma:** {caster.user.display_name} se desvanece en las sombras. ¡Esquivará el próximo ataque!")
                elif special_id == "luz_curativa":
                    if caster.anti_heal_turns > 0:
                        logs.append(f"🚫 **Luz Curativa:** {caster.user.display_name} intentó curarse, pero está afectado por anti-cura.")
                    else:
                        heal_val = int(caster.max_hp * 0.25) + caster.subclass_extras.get("heal_power", 0)
                        caster.hp = min(caster.max_hp, caster.hp + heal_val)
                        logs.append(f"💚 **Luz Curativa:** {caster.user.display_name} se cura **{heal_val}** HP.")
                elif special_id == "resurreccion_parcial":
                    if caster.anti_heal_turns > 0:
                        logs.append(f"🚫 **Resurrección Parcial:** {caster.user.display_name} intentó curarse, pero está afectado por anti-cura.")
                    else:
                        heal_val = int(caster.max_hp * 0.40) + caster.subclass_extras.get("heal_power", 0)
                        caster.hp = min(caster.max_hp, caster.hp + heal_val)
                        logs.append(f"💚 **Resurrección Parcial:** {caster.user.display_name} se cura **{heal_val}** HP.")
                elif special_id == "santuario":
                    shield_val = int(caster.max_hp * 0.15)
                    caster.shield += shield_val
                    if caster == self.p1:
                        self.p1_blinded_turns = 0
                        self.p1_poison_turns = 0
                        self.p1_poison_damage = 0
                        self.p1_burn_turns = 0
                    else:
                        self.p2_blinded_turns = 0
                        self.p2_poison_turns = 0
                        self.p2_poison_damage = 0
                        self.p2_burn_turns = 0
                    caster.stun_turns = 0
                    caster.frozen_turns = 0
                    caster.silence_turns = 0
                    caster.weakness_turns = 0
                    caster.fragility_turns = 0
                    caster.vulnerability_turns = 0
                    caster.anti_heal_turns = 0
                    logs.append(f"🛡️ **Santuario:** {caster.user.display_name} crea un santuario: Escudo de **{shield_val}** HP y disipa todos sus debuffs.")
                elif special_id == "muralla_inquebrantable":
                    caster.damage_reduction_turns = 4
                    caster.damage_reduction_pct = 0.50
                    logs.append(f"🏰 **Muralla Inquebrantable:** {caster.user.display_name} se atrinchera. ¡Recibe -50% de daño por 3 turnos!")
                elif special_id == "aura_salvacion":
                    shield_val = int(caster.max_hp * 0.15)
                    caster.shield += shield_val
                    caster.hot_turns = 4
                    caster.hot_pct = 0.05
                    logs.append(f"💛 **Aura de Salvación:** {caster.user.display_name} activa un aura: Escudo de **{shield_val}** HP y curación gradual (+5%/t) por 3 turnos.")
                elif special_id == "juicio_final":
                    caster.juicio_final_turns = 3
                    caster.juicio_final_reflect_pct = 1.50
                    logs.append(f"⚖️ **Juicio Final:** {caster.user.display_name} emite una luz juzgadora. ¡Reflejará 150% de daño recibido por 2 turnos!")

        # 3. Calcular ataque de P1 a P2
        p1_dmg = 0
        p1_log = ""
        p1_is_magic = False
        if p1_act in ('attack', 'special'):
            p1_dmg, p1_log = self._calculate_action_result(self.p1, self.p2, p1_act)
            if p1_act == 'special':
                p1_is_magic = self.p1_special_id in ("drenaje", "quemadura", "onda_escarcha", "sobrecarga_arcana", "tormenta_elemental", "singularidad", "pacto_sangre")

        # 4. Calcular ataque de P2 a P1
        p2_dmg = 0
        p2_log = ""
        p2_is_magic = False
        if p2_act in ('attack', 'special'):
            p2_dmg, p2_log = self._calculate_action_result(self.p2, self.p1, p2_act)
            if p2_act == 'special':
                p2_is_magic = self.p2_special_id in ("drenaje", "quemadura", "onda_escarcha", "sobrecarga_arcana", "tormenta_elemental", "singularidad", "pacto_sangre")

        # 5. Aplicar daño simultáneamente
        # P1 a P2
        if p1_dmg > 0:
            if not p1_is_magic:
                self.p2.last_physical_damage_taken = p1_dmg
            if self.p2.juicio_final_turns > 0:
                reflect_dmg = int(p1_dmg * self.p2.juicio_final_reflect_pct)
                self.p2.hp = max(0, self.p2.hp - p1_dmg)
                self.p1.hp = max(0, self.p1.hp - reflect_dmg)
                logs.append(f"⚖️ **Juicio Final:** {self.p2.user.display_name} refleja el golpe devolviendo **{reflect_dmg}** de daño a {self.p1.user.display_name}!")
            elif self.p2_retribution_active:
                cfg_rep = SKILLS_CONFIG["represalia"]
                mitigated = max(1, int(p1_dmg * cfg_rep["mitigation"]))
                reflect_dmg = int(p1_dmg * cfg_rep["reflect"])
                # Apply Vengador reflect boost conversion if any (+25% extra reflect, -15% mitigation)
                extra_reflect = self.p2.subclass_extras.get("extra_reflect_pct", 0.0)
                less_mitigation = self.p2.subclass_extras.get("less_mitigation_pct", 0.0)
                reflect_dmg = int(reflect_dmg * (1.0 + extra_reflect))
                mitigated = max(1, int(p1_dmg * (cfg_rep["mitigation"] + less_mitigation)))
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
            if not p2_is_magic:
                self.p1.last_physical_damage_taken = p2_dmg
            if self.p1.juicio_final_turns > 0:
                reflect_dmg = int(p2_dmg * self.p1.juicio_final_reflect_pct)
                self.p1.hp = max(0, self.p1.hp - p2_dmg)
                self.p2.hp = max(0, self.p2.hp - reflect_dmg)
                logs.append(f"⚖️ **Juicio Final:** {self.p1.user.display_name} refleja el golpe devolviendo **{reflect_dmg}** de daño a {self.p2.user.display_name}!")
            elif self.p1_retribution_active:
                cfg_rep = SKILLS_CONFIG["represalia"]
                mitigated = max(1, int(p2_dmg * cfg_rep["mitigation"]))
                reflect_dmg = int(p2_dmg * cfg_rep["reflect"])
                # Apply Vengador reflect boost conversion if any (+25% extra reflect, -15% mitigation)
                extra_reflect = self.p1.subclass_extras.get("extra_reflect_pct", 0.0)
                less_mitigation = self.p1.subclass_extras.get("less_mitigation_pct", 0.0)
                reflect_dmg = int(reflect_dmg * (1.0 + extra_reflect))
                mitigated = max(1, int(p2_dmg * (cfg_rep["mitigation"] + less_mitigation)))
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

        # Accumulate damage taken
        for p in (self.p1, self.p2):
            damage_taken = p.pre_hit_hp - p.hp
            if damage_taken > 0:
                p.total_damage_taken += damage_taken

        # Decrementar cooldowns de especial y turnos de buffs/debuffs
        for p in (self.p1, self.p2):
            if p.frozen_turns > 0:
                # Si está congelado, los cooldowns no se reducen
                pass
            else:
                if p.special_cooldown > 0:
                    p.special_cooldown -= 1
                if p.skill10_cooldown > 0:
                    p.skill10_cooldown -= 1
                if p.skill15_cooldown > 0:
                    p.skill15_cooldown -= 1
            if p.taunt_cooldown > 0:
                p.taunt_cooldown -= 1
            if p.stun_turns > 0:
                p.stun_turns -= 1
            if p.frozen_turns > 0:
                p.frozen_turns -= 1
            if p.silence_turns > 0:
                p.silence_turns -= 1
            if p.bleed_turns > 0 and p.hp > 0:
                b_dmg = max(1, int(p.last_physical_damage_taken * p.bleed_source_pct))
                p.hp = max(0, p.hp - b_dmg)
                p.bleed_turns -= 1
                logs.append(f"🩸 **Sangrado:** {p.user.display_name} sufre **{b_dmg}** HP de daño por sangrado.")
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
            if p.hot_turns > 0:
                p.hot_turns -= 1
            if p.enhanced_burn_turns > 0:
                p.enhanced_burn_turns -= 1

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
            if self.p1_poison_turns == 0:
                self.p1_poison_damage = 0
        if self.p2_poison_turns > 0:
            self.p2_poison_turns -= 1
            if self.p2_poison_turns == 0:
                self.p2_poison_damage = 0
            
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
            new_view.p1_poison_damage = self.p1_poison_damage
            new_view.p2_poison_damage = self.p2_poison_damage
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

    def _calculate_action_result(self, attacker: Combatant, defender: Combatant, action_type: str) -> tuple[int, str]:
        """Calcula el daño y genera la línea de log para una acción ofensiva individual."""
        import random

        # Verificar si el atacante está cegado
        blind_turns = self.p1_blinded_turns if attacker == self.p1 else self.p2_blinded_turns
        if blind_turns > 0 and random.random() < SKILLS_CONFIG["ceguera"]["fail_chance"]:
            log_line = f"💨 {attacker.user.display_name} tiene los ojos llenos de tierra y **FALLÓ** su ataque!"
            return 0, log_line

        # Evasión y Esquiva
        dodge_chance = defender.subclass_extras.get("dodge_chance_bonus", 0.0) + (defender.evasion_buff_pct if defender.evasion_buff_turns > 0 else 0.0)
        has_dodge_passive = any(p['id'] == 'dodge' for p in defender.passives)
        if has_dodge_passive:
            dodge_chance += 0.05
            
        special_id = self.p1_special_id if attacker == self.p1 else self.p2_special_id
        if action_type == 'special' and special_id == 'estocada_precisa':
            # Estocada precisa ignora 50% de la evasión del rival
            dodge_chance *= 0.5

        if defender.guaranteed_dodge_next:
            defender.guaranteed_dodge_next = False
            if action_type == 'special' and special_id == 'estocada_precisa' and random.random() < 0.5:
                # Estocada Precisa tiene un 50% de chance de atravesar el Paso Fantasma
                pass
            else:
                log_line = f"💨 {defender.user.display_name} **ESQUIVÓ** el ataque de {attacker.user.display_name} gracias a Paso Fantasma!"
                return 0, log_line
        elif dodge_chance > 0 and random.random() < dodge_chance:
            log_line = f"💨 {defender.user.display_name} **ESQUIVÓ** el ataque de {attacker.user.display_name}!"
            return 0, log_line

        # Si el atacante tiene Frenesí activo: +35% ATK
        atk_val = attacker.atk
        if (self.p1_frenzy_turns > 0 and attacker == self.p1) or (self.p2_frenzy_turns > 0 and attacker == self.p2):
            atk_boost = SKILLS_CONFIG["frenesi"]["atk_boost"]
            atk_val = int(atk_val * (1.0 + atk_boost))

        # Buffs / Debuffs de subclase
        if attacker.atk_buff_turns > 0:
            atk_val = int(atk_val * (1.0 + attacker.atk_buff_pct))
        if attacker.weakness_turns > 0:
            atk_val = int(atk_val * (1.0 - attacker.weakness_pct))
            
        defender_def_val = defender.def_stat
        if defender.fragility_turns > 0:
            defender_def_val = int(defender_def_val * (1.0 - defender.fragility_pct))

        # Si tiene pasiva de parry, no recibe reducción de daño de defender (pero sí cuenta para contraataque en el loop principal)
        defender_has_parry = any(p['id'] == 'parry' for p in defender.passives)
        is_defending_for_damage = defender.is_defending and not defender_has_parry

        # Pasivo: Golpe crítico
        extra_crit = 0.10 if any(p['id'] == 'crit_boost' for p in attacker.passives) else 0.0
        # Agregar bonus de crit por subclase (Duelista conversion)
        extra_crit += attacker.subclass_extras.get("crit_chance_bonus", 0.0)
        
        # Pasivo: Furia creciente
        has_fury = any(p['id'] == 'fury' for p in attacker.passives)
        fury_active = (attacker.hp / attacker.max_hp) < 0.30

        # Helper para aplicar modificadores comunes y formatear log
        def finalize_damage_and_log(raw_damage, skill_name, skill_emoji, detail_log="", custom_log=None):
            dmg = raw_damage
            
            # Amplificación combinada
            amp_pct = 0.0
            if (self.p1_frenzy_turns > 0 and defender == self.p1) or (self.p2_frenzy_turns > 0 and defender == self.p2):
                amp_pct += SKILLS_CONFIG["frenesi"]["damage_received_boost"]
            if defender.vulnerability_turns > 0:
                amp_pct += defender.vulnerability_pct
            
            amp_pct = min(0.75, amp_pct)
            dmg = int(dmg * (1.0 + amp_pct))
                
            # Damage reduction
            if defender.damage_reduction_turns > 0:
                dmg = int(dmg * (1.0 - defender.damage_reduction_pct))
                
            # Escudo arcano
            shield_log = ""
            if defender.arcane_shield_active:
                dmg = max(1, int(dmg / 2))
                defender.arcane_shield_active = False
                shield_log = " 🔮*(Escudo arcano reduce daño)*"
                
            # Muerte súbita (turno 50+)
            sudden_death_log = ""
            if (self.turn_count + 1) >= 50:
                dmg = dmg * 2
                sudden_death_log = " ⚠️*(Muerte Súbita)*"
                
            if custom_log:
                log_line = custom_log + f"{shield_log}{sudden_death_log}"
            else:
                log_line = f"{skill_emoji} {attacker.user.display_name} usa **{skill_name}** → **{dmg}** daño a {defender.user.display_name}!{detail_log}{shield_log}{sudden_death_log}"
            return dmg, log_line

        if action_type == 'attack':
            damage, crit = calc_attack_damage(atk_val, defender_def_val, is_defending_for_damage, extra_crit, has_fury, fury_active)
            
            # Amplificación combinada
            amp_pct = 0.0
            if (self.p1_frenzy_turns > 0 and defender == self.p1) or (self.p2_frenzy_turns > 0 and defender == self.p2):
                amp_pct += SKILLS_CONFIG["frenesi"]["damage_received_boost"]
            if defender.vulnerability_turns > 0:
                amp_pct += defender.vulnerability_pct
                
            amp_pct = min(0.75, amp_pct)
            damage = int(damage * (1.0 + amp_pct))
            if defender.damage_reduction_turns > 0:
                damage = int(damage * (1.0 - defender.damage_reduction_pct))
            
            # Pasivo: Escudo arcano
            shield_log = ""
            if defender.arcane_shield_active:
                damage = max(1, int(damage / 2))
                defender.arcane_shield_active = False
                shield_log = " 🔮*(Escudo arcano reduce daño)*"
                
            # Muerte súbita (turno 50+)
            sudden_death_log = ""
            if (self.turn_count + 1) >= 50:
                damage = damage * 2
                sudden_death_log = " ⚠️*(Muerte Súbita)*"

            crit_text = " **¡CRÍTICO!**" if crit else ""
            
            # Aplicar asesino crit_mult_bonus si crítico y atacante es Asesino
            if crit:
                extra_mult = attacker.subclass_extras.get("crit_mult_bonus", 0.0)
                if extra_mult > 0:
                    damage = int(damage * ((1.5 + extra_mult) / 1.5))
                    crit_text = f" **¡CRÍTICO BRUTAL!** ({(1.5 + extra_mult):.2f}x)"

            defend_text = " *(bloqueado parcialmente)*" if is_defending_for_damage else ""
            log_line = f"⚔️ {attacker.user.display_name} ataca → **{damage}** daño{crit_text}{defend_text}{shield_log}{sudden_death_log}"
            
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
                    if self.p1_poison_turns == 0:
                        self.p1_poison_damage = 10
                    else:
                        self.p1_poison_damage = min(30, self.p1_poison_damage + 10)
                    self.p1_poison_turns = turns
                else:
                    if self.p2_poison_turns == 0:
                        self.p2_poison_damage = 10
                    else:
                        self.p2_poison_damage = min(30, self.p2_poison_damage + 10)
                    self.p2_poison_turns = turns
                
                raw_dmg = int(atk_val * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], f" y envenena a {defender.user.display_name}!")
                
            elif special_id == "quemadura":
                turns = cfg["turns"] + 1
                if defender == self.p1:
                    self.p1_burn_turns = turns
                else:
                    self.p2_burn_turns = turns
                
                raw_dmg = int(attacker.mag * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], f" y quema a {defender.user.display_name}!")

            # ── HABILIDADES DE SUBCLASE ──
            elif special_id == "golpe_escudo":
                raw_dmg = int(atk_val * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                if defender.frozen_turns > 0:
                    defender.frozen_turns += 1
                    detail = f" y refuerza la congelación activa!"
                else:
                    defender.stun_turns = cfg.get("stun_turns", 1) + 1
                    detail = f" y lo **ATURDE** por 1 turno"
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], detail)

            elif special_id == "golpe_desesperado":
                raw_dmg = int(atk_val * cfg["base_damage_mult"])
                hp_ratio = attacker.hp / attacker.max_hp
                hp_mult = 1.0 / max(0.01, hp_ratio)
                raw_dmg = int(raw_dmg * hp_mult)
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], f" *(multiplicador por HP baja: {hp_mult:.2f}x)*")

            elif special_id == "estocada_precisa":
                raw_dmg = int(atk_val * cfg["damage_mult"])
                raw_dmg = int(raw_dmg * 1.5) # Crítico garantizado
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], " **¡CRÍTICO GARANTIZADO!** (ignora evasión)")

            elif special_id == "castigo_divino":
                raw_dmg = int(atk_val * cfg["base_damage_mult"]) + int(attacker.total_damage_taken * cfg["scaling_factor"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], f" *(daño por golpes acumulados: +{int(attacker.total_damage_taken * cfg['scaling_factor'])} )*")

            elif special_id == "golpe_sombras":
                raw_dmg = int(atk_val * cfg["damage_mult"])
                is_poisoned = (self.p1_poison_turns > 0 if defender == self.p1 else self.p2_poison_turns > 0)
                detail = ""
                if is_poisoned:
                    raw_dmg = int(raw_dmg * 2.0)
                    detail = " **¡DAÑO DUPLICADO por Veneno!**"
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], detail)

            elif special_id == "trampa_aconito":
                raw_dmg = int(atk_val * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                defender.weakness_turns = 4
                defender.weakness_pct = 0.20
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], " y aplica **Debilidad** (-20% ATK por 3 turnos)")

            elif special_id == "llamarada":
                raw_dmg = int(attacker.mag * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                if defender == self.p1:
                    self.p1_burn_turns = 5
                else:
                    self.p2_burn_turns = 5
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], " y aplica **Quemadura** por 4 turnos")

            elif special_id == "onda_escarcha":
                raw_dmg = int(attacker.mag * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                if defender.stun_turns > 0:
                    defender.stun_turns += 1
                    detail = " y refuerza el aturdimiento activo!"
                else:
                    defender.frozen_turns = 2
                    detail = " y **CONGELA** al rival por 1 turno"
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], detail)

            elif special_id == "sobrecarga_arcana":
                raw_dmg = int(attacker.mag * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                
                self_dmg = int(attacker.hp * 0.10)
                attacker.hp = max(1, attacker.hp - self_dmg)
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], f" *(sufre **{self_dmg}** HP autodaño por sobrecarga)*")

            elif special_id == "pacto_sangre":
                drain_pct = cfg["drain_pct"]
                extra_drain = attacker.subclass_extras.get("extra_drain_pct", 0.0)
                drain_pct += extra_drain
                
                steal_amt = max(1, int(defender.hp * drain_pct))
                defender.hp = max(0, defender.hp - steal_amt)
                attacker.hp = min(attacker.max_hp, attacker.hp + steal_amt)
                defender.anti_heal_turns = 3
                
                custom_log = f"{cfg['emoji']} **{cfg['name']}**: {attacker.user.display_name} drena **{steal_amt}** HP de {defender.user.display_name} y aplica **Anti-curación** por 2 turnos!"
                return finalize_damage_and_log(0, cfg["name"], cfg["emoji"], custom_log=custom_log)

            elif special_id == "ejecucion":
                raw_dmg = int(atk_val * cfg["damage_mult"])
                is_low = (defender.hp / defender.max_hp) < cfg["execute_threshold_pct"]
                detail = ""
                if is_low:
                    raw_dmg = int(raw_dmg * cfg["execute_bonus_mult"])
                    detail = " **¡EJECUCIÓN EXITOSA! (daño duplicado)**"
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], detail)

            elif special_id == "carga_sagrada":
                raw_dmg = int(atk_val * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"])

            elif special_id == "ejecucion_sombria":
                crit_mult = 1.5 + attacker.subclass_extras.get("crit_mult_bonus", 0.0)
                raw_dmg = int(atk_val * cfg["damage_mult"])
                
                extra_crit = 0.10 if any(p['id'] == 'crit_boost' for p in attacker.passives) else 0.0
                extra_crit += attacker.subclass_extras.get("crit_chance_bonus", 0.0)
                crit_chance = 0.10 + extra_crit
                crit = random.random() < crit_chance
                
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                
                detail = ""
                if crit:
                    damage = int(damage * crit_mult)
                    detail = f" **¡CRÍTICO BRUTAL!** ({crit_mult:.2f}x)"
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], detail)

            elif special_id == "danza_cuchillas":
                total_dmg = 0
                for _ in range(3):
                    raw_dmg = int(atk_val * 0.7)
                    def_mitig = int(defender_def_val * 0.20)
                    if is_defending_for_damage:
                        def_mitig = int(defender_def_val * 0.20 * 2.5)
                        raw_dmg = int(raw_dmg * 0.4)
                    total_dmg += max(1, raw_dmg - def_mitig)
                attacker.evasion_buff_turns = 3
                attacker.evasion_buff_pct = 0.30
                return finalize_damage_and_log(total_dmg, cfg["name"], cfg["emoji"], " y aumenta su Evasión por 2 turnos")

            elif special_id == "enjambre_trampas":
                raw_dmg = int(atk_val * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                
                defender.weakness_turns = 4
                defender.weakness_pct = 0.20
                defender.fragility_turns = 4
                defender.fragility_pct = 0.20
                if defender == self.p1:
                    self.p1_poison_turns = 4
                else:
                    self.p2_poison_turns = 4
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], " y aplica **Debilidad, Fragilidad y Veneno** al rival")

            elif special_id == "cataclismo_fuego":
                raw_dmg = int(attacker.mag * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                if defender == self.p1:
                    self.p1_burn_turns = 6
                else:
                    self.p2_burn_turns = 6
                defender.enhanced_burn_turns = 6
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], " y desata una **Quemadura reforzada** (8% HP max/t) por 5 turnos")

            elif special_id == "tormenta_elemental":
                raw_dmg = int(attacker.mag * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                if defender == self.p1:
                    self.p1_burn_turns = 3
                else:
                    self.p2_burn_turns = 3
                if defender.stun_turns > 0:
                    defender.stun_turns += 1
                    detail = " y refuerza el aturdimiento activo!"
                else:
                    defender.frozen_turns = 2
                    detail = " y aplica **Quemadura y Congelación**"
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], detail)

            elif special_id == "singularidad":
                raw_dmg = int(attacker.mag * cfg["damage_mult"])
                def_mitig = int(defender_def_val * cfg["def_mitigation_factor"])
                if is_defending_for_damage:
                    def_mitig = int(defender_def_val * cfg["def_mitigation_factor"] * 2.5)
                    raw_dmg = int(raw_dmg * 0.4)
                damage = max(1, raw_dmg - def_mitig)
                
                self_dmg = int(attacker.hp * 0.15)
                attacker.hp = max(1, attacker.hp - self_dmg)
                attacker.vulnerability_turns = 2
                attacker.vulnerability_pct = 0.30
                return finalize_damage_and_log(damage, cfg["name"], cfg["emoji"], f" y aplica **Vulnerabilidad** a sí mismo (recibe +30% daño y sufre **{self_dmg}** HP autodaño)")

            elif special_id == "consumir_alma":
                is_low = (defender.hp / defender.max_hp) < cfg["execute_threshold_pct"]
                drain_pct = cfg["execute_drain_pct"] if is_low else cfg["base_drain_pct"]
                extra_drain = attacker.subclass_extras.get("extra_drain_pct", 0.0)
                drain_pct += extra_drain
                
                steal_amt = max(1, int(defender.hp * drain_pct))
                defender.hp = max(0, defender.hp - steal_amt)
                attacker.hp = min(attacker.max_hp, attacker.hp + steal_amt)
                
                detail = " **¡EJECUCIÓN COMPLETA! (drenaje de 35%+)**" if is_low else ""
                custom_log = f"{cfg['emoji']} **{cfg['name']}**: {attacker.user.display_name} consume el alma de {defender.user.display_name} drenando **{steal_amt}** HP{detail}."
                return finalize_damage_and_log(0, cfg["name"], cfg["emoji"], custom_log=custom_log)

        return 0, ""

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
# VISTA: SELECCIÓN DE CLASES Y SUBCLASES
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


class SubclassSelectionView(discord.ui.View):
    """Vista para que un jugador seleccione su subclase de combate."""
    def __init__(self, user: discord.Member, class_name: str, current_subclass: str | None):
        super().__init__(timeout=90)
        self.user = user
        self.class_name = class_name
        self.selected_subclass = None

        subclasses = get_available_subclasses(class_name)
        options = []
        for sub_name in subclasses:
            cfg = SUBCLASSES[sub_name]
            desc_short = cfg['desc'][:100]
            options.append(
                discord.SelectOption(
                    label=f"{cfg['emoji']} {sub_name}",
                    value=sub_name,
                    description=desc_short
                )
            )

        placeholder = f"Subclase actual: {current_subclass or 'Ninguna'}"
        self.select = discord.ui.Select(placeholder=placeholder, options=options, min_values=1, max_values=1)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este selector.", ephemeral=True)
            return

        self.selected_subclass = self.select.values[0]
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

        p1 = Combatant(challenger, c_stats['level'], c_equip, c_stats.get('combat_class'), c_stats.get('combat_subclass'))
        p2 = Combatant(rival, r_stats['level'], r_equip, r_stats.get('combat_class'), r_stats.get('combat_subclass'))

        duel_view = DuelView(p1, p2, apuesta, self)
        embed = duel_view._build_embed()

        duel_msg = await interaction.followup.send(embed=embed, view=duel_view)
        duel_view.interaction_msg = duel_msg

    # ──────────────────── /clase ────────────────────

    @app_commands.command(name="clase", description="Elige o cambia tu clase y subclase de combate")
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
        current_subclass = c_stats.get('combat_subclass')
        player_level = c_stats['level']
        
        # ── Paso 1: Elegir clase ──
        embed = discord.Embed(
            title="🎭 Elige tu Clase de Combate",
            description="Al elegir una clase, tu Habilidad Especial en los duelos cambiará y solo podrás equipar armaduras de ciertos materiales y ciertas armas.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⚔️ Guerrero",
            value="**Especial Nv.5:** `Frenesí de Batalla` (+35% ATK, +15% daño recibido por 2 turnos).\n"
                  "**Subclases Nv.10:** Centinela 🛡️ · Berserker 🔥 · Duelista 🎯\n"
                  "**Armadura:** Hierro (Placas) · **Armas:** Arma, Escudo",
            inline=False
        )
        embed.add_field(
            name="🛡️ Paladín",
            value="**Especial Nv.5:** `Postura de Represalia` (mitiga 50% y refleja 100% esa ronda).\n"
                  "**Subclases Nv.10:** Guardián Sagrado ✨ · Vengador ⚔️ · Cruzado 🚩\n"
                  "**Armadura:** Hierro (Placas) · **Armas:** Arma, Escudo",
            inline=False
        )
        embed.add_field(
            name="🥷 Pícaro",
            value="**Especial Nv.5:** `Daga Envenenada` (daño físico + veneno 3 turnos).\n"
                  "**Subclases Nv.10:** Asesino 🗡️ · Sombra 👤 · Trampero 🕸️\n"
                  "**Armadura:** Cuero · **Armas:** Arma",
            inline=False
        )
        embed.add_field(
            name="🔥 Mago",
            value="**Especial Nv.5:** `Tormenta de Fuego` (daño mágico + quemadura 3 turnos).\n"
                  "**Subclases Nv.10:** Piromante 🔥 · Elementalista ❄️ · Arcanista 💥\n"
                  "**Armadura:** Tela · **Armas:** Bastón Mágico",
            inline=False
        )
        embed.add_field(
            name="⚕️ Clérigo",
            value="**Especial Nv.5:** `Drenaje Sagrado` (roba 15% HP actual, limpia debuffs).\n"
                  "**Subclases Nv.10:** Sanador 💚 · Oscuro 🖤 · Guardián de la Fe 🛡️\n"
                  "**Armadura:** Tela · **Armas:** Bastón Mágico",
            inline=False
        )
        
        footer_parts = []
        if current_class:
            footer_parts.append(f"Clase actual: {current_class}")
        if current_subclass:
            footer_parts.append(f"Subclase: {current_subclass}")
        if footer_parts:
            embed.set_footer(text=" · ".join(footer_parts))

        view = ClassSelectionView(interaction.user, current_class)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        await view.wait()
        
        if not view.selected_class:
            return
            
        selected_class = view.selected_class

        # ── Paso 2: Elegir subclase (si tiene nivel 10+) ──
        if player_level >= SUBCLASS_UNLOCK_LEVEL:
            # Si cambió de clase, resetear subclase
            if selected_class != current_class:
                current_subclass = None

            # Mostrar info de las 3 subclases
            sub_infos = get_all_subclass_info_for_display(selected_class)
            sub_embed = discord.Embed(
                title=f"🎭 Elige tu Subclase de {selected_class}",
                description=f"Clase seleccionada: **{selected_class}**\nElige tu especialización:",
                color=discord.Color.purple()
            )
            for info in sub_infos:
                skill_text = f"**Nv.10 — {info['skill_10_name']}:** {info['skill_10_desc']}\n"
                if player_level >= ULTIMATE_UNLOCK_LEVEL:
                    skill_text += f"**Nv.15 — {info['skill_15_name']}:** {info['skill_15_desc']}"
                else:
                    skill_text += f"*Nv.15 — {info['skill_15_name']}:* 🔒 Se desbloquea a Nv.15"
                sub_embed.add_field(
                    name=f"{info['emoji']} {info['name']} ({info['role']})",
                    value=f"*{info['desc']}*\n{skill_text}",
                    inline=False
                )

            sub_view = SubclassSelectionView(interaction.user, selected_class, current_subclass)
            await interaction.followup.send(embed=sub_embed, view=sub_view, ephemeral=True)

            await sub_view.wait()

            selected_subclass = sub_view.selected_subclass
            success = await asyncio.to_thread(
                update_user_class_and_subclass, user_id, selected_class, selected_subclass
            )
            if success:
                msg = f"✅ ¡Clase: **{selected_class}**"
                if selected_subclass:
                    msg += f" · Subclase: **{selected_subclass}**"
                msg += "! Tu configuración de combate ha sido actualizada."
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.followup.send("❌ Hubo un error al guardar en la base de datos.", ephemeral=True)
        else:
            # Solo clase (aún no tiene nivel para subclase)
            success = await asyncio.to_thread(
                update_user_class_and_subclass, user_id, selected_class, None
            )
            if success:
                await interaction.followup.send(
                    f"✅ ¡Clase: **{selected_class}**! A nivel **{SUBCLASS_UNLOCK_LEVEL}** podrás elegir una subclase.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("❌ Hubo un error al guardar en la base de datos.", ephemeral=True)

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
        subclass_text = f" · Subclase: **{stats['combat_subclass']}**" if stats.get('combat_subclass') else ""
        embed = discord.Embed(
            title=f"{rank_emoji} Perfil de Combate — {target.display_name}",
            description=f"**{rank}** · Nivel **{stats['level']}**{class_text}{subclass_text}",
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
                f"❤️ HP: {base['hp']} (+{effective.get('hp', 0):.1f} efec. [{bonus.get('hp', 0)} eq., {pct_per_stat.get('hp', 100.0):.0f}% ef.])\n"
                f"⚔️ ATK: {base['atk']} (+{effective.get('atk', 0):.1f} efec. [{bonus.get('atk', 0)} eq., {pct_per_stat.get('atk', 100.0):.0f}% ef.])\n"
                f"🔮 MAG: {base['mag']} (+{effective.get('mag', 0):.1f} efec. [{bonus.get('mag', 0)} eq., {pct_per_stat.get('mag', 100.0):.0f}% ef.])\n"
                f"🛡️ DEF: {base['def']} (+{effective.get('def', 0):.1f} efec. [{bonus.get('def', 0)} eq., {pct_per_stat.get('def', 100.0):.0f}% ef.])"
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
            name="🎒 Eficiencia de Equipo",
            value=f"Eficiencia promedio: `{gear_bar}` {pct_used:.0f}% (100% = sin pérdidas por softcap)",
            inline=False
        )

        # Cooldown
        cooldown = get_duel_cooldown_minutes(stats['level'])
        embed.set_footer(text=f"Cooldown entre duelos: {cooldown:.0f} min")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ──────────────────── /estados ────────────────────

    @app_commands.command(name="estados", description="Muestra qué hace cada buff, debuff y estado de combate")
    async def estados_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Glosario de Estados de Combate",
            description="Todos los buffs, debuffs y efectos que puedes encontrar en duelos y raids.",
            color=discord.Color.dark_gold()
        )

        embed.add_field(
            name="🔥 Daño sobre tiempo (DOT)",
            value=(
                "☠️ **Veneno** — 10 HP/turno, hasta 3 capas (máx. 30/turno), 3 turnos.\n"
                "🔥 **Quemadura** — 5-8% HP máx/turno, no stackea, 3-5 turnos.\n"
                "🩸 **Sangrado** — 6% del último golpe físico recibido/turno, 3 turnos."
            ),
            inline=False
        )
        embed.add_field(
            name="🧊 Control",
            value=(
                "😵 **Aturdimiento** — pierde el turno. 1 turno.\n"
                "❄️ **Congelación** — +1 turno al cooldown de tu próxima especial. 1 turno.\n"
                "🔇 **Silencio** — no puedes usar especiales. 2 turnos.\n"
                "🌀 **Ceguera** — 65% de fallar tus ataques. 3 turnos."
            ),
            inline=False
        )
        embed.add_field(
            name="📉 Debuffs de stat",
            value=(
                "🛡️💥 **Fragilidad** — -20% DEF. 3 turnos.\n"
                "💢 **Debilidad** — -20% ATK. 3 turnos.\n"
                "🎯 **Vulnerabilidad** — +30% daño recibido (tope combinado +75%). 1-3 turnos.\n"
                "🚫 **Anti-cura** — bloquea toda curación. 2 turnos."
            ),
            inline=False
        )
        embed.add_field(
            name="✨ Buffs",
            value=(
                "⚔️ **Frenesí** — +35% ATK / +15% daño recibido. 2 turnos.\n"
                "🛡️ **Escudo** — absorbe daño (valor según la fuente).\n"
                "💚 **Regeneración (HoT)** — cura % HP máx/turno (valor según la fuente).\n"
                "🔥 **Furia Creciente** — +10% daño con HP < 30% (pasivo, no expira)."
            ),
            inline=False
        )

        embed.set_footer(text="Usa /perfil_combate para ver tu clase, subclase y nivel actual.")
        await interaction.response.send_message(embed=embed)

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
            f"⚔️ ATK: +{effective.get('atk', 0):.1f} · "
            f"🔮 MAG: +{effective.get('mag', 0):.1f} · "
            f"🛡️ DEF: +{effective.get('def', 0):.1f} · "
            f"❤️ HP: +{effective.get('hp', 0):.1f}"
        )
        gear_bar = format_progress_bar(int(pct_used), 100, size=15)
        embed.add_field(
            name="📊 Bonus Total de Equipo",
            value=f"{bonus_text}\nEficiencia promedio: `{gear_bar}` {pct_used:.0f}% (100% = sin pérdidas)",
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
