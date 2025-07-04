import discord
from discord.ext import commands
import wavelink

class MusicStop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="stop", help="Detiene la música y desconecta al bot del canal de voz.")
    async def stop(self, ctx):
        player: wavelink.Player = wavelink.Pool.get_node().get_player(ctx.guild)
        if not player or not player.is_connected():
            await ctx.send("❌ No estoy conectado a ningún canal de voz.")
            return
        await player.disconnect()
        await ctx.send("⏹️ Música detenida y bot desconectado del canal de voz.")

async def setup(bot):
    await bot.add_cog(MusicStop(bot))
    print("MusicStop cog loaded successfully.")
