import discord
import random
from src.db import get_balance, set_balance, registrar_transaccion
from .energia import get_energia, set_energia
from .niveles_trabajo import (
    add_experiencia_trabajo, 
    calcular_energia_requerida, 
    calcular_recompensa, 
    get_nivel_trabajo
)

class ArtistaView(discord.ui.View):
    def __init__(self, user, obra_objetivo, recompensa_base):
        super().__init__(timeout=120)  # 2 minutos para completar
        self.user = user
        self.obra_objetivo = obra_objetivo
        self.recompensa_base = recompensa_base
        self.colores_seleccionados = []
        self.tecnicas_usadas = []
        self.creatividad_bonus = 0
        self.pinceladas = 0
        
    @discord.ui.button(label="🔴 Rojo", style=discord.ButtonStyle.danger)
    async def color_rojo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._usar_color(interaction, "rojo", "🔴")
    
    @discord.ui.button(label="🔵 Azul", style=discord.ButtonStyle.primary)
    async def color_azul(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._usar_color(interaction, "azul", "🔵")
    
    @discord.ui.button(label="🟡 Amarillo", style=discord.ButtonStyle.secondary)
    async def color_amarillo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._usar_color(interaction, "amarillo", "🟡")
    
    @discord.ui.button(label="🟢 Verde", style=discord.ButtonStyle.success)
    async def color_verde(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._usar_color(interaction, "verde", "🟢")
    
    @discord.ui.button(label="🖌️ Pincelar", style=discord.ButtonStyle.secondary)
    async def pincelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        if not self.colores_seleccionados:
            await self._actualizar_mensaje(interaction, "⚠️ **¡Necesitas seleccionar al menos un color primero!**")
            return
        
        self.pinceladas += 1
        
        # Posibilidad de técnica especial
        if random.random() < 0.3:  # 30% chance
            tecnica = random.choice(["difuminado", "textura", "sombras", "luces"])
            if tecnica not in self.tecnicas_usadas:
                self.tecnicas_usadas.append(tecnica)
                self.creatividad_bonus += 10
                await self._actualizar_mensaje(interaction, f"✨ **¡Técnica especial: {tecnica.title()}! (+10 creatividad)**")
            else:
                await self._actualizar_mensaje(interaction, f"🖌️ **Pincelada aplicada... ({self.pinceladas} total)**")
        else:
            await self._actualizar_mensaje(interaction, f"🖌️ **Pincelada aplicada... ({self.pinceladas} total)**")
    
    @discord.ui.button(label="🎨 Finalizar Obra", style=discord.ButtonStyle.success)
    async def finalizar_obra(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        if len(self.colores_seleccionados) < 2:
            await self._actualizar_mensaje(interaction, "⚠️ **Necesitas al menos 2 colores para finalizar la obra!**")
            return
        
        if self.pinceladas < 3:
            await self._actualizar_mensaje(interaction, "⚠️ **Necesitas al menos 3 pinceladas para completar la obra!**")
            return
        
        await self._evaluar_obra(interaction)
    
    async def _usar_color(self, interaction, color, emoji):
        if color in self.colores_seleccionados:
            await self._actualizar_mensaje(interaction, f"⚠️ **Ya usaste {emoji} {color}!**")
            return
        
        if len(self.colores_seleccionados) >= 4:
            await self._actualizar_mensaje(interaction, "⚠️ **¡Máximo 4 colores por obra!**")
            return
        
        self.colores_seleccionados.append(color)
        
        # Verificar combinaciones especiales
        combinacion_bonus = self._verificar_combinacion()
        if combinacion_bonus > 0:
            self.creatividad_bonus += combinacion_bonus
            await self._actualizar_mensaje(interaction, f"✅ **{emoji} {color.title()} agregado! +{combinacion_bonus} por combinación!**")
        else:
            await self._actualizar_mensaje(interaction, f"✅ **{emoji} {color.title()} agregado a la paleta!**")
    
    def _verificar_combinacion(self):
        """Verificar si hay combinaciones de colores especiales."""
        colores = set(self.colores_seleccionados)
        
        # Combinaciones especiales
        if {"rojo", "azul", "amarillo"}.issubset(colores):
            return 20  # Colores primarios
        elif {"rojo", "azul"}.issubset(colores):
            return 10  # Contraste frío-cálido
        elif {"amarillo", "verde"}.issubset(colores):
            return 10  # Naturaleza
        elif {"rojo", "amarillo"}.issubset(colores):
            return 10  # Calidez
        
        return 0
    
    async def _evaluar_obra(self, interaction):
        # Calcular puntuación
        colores_objetivo = self.obra_objetivo["colores"]
        colores_correctos = len(set(self.colores_seleccionados) & set(colores_objetivo))
        colores_totales = len(set(self.colores_seleccionados) | set(colores_objetivo))
        
        # Puntuación base por colores
        precision_colores = (colores_correctos / len(colores_objetivo)) * 60
        
        # Bonificación por técnica (pinceladas)
        bonus_tecnica = min(30, self.pinceladas * 3)  # Máximo 30 puntos
        
        # Bonificación por creatividad
        bonus_creatividad = min(40, self.creatividad_bonus)  # Máximo 40 puntos
        
        puntuacion_total = precision_colores + bonus_tecnica + bonus_creatividad
        puntuacion_total = min(100, puntuacion_total)  # Máximo 100
        
        await self._completar_trabajo(interaction, puntuacion_total, colores_correctos, len(colores_objetivo))
    
    async def _actualizar_mensaje(self, interaction, accion):
        progreso_colores = len(self.colores_seleccionados) / 4
        barra_colores = '🎨' * len(self.colores_seleccionados) + '⬜' * (4 - len(self.colores_seleccionados))
        
        colores_texto = ", ".join([f"**{color.title()}**" for color in self.colores_seleccionados]) if self.colores_seleccionados else "*Ninguno*"
        tecnicas_texto = ", ".join([f"**{tec.title()}**" for tec in self.tecnicas_usadas]) if self.tecnicas_usadas else "*Ninguna*"
        
        embed = discord.Embed(
            title="🎨 Trabajo: Artista",
            description=(
                f"🖼️ **Obra objetivo:** {self.obra_objetivo['nombre']}\n"
                f"🎯 **Colores sugeridos:** {', '.join(self.obra_objetivo['colores'])}\n"
                f"🎨 **Colores usados:** {colores_texto}\n"
                f"🖌️ **Pinceladas:** {self.pinceladas}\n"
                f"✨ **Técnicas:** {tecnicas_texto}\n"
                f"📊 **Progreso:** {barra_colores} ({len(self.colores_seleccionados)}/4)\n"
                f"🌟 **Creatividad:** +{self.creatividad_bonus}\n\n"
                f"{accion}"
            ),
            color=discord.Color.purple()
        )
        embed.add_field(
            name="🎮 Controles:",
            value=(
                "🔴🔵🟡🟢 **Colores** | 🖌️ **Pincelar** (técnicas especiales)\n"
                "🎨 **Finalizar:** Completa tu obra (mín. 2 colores + 3 pinceladas)"
            ),
            inline=False
        )
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)
    
    async def _completar_trabajo(self, interaction, puntuacion, colores_correctos, colores_objetivo_total):
        # Desactivar todos los botones
        self.color_rojo.disabled = True
        self.color_azul.disabled = True
        self.color_amarillo.disabled = True
        self.color_verde.disabled = True
        self.pincelar.disabled = True
        self.finalizar_obra.disabled = True
        self.stop()
        
        # Obtener bonificación por nivel
        user_id = self.user.id
        tipo_trabajo = 'artista'
            
        # Aplicar bonificación de nivel a la recompensa base
        recompensa_base_con_nivel = calcular_recompensa(self.recompensa_base, user_id, tipo_trabajo)
            
        # Calcular recompensa final con multiplicador de puntuación
        multiplicador = puntuacion / 100
        recompensa_final = int(recompensa_base_con_nivel * multiplicador)
        
        # Determinar resultado
        if puntuacion >= 90:
            resultado = "🏆 ¡OBRA MAESTRA!"
            color = discord.Color.gold()
        elif puntuacion >= 75:
            resultado = "🌟 ¡Arte Excepcional!"
            color = discord.Color.purple()
        elif puntuacion >= 60:
            resultado = "✅ Buen Trabajo"
            color = discord.Color.blue()
        elif puntuacion >= 40:
            resultado = "⚠️ Arte Amateur"
            color = discord.Color.orange()
        else:
            resultado = "❌ Necesitas Práctica"
            color = discord.Color.red()
        
        # Añadir experiencia (depende de la dificultad y éxito)
        xp_ganada = int(puntuacion / 10) * colores_objetivo_total  # XP base según puntuación
        
        if colores_correctos == colores_objetivo_total:
            xp_ganada += 15  # Bonus por precisión de colores
        
        if self.creatividad_bonus >= 30:
            xp_ganada += 10  # Bonus por creatividad
            
        # Registrar progreso y verificar subida de nivel
        resultado_nivel = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
        subio_nivel = resultado_nivel["subio_nivel"]
        nivel_nuevo = resultado_nivel["nivel_nuevo"]
        xp_actual = resultado_nivel["xp_actual"]
        xp_para_siguiente = resultado_nivel["xp_para_siguiente"]
        
        # Actualizar balance
        if recompensa_final > 0:
            saldo_actual = get_balance(user_id)
            set_balance(user_id, saldo_actual + recompensa_final)
            registrar_transaccion(user_id, recompensa_final, "Trabajo: Artista completado")
        
        # Obtener información del nivel para mostrar
        if nivel_nuevo < 10:
            progreso = xp_actual / xp_para_siguiente if xp_para_siguiente > 0 else 1
            barra_progreso = '█' * int(progreso * 10) + '░' * (10 - int(progreso * 10))
            info_nivel = f"**Nivel {nivel_nuevo}** | {barra_progreso} {xp_actual}/{xp_para_siguiente} XP"
        else:
            info_nivel = f"**Nivel {nivel_nuevo}** | ✅ Nivel máximo alcanzado"
        
        embed = discord.Embed(
            title=f"🎨 {resultado}",
            description=(
                f"🖼️ **Obra creada:** {self.obra_objetivo['nombre']}\n"
                f"📊 **Puntuación:** {int(puntuacion)}/100\n"
                f"🎯 **Precisión de colores:** {colores_correctos}/{colores_objetivo_total}\n"
                f"🖌️ **Pinceladas totales:** {self.pinceladas}\n"
                f"✨ **Bonus creatividad:** +{self.creatividad_bonus}\n"
                f"🌟 **Bonus por nivel:** +{int((calcular_recompensa(1, user_id, tipo_trabajo) - 1) * 100)}%\n"
                f"💰 **Recompensa:** {recompensa_final} monedas\n\n"
                f"📊 {info_nivel}\n"
                f"✨ **XP ganada:** +{xp_ganada} XP"
            ),
            color=color
        )
        
        # Añadir mensaje de subida de nivel si corresponde
        if subio_nivel:
            from .niveles_trabajo import TIPOS_TRABAJO
            nueva_bonificacion = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel_nuevo, "Sin bonificación")
            embed.add_field(
                name="🎊 ¡SUBISTE DE NIVEL!",
                value=f"Tu nivel de Artista ha subido a **{nivel_nuevo}**\n"
                      f"🌟 **Nueva bonificación:** {nueva_bonificacion}",
                inline=False
            )
        
        if len(self.tecnicas_usadas) >= 3:
            embed.add_field(
                name="🎨 ¡Maestro de Técnicas!",
                value=f"Dominaste: {', '.join(self.tecnicas_usadas)}",
                inline=False
            )
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

async def iniciar_trabajo_artista(interaction: discord.Interaction):
    """Función principal para iniciar el trabajo de artista."""
    user_id = interaction.user.id
    tipo_trabajo = 'artista'
    
    # Obtener nivel del trabajo y bonificaciones
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel = nivel_info["nivel"]
    
    # Verificar energía del usuario - aplicar bonificación por nivel
    energia_actual = get_energia(user_id)
    energia_base = 15
    energia_requerida = calcular_energia_requerida(energia_base, user_id, tipo_trabajo)
    
    if energia_actual < energia_requerida:
        embed = discord.Embed(
            title="⚡ Sin Energía",
            description=(
                f"❌ No tienes suficiente energía para trabajar.\n"
                f"🔋 **Energía actual:** {energia_actual}/100\n"
                f"⚡ **Energía requerida:** {energia_requerida}\n\n"
                f"💡 *La energía se recarga automáticamente*"
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Consumir energía
    set_energia(user_id, energia_actual - energia_requerida)
    
    # Obras disponibles
    obras_disponibles = [
        {
            "nombre": "🌅 Amanecer en el Campo",
            "colores": ["amarillo", "rojo", "verde"],
            "dificultad": "Fácil"
        },
        {
            "nombre": "🌊 Océano Tormentoso",
            "colores": ["azul", "verde"],
            "dificultad": "Fácil"
        },
        {
            "nombre": "🍂 Bosque Otoñal",
            "colores": ["rojo", "amarillo", "verde"],
            "dificultad": "Medio"
        },
        {
            "nombre": "🌆 Ciudad al Atardecer",
            "colores": ["rojo", "amarillo", "azul"],
            "dificultad": "Medio"
        },
        {
            "nombre": "🎭 Retrato Abstracto",
            "colores": ["rojo", "azul", "amarillo", "verde"],
            "dificultad": "Difícil"
        }
    ]
    
    # Seleccionar obra aleatoria
    obra_objetivo = random.choice(obras_disponibles)
    
    # Calcular recompensa base según dificultad
    if obra_objetivo["dificultad"] == "Fácil":
        recompensa_base = 120
    elif obra_objetivo["dificultad"] == "Medio":
        recompensa_base = 180
    else:  # Difícil
        recompensa_base = 250
    
    # Aplicar bonificaciones de nivel
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel_actual = nivel_info["nivel"]
    bonificacion_recompensa = calcular_recompensa(1, user_id, tipo_trabajo) - 1
    bonificacion_energia = calcular_energia_requerida(100, user_id, tipo_trabajo) / 100
    
    # Mostrar recompensa con bonus de nivel aplicado
    recompensa_con_nivel = calcular_recompensa(recompensa_base, user_id, tipo_trabajo)
    
    # Info de nivel para mostrar
    from .niveles_trabajo import TIPOS_TRABAJO
    bonificacion_actual = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel_actual, "Sin bonificaciones")
    
    embed = discord.Embed(
        title="🎨 Trabajo: Artista",
        description=(
            f"🖼️ **Obra a crear:** {obra_objetivo['nombre']}\n"
            f"🎯 **Colores sugeridos:** {', '.join(obra_objetivo['colores'])}\n"
            f"🏆 **Dificultad:** {obra_objetivo['dificultad']}\n"
            f"💰 **Recompensa:** {recompensa_con_nivel}+ monedas\n"
            f"⏱️ **Tiempo límite:** 2 minutos\n\n"
            f"📊 **Nivel actual:** {nivel_actual} ({'+' + str(int(bonificacion_recompensa * 100)) + '%' if bonificacion_recompensa > 0 else '0%'} recompensa, {'-' + str(int((1-bonificacion_energia) * 100)) + '%' if bonificacion_energia < 1 else '0%'} energía)\n"
            f"🌟 **Bonificación de nivel:** {bonificacion_actual}\n\n"
            f"🎨 **¡Deja volar tu creatividad!**"
        ),
        color=discord.Color.purple()
    )
    embed.add_field(
        name="🎮 Cómo jugar:",
        value=(
            "1️⃣ Selecciona colores para tu paleta\n"
            "2️⃣ Usa pinceladas para aplicar técnicas\n"
            "3️⃣ Busca combinaciones especiales (+bonus)\n"
            "4️⃣ ¡Finaliza cuando estés satisfecho!"
        ),
        inline=False
    )
    
    view = ArtistaView(interaction.user, obra_objetivo, recompensa_base)
    await interaction.response.send_message(embed=embed, view=view)
