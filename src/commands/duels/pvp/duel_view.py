import discord
import asyncio
import random
import logging
from datetime import datetime
from src.db import (
    deduct_balance, add_balance, registrar_transaccion,
    update_combat_stats_after_duel, log_duel, get_user_equipment,
    get_user_consumables, get_consumable_catalog, use_consumable,
    add_combat_currency
)
from src.utils.combat_progression import (
    calc_duel_xp, calc_defend_heal, format_progress_bar, format_hp_bar,
    get_combat_rank, get_combat_rank_emoji, generate_loot, calc_attack_damage,
    can_proc, mark_proc, format_username_with_prestige,
    CHALLENGE_TIMEOUT_SECONDS, TURN_TIMEOUT_SECONDS,
    DROP_RATE_WINNER, DROP_RATE_LOSER, format_currency
)

from src.utils.combat_config import SKILLS_CONFIG
from src.commands.duels.pvp.pvp_combatant import Combatant

logger = logging.getLogger(__name__)

def get_combatant_available_skills(combatant: Combatant):
    available = []
    for skill_id, skill in SKILLS_CONFIG.items():
        if skill.get("class") is None:
            if combatant.combat_class is None:
                available.append((skill_id, skill))
        else:
            if combatant.combat_class == skill["class"]:
                req_subclass = skill.get("subclass")
                if req_subclass:
                    if combatant.combat_subclass == req_subclass and combatant.level >= skill["min_level"]:
                        available.append((skill_id, skill))
                else:
                    if combatant.level >= skill["min_level"]:
                        available.append((skill_id, skill))
    return available

