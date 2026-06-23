import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from typing import Optional, Dict, Any
from src.db import get_balance, set_balance, ensure_user, registrar_transaccion, record_game_result
from src.utils.dynamic_difficulty import DynamicDifficulty

# Cartas y sus valores
CARD_VALUES = {
    'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, 
    '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13
}

async def _prepare_higher_lower_db(user_id, user_name, apuesta):
    await asyncio.to_thread(ensure_user, user_id, user_name)
    saldo = await asyncio.to_thread(get_balance, user_id)
    difficulty_modifier, difficulty_explanation = await asyncio.to_thread(
        DynamicDifficulty.calculate_dynamic_difficulty, user_id, apuesta, 'higher_lower'
    )
    return saldo, difficulty_modifier, difficulty_explanation

CARD_SUITS = ['♠️', '♥️', '♦️', '♣️']
CARD_NAMES = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

class HigherLowerView(discord.ui.View):
    def __init__(self, user, apuesta: int, saldo: int, difficulty_modifier: float, difficulty_explanation: str):
        super().__init__(timeout=60)
        self.user = user
        self.apuesta = apuesta
        self.saldo = saldo
        self.difficulty_modifier = difficulty_modifier
        self.difficulty_explanation = difficulty_explanation
        self.current_card: Optional[Dict[str, Any]] = None
        self.next_card: Optional[Dict[str, Any]] = None
        self.round_number = 1
        self.consecutive_wins = 0
        self.total_multiplier = 1.0
        self.game_over = False
        self.max_rounds = 5
        
        # Generar primera carta
        self._generate_new_card()
    
    def _generate_new_card(self):
        """Genera una nueva carta aleatoria."""
        name = random.choice(CARD_NAMES)
        self.current_card = {
            'name': name,
            'suit': random.choice(CARD_SUITS),
            'value': CARD_VALUES[name]
        }
    
    def _generate_next_card_with_difficulty(self, player_choice: str):
        """
        Genera la siguiente carta aplicando dificultad dinámica (mediante redraw sutil).
        """
        if not self.current_card:
            return
            
        current_value = self.current_card['value']
        
        # 1. Generar carta de forma 100% natural (sin empates)
        while True:
            next_name = random.choice(CARD_NAMES)
            next_value = CARD_VALUES[next_name]
            if next_value != current_value:
                break
        
        # Evaluar si el jugador acertaría con esta carta
        user_correct = False
        if player_choice == 'higher' and next_value > current_value:
            user_correct = True
        elif player_choice == 'lower' and next_value < current_value:
            user_correct = True
            
        # 2. Aplicar redraw sutil según dificultad
        if self.difficulty_modifier > 0 and user_correct:
            # Pequeña probabilidad de volver a barajar si es demasiado suertudo
            penalty_chance = self.difficulty_modifier * 0.4 + (self.round_number - 1) * 0.05
            if random.random() < min(0.6, penalty_chance):
                while True:
                    next_name = random.choice(CARD_NAMES)
                    next_value = CARD_VALUES[next_name]
                    if next_value != current_value:
                        break
        elif self.difficulty_modifier < 0 and not user_correct:
            # Pequeña probabilidad de salvarlo de fallar si es desafortunado
            save_chance = abs(self.difficulty_modifier) * 0.4
            if random.random() < min(0.5, save_chance):
                while True:
                    next_name = random.choice(CARD_NAMES)
                    next_value = CARD_VALUES[next_name]
                    if next_value != current_value:
                        break

        self.next_card = {
            'name': next_name,
            'suit': random.choice(CARD_SUITS),
            'value': next_value
        }
    
    @discord.ui.button(label="📈 MAYOR", style=discord.ButtonStyle.success, emoji="⬆️")
    async def higher_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
        
        await self._process_choice(interaction, "higher")
    
    @discord.ui.button(label="📉 MENOR", style=discord.ButtonStyle.danger, emoji="⬇️")
    async def lower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
        
        await self._process_choice(interaction, "lower")
    
    @discord.ui.button(label="💰 COBRAR", style=discord.ButtonStyle.primary, emoji="💎")
    async def cash_out_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.game_over:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
        
        if self.consecutive_wins == 0:
            await interaction.response.send_message("❌ No tienes ganancias para cobrar.", ephemeral=True)
            return
        
        await self._cash_out(interaction)
    
    async def _process_choice(self, interaction: discord.Interaction, choice: str):
        """Procesa la elección del jugador."""
        if not self.current_card:
            return
            
        # Generar siguiente carta con dificultad
        self._generate_next_card_with_difficulty(choice)
        
        if not self.next_card:
            return
        
        current_value = self.current_card['value']
        next_value = self.next_card['value']
        
        # Determinar si acertó
        correct = False
        if choice == "higher" and next_value > current_value:
            correct = True
        elif choice == "lower" and next_value < current_value:
            correct = True
        elif next_value == current_value:
            # Ya no debería ocurrir, pero por seguridad
            correct = False
        
        # Crear embed de resultado
        choice_emoji = "📈⬆️" if choice == "higher" else "📉⬇️"
        choice_text = "MAYOR" if choice == "higher" else "MENOR"
        
        embed = discord.Embed(
            title="🃏 Higher or Lower - Resultado",
            color=discord.Color.green() if correct else discord.Color.red()
        )
        
        embed.add_field(
            name="🎴 Cartas",
            value=(
                f"**Carta anterior:** {self.current_card['name']}{self.current_card['suit']} (Valor: {current_value})\n"
                f"**Nueva carta:** {self.next_card['name']}{self.next_card['suit']} (Valor: {next_value})\n"
                f"**Tu elección:** {choice_emoji} {choice_text}"
            ),
            inline=False
        )
        
        if correct:
            self.consecutive_wins += 1
            self.round_number += 1
            
            # Calcular multiplicador progresivo
            round_multiplier = 1.0 + (self.consecutive_wins * 0.3)  # 30% más por cada acierto
            self.total_multiplier = round_multiplier
            
            potential_winnings = int(self.apuesta * self.total_multiplier)
            
            embed.add_field(
                name="✅ ¡Correcto!",
                value=(
                    f"🎯 **Ronda:** {self.consecutive_wins}/{self.max_rounds}\n"
                    f"📊 **Multiplicador:** x{self.total_multiplier:.1f}\n"
                    f"💰 **Ganancias potenciales:** {potential_winnings} monedas\n"
                    f"📈 **Siguiente ronda:** x{1.0 + (self.consecutive_wins * 0.3):.1f}"
                ),
                inline=False
            )
            
            # Verificar si llegó al máximo de rondas
            if self.consecutive_wins >= self.max_rounds:
                embed.add_field(
                    name="🏆 ¡MÁXIMO ALCANZADO!",
                    value="Has completado todas las rondas. ¡Cobrando automáticamente!",
                    inline=False
                )
                await interaction.response.edit_message(embed=embed, view=None)
                await asyncio.sleep(2)
                await self._cash_out(interaction, auto_cash=True)
                return
            
            # Actualizar carta actual
            self.current_card = self.next_card
            
            embed.add_field(
                name="🎮 Continuar",
                value="¿La siguiente carta será mayor o menor que la actual?",
                inline=False
            )
            
        else:
            # Perdió
            self.game_over = True
            await self._end_game(interaction, embed, won=False)
            return
        

        embed.set_footer(text=f"Tiempo límite: 60s • Ronda {self.consecutive_wins + 1}")
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def _cash_out(self, interaction: discord.Interaction, auto_cash: bool = False):
        """Cobra las ganancias acumuladas."""
        if self.consecutive_wins == 0:
            return
        
        self.game_over = True
        
        # --- MEJORAS BLACK MARKET ---
        ganancia_bonus = 1.0
        from src.db import usuario_tiene_mejora
        if await asyncio.to_thread(usuario_tiene_mejora, self.user.id, 3):  # Magnate
            ganancia_bonus += 0.15
        # ----------------------------
        
        winnings = int(self.apuesta * self.total_multiplier * ganancia_bonus)
        profit = winnings - self.apuesta
        
        # Actualizar balance
        new_balance = self.saldo - self.apuesta + winnings
        await asyncio.to_thread(set_balance, self.user.id, new_balance)
        await asyncio.to_thread(registrar_transaccion, self.user.id, profit, f"Higher/Lower: {self.consecutive_wins} aciertos consecutivos")
        
        # Registrar resultado para dificultad
        await asyncio.to_thread(record_game_result,
            self.user.id, 'higher_lower', self.apuesta, 'win', 
            profit, self.difficulty_modifier, new_balance
        )
        
        embed = discord.Embed(
            title="💰 Higher or Lower - ¡Cobrado!",
            description=f"{'🏆 ¡Completaste todas las rondas!' if auto_cash else '💎 Has decidido cobrar tus ganancias'}",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="🎯 Resultado Final",
            value=(
                f"🎴 **Rondas completadas:** {self.consecutive_wins}\n"
                f"📊 **Multiplicador final:** x{self.total_multiplier:.1f}\n"
                f"💰 **Apuesta inicial:** {self.apuesta} monedas\n"
                f"💵 **Total cobrado:** {winnings} monedas\n"
                f"📈 **Ganancia neta:** +{profit} monedas"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💳 Nuevo Saldo",
            value=f"{new_balance:,} monedas",
            inline=False
        )
        
        embed.set_footer(text="¡Felicitaciones por tu estrategia!")
        
        # Desactivar botones
        for item in self.children:
            try:
                item.disabled = True
            except AttributeError:
                pass
        
        if auto_cash:
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)
        
        self.stop()
    
    async def _end_game(self, interaction: discord.Interaction, embed: discord.Embed, won: bool):
        """Termina el juego."""
        self.game_over = True
        
        if not won:
            # Perdió - solo pierde la apuesta
            new_balance = self.saldo - self.apuesta
            await asyncio.to_thread(set_balance, self.user.id, new_balance)
            await asyncio.to_thread(registrar_transaccion, self.user.id, -self.apuesta, "Higher/Lower: perdió")
            
            # Registrar resultado para dificultad
            await asyncio.to_thread(record_game_result,
                self.user.id, 'higher_lower', self.apuesta, 'loss', 
                0, self.difficulty_modifier, new_balance
            )
            
            embed.add_field(
                name="❌ ¡Perdiste!",
                value=(
                    f"🎴 **Rondas completadas:** {self.consecutive_wins}\n"
                    f"💰 **Apuesta perdida:** {self.apuesta} monedas\n"
                    f"💳 **Nuevo saldo:** {new_balance:,} monedas"
                ),
                inline=False
            )
            
            if self.consecutive_wins > 0:
                potential_winnings = int(self.apuesta * self.total_multiplier)
                embed.add_field(
                    name="💔 Tan Cerca...",
                    value=f"Podrías haber ganado {potential_winnings} monedas si hubieras cobrado antes.",
                    inline=False
                )
        
        embed.set_footer(text="Gracias por jugar Higher or Lower")
        
        # Desactivar botones
        for item in self.children:
            try:
                item.disabled = True
            except AttributeError:
                pass
        
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()
    
    async def on_timeout(self):
        """Se ejecuta cuando se agota el tiempo."""
        if not self.game_over:
            self.game_over = True
            # Si tiene ganancias acumuladas, las cobra automáticamente
            if self.consecutive_wins > 0:
                # El timeout cobra automáticamente las ganancias
                winnings = int(self.apuesta * self.total_multiplier)
                profit = winnings - self.apuesta
                new_balance = self.saldo - self.apuesta + winnings
                await asyncio.to_thread(set_balance, self.user.id, new_balance)
                await asyncio.to_thread(registrar_transaccion, self.user.id, profit, f"Higher/Lower: timeout con {self.consecutive_wins} aciertos")
                
                await asyncio.to_thread(record_game_result,
                    self.user.id, 'higher_lower', self.apuesta, 'win', 
                    profit, self.difficulty_modifier, new_balance
                )

