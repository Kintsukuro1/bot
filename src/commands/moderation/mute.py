import discord
from discord.ext import commands
from discord import app_commands

class Mute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mute", description="Silencia a un usuario en el servidor.")
    @app_commands.describe(miembro="Usuario a silenciar", motivo="Motivo del silencio")
    @app_commands.default_permissions(manage_roles=True)
    async def mute(self, interaction: discord.Interaction, miembro: discord.Member, motivo: str = "Sin motivo"):
        """Silencia a un usuario en el servidor."""
        # Responder diferido por si la creación del rol o permisos toma tiempo
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Este comando solo puede ser usado en servidores.", ephemeral=True)
            return

        # Evitar auto-silenciado
        if miembro.id == interaction.user.id:
            await interaction.followup.send("❌ No puedes silenciarte a ti mismo.", ephemeral=True)
            return

        muted_role = discord.utils.get(guild.roles, name="Muted")

        # Si no existe el rol, créalo y ajusta permisos
        if not muted_role:
            try:
                muted_role = await guild.create_role(name="Muted", reason="Rol para silenciar usuarios")
                for channel in guild.channels:
                    if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)):
                        try:
                            await channel.set_permissions(muted_role, speak=False, send_messages=False, add_reactions=False)
                        except discord.Forbidden:
                            pass
            except discord.Forbidden:
                await interaction.followup.send("❌ No tengo permisos para crear el rol 'Muted'.", ephemeral=True)
                return

        try:
            await miembro.add_roles(muted_role, reason=motivo)
            await interaction.followup.send(f"🔇 {miembro.mention} ha sido silenciado. Motivo: {motivo}", ephemeral=False)
        except discord.Forbidden:
            await interaction.followup.send("❌ No tengo permisos suficientes para agregar el rol a este usuario (puede que tenga un rol superior al mío o no tenga permisos de gestionar roles).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ocurrió un error al intentar silenciar al usuario: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Mute(bot))