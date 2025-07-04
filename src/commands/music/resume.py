import discord
from discord.ext import commands
import wavelink

class MusicResume(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="resume", help="Reanuda la canción pausada.")
    async def resume(self, ctx):
        player: wavelink.Player = wavelink.Pool.get_node().get_player(ctx.guild)
        if not player or not player.is_connected() or not player.current:
            await ctx.send("❌ No hay ninguna canción pausada o reproduciéndose.")
            return
        if not player.paused:
            await ctx.send("▶️ La canción ya está sonando.")
            return
        await player.pause(False)
        await ctx.send("▶️ Canción reanudada.")

async def setup(bot):
    await bot.add_cog(MusicResume(bot))
    print("MusicResume cog loaded successfully.")
