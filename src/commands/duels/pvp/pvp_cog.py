import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from src.db import (
    ensure_user, get_balance, deduct_balance, add_balance,
    get_combat_stats, update_user_class_and_subclass,
    get_user_equipment, get_combat_wallet, add_combat_currency,
    get_gem_catalog, get_consumable_catalog, get_user_consumables,
    get_duel_leaderboard
)
from src.utils.combat_progression import (
    calc_base_stats, calc_equipment_bonus, get_effective_bonus,
    get_duel_cooldown_minutes, format_hp_bar, format_progress_bar,
    get_combat_rank, get_combat_rank_emoji, calc_combat_xp_needed,
    format_stat_type, SLOT_EMOJIS,
    EQUIPMENT_SLOTS, MIN_BET, MAX_LEVEL_DIFFERENCE, CHALLENGE_TIMEOUT_SECONDS,
    SUBCLASS_UNLOCK_LEVEL, ULTIMATE_UNLOCK_LEVEL, format_currency
)

from src.utils.prestige_config import format_username_with_prestige


from src.utils.subclass_config import get_all_subclass_info_for_display, get_available_subclasses, SUBCLASSES
from src.commands.duels.pvp.pvp_combatant import Combatant
from src.commands.duels.pvp.duel_view import ChallengeView, DuelView
from src.commands.duels.pvp.loot_views import GemShopView, ConsumableShopView, ClassSelectionView, SubclassSelectionView, format_item_stats_display

logger = logging.getLogger(__name__)

