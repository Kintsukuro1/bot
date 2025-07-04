import discord
from discord.ext import commands
import wavelink

class MusicClear(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="clear", help="Limpia la cola de reproducción.")
    async def clear(self, ctx):
        # Obtener el player del servidor actual
        node = wavelink.Pool.get_node()
        if not node:
            await ctx.send("❌ No hay nodos de Lavalink disponibles.")
            return
            
        player = node.get_player(ctx.guild)
        if not player or not player.is_connected():
            await ctx.send("❌ No estoy conectado a ningún canal de voz.")
            return
        
        # Limpiar la cola (aún no implementado en wavelink v2, se actualizará cuando esté disponible)
        # Por ahora, simplemente paramos y reiniciamos
        if hasattr(player, 'queue') and player.queue:
            player.queue.clear()
            await ctx.send("🧹 Cola de reproducción limpiada.")
        else:
            await ctx.send("ℹ️ La cola de reproducción ya está vacía.")

async def setup(bot):
    await bot.add_cog(MusicClear(bot))
    print("MusicClear cog loaded successfully.")
