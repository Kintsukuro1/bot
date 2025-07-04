import discord
from discord.ext import commands
import wavelink

class MusicLoop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loop_mode = {}  # Diccionario para almacenar el modo de repetición por servidor

    @commands.command(name="loop", help="Activa/desactiva la repetición de la canción o cola actual.")
    async def loop(self, ctx, mode=None):
        # Obtener el player del servidor actual
        node = wavelink.Pool.get_node()
        if not node:
            await ctx.send("❌ No hay nodos de Lavalink disponibles.")
            return
            
        player = node.get_player(ctx.guild)
        if not player or not player.is_connected():
            await ctx.send("❌ No estoy conectado a ningún canal de voz.")
            return
        
        guild_id = ctx.guild.id
        
        # Si no se especificó un modo, alterna entre los modos
        if not mode:
            current_mode = self.loop_mode.get(guild_id, "off")
            if current_mode == "off":
                new_mode = "song"
            elif current_mode == "song":
                new_mode = "queue"
            else:
                new_mode = "off"
        else:
            # Si se especificó un modo, establecerlo directamente
            mode = mode.lower()
            if mode in ["off", "song", "queue"]:
                new_mode = mode
            else:
                await ctx.send("❌ Modo inválido. Usa 'off', 'song' o 'queue'.")
                return
        
        # Guardar el nuevo modo
        self.loop_mode[guild_id] = new_mode
        
        # Mostrar mensaje de confirmación
        if new_mode == "off":
            await ctx.send("🔄 Repetición desactivada.")
        elif new_mode == "song":
            await ctx.send("🔂 Repetición de canción activada.")
        else:
            await ctx.send("🔁 Repetición de cola activada.")

async def setup(bot):
    await bot.add_cog(MusicLoop(bot))
    print("MusicLoop cog loaded successfully.")
