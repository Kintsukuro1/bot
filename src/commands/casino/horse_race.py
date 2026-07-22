import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from typing import Dict, List, Tuple

from src.db import get_balance, ensure_user
from src.services.casino_service import CasinoService
from src.utils.dynamic_difficulty import DynamicDifficulty

HORSE_TEMPLATES = [
    {"emoji": "⚡"},
    {"emoji": "🌑"},
    {"emoji": "🌪️"},
    {"emoji": "🔥"},
    {"emoji": "🍃"}
]

POSSIBLE_NAMES = [
    "Foot licker",
    "Trash can",
    "Vivaloo minlgy",
    "few jobs aplication",
    "fourthy dreams",
    "whilling to change"
]

SECRET_HORSES = [
    "turbulent waters"
]

def generate_horse_names(num_horses: int) -> List[str]:
    """
    Generate distinct random names for the given number of horses.
    If there are more horses than possible names, generate fallback names.
    """
    base_count = len(POSSIBLE_NAMES)

    shuffled_names = POSSIBLE_NAMES[:]  # copy to avoid mutating the global list
    random.shuffle(shuffled_names)

    # Use as many shuffled names as we have available
    assigned_names = shuffled_names[:min(num_horses, base_count)]

    # If we still have more horses than names, generate fallback names
    if num_horses > base_count:
        remaining = num_horses - base_count
        for i in range(remaining):
            assigned_names.append(f"Horse {i + 1}")
            
    return assigned_names

def create_horses() -> Tuple[List[dict], Dict[int, int]]:
    """Creates a list of horse dicts and a doping dictionary for a single race."""
    num_horses = len(HORSE_TEMPLATES)
    names = generate_horse_names(num_horses)
    
    race_horses = []
    for i, template in enumerate(HORSE_TEMPLATES):
        race_horses.append({
            "name": names[i],
            "emoji": template["emoji"]
        })
        
    # 5% chance para un caballo secreto en la carrera
    if random.random() < 0.05:
        secret_horse = random.choice(SECRET_HORSES)
        replace_idx = random.randint(0, num_horses - 1)
        race_horses[replace_idx]['name'] = secret_horse

    race_doping = {i: 0 for i in range(num_horses)}
    return race_horses, race_doping



class HorseBetModal(discord.ui.Modal, title="Apostar en la Carrera"):
    amount = discord.ui.TextInput(
        label="Cantidad a apostar",
        style=discord.TextStyle.short,
        placeholder="Ej: 100",
        required=True
    )

    def __init__(self, race_view, horse_idx: int):
        super().__init__()
        self.race_view = race_view
        self.horse_idx = horse_idx
        self.horse_name = race_view.horses[horse_idx]['name']
        self.horse_emoji = race_view.horses[horse_idx]['emoji']

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.amount.value)
            if bet_amount <= 0:
                await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Ingresa una cantidad válida.", ephemeral=True)
            return

        user_id = interaction.user.id
        can_play, lockout_msg = await CasinoService.check_casino_lockout(user_id)
        if not can_play:
            await interaction.response.send_message(lockout_msg, ephemeral=True)
            return

        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        async with self.race_view.lock:
            balance = await asyncio.to_thread(get_balance, user_id)
            
            old_bet = 0
            if user_id in self.race_view.bets:
                old_bet = self.race_view.bets[user_id]['amount']
                
            total_available = balance + old_bet

            if bet_amount > total_available:
                await interaction.response.send_message("❌ No tienes suficiente saldo.", ephemeral=True)
                return

            if old_bet > 0:
                await CasinoService.refund_bet(user_id, old_bet, 'horse_race', 'Devolución Apuesta Anterior Caballos')
            
            success, _ = await CasinoService.place_bet(user_id, bet_amount, 'horse_race')
            if not success:
                await interaction.response.send_message("❌ No tienes suficiente saldo.", ephemeral=True)
                return
            
            self.race_view.bets[user_id] = {
                'horse_idx': self.horse_idx,
                'amount': bet_amount,
                'user': interaction.user
            }

        await interaction.response.send_message(f"✅ Has apostado **{bet_amount}** a {self.horse_emoji} **{self.horse_name}**.", ephemeral=True)
        await self.race_view.update_embed()

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        from src.services.casino_service import CasinoCircuitBreakerError
        msg = str(error) if isinstance(error, CasinoCircuitBreakerError) else "❌ Ocurrió un error inesperado al procesar tu apuesta."
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass


class HorseSelect(discord.ui.Select):
    def __init__(self, horses):
        options = [
            discord.SelectOption(label=h['name'], emoji=h['emoji'], value=str(i))
            for i, h in enumerate(horses)
        ]
        super().__init__(placeholder="Elige un caballo para apostar...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: HorseRaceView = self.view
        if view.started:
            await interaction.response.send_message("❌ La carrera ya ha comenzado.", ephemeral=True)
            return
            
        horse_idx = int(self.values[0])
        await interaction.response.send_modal(HorseBetModal(view, horse_idx))

class HorseRaceView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=None) # Timeout manually handled
        self.channel = channel
        self.bets: Dict[int, dict] = {} # user_id -> {'horse_idx': int, 'amount': int, 'user': User}
        self.started = False
        self.message = None
        self.lock = asyncio.Lock()
        
        # Create independent horse data for this race
        self.horses, self.horse_doping = create_horses()
        
        # Generar multiplicadores aleatorios (cuotas) para cada caballo (entre 1.5 y 5.0)
        self.multipliers = [round(random.uniform(1.5, 5.0), 1) for _ in self.horses]
        
        self.add_item(HorseSelect(self.horses))

    async def update_embed(self):
        if not self.message: return
        embed = self.message.embeds[0]
        
        bets_text = "\n".join([f"{data['user'].display_name}: **{data['amount']}** a {self.horses[data['horse_idx']]['emoji']}" for data in self.bets.values()])
        if not bets_text:
            bets_text = "Nadie ha apostado aún."
            
        embed.clear_fields()
        embed.add_field(name="🏇 Apuestas actuales", value=bets_text, inline=False)
        
        try:
            await self.message.edit(embed=embed, view=self)
        except (discord.NotFound, discord.Forbidden):
            return

    async def run_race(self):
        self.started = True
        for item in self.children:
            item.disabled = True
            
        embed = self.message.embeds[0]
        embed.title = "🏁 ¡LA CARRERA HA COMENZADO! 🏁"
        embed.color = discord.Color.red()
        await self.message.edit(embed=embed, view=self)

        mentions = " ".join([data['user'].mention for data in self.bets.values()])
        if mentions:
            await self.channel.send(f"🏁 ¡La carrera ha comenzado! {mentions}")
        else:
            await self.channel.send("🏁 ¡La carrera ha comenzado! (No hay participantes)")

        # Estado de la carrera (distancia 0 a 20)
        positions = [0] * len(self.horses)
        race_length = 20
        winner_idx = -1

        emojis_pista = []
        caballos_muertos = []
        for i in range(len(self.horses)):
            if self.horse_doping[i] > 3:
                emojis_pista.append("💀")
                caballos_muertos.append(self.horses[i]['name'])
            else:
                emojis_pista.append(self.horses[i]['emoji'])

        if caballos_muertos:
            embed.description = f"⚠️ **¡ATENCIÓN!** {', '.join(caballos_muertos)} ha sufrido un infarto por sobredosis de doping antes de iniciar la carrera.\n\n"
        else:
            embed.description = ""

        # Dibujar pista inicial
        track = ""
        for i, h in enumerate(self.horses):
            line = emojis_pista[i] + "➖" * race_length + " 🏁"
            track += f"{line}\n"

        ticks = 0
        max_ticks = 100
        while winner_idx == -1 and ticks < max_ticks:
            ticks += 1
            await asyncio.sleep(1.5)
            
            # Avanzar caballos aleatoriamente
            for i in range(len(self.horses)):
                if self.horse_doping[i] > 3:
                    # El caballo murió por sobredosis, no avanza
                    pass
                else:
                    # Caballos con multiplicador más bajo (favoritos) tienen un leve bonus de velocidad
                    speed_bonus = (5.0 - self.multipliers[i]) * 0.2
                    doping_bonus = self.horse_doping[i] * 1.5
                    move = random.randint(1, 3) + random.random() * speed_bonus + doping_bonus
                    positions[i] += int(move)
                
                if positions[i] >= race_length:
                    positions[i] = race_length
                    if winner_idx == -1:
                        winner_idx = i
                        
            # Dibujar pista
            track = ""
            for i, h in enumerate(self.horses):
                pos = min(positions[i], race_length)
                line = "➖" * pos + emojis_pista[i] + "➖" * (race_length - pos) + " 🏁"
                track += f"{line}\n"
                
            embed.description = f"**Pista:**\n\n{track}"
            if caballos_muertos:
                embed.description = f"⚠️ **Sobredosis:** {', '.join(caballos_muertos)} (Eliminados)\n\n" + embed.description
            await self.message.edit(embed=embed, view=self)

        # Si terminó por límite de ticks sin un ganador oficial, resolver según posiciones actuales
        if winner_idx == -1:
            max_pos = -1
            for i in range(len(self.horses)):
                # Priorizar caballos vivos
                if self.horse_doping[i] <= 3 and positions[i] > max_pos:
                    max_pos = positions[i]
                    winner_idx = i
            if winner_idx == -1:
                winner_idx = 0

        # Carrera terminada
        winner_horse = self.horses[winner_idx]
        winner_mult = self.multipliers[winner_idx]
        
        embed.title = f"🏆 ¡{winner_horse['name']} ({winner_horse['emoji']}) GANA LA CARRERA! 🏆"
        embed.color = discord.Color.gold()
        embed.description = f"**Pista:**\n\n{track}\n\n**Pagos (x{winner_mult}):**\n"
        
        # Calcular totales para el pozo
        total_losing_bets = sum(b['amount'] for b in self.bets.values() if b['horse_idx'] != winner_idx)
        total_winning_bets = sum(b['amount'] for b in self.bets.values() if b['horse_idx'] == winner_idx)

        # Pagar a los ganadores
        winners_text = ""
        for user_id, bet_data in self.bets.items():
            bet_amt = bet_data['amount']
            user = bet_data['user']
            
            # Calcular dificultad
            diff_mod, _ = await asyncio.to_thread(DynamicDifficulty.calculate_dynamic_difficulty, user_id, bet_amt, 'horse_race')
            
            if bet_data['horse_idx'] == winner_idx:
                # Ganancia = apuesta * multiplicador + proporción del pozo de perdedores
                base_winnings = bet_amt * winner_mult
                pool_share = total_losing_bets * (bet_amt / total_winning_bets) if total_winning_bets > 0 else 0
                
                winnings = int(base_winnings + pool_share)
                
                current_bal = await asyncio.to_thread(get_balance, user_id)
                nuevo_saldo, impuesto = await CasinoService.settle_win(
                    user_id,
                    bet_amt,
                    winnings,
                    'horse_race',
                    diff_mod,
                    current_bal
                )
                lockout_activated = await CasinoService.check_and_apply_winstreak_lockout(user_id, nuevo_saldo)
                
                winners_text += f"✅ {user.mention} ganó **{winnings - impuesto}** monedas netas.\n"
                if lockout_activated:
                    winners_text += f"⚠️ {user.mention} **🎰 Has ganado mucho muy rápido — tómate un descanso de 25 minutos antes de seguir jugando.**\n"
            else:
                current_bal = await asyncio.to_thread(get_balance, user_id)
                await CasinoService.settle_loss(
                    user_id,
                    bet_amt,
                    'horse_race',
                    diff_mod,
                    current_bal
                )
                winners_text += f"❌ {user.display_name} perdió **{bet_amt}** monedas.\n"
                
        if not winners_text:
            winners_text = "Nadie ganó."
            
        embed.add_field(name="Resultados de las apuestas", value=winners_text)
        await self.message.edit(embed=embed, view=None)

