import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import random
import logging
import os
from datetime import datetime, time, timedelta
from typing import Optional
from src.services.lottery_service import LotteryService
from src.services.casino_service import CasinoService
from src.db import ensure_user, get_balance, get_active_tickets, get_user_prestige_level
from src.utils.cooldowns import ECONOMY_COOLDOWN

logger = logging.getLogger(__name__)

LOTTO_NOTIFICATION_CHANNEL_ID = int(os.getenv('LOTTO_NOTIFICATION_CHANNEL_ID', '1519533661806923866'))

async def send_loto_notification(
    bot: commands.Bot,
    embed: discord.Embed,
    content: Optional[str] = None,
) -> None:
    target_channel_id = LOTTO_NOTIFICATION_CHANNEL_ID
    target_channel = bot.get_channel(target_channel_id)
    if not target_channel:
        try:
            target_channel = await bot.fetch_channel(target_channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logger.error(
                f"Error al obtener canal de destino loto {target_channel_id}: {e}"
            )
            return
    try:
        await target_channel.send(content=content, embed=embed)
    except (discord.Forbidden, discord.HTTPException) as e:
        logger.error(
            f"Error enviando mensaje a canal de destino loto {target_channel_id}: {e}"
        )


class Loto(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_lottery_draw.start()

    def cog_unload(self):
        self.daily_lottery_draw.cancel()

    @tasks.loop(time=time(hour=0, minute=0, second=0))
    async def daily_lottery_draw(self):
        """Tarea que ejecuta automáticamente el sorteo a las 12:00 de la noche (00:00)."""
        logger.info("Ejecutando sorteo automático de lotería diaria...")
        try:
            results = await LotteryService.draw_lottery()
            await self.announce_draw_results(results)
        except Exception as e:
            logger.error(f"Error en sorteo automático de lotería: {e}")

    async def loto(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)
        
        state = await LotteryService.get_state()
        pool = state['pool']
        next_draw = state['next_draw']
        
        prestige_lvl = await asyncio.to_thread(get_user_prestige_level, user_id)
        ticket_limit = 6 if prestige_lvl >= 1 else 5
        
        tickets = await asyncio.to_thread(get_active_tickets)
        user_tickets = [t[1] for t in tickets if t[0] == user_id]
        
        embed = discord.Embed(
            title="🎰 LOTO DEL CASINO 🎰",
            color=discord.Color.purple(),
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )
        
        next_draw_str = "Hoy a medianoche"
        if next_draw:
            next_draw_str = next_draw.strftime("%d/%m/%Y a las 00:00")

        prestige_note = " *(+1 por Prestigio 🌟)*" if prestige_lvl >= 1 else ""
        embed.description = (
            f"💰 **Pozo Acumulado Actual:** `{pool:,}` monedas\n"
            f"📅 **Próximo Sorteo:** `{next_draw_str}`\n"
            f"🎟️ **Precio del Boleto:** `500` monedas\n"
            f"⚠️ **Límite diario:** `{ticket_limit}` boletos por usuario{prestige_note}"
        )
        
        if user_tickets:
            tickets_list = "\n".join(f"🎫 Boleto: `[{t.replace(',', ', ')}]`" for t in user_tickets)
            embed.add_field(name=f"Tus Boletos Hoy ({len(user_tickets)}/{ticket_limit})", value=tickets_list, inline=False)
        else:
            embed.add_field(name=f"Tus Boletos Hoy (0/{ticket_limit})", value="No tienes boletos para el sorteo de hoy.\n¡Usa el botón de abajo para comprar uno!", inline=False)

        embed.add_field(
            name="🏆 Tabla de Premios", 
            value=(
                "- **4 aciertos (Jackpot):** 100% del pozo acumulado (compartido)\n"
                "- **3 aciertos:** 15% del pozo acumulado (compartido)\n"
                "- **2 aciertos:** 2% del pozo acumulado (compartido)\n"
                "- **1 acierto:** 200 monedas de reembolso"
            ),
            inline=False
        )
        
        embed.set_footer(text="¡2% de todas las apuestas en juegos individuales se añaden al pozo!")
        view = LotoView(self, user_id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def loto_comprar(
        self, 
        interaction: discord.Interaction, 
        num1: Optional[int] = None, 
        num2: Optional[int] = None, 
        num3: Optional[int] = None, 
        num4: Optional[int] = None
    ):

        await interaction.response.defer()
        user_id = interaction.user.id
        can_play, lockout_msg = await CasinoService.check_casino_lockout(user_id)
        if not can_play:
            await interaction.followup.send(lockout_msg, ephemeral=True)
            return

        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)
        
        # Límite dinámico: Prestigio I permite 6 boletos en vez de 5
        prestige_lvl = await asyncio.to_thread(get_user_prestige_level, user_id)
        ticket_limit = 6 if prestige_lvl >= 1 else 5
        
        # Validar si el usuario ya tiene el límite de boletos antes de procesar
        current_count = await LotteryService.get_user_tickets(user_id)
        if current_count >= ticket_limit:
            await interaction.followup.send(f"❌ Ya has alcanzado el límite de {ticket_limit} boletos de loto para hoy.", ephemeral=True)
            return

        # Colectar los números ingresados
        entered = [n for n in [num1, num2, num3, num4] if n is not None]
        
        # Validar rangos e duplicados de los ingresados
        if any(n < 1 or n > 25 for n in entered):
            await interaction.followup.send("❌ Todos los números del loto deben estar entre 1 y 25.", ephemeral=True)
            return
            
        if len(set(entered)) != len(entered):
            await interaction.followup.send("❌ Los números ingresados no pueden repetirse.", ephemeral=True)
            return
            
        # Autocompletar los números faltantes de forma aleatoria
        available = list(set(range(1, 26)) - set(entered))
        needed = 4 - len(entered)
        if needed > 0:
            chosen = random.sample(available, needed)
            entered.extend(chosen)
            
        numbers = sorted(entered)
        
        # Llamar al servicio
        success, message, new_balance = await LotteryService.purchase_ticket(user_id, numbers)
        
        if not success:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="🎫 BOLETO ADQUIRIDO",
            description=f"{message}\n\nCada boleto aumenta la emoción. ¡Suerte en el sorteo de medianoche!",
            color=discord.Color.green()
        )
        embed.add_field(name="Precio", value="500 monedas", inline=True)
        embed.add_field(name="Tu saldo actual", value=f"{new_balance:,} monedas", inline=True)
        await interaction.followup.send(embed=embed)

class LotoView(discord.ui.View):
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="🎟️ Comprar Boleto (500)", style=discord.ButtonStyle.success)
    async def buy_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        await self.cog.loto_comprar(interaction)

    async def loto_draw(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        try:
            results = await LotteryService.draw_lottery()
            await self.announce_draw_results(results, manual_ctx=interaction)
        except Exception as e:
            logger.error(f"Error en sorteo manual de loto: {e}")
            await interaction.followup.send(f"❌ Ocurrió un error al realizar el sorteo: {e}", ephemeral=True)


    async def announce_draw_results(self, results: dict, manual_ctx=None):
        """Anuncia los resultados del sorteo en el canal de logs y en los canales públicos de los servidores."""
        if results.get('no_tickets', False):
            embed = discord.Embed(
                title="🎰 Sorteo de Loto - Sin Participantes",
                description="Hoy no se registraron boletos para el loto del casino. ¡El pozo acumulado se mantiene intacto!",
                color=discord.Color.yellow()
            )
            embed.add_field(name="Pozo Acumulado", value=f"{results['pool']:,} monedas", inline=True)
            embed.set_footer(text="Próximo sorteo mañana a medianoche. ¡Compra boletos con /loto_comprar!")
            
            # Enviar a logs
            logs_channel = self.bot.get_channel(1519413696206737559)
            if not logs_channel:
                try:
                    logs_channel = await self.bot.fetch_channel(1519413696206737559)
                except Exception:
                    logs_channel = None
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            # Enviar a canal específico de notificaciones centralizado
            await send_loto_notification(self.bot, embed)
            
            if manual_ctx:
                if isinstance(manual_ctx, discord.Interaction):
                    await manual_ctx.followup.send(embed=embed)
                else:
                    await manual_ctx.send(embed=embed)
            return

        winning_nums = results['winning_numbers']
        winning_nums_str = " ".join(f"**[{n:02d}]**" for n in winning_nums)
        
        embed = discord.Embed(
            title="🎰 RESULTADOS DEL SORTEO DE LOTO 🎰",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )
        embed.description = f"¡El sorteo del loto ha finalizado!\n\n🔴 **Números Ganadores:** {winning_nums_str}"
        
        embed.add_field(name="💰 Pozo del Sorteo", value=f"{results['pool']:,} monedas", inline=True)
        embed.add_field(name="🎟️ Boletos Vendidos", value=f"{results['total_tickets']:,}", inline=True)
        embed.add_field(name="💸 Nuevo Pozo Acumulado", value=f"{results['new_pool']:,} monedas", inline=False)
        
        # Ganadores de 4 aciertos (Jackpot)
        winners_4 = [f"<@{uid}>" for uid in results['winners_4']]
        w4_text = ", ".join(winners_4) if winners_4 else "Nadie ganó el Jackpot."
        embed.add_field(name="🏆 Jackpot (4 Aciertos - 100%)", value=w4_text, inline=False)
        
        # Ganadores de 3 aciertos (15% del pozo)
        winners_3 = []
        for uid in results['winners_3']:
            payout = results['payouts'].get(uid, 0)
            winners_3.append(f"<@{uid}> ({payout:,} monedas)")
        w3_text = ", ".join(winners_3) if winners_3 else "Sin ganadores."
        embed.add_field(name="🥈 3 Aciertos (15% pozo)", value=w3_text, inline=False)
        
        # Ganadores de 2 aciertos (2% del pozo)
        winners_2 = []
        for uid in results['winners_2']:
            payout = results['payouts'].get(uid, 0)
            winners_2.append(f"<@{uid}> ({payout:,} monedas)")
        w2_text = ", ".join(winners_2) if winners_2 else "Sin ganadores."
        embed.add_field(name="🥉 2 Aciertos (2% pozo)", value=w2_text, inline=False)
        
        # Ganadores de 1 acierto (Reembolso)
        winners_1 = [f"<@{uid}>" for uid in results['winners_1']]
        w1_text = ", ".join(winners_1) if winners_1 else "Sin ganadores."
        embed.add_field(name="🎫 1 Acierto (Reembolso 200 monedas)", value=w1_text, inline=False)
        
        embed.set_footer(text="Próximo sorteo mañana a medianoche. ¡Usa /loto_comprar para participar!")

        # 1. Enviar al canal de logs
        logs_channel = self.bot.get_channel(1519413696206737559)
        if not logs_channel:
            try:
                logs_channel = await self.bot.fetch_channel(1519413696206737559)
            except Exception:
                logs_channel = None
        if logs_channel:
            try:
                await logs_channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Error enviando sorteo a canal de logs: {e}")

        # 1b. Enviar a canal específico de notificaciones con tags centralizado
        participants = results.get('participants', [])
        content = None
        if participants:
            content = " ".join(f"<@{uid}>" for uid in participants)
        await send_loto_notification(self.bot, embed, content=content)
        # 2. Enviar a canales públicos en los servidores
        for guild in self.bot.guilds:
            target_channel = None
            for channel in guild.text_channels:
                if channel.name in ['loto', 'loto-casino', 'casino']:
                    if channel.permissions_for(guild.me).send_messages:
                        target_channel = channel
                        break
            
            if target_channel:
                try:
                    await target_channel.send(embed=embed)
                except Exception as e:
                    logger.error(f"Error enviando sorteo a canal publico {target_channel.name} en {guild.name}: {e}")

        # 3. Si se gatilló manualmente, responder
        if manual_ctx:
            if isinstance(manual_ctx, discord.Interaction):
                await manual_ctx.followup.send(embed=embed)
            else:
                await manual_ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Loto(bot))

