import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from typing import List

from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, registrar_transaccion, record_game_result
from src.commands.economy.pets import process_post_game_events
from src.utils.dynamic_difficulty import DynamicDifficulty
from src.utils.cooldowns import CASINO_COOLDOWN

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
        
        if self.is_bomb:
            view.game_over = True
            self.style = discord.ButtonStyle.danger
            self.emoji = "💣"
            self.label = ""
            await interaction.response.defer()
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

        if view.game_over:
            await interaction.response.send_message("Esta partida ya terminó.", ephemeral=True)
            return
            
        if view.diamonds_found == 0:
            await interaction.response.send_message("Debes revelar al menos una gema antes de retirarte.", ephemeral=True)
            return

        view.game_over = True
        await interaction.response.defer()
        await view.process_win(interaction)

class MinesView(discord.ui.View):
    def __init__(self, user_id: int, bet: int, bombs: int, difficulty_modifier: float, balance: int, client: discord.Client = None, channel: discord.abc.Messageable = None):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.bet = bet
        self.bombs = bombs
        self.difficulty_modifier = difficulty_modifier
        self.balance = balance
        self.client = client
        self.channel = channel
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
            
            user_obj = None
            if self.channel and hasattr(self.channel, 'guild') and self.channel.guild:
                user_obj = self.channel.guild.get_member(self.user_id)
            if not user_obj and self.client:
                user_obj = self.client.get_user(self.user_id)

            if self.client and self.channel and user_obj:
                class DummyInteraction:
                    def __init__(self, client, channel, user):
                        self.client = client
                        self.channel = channel
                        self.user = user

                dummy_inter = DummyInteraction(self.client, self.channel, user_obj)
                try:
                    await process_post_game_events(dummy_inter, self.user_id, 'mines', self.bet, 0)
                except Exception:
                    pass

            try:
                if hasattr(self, 'message') and self.message:
                    embed = self.message.embeds[0]
                    embed.color = discord.Color.dark_red()
                    embed.title = "💥 Mines - ¡Se acabó el tiempo!"
                    embed.description = f"Tardaste demasiado en jugar y la mina explotó.\nPerdiste **{self.bet}** monedas.\nNuevo saldo: **{nuevo_saldo}**"
                    await self.message.edit(embed=embed, view=self)
            except:
                pass

    async def update_game(self, interaction: discord.Interaction):
        # Ajustar house edge según la dificultad (dificultad positiva aumenta house edge, negativa lo reduce)
        house_edge = 0.05 + (self.difficulty_modifier * 0.04)
        house_edge = max(0.01, min(0.15, house_edge))
        
        current_multiplier = calculate_multiplier(self.bombs, self.total_cells, self.diamonds_found, house_edge)
        next_multiplier = calculate_multiplier(self.bombs, self.total_cells, self.diamonds_found + 1, house_edge)
        
        current_win = int(self.bet * current_multiplier)
        
        # Check if won game (all diamonds found)
        if self.diamonds_found == (self.total_cells - self.bombs):
            if not self.game_over:
                self.game_over = True
                await interaction.response.defer()
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
                
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def process_loss(self, interaction: discord.Interaction):
        self.game_over = True
        self.reveal_all()
        
        nuevo_saldo = self.balance
        await asyncio.to_thread(registrar_transaccion, self.user_id, -self.bet, f"Mines: Perdida ({self.bombs} bombas)")
        await asyncio.to_thread(record_game_result, self.user_id, 'mines', self.bet, 'loss', 0, self.difficulty_modifier, nuevo_saldo)
        try:
            await process_post_game_events(interaction, self.user_id, 'mines', self.bet, 0)
        except Exception:
            raise

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
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
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
        
        # Ajustar house edge según la dificultad
        house_edge = 0.05 + (self.difficulty_modifier * 0.04)
        house_edge = max(0.01, min(0.15, house_edge))
        
        multiplier = calculate_multiplier(self.bombs, self.total_cells, self.diamonds_found, house_edge)
        winnings = int(self.bet * multiplier)
        profit = winnings - self.bet
        
        nuevo_saldo = self.balance + winnings
        await asyncio.to_thread(add_balance, self.user_id, winnings)
        await asyncio.to_thread(registrar_transaccion, self.user_id, profit, f"Mines: Retiro x{multiplier:.2f} ({self.bombs} bombas)")
        await asyncio.to_thread(record_game_result, self.user_id, 'mines', self.bet, 'win', profit, self.difficulty_modifier, nuevo_saldo)
        try:
            await process_post_game_events(interaction, self.user_id, 'mines', self.bet, profit)
        except Exception:
            raise

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
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