class HorseRace(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_races = {} # channel_id -> HorseRaceView

    @app_commands.command(name="horse_race", description="Organiza una carrera de caballos multijugador.")
    async def horse_race(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        if channel_id in self.active_races:
            await interaction.response.send_message("❌ Ya hay una carrera activa en este canal.", ephemeral=True)
            return
            
        try:
            view = HorseRaceView(interaction.channel)
            self.active_races[channel_id] = view
            
            desc = "**Caballos en pista:**\n"
            for i, h in enumerate(view.horses):
                desc += f"{h['emoji']} **{h['name']}** - Cuota: **x{view.multipliers[i]}**\n"
                
            desc += "\nTienen **60 segundos** para hacer sus apuestas utilizando el menú de abajo."
            
            embed = discord.Embed(
                title="🏇 ¡NUEVA CARRERA DE CABALLOS! 🏇",
                description=desc,
                color=discord.Color.blue()
            )
            
            await interaction.response.send_message(embed=embed, view=view)
            view.message = await interaction.original_response()
            
            # Esperar 60 segundos para apuestas
            await asyncio.sleep(60)
            
            # Comenzar carrera
            await view.run_race()
            
        finally:
            if channel_id in self.active_races:
                del self.active_races[channel_id]

async def setup(bot):
    await bot.add_cog(HorseRace(bot))