class DuelsCog(commands.Cog):
    """Sistema de Duelos PvP."""

    def __init__(self, bot):
        self.bot = bot
        self.active_duels: set[int] = set()

    @app_commands.command(name="duelo", description="Reta a otro usuario a un duelo PvP con apuesta de monedas")
    @app_commands.describe(
        rival="Usuario al que quieres retar",
        apuesta="Cantidad de monedas a apostar"
    )
    async def duelo_cmd(self, interaction: discord.Interaction, rival: discord.Member, apuesta: int):
        challenger = interaction.user
        challenger_id = challenger.id
        rival_id = rival.id

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

        await asyncio.to_thread(ensure_user, challenger_id, challenger.name)
        await asyncio.to_thread(ensure_user, rival_id, rival.name)

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

        c_stats = await asyncio.to_thread(get_combat_stats, challenger_id)
        r_stats = await asyncio.to_thread(get_combat_stats, rival_id)

        level_diff = abs(c_stats['level'] - r_stats['level'])
        if level_diff > MAX_LEVEL_DIFFERENCE:
            await interaction.response.send_message(
                f"❌ La diferencia de nivel es demasiado grande "
                f"(Nv.{c_stats['level']} vs Nv.{r_stats['level']}, máx {MAX_LEVEL_DIFFERENCE}).",
                ephemeral=True
            )
            return

        success, _ = await asyncio.to_thread(deduct_balance, challenger_id, apuesta)
        if not success:
            await interaction.response.send_message("❌ No se pudo cobrar la apuesta.", ephemeral=True)
            return

        self.active_duels.add(challenger_id)
        self.active_duels.add(rival_id)

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

        await challenge_view.wait()

        if not challenge_view.accepted:
            return

        await asyncio.sleep(1)

        c_equip = await asyncio.to_thread(get_user_equipment, challenger_id)
        r_equip = await asyncio.to_thread(get_user_equipment, rival_id)

        p1 = Combatant(challenger, c_stats['level'], c_equip, c_stats.get('combat_class'), c_stats.get('combat_subclass'))
        p2 = Combatant(rival, r_stats['level'], r_equip, r_stats.get('combat_class'), r_stats.get('combat_subclass'))

        duel_view = DuelView(p1, p2, apuesta, self)
        embed = duel_view._build_embed()

        duel_msg = await interaction.followup.send(embed=embed, view=duel_view)
        duel_view.interaction_msg = duel_msg

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

        if current_class:
            if current_subclass:
                await interaction.response.send_message(
                    f"❌ Ya has elegido tu clase (**{current_class}**) y subclase (**{current_subclass}**). Estas elecciones son permanentes.",
                    ephemeral=True
                )
                return

            if player_level < SUBCLASS_UNLOCK_LEVEL:
                await interaction.response.send_message(
                    f"❌ Ya has elegido la clase **{current_class}** y no puedes cambiarla. Podrás elegir una subclase a nivel {SUBCLASS_UNLOCK_LEVEL}.",
                    ephemeral=True
                )
                return

            selected_class = current_class
            sub_infos = get_all_subclass_info_for_display(selected_class)
            sub_embed = discord.Embed(
                title=f"🎭 Elige tu Subclase de {selected_class}",
                description=f"Clase actual: **{selected_class}** (no se puede cambiar).\nElige tu especialización:",
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
            await interaction.response.send_message(embed=sub_embed, view=sub_view, ephemeral=True)
            await sub_view.wait()

            selected_subclass = sub_view.selected_subclass
            if not selected_subclass:
                return

            success = await asyncio.to_thread(update_user_class_and_subclass, user_id, selected_class, selected_subclass)
            if success:
                await interaction.followup.send(f"✅ ¡Tu subclase ha sido actualizada a **{selected_subclass}**!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Hubo un error al guardar en la base de datos.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎭 Elige tu Clase de Combate",
            description="Al elegir una clase, tu Habilidad Especial en los duelos cambiará y solo podrás equipar armaduras de ciertos materiales y ciertas armas.",
            color=discord.Color.blue()
        )
        view = ClassSelectionView(interaction.user, current_class)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()
        
        if not view.selected_class:
            return
            
        selected_class = view.selected_class
        if player_level >= SUBCLASS_UNLOCK_LEVEL:
            sub_view = SubclassSelectionView(interaction.user, selected_class, current_subclass)
            await interaction.followup.send("Elige tu subclase:", view=sub_view, ephemeral=True)
            await sub_view.wait()
            selected_subclass = sub_view.selected_subclass
            await asyncio.to_thread(update_user_class_and_subclass, user_id, selected_class, selected_subclass)
            await interaction.followup.send(f"✅ ¡Configuración actualizada: **{selected_class}** / **{selected_subclass}**!", ephemeral=True)
        else:
            await asyncio.to_thread(update_user_class_and_subclass, user_id, selected_class, None)
            await interaction.followup.send(f"✅ ¡Clase elegida: **{selected_class}**!", ephemeral=True)

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

        bonus, passives, _ = calc_equipment_bonus(equipment)
        effective, pct_used, pct_per_stat = get_effective_bonus(bonus, stats['level'])

        class_text = f" · Clase: **{stats['combat_class']}**" if stats.get('combat_class') else ""
        subclass_text = f" · Subclase: **{stats['combat_subclass']}**" if stats.get('combat_subclass') else ""
        embed = discord.Embed(
            title=f"{rank_emoji} Perfil de Combate — {target.display_name}",
            description=f"**{rank}** · Nivel **{stats['level']}**{class_text}{subclass_text}",
            color=discord.Color.dark_gold()
        )

        xp_needed = calc_combat_xp_needed(stats['level'])
        if xp_needed > 0:
            bar = format_progress_bar(stats['xp'], xp_needed)
            embed.add_field(name="Experiencia", value=f"`{bar}` {stats['xp']:,}/{xp_needed:,} XP", inline=False)

        total = stats['wins'] + stats['losses']
        win_rate = (stats['wins'] / total * 100) if total > 0 else 0
        embed.add_field(
            name="⚔️ Combates",
            value=f"Victorias: **{stats['wins']}** | Derrotas: **{stats['losses']}**\nWinrate: **{win_rate:.1f}%**",
            inline=True
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="monedas_combate", description="Consulta tu saldo de monedas de combate (Bronce, Plata, Oro)")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def monedas_combate_cmd(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer(ephemeral=True)
        target = usuario or interaction.user
        await asyncio.to_thread(ensure_user, target.id, target.name)

        bronze_balance = await asyncio.to_thread(get_combat_wallet, target.id)
        stats = await asyncio.to_thread(get_combat_stats, target.id)
        rank_emoji = get_combat_rank_emoji(stats['level'])
        formatted_balance = format_currency(bronze_balance)

        embed = discord.Embed(
            title=f"{rank_emoji} Billetera de Combate — {target.display_name}",
            description=f"Saldo actual: **{formatted_balance}**",
            color=discord.Color.dark_gold()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="gemas", description="Tienda de gemas de combate y gestión de inserciones/remociones")
    async def gemas_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        catalog = await asyncio.to_thread(get_gem_catalog)
        equipment = await asyncio.to_thread(get_user_equipment, interaction.user.id)

        embed = discord.Embed(
            title="💎 Tienda de Gemas de Combate",
            description="Elige un slot de tu equipo y una gema para comprar e insertar.",
            color=discord.Color.blue()
        )
        view = GemShopView(interaction.user, catalog, equipment)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="consumibles", description="Tienda de consumibles de combate")
    async def consumibles_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        catalog = await asyncio.to_thread(get_consumable_catalog)
        embed = discord.Embed(
            title="🧪 Tienda de Consumibles de Combate",
            description="Elige un consumible para comprar.",
            color=discord.Color.green()
        )
        view = ConsumableShopView(interaction.user, catalog)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="estados", description="Muestra qué hace cada buff, debuff y estado de combate")
    async def estados_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Glosario de Estados de Combate",
            description="Todos los buffs, debuffs y efectos de combate.",
            color=discord.Color.dark_gold()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="duelo_inventario", description="Muestra tu equipo de combate actual")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def duelo_inventario_cmd(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer(ephemeral=True)
        target = usuario or interaction.user
        await asyncio.to_thread(ensure_user, target.id, target.name)
        equipment = await asyncio.to_thread(get_user_equipment, target.id)

        embed = discord.Embed(title=f"🎒 Equipo de Combate — {target.display_name}", color=discord.Color.dark_teal())
        for slot, piece in equipment.items():
            val = piece["item_name"] if piece else "— Vacío —"
            embed.add_field(name=slot, value=val, inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ranking_duelos", description="Muestra el ranking de duelos PvP")
    async def ranking_duelos_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = await asyncio.to_thread(get_duel_leaderboard, "wins", 10)
        embed = discord.Embed(title="🏆 Ranking de Duelos", color=discord.Color.gold())
        if not rows:
            embed.description = "Sin registros."
        else:
            lines = [f"`{i+1}.` User {r[0]} — {r[2]} Victorias (Nv. {r[1]})" for i, r in enumerate(rows)]
            embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(DuelsCog(bot))
    logger.info("Duels cog loaded successfully.")
