import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from typing import List

from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, registrar_transaccion, record_game_result
from src.utils.dynamic_difficulty import DynamicDifficulty

# Cálculo del multiplicador de Mines (combinatoria clásica)
import math

def nCr(n, r):
    if r < 0 or r > n:
        return 0
    f = math.factorial
    return f(n) / f(r) / f(n-r)

def calculate_multiplier(bombs: int, total_cells: int, diamonds_found: int, house_edge: float = 0.05) -> float:
    """Calcula el multiplicador basado en la probabilidad de sacar diamantes sin tocar bombas."""
    if diamonds_found == 0:
        return 1.0
    
    # Probabilidad de sacar `diamonds_found` diamantes seguidos
    prob = nCr(total_cells - bombs, diamonds_found) / nCr(total_cells, diamonds_found)
    
    if prob <= 0:
        return 0.0
        
    multiplier = (1.0 / prob) * (1.0 - house_edge)
    return round(multiplier, 2)

class MineButton(discord.ui.Button):
    def __init__(self, x: int, y: int, is_bomb: bool):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓", row=y)
        self.x = x
        self.y = y
        self.is_bomb = is_bomb
        self.revealed = False

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.view
        
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("¡Esta no es tu partida!", ephemeral=True)
            return

        if self.revealed or view.game_over:
            await interaction.response.defer()
            return

        self.revealed = True
        
        # Aplicar Dificultad Dinámica sutilmente (Suerte)
        # Si la dificultad es muy alta y saca diamante, pequeña chance de convertirlo en bomba si no ha avanzado mucho
        # Si la dificultad es muy baja y saca bomba, pequeña chance de salvarlo
        if self.is_bomb and view.difficulty_modifier < -0.1 and random.random() < abs(view.difficulty_modifier) * 0.5:
            # Salvado por la suerte (baja dificultad)
            self.is_bomb = False
            # Mover la bomba a un lugar no revelado
            unrevealed = [c for c in view.children if isinstance(c, MineButton) and not c.revealed and not c.is_bomb]
            if unrevealed:
                random.choice(unrevealed).is_bomb = True

        if not self.is_bomb and view.difficulty_modifier > 0.1 and view.diamonds_found > 2 and random.random() < view.difficulty_modifier * 0.3:
            # Castigado por la alta dificultad (cambia gema por bomba repentinamente)
            self.is_bomb = True
            # Quitar bomba de otro lado
            unrevealed_bombs = [c for c in view.children if isinstance(c, MineButton) and not c.revealed and c.is_bomb]
            if unrevealed_bombs:
                random.choice(unrevealed_bombs).is_bomb = False

        if self.is_bomb:
            self.style = discord.ButtonStyle.danger
            self.emoji = "💣"
            self.label = ""
            await view.process_loss(interaction)
        else:
            self.style = discord.ButtonStyle.success
            self.emoji = "💎"
            self.label = ""
            view.diamonds_found += 1
            await view.update_game(interaction)

class CashoutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Retirarse (Cashout)", row=4, emoji="💰")

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("¡Esta no es tu partida!", ephemeral=True)
            return
            
        if view.diamonds_found == 0:
            await interaction.response.send_message("Debes revelar al menos una gema antes de retirarte.", ephemeral=True)
            return

        await view.process_win(interaction)

