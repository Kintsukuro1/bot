import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from typing import Optional
from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, usuario_tiene_item, usuario_tiene_mejora, registrar_transaccion, record_game_result
from src.services.casino_service import CasinoService
from src.commands.economy.pets import process_post_game_events
from src.commands.shop.black_market_items import BLACK_MARKET
from src.utils.dynamic_difficulty import DynamicDifficulty
from src.utils.cooldowns import CASINO_COOLDOWN

class CoinflipDuelView(discord.ui.View):
    def __init__(self, challenger, challenged, apuesta):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.challenged = challenged
        self.apuesta = apuesta
        self.game_started = False
        self.game_over = False

    @discord.ui.button(label="✅ Aceptar Duelo", style=discord.ButtonStyle.success)
    async def accept_duel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("Solo el retado puede aceptar el duelo.", ephemeral=True)
            return

        if self.game_over or self.game_started:
            await interaction.response.send_message("Este duelo ya fue resuelto.", ephemeral=True)
            return

        can_play, lockout_msg = await CasinoService.check_casino_lockout(self.challenged.id)
        if not can_play:
            await interaction.response.send_message(lockout_msg, ephemeral=True)
            return

        self.game_started = True
        self.game_over = True
        
        success, challenged_balance = await CasinoService.place_bet(self.challenged.id, self.apuesta, 'coinflip_duel')
        if not success:
            self.game_started = False
            self.game_over = False
            await interaction.response.send_message(f"❌ No tienes suficiente saldo para este duelo. Necesitas {self.apuesta} monedas.", ephemeral=True)
            return

        # Desactivar botones
        for item in self.children:
            item.disabled = True
            
        # Lanzamiento 100% justo (50/50)
        # El retador tiene cara, el retado tiene sello
        resultado_moneda = random.choice(['cara', 'sello'])
        
        if resultado_moneda == 'cara':
            winner = self.challenger
            loser = self.challenged
            challenger_win = True
        else:
            winner = self.challenged
            loser = self.challenger
            challenger_win = False
            
        # Procesar transferencias
        lockout_activated = False
        impuesto = 0
        if challenger_win:
            challenger_bal = await asyncio.to_thread(get_balance, self.challenger.id)
            nuevo_saldo, impuesto = await CasinoService.settle_win(
                self.challenger.id,
                self.apuesta,
                self.apuesta * 2,
                'coinflip_duel',
                0.0,
                challenger_bal
            )
            lockout_activated = await CasinoService.check_and_apply_winstreak_lockout(self.challenger.id, nuevo_saldo)
            
            await CasinoService.settle_loss(
                self.challenged.id,
                self.apuesta,
                'coinflip_duel',
                0.0,
                challenged_balance
            )
            try:
                await process_post_game_events(interaction, self.challenger.id, 'coinflip_duel', self.apuesta, self.apuesta)
            except Exception:
                pass
            try:
                await process_post_game_events(interaction, self.challenged.id, 'coinflip_duel', self.apuesta, 0)
            except Exception:
                pass
        else:
            nuevo_saldo, impuesto = await CasinoService.settle_win(
                self.challenged.id,
                self.apuesta,
                self.apuesta * 2,
                'coinflip_duel',
                0.0,
                challenged_balance
            )
            lockout_activated = await CasinoService.check_and_apply_winstreak_lockout(self.challenged.id, nuevo_saldo)
            
            challenger_bal = await asyncio.to_thread(get_balance, self.challenger.id)
            await CasinoService.settle_loss(
                self.challenger.id,
                self.apuesta,
                'coinflip_duel',
                0.0,
                challenger_bal
            )
            try:
                await process_post_game_events(interaction, self.challenger.id, 'coinflip_duel', self.apuesta, 0)
            except Exception:
                pass
            try:
                await process_post_game_events(interaction, self.challenged.id, 'coinflip_duel', self.apuesta, self.apuesta)
            except Exception:
                pass
            
        # Embed de resultado final
        desc = (
            f"🪙 **Lanzamiento:** {resultado_moneda.upper()}\n\n"
            f"👤 **{self.challenger.display_name}:** CARA 🪙\n"
            f"👤 **{self.challenged.display_name}:** SELLO 🪙\n\n"
            f"🏆 **GANADOR:** {winner.mention}\n"
            f"💰 **Premio Bruto:** {self.apuesta * 2} monedas\n"
            f"💸 **Impuesto Casino (3%):** {impuesto} monedas (destruido)\n"
            f"✨ **Premio Neto:** {self.apuesta * 2 - impuesto} monedas\n\n"
            f"💳 **Saldos actuales:**\n"
            f"• {self.challenger.display_name}: {await asyncio.to_thread(get_balance, self.challenger.id):,} monedas\n"
            f"• {self.challenged.display_name}: {await asyncio.to_thread(get_balance, self.challenged.id):,} monedas"
        )
        if lockout_activated:
            desc += f"\n\n⚠️ <@{winner.id}> **🎰 Has ganado mucho muy rápido — tómate un descanso de 25 minutos antes de seguir jugando.**"

        embed = discord.Embed(
            title="⚔️ Resultado del Duelo de Coinflip",
            description=desc,
            color=discord.Color.gold()
        )
        
        # GIFs de resultado
        cara_gif = "https://cdn.discordapp.com/attachments/1142907813757198386/1386677290578214932/gif_cara.gif?ex=685a935d&is=685941dd&hm=d41249e840fb753ab064a397836bd37b77616ba50df68a37e17f00287199b958&"
        cruz_gif = "https://cdn.discordapp.com/attachments/1142907813757198386/1386677290179629107/gif_sello.gif?ex=685a935d&is=685941dd&hm=b1b05c3bc3c7791e6a224d2d27861ddfa990a0ddfc24c24cefa0b209bdad3594&"
        embed.set_image(url=cara_gif if resultado_moneda == 'cara' else cruz_gif)
        
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="❌ Rechazar Duelo", style=discord.ButtonStyle.danger)
    async def decline_duel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("Solo el retado puede rechazar el duelo.", ephemeral=True)
            return

        if self.game_over:
            await interaction.response.send_message("Este duelo ya fue resuelto.", ephemeral=True)
            return
        
        self.game_over = True
        self.game_started = True
        await CasinoService.refund_bet(self.challenger.id, self.apuesta, 'coinflip_duel', 'Duelo rechazado')
        
        embed = discord.Embed(
            title="⚔️ Duelo Rechazado",
            description=f"**{self.challenged.display_name}** ha rechazado el duelo de **{self.challenger.display_name}**",
            color=discord.Color.red()
        )
        
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        """Se ejecuta cuando se agota el tiempo."""
        if not self.game_over:
            self.game_over = True
            await CasinoService.refund_bet(self.challenger.id, self.apuesta, 'coinflip_duel', 'Timeout sin aceptar')
            for item in self.children:
                item.disabled = True
            try:
                if hasattr(self, 'message') and self.message:
                    embed = self.message.embeds[0]
                    embed.color = discord.Color.red()
                    embed.title = "⚔️ Duelo Cancelado"
                    embed.description += "\n\n⌛ **El duelo ha expirado.** Las monedas del retador han sido devueltas."
                    await self.message.edit(embed=embed, view=self)
            except Exception:
                pass
            except Exception:
                pass


