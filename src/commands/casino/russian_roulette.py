import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from typing import List

from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, registrar_transaccion, record_game_result
from src.commands.economy.pets import process_post_game_events
from src.utils.dynamic_difficulty import DynamicDifficulty

class RRLobbyView(discord.ui.View):
    def __init__(self, host: discord.Member, bet: int):
        super().__init__(timeout=60)
        self.host = host
        self.bet = bet
        self.initial_bet = bet
        self.bullets = 1
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
        self.players.append(interaction.user)

        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)
        
        success, balance = await asyncio.to_thread(deduct_balance, user_id, self.bet)
        if not success:
            self.players.remove(interaction.user)
            await interaction.response.send_message("No tienes suficiente saldo para entrar.", ephemeral=True)
            return
        
        embed = self.message.embeds[0]
        players_text = "\n".join([f"• {p.display_name}" for p in self.players])
        bullet_text = f"{self.bullets} balas" if self.bullets > 1 else "1 bala"
        embed.description = (
            f"**Pozo acumulado:** {self.bet * len(self.players)} monedas\n"
            f"**Balas en el cargador:** {bullet_text} 🔴\n\n"
            f"**Jugadores ({len(self.players)}/6):**\n{players_text}"
        )
        
        await interaction.response.edit_message(embed=embed)
        
        if len(self.players) == 6:
            await self.start_game()

    @discord.ui.button(label="Agregar Bala", style=discord.ButtonStyle.secondary, emoji="➕", custom_id="btn_add_bullet")
    async def btn_add_bullet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.bullets >= 6:
            await interaction.response.send_message("El cargador no puede tener más de 6 balas.", ephemeral=True)
            return

        new_bullets = self.bullets + 1
        new_bet = self.initial_bet + int(self.initial_bet * 0.5 * (new_bullets - 1))
        diff = new_bet - self.bet

        # Verificar saldo de todos los jugadores
        cannot_afford = []
        for p in self.players:
            bal = await asyncio.to_thread(get_balance, p.id)
            if bal < diff:
                cannot_afford.append(p.display_name)

        if cannot_afford:
            players_list = ", ".join(cannot_afford)
            await interaction.response.send_message(
                f"No se puede agregar otra bala. Los siguientes jugadores no tienen suficiente saldo para cubrir el aumento de {diff} monedas: {players_list}", 
                ephemeral=True
            )
            return

        # Cobrar la diferencia a cada jugador
        for p in self.players:
            await asyncio.to_thread(deduct_balance, p.id, diff)

        self.bullets = new_bullets
        self.bet = new_bet

        embed = self.message.embeds[0]
        players_text = "\n".join([f"• {p.display_name}" for p in self.players])
        bullet_text = f"{self.bullets} balas" if self.bullets > 1 else "1 bala"
        embed.description = (
            f"**Pozo acumulado:** {self.bet * len(self.players)} monedas\n"
            f"**Balas en el cargador:** {bullet_text} 🔴\n\n"
            f"**Jugadores ({len(self.players)}/6):**\n{players_text}"
        )
        embed.set_footer(text=f"Entrada: {self.bet} monedas | Esperando jugadores...")
        
        await interaction.response.edit_message(embed=embed)

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
        
        # Registrar las entradas (ya cobradas)
        for p in self.players:
            await asyncio.to_thread(registrar_transaccion, p.id, -self.bet, "Entrada Ruleta Rusa")
            
        await self.message.edit(embed=embed, view=None)
        
        # Pasar el control a la vista del juego con el número de balas
        game_view = RRGameView(self.players.copy(), self.bet, self.bullets, self.message)
        await game_view.start_turn()

    async def on_timeout(self):
        if not self.started:
            if len(self.players) < 2:
                for p in self.players:
                    await asyncio.to_thread(add_balance, p.id, self.bet)
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
    def __init__(self, players: List[discord.Member], bet: int, bullets: int, message: discord.Message):
        super().__init__(timeout=None)
        self.players = players
        self.initial_players_count = len(players)
        self.bet = bet
        self.bullets = bullets
        self.initial_bullets = bullets
        self.message = message
        
        self.current_turn = 0
        self.chamber_slots = 6
        self.has_spun_this_turn = False

    async def start_turn(self):
        if len(self.players) == 1:
            await self.end_game_winner()
            return

        current_player = self.players[self.current_turn]
        
        self.clear_items()
        
        btn_self = discord.ui.Button(label="Apretar Gatillo", style=discord.ButtonStyle.danger, emoji="🔫", custom_id="btn_trigger_self")
        btn_self.callback = self.pull_trigger_self
        self.add_item(btn_self)

        btn_other = discord.ui.Button(label="Apuntar a Otro", style=discord.ButtonStyle.secondary, emoji="🎯", custom_id="btn_trigger_other")
        btn_other.callback = self.pull_trigger_other
        self.add_item(btn_other)

        btn_spin = discord.ui.Button(label="Girar Cargador", style=discord.ButtonStyle.primary, emoji="🌀", custom_id="btn_spin", disabled=self.has_spun_this_turn)
        btn_spin.callback = self.spin_cylinder
        self.add_item(btn_spin)

        embed = self.message.embeds[0]
        embed.description = (
            f"**Turno de:** {current_player.mention}\n\n"
            f"Elige una acción abajo. Tienes 30 segundos..."
        )
        
        await self.message.edit(content=current_player.mention, embed=embed, view=self)

    async def spin_cylinder(self, interaction: discord.Interaction):
        current_player = self.players[self.current_turn]
        if interaction.user.id != current_player.id:
            await interaction.response.send_message("¡No es tu turno!", ephemeral=True)
            return

        self.chamber_slots = 6
        self.has_spun_this_turn = True
        
        await interaction.response.defer()
        
        embed = self.message.embeds[0]
        embed.description = f"🌀 **{current_player.display_name}** hace girar el cargador..."
        await self.message.edit(embed=embed, view=None)
        
        await asyncio.sleep(2)
        await self.start_turn()

    async def pull_trigger_self(self, interaction: discord.Interaction):
        await self.process_shot(interaction, aim_at_self=True)

    async def pull_trigger_other(self, interaction: discord.Interaction):
        await self.process_shot(interaction, aim_at_self=False)

    async def process_shot(self, interaction: discord.Interaction, aim_at_self: bool):
        current_player = self.players[self.current_turn]
        
        if interaction.user.id != current_player.id:
            await interaction.response.send_message("¡No es tu turno!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        embed = self.message.embeds[0]
        
        if aim_at_self:
            embed.description = f"🔫 **{current_player.display_name}** se pone el arma en la cabeza y aprieta el gatillo..."
        else:
            other_players = [p for p in self.players if p.id != current_player.id]
            target = random.choice(other_players)
            embed.description = f"🎯 **{current_player.display_name}** apunta con el arma a **{target.display_name}** y aprieta el gatillo..."
            
        await self.message.edit(embed=embed, view=None)
        
        await asyncio.sleep(2)
        
        # Determinar si la bala se dispara
        is_fired = random.randint(1, self.chamber_slots) <= self.bullets
        
        dead_player = None
        message_text = ""
        
        if is_fired:
            if aim_at_self:
                dead_player = current_player
                message_text = f"💥 **¡BAM!** El arma se disparó. {current_player.mention} ha muerto."
            else:
                dead_player = target
                message_text = f"💥 **¡BAM!** El arma se disparó. {current_player.mention} ha matado a {target.mention}."
        else:
            if aim_at_self:
                message_text = "💨 *Click...* Escuchas que el arma hace click."
            else:
                dead_player = current_player
                message_text = f"💨 *Click...* Escuchas que el arma hace click. Al fallar el tiro contra {target.display_name}, la mala suerte se vuelve contra {current_player.mention} y muere."
                
        embed = self.message.embeds[0]
        if dead_player:
            embed.color = discord.Color.dark_red()
            embed.description = message_text
            await self.message.edit(embed=embed)
            
            # Registrar derrota para el jugador que murió
            diff, _ = await asyncio.to_thread(DynamicDifficulty.calculate_dynamic_difficulty, dead_player.id, self.bet, 'russian_roulette')
            bal = await asyncio.to_thread(get_balance, dead_player.id)
            await asyncio.to_thread(record_game_result, dead_player.id, 'russian_roulette', self.bet, 'loss', 0, diff, bal)
            try:
                await process_post_game_events(interaction, dead_player.id, 'russian_roulette', self.bet, 0)
            except Exception:
                pass
                
            # Remover al jugador muerto
            dead_index = self.players.index(dead_player)
            self.players.pop(dead_index)
            
            # Recargar y girar cilindro
            self.chamber_slots = 6
            self.bullets = self.initial_bullets
            self.has_spun_this_turn = False
            
            # Si queda más de un jugador, actualizar el índice del turno del siguiente jugador
            if len(self.players) > 1:
                if dead_player.id != current_player.id:
                    # El tirador sobrevivió. Buscar el nuevo índice del tirador en la lista y pasar al siguiente.
                    shooter_index = next(i for i, p in enumerate(self.players) if p.id == current_player.id)
                    self.current_turn = (shooter_index + 1) % len(self.players)
                else:
                    # El tirador murió. El turno pasa automáticamente al jugador que quedó en el mismo índice.
                    if self.current_turn >= len(self.players):
                        self.current_turn = 0
            
            await asyncio.sleep(3)
        else:
            embed.color = discord.Color.orange()
            embed.description = message_text
            await self.message.edit(embed=embed)
            
            # Reducir recámara disponible, avanzar turno
            self.chamber_slots -= 1
            self.has_spun_this_turn = False
            self.current_turn = (self.current_turn + 1) % len(self.players)
            
            await asyncio.sleep(2)
            
        await self.start_turn()

    async def end_game_winner(self):
        winner = self.players[0]
        pozo = self.initial_players_count * self.bet
        profit = pozo - self.bet
        
        diff, _ = await asyncio.to_thread(DynamicDifficulty.calculate_dynamic_difficulty, winner.id, self.bet, 'russian_roulette')
        await asyncio.to_thread(add_balance, winner.id, pozo)
        nuevo_saldo = await asyncio.to_thread(get_balance, winner.id)
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
        
        success, balance = await asyncio.to_thread(deduct_balance, host.id, entrada)
        if not success:
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