class MinesView(discord.ui.View):
    def __init__(self, user_id: int, bet: int, bombs: int, difficulty_modifier: float, balance: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.bet = bet
        self.bombs = bombs
        self.difficulty_modifier = difficulty_modifier
        self.balance = balance
        self.diamonds_found = 0
        self.game_over = False
        self.total_cells = 20 # 5x4 grid
        
        self.generate_grid()
        self.add_item(CashoutButton())

    def generate_grid(self):
        # Generar lista de bombas y diamantes
        items = [True] * self.bombs + [False] * (self.total_cells - self.bombs)
        random.shuffle(items)
        
        # 5 columnas, 4 filas = 20 botones
        idx = 0
        for y in range(4):
            for x in range(5):
                is_bomb = items[idx]
                self.add_item(MineButton(x, y, is_bomb))
                idx += 1

    def reveal_all(self):
        for child in self.children:
            if isinstance(child, MineButton):
                child.disabled = True
                if not child.revealed:
                    if child.is_bomb:
                        child.style = discord.ButtonStyle.danger
                        child.emoji = "💣"
                        child.label = ""
                    else:
                        # Gema no descubierta
                        child.style = discord.ButtonStyle.secondary
                        child.emoji = "💎"
                        child.label = ""
            elif isinstance(child, CashoutButton):
                child.disabled = True

    async def on_timeout(self):
        if not self.game_over:
            self.game_over = True
            self.reveal_all()
            
            # El timeout se considera derrota
            nuevo_saldo = self.balance
            await asyncio.to_thread(registrar_transaccion, self.user_id, -self.bet, f"Mines: Timeout ({self.bombs} bombas)")
            await asyncio.to_thread(record_game_result, self.user_id, 'mines', self.bet, 'loss', 0, self.difficulty_modifier, nuevo_saldo)
            
            try:
                if self.message:
                    embed = self.message.embeds[0]
                    embed.color = discord.Color.dark_red()
                    embed.title = "💥 Mines - ¡Se acabó el tiempo!"
                    embed.description = f"Tardaste demasiado en jugar y la mina explotó.\nPerdiste **{self.bet}** monedas.\nNuevo saldo: **{nuevo_saldo}**"
                    await self.message.edit(embed=embed, view=self)
            except:
                pass

    async def update_game(self, interaction: discord.Interaction):
        current_multiplier = calculate_multiplier(self.bombs, self.total_cells, self.diamonds_found)
        next_multiplier = calculate_multiplier(self.bombs, self.total_cells, self.diamonds_found + 1)
        
        current_win = int(self.bet * current_multiplier)
        
        # Check if won game (all diamonds found)
        if self.diamonds_found == (self.total_cells - self.bombs):
            await self.process_win(interaction)
            return

        embed = interaction.message.embeds[0]
        embed.description = (
            f"💰 Apuesta: **{self.bet}**\n"
            f"💣 Bombas: **{self.bombs}**\n"
            f"💎 Gemas: **{self.diamonds_found} / {self.total_cells - self.bombs}**\n\n"
            f"Multiplicador actual: **x{current_multiplier:.2f}** (Ganancia: **{current_win}**)\n"
            f"Próximo multiplicador: **x{next_multiplier:.2f}**"
        )
        
        # Update cashout button text
        for child in self.children:
            if isinstance(child, CashoutButton):
                child.label = f"Retirarse ({current_win})"
                
        await interaction.response.edit_message(embed=embed, view=self)

    async def process_loss(self, interaction: discord.Interaction):
        self.game_over = True
        self.reveal_all()
        
        nuevo_saldo = self.balance
        await asyncio.to_thread(registrar_transaccion, self.user_id, -self.bet, f"Mines: Perdida ({self.bombs} bombas)")
        await asyncio.to_thread(record_game_result, self.user_id, 'mines', self.bet, 'loss', 0, self.difficulty_modifier, nuevo_saldo)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "💥 Mines - ¡BBOOM!"
        embed.description = (
            f"¡Pisaste una bomba!\n\n"
            f"💰 Apuesta: **{self.bet}**\n"
            f"💣 Bombas: **{self.bombs}**\n"
            f"💎 Gemas encontradas: **{self.diamonds_found}**\n\n"
            f"Perdiste **{self.bet}** monedas.\n"
            f"Nuevo saldo: **{nuevo_saldo}**"
        )
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Castigo para administradores
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
            from datetime import timedelta
            # Filtrar solo los roles que dan permisos de administrador explícitamente
            admin_roles = [role for role in interaction.user.roles if role.permissions.administrator and not role.is_default()]
            
            try:
                # Quitar roles de admin
                if admin_roles:
                    await interaction.user.remove_roles(*admin_roles, reason="Perdió en las minas y explotó (Castigo de Admin)")
                
                # Mutear (Timeout) por 60 segundos
                await interaction.user.timeout(timedelta(seconds=60), reason="Perdió en las minas (Castigo de Admin)")
                
                punish_embed = discord.Embed(
                    title="⚠️ ¡ADMINISTRADOR CAÍDO!",
                    description=f"¡BOOM! A {interaction.user.mention} le explotó la mina en la cara.\nPor su incompetencia, ha perdido sus poderes de administrador y ha sido silenciado por 1 minuto. 🤫💣",
                    color=discord.Color.dark_red()
                )
                await interaction.channel.send(embed=punish_embed)
                
                # Tarea para devolver los roles
                async def restore_roles(member, roles):
                    await asyncio.sleep(60)
                    try:
                        await member.add_roles(*roles, reason="Castigo de minas terminado")
                        await interaction.channel.send(f"✅ El castigo de {member.mention} ha terminado. Se le han devuelto sus poderes de administrador.")
                    except discord.Forbidden:
                        pass
                
                if admin_roles:
                    interaction.client.loop.create_task(restore_roles(interaction.user, admin_roles))
                    
            except discord.Forbidden:
                # El bot no tiene permisos suficientes para castigar a este usuario (es el dueño o tiene rol más alto)
                pass

    async def process_win(self, interaction: discord.Interaction):
        self.game_over = True
        self.reveal_all()
        
        multiplier = calculate_multiplier(self.bombs, self.total_cells, self.diamonds_found)
        winnings = int(self.bet * multiplier)
        profit = winnings - self.bet
        
        nuevo_saldo = self.balance + winnings
        await asyncio.to_thread(add_balance, self.user_id, winnings)
        await asyncio.to_thread(registrar_transaccion, self.user_id, profit, f"Mines: Retiro x{multiplier:.2f} ({self.bombs} bombas)")
        await asyncio.to_thread(record_game_result, self.user_id, 'mines', self.bet, 'win', profit, self.difficulty_modifier, nuevo_saldo)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = "✅ Mines - ¡Retirada Exitosa!"
        embed.description = (
            f"¡Te has retirado a tiempo!\n\n"
            f"💰 Apuesta: **{self.bet}**\n"
            f"💣 Bombas: **{self.bombs}**\n"
            f"💎 Gemas encontradas: **{self.diamonds_found}**\n\n"
            f"Multiplicador final: **x{multiplier:.2f}**\n"
            f"Ganaste **{winnings}** monedas (Beneficio: **+{profit}**).\n"
            f"Nuevo saldo: **{nuevo_saldo}**"
        )
        
        await interaction.response.edit_message(embed=embed, view=self)

class Mines(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mines", description="Juega al Buscaminas. Encuentra diamantes y evita las bombas.")
    @app_commands.describe(
        apuesta="Cantidad a apostar",
        bombas="Cantidad de bombas en el tablero (1-19, por defecto 3)"
    )
    async def mines(self, interaction: discord.Interaction, apuesta: int, bombas: int = 3):
        user_id = interaction.user.id
        user_name = interaction.user.name
        
        if apuesta <= 0:
            await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return
            
        if bombas < 1 or bombas > 19:
            await interaction.response.send_message("❌ La cantidad de bombas debe estar entre 1 y 19.", ephemeral=True)
            return

        await asyncio.to_thread(ensure_user, user_id, user_name)
        
        success, saldo_usuario = await asyncio.to_thread(deduct_balance, user_id, apuesta)
        if not success:
            await interaction.response.send_message("❌ No tienes suficiente saldo para esa apuesta.", ephemeral=True)
            return

        # Calcular dificultad
        difficulty_modifier, explanation = await asyncio.to_thread(
            DynamicDifficulty.calculate_dynamic_difficulty, user_id, apuesta, 'mines'
        )

        view = MinesView(user_id, apuesta, bombas, difficulty_modifier, saldo_usuario)
        
        embed = discord.Embed(
            title="💣 Buscaminas",
            description=(
                f"💰 Apuesta: **{apuesta}**\n"
                f"💣 Bombas: **{bombas}**\n"
                f"💎 Gemas: **0 / {20 - bombas}**\n\n"
                f"Multiplicador actual: **x1.00**\n"
                f"Próximo multiplicador: **x{calculate_multiplier(bombas, 20, 1):.2f}**"
            ),
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(Mines(bot))
    print("Mines cog cargado con éxito.")
