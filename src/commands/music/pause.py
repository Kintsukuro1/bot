import discord
from discord.ext import commands
import wavelink

class MusicPause(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="pause", help="Pausa la canción actual.")
    async def pause(self, ctx):
        player: wavelink.Player = wavelink.Pool.get_node().get_player(ctx.guild)
        if not player or not player.is_connected() or not player.current:
            await ctx.send("❌ No hay ninguna canción reproduciéndose.")
            return
        if player.paused:
            await ctx.send("⏸️ La canción ya está pausada.")
            return
        await player.pause(True)
        await ctx.send("⏸️ Canción pausada.")

async def setup(bot):
    await bot.add_cog(MusicPause(bot))
    print("MusicPause cog loaded successfully.")