class CoinflipView(discord.ui.View):
    def __init__(self, user, apuesta, saldo):
        super().__init__(timeout=30)
        self.user = user
        self.apuesta = apuesta
        self.saldo = saldo
        self.game_over = False

    @discord.ui.button(label="🪙 CARA", style=discord.ButtonStyle.primary, emoji="😊")
    async def cara_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
        
        self.game_over = True
        await self._play_coinflip(interaction, "cara")

    @discord.ui.button(label="🪙 SELLO", style=discord.ButtonStyle.secondary, emoji="⚡")
    async def sello_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
        
        self.game_over = True
        await self._play_coinflip(interaction, "sello")

    async def _play_coinflip(self, interaction, eleccion):
        """Ejecuta el juego de coinflip con dificultad dinámica."""
        user_id = self.user.id
        
        # Calcular dificultad dinámica
        difficulty_modifier, difficulty_explanation = await asyncio.to_thread(
            DynamicDifficulty.calculate_dynamic_difficulty, user_id, self.apuesta, 'coinflip'
        )
        
        # Probabilidad base del 50%
        base_prob = 0.5
        
        # Aplicar dificultad dinámica (ahora afecta al resultado de la moneda, no a una segunda verificación)
        prob_ganar = DynamicDifficulty.apply_difficulty_to_odds(base_prob, difficulty_modifier)
        
        # Calcular probabilidades adicionales basadas en el porcentaje de apuesta (con respecto al saldo original)
        saldo_original = self.saldo + self.apuesta
        porcentaje_apuesta = (self.apuesta / saldo_original) * 100 if saldo_original > 0 else 100.0
        bet_adjustment = 0.0
        if porcentaje_apuesta <= 25:
            bet_adjustment = 0.1  # Bonificación por apuesta conservadora
        elif porcentaje_apuesta >= 75:
            bet_adjustment = -0.05  # Penalización menor por apuesta arriesgada
            
        prob_ganar = max(0.15, min(0.85, prob_ganar + bet_adjustment))
            
        # --- MEJORAS BLACK MARKET ---
        ganancia_bonus = 1.0
        if await asyncio.to_thread(usuario_tiene_mejora, user_id, 2):  # Apostador Pro
            prob_ganar += 0.03  # Mejora las probabilidades
        if await asyncio.to_thread(usuario_tiene_mejora, user_id, 3):  # Magnate
            ganancia_bonus += 0.15  # Aumenta la ganancia
        if await asyncio.to_thread(usuario_tiene_mejora, user_id, 10):  # Corona
            ganancia_bonus += 0.05
        # ---------------------------
        
        # Animación de lanzamiento
        tirada_embed = discord.Embed(
            title="🪙 Lanzando la moneda...",
            description=(
                f"🎯 **Tu elección:** {eleccion.upper()}\n"
                f"💰 **Apuesta:** {self.apuesta} monedas\n\n"
                f"*La moneda está girando en el aire...*"
            ),
            color=discord.Color.blurple()
        )
        
        # Desactivar botones
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=tirada_embed, view=self)
        await asyncio.sleep(2)
        
        # Determinar resultado
        # prob_ganar es la probabilidad de que el usuario gane
        gano_final = random.random() < prob_ganar
        resultado_moneda = eleccion if gano_final else ('sello' if eleccion == 'cara' else 'cara')
        
        # GIFs de resultado
        cara_gif = "https://cdn.discordapp.com/attachments/1142907813757198386/1386677290578214932/gif_cara.gif?ex=685a935d&is=685941dd&hm=d41249e840fb753ab064a397836bd37b77616ba50df68a37e17f00287199b958&"
        cruz_gif = "https://cdn.discordapp.com/attachments/1142907813757198386/1386677290179629107/gif_sello.gif?ex=685a935d&is=685941dd&hm=b1b05c3bc3c7791e6a224d2d27861ddfa990a0ddfc24c24cefa0b209bdad3594&"
        
        if gano_final:
            # Usuario ganó
            ganancia = int(self.apuesta * ganancia_bonus)
            winnings = self.apuesta + ganancia
            nuevo_saldo, impuesto = await CasinoService.settle_win(
                user_id,
                self.apuesta,
                winnings,
                'coinflip',
                difficulty_modifier,
                self.saldo
            )
            lockout_activated = await CasinoService.check_and_apply_winstreak_lockout(user_id, nuevo_saldo)
            
            try:
                await process_post_game_events(interaction, user_id, 'coinflip', self.apuesta, ganancia)
            except Exception:
                pass
            
            desc_text = (
                f"🪙 **Resultado:** {resultado_moneda.upper()}\n"
                f"🎯 **Tu elección:** {eleccion.upper()}\n"
                f"✅ **¡Acertaste!**\n\n"
                f"💰 **Premio Bruto:** +{winnings} monedas\n"
                f"💸 **Impuesto Casino (3%):** -{impuesto} monedas (destruido)\n"
                f"✨ **Premio Neto:** +{winnings - impuesto} monedas\n"
                f"💳 **Saldo actual:** {nuevo_saldo} monedas"
            )
            if lockout_activated:
                desc_text += "\n\n⚠️ **🎰 Has ganado mucho muy rápido — tómate un descanso de 25 minutos antes de seguir jugando.**"
                
            embed = discord.Embed(
                title="🎉 ¡GANASTE!",
                description=desc_text,
                color=discord.Color.green()
            )
            embed.set_image(url=cara_gif if resultado_moneda == 'cara' else cruz_gif)
        else:
            # Usuario perdió
            nuevo_saldo = await CasinoService.settle_loss(
                user_id,
                self.apuesta,
                'coinflip',
                difficulty_modifier,
                self.saldo
            )
            try:
                await process_post_game_events(interaction, user_id, 'coinflip', self.apuesta, 0)
            except Exception:
                pass
            
            # El usuario sólo pierde cuando no acierta
            razon = "No acertaste el resultado"
            
            embed = discord.Embed(
                title="😞 Perdiste",
                description=(
                    f"🪙 **Resultado:** {resultado_moneda.upper()}\n"
                    f"🎯 **Tu elección:** {eleccion.upper()}\n"
                    f"❌ **{razon}**\n\n"
                    f"💸 **Pérdida:** -{self.apuesta} monedas\n"
                    f"💳 **Saldo actual:** {nuevo_saldo} monedas"
                ),
                color=discord.Color.red()
            )
            embed.set_image(url=cara_gif if resultado_moneda == 'cara' else cruz_gif)
        
        await interaction.edit_original_response(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        """Se ejecuta cuando se agota el tiempo."""
        if not self.game_over:
            self.game_over = True
            await CasinoService.refund_bet(self.user.id, self.apuesta, 'coinflip', 'Timeout sin jugar')
            for item in self.children:
                item.disabled = True

class Coinflip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="coinflip", description="Juega un coinflip: elige cara o sello con los botones")
    @app_commands.describe(
        apuesta="Cantidad de monedas a apostar",
        retar="Usuario al que quieres retar a un duelo (opcional)"
    )
    @CASINO_COOLDOWN
    async def coinflip(self, interaction: discord.Interaction, apuesta: int, retar: Optional[discord.Member] = None):
        await interaction.response.defer()
        user_id = interaction.user.id
        user_name = interaction.user.name
        await asyncio.to_thread(ensure_user, user_id, user_name)  # Asegura registro y datos del usuario

        can_play, lockout_msg = await CasinoService.check_casino_lockout(user_id)
        if not can_play:
            await interaction.followup.send(lockout_msg, ephemeral=True)
            return

        if apuesta <= 0:
            await interaction.followup.send("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return

        # Si se especificó un usuario para retar, realizar todas las validaciones antes de descontar saldo
        if retar:
            if retar.id == interaction.user.id:
                await interaction.followup.send("❌ No puedes retarte a ti mismo.", ephemeral=True)
                return
            
            if retar.bot:
                await interaction.followup.send("❌ No puedes retar a un bot.", ephemeral=True)
                return
            
            can_play_opponent, opponent_lockout_msg = await CasinoService.check_casino_lockout(retar.id)
            if not can_play_opponent:
                await interaction.followup.send(f"❌ {retar.display_name} está bloqueado del casino temporalmente.", ephemeral=True)
                return

            # Asegurar que el retado esté registrado
            await asyncio.to_thread(ensure_user, retar.id, retar.name)
            challenged_balance = await asyncio.to_thread(get_balance, retar.id)
            
            if challenged_balance < apuesta:
                await interaction.followup.send(
                    f"❌ {retar.display_name} no tiene suficiente saldo para este duelo. "
                    f"Necesita al menos {apuesta} monedas (tiene {challenged_balance}).", 
                    ephemeral=True
                )
                return

        # Descontar el saldo del retador
        success, saldo = await CasinoService.place_bet(user_id, apuesta, 'coinflip')
        if not success:
            await interaction.followup.send("❌ No tienes suficiente saldo para esa apuesta.", ephemeral=True)
            return
        
        # Si se especificó un usuario para retar, iniciar duelo
        if retar:
            # Crear embed de reto
            embed = discord.Embed(
                title="⚔️ Reto de Duelo - Coinflip",
                description=(
                    f"🥊 **{interaction.user.display_name}** te ha retado a un duelo!\n\n"
                    f"💰 **Apuesta:** {apuesta} monedas cada uno\n"
                    f"🏆 **Premio total:** {apuesta * 2} monedas\n"
                    f"🎯 **Juego:** Coinflip con dificultad dinámica\n\n"
                    f"**{retar.display_name}**, ¿aceptas el reto?"
                ),
                color=discord.Color.orange()
            )
            embed.set_footer(text=f"Retado por {interaction.user.display_name} • Tienes 60 segundos para responder")
            
            # Crear vista de duelo
            duel_view = CoinflipDuelView(interaction.user, retar, apuesta)
            
            duel_view.message = await interaction.followup.send(embed=embed, view=duel_view)
            return
        
        # Juego normal (sin duelo)
        # Crear embed inicial
        embed = discord.Embed(
            title="🪙 Coinflip Casino",
            description=(
                f"💰 **Apuesta:** {apuesta} monedas\n"
                f"💳 **Tu saldo:** {saldo} monedas\n\n"
                f"🎯 **¿Qué eliges?**\n"
                f"Haz clic en **CARA** o **SELLO** para lanzar la moneda"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="Tienes 30 segundos para elegir")
        
        # Crear vista con botones
        view = CoinflipView(interaction.user, apuesta, saldo)
        
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Coinflip(bot))
    print("Coinflip cog loaded successfully.")
