import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from typing import Optional
from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, usuario_tiene_item, usuario_tiene_mejora, registrar_transaccion, record_game_result
from src.commands.economy.pets import process_post_game_events
from src.commands.shop.black_market_items import BLACK_MARKET
from src.utils.dynamic_difficulty import DynamicDifficulty

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
        
        # Verificar saldos (retador ya fue descontado)
        challenger_balance = await asyncio.to_thread(get_balance, self.challenger.id)
        
        success, challenged_balance = await asyncio.to_thread(deduct_balance, self.challenged.id, self.apuesta)
        if not success:
            await interaction.response.send_message(f"❌ No tienes suficiente saldo para este duelo. Necesitas {self.apuesta} monedas.", ephemeral=True)
            return
        
        self.game_started = True
        self.game_over = True
        
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
        if challenger_win:
            await asyncio.to_thread(add_balance, self.challenger.id, self.apuesta * 2)
            await asyncio.to_thread(registrar_transaccion, self.challenger.id, self.apuesta, f"Duelo coinflip: ganó vs {self.challenged.display_name}")
            await asyncio.to_thread(registrar_transaccion, self.challenged.id, -self.apuesta, f"Duelo coinflip: perdió vs {self.challenger.display_name}")
            
            # Registrar historial con dificultad neutral 0.0 (duelo PVP justo)
            await asyncio.to_thread(record_game_result, self.challenger.id, 'coinflip_duel', self.apuesta, 'win', self.apuesta, 0.0, challenger_balance + self.apuesta)
            try:
                await process_post_game_events(interaction, self.challenger.id, 'coinflip_duel', self.apuesta, self.apuesta)
            except Exception:
                pass
            await asyncio.to_thread(record_game_result, self.challenged.id, 'coinflip_duel', self.apuesta, 'loss', 0, 0.0, challenged_balance)
            try:
                await process_post_game_events(interaction, self.challenged.id, 'coinflip_duel', self.apuesta, 0)
            except Exception:
                pass
        else:
            await asyncio.to_thread(add_balance, self.challenged.id, self.apuesta * 2)
            await asyncio.to_thread(registrar_transaccion, self.challenger.id, -self.apuesta, f"Duelo coinflip: perdió vs {self.challenged.display_name}")
            await asyncio.to_thread(registrar_transaccion, self.challenged.id, self.apuesta, f"Duelo coinflip: ganó vs {self.challenger.display_name}")
            
            # Registrar historial
            await asyncio.to_thread(record_game_result, self.challenger.id, 'coinflip_duel', self.apuesta, 'loss', 0, 0.0, challenger_balance - self.apuesta)
            try:
                await process_post_game_events(interaction, self.challenger.id, 'coinflip_duel', self.apuesta, 0)
            except Exception:
                pass
            await asyncio.to_thread(record_game_result, self.challenged.id, 'coinflip_duel', self.apuesta, 'win', self.apuesta, 0.0, challenged_balance + self.apuesta * 2)
            try:
                await process_post_game_events(interaction, self.challenged.id, 'coinflip_duel', self.apuesta, self.apuesta)
            except Exception:
                pass
            
        # Embed de resultado final
        embed = discord.Embed(
            title="⚔️ Resultado del Duelo de Coinflip",
            description=(
                f"🪙 **Lanzamiento:** {resultado_moneda.upper()}\n\n"
                f"👤 **{self.challenger.display_name}:** CARA 🪙\n"
                f"👤 **{self.challenged.display_name}:** SELLO 🪙\n\n"
                f"🏆 **GANADOR:** {winner.mention}\n"
                f"💰 **Premio:** {self.apuesta} monedas de su oponente\n\n"
                f"💳 **Saldos actuales:**\n"
                f"• {self.challenger.display_name}: {await asyncio.to_thread(get_balance, self.challenger.id):,} monedas\n"
                f"• {self.challenged.display_name}: {await asyncio.to_thread(get_balance, self.challenged.id):,} monedas"
            ),
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
        
        self.game_over = True
        await asyncio.to_thread(add_balance, self.challenger.id, self.apuesta)
        
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
            await asyncio.to_thread(add_balance, self.challenger.id, self.apuesta)
            for item in self.children:
                item.disabled = True


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
        
        # Calcular probabilidades adicionales basadas en el porcentaje de apuesta
        porcentaje_apuesta = (self.apuesta / self.saldo) * 100
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
            nuevo_saldo = self.saldo + self.apuesta + ganancia
            await asyncio.to_thread(add_balance, user_id, self.apuesta + ganancia)
            await asyncio.to_thread(registrar_transaccion, user_id, ganancia, f"Coinflip: ganó con {eleccion}")
            
            # Registrar resultado para el sistema de dificultad
            await asyncio.to_thread(record_game_result, user_id, 'coinflip', self.apuesta, 'win', ganancia, difficulty_modifier, nuevo_saldo)
            try:
                await process_post_game_events(interaction, user_id, 'coinflip', self.apuesta, ganancia)
            except Exception:
                pass
            
            embed = discord.Embed(
                title="🎉 ¡GANASTE!",
                description=(
                    f"🪙 **Resultado:** {resultado_moneda.upper()}\n"
                    f"🎯 **Tu elección:** {eleccion.upper()}\n"
                    f"✅ **¡Acertaste!**\n\n"
                    f"💰 **Ganancia:** +{ganancia} monedas\n"
                    f"💳 **Saldo actual:** {nuevo_saldo} monedas"
                ),
                color=discord.Color.green()
            )
            embed.set_image(url=cara_gif if resultado_moneda == 'cara' else cruz_gif)
        else:
            # Usuario perdió
            nuevo_saldo = self.saldo
            await asyncio.to_thread(registrar_transaccion, user_id, -self.apuesta, f"Coinflip: perdió con {eleccion}")
            
            # Registrar resultado para el sistema de dificultad
            await asyncio.to_thread(record_game_result, user_id, 'coinflip', self.apuesta, 'loss', 0, difficulty_modifier, nuevo_saldo)
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
            await asyncio.to_thread(add_balance, self.user.id, self.apuesta)
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
    async def coinflip(self, interaction: discord.Interaction, apuesta: int, retar: Optional[discord.Member] = None):
        user_id = interaction.user.id
        user_name = interaction.user.name
        await asyncio.to_thread(ensure_user, user_id, user_name)  # Asegura registro y datos del usuario
        if apuesta <= 0:
            await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return

        success, saldo = await asyncio.to_thread(deduct_balance, user_id, apuesta)
        if not success:
            await interaction.response.send_message("❌ No tienes suficiente saldo para esa apuesta.", ephemeral=True)
            return
        
        # Si se especificó un usuario para retar, iniciar duelo
        if retar:
            # Validaciones para duelos
            if retar.id == interaction.user.id:
                await interaction.response.send_message("❌ No puedes retarte a ti mismo.", ephemeral=True)
                return
            
            if retar.bot:
                await interaction.response.send_message("❌ No puedes retar a un bot.", ephemeral=True)
                return
            
            # Asegurar que el retado esté registrado
            await asyncio.to_thread(ensure_user, retar.id, retar.name)
            challenged_balance = await asyncio.to_thread(get_balance, retar.id)
            
            if challenged_balance < apuesta:
                await interaction.response.send_message(
                    f"❌ {retar.display_name} no tiene suficiente saldo para este duelo. "
                    f"Necesita al menos {apuesta} monedas (tiene {challenged_balance}).", 
                    ephemeral=True
                )
                return
            
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
            
            await interaction.response.send_message(embed=embed, view=duel_view)
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
        
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Coinflip(bot))
    print("Coinflip cog loaded successfully.")
