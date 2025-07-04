import discord
from discord.ext import commands
import wavelink

class MusicLeave(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="leave", help="Desconecta el bot del canal de voz.")
    async def leave(self, ctx):
        # Obtener el player del servidor actual
        node = wavelink.Pool.get_node()
        if not node:
            await ctx.send("❌ No hay nodos de Lavalink disponibles.")
            return
            
        player = node.get_player(ctx.guild)
        if not player or not player.is_connected():
            await ctx.send("❌ No estoy conectado a ningún canal de voz.")
            return
        
        # Desconectar
        await player.disconnect()
        await ctx.send("👋 Desconectado del canal de voz.")

async def setup(bot):
    await bot.add_cog(MusicLeave(bot))
    print("MusicLeave cog loaded successfully.")
