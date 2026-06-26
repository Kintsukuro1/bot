import discord
from discord.ext import commands
from discord import app_commands
import random
import uuid
import time
import asyncio
from src.db import get_balance, deduct_balance, add_balance, registrar_transaccion, save_multiplayer_game, get_multiplayer_game, delete_multiplayer_game

# Helpers para el motor
def generate_dice(count):
    return [random.randint(1, 6) for _ in range(count)]

class LiarsDiceGame:
    def __init__(self, game_id, host_id, bet, players=None):
        self.game_id = game_id
        self.host_id = host_id
        self.bet = bet
        self.players = players if players else [] # list of user_ids
        
        self.dice = {} # dict of user_id -> list of ints
        self.turn_index = 0
        self.current_bid = None # {"qty": int, "val": int, "player_id": int}
        self.status = "Lobby" # Lobby, Playing, Finished
        self.pot = 0
        
    def to_dict(self):
        return {
            "game_id": self.game_id,
            "host_id": self.host_id,
            "bet": self.bet,
            "players": self.players,
            "dice": self.dice,
            "turn_index": self.turn_index,
            "current_bid": self.current_bid,
            "status": self.status,
            "pot": self.pot
        }
        
    @classmethod
    def from_dict(cls, data):
        game = cls(data["game_id"], data["host_id"], data["bet"], data["players"])
        game.dice = {int(k): v for k, v in data.get("dice", {}).items()}
        game.turn_index = data.get("turn_index", 0)
        game.current_bid = data.get("current_bid", None)
        game.status = data.get("status", "Lobby")
        game.pot = data.get("pot", 0)
        return game
        
    def start_game(self):
        self.status = "Playing"
        self.pot = len(self.players) * self.bet
        for pid in self.players:
            self.dice[pid] = generate_dice(5)
        self.turn_index = random.randint(0, len(self.players) - 1)
        
    def get_current_player(self):
        return self.players[self.turn_index]
        
    def next_turn(self):
        self.turn_index = (self.turn_index + 1) % len(self.players)
        
    def total_dice(self):
        return sum(len(d) for d in self.dice.values())

