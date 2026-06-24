import discord
from discord.ext import commands
from discord import app_commands
import asyncio

from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, registrar_transaccion, record_game_result
from src.commands.economy.pets import process_post_game_events
from src.utils.dynamic_difficulty import DynamicDifficulty

CHOICES = {
    "rock": {"name": "Piedra", "emoji": "🪨", "beats": "scissors"},
    "paper": {"name": "Papel", "emoji": "📄", "beats": "rock"},
    "scissors": {"name": "Tijeras", "emoji": "✂️", "beats": "paper"}
}

class RPSChoiceView(discord.ui.View):
    def __init__(self, parent_view, user_type: str):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.user_type = user_type # 'challenger' or 'challenged'

    @discord.ui.button(label="Piedra", emoji="🪨", style=discord.ButtonStyle.secondary)
    async def btn_rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.make_choice(interaction, "rock")

    @discord.ui.button(label="Papel", emoji="📄", style=discord.ButtonStyle.secondary)
    async def btn_paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.make_choice(interaction, "paper")

    @discord.ui.button(label="Tijeras", emoji="✂️", style=discord.ButtonStyle.secondary)
    async def btn_scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.make_choice(interaction, "scissors")

    async def make_choice(self, interaction: discord.Interaction, choice: str):
        if self.user_type == 'challenger':
            self.parent_view.challenger_choice = choice
        else:
            self.parent_view.challenged_choice = choice
            
        await interaction.response.send_message(f"Has elegido {CHOICES[choice]['emoji']} en secreto. Esperando...", ephemeral=True)
        await self.parent_view.check_results()