class HigherLower(commands.Cog):
    """Cog para el juego Higher or Lower."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="higherlow", description="Juega Higher or Lower: predice si la siguiente carta será mayor o menor")
    @app_commands.describe(apuesta="Cantidad de monedas a apostar")
    async def higher_lower_slash(self, interaction: discord.Interaction, apuesta: int):
        await self._higher_lower_game(interaction, apuesta, is_slash=True)

    @commands.command(name="higherlow", help="Juega Higher or Lower: predice si la siguiente carta será mayor o menor. Uso: !higherlow <apuesta>")
    async def higher_lower(self, ctx, apuesta: int):
        await self._higher_lower_game(ctx, apuesta, is_slash=False)

    async def _higher_lower_game(self, ctx_or_interaction, apuesta: int, is_slash: bool = False):
        if is_slash:
            user = ctx_or_interaction.user
            user_id = user.id
            user_name = user.name
        else:
            user = ctx_or_interaction.author
            user_id = user.id
            user_name = user.name

        # Validaciones
        if apuesta <= 0:
            error_msg = "❌ La apuesta debe ser mayor a 0."
            if is_slash:
                await ctx_or_interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await ctx_or_interaction.send(error_msg)
            return

        saldo, difficulty_modifier, difficulty_explanation = await _prepare_higher_lower_db(
            user_id, user_name, apuesta
        )
            
        if apuesta > saldo:
            error_msg = f"❌ No tienes suficiente saldo. Tu saldo: {saldo:,} monedas."
            if is_slash:
                await ctx_or_interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await ctx_or_interaction.send(error_msg)
            return
        
        # Crear vista del juego
        view = HigherLowerView(user, apuesta, saldo, difficulty_modifier, difficulty_explanation)
        
        # Crear embed inicial
        embed = discord.Embed(
            title="🃏 Higher or Lower Casino",
            description=(
                "🎯 **Objetivo:** Predice si la siguiente carta será mayor o menor\n"
                "📈 **Estrategia:** Acumula rondas para multiplicar tus ganancias\n"
                "💰 **Riesgo:** Puedes cobrar en cualquier momento o perder todo"
            ),
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🎴 Carta Actual",
            value=f"**{view.current_card['name'] if view.current_card else 'Error'}{view.current_card['suit'] if view.current_card else ''}** (Valor: {view.current_card['value'] if view.current_card else 0})",
            inline=True
        )
        
        embed.add_field(
            name="💰 Apuesta",
            value=f"{apuesta} monedas",
            inline=True
        )
        
        embed.set_footer(text="Valores: A=1, J=11, Q=12, K=13")
        
        if is_slash:
            await ctx_or_interaction.response.send_message(embed=embed, view=view)
        else:
            await ctx_or_interaction.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(HigherLower(bot))
    print("HigherLower cog loaded successfully.")
