import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional
import asyncio

class PollView(discord.ui.View):
    def __init__(self, question: str, options: List[str], creator_id: int, duration: int = 300):
        super().__init__(timeout=duration)
        self.question = question
        self.options = options
        self.creator_id = creator_id
        self.votes = {i: set() for i in range(len(options))}  # {opción_index: {user_ids}}
        self.voters = set()  # Para evitar votos duplicados
        
        # Crear botones para cada opción (máximo 25 por limitaciones de Discord)
        for i, option in enumerate(options[:25]):
            button = discord.ui.Button(
                label=f"{i+1}. {option}",
                style=discord.ButtonStyle.primary,
                custom_id=f"poll_option_{i}"
            )
            button.callback = self.create_vote_callback(i)
            self.add_item(button)
        
        # Botón para finalizar poll (solo para el creador)
        end_button = discord.ui.Button(
            label="🔒 Finalizar Votación",
            style=discord.ButtonStyle.danger,
            custom_id="end_poll"
        )
        end_button.callback = self.end_poll
        self.add_item(end_button)

    def create_vote_callback(self, option_index: int):
        async def vote_callback(interaction: discord.Interaction):
            user_id = interaction.user.id
            
            # Verificar si el usuario ya votó
            if user_id in self.voters:
                # Remover voto anterior
                for votes_set in self.votes.values():
                    votes_set.discard(user_id)
            
            # Agregar nuevo voto
            self.votes[option_index].add(user_id)
            self.voters.add(user_id)
            
            # Actualizar embed
            embed = self.create_results_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        
        return vote_callback

    async def end_poll(self, interaction: discord.Interaction):
        # Solo el creador puede finalizar la votación
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message("❌ Solo quien creó la votación puede finalizarla.", ephemeral=True)
            return
        
        # Finalizar votación
        for item in self.children:
            item.disabled = True
        
        embed = self.create_results_embed(final=True)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    def create_results_embed(self, final: bool = False) -> discord.Embed:
        total_votes = len(self.voters)
        
        title = "📊 Votación Finalizada" if final else "📊 Votación en Curso"
        embed = discord.Embed(
            title=title,
            description=f"**{self.question}**",
            color=discord.Color.green() if final else discord.Color.blue()
        )
        
        # Calcular y mostrar resultados
        if total_votes > 0:
            # Ordenar opciones por número de votos (descendente)
            sorted_options = sorted(
                enumerate(self.options), 
                key=lambda x: len(self.votes[x[0]]), 
                reverse=True
            )
            
            results_text = ""
            for i, (option_index, option) in enumerate(sorted_options):
                vote_count = len(self.votes[option_index])
                percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
                
                # Crear barra de progreso visual
                bar_length = 20
                filled_length = int(bar_length * percentage / 100)
                bar = "█" * filled_length + "░" * (bar_length - filled_length)
                
                # Emoji para el ganador
                position_emoji = "🥇" if i == 0 and final and vote_count > 0 else f"{option_index + 1}."
                
                results_text += f"{position_emoji} **{option}**\n"
                results_text += f"`{bar}` {percentage:.1f}% ({vote_count} votos)\n\n"
            
            embed.add_field(
                name="📈 Resultados",
                value=results_text,
                inline=False
            )
        else:
            embed.add_field(
                name="📈 Resultados",
                value="🚫 Aún no hay votos",
                inline=False
            )
        
        # Información adicional
        embed.add_field(
            name="👥 Participación",
            value=f"**{total_votes}** personas han votado",
            inline=True
        )
        
        if not final:
            embed.add_field(
                name="⏱️ Estado",
                value="✅ Votación activa",
                inline=True
            )
            embed.set_footer(text="Haz clic en una opción para votar • Puedes cambiar tu voto")
        else:
            embed.set_footer(text="Votación finalizada")
        
        return embed

    async def on_timeout(self):
        # Finalizar votación automáticamente cuando expire el tiempo
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message') and self.message:
                embed = self.create_results_embed(final=True)
                await self.message.edit(embed=embed, view=self)
        except Exception as e:
            print(f"Error handling poll timeout edit: {e}")

            raise
class Poll(commands.Cog):
    """Cog para crear votaciones interactivas."""
    
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="poll", description="Crear una votación interactiva")
    @app_commands.describe(
        pregunta="La pregunta de la votación",
        opcion1="Primera opción",
        opcion2="Segunda opción",
        opcion3="Tercera opción (opcional)",
        opcion4="Cuarta opción (opcional)",
        opcion5="Quinta opción (opcional)",
        duracion="Duración en minutos (por defecto 5 minutos)"
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        pregunta: str,
        opcion1: str,
        opcion2: str,
        opcion3: Optional[str] = None,
        opcion4: Optional[str] = None,
        opcion5: Optional[str] = None,
        duracion: Optional[int] = 5
    ):
        # Recopilar opciones no vacías
        opciones = [opcion1, opcion2]
        for opcion in [opcion3, opcion4, opcion5]:
            if opcion:
                opciones.append(opcion)
        
        # Validaciones
        if len(opciones) < 2:
            await interaction.response.send_message("❌ Necesitas al menos 2 opciones para crear una votación.", ephemeral=True)
            return
        
        if len(opciones) > 25:
            await interaction.response.send_message("❌ Máximo 25 opciones permitidas.", ephemeral=True)
            return
        
        if duracion < 1 or duracion > 60:
            await interaction.response.send_message("❌ La duración debe estar entre 1 y 60 minutos.", ephemeral=True)
            return
        
        # Verificar longitud de opciones
        for i, opcion in enumerate(opciones):
            if len(opcion) > 80:
                await interaction.response.send_message(f"❌ La opción {i+1} es demasiado larga (máximo 80 caracteres).", ephemeral=True)
                return
        
        # Crear la vista de votación
        duracion_segundos = duracion * 60
        view = PollView(pregunta, opciones, interaction.user.id, duracion_segundos)
        
        # Crear embed inicial
        embed = view.create_results_embed()
        embed.add_field(
            name="⏰ Duración",
            value=f"{duracion} minutos",
            inline=True
        )
        embed.add_field(
            name="👤 Creador",
            value=interaction.user.mention,
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        view.message = message

    @app_commands.command(name="poll_simple", description="Crear una votación simple Sí/No")
    @app_commands.describe(
        pregunta="La pregunta de la votación",
        duracion="Duración en minutos (por defecto 5 minutos)"
    )
    async def poll_simple(
        self,
        interaction: discord.Interaction,
        pregunta: str,
        duracion: Optional[int] = 5
    ):
        # Crear votación simple con Sí/No
        opciones = ["✅ Sí", "❌ No"]
        
        if duracion < 1 or duracion > 60:
            await interaction.response.send_message("❌ La duración debe estar entre 1 y 60 minutos.", ephemeral=True)
            return
        
        # Crear la vista de votación
        duracion_segundos = duracion * 60
        view = PollView(pregunta, opciones, interaction.user.id, duracion_segundos)
        
        # Crear embed inicial
        embed = view.create_results_embed()
        embed.add_field(
            name="⏰ Duración",
            value=f"{duracion} minutos",
            inline=True
        )
        embed.add_field(
            name="👤 Creador",
            value=interaction.user.mention,
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        view.message = message

async def setup(bot):
    await bot.add_cog(Poll(bot))
    print("Poll cog loaded successfully.")