class RPSMainView(discord.ui.View):
    def __init__(self, challenger: discord.Member, challenged: discord.Member, bet: int):
        super().__init__(timeout=300) # 5 minutos para responder
        self.challenger = challenger
        self.challenged = challenged
        self.bet = bet
        
        self.accepted = False
        self.challenger_choice = None
        self.challenged_choice = None
        self.message = None

    @discord.ui.button(label="Aceptar Reto", style=discord.ButtonStyle.success, emoji="⚔️", custom_id="btn_accept")
    async def btn_accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("¡Este reto no es para ti!", ephemeral=True)
            return
            
        # Verificar saldo del retado
        await asyncio.to_thread(ensure_user, self.challenged.id, self.challenged.name)
        success, balance_challenged = await asyncio.to_thread(deduct_balance, self.challenged.id, self.bet)
        
        if not success:
            await interaction.response.send_message("❌ No tienes suficiente saldo para aceptar esta apuesta.", ephemeral=True)
            return

        self.accepted = True
        
        await asyncio.to_thread(registrar_transaccion, self.challenger.id, -self.bet, f"Apuesta PPT vs {self.challenged.display_name}")
        await asyncio.to_thread(registrar_transaccion, self.challenged.id, -self.bet, f"Apuesta PPT vs {self.challenger.display_name}")

        # Cambiar botones
        self.clear_items()
        
        btn_challenger = discord.ui.Button(label=f"Jugada de {self.challenger.display_name}", style=discord.ButtonStyle.primary, custom_id="btn_play_1")
        btn_challenger.callback = self.play_challenger
        self.add_item(btn_challenger)
        
        btn_challenged = discord.ui.Button(label=f"Jugada de {self.challenged.display_name}", style=discord.ButtonStyle.danger, custom_id="btn_play_2")
        btn_challenged.callback = self.play_challenged
        self.add_item(btn_challenged)

        embed = self.message.embeds[0]
        embed.color = discord.Color.orange()
        embed.description = f"⚔️ **¡Reto Aceptado!** ⚔️\n\nPozo total: **{self.bet * 2}** monedas.\nAmbos jugadores deben elegir su jugada haciendo clic en sus respectivos botones."
        await interaction.response.edit_message(embed=embed, view=self)

    async def play_challenger(self, interaction: discord.Interaction):
        if interaction.user.id != self.challenger.id:
            await interaction.response.send_message("¡Ese no es tu botón!", ephemeral=True)
            return
        if self.challenger_choice:
            await interaction.response.send_message("Ya has elegido tu jugada. Espera a tu oponente.", ephemeral=True)
            return
        await interaction.response.send_message("Elige tu jugada:", view=RPSChoiceView(self, 'challenger'), ephemeral=True)

    async def play_challenged(self, interaction: discord.Interaction):
        if interaction.user.id != self.challenged.id:
            await interaction.response.send_message("¡Ese no es tu botón!", ephemeral=True)
            return
        if self.challenged_choice:
            await interaction.response.send_message("Ya has elegido tu jugada. Espera a tu oponente.", ephemeral=True)
            return
        await interaction.response.send_message("Elige tu jugada:", view=RPSChoiceView(self, 'challenged'), ephemeral=True)

    async def check_results(self):
        if not self.challenger_choice or not self.challenged_choice:
            return

        self.clear_items()
        embed = self.message.embeds[0]
        
        ch_c = self.challenger_choice
        cd_c = self.challenged_choice
        
        embed.description = (
            f"**{self.challenger.display_name}** eligió: {CHOICES[ch_c]['emoji']} {CHOICES[ch_c]['name']}\n"
            f"**{self.challenged.display_name}** eligió: {CHOICES[cd_c]['emoji']} {CHOICES[cd_c]['name']}\n\n"
        )
        
        pozo = self.bet * 2
        
        # Calcular dificultad para registrar (el modificador no afecta este PvP puro)
        diff_1, _ = await asyncio.to_thread(DynamicDifficulty.calculate_dynamic_difficulty, self.challenger.id, self.bet, 'rps')
        diff_2, _ = await asyncio.to_thread(DynamicDifficulty.calculate_dynamic_difficulty, self.challenged.id, self.bet, 'rps')
        
        bal_1 = await asyncio.to_thread(get_balance, self.challenger.id)
        bal_2 = await asyncio.to_thread(get_balance, self.challenged.id)

        if ch_c == cd_c:
            # Empate, devolver dinero
            await asyncio.to_thread(add_balance, self.challenger.id, self.bet)
            await asyncio.to_thread(add_balance, self.challenged.id, self.bet)
            
            await asyncio.to_thread(registrar_transaccion, self.challenger.id, self.bet, "Empate PPT (Devolución)")
            await asyncio.to_thread(registrar_transaccion, self.challenged.id, self.bet, "Empate PPT (Devolución)")
            
            await asyncio.to_thread(record_game_result, self.challenger.id, 'rps', self.bet, 'tie', 0, diff_1, bal_1 + self.bet)
            try:
                await process_post_game_events(interaction, self.challenger.id, 'rps', self.bet, 0)
            except Exception:
                pass
            await asyncio.to_thread(record_game_result, self.challenged.id, 'rps', self.bet, 'tie', 0, diff_2, bal_2 + self.bet)
            try:
                await process_post_game_events(interaction, self.challenged.id, 'rps', self.bet, 0)
            except Exception:
                pass

            embed.title = "🤝 ¡Empate!"
            embed.color = discord.Color.light_grey()
            embed.description += "Ambos reciben su apuesta de vuelta."
            
        elif CHOICES[ch_c]['beats'] == cd_c:
            # Gana retador
            await asyncio.to_thread(add_balance, self.challenger.id, pozo)
            await asyncio.to_thread(registrar_transaccion, self.challenger.id, pozo, f"Ganó PPT vs {self.challenged.display_name}")
            
            await asyncio.to_thread(record_game_result, self.challenger.id, 'rps', self.bet, 'win', self.bet, diff_1, bal_1 + pozo)
            try:
                await process_post_game_events(interaction, self.challenger.id, 'rps', self.bet, self.bet)
            except Exception:
                pass
            await asyncio.to_thread(record_game_result, self.challenged.id, 'rps', self.bet, 'loss', 0, diff_2, bal_2)
            try:
                await process_post_game_events(interaction, self.challenged.id, 'rps', self.bet, 0)
            except Exception:
                pass

            embed.title = f"👑 ¡{self.challenger.display_name} gana!"
            embed.color = discord.Color.green()
            embed.description += f"**{self.challenger.display_name}** se lleva el pozo de **{pozo}** monedas."
            
        else:
            # Gana retado
            await asyncio.to_thread(add_balance, self.challenged.id, pozo)
            await asyncio.to_thread(registrar_transaccion, self.challenged.id, pozo, f"Ganó PPT vs {self.challenger.display_name}")
            
            await asyncio.to_thread(record_game_result, self.challenger.id, 'rps', self.bet, 'loss', 0, diff_1, bal_1)
            try:
                await process_post_game_events(interaction, self.challenger.id, 'rps', self.bet, 0)
            except Exception:
                pass
            await asyncio.to_thread(record_game_result, self.challenged.id, 'rps', self.bet, 'win', self.bet, diff_2, bal_2 + pozo)
            try:
                await process_post_game_events(interaction, self.challenged.id, 'rps', self.bet, self.bet)
            except Exception:
                pass

            embed.title = f"👑 ¡{self.challenged.display_name} gana!"
            embed.color = discord.Color.green()
            embed.description += f"**{self.challenged.display_name}** se lleva el pozo de **{pozo}** monedas."

        try:
            await self.message.edit(embed=embed, view=None)
        except:
            raise

    async def on_timeout(self):
        self.clear_items()
        try:
            if self.message:
                embed = self.message.embeds[0]
                embed.color = discord.Color.dark_grey()
                if not self.accepted:
                    await asyncio.to_thread(add_balance, self.challenger.id, self.bet)
                    embed.description = "El reto expiró porque no fue aceptado a tiempo."
                else:
                    embed.description = "El reto fue cancelado porque alguien no eligió su jugada a tiempo.\nSe ha devuelto el dinero a ambos."
                    
                    # Devolver dinero a ambos
                    await asyncio.to_thread(add_balance, self.challenger.id, self.bet)
                    await asyncio.to_thread(add_balance, self.challenged.id, self.bet)
                    
                await self.message.edit(embed=embed, view=None)
        except:
            raise

