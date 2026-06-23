import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, registrar_transaccion, record_game_result
from src.utils.dynamic_difficulty import DynamicDifficulty

suits = ["♠", "♥", "♦", "♣"]
ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
values = {"A": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10}

def draw_card(deck):
    card = random.choice(deck)
    deck.remove(card)
    return card

def hand_value(hand):
    value = sum(values[card[:-1]] for card in hand)
    aces = sum(1 for card in hand if card[:-1] == "A")
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value

class BlackjackView(discord.ui.View):
    def __init__(self, user, apuesta, saldo, deck, player_hand, dealer_hand, difficulty_modifier=0.0, difficulty_explanation=""):
        super().__init__(timeout=60)
        self.user = user
        self.apuesta = apuesta
        self.saldo = saldo
        self.deck = deck
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.difficulty_modifier = difficulty_modifier
        self.difficulty_explanation = difficulty_explanation
        self.game_over = False

    @discord.ui.button(label="🃏 Pedir Carta", style=discord.ButtonStyle.primary)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
        
        # Pedir carta con ajuste de suerte (redraw)
        new_card = draw_card(self.deck)
        temp_val = hand_value(self.player_hand + [new_card])
        
        if self.difficulty_modifier > 0 and temp_val in [20, 21]:
            if random.random() < (self.difficulty_modifier * 0.4):
                self.deck.append(new_card)
                random.shuffle(self.deck)
                new_card = draw_card(self.deck)
        elif self.difficulty_modifier < 0 and temp_val > 21:
            if random.random() < (abs(self.difficulty_modifier) * 0.4):
                self.deck.append(new_card)
                random.shuffle(self.deck)
                new_card = draw_card(self.deck)
                
        self.player_hand.append(new_card)
        player_value = hand_value(self.player_hand)
        dealer_visible = hand_value([self.dealer_hand[0]])
        
        embed = discord.Embed(title="🃏 Blackjack - Nueva Carta", color=discord.Color.blue())
        embed.add_field(name="💁 Tus cartas", value=f"{' '.join(self.player_hand)} \n**Valor: {player_value}**", inline=False)
        embed.add_field(name="🤖 Dealer", value=f"{self.dealer_hand[0]} 🎴 \n**Visible: {dealer_visible}**", inline=False)
        embed.add_field(name="💰 Apuesta", value=f"{self.apuesta} monedas", inline=True)
        
        if player_value > 21:
            # Jugador se pasa
            self.game_over = True
            await self._finish_game(interaction, embed, "bust")
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🛑 Plantarse", style=discord.ButtonStyle.secondary)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
        
        self.game_over = True
        await self._finish_game(interaction, None, "stand")

    async def _finish_game(self, interaction, embed_in_progress, action):
        """Finaliza el juego y calcula resultados."""
        user_id = self.user.id
        player_value = hand_value(self.player_hand)
        
        if action == "bust":
            # Jugador se pasó
            nuevo_saldo = self.saldo
            await asyncio.to_thread(registrar_transaccion, user_id, -self.apuesta, "Blackjack: se pasó de 21")
            await asyncio.to_thread(record_game_result, user_id, 'blackjack', self.apuesta, 'loss', 0, self.difficulty_modifier, nuevo_saldo)
            
            embed_in_progress.add_field(name="💥 ¡Te pasaste!", value=f"❌ Perdiste **{self.apuesta}** monedas", inline=False)
            embed_in_progress.color = discord.Color.red()
            embed_in_progress.add_field(name="💳 Saldo actual", value=f"{nuevo_saldo} monedas", inline=False)
            
            # Desactivar botones
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
            
            await interaction.response.edit_message(embed=embed_in_progress, view=self)
            self.stop()
            return
        
        # Jugar la mano del dealer con ajuste de suerte (redraw)
        dealer_value = hand_value(self.dealer_hand)
        while dealer_value < 17:
            new_card = draw_card(self.deck)
            temp_val = hand_value(self.dealer_hand + [new_card])
            
            if self.difficulty_modifier > 0 and temp_val > 21:
                # Evitar que el dealer se pase si la dificultad es alta
                if random.random() < (self.difficulty_modifier * 0.4):
                    self.deck.append(new_card)
                    random.shuffle(self.deck)
                    new_card = draw_card(self.deck)
            elif self.difficulty_modifier < 0 and temp_val in [20, 21]:
                # Evitar que el dealer saque una mano perfecta si la dificultad es baja
                if random.random() < (abs(self.difficulty_modifier) * 0.4):
                    self.deck.append(new_card)
                    random.shuffle(self.deck)
                    new_card = draw_card(self.deck)
                    
            self.dealer_hand.append(new_card)
            dealer_value = hand_value(self.dealer_hand)
        
        # Crear embed del resultado final
        embed = discord.Embed(title="🃏 Blackjack - Resultado Final", color=discord.Color.blue())
        embed.add_field(name="💁 Tus cartas", value=f"{' '.join(self.player_hand)} \n**Valor: {player_value}**", inline=False)
        embed.add_field(name="🤖 Cartas del dealer", value=f"{' '.join(self.dealer_hand)} \n**Valor: {dealer_value}**", inline=False)
        
        # --- MEJORAS BLACK MARKET ---
        ganancia_bonus = 1.0
        from src.db import usuario_tiene_mejora
        if await asyncio.to_thread(usuario_tiene_mejora, user_id, 3):  # Magnate
            ganancia_bonus += 0.15
        # ----------------------------
        
        # Determinar resultado
        if dealer_value > 21:
            # Dealer se pasa
            ganancia = int(self.apuesta * ganancia_bonus)
            nuevo_saldo = self.saldo + self.apuesta + ganancia
            await asyncio.to_thread(add_balance, user_id, self.apuesta + ganancia)
            await asyncio.to_thread(registrar_transaccion, user_id, ganancia, "Blackjack: dealer se pasó")
            await asyncio.to_thread(record_game_result, user_id, 'blackjack', self.apuesta, 'win', ganancia, self.difficulty_modifier, nuevo_saldo)
            
            embed.add_field(name="🎉 ¡Ganaste!", value=f"✅ El dealer se pasó\n**+{ganancia}** monedas", inline=False)
            embed.color = discord.Color.green()
        elif player_value > dealer_value:
            # Jugador gana
            ganancia = int(self.apuesta * ganancia_bonus)
            nuevo_saldo = self.saldo + self.apuesta + ganancia
            await asyncio.to_thread(add_balance, user_id, self.apuesta + ganancia)
            await asyncio.to_thread(registrar_transaccion, user_id, ganancia, "Blackjack: ganó al dealer")
            await asyncio.to_thread(record_game_result, user_id, 'blackjack', self.apuesta, 'win', ganancia, self.difficulty_modifier, nuevo_saldo)
            
            embed.add_field(name="🎉 ¡Ganaste!", value=f"✅ Tu mano es mejor\n**+{ganancia}** monedas", inline=False)
            embed.color = discord.Color.green()
        elif player_value < dealer_value:
            # Dealer gana
            nuevo_saldo = self.saldo
            await asyncio.to_thread(registrar_transaccion, user_id, -self.apuesta, "Blackjack: perdió contra dealer")
            await asyncio.to_thread(record_game_result, user_id, 'blackjack', self.apuesta, 'loss', 0, self.difficulty_modifier, nuevo_saldo)
            
            embed.add_field(name="😞 Perdiste", value=f"❌ El dealer tiene mejor mano\n**-{self.apuesta}** monedas", inline=False)
            embed.color = discord.Color.red()
        else:
            # Empate
            nuevo_saldo = self.saldo + self.apuesta
            await asyncio.to_thread(add_balance, user_id, self.apuesta)
            await asyncio.to_thread(record_game_result, user_id, 'blackjack', self.apuesta, 'draw', 0, self.difficulty_modifier, nuevo_saldo)
            
            embed.add_field(name="🤝 ¡Empate!", value="🟰 Misma puntuación\nRecuperas tu apuesta", inline=False)
            embed.color = discord.Color.yellow()
        
        saldo_actual = await asyncio.to_thread(get_balance, user_id)
        embed.add_field(name="💳 Saldo actual", value=f"{saldo_actual:,} monedas", inline=False)
        
        # Desactivar botones
        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        """Se ejecuta cuando se agota el tiempo."""
        if not self.game_over:
            self.game_over = True
            # Desactivar botones
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True

