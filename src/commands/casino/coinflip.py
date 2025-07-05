import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from typing import Optional
from src.db import get_balance, set_balance, ensure_user, usuario_tiene_item, usuario_tiene_mejora, registrar_transaccion, record_game_result
from src.commands.shop.black_market_items import BLACK_MARKET
from src.utils.dynamic_difficulty import DynamicDifficulty

class CoinflipDuelView(discord.ui.View):
    def __init__(self, challenger, challenged, apuesta):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.challenged = challenged
        self.apuesta = apuesta
        self.challenger_choice = None
        self.challenged_choice = None
        self.game_started = False
        self.game_over = False

    @discord.ui.button(label="✅ Aceptar Duelo", style=discord.ButtonStyle.success)
    async def accept_duel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("Solo el retado puede aceptar el duelo.", ephemeral=True)
            return
        
        # Verificar saldo del retado
        challenged_balance = get_balance(self.challenged.id)
        if challenged_balance < self.apuesta:
            await interaction.response.send_message(f"❌ No tienes suficiente saldo para este duelo. Necesitas {self.apuesta} monedas.", ephemeral=True)
            return
        
        self.game_started = True
        
        # Actualizar vista con botones de elección
        self.clear_items()
        
        # Botones para el retador
        challenger_cara = discord.ui.Button(
            label="🪙 CARA", 
            style=discord.ButtonStyle.primary, 
            custom_id="challenger_cara",
            emoji="😊"
        )
        challenger_sello = discord.ui.Button(
            label="🪙 SELLO", 
            style=discord.ButtonStyle.secondary, 
            custom_id="challenger_sello",
            emoji="⚡"
        )
        
        # Botones para el retado
        challenged_cara = discord.ui.Button(
            label="🪙 CARA", 
            style=discord.ButtonStyle.primary, 
            custom_id="challenged_cara",
            emoji="😊"
        )
        challenged_sello = discord.ui.Button(
            label="🪙 SELLO", 
            style=discord.ButtonStyle.secondary, 
            custom_id="challenged_sello",
            emoji="⚡"
        )
        
        challenger_cara.callback = self.create_choice_callback("cara", "challenger")
        challenger_sello.callback = self.create_choice_callback("sello", "challenger")
        challenged_cara.callback = self.create_choice_callback("cara", "challenged")
        challenged_sello.callback = self.create_choice_callback("sello", "challenged")
        
        self.add_item(challenger_cara)
        self.add_item(challenger_sello)
        self.add_item(challenged_cara)
        self.add_item(challenged_sello)
        
        embed = discord.Embed(
            title="⚔️ Duelo de Coinflip Aceptado",
            description=(
                f"🥊 **{self.challenger.display_name}** vs **{self.challenged.display_name}**\n"
                f"💰 **Apuesta:** {self.apuesta} monedas cada uno\n"
                f"🏆 **Premio total:** {self.apuesta * 2} monedas\n\n"
                f"**{self.challenger.display_name}:** Usa los primeros 2 botones\n"
                f"**{self.challenged.display_name}:** Usa los últimos 2 botones\n\n"
                f"⏳ Ambos deben elegir para comenzar el duelo"
            ),
            color=discord.Color.orange()
        )
        
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="❌ Rechazar Duelo", style=discord.ButtonStyle.danger)
    async def decline_duel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("Solo el retado puede rechazar el duelo.", ephemeral=True)
            return
        
        self.game_over = True
        
        embed = discord.Embed(
            title="⚔️ Duelo Rechazado",
            description=f"**{self.challenged.display_name}** ha rechazado el duelo de **{self.challenger.display_name}**",
            color=discord.Color.red()
        )
        
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    def create_choice_callback(self, choice, player):
        async def choice_callback(interaction: discord.Interaction):
            if self.game_over:
                await interaction.response.send_message("El duelo ya ha terminado.", ephemeral=True)
                return
            
            if player == "challenger" and interaction.user.id != self.challenger.id:
                await interaction.response.send_message("Solo el retador puede usar estos botones.", ephemeral=True)
                return
            elif player == "challenged" and interaction.user.id != self.challenged.id:
                await interaction.response.send_message("Solo el retado puede usar estos botones.", ephemeral=True)
                return
            
            # Registrar elección
            if player == "challenger":
                self.challenger_choice = choice
            else:
                self.challenged_choice = choice
            
            # Verificar si ambos han elegido
            if self.challenger_choice and self.challenged_choice:
                await self._execute_duel(interaction)
            else:
                # Mostrar que el jugador ha elegido
                waiting_for = self.challenged.display_name if self.challenger_choice else self.challenger.display_name
                
                embed = discord.Embed(
                    title="⚔️ Duelo de Coinflip en Progreso",
                    description=(
                        f"🥊 **{self.challenger.display_name}** vs **{self.challenged.display_name}**\n"
                        f"💰 **Apuesta:** {self.apuesta} monedas cada uno\n\n"
                        f"✅ **{interaction.user.display_name}** ha elegido {choice.upper()}\n"
                        f"⏳ Esperando a **{waiting_for}**..."
                    ),
                    color=discord.Color.blue()
                )
                
                await interaction.response.edit_message(embed=embed, view=self)
        
        return choice_callback

    async def _execute_duel(self, interaction):
        """Ejecuta el duelo de coinflip."""
        self.game_over = True
        
        # Desactivar botones
        for item in self.children:
            item.disabled = True
        
        # Calcular dificultad dinámica para ambos jugadores
        challenger_difficulty, challenger_explanation = DynamicDifficulty.calculate_dynamic_difficulty(
            self.challenger.id, self.apuesta, 'coinflip_duel'
        )
        challenged_difficulty, challenged_explanation = DynamicDifficulty.calculate_dynamic_difficulty(
            self.challenged.id, self.apuesta, 'coinflip_duel'
        )
        
        # En duelos, la probabilidad se basa en la diferencia de dificultades
        difficulty_diff = challenger_difficulty - challenged_difficulty
        
        # Probabilidad base 50/50, ajustada por diferencia de habilidades
        challenger_base_prob = 0.5 + (difficulty_diff * 0.1)  # Máximo ±10% por diferencia
        challenger_base_prob = max(0.35, min(0.65, challenger_base_prob))  # Limitar entre 35% y 65%
        
        # Lanzar la moneda
        resultado_moneda = random.choice(['cara', 'sello'])
        
        # Determinar ganador
        challenger_wins = False
        challenged_wins = False
        
        # Verificar si alguno acertó
        challenger_correct = (self.challenger_choice == resultado_moneda)
        challenged_correct = (self.challenged_choice == resultado_moneda)
        
        if challenger_correct and not challenged_correct:
            # Solo el retador acertó
            challenger_wins = random.random() < challenger_base_prob
        elif challenged_correct and not challenger_correct:
            # Solo el retado acertó
            challenger_wins = random.random() < (1 - challenger_base_prob)
        elif challenger_correct and challenged_correct:
            # Ambos acertaron - usar probabilidad base
            challenger_wins = random.random() < challenger_base_prob
        else:
            # Nadie acertó - usar probabilidad base
            challenger_wins = random.random() < challenger_base_prob
        
        challenged_wins = not challenger_wins
        
        # Procesar resultados
        challenger_balance = get_balance(self.challenger.id)
        challenged_balance = get_balance(self.challenged.id)
        
        if challenger_wins:
            # El retador gana
            winner = self.challenger
            loser = self.challenged
            
            set_balance(self.challenger.id, challenger_balance + self.apuesta)
            set_balance(self.challenged.id, challenged_balance - self.apuesta)
            
            registrar_transaccion(self.challenger.id, self.apuesta, f"Duelo coinflip: ganó vs {self.challenged.display_name}")
            registrar_transaccion(self.challenged.id, -self.apuesta, f"Duelo coinflip: perdió vs {self.challenger.display_name}")
            
            # Registrar para sistema de dificultad
            record_game_result(self.challenger.id, 'coinflip_duel', self.apuesta, 'win', self.apuesta, challenger_difficulty, challenger_balance + self.apuesta)
            record_game_result(self.challenged.id, 'coinflip_duel', self.apuesta, 'loss', 0, challenged_difficulty, challenged_balance - self.apuesta)
            
        else:
            # El retado gana
            winner = self.challenged
            loser = self.challenger
            
            set_balance(self.challenger.id, challenger_balance - self.apuesta)
            set_balance(self.challenged.id, challenged_balance + self.apuesta)
            
            registrar_transaccion(self.challenger.id, -self.apuesta, f"Duelo coinflip: perdió vs {self.challenged.display_name}")
            registrar_transaccion(self.challenged.id, self.apuesta, f"Duelo coinflip: ganó vs {self.challenger.display_name}")
            
            # Registrar para sistema de dificultad
            record_game_result(self.challenger.id, 'coinflip_duel', self.apuesta, 'loss', 0, challenger_difficulty, challenger_balance - self.apuesta)
            record_game_result(self.challenged.id, 'coinflip_duel', self.apuesta, 'win', self.apuesta, challenged_difficulty, challenged_balance + self.apuesta)
        
        # Crear embed de resultado
        embed = discord.Embed(
            title="⚔️ Resultado del Duelo",
            description=(
                f"🪙 **Resultado de la moneda:** {resultado_moneda.upper()}\n\n"
                f"🥊 **{self.challenger.display_name}** eligió: {(self.challenger_choice or 'N/A').upper()} {'✅' if self.challenger_choice == resultado_moneda else '❌'}\n"
                f"🥊 **{self.challenged.display_name}** eligió: {(self.challenged_choice or 'N/A').upper()} {'✅' if self.challenged_choice == resultado_moneda else '❌'}\n\n"
                f"🏆 **GANADOR:** {winner.display_name}\n"
                f"💰 **Premio:** {self.apuesta} monedas\n\n"
                f"💳 **Saldos actuales:**\n"
                f"• {self.challenger.display_name}: {get_balance(self.challenger.id)} monedas\n"
                f"• {self.challenged.display_name}: {get_balance(self.challenged.id)} monedas"
            ),
            color=discord.Color.gold()
        )
        
        # GIF de resultado
        cara_gif = "https://cdn.discordapp.com/attachments/1142907813757198386/1386677290578214932/gif_cara.gif?ex=685a935d&is=685941dd&hm=d41249e840fb753ab064a397836bd37b77616ba50df68a37e17f00287199b958&"
        cruz_gif = "https://cdn.discordapp.com/attachments/1142907813757198386/1386677290179629107/gif_sello.gif?ex=685a935d&is=685941dd&hm=b1b05c3bc3c7791e6a224d2d27861ddfa990a0ddfc24c24cefa0b209bdad3594&"
        embed.set_image(url=cara_gif if resultado_moneda == 'cara' else cruz_gif)
        
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        """Se ejecuta cuando se agota el tiempo."""
        if not self.game_over:
            self.game_over = True
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
        difficulty_modifier, difficulty_explanation = DynamicDifficulty.calculate_dynamic_difficulty(
            user_id, self.apuesta, 'coinflip'
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
        if usuario_tiene_mejora(user_id, 2):  # Apostador Pro
            prob_ganar += 0.03  # Mejora las probabilidades
        if usuario_tiene_mejora(user_id, 3):  # Magnate
            ganancia_bonus += 0.10  # Aumenta la ganancia
        # ---------------------------
        
        # Animación de lanzamiento
        tirada_embed = discord.Embed(
            title="🪙 Lanzando la moneda...",
            description=(
                f"🎯 **Tu elección:** {eleccion.upper()}\n"
                f"💰 **Apuesta:** {self.apuesta} monedas\n"
                f"📊 {difficulty_explanation}\n\n"
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
        # La dificultad influye en el resultado de la moneda, no en una verificación adicional
        probabilidad_cara = 0.5
        
        # Ajustar probabilidad de cara según dificultad
        if eleccion == 'cara':
            probabilidad_cara = 0.5 - (0.3 * (1 - prob_ganar))  # Difícil = menos prob de cara
        else:  # Sello
            probabilidad_cara = 0.5 + (0.3 * (1 - prob_ganar))  # Difícil = más prob de cara
            
        # Resultado final (ajustado entre 0.2 y 0.8)
        probabilidad_cara = max(0.2, min(0.8, probabilidad_cara))
        
        # Determinar el resultado de la moneda según la probabilidad ajustada
        resultado_moneda = 'cara' if random.random() < probabilidad_cara else 'sello'
        
        # El usuario gana si acertó - sistema simple y directo
        usuario_acerto = (eleccion == resultado_moneda)
        gano_final = usuario_acerto
        
        # GIFs de resultado
        cara_gif = "https://cdn.discordapp.com/attachments/1142907813757198386/1386677290578214932/gif_cara.gif?ex=685a935d&is=685941dd&hm=d41249e840fb753ab064a397836bd37b77616ba50df68a37e17f00287199b958&"
        cruz_gif = "https://cdn.discordapp.com/attachments/1142907813757198386/1386677290179629107/gif_sello.gif?ex=685a935d&is=685941dd&hm=b1b05c3bc3c7791e6a224d2d27861ddfa990a0ddfc24c24cefa0b209bdad3594&"
        
        if gano_final:
            # Usuario ganó
            ganancia = int(self.apuesta * ganancia_bonus)
            nuevo_saldo = self.saldo + ganancia
            set_balance(user_id, nuevo_saldo)
            registrar_transaccion(user_id, ganancia, f"Coinflip: ganó con {eleccion}")
            
            # Registrar resultado para el sistema de dificultad
            record_game_result(user_id, 'coinflip', self.apuesta, 'win', ganancia, difficulty_modifier, nuevo_saldo)
            
            embed = discord.Embed(
                title="🎉 ¡GANASTE!",
                description=(
                    f"🪙 **Resultado:** {resultado_moneda.upper()}\n"
                    f"🎯 **Tu elección:** {eleccion.upper()}\n"
                    f"✅ **¡Acertaste!**\n\n"
                    f"💰 **Ganancia:** +{ganancia} monedas\n"
                    f"💳 **Saldo actual:** {get_balance(user_id)} monedas\n\n"
                    f"📊 {difficulty_explanation}"
                ),
                color=discord.Color.green()
            )
            embed.set_image(url=cara_gif if resultado_moneda == 'cara' else cruz_gif)
        else:
            # Usuario perdió
            nuevo_saldo = self.saldo - self.apuesta
            set_balance(user_id, nuevo_saldo)
            registrar_transaccion(user_id, -self.apuesta, f"Coinflip: perdió con {eleccion}")
            
            # Registrar resultado para el sistema de dificultad
            record_game_result(user_id, 'coinflip', self.apuesta, 'loss', 0, difficulty_modifier, nuevo_saldo)
            
            # El usuario sólo pierde cuando no acierta
            razon = "No acertaste el resultado"
            
            embed = discord.Embed(
                title="😞 Perdiste",
                description=(
                    f"🪙 **Resultado:** {resultado_moneda.upper()}\n"
                    f"🎯 **Tu elección:** {eleccion.upper()}\n"
                    f"❌ **{razon}**\n\n"
                    f"💸 **Pérdida:** -{self.apuesta} monedas\n"
                    f"💳 **Saldo actual:** {get_balance(user_id)} monedas\n\n"
                    f"📊 {difficulty_explanation}"
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
        ensure_user(user_id, user_name)  # Asegura registro y datos del usuario
        saldo = get_balance(user_id)
        
        if saldo <= 0:
            await interaction.response.send_message("❌ No tienes saldo suficiente para apostar.", ephemeral=True)
            return
            
        if apuesta <= 0:
            await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return
            
        if apuesta > saldo:
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
            ensure_user(retar.id, retar.name)
            challenged_balance = get_balance(retar.id)
            
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
