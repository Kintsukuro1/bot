import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, registrar_transaccion, record_game_result
from src.commands.economy.pets import process_post_game_events
from src.utils.dynamic_difficulty import DynamicDifficulty
from src.utils.cooldowns import CASINO_COOLDOWN

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
        self.player_hands = [player_hand]
        self.current_hand_idx = 0
        self.dealer_hand = dealer_hand
        self.difficulty_modifier = difficulty_modifier
        self.difficulty_explanation = difficulty_explanation
        self.game_over = False
        self._payout_done = False
        
        # Ocultar botón Dividir si no aplica
        if len(player_hand) != 2 or player_hand[0][:-1] != player_hand[1][:-1]:
            for child in self.children:
                if getattr(child, "label", "") == "✂️ Dividir":
                    self.remove_item(child)
                    break

    @discord.ui.button(label="✂️ Dividir", style=discord.ButtonStyle.success)
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
            
        await interaction.response.defer()
        from src.db import deduct_balance
        success, nuevo_saldo = await asyncio.to_thread(deduct_balance, self.user.id, self.apuesta)
        if not success:
            await interaction.response.send_message("❌ No tienes suficiente saldo para dividir (requiere apostar de nuevo).", ephemeral=True)
            return
            
        self.saldo = nuevo_saldo
        self.remove_item(button)
        
        # Split hands
        hand1 = [self.player_hands[0][0], draw_card(self.deck)]
        hand2 = [self.player_hands[0][1], draw_card(self.deck)]
        self.player_hands = [hand1, hand2]
        
        await self._update_ui(interaction, "Manos divididas exitosamente.")

    @discord.ui.button(label="🃏 Pedir Carta", style=discord.ButtonStyle.primary)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
            
        await interaction.response.defer()
        # Remover el botón de dividir si piden carta
        for child in self.children:
            if getattr(child, "label", "") == "✂️ Dividir":
                self.remove_item(child)
                break
                
        current_hand = self.player_hands[self.current_hand_idx]
        new_card = draw_card(self.deck)
        temp_val = hand_value(current_hand + [new_card])
        
        # Dificultad dinámica
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
                
        current_hand.append(new_card)
        player_value = hand_value(current_hand)
        
        if player_value > 21:
            if self.current_hand_idx < len(self.player_hands) - 1:
                self.current_hand_idx += 1
                await self._update_ui(interaction, f"💥 La Mano {self.current_hand_idx} se ha pasado de 21.")
            else:
                self.game_over = True
                await self._finish_game(interaction)
        else:
            await self._update_ui(interaction)

    @discord.ui.button(label="🛑 Plantarse", style=discord.ButtonStyle.secondary)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return

        if self.current_hand_idx < len(self.player_hands) - 1:
            await interaction.response.defer()
            self.current_hand_idx += 1
            await self._update_ui(interaction, f"🛑 Te plantaste en la Mano {self.current_hand_idx}.")
        else:
            self.game_over = True
            await interaction.response.defer()
            await self._finish_game(interaction)

    async def _update_ui(self, interaction, custom_msg=None):
        dealer_visible = hand_value([self.dealer_hand[0]])
        title = "🃏 Blackjack Casino"
        if custom_msg:
            title += f" - {custom_msg}"
            
        embed = discord.Embed(title=title, color=discord.Color.blue())
        
        for i, hand in enumerate(self.player_hands):
            val = hand_value(hand)
            name = f"💁 Mano {i+1}" if len(self.player_hands) > 1 else "💁 Tus cartas"
            if i == self.current_hand_idx and not self.game_over:
                name += " 👈 (Turno Actual)"
            embed.add_field(name=name, value=f"{' '.join(hand)} \n**Valor: {val}**", inline=False)
            
        embed.add_field(name="🤖 Dealer", value=f"{self.dealer_hand[0]} 🎴 \n**Visible: {dealer_visible}**", inline=False)
        embed.add_field(name="💰 Apuesta Total", value=f"{self.apuesta * len(self.player_hands)} monedas", inline=True)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def _finish_game(self, interaction):
        if self._payout_done:
            return
        self._payout_done = True

        user_id = self.user.id
        all_busted = all(hand_value(h) > 21 for h in self.player_hands)
        
        if not all_busted:
            dealer_value = hand_value(self.dealer_hand)
            while dealer_value < 17:
                self.dealer_hand.append(draw_card(self.deck))
                dealer_value = hand_value(self.dealer_hand)
        else:
            dealer_value = hand_value(self.dealer_hand)
            
        embed = discord.Embed(title="🃏 Blackjack - Resultado Final", color=discord.Color.blurple())
        embed.add_field(name="🤖 Cartas del dealer", value=f"{' '.join(self.dealer_hand)} \n**Valor: {dealer_value}**", inline=False)
        
        total_ganancia = 0
        total_apostado = self.apuesta * len(self.player_hands)
        
        ganancia_bonus = 1.0
        from src.db import usuario_tiene_mejora
        if await asyncio.to_thread(usuario_tiene_mejora, user_id, 3):
            ganancia_bonus += 0.15
            
        for i, hand in enumerate(self.player_hands):
            player_value = hand_value(hand)
            name = f"💁 Mano {i+1}" if len(self.player_hands) > 1 else "💁 Tu mano"
            
            if player_value > 21:
                embed.add_field(name=f"{name} (💥 Voló)", value=f"{' '.join(hand)} \nValor: {player_value}\n**-{self.apuesta} monedas**", inline=False)
            elif dealer_value > 21 or player_value > dealer_value:
                ganancia = int(self.apuesta * ganancia_bonus)
                total_ganancia += (self.apuesta + ganancia)
                embed.add_field(name=f"{name} (✅ Ganó)", value=f"{' '.join(hand)} \nValor: {player_value}\n**+{ganancia} monedas**", inline=False)
            elif player_value < dealer_value:
                embed.add_field(name=f"{name} (❌ Perdió)", value=f"{' '.join(hand)} \nValor: {player_value}\n**-{self.apuesta} monedas**", inline=False)
            else:
                total_ganancia += self.apuesta
                embed.add_field(name=f"{name} (🤝 Empate)", value=f"{' '.join(hand)} \nValor: {player_value}\n**Empate**", inline=False)
                
        net_profit = total_ganancia - total_apostado
        
        if total_ganancia > 0:
            await asyncio.to_thread(add_balance, user_id, total_ganancia)
            
        saldo_actual = await asyncio.to_thread(get_balance, user_id)
        
        if net_profit > 0:
            result_str = 'win'
            await asyncio.to_thread(registrar_transaccion, user_id, net_profit, "Blackjack: ganancias")
        elif net_profit < 0:
            result_str = 'loss'
            await asyncio.to_thread(registrar_transaccion, user_id, net_profit, "Blackjack: pérdidas")
        else:
            result_str = 'draw'
            
        win_amount = net_profit if net_profit > 0 else 0
        
        await asyncio.to_thread(record_game_result, user_id, 'blackjack', total_apostado, result_str, win_amount, self.difficulty_modifier, saldo_actual)
        try:
            await process_post_game_events(interaction, user_id, 'blackjack', total_apostado, win_amount)
        except Exception:
            raise
            
        embed.add_field(name="💳 Saldo actual", value=f"{saldo_actual:,} monedas", inline=False)
        
        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True
                
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if not self.game_over:
            self.game_over = True
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
            
            # Register the loss since bet was already deducted
            user_id = self.user.id
            try:
                saldo_actual = await asyncio.to_thread(get_balance, user_id)
                await asyncio.to_thread(registrar_transaccion, user_id, -self.apuesta, "Blackjack: timeout (pérdida)")
                await asyncio.to_thread(record_game_result, user_id, 'blackjack', self.apuesta, 'loss', 0, self.difficulty_modifier, saldo_actual)
            except Exception:
                pass

