import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from src.db import get_balance, deduct_balance, add_balance, ensure_user, registrar_transaccion, record_game_result, get_provably_fair_seeds, advance_provably_fair_nonce
from src.utils.provably_fair import get_uniform_integer

# Definición simple de baraja
SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
# Valores numéricos para comparar (el palo no importa)
RANK_VALUES = {r: i for i, r in enumerate(RANKS)}

def draw_card_pf(user_id: int):
    """Saca una carta usando Provably Fair (0 a 51). Retorna la carta y su valor."""
    seeds = get_provably_fair_seeds(user_id)
    nonce = advance_provably_fair_nonce(user_id)
    
    # Hay 52 cartas
    card_index, _ = get_uniform_integer(seeds["server_seed"], seeds["client_seed"], nonce, 52)
    
    suit = SUITS[card_index // 13]
    rank = RANKS[card_index % 13]
    
    return f"{rank}{suit}", RANK_VALUES[rank], nonce

class WarSettings(discord.ui.Modal, title="Apuesta para Casino War"):
    def __init__(self, view):
        super().__init__()
        self.view = view
        
    monto = discord.ui.TextInput(
        label="Monto a apostar",
        placeholder="Ej: 500",
        required=True,
        max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            apuesta = int(self.monto.value)
            if apuesta <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Monto inválido.", ephemeral=True)
            raise

        saldo = await asyncio.to_thread(get_balance, interaction.user.id)
        if saldo < apuesta:
            await interaction.response.send_message("❌ Saldo insuficiente.", ephemeral=True)
            return

        self.view.apuesta = apuesta
        self.view.configurado = True
        
        await self.view.actualizar_menu(interaction)

class TieDecisionView(discord.ui.View):
    def __init__(self, parent_view, apuesta):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.user_id = parent_view.user_id
        self.apuesta = apuesta
        self.decision = None

    @discord.ui.button(label="🏳️ Rendirse (-50%)", style=discord.ButtonStyle.danger)
    async def surrender(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Solo el creador puede usar esto.", ephemeral=True)
            return
            
        await interaction.response.defer()
        self.decision = "Surrender"
        self.stop()
        
    @discord.ui.button(label="⚔️ Ir a la Guerra (Doblar)", style=discord.ButtonStyle.success)
    async def go_to_war(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Solo el creador puede usar esto.", ephemeral=True)
            return
            
        saldo = await asyncio.to_thread(get_balance, self.user_id)
        if saldo < self.apuesta:
            await interaction.response.send_message("❌ Saldo insuficiente para ir a la Guerra.", ephemeral=True)
            return
            
        await interaction.response.defer()
        self.decision = "War"
        self.stop()
        
    async def on_timeout(self):
        # Si se queda afk, se rinde por defecto
        self.decision = "Surrender"
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except:
            raise

class CasinoWarView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.apuesta = 0
        self.configurado = False
        
    @discord.ui.button(label="⚙️ Configurar Apuesta", style=discord.ButtonStyle.secondary)
    async def config(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Solo el creador puede usar esto.", ephemeral=True)
            return
        await interaction.response.send_modal(WarSettings(self))
        
    @discord.ui.button(label="🃏 Repartir Cartas", style=discord.ButtonStyle.primary)
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Solo el creador puede jugar.", ephemeral=True)
            return
            
        if not self.configurado:
            await interaction.response.send_message("⚠️ Por favor configura tu apuesta primero.", ephemeral=True)
            return
            
        await asyncio.to_thread(ensure_user, self.user_id)

        # Descontar saldo
        success, nuevo_saldo = await asyncio.to_thread(deduct_balance, self.user_id, self.apuesta)
        if not success:
            await interaction.response.send_message("❌ Saldo insuficiente.", ephemeral=True)
            return
            
        self.clear_items()
        
        player_card, player_val, nonce1 = await asyncio.to_thread(draw_card_pf, self.user_id)
        dealer_card, dealer_val, nonce2 = await asyncio.to_thread(draw_card_pf, self.user_id)
        
        embed = discord.Embed(title="⚔️ Casino War", color=discord.Color.blue())
        embed.add_field(name="Tus Cartas", value=f"🃏 **{player_card}**", inline=True)
        embed.add_field(name="Crupier", value=f"🃏 **{dealer_card}**", inline=True)
        
        if player_val > dealer_val:
            profit = self.apuesta
            await asyncio.to_thread(add_balance, self.user_id, self.apuesta * 2)
            await asyncio.to_thread(registrar_transaccion, self.user_id, profit, "Ganancia Casino War")
            saldo_final = nuevo_saldo + self.apuesta * 2
            await asyncio.to_thread(record_game_result, self.user_id, 'casino_war', self.apuesta, 'win', profit, 0.0, saldo_final)
            embed.description = f"**¡GANASTE!** Tu carta es mayor.\nGanancia: {self.apuesta * 2} monedas."
            embed.color = discord.Color.green()
            await interaction.response.edit_message(embed=embed, view=None)
            
        elif player_val < dealer_val:
            await asyncio.to_thread(registrar_transaccion, self.user_id, -self.apuesta, "Pérdida Casino War")
            await asyncio.to_thread(record_game_result, self.user_id, 'casino_war', self.apuesta, 'loss', 0, 0.0, nuevo_saldo)
            embed.description = "**¡PERDISTE!** La banca tiene una carta mayor."
            embed.color = discord.Color.red()
            await interaction.response.edit_message(embed=embed, view=None)
            
        else:
            # EMPATE - Toma de decisión
            embed.description = "¡EMPATE! Elige si rendirte (pierdes la mitad) o ir a la Guerra (apuestas el doble)."
            embed.color = discord.Color.gold()
            
            tie_view = TieDecisionView(self, self.apuesta)
            await interaction.response.edit_message(embed=embed, view=tie_view)
            tie_view.message = interaction.message
            
            await tie_view.wait()
            
            if tie_view.decision == "Surrender":
                devolucion = int(self.apuesta * 0.5)
                await asyncio.to_thread(add_balance, self.user_id, devolucion)
                await asyncio.to_thread(registrar_transaccion, self.user_id, -(self.apuesta - devolucion), "Casino War: Rendición")
                await asyncio.to_thread(record_game_result, self.user_id, 'casino_war', self.apuesta, 'loss', 0, 0.0, nuevo_saldo + devolucion)
                embed.description = f"Te has rendido. Recuperas {devolucion} monedas."
                embed.color = discord.Color.orange()
                await interaction.edit_original_response(embed=embed, view=None)
                
            elif tie_view.decision == "War":
                # Cobrar la otra apuesta
                success, _ = await asyncio.to_thread(deduct_balance, self.user_id, self.apuesta)
                if not success:
                    embed.description = "❌ No tenías saldo para la Guerra. Cancelando y rindiendo la mano automáticamente."
                    devolucion = int(self.apuesta * 0.5)
                    await asyncio.to_thread(add_balance, self.user_id, devolucion)
                    await interaction.edit_original_response(embed=embed, view=None)
                    return
                
                # Quema de cartas (simulada por nonces extra)
                for _ in range(3):
                    await asyncio.to_thread(advance_provably_fair_nonce, self.user_id)
                
                war_player_card, war_player_val, n3 = await asyncio.to_thread(draw_card_pf, self.user_id)
                war_dealer_card, war_dealer_val, n4 = await asyncio.to_thread(draw_card_pf, self.user_id)
                
                embed.add_field(name="Tu Carta (Guerra)", value=f"🃏 **{war_player_card}**", inline=True)
                embed.add_field(name="Crupier (Guerra)", value=f"🃏 **{war_dealer_card}**", inline=True)
                
                if war_player_val >= war_dealer_val:
                    pago = self.apuesta * 3
                    profit = self.apuesta
                    await asyncio.to_thread(add_balance, self.user_id, pago)
                    await asyncio.to_thread(registrar_transaccion, self.user_id, profit, "Ganancia Casino War (Guerra)")
                    saldo_final = await asyncio.to_thread(get_balance, self.user_id)
                    await asyncio.to_thread(record_game_result, self.user_id, 'casino_war', self.apuesta * 2, 'win', profit, 0.0, saldo_final)
                    embed.description = f"**¡GANASTE LA GUERRA!**\nGanancia total: {pago} monedas."
                    embed.color = discord.Color.green()
                else:
                    saldo_final = await asyncio.to_thread(get_balance, self.user_id)
                    await asyncio.to_thread(registrar_transaccion, self.user_id, -(self.apuesta * 2), "Pérdida Casino War (Guerra)")
                    await asyncio.to_thread(record_game_result, self.user_id, 'casino_war', self.apuesta * 2, 'loss', 0, 0.0, saldo_final)
                    embed.description = "**¡PERDISTE LA GUERRA!**"
                    embed.color = discord.Color.red()
                    
                await interaction.edit_original_response(embed=embed, view=None)

    async def actualizar_menu(self, interaction):
        embed = discord.Embed(
            title="⚔️ Casino War",
            description=(
                f"**Apuesta Activa:** {self.apuesta if self.configurado else 'No configurada'}\n\n"
                f"Configura tu apuesta y presiona Repartir para jugar contra la banca."
            ),
            color=discord.Color.blue()
        )
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)
            raise

class CasinoWarCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="casino_war", description="Juega Casino War. Si hay empate, decide si rendirte o ir a la Guerra.")
    async def casino_war_cmd(self, interaction: discord.Interaction):
        view = CasinoWarView(interaction.user.id)
        embed = discord.Embed(
            title="⚔️ Casino War",
            description="Haz clic en Configurar Apuesta para empezar.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(CasinoWarCog(bot))
    print("✅ Casino War command loaded.")
