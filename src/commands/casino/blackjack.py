import discord
from discord.ext import commands
from discord import app_commands
import random
from src.db import get_balance, set_balance, ensure_user, registrar_transaccion

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
    def __init__(self, user, apuesta, saldo, deck, player_hand, dealer_hand):
        super().__init__(timeout=60)
        self.user = user
        self.apuesta = apuesta
        self.saldo = saldo
        self.deck = deck
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.game_over = False

    @discord.ui.button(label="🃏 Pedir Carta", style=discord.ButtonStyle.primary)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
        
        # Pedir carta
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
            set_balance(user_id, self.saldo - self.apuesta)
            registrar_transaccion(user_id, -self.apuesta, "Blackjack: se pasó de 21")
            embed_in_progress.add_field(name="💥 ¡Te pasaste!", value=f"❌ Perdiste **{self.apuesta}** monedas", inline=False)
            embed_in_progress.color = discord.Color.red()
            embed_in_progress.add_field(name="💳 Saldo actual", value=f"{get_balance(user_id)} monedas", inline=False)
            
            # Desactivar botones
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
            
            await interaction.response.edit_message(embed=embed_in_progress, view=self)
            self.stop()
            return
        
        # Jugar la mano del dealer
        dealer_value = hand_value(self.dealer_hand)
        while dealer_value < 17:
            self.dealer_hand.append(draw_card(self.deck))
            dealer_value = hand_value(self.dealer_hand)
        
        # Crear embed del resultado final
        embed = discord.Embed(title="🃏 Blackjack - Resultado Final", color=discord.Color.blue())
        embed.add_field(name="💁 Tus cartas", value=f"{' '.join(self.player_hand)} \n**Valor: {player_value}**", inline=False)
        embed.add_field(name="🤖 Cartas del dealer", value=f"{' '.join(self.dealer_hand)} \n**Valor: {dealer_value}**", inline=False)
        
        # Determinar resultado
        if dealer_value > 21:
            # Dealer se pasa
            ganancia = self.apuesta
            set_balance(user_id, self.saldo + ganancia)
            registrar_transaccion(user_id, ganancia, "Blackjack: dealer se pasó")
            embed.add_field(name="🎉 ¡Ganaste!", value=f"✅ El dealer se pasó\n**+{ganancia}** monedas", inline=False)
            embed.color = discord.Color.green()
        elif player_value > dealer_value:
            # Jugador gana
            ganancia = self.apuesta
            set_balance(user_id, self.saldo + ganancia)
            registrar_transaccion(user_id, ganancia, "Blackjack: ganó al dealer")
            embed.add_field(name="🎉 ¡Ganaste!", value=f"✅ Tu mano es mejor\n**+{ganancia}** monedas", inline=False)
            embed.color = discord.Color.green()
        elif player_value < dealer_value:
            # Dealer gana
            set_balance(user_id, self.saldo - self.apuesta)
            registrar_transaccion(user_id, -self.apuesta, "Blackjack: perdió contra dealer")
            embed.add_field(name="😞 Perdiste", value=f"❌ El dealer tiene mejor mano\n**-{self.apuesta}** monedas", inline=False)
            embed.color = discord.Color.red()
        else:
            # Empate
            embed.add_field(name="🤝 ¡Empate!", value="🟰 Misma puntuación\nRecuperas tu apuesta", inline=False)
            embed.color = discord.Color.yellow()
        
        embed.add_field(name="💳 Saldo actual", value=f"{get_balance(user_id)} monedas", inline=False)
        
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
        ensure_user(user_id, user_name)  # Asegura registro y datos del usuario
        saldo = get_balance(user_id)
        
        if apuesta <= 0:
            await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return
        if apuesta > saldo:
            await interaction.response.send_message("❌ No tienes suficiente saldo para esa apuesta.", ephemeral=True)
            return

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
                embed.add_field(name="🤝 ¡Empate!", value="🟰 Ambos tienen blackjack\nRecuperas tu apuesta", inline=False)
                embed.color = discord.Color.yellow()
            else:
                # Blackjack del jugador
                ganancia = int(apuesta * 1.5)
                set_balance(user_id, saldo + ganancia)
                registrar_transaccion(user_id, ganancia, "Blackjack: blackjack natural")
                embed.add_field(name="🎉 ¡BLACKJACK!", value=f"✅ **+{ganancia}** monedas (1.5x)", inline=False)
                embed.color = discord.Color.gold()
                embed.set_field_at(3, name="💳 Saldo actual", value=f"{get_balance(user_id)} monedas", inline=True)
            
            await interaction.response.send_message(embed=embed)
            return
        
        # Crear vista con botones
        view = BlackjackView(interaction.user, apuesta, saldo, deck, player_hand, dealer_hand)
        embed.set_footer(text="Usa los botones para tomar tu decisión • Tiempo límite: 60 segundos")
        
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Blackjack(bot))
    print("Blackjack cog loaded successfully.")
