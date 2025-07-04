import discord
from discord.ext import commands
import wavelink

class MusicRemove(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="remove", help="Elimina una canción de la cola de reproducción. Uso: !remove <número>")
    async def remove(self, ctx, position: int = None):
        # Verificar que se proporcionó un número
        if position is None:
            await ctx.send("❌ Por favor, especifica el número de la canción a eliminar.")
            return
            
        # El número debe ser positivo
        if position <= 0:
            await ctx.send("❌ El número debe ser mayor que 0.")
            return
        
        # Obtener el player del servidor actual
        node = wavelink.Pool.get_node()
        if not node:
            await ctx.send("❌ No hay nodos de Lavalink disponibles.")
            return
            
        player = node.get_player(ctx.guild)
        if not player or not player.is_connected():
            await ctx.send("❌ No estoy conectado a ningún canal de voz.")
            return
        
        # Verificar si la cola existe y tiene la canción solicitada
        if not hasattr(player, 'queue') or not player.queue or len(player.queue) < position:
            await ctx.send(f"❌ No hay canción en la posición {position} de la cola.")
            return
        
        # Eliminar la canción (índice es posición - 1)
        try:
            removed_track = player.queue[position - 1]
            del player.queue[position - 1]
            await ctx.send(f"✅ Se eliminó **{removed_track.title}** de la cola.")
        except Exception as e:
            await ctx.send(f"❌ Error al eliminar la canción: {str(e)}")

async def setup(bot):
    await bot.add_cog(MusicRemove(bot))
    print("MusicRemove cog loaded successfully.")
