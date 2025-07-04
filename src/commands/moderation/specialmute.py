import discord
from discord.ext import commands
import random
import datetime

LOG_CHANNEL_ID = 1361556360000573622
ID_AUTORIZADO = 287396390747766795

MUTE_OPTIONS = [
    ("5 minutos", 5),
    ("10 minutos", 10),
    ("30 minutos", 30),
    ("1 hora", 60),
    ("1 día", 60*24),
    ("se salvó", 0)
]

class SpecialMute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="specialmute",
        description="Mutea a un usuario aleatoriamente (solo mención, no ID)."
    )
    @discord.app_commands.describe(
        miembro="Usuario a mutear (selecciónalo del menú o menciónalo)"
    )
    async def specialmute(self, interaction: discord.Interaction, miembro: discord.Member):
        if interaction.user.id != ID_AUTORIZADO:
            await interaction.response.send_message("No tienes permiso para usar este comando.", ephemeral=True)
            return

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        mention = miembro.mention
        resultado, minutos = random.choice(MUTE_OPTIONS)

        if minutos > 0:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=minutos)
            try:
                await miembro.timeout(until, reason="Mute especial (timeout)")
                msg = f"🔇 {mention} Wena hablai puras weas y te ganaste {resultado} de silencio."
            except Exception as e:
                msg = f"No se pudo mutear a {mention}: {e}"
        else:
            msg = f"🟢 {mention} Te salvaste de pura suerte."

        if log_channel:
            await log_channel.send(msg)
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(SpecialMute(bot))


