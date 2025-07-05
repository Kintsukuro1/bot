from discord.ext import commands

class SyncCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="sync",
        help="Sincroniza los comandos slash del bot."
    )
    @commands.guild_only()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context) -> None:
        """
        Sincroniza los comandos slash del bot.
        """
        try:
            await ctx.send("⏳ Sincronizando comandos slash...")
            
            # Sincronizar globalmente
            synced = await ctx.bot.tree.sync()
            
            # Sincronizar también en el servidor actual si estamos en uno
            if ctx.guild:
                await ctx.bot.tree.sync(guild=ctx.guild)
            
            await ctx.send(f"✅ {len(synced)} comandos slash sincronizados correctamente.")
        except Exception as e:
            await ctx.send(f"❌ Error al sincronizar comandos: {str(e)}")

async def setup(bot):
    await bot.add_cog(SyncCommand(bot))
    print("SyncCommand cog loaded successfully.")