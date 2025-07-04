import discord
from discord.ext import commands
import wavelink

class MusicShuffle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="shuffle", help="Mezcla la cola de reproducción.")
    async def shuffle(self, ctx):
        # Obtener el player del servidor actual
        node = wavelink.Pool.get_node()
        if not node:
            await ctx.send("❌ No hay nodos de Lavalink disponibles.")
            return
            
        player = node.get_player(ctx.guild)
        if not player or not player.is_connected():
            await ctx.send("❌ No estoy conectado a ningún canal de voz.")
            return
        
        # Verificar si hay canciones en la cola
        if not hasattr(player, 'queue') or not player.queue:
            await ctx.send("❌ La cola de reproducción está vacía.")
            return
        
        # Mezclar la cola
        try:
            import random
            random.shuffle(player.queue)
            await ctx.send("🔀 La cola de reproducción ha sido mezclada.")
        except Exception as e:
            await ctx.send(f"❌ Error al mezclar la cola: {str(e)}")

async def setup(bot):
    await bot.add_cog(MusicShuffle(bot))
    print("MusicShuffle cog loaded successfully.")