class MinesSetupView(discord.ui.View):
    def __init__(self, user_id: int, apuesta: int, user_name: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.apuesta = apuesta
        self.user_name = user_name
        self.bombas = 3
        
        options = []
        for i in range(1, 20):
            mult = calculate_multiplier(i, 20, 1)
            options.append(discord.SelectOption(label=f"{i} Bombas", description=f"Primer multiplicador: x{mult:.2f}", value=str(i), default=(i==3)))
            
        self.select_bombas = discord.ui.Select(placeholder="Selecciona la cantidad de bombas...", options=options)
        self.select_bombas.callback = self.select_callback
        self.add_item(self.select_bombas)
        
        self.btn_start = discord.ui.Button(label="Comenzar Juego", style=discord.ButtonStyle.success)
        self.btn_start.callback = self.start_callback
        self.add_item(self.btn_start)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta no es tu partida.", ephemeral=True)
            return
            
        self.bombas = int(self.select_bombas.values[0])
        for opt in self.select_bombas.options:
            opt.default = (opt.value == str(self.bombas))
            
        mult = calculate_multiplier(self.bombas, 20, 1)
        embed = interaction.message.embeds[0]
        embed.description = (
            f"💰 Apuesta: **{self.apuesta}**\n"
            f"💣 Bombas seleccionadas: **{self.bombas}**\n\n"
            f"Multiplicador al primer acierto: **x{mult:.2f}**\n"
            "A mayor cantidad de bombas, mayor el riesgo y las ganancias."
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def start_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta no es tu partida.", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        await asyncio.to_thread(ensure_user, self.user_id, self.user_name)
        success, saldo_usuario = await asyncio.to_thread(deduct_balance, self.user_id, self.apuesta)
        if not success:
            await interaction.followup.send("❌ No tienes suficiente saldo para esa apuesta.", ephemeral=True)
            return
            
        difficulty_modifier, explanation = await asyncio.to_thread(
            DynamicDifficulty.calculate_dynamic_difficulty, self.user_id, self.apuesta, 'mines'
        )

        view = MinesView(self.user_id, self.apuesta, self.bombas, difficulty_modifier, saldo_usuario, client=interaction.client, channel=interaction.channel)
        
        embed = discord.Embed(
            title="💣 Buscaminas",
            description=(
                f"💰 Apuesta: **{self.apuesta}**\n"
                f"💣 Bombas: **{self.bombas}**\n"
                f"💎 Gemas: **0 / {20 - self.bombas}**\n\n"
                f"Multiplicador actual: **x1.00**\n"
                f"Próximo multiplicador: **x{calculate_multiplier(self.bombas, 20, 1):.2f}**"
            ),
            color=discord.Color.blue()
        )
        
        view.message = await interaction.edit_original_response(embed=embed, view=view)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except:
            raise

class Mines(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mines", description="Juega al Buscaminas. Encuentra diamantes y evita las bombas.")
    @app_commands.describe(
        apuesta="Cantidad a apostar"
    )
    @CASINO_COOLDOWN
    async def mines(self, interaction: discord.Interaction, apuesta: int):
        user_id = interaction.user.id
        user_name = interaction.user.name
        
        if apuesta <= 0:
            await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        view = MinesSetupView(user_id, apuesta, user_name)
        
        embed = discord.Embed(
            title="💣 Configuración de Buscaminas",
            description=(
                f"💰 Apuesta: **{apuesta}**\n"
                f"💣 Bombas seleccionadas: **3**\n\n"
                f"Multiplicador al primer acierto: **x{calculate_multiplier(3, 20, 1):.2f}**\n"
                "A mayor cantidad de bombas, mayor el riesgo y las ganancias."
            ),
            color=discord.Color.blue()
        )
        
        view.message = await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Mines(bot))
    print("Mines cog cargado con éxito.")