class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="blackjack", description="Juega una partida de blackjack contra la casa")
    @app_commands.describe(apuesta="Cantidad de monedas a apostar")
    @CASINO_COOLDOWN
    async def blackjack(self, interaction: discord.Interaction, apuesta: int):
        await interaction.response.defer()
        user_id = interaction.user.id
        user_name = interaction.user.name
        await asyncio.to_thread(ensure_user, user_id, user_name)
        
        if apuesta <= 0:
            await interaction.followup.send("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return
            
        success, saldo = await asyncio.to_thread(deduct_balance, user_id, apuesta)
        if not success:
            await interaction.followup.send("❌ No tienes suficiente saldo para esa apuesta.", ephemeral=True)
            return

        difficulty_modifier, difficulty_explanation = await asyncio.to_thread(
            DynamicDifficulty.calculate_dynamic_difficulty, user_id, apuesta, 'blackjack'
        )

        deck = [f"{rank}{suit}" for suit in suits for rank in ranks]
        random.shuffle(deck)
        
        player_hand = [draw_card(deck), draw_card(deck)]
        dealer_hand = [draw_card(deck), draw_card(deck)]
        
        player_value = hand_value(player_hand)
        dealer_visible = hand_value([dealer_hand[0]])
        
        embed = discord.Embed(title="🃏 Blackjack Casino", color=discord.Color.blue())
        embed.add_field(name="💁 Tus cartas", value=f"{' '.join(player_hand)} \n**Valor: {player_value}**", inline=False)
        embed.add_field(name="🤖 Dealer", value=f"{dealer_hand[0]} 🎴 \n**Visible: {dealer_visible}**", inline=False)
        embed.add_field(name="💰 Apuesta", value=f"{apuesta} monedas", inline=True)
        embed.add_field(name="💳 Saldo", value=f"{saldo} monedas", inline=True)
        
        if player_value == 21:
            dealer_value = hand_value(dealer_hand)
            embed.add_field(name="🤖 Cartas del dealer", value=f"{' '.join(dealer_hand)} \n**Valor: {dealer_value}**", inline=False)
            
            if dealer_value == 21:
                await asyncio.to_thread(record_game_result, user_id, 'blackjack', apuesta, 'draw', 0, difficulty_modifier, saldo)
                try:
                    await process_post_game_events(interaction, user_id, 'blackjack', apuesta, 0)
                except Exception:
                    pass
                embed.add_field(name="🤝 ¡Empate!", value="🟰 Ambos tienen blackjack\nRecuperas tu apuesta", inline=False)
                embed.color = discord.Color.yellow()
            else:
                ganancia_bonus = 1.0
                from src.db import usuario_tiene_mejora
                if await asyncio.to_thread(usuario_tiene_mejora, user_id, 3):
                    ganancia_bonus += 0.15
                    
                ganancia = int(apuesta * 1.5 * ganancia_bonus)
                nuevo_saldo = saldo + apuesta + ganancia
                await asyncio.to_thread(add_balance, user_id, apuesta + ganancia)
                await asyncio.to_thread(registrar_transaccion, user_id, ganancia, "Blackjack: blackjack natural")
                await asyncio.to_thread(record_game_result, user_id, 'blackjack', apuesta, 'win', ganancia, difficulty_modifier, nuevo_saldo)
                try:
                    await process_post_game_events(interaction, user_id, 'blackjack', apuesta, ganancia)
                except Exception:
                    pass
                
                embed.add_field(name="🎉 ¡BLACKJACK!", value=f"✅ **+{ganancia}** monedas (1.5x)", inline=False)
                embed.color = discord.Color.gold()
                embed.set_field_at(3, name="💳 Saldo actual", value=f"{nuevo_saldo} monedas", inline=True)
            
            await interaction.followup.send(embed=embed)
            return
        
        view = BlackjackView(interaction.user, apuesta, saldo, deck, player_hand, dealer_hand, difficulty_modifier, difficulty_explanation)
        embed.set_footer(text="Usa los botones para tomar tu decisión ⏳ Tiempo límite: 60 segundos")
        
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Blackjack(bot))
    print("Blackjack cog loaded successfully.")
