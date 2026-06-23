import discord
from discord.ext import commands
from discord import app_commands

class Unmute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="unmute", description="Quita el silencio a un usuario en el servidor.")
    @app_commands.describe(miembro="Usuario a desmutear")
    @app_commands.default_permissions(manage_roles=True)
    async def unmute(self, interaction: discord.Interaction, miembro: discord.Member):
        """Quita el silencio a un usuario en el servidor."""
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Este comando solo puede ser usado en servidores.", ephemeral=True)
            return

        muted_role = discord.utils.get(guild.roles, name="Muted")

        if not muted_role:
            await interaction.followup.send("❌ No existe el rol 'Muted' en este servidor.", ephemeral=True)
            return

        if muted_role in miembro.roles:
            try:
                await miembro.remove_roles(muted_role, reason=f"Unmute solicitado por {interaction.user.name}")
                await interaction.followup.send(f"🔊 {miembro.mention} ya puede hablar y escribir de nuevo.", ephemeral=False)
            except discord.Forbidden:
                await interaction.followup.send("❌ No tengo permisos suficientes para remover el rol a este usuario (puede que tenga un rol superior al mío o no tenga permisos de gestionar roles).", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Ocurrió un error al intentar desmutear al usuario: {e}", ephemeral=True)
        else:
            await interaction.followup.send(f"ℹ️ {miembro.mention} no está silenciado.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Unmute(bot))