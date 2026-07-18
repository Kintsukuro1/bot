import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from src.utils.dynamic_difficulty import DynamicDifficulty
from src.services import UserService

class DifficultyStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Ver tus estadísticas de juego y nivel de dificultad actual")
    async def stats(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_name = interaction.user.name
        await UserService.ensure_user(user_id, user_name)
        
        # Obtener estadísticas detalladas de forma asíncrona
        stats = await asyncio.to_thread(DynamicDifficulty.get_difficulty_stats, user_id)
        
        if stats['status'] == 'new_player':
            embed = discord.Embed(
                title="📊 Tus Estadísticas de Juego",
                description="🆕 **Jugador Nuevo**\n\nJuega algunos juegos para generar estadísticas personalizadas.",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="💡 Sistema de Dificultad Dinámica",
                value=(
                    "El casino ajusta automáticamente la dificultad basándose en:\n"
                    "• Tu historial de victorias y derrotas\n"
                    "• Patrones de apuesta\n"
                    "• Rachas de suerte\n"
                    "• Frecuencia de juego\n"
                    "• Tendencias de balance"
                ),
                inline=False
            )
        else:
            # Determinar color basado en dificultad
            difficulty = stats['current_difficulty']
            if difficulty > 0.2:
                color = discord.Color.red()
                difficulty_emoji = "🔥"
                difficulty_text = "MUY ALTA"
            elif difficulty > 0.1:
                color = discord.Color.orange()
                difficulty_emoji = "⚠️"
                difficulty_text = "ALTA"
            elif difficulty > 0.05:
                color = discord.Color.yellow()
                difficulty_emoji = "📈"
                difficulty_text = "MEDIA-ALTA"
            elif difficulty > -0.05:
                color = discord.Color.blue()
                difficulty_emoji = "🎯"
                difficulty_text = "EQUILIBRADA"
            elif difficulty > -0.15:
                color = discord.Color.green()
                difficulty_emoji = "💙"
                difficulty_text = "MEDIA-BAJA"
            else:
                color = discord.Color.from_rgb(0, 255, 127)
                difficulty_emoji = "🍀"
                difficulty_text = "BAJA"
            
            embed = discord.Embed(
                title="📊 Tus Estadísticas de Juego",
                description=f"{difficulty_emoji} **Dificultad Actual:** {difficulty_text} ({difficulty:+.1%})",
                color=color
            )
            
            # Estadísticas básicas
            total_games = stats['total_games']
            win_rate = stats['win_rate']
            
            embed.add_field(
                name="🎮 Historial de Juegos",
                value=(
                    f"**Total jugados:** {total_games:,}\n"
                    f"**Tasa de victoria:** {win_rate:.1%}\n"
                    f"**Promedio de apuesta:** {stats['avg_bet']:,.0f} monedas"
                ),
                inline=True
            )
            
            # Rachas
            hot_streak = stats['hot_streak']
            cold_streak = stats['cold_streak']
            
            streak_text = ""
            if hot_streak > 0:
                streak_text = f"🔥 **Racha ganadora:** {hot_streak} juegos"
            elif cold_streak > 0:
                streak_text = f"❄️ **Racha perdedora:** {cold_streak} juegos"
            else:
                streak_text = "⚖️ **Sin racha actual**"
            
            embed.add_field(
                name="🎯 Rachas",
                value=streak_text,
                inline=True
            )
            
            # Perfil de riesgo
            risk_profile = stats['risk_profile']
            risk_emoji = {
                'CONSERVATIVE': '🛡️',
                'BALANCED': '⚖️',
                'AGGRESSIVE': '⚡'
            }
            
            embed.add_field(
                name="📈 Perfil de Riesgo",
                value=f"{risk_emoji.get(risk_profile, '⚖️')} **{risk_profile.title()}**",
                inline=True
            )
            
            # Actividad reciente
            recent_games = stats['recent_games_24h']
            if recent_games > 15:
                activity_text = f"🚀 **Muy activo** ({recent_games} juegos hoy)"
            elif recent_games > 5:
                activity_text = f"📊 **Activo** ({recent_games} juegos hoy)"
            else:
                activity_text = f"😴 **Poco activo** ({recent_games} juegos hoy)"
            
            embed.add_field(
                name="⏰ Actividad Reciente",
                value=activity_text,
                inline=True
            )
            
            # Explicación del sistema
            embed.add_field(
                name="💡 ¿Cómo funciona?",
                value=(
                    "La dificultad se ajusta automáticamente según tu rendimiento:\n"
                    f"• **{difficulty_emoji} Dificultad {difficulty_text.lower()}** afecta tus probabilidades\n"
                    "• El sistema aprende de tus patrones de juego\n"
                    "• Mantiene el equilibrio y la diversión"
                ),
                inline=False
            )
            
            # Último juego
            if stats['last_game']:
                embed.set_footer(text=f"Último juego: {stats['last_game'].strftime('%d/%m/%Y %H:%M')} · Usa /provably_fair para ver el esquema criptográfico")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="difficulty", description="Ver información detallada sobre el sistema de dificultad")
    async def difficulty_info(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎯 Sistema de Dificultad Dinámica",
            description=(
                "El casino utiliza un sistema avanzado que ajusta automáticamente "
                "la dificultad de los juegos basándose en tu comportamiento y rendimiento."
            ),
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="📊 Factores Analizados",
            value=(
                "• **Tasa de Victoria** (25%): Tu historial de victorias vs derrotas\n"
                "• **Rachas** (20%): Secuencias de victorias o derrotas consecutivas\n"
                "• **Patrón de Apuestas** (15%): Cómo varían tus apuestas\n"
                "• **Actividad Temporal** (10%): Frecuencia de juego\n"
                "• **Perfil de Riesgo** (15%): Si eres conservador o agresivo\n"
                "• **Tendencia de Balance** (15%): Si estás ganando o perdiendo dinero"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎮 Efectos en los Juegos",
            value=(
                "**🍀 Dificultad Baja:** Mejores probabilidades, más oportunidades\n"
                "**🎯 Dificultad Equilibrada:** Probabilidades estándar\n"
                "**🔥 Dificultad Alta:** Mayor desafío, pero recompensas iguales"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💡 Consejos",
            value=(
                "• El sistema premia la consistencia\n"
                "• Varía tus estrategias de apuesta\n"
                "• Las rachas largas aumentan la dificultad\n"
                "• Tómate descansos para resetear patrones\n"
                "• El sistema se adapta en tiempo real"
            ),
            inline=False
        )
        
        embed.set_footer(text="Usa /stats para ver tu nivel actual de dificultad")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(DifficultyStats(bot))
    print("DifficultyStats cog loaded successfully.")
