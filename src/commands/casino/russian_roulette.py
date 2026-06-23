import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from typing import List

from src.db import get_balance, set_balance, ensure_user, registrar_transaccion, record_game_result
from src.utils.dynamic_difficulty import DynamicDifficulty

class RRLobbyView(discord.ui.View):
    def __init__(self, host: discord.Member, bet: int):
        super().__init__(timeout=60)
        self.host = host
        self.bet = bet
        self.players: List[discord.Member] = [host]
        self.started = False
        self.message = None

    @discord.ui.button(label="Unirse al Juego", style=discord.ButtonStyle.primary, emoji="🔫", custom_id="btn_join")
    async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("Ya estás en el juego.", ephemeral=True)
            return
            
        if len(self.players) >= 6:
            await interaction.response.send_message("El juego ya está lleno (máximo 6 jugadores).", ephemeral=True)
            return

        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)
        balance = await asyncio.to_thread(get_balance, user_id)
        
        if balance < self.bet:
            await interaction.response.send_message("No tienes suficiente saldo para entrar.", ephemeral=True)
            return

        self.players.append(interaction.user)
        
        embed = self.message.embeds[0]
        players_text = "\n".join([f"• {p.display_name}" for p in self.players])
        embed.description = f"**Pozo acumulado:** {self.bet * len(self.players)} monedas\n\n**Jugadores ({len(self.players)}/6):**\n{players_text}"
        
        await interaction.response.edit_message(embed=embed)
        
        if len(self.players) == 6:
            await self.start_game()

    @discord.ui.button(label="Comenzar Ya", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_start")
    async def btn_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message("Solo el creador puede iniciar el juego.", ephemeral=True)
            return
            
        if len(self.players) < 2:
            await interaction.response.send_message("Se necesitan al menos 2 jugadores para comenzar.", ephemeral=True)
            return
            
        await self.start_game()

    async def start_game(self):
        self.started = True
        self.clear_items()
        
        embed = self.message.embeds[0]
        embed.title = "🔫 Ruleta Rusa - ¡El juego ha comenzado!"
        embed.color = discord.Color.red()
        
        # Cobrar las entradas
        for p in self.players:
            bal = await asyncio.to_thread(get_balance, p.id)
            await asyncio.to_thread(set_balance, p.id, bal - self.bet)
            await asyncio.to_thread(registrar_transaccion, p.id, -self.bet, "Entrada Ruleta Rusa")
            
        await self.message.edit(embed=embed, view=None)
        
        # Pasar el control a la vista del juego
        game_view = RRGameView(self.players.copy(), self.bet, self.message)
        await game_view.start_turn()

    async def on_timeout(self):
        if not self.started:
            if len(self.players) < 2:
                self.clear_items()
                try:
                    if self.message:
                        embed = self.message.embeds[0]
                        embed.color = discord.Color.dark_grey()
                        embed.description = "El juego fue cancelado porque no se unieron suficientes jugadores."
                        await self.message.edit(embed=embed, view=None)
                except:
                    pass
            else:
                await self.start_game()

class RRGameView(discord.ui.View):
    def __init__(self, players: List[discord.Member], bet: int, message: discord.Message):
        super().__init__(timeout=None)
        self.players = players
        self.initial_players_count = len(players)
        self.bet = bet
        self.message = message
        
        self.current_turn = 0
        self.chamber_slots = 6
        self.bullet_pos = random.randint(1, 6)

    async def start_turn(self):
        if len(self.players) == 1:
            await self.end_game_winner()
            return

        current_player = self.players[self.current_turn]
        
        self.clear_items()
        btn = discord.ui.Button(label="Apretar Gatillo", style=discord.ButtonStyle.danger, emoji="🔫", custom_id="btn_trigger")
        btn.callback = self.pull_trigger
        self.add_item(btn)

        embed = self.message.embeds[0]
        embed.description = (
            f"**Turno de:** {current_player.mention}\n"
            f"**Probabilidad de morir:** 1 en {self.chamber_slots}\n\n"
            f"Tienes 30 segundos para apretar el gatillo..."
        )
        
        await self.message.edit(content=current_player.mention, embed=embed, view=self)

    async def pull_trigger(self, interaction: discord.Interaction):
        current_player = self.players[self.current_turn]
        
        if interaction.user.id != current_player.id:
            await interaction.response.send_message("¡No es tu turno!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Simular suspense
        embed = self.message.embeds[0]
        embed.description = f"**{current_player.display_name}** se pone el arma en la cabeza y aprieta el gatillo..."
        await self.message.edit(embed=embed, view=None)
        
        await asyncio.sleep(2)
        
        # 1 en chamber_slots chance de morir
        is_dead = random.randint(1, self.chamber_slots) == 1
        
        if is_dead:
            embed.color = discord.Color.dark_red()
            embed.description = f"💥 **¡BAM!** {current_player.mention} ha muerto."
            await self.message.edit(embed=embed)
            
            # Jugador pierde (ya se le cobró, solo registrar resultado)
            diff, _ = await asyncio.to_thread(DynamicDifficulty.calculate_dynamic_difficulty, current_player.id, self.bet, 'russian_roulette')
            bal = await asyncio.to_thread(get_balance, current_player.id)
            await asyncio.to_thread(record_game_result, current_player.id, 'russian_roulette', self.bet, 'loss', 0, diff, bal)
            
            self.players.pop(self.current_turn)
            # Recargar y girar cilindro
            self.chamber_slots = 6
            # El turno pasa al siguiente automáticamente porque quitamos a uno de la lista
            if self.current_turn >= len(self.players):
                self.current_turn = 0
                
            await asyncio.sleep(3)
        else:
            embed.color = discord.Color.orange()
            embed.description = f"💨 *Click...* ¡{current_player.display_name} está a salvo!"
            await self.message.edit(embed=embed)
            
            self.chamber_slots -= 1
            self.current_turn = (self.current_turn + 1) % len(self.players)
            await asyncio.sleep(2)
            
        await self.start_turn()

    async def end_game_winner(self):
        winner = self.players[0]
        pozo = self.initial_players_count * self.bet
        profit = pozo - self.bet
        
        diff, _ = await asyncio.to_thread(DynamicDifficulty.calculate_dynamic_difficulty, winner.id, self.bet, 'russian_roulette')
        bal = await asyncio.to_thread(get_balance, winner.id)
        nuevo_saldo = bal + pozo
        
        await asyncio.to_thread(set_balance, winner.id, nuevo_saldo)
        await asyncio.to_thread(registrar_transaccion, winner.id, pozo, f"Ganó Ruleta Rusa (Pozo de {self.initial_players_count} jugadores)")
        await asyncio.to_thread(record_game_result, winner.id, 'russian_roulette', self.bet, 'win', profit, diff, nuevo_saldo)
        
        embed = self.message.embeds[0]
        embed.color = discord.Color.gold()
        embed.title = "🏆 ¡Ruleta Rusa Terminada!"
        embed.description = (
            f"**¡El último sobreviviente es {winner.mention}!**\n\n"
            f"Se lleva el pozo total de **{pozo}** monedas.\n"
            f"Nuevo saldo: **{nuevo_saldo}**"
        )
        await self.message.edit(content=winner.mention, embed=embed, view=None)

class RussianRoulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_lobbies = set() # channel_id

    @app_commands.command(name="russian_roulette", description="Organiza un juego de Ruleta Rusa de Apuestas.")
    @app_commands.describe(entrada="Cantidad de monedas para entrar al juego")
    async def russian_roulette(self, interaction: discord.Interaction, entrada: int):
        channel_id = interaction.channel_id
        if channel_id in self.active_lobbies:
            await interaction.response.send_message("❌ Ya hay un lobby activo en este canal.", ephemeral=True)
            return
            
        if entrada <= 0:
            await interaction.response.send_message("❌ La entrada debe ser mayor a 0.", ephemeral=True)
            return
            
        host = interaction.user
        await asyncio.to_thread(ensure_user, host.id, host.name)
        balance = await asyncio.to_thread(get_balance, host.id)
        
        if balance < entrada:
            await interaction.response.send_message("❌ No tienes suficiente saldo para abrir este juego.", ephemeral=True)
            return

        self.active_lobbies.add(channel_id)
        
        try:
            view = RRLobbyView(host, entrada)
            
            embed = discord.Embed(
                title="🔫 Ruleta Rusa de Apuestas",
                description=f"**Pozo acumulado:** {entrada} monedas\n\n**Jugadores (1/6):**\n• {host.display_name}",
                color=discord.Color.dark_red()
            )
            embed.set_footer(text=f"Entrada: {entrada} monedas | Esperando jugadores...")
            
            await interaction.response.send_message(embed=embed, view=view)
            view.message = await interaction.original_response()
            
            # Wait for timeout to automatically start if not manually started
            await view.wait()
        finally:
            if channel_id in self.active_lobbies:
                self.active_lobbies.remove(channel_id)

async def setup(bot):
    await bot.add_cog(RussianRoulette(bot))
    print("RussianRoulette cog cargado con éxito.")