class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="blackjack", description="Juega una partida de blackjack contra la casa")
    @app_commands.describe(apuesta="Cantidad de monedas a apostar")
    async def blackjack(self, interaction: discord.Interaction, apuesta: int):
        user_id = interaction.user.id
        user_name = interaction.user.name
        await asyncio.to_thread(ensure_user, user_id, user_name)
        
        if apuesta <= 0:
            await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return
            
        success, saldo = await asyncio.to_thread(deduct_balance, user_id, apuesta)
        if not success:
            await interaction.response.send_message("❌ No tienes suficiente saldo para esa apuesta.", ephemeral=True)
            return

        # Calcular dificultad dinámica
        difficulty_modifier, difficulty_explanation = await asyncio.to_thread(
            DynamicDifficulty.calculate_dynamic_difficulty, user_id, apuesta, 'blackjack'
        )

        # Crear baraja
        deck = [f"{rank}{suit}" for suit in suits for rank in ranks]
        
        # Repartir cartas iniciales
        player_hand = [draw_card(deck), draw_card(deck)]
        dealer_hand = [draw_card(deck), draw_card(deck)]
        
        # Mostrar estado inicial
        player_value = hand_value(player_hand)
        dealer_visible = hand_value([dealer_hand[0]])
        
        embed = discord.Embed(title="🃏 Blackjack Casino", color=discord.Color.blue())
        embed.add_field(name="💁 Tus cartas", value=f"{' '.join(player_hand)} \n**Valor: {player_value}**", inline=False)
        embed.add_field(name="🤖 Dealer", value=f"{dealer_hand[0]} 🎴 \n**Visible: {dealer_visible}**", inline=False)
        embed.add_field(name="💰 Apuesta", value=f"{apuesta} monedas", inline=True)
        embed.add_field(name="💳 Saldo", value=f"{saldo} monedas", inline=True)
        
        # Verificar blackjack natural
        if player_value == 21:
            dealer_value = hand_value(dealer_hand)
            embed.add_field(name="🤖 Cartas del dealer", value=f"{' '.join(dealer_hand)} \n**Valor: {dealer_value}**", inline=False)
            
            if dealer_value == 21:
                # Empate
                await asyncio.to_thread(record_game_result, user_id, 'blackjack', apuesta, 'draw', 0, difficulty_modifier, saldo)
                embed.add_field(name="🤝 ¡Empate!", value="🟰 Ambos tienen blackjack\nRecuperas tu apuesta", inline=False)
                embed.color = discord.Color.yellow()
            else:
                # Blackjack del jugador
                ganancia_bonus = 1.0
                from src.db import usuario_tiene_mejora
                if await asyncio.to_thread(usuario_tiene_mejora, user_id, 3):  # Magnate
                    ganancia_bonus += 0.15
                    
                ganancia = int(apuesta * 1.5 * ganancia_bonus)
                nuevo_saldo = saldo + apuesta + ganancia
                await asyncio.to_thread(add_balance, user_id, apuesta + ganancia)
                await asyncio.to_thread(registrar_transaccion, user_id, ganancia, "Blackjack: blackjack natural")
                await asyncio.to_thread(record_game_result, user_id, 'blackjack', apuesta, 'win', ganancia, difficulty_modifier, nuevo_saldo)
                
                embed.add_field(name="🎉 ¡BLACKJACK!", value=f"✅ **+{ganancia}** monedas (1.5x)", inline=False)
                embed.color = discord.Color.gold()
                embed.set_field_at(3, name="💳 Saldo actual", value=f"{nuevo_saldo} monedas", inline=True)
            
            await interaction.response.send_message(embed=embed)
            return
        
        # Crear vista con botones pasando el modificador y explicación de dificultad
        view = BlackjackView(interaction.user, apuesta, saldo, deck, player_hand, dealer_hand, difficulty_modifier, difficulty_explanation)
        embed.set_footer(text="Usa los botones para tomar tu decisión • Tiempo límite: 60 segundos")
        
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Blackjack(bot))
    print("Blackjack cog loaded successfully.")
