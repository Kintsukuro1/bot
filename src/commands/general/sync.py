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
    async def sync(self, ctx: commands.Context, spec: str = None) -> None:
        """
        Sincroniza los comandos slash del bot.
        Modo de uso:
        !sync         -> Limpia comandos locales de la guild (evita duplicados) y sincroniza globales.
        !sync guild   -> Sincroniza comandos solo en el servidor actual.
        !sync clear   -> Elimina los comandos específicos de este servidor.
        !sync global  -> Sincroniza comandos globales únicamente.
        """
        try:
            if spec == "guild":
                await ctx.send("⏳ Sincronizando comandos slash localmente en este servidor...")
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
                await ctx.send(f"✅ {len(synced)} comandos slash locales sincronizados.")
            elif spec == "clear":
                await ctx.send("⏳ Limpiando comandos locales de este servidor...")
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                await ctx.send("🧹 Todos los comandos locales han sido eliminados de este servidor.")
            elif spec == "global":
                await ctx.send("⏳ Sincronizando comandos globales...")
                synced = await ctx.bot.tree.sync()
                await ctx.send(f"✅ {len(synced)} comandos slash globales sincronizados.")
            else:
                await ctx.send("⏳ Limpiando comandos locales para evitar duplicados y sincronizando globalmente...")
                # 1. Limpiar comandos de la guild actual
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                # 2. Sincronizar globalmente
                synced = await ctx.bot.tree.sync()
                await ctx.send(f"✅ Comandos locales limpiados. {len(synced)} comandos globales sincronizados exitosamente.")
        except Exception as e:
            await ctx.send(f"❌ Error al sincronizar comandos: {str(e)}")

async def setup(bot):
    await bot.add_cog(SyncCommand(bot))
    print("SyncCommand cog loaded successfully.")