class ChallengeView(discord.ui.View):
    """Botones para que el rival acepte o rechace el duelo."""

    def __init__(self, challenger: discord.Member, rival: discord.Member, bet: int, cog: 'DuelsCog'):
        super().__init__(timeout=CHALLENGE_TIMEOUT_SECONDS)
        self.challenger = challenger
        self.rival = rival
        self.bet = bet
        self.cog = cog
        self.accepted = None

    @discord.ui.button(label="✅ Aceptar", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.rival.id:
            await interaction.response.send_message("❌ Solo el retado puede responder.", ephemeral=True)
            return

        await interaction.response.defer()

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
            description=f"{self.rival.mention} acepta el reto de {self.challenger.mention}.\nPreparando la arena...",
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
            await asyncio.to_thread(add_balance, self.challenger.id, self.bet)
            for item in self.children:
                item.disabled = True
            self._cleanup()

    def _cleanup(self):
        self.cog.active_duels.discard(self.challenger.id)
        self.cog.active_duels.discard(self.rival.id)

class PersonalDuelSkillSelectView(discord.ui.View):
    """Menú efímero de un solo select para que un jugador elija su habilidad especial en un duelo."""

    def __init__(self, duel_view, player, options: list[discord.SelectOption]):
        super().__init__(timeout=60)
        self.duel_view = duel_view
        self.player = player

        select = discord.ui.Select(
            placeholder="✨ Seleccionar Habilidad Especial...",
            min_values=1, max_values=1, options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True

        if self.duel_view.game_over:
            await interaction.response.edit_message(content="❌ El duelo ya terminó.", view=self)
            return

        current_action = self.duel_view.p1_action if self.player == self.duel_view.p1 else self.duel_view.p2_action
        if current_action is not None:
            await interaction.response.edit_message(content="❌ Ya has elegido tu acción para esta ronda.", view=self)
            return

        selected_value = interaction.data["values"][0]
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

        if self.player == self.duel_view.p1:
            self.duel_view.p1_action = 'special'
            self.duel_view.p1_special_id = selected_value
            self.duel_view.p1.consecutive_timeouts = 0
        else:
            self.duel_view.p2_action = 'special'
            self.duel_view.p2_special_id = selected_value
            self.duel_view.p2.consecutive_timeouts = 0

        await interaction.response.edit_message(content=f"✅ Habilidad especial registrada: **{req['name']}**", view=self)
        await self.duel_view._check_and_resolve(interaction, is_ephemeral=True)

class PersonalDuelConsumableSelectView(discord.ui.View):
    """Menú efímero de un solo select para que un jugador elija su consumible en un duelo."""

    def __init__(self, duel_view, player, options: list[discord.SelectOption]):
        super().__init__(timeout=60)
        self.duel_view = duel_view
        self.player = player

        select = discord.ui.Select(
            placeholder="🧪 Seleccionar Consumible...",
            min_values=1, max_values=1, options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True

        if self.duel_view.game_over:
            await interaction.response.edit_message(content="❌ El duelo ya terminó.", view=self)
            return

        current_action = self.duel_view.p1_action if self.player == self.duel_view.p1 else self.duel_view.p2_action
        if current_action is not None:
            await interaction.response.edit_message(content="❌ Ya has elegido tu acción para esta ronda.", view=self)
            return

        selected_value = interaction.data["values"][0]
        success = await asyncio.to_thread(use_consumable, self.player.user.id, selected_value)
        if not success:
            await interaction.response.edit_message(content="❌ No tienes suficiente cantidad de este consumible.", view=self)
            return

        if self.player == self.duel_view.p1:
            self.duel_view.p1_action = f"consumable:{selected_value}"
            self.duel_view.p1.consecutive_timeouts = 0
        else:
            self.duel_view.p2_action = f"consumable:{selected_value}"
            self.duel_view.p2.consecutive_timeouts = 0

        catalog = await asyncio.to_thread(get_consumable_catalog)
        c_info = next((item for item in catalog if item['consumable_key'] == selected_value), None)
        c_name = c_info['name'] if c_info else selected_value

        await interaction.response.edit_message(content=f"✅ Consumible registrado: **{c_name}**", view=self)
        await self.duel_view._check_and_resolve(interaction, is_ephemeral=True)

class DuelView(discord.ui.View):
    """Vista principal del combate PvP por turnos simultáneos."""

    def __init__(self, p1: Combatant, p2: Combatant, bet: int, cog: 'DuelsCog'):
        super().__init__(timeout=TURN_TIMEOUT_SECONDS)
        self.p1 = p1
        self.p2 = p2
        self.bet = bet
        self.cog = cog

        self.p1_action = None
        self.p2_action = None
        self.p1_special_id = None
        self.p2_special_id = None

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
        self.action_log = []
        self.interaction_msg = None

        for p in (self.p1, self.p2):
            if hasattr(p, "abyssus_log"):
                self.action_log.append(p.abyssus_log)

    @property
    def p1_blinded_turns(self) -> int:
        return self.p1.blinded_turns

    @p1_blinded_turns.setter
    def p1_blinded_turns(self, value: int):
        self.p1.blinded_turns = value

    @property
    def p2_blinded_turns(self) -> int:
        return self.p2.blinded_turns

    @p2_blinded_turns.setter
    def p2_blinded_turns(self, value: int):
        self.p2.blinded_turns = value

    def _build_embed(self):
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

        for p in (self.p1, self.p2):
            rank_emoji = get_combat_rank_emoji(p.level)
            hp_bar = format_hp_bar(p.hp, p.max_hp)
            
            blind_turns = self.p1_blinded_turns if p == self.p1 else self.p2_blinded_turns
            frenzy_turns = self.p1_frenzy_turns if p == self.p1 else self.p2_frenzy_turns
            poison_turns = self.p1_poison_turns if p == self.p1 else self.p2_poison_turns
            burn_turns = self.p1_burn_turns if p == self.p1 else self.p2_burn_turns
            
            status_icons = ""
            if blind_turns > 0: status_icons += f" 👁️({blind_turns}t)"
            if frenzy_turns > 0: status_icons += f" ⚔️(Frenesí {frenzy_turns}t)"
            if poison_turns > 0: status_icons += f" 🧪({poison_turns}t)"
            if burn_turns > 0: status_icons += f" 🔥({burn_turns}t)"
            if p.stun_turns > 0: status_icons += f" 💫(Aturdido {p.stun_turns}t)"
            if p.damage_reduction_turns > 0: status_icons += f" 🏰(-{int(p.damage_reduction_pct*100)}% daño {p.damage_reduction_turns}t)"
            if p.atk_buff_turns > 0: status_icons += f" 💪(+{int(p.atk_buff_pct*100)}% ATK {p.atk_buff_turns}t)"
            if p.juicio_final_turns > 0: status_icons += f" ⚖️(Reflejo {p.juicio_final_turns}t)"
            if p.evasion_buff_turns > 0: status_icons += f" 💨(Evasión+ {p.evasion_buff_turns}t)"
            if p.guaranteed_dodge_next: status_icons += " 👻(Esquiva)"
            if p.anti_heal_turns > 0: status_icons += f" 🚫(Anti-cura {p.anti_heal_turns}t)"
            if p.weakness_turns > 0: status_icons += f" ❄️(Debil {p.weakness_turns}t)"
            if p.fragility_turns > 0: status_icons += f" 💔(Frágil {p.fragility_turns}t)"
            if p.vulnerability_turns > 0: status_icons += f" ⚠️(Vulner. {p.vulnerability_turns}t)"
            if p.shield > 0: status_icons += f" 🛡️({p.shield})"
            if p.special_cooldown > 0: status_icons += f" ⏳({p.special_cooldown}t)"
            if p.skill10_cooldown > 0: status_icons += f" ⏳S10({p.skill10_cooldown}t)"
            if p.skill15_cooldown > 0: status_icons += f" ⏳ULT({p.skill15_cooldown}t)"
            
            passive_icons = "".join([f" {pass_item.get('emoji', '✨')}" for pass_item in p.passives])
            class_tag = f" [{p.combat_subclass or p.combat_class}]" if (p.combat_subclass or p.combat_class) else ""

            embed.add_field(
                name=f"{rank_emoji} {p.user.display_name}{class_tag} (Nv.{p.level}){status_icons}{passive_icons}",
                value=f"{hp_bar}\n⚔️ {p.atk} ATK · 🔮 {p.mag} MAG · 🛡️ {p.def_stat} DEF",
                inline=False
            )

        if self.action_log:
            embed.add_field(name="📜 Registro", value="\n".join(self.action_log[-6:]), inline=False)

        embed.add_field(name="💰 Apuesta", value=f"{self.bet:,} monedas", inline=True)
        embed.set_footer(text=f"Tiempo por ronda: {TURN_TIMEOUT_SECONDS}s")
        return embed

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
                value=skill_id, emoji=skill['emoji'], description=skill['desc'][:100]
            ) for skill_id, skill in player_skills
        ]

        view = PersonalDuelSkillSelectView(duel_view=self, player=cp, options=options)
        await interaction.response.send_message("Elige tu habilidad especial:", view=view, ephemeral=True)

    @discord.ui.button(label="🧪 Usar Consumible", style=discord.ButtonStyle.success, row=1)
    async def consumable_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        current_action = self.p1_action if cp == self.p1 else self.p2_action
        if current_action is not None:
            await interaction.response.send_message("❌ Ya has elegido tu acción para esta ronda.", ephemeral=True)
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
            options.append(discord.SelectOption(label=f"{name} (Tienes: {qty})", value=key, description=desc[:100]))

        view = PersonalDuelConsumableSelectView(duel_view=self, player=cp, options=options)
        await interaction.response.send_message("Elige tu consumible:", view=view, ephemeral=True)

    def _apply_damage_to_combatant(self, target: Combatant, raw_dmg: int, logs: list[str]) -> int:
        if raw_dmg <= 0:
            return 0
        absorbed = 0
        if target.shield > 0:
            absorbed = min(target.shield, raw_dmg)
            raw_dmg -= absorbed
            target.shield -= absorbed
            logs.append(f"🛡️ **Escudo:** Se absorbieron **{absorbed}** de daño. Queda {target.shield} de escudo en {target.user.display_name}.")
        target.hp = max(0, target.hp - raw_dmg)
        return raw_dmg

    async def _check_and_resolve(self, interaction: discord.Interaction, is_ephemeral: bool = False):
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

    async def _resolve_round(self, interaction: discord.Interaction = None):
        self.p1_retribution_active = False
        self.p2_retribution_active = False

        p1_has_parry = any(p_item['id'] == 'parry' for p_item in self.p1.passives)
        p2_has_parry = any(p_item['id'] == 'parry' for p_item in self.p2.passives)

        self.p1.pre_hit_hp = self.p1.hp
        self.p2.pre_hit_hp = self.p2.hp

        p1_act = self.p1_action
        p2_act = self.p2_action

        self.p1.is_defending = (p1_act == 'defend')
        self.p2.is_defending = (p2_act == 'defend')

        logs = [f"🏁 **Ronda {self.turn_count + 1}:**"]

        for caster, target, act in ((self.p1, self.p2, p1_act), (self.p2, self.p1, p2_act)):
            if act and act.startswith("consumable:"):
                ckey = act.split(":")[1]
                if ckey == "pocion_curacion":
                    if caster.anti_heal_turns == 0:
                        heal_amt = int(caster.max_hp * 0.25)
                        heal_amt = int(heal_amt * (1.0 + caster.healing_bonus_pct))
                        caster.hp = min(caster.max_hp, caster.hp + heal_amt)
                        logs.append(f"🧪 **Poción de Curación:** {caster.user.display_name} usa una poción y se cura **{heal_amt}** HP.")
                    else:
                        logs.append(f"🧪 **Poción de Curación:** {caster.user.display_name} usa una poción, pero tiene anti-curación.")
                elif ckey == "pergamino_purificacion":
                    caster.stun_turns = 0
                    caster.frozen_turns = 0
                    caster.silence_turns = 0
                    caster.weakness_turns = 0
                    caster.fragility_turns = 0
                    caster.vulnerability_turns = 0
                    caster.bleed_turns = 0
                    caster.anti_heal_turns = 0
                    logs.append(f"📜 **Pergamino de Purificación:** {caster.user.display_name} limpia todos sus estados alterados.")
                elif ckey == "bomba_humo":
                    caster.guaranteed_dodge_next = True
                    logs.append(f"💨 **Bomba de Humo:** {caster.user.display_name} se oculta. ¡Garantiza esquivar el próximo golpe!")
                elif ckey == "frasco_silencio":
                    target.silence_turns = 3
                    logs.append(f"🤫 **Frasco de Silencio:** {caster.user.display_name} silencia a {target.user.display_name} por 2 turnos.")

        is_sudden_death = (self.turn_count + 1) >= 50
        if is_sudden_death:
            fatigue_level = (self.turn_count + 1) - 50 + 1
            fatigue_pct = 0.05 * fatigue_level
            for defender in (self.p1, self.p2):
                if defender.hp > 0:
                    fatigue_dmg = min(defender.hp, max(1, int(defender.max_hp * fatigue_pct)))
                    defender.hp = max(0, defender.hp - fatigue_dmg)
                    logs.append(f"💀 **Fatiga:** {defender.user.display_name} sufre **{fatigue_dmg}** HP de daño.")

        if self.p1.is_defending:
            heal1 = calc_defend_heal(self.p1.max_hp)
            self.p1.hp = min(self.p1.max_hp, self.p1.hp + heal1)
            logs.append(f"🛡️ {self.p1.user.display_name} se defiende y recupera **{heal1}** HP.")
        if self.p2.is_defending:
            heal2 = calc_defend_heal(self.p2.max_hp)
            self.p2.hp = min(self.p2.max_hp, self.p2.hp + heal2)
            logs.append(f"🛡️ {self.p2.user.display_name} se defiende y recupera **{heal2}** HP.")

        # Calculo de acciones
        p1_dmg = max(1, self.p1.atk - self.p2.def_stat) if p1_act == 'attack' else 0
        p2_dmg = max(1, self.p2.atk - self.p1.def_stat) if p2_act == 'attack' else 0

        if p1_dmg > 0:
            self.p2.hp = max(0, self.p2.hp - p1_dmg)
            logs.append(f"⚔️ {self.p1.user.display_name} inflige **{p1_dmg}** de daño a {self.p2.user.display_name}.")
        if p2_dmg > 0:
            self.p1.hp = max(0, self.p1.hp - p2_dmg)
            logs.append(f"⚔️ {self.p2.user.display_name} inflige **{p2_dmg}** de daño a {self.p1.user.display_name}.")

        self.p1_action = None
        self.p2_action = None
        self.turn_count += 1
        self.action_log.extend(logs)

        if len(self.action_log) > 6:
            self.action_log = self.action_log[-6:]

        if self.p1.hp <= 0 or self.p2.hp <= 0 or self.turn_count >= 50:
            self.game_over = True
            await self._finish_duel(interaction)
            return

        embed = self._build_embed()
        try:
            if interaction and getattr(interaction, "message", None):
                await interaction.message.edit(embed=embed, view=self)
            elif self.interaction_msg:
                await self.interaction_msg.edit(embed=embed, view=self)
        except Exception:
            pass

    async def _finish_duel(self, interaction: discord.Interaction):
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
            pass
        self.stop()

    async def _resolve_duel(self):
        if self.p1.hp <= 0 and self.p2.hp <= 0:
            winner, loser = (self.p1, self.p2) if self.p1.pre_hit_hp >= self.p2.pre_hit_hp else (self.p2, self.p1)
        elif self.p1.hp <= 0:
            winner, loser = self.p2, self.p1
        else:
            winner, loser = self.p1, self.p2

        await asyncio.to_thread(add_balance, winner.user.id, self.bet * 2)
        await asyncio.to_thread(registrar_transaccion, winner.user.id, self.bet, "Duelo PvP: victoria")
        await asyncio.to_thread(registrar_transaccion, loser.user.id, -self.bet, "Duelo PvP: derrota")

        winner_xp = calc_duel_xp(True, loser.level)
        loser_xp = calc_duel_xp(False, winner.level)

        w_result = await asyncio.to_thread(update_combat_stats_after_duel, winner.user.id, winner_xp, True, self.bet)
        l_result = await asyncio.to_thread(update_combat_stats_after_duel, loser.user.id, loser_xp, False, -self.bet)

        embed = discord.Embed(
            title="⚔️ Duelo PvP — Resultado Final",
            description=f"🏆 **{winner.user.display_name}** vence a **{loser.user.display_name}**!",
            color=discord.Color.gold()
        )
        embed.add_field(name="💰 Recompensa", value=f"{winner.user.display_name} gana **{self.bet:,}** monedas", inline=False)
        return embed
