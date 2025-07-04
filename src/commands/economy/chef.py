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

class ChefView(discord.ui.View):
    def __init__(self, user, plato_objetivo, ingredientes_disponibles, recompensa_base):
        super().__init__(timeout=150)  # 2.5 minutos para completar
        self.user = user
        self.plato_objetivo = plato_objetivo
        self.ingredientes_disponibles = ingredientes_disponibles
        self.ingredientes_seleccionados = []
        self.recompensa_base = recompensa_base
        self.tiempo_restante = 150
        self.preparacion_perfecta = False
        
    @discord.ui.button(label="🥕 Vegetales", style=discord.ButtonStyle.secondary)
    async def agregar_vegetales(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._agregar_ingrediente(interaction, "vegetales", "🥕")
    
    @discord.ui.button(label="🥩 Proteína", style=discord.ButtonStyle.secondary)
    async def agregar_proteina(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._agregar_ingrediente(interaction, "proteina", "🥩")
    
    @discord.ui.button(label="🌾 Carbohidratos", style=discord.ButtonStyle.secondary)
    async def agregar_carbos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._agregar_ingrediente(interaction, "carbohidratos", "🌾")
    
    @discord.ui.button(label="🧂 Especias", style=discord.ButtonStyle.secondary)
    async def agregar_especias(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._agregar_ingrediente(interaction, "especias", "🧂")
    
    @discord.ui.button(label="👨‍🍳 Cocinar", style=discord.ButtonStyle.success)
    async def cocinar_plato(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        if len(self.ingredientes_seleccionados) < 2:
            await self._actualizar_mensaje(interaction, "⚠️ **Necesitas al menos 2 ingredientes para cocinar!**")
            return
        
        await self._evaluar_plato(interaction)
    
    async def _agregar_ingrediente(self, interaction, tipo_ingrediente, emoji):
        if tipo_ingrediente in self.ingredientes_seleccionados:
            await self._actualizar_mensaje(interaction, f"⚠️ **Ya agregaste {emoji} {tipo_ingrediente}!**")
            return
        
        if len(self.ingredientes_seleccionados) >= 4:
            await self._actualizar_mensaje(interaction, "⚠️ **¡Máximo 4 ingredientes!**")
            return
        
        self.ingredientes_seleccionados.append(tipo_ingrediente)
        await self._actualizar_mensaje(interaction, f"✅ **{emoji} {tipo_ingrediente.title()} agregado!**")
    
    async def _evaluar_plato(self, interaction):
        # Verificar si la combinación es correcta
        ingredientes_objetivo = self.plato_objetivo["ingredientes"]
        ingredientes_correctos = 0
        ingredientes_extra = 0
        
        for ingrediente in self.ingredientes_seleccionados:
            if ingrediente in ingredientes_objetivo:
                ingredientes_correctos += 1
            else:
                ingredientes_extra += 1
        
        ingredientes_faltantes = len(ingredientes_objetivo) - ingredientes_correctos
        
        # Calcular puntuación
        if ingredientes_correctos == len(ingredientes_objetivo) and ingredientes_extra == 0:
            puntuacion = 100  # Perfecto
            self.preparacion_perfecta = True
        elif ingredientes_correctos == len(ingredientes_objetivo):
            puntuacion = 85 - (ingredientes_extra * 10)  # Correcto pero con extras
        else:
            puntuacion = max(20, (ingredientes_correctos * 100 // len(ingredientes_objetivo)) - (ingredientes_extra * 15))
        
        await self._completar_trabajo(interaction, puntuacion, ingredientes_correctos, ingredientes_faltantes, ingredientes_extra)
    
    async def _actualizar_mensaje(self, interaction, accion):
        progreso = len(self.ingredientes_seleccionados) / 4
        barra_progreso = '🟩' * len(self.ingredientes_seleccionados) + '⬜' * (4 - len(self.ingredientes_seleccionados))
        
        ingredientes_texto = ", ".join([f"**{ing.title()}**" for ing in self.ingredientes_seleccionados]) if self.ingredientes_seleccionados else "*Ninguno*"
        
        embed = discord.Embed(
            title="👨‍🍳 Trabajo: Chef",
            description=(
                f"🎯 **Plato objetivo:** {self.plato_objetivo['nombre']}\n"
                f"📋 **Ingredientes objetivo:** {', '.join(self.plato_objetivo['ingredientes'])}\n"
                f"🛒 **Seleccionados:** {ingredientes_texto}\n"
                f"📊 **Progreso:** {barra_progreso} ({len(self.ingredientes_seleccionados)}/4)\n\n"
                f"{accion}"
            ),
            color=discord.Color.orange()
        )
        embed.add_field(
            name="🎮 Controles:",
            value=(
                "🥕 **Vegetales** | 🥩 **Proteína** | 🌾 **Carbohidratos** | 🧂 **Especias**\n"
                "👨‍🍳 **Cocinar:** Prepara el plato (mín. 2 ingredientes)"
            ),
            inline=False
        )
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)
    
    async def _completar_trabajo(self, interaction, puntuacion, correctos, faltantes, extras):
        # Desactivar todos los botones
        self.agregar_vegetales.disabled = True
        self.agregar_proteina.disabled = True
        self.agregar_carbos.disabled = True
        self.agregar_especias.disabled = True
        self.cocinar_plato.disabled = True
        self.stop()
        
        # Tipo de trabajo y usuario
        user_id = self.user.id
        tipo_trabajo = 'chef'
        
        # Aplicar bonificación de nivel a la recompensa base
        recompensa_base_con_nivel = calcular_recompensa(self.recompensa_base, user_id, tipo_trabajo)
        
        # Calcular recompensa
        multiplicador = puntuacion / 100
        recompensa_final = int(recompensa_base_con_nivel * multiplicador)
        
        # Determinar resultado
        if puntuacion >= 95:
            resultado = "🏆 ¡OBRA MAESTRA!"
            color = discord.Color.gold()
        elif puntuacion >= 80:
            resultado = "🌟 ¡Excelente!"
            color = discord.Color.green()
        elif puntuacion >= 60:
            resultado = "✅ Bien hecho"
            color = discord.Color.blue()
        elif puntuacion >= 40:
            resultado = "⚠️ Mejorable"
            color = discord.Color.orange()
        else:
            resultado = "❌ ¡Desastre culinario!"
            color = discord.Color.red()
        
        # Añadir experiencia (depende de la puntuación)
        xp_ganada = int(puntuacion / 5)  # 20 XP máximo por trabajo perfecto
        if self.preparacion_perfecta:
            xp_ganada += 10  # Bonus por preparación perfecta
        
        # Registrar progreso y verificar subida de nivel
        resultado_nivel = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
        subio_nivel = resultado_nivel["subio_nivel"]
        nivel_nuevo = resultado_nivel["nivel_nuevo"]
        xp_actual = resultado_nivel["xp_actual"]
        xp_para_siguiente = resultado_nivel["xp_para_siguiente"]
        
        # Obtener información del nivel para mostrar
        if nivel_nuevo < 10:
            progreso = xp_actual / xp_para_siguiente if xp_para_siguiente > 0 else 1
            barra_progreso = '█' * int(progreso * 10) + '░' * (10 - int(progreso * 10))
            info_nivel = f"**Nivel {nivel_nuevo}** | {barra_progreso} {xp_actual}/{xp_para_siguiente} XP"
        else:
            info_nivel = f"**Nivel {nivel_nuevo}** | ✅ Nivel máximo alcanzado"
        
        # Actualizar balance
        if recompensa_final > 0:
            saldo_actual = get_balance(user_id)
            set_balance(user_id, saldo_actual + recompensa_final)
            registrar_transaccion(user_id, recompensa_final, "Trabajo: Chef completado")
        
        # Obtener bonificación de nivel para mostrar
        bonificacion_nivel_porcentaje = int((calcular_recompensa(1, user_id, tipo_trabajo) - 1) * 100)
        
        embed = discord.Embed(
            title=f"👨‍🍳 {resultado}",
            description=(
                f"🍽️ **Plato preparado:** {self.plato_objetivo['nombre']}\n"
                f"📊 **Puntuación:** {puntuacion}/100\n"
                f"✅ **Ingredientes correctos:** {correctos}\n"
                f"❌ **Ingredientes faltantes:** {faltantes}\n"
                f"➕ **Ingredientes extra:** {extras}\n"
                f"🌟 **Bonus por nivel:** +{bonificacion_nivel_porcentaje}%\n"
                f"💰 **Recompensa:** {recompensa_final} monedas\n\n"
                f"📊 {info_nivel}\n"
                f"✨ **XP ganada:** +{xp_ganada} XP"
            ),
            color=color
        )
        
        if self.preparacion_perfecta:
            embed.add_field(
                name="🎉 ¡Bonificación Perfecta!",
                value="¡Preparaste el plato exactamente como se pedía!",
                inline=False
            )
            
        # Añadir mensaje de subida de nivel si corresponde
        if subio_nivel:
            from .niveles_trabajo import TIPOS_TRABAJO
            nueva_bonificacion = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel_nuevo, "Sin bonificación")
            embed.add_field(
                name="🎊 ¡SUBISTE DE NIVEL!",
                value=f"Tu nivel de Chef ha subido a **{nivel_nuevo}**\n"
                      f"🌟 **Nueva bonificación:** {nueva_bonificacion}",
                inline=False
            )
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

async def iniciar_trabajo_chef(interaction: discord.Interaction):
    """Función principal para iniciar el trabajo de chef."""
    user_id = interaction.user.id
    tipo_trabajo = 'chef'
    
    # Obtener nivel del trabajo y bonificaciones
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel = nivel_info["nivel"]
    
    # Verificar energía del usuario - aplicar bonificación por nivel
    energia_actual = get_energia(user_id)
    energia_base = 20
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
    
    # Platos disponibles con sus ingredientes requeridos
    platos_disponibles = [
        {
            "nombre": "🍝 Pasta Bolognesa",
            "ingredientes": ["proteina", "carbohidratos", "especias"],
            "dificultad": "Fácil"
        },
        {
            "nombre": "🥗 Ensalada Gourmet",
            "ingredientes": ["vegetales", "proteina", "especias"],
            "dificultad": "Fácil"
        },
        {
            "nombre": "🍲 Guiso Completo",
            "ingredientes": ["vegetales", "proteina", "carbohidratos", "especias"],
            "dificultad": "Difícil"
        },
        {
            "nombre": "🍛 Arroz con Pollo",
            "ingredientes": ["proteina", "carbohidratos", "vegetales"],
            "dificultad": "Medio"
        },
        {
            "nombre": "🌮 Tacos Especiales",
            "ingredientes": ["proteina", "vegetales", "especias"],
            "dificultad": "Medio"
        }
    ]
    
    # Seleccionar plato aleatorio
    plato_objetivo = random.choice(platos_disponibles)
    
    # Calcular recompensa base según dificultad
    if plato_objetivo["dificultad"] == "Fácil":
        recompensa_base = 150
    elif plato_objetivo["dificultad"] == "Medio":
        recompensa_base = 200
    else:  # Difícil
        recompensa_base = 300
    
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
    
    # Ingredientes disponibles
    ingredientes_disponibles = ["vegetales", "proteina", "carbohidratos", "especias"]
    
    embed = discord.Embed(
        title="👨‍🍳 Trabajo: Chef",
        description=(
            f"🎯 **Plato a preparar:** {plato_objetivo['nombre']}\n"
            f"📋 **Ingredientes necesarios:** {', '.join(plato_objetivo['ingredientes'])}\n"
            f"🏆 **Dificultad:** {plato_objetivo['dificultad']}\n"
            f"💰 **Recompensa:** {recompensa_con_nivel}+ monedas\n"
            f"⏱️ **Tiempo límite:** 2.5 minutos\n\n"
            f"📊 **Nivel actual:** {nivel_actual} ({'+' + str(int(bonificacion_recompensa * 100)) + '%' if bonificacion_recompensa > 0 else '0%'} recompensa, {'-' + str(int((1-bonificacion_energia) * 100)) + '%' if bonificacion_energia < 1 else '0%'} energía)\n"
            f"🌟 **Bonificación de nivel:** {bonificacion_actual}\n\n"
            f"🔍 **Selecciona los ingredientes correctos...**"
        ),
        color=discord.Color.orange()
    )
    embed.add_field(
        name="🎮 Cómo jugar:",
        value=(
            "1️⃣ Selecciona los ingredientes necesarios\n"
            "2️⃣ Evita ingredientes innecesarios (penalizan)\n"
            "3️⃣ ¡Cocina cuando tengas todo listo!\n"
            "4️⃣ La precisión determina tu recompensa"
        ),
        inline=False
    )
    
    view = ChefView(interaction.user, plato_objetivo, ingredientes_disponibles, recompensa_base)
    await interaction.response.send_message(embed=embed, view=view)