class RPSBet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rps_bet", description="Reta a otro usuario a un duelo de Piedra, Papel o Tijera por dinero.")
    @app_commands.describe(
        oponente="Usuario al que quieres retar",
        apuesta="Cantidad de monedas a apostar"
    )
    async def rps_bet(self, interaction: discord.Interaction, oponente: discord.Member, apuesta: int):
        retador = interaction.user
        
        if oponente.id == retador.id:
            await interaction.response.send_message("❌ No puedes retarte a ti mismo.", ephemeral=True)
            return
            
        if oponente.bot:
            await interaction.response.send_message("❌ No puedes retar a un bot.", ephemeral=True)
            return
            
        if apuesta <= 0:
            await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return

        await asyncio.to_thread(ensure_user, retador.id, retador.name)
        
        success, saldo_retador = await asyncio.to_thread(deduct_balance, retador.id, apuesta)
        if not success:
            await interaction.response.send_message("❌ No tienes suficiente saldo para esta apuesta.", ephemeral=True)
            return

        view = RPSMainView(retador, oponente, apuesta)
        
        embed = discord.Embed(
            title="⚔️ Duelo: Piedra, Papel, Tijera",
            description=f"{oponente.mention}, ¡has sido retado por {retador.mention}!\n\n💰 **Apuesta:** {apuesta} monedas.\nPresiona el botón abajo para aceptar el reto.",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(f"{oponente.mention}", embed=embed, view=view)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(RPSBet(bot))
    print("RPSBet cog cargado con éxito.")