class LiarsDiceView(discord.ui.View):
    def __init__(self, game: LiarsDiceGame):
        super().__init__(timeout=120)
        self.game = game
        self.generar_interfaz()
        
    def generar_interfaz(self):
        self.clear_items()
        
        # Botón para ver dados propios (siempre disponible)
        btn_ver = discord.ui.Button(label="Ver Mis Dados", style=discord.ButtonStyle.secondary, emoji="🎲", row=0)
        btn_ver.callback = self.btn_ver_callback
        self.add_item(btn_ver)
        
        # Si alguien hizo una apuesta, se puede dudar
        if self.game.current_bid:
            btn_dudar = discord.ui.Button(label="¡Mentiroso! (Dudar)", style=discord.ButtonStyle.danger, row=0)
            btn_dudar.callback = self.btn_dudar_callback
            self.add_item(btn_dudar)
            
        # Select para la cantidad (1 a total_dados)
        max_dados = self.game.total_dice()
        # Para no exceder los límites de discord select (max 25), lo agrupamos o limitamos
        min_qty = self.game.current_bid["qty"] if self.game.current_bid else 1
        max_rango = min(min_qty + 24, max_dados)
        
        opciones_qty = []
        for i in range(min_qty, max_rango + 1):
            opciones_qty.append(discord.SelectOption(label=f"Cantidad: {i}", value=str(i)))
            
        select_qty = discord.ui.Select(placeholder="1. Selecciona Cantidad...", options=opciones_qty, row=1)
        select_qty.callback = self.select_qty_callback
        
        # Select para el valor (1 al 6)
        opciones_val = []
        for i in range(1, 7):
            opciones_val.append(discord.SelectOption(label=f"Valor: {i}", emoji="🎲", value=str(i)))
            
        select_val = discord.ui.Select(placeholder="2. Selecciona Valor de la Cara...", options=opciones_val, row=2)
        select_val.callback = self.select_val_callback
        
        # Botón para confirmar apuesta
        btn_apostar = discord.ui.Button(label="Subir Apuesta", style=discord.ButtonStyle.primary, row=3)
        btn_apostar.callback = self.btn_apostar_callback
        
        self.add_item(select_qty)
        self.add_item(select_val)
        self.add_item(btn_apostar)
        
        self.select_qty = select_qty
        self.select_val = select_val

    async def select_qty_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.get_current_player():
            await interaction.response.send_message("❌ No es tu turno.", ephemeral=True)
            return
        await interaction.response.defer()

    async def select_val_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.get_current_player():
            await interaction.response.send_message("❌ No es tu turno.", ephemeral=True)
            return
        await interaction.response.defer()

    async def btn_ver_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.game.players:
            await interaction.response.send_message("❌ No estás jugando en esta mesa.", ephemeral=True)
            return
            
        mis_dados = self.game.dice[interaction.user.id]
        mis_dados.sort()
        texto = " ".join([f"**[{d}]**" for d in mis_dados])
        await interaction.response.send_message(f"🎲 **Tus Dados:** {texto}", ephemeral=True)
        
    async def btn_dudar_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.get_current_player():
            await interaction.response.send_message("❌ No es tu turno.", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Resolver la duda
        bid = self.game.current_bid
        val = bid["val"]
        qty = bid["qty"]
        
        # Contar todos los dados en la mesa con ese valor (el 1 es comodín típicamente, pero aquí haremos 1 normal para simplificar)
        total_count = 0
        todos_los_dados = []
        
        for pid, dados in self.game.dice.items():
            count = dados.count(val)
            total_count += count
            texto_dados = " ".join([f"[{d}]" for d in sorted(dados)])
            todos_los_dados.append(f"<@{pid}>: {texto_dados} ({count} de valor {val})")
            
        self.game.status = "Finished"
        
        # Si total_count >= qty, la apuesta era cierta. El que dudó (current_player) pierde.
        # Si total_count < qty, la apuesta era mentira. El que apostó (bid["player_id"]) pierde.
        if total_count >= qty:
            perdedor = interaction.user.id
            ganador = bid["player_id"]
            resultado = f"¡**<@{bid['player_id']}>** dijo la verdad! Había {total_count} dados con el valor {val}. <@{perdedor}> pierde."
        else:
            perdedor = bid["player_id"]
            ganador = interaction.user.id
            resultado = f"¡**<@{bid['player_id']}>** MINTIÓ! Solo había {total_count} dados con el valor {val}. <@{perdedor}> pierde."
            
        # Pago
        # Repartir el pozo entre los ganadores (todos menos el perdedor)
        pago_por_ganador = self.game.pot // (len(self.game.players) - 1)
        
        for pid in self.game.players:
            if pid != perdedor:
                await asyncio.to_thread(add_balance, pid, pago_por_ganador)
                await asyncio.to_thread(registrar_transaccion, pid, pago_por_ganador, "Ganancia Liar's Dice")
                
        await asyncio.to_thread(delete_multiplayer_game, self.game.game_id)
        
        embed = discord.Embed(
            title="🎲 Resolución: ¡Mentiroso!",
            description=f"{resultado}\n\n**Mesa:**\n" + "\n".join(todos_los_dados),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Los ganadores se reparten {self.game.pot} monedas.")
        
        for item in self.children:
            item.disabled = True
            
        await interaction.edit_original_response(embed=embed, view=self)
        self.stop()
        
    async def btn_apostar_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.get_current_player():
            await interaction.response.send_message("❌ No es tu turno.", ephemeral=True)
            return
            
        if not self.select_qty.values or not self.select_val.values:
            await interaction.response.send_message("❌ Debes seleccionar Cantidad y Valor.", ephemeral=True)
            return
            
        new_qty = int(self.select_qty.values[0])
        new_val = int(self.select_val.values[0])
        
        if self.game.current_bid:
            old_qty = self.game.current_bid["qty"]
            old_val = self.game.current_bid["val"]
            
            # Regla: Debe aumentar cantidad, o si es igual cantidad, debe aumentar valor.
            if new_qty < old_qty:
                await interaction.response.send_message("❌ Debes decir una cantidad mayor o igual a la actual.", ephemeral=True)
                return
            if new_qty == old_qty and new_val <= old_val:
                await interaction.response.send_message("❌ Si mantienes la cantidad, debes decir un valor de dado mayor.", ephemeral=True)
                return
                
        # Apuesta válida
        self.game.current_bid = {
            "qty": new_qty,
            "val": new_val,
            "player_id": interaction.user.id
        }
        self.game.next_turn()
        
        await asyncio.to_thread(save_multiplayer_game, self.game.game_id, "liars_dice", self.game.to_dict())
        
        await interaction.response.defer()
        
        self.generar_interfaz()
        embed = generar_embed_juego(self.game)
        await interaction.edit_original_response(embed=embed, view=self)

def generar_embed_juego(game: LiarsDiceGame):
    embed = discord.Embed(
        title="🎲 Dados de Mentiroso",
        description=f"**Apuesta Activa:** " + (f"{game.current_bid['qty']} dados de valor {game.current_bid['val']} (Por <@{game.current_bid['player_id']}>)" if game.current_bid else "Ninguna. ¡Haz la primera apuesta!"),
        color=discord.Color.blue()
    )
    
    lista_jugadores = ""
    for pid in game.players:
        marca = "👉 " if pid == game.get_current_player() else "   "
        lista_jugadores += f"{marca}<@{pid}> ({len(game.dice[pid])} dados)\n"
        
    embed.add_field(name="Turno Actual", value=lista_jugadores, inline=False)
    embed.set_footer(text=f"Total de dados en la mesa: {game.total_dice()} | Pozo: {game.pot}")
    
    return embed

class LobbyView(discord.ui.View):
    def __init__(self, game: LiarsDiceGame):
        super().__init__(timeout=300)
        self.game = game

    @discord.ui.button(label="Unirse a la Mesa", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.game.players:
            await interaction.response.send_message("❌ Ya estás en la mesa.", ephemeral=True)
            return
            
        if len(self.game.players) >= 4:
            await interaction.response.send_message("❌ La mesa está llena.", ephemeral=True)
            return
            
        # Cobrar apuesta
        success, _ = await asyncio.to_thread(deduct_balance, interaction.user.id, self.game.bet)
        if not success:
            await interaction.response.send_message("❌ No tienes suficiente saldo para pagar la entrada.", ephemeral=True)
            return
            
        self.game.players.append(interaction.user.id)
        await asyncio.to_thread(save_multiplayer_game, self.game.game_id, "liars_dice", self.game.to_dict())
        
        await interaction.response.defer()
        
        embed = interaction.message.embeds[0]
        lista = "\n".join([f"- <@{p}>" for p in self.game.players])
        embed.description = f"**Entrada:** {self.game.bet} monedas\n\n**Jugadores ({len(self.game.players)}/4):**\n{lista}"
        await interaction.edit_original_response(embed=embed, view=self)
        
    @discord.ui.button(label="Iniciar Juego", style=discord.ButtonStyle.primary)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Solo el creador puede iniciar el juego.", ephemeral=True)
            return
            
        if len(self.game.players) < 2:
            await interaction.response.send_message("❌ Se necesitan al menos 2 jugadores.", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        self.game.start_game()
        await asyncio.to_thread(save_multiplayer_game, self.game.game_id, "liars_dice", self.game.to_dict())
        
        embed = generar_embed_juego(self.game)
        view = LiarsDiceView(self.game)
        
        await interaction.edit_original_response(embed=embed, view=view)
        self.stop()
        
    async def on_timeout(self):
        if self.game.status == "Lobby":
            # Devolver apuestas a los que entraron
            for pid in self.game.players:
                await asyncio.to_thread(add_balance, pid, self.game.bet)
            await asyncio.to_thread(delete_multiplayer_game, self.game.game_id)
            
            for item in self.children:
                item.disabled = True
            
            try:
                if self.message:
                    await self.message.edit(content="⏳ El lobby expiró y las entradas fueron devueltas.", view=self)
            except:
                pass

class LiarsDiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="liars_dice", description="Abre una mesa de Dados de Mentiroso (Multijugador).")
    @app_commands.describe(apuesta="Cantidad a apostar para entrar a la mesa")
    async def liars_dice_cmd(self, interaction: discord.Interaction, apuesta: int):
        if apuesta <= 0:
            await interaction.response.send_message("❌ Apuesta inválida.", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        success, _ = await asyncio.to_thread(deduct_balance, interaction.user.id, apuesta)
        if not success:
            await interaction.followup.send("❌ No tienes suficiente saldo para crear la mesa.", ephemeral=True)
            return
            
        import uuid
        game_id = str(uuid.uuid4())[:8]
        game = LiarsDiceGame(game_id, interaction.user.id, apuesta, [interaction.user.id])
        await asyncio.to_thread(save_multiplayer_game, game.game_id, "liars_dice", game.to_dict())
        
        embed = discord.Embed(
            title="🎲 Mesa de Dados de Mentiroso",
            description=f"**Entrada:** {apuesta} monedas\n\n**Jugadores (1/4):**\n- <@{interaction.user.id}>",
            color=discord.Color.green()
        )
        
        view = LobbyView(game)
        view.message = await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(LiarsDiceCog(bot))
    print("Liar's Dice command loaded.")
