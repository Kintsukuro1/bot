from typing import Literal, Optional
import discord
from discord.ext import commands

class SyncCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="sync",
        help=(
            "Sincroniza los comandos slash del bot.\n"
            "Uso:\n"
            "!sync           -> Sincroniza globalmente\n"
            "!sync ~         -> Solo en el servidor actual\n"
            "!sync *         -> Copia globales al servidor actual\n"
            "!sync ^         -> Borra comandos del servidor actual\n"
            "!sync <guilds>  -> Sincroniza en los guilds dados"
        )
    )
    @commands.guild_only()
    @commands.is_owner()
    async def sync(
        self,
        ctx: commands.Context,
        guilds: commands.Greedy[discord.Object] = None,
        spec: Optional[Literal["~", "*", "^"]] = None
    ) -> None:
        """
        Sincroniza los comandos slash del bot.
        """
        guilds = guilds or []
        if not guilds:
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
                scope = f"el servidor actual ({ctx.guild.name})"
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
                scope = f"copiados globales al servidor actual ({ctx.guild.name})"
            elif spec == "^":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
                scope = f"borrados del servidor actual ({ctx.guild.name})"
            else:
                synced = await ctx.bot.tree.sync()
                scope = "globalmente"
            await ctx.send(
                f"✅ {len(synced)} comandos sincronizados {scope}."
            )
            return
        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1
        await ctx.send(f"✅ Árbol sincronizado en {ret}/{len(guilds)} servidores.")

async def setup(bot):
    await bot.add_cog(SyncCommand(bot))
    print("SyncCommand cog loaded successfully.")