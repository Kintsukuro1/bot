import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from src.services import UserService, EconomyService

logger = logging.getLogger(__name__)

class Regalar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="regalar", description="Regala dinero a otro usuario")
    @app_commands.describe(
        usuario="El usuario al que quieres regalarle dinero",
        cantidad="Cantidad de monedas a regalar"
    )
    async def regalar(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        # Verificar que no sea el mismo usuario
        if interaction.user.id == usuario.id:
            await interaction.response.send_message("❌ No puedes regalarte dinero a ti mismo.", ephemeral=True)
            return
        
        # Verificar que no sea un bot
        if usuario.bot:
            await interaction.response.send_message("❌ No puedes regalar dinero a un bot.", ephemeral=True)
            return
        
        # Verificar cantidad válida
        if cantidad <= 0:
            await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)
            return
        
        # Límite mínimo y máximo por transacción
        if cantidad < 10:
            await interaction.response.send_message("❌ La cantidad mínima para regalar es de 10 monedas.", ephemeral=True)
            return
        
        if cantidad > 50000:
            await interaction.response.send_message("❌ La cantidad máxima para regalar es de 50,000 monedas por transacción.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Asegurar usuarios y obtener saldo asíncronamente
        await UserService.ensure_user(interaction.user.id, interaction.user.name)
        await UserService.ensure_user(usuario.id, usuario.name)
        saldo_remitente = await UserService.get_balance(interaction.user.id)
        
        if saldo_remitente < cantidad:
            await interaction.followup.send(f"❌ No tienes suficiente saldo. Tu saldo actual: {saldo_remitente:,} monedas.", ephemeral=True)
            return
        
        # Crear embed de confirmación
        embed = discord.Embed(
            title="💝 Confirmar Regalo",
            description=(
                f"**De:** {interaction.user.display_name}\n"
                f"**Para:** {usuario.display_name}\n"
                f"**Cantidad:** {cantidad:,} monedas\n\n"
                f"¿Estás seguro de que quieres regalar {cantidad:,} monedas a {usuario.display_name}?"
            ),
            color=discord.Color.gold()
        )
        embed.add_field(
            name="💰 Tu saldo actual",
            value=f"{saldo_remitente:,} monedas",
            inline=True
        )
        embed.add_field(
            name="💳 Tu saldo después",
            value=f"{saldo_remitente - cantidad:,} monedas",
            inline=True
        )
        
        # Crear vista con botones de confirmación
        view = ConfirmGiftView(interaction.user, usuario, cantidad, saldo_remitente)
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        message = await interaction.original_response()
        view.message = message

class ConfirmGiftView(discord.ui.View):
    def __init__(self, remitente, destinatario, cantidad, saldo_remitente):
        super().__init__(timeout=30)
        self.remitente = remitente
        self.destinatario = destinatario
        self.cantidad = cantidad
        self.saldo_remitente = saldo_remitente
        self.confirmado = False

    @discord.ui.button(label="✅ Confirmar Regalo", style=discord.ButtonStyle.success)
    async def confirmar_regalo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.remitente.id:
            await interaction.response.send_message("❌ Solo quien inició el regalo puede confirmarlo.", ephemeral=True)
            return
        
        if self.confirmado:
            await interaction.response.send_message("❌ Este regalo ya fue procesado.", ephemeral=True)
            return
        
        await interaction.response.defer()
        self.confirmado = True
        
        try:
            # Transferencia atómica de saldo
            success, saldo_remitente_final, saldo_destinatario_final = await EconomyService.transfer_balance(
                self.remitente.id,
                self.destinatario.id,
                self.cantidad,
                "Regalo"
            )

            if not success:
                # Obtener saldo fresco para informar al emisor
                saldo_fresco = await UserService.get_balance(self.remitente.id)
                embed = discord.Embed(
                    title="❌ Regalo Cancelado",
                    description=f"No tienes suficiente saldo al momento de confirmar. Saldo actual: {saldo_fresco:,} monedas.",
                    color=discord.Color.red()
                )
                await interaction.edit_original_response(embed=embed, view=None)
                return
            
            # Embed de éxito
            embed = discord.Embed(
                title="🎉 ¡Regalo Enviado!",
                description=(
                    f"**{self.remitente.display_name}** ha regalado **{self.cantidad:,} monedas** "
                    f"a **{self.destinatario.display_name}**"
                ),
                color=discord.Color.green()
            )
            
            embed.add_field(
                name=f"💰 {self.remitente.display_name}",
                value=f"Saldo: {saldo_remitente_final:,} monedas",
                inline=True
            )
            embed.add_field(
                name=f"💰 {self.destinatario.display_name}",
                value=f"Saldo: {saldo_destinatario_final:,} monedas",
                inline=True
            )
            embed.set_footer(text="¡Gracias por tu generosidad! 💝")
            
            # Desactivar botones
            for item in self.children:
                item.disabled = True
            
            await interaction.edit_original_response(embed=embed, view=self)
            
            # Intentar notificar al destinatario de forma pública
            try:
                mention_embed = discord.Embed(
                    title="🎁 ¡Has recibido un regalo!",
                    description=(
                        f"**{self.remitente.display_name}** te ha regalado **{self.cantidad:,} monedas**\n\n"
                        f"💰 **Tu nuevo saldo:** {saldo_destinatario_final:,} monedas"
                    ),
                    color=discord.Color.green()
                )
                mention_embed.set_footer(text="Usa /plata para ver tu saldo actualizado")
                
                await interaction.channel.send(
                    content=f"{self.destinatario.mention}",
                    embed=mention_embed
                )
            except Exception as ex:
                logger.warning(f"No se pudo enviar mensaje público de notificación de regalo: {ex}")
                
                raise
        except Exception as e:
            logger.error(f"Error al procesar regalo: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Error al Procesar Regalo",
                description="Ocurrió un error al procesar la transacción. Por favor, intenta de nuevo.",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)
        
            raise
        self.stop()

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancelar_regalo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.remitente.id:
            await interaction.response.send_message("❌ Solo quien inició el regalo puede cancelarlo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        embed = discord.Embed(
            title="❌ Regalo Cancelado",
            description=f"El regalo de {self.cantidad:,} monedas ha sido cancelado.",
            color=discord.Color.red()
        )
        
        # Desactivar botones
        for item in self.children:
            item.disabled = True
        
        await interaction.edit_original_response(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        """Se ejecuta cuando se agota el tiempo."""
        if not self.confirmado:
            for item in self.children:
                item.disabled = True
            try:
                if hasattr(self, 'message') and self.message:
                    embed = discord.Embed(
                        title="⏰ Regalo Expirado",
                        description=f"El tiempo para confirmar el regalo de {self.cantidad:,} monedas ha expirado.",
                        color=discord.Color.orange()
                    )
                    await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

                raise
async def setup(bot):
    await bot.add_cog(Regalar(bot))
    logger.info("Regalar cog loaded successfully.")
