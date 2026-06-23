import discord
import random
from src.db import get_balance, set_balance, registrar_transaccion, usuario_tiene_mejora
from .energia import get_energia, set_energia
from .niveles_trabajo import (
    add_experiencia_trabajo, 
    calcular_energia_requerida, 
    calcular_recompensa, 
    get_nivel_trabajo,
    TIPOS_TRABAJO
)
import asyncio

class SecretIngredientSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Ninguno 🥣", value="ninguno", description="No usar ingrediente secreto"),
            discord.SelectOption(label="Trufa Silvestre 🍄", value="trufa", description="Ideal para perfiles terrosos y de bosque"),
            discord.SelectOption(label="Láminas de Oro 🪙", value="oro", description="Ideal para perfiles gourmet y lujosos"),
            discord.SelectOption(label="Azafrán Exótico 🌺", value="azafran", description="Ideal para perfiles aromáticos y exóticos")
        ]
        super().__init__(placeholder="Elige un ingrediente secreto opcional...", min_values=1, max_values=1, options=options, row=2)
        
    async def callback(self, interaction: discord.Interaction):
        self.view.ingrediente_secreto_seleccionado = self.values[0]
        label_secreto = self.values[0].title()
        if self.values[0] == "trufa":
            label_secreto = "Trufa Silvestre 🍄"
        elif self.values[0] == "oro":
            label_secreto = "Láminas de Oro 🪙"
        elif self.values[0] == "azafran":
            label_secreto = "Azafrán Exótico 🌺"
        else:
            label_secreto = "Ninguno 🥣"
        await self.view._actualizar_mensaje(interaction, f"✨ **Ingrediente secreto seleccionado: {label_secreto}**")

class ChefView(discord.ui.View):
    def __init__(self, user, plato_objetivo, ingredientes_disponibles, recompensa_base, nivel):
        super().__init__(timeout=150)  # 2.5 minutos para completar
        self.user = user
        self.plato_objetivo = plato_objetivo
        self.ingredientes_disponibles = ingredientes_disponibles
        self.ingredientes_seleccionados = []
        self.recompensa_base = recompensa_base
        self.nivel = nivel
        self.tiempo_restante = 150
        self.preparacion_perfecta = False
        
        self.ingrediente_secreto_seleccionado = "ninguno"
        self.temperatura = "Media"
        
        # Desbloqueos interactivos por nivel
        if self.nivel >= 5:
            self.add_item(SecretIngredientSelect())
        if self.nivel < 8:
            self.remove_item(self.ciclar_temperatura)
        
    @discord.ui.button(label="🥕 Vegetales", style=discord.ButtonStyle.secondary)
    async def agregar_vegetales(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._agregar_ingrediente(interaction, "vegetales", "🥕")
    
    @discord.ui.button(label="🥩 Proteína", style=discord.ButtonStyle.secondary)
    async def agregar_proteina(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._agregar_ingrediente(interaction, "proteina", "🥩")
    
    @discord.ui.button(label="🌾 Carbohidratos", style=discord.ButtonStyle.secondary)
    async def agregar_carbos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._agregar_ingrediente(interaction, "carbohidratos", "🌾")
    
    @discord.ui.button(label="🧂 Especias", style=discord.ButtonStyle.secondary)
    async def agregar_especias(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._agregar_ingrediente(interaction, "especias", "🧂")
        
    @discord.ui.button(label="🌡️ Temp: Media", style=discord.ButtonStyle.secondary, row=1)
    async def ciclar_temperatura(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        await interaction.response.defer()
            
        if self.temperatura == "Baja":
            self.temperatura = "Media"
            button.label = "🌡️ Temp: Media"
            button.style = discord.ButtonStyle.primary
        elif self.temperatura == "Media":
            self.temperatura = "Alta"
            button.label = "🌡️ Temp: Alta"
            button.style = discord.ButtonStyle.danger
        else:
            self.temperatura = "Baja"
            button.label = "🌡️ Temp: Baja"
            button.style = discord.ButtonStyle.secondary
            
        await self._actualizar_mensaje(interaction, f"🌡️ **Temperatura cambiada a {self.temperatura}!**")
    
    @discord.ui.button(label="👨‍🍳 Cocinar", style=discord.ButtonStyle.success)
    async def cocinar_plato(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
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
        # Verificar ingredientes básicos
        ingredientes_objetivo = self.plato_objetivo["ingredientes"]
        ingredientes_correctos = 0
        ingredientes_extra = 0
        
        for ingrediente in self.ingredientes_seleccionados:
            if ingrediente in ingredientes_objetivo:
                ingredientes_correctos += 1
            else:
                ingredientes_extra += 1
        
        ingredientes_faltantes = len(ingredientes_objetivo) - ingredientes_correctos
        
        # Calcular puntuación base
        if ingredientes_correctos == len(ingredientes_objetivo) and ingredientes_extra == 0:
            puntuacion = 100  # Perfecto
            self.preparacion_perfecta = True
        elif ingredientes_correctos == len(ingredientes_objetivo):
            puntuacion = 85 - (ingredientes_extra * 10)  # Correcto pero con extras
        else:
            puntuacion = max(20, (ingredientes_correctos * 100 // len(ingredientes_objetivo)) - (ingredientes_extra * 15))
        
        # Modificador por Ingrediente Secreto (Nivel >= 5)
        secreto_multiplier = 1.0
        secreto_feedback = ""
        secreto_xp_bonus = 0
        
        if self.nivel >= 5 and self.ingrediente_secreto_seleccionado != "ninguno":
            if self.ingrediente_secreto_seleccionado == self.plato_objetivo.get("secret_ideal"):
                secreto_multiplier = 1.3
                secreto_xp_bonus = 20
                secreto_feedback = f"\n✨ **¡Ingrediente Secreto Perfecto! (+30% monedas, +20 XP)**"
            else:
                secreto_multiplier = 0.8
                secreto_feedback = f"\n❌ **El ingrediente secreto arruinó el perfil de sabor. (-20% monedas)**"
                
        # Modificador por Temperatura (Nivel >= 8)
        temp_multiplier = 1.0
        temp_feedback = ""
        
        if self.nivel >= 8:
            if self.temperatura == self.plato_objetivo.get("temp_ideal"):
                temp_multiplier = 2.0
                temp_feedback = f"\n🌡️ **¡Punto de cocción perfecto! (Recompensa x2)**"
            else:
                temp_multiplier = 0.5
                temp_feedback = f"\n🌡️ **¡Plato mal cocinado (crudo/quemado)! (Recompensa x0.5)**"
                self.preparacion_perfecta = False  # No es perfecto si falló cocción
        
        await self._completar_trabajo(
            interaction, puntuacion, ingredientes_correctos, ingredientes_faltantes, ingredientes_extra,
            secreto_multiplier, secreto_feedback, secreto_xp_bonus, temp_multiplier, temp_feedback
        )
    
    async def _actualizar_mensaje(self, interaction, accion):
        progreso = len(self.ingredientes_seleccionados) / 4
        barra_progreso = '🟩' * len(self.ingredientes_seleccionados) + '⬜' * (4 - len(self.ingredientes_seleccionados))
        
        ingredientes_texto = ", ".join([f"**{ing.title()}**" for ing in self.ingredientes_seleccionados]) if self.ingredientes_seleccionados else "*Ninguno*"
        
        secreto_msg = ""
        if self.nivel >= 5:
            label_secreto = self.ingrediente_secreto_seleccionado.title()
            if self.ingrediente_secreto_seleccionado == "trufa":
                label_secreto = "Trufa Silvestre 🍄"
            elif self.ingrediente_secreto_seleccionado == "oro":
                label_secreto = "Láminas de Oro 🪙"
            elif self.ingrediente_secreto_seleccionado == "azafran":
                label_secreto = "Azafrán Exótico 🌺"
            else:
                label_secreto = "Ninguno 🥣"
            secreto_msg = f"✨ **Ingrediente Secreto:** {label_secreto}\n"
            if "pista_secreta" in self.plato_objetivo:
                secreto_msg += f"💡 *Pista especial:* {self.plato_objetivo['pista_secreta']}\n"
                
        temp_msg = ""
        if self.nivel >= 8:
            temp_msg = f"🌡️ **Temperatura actual:** {self.temperatura}\n💡 *Pista cocción:* {self.plato_objetivo['pista_temp']}\n"
            
        embed = discord.Embed(
            title="👨‍🍳 Trabajo: Chef",
            description=(
                f"🎯 **Plato objetivo:** {self.plato_objetivo['nombre']}\n"
                f"📋 **Ingredientes objetivo:** {', '.join(self.plato_objetivo['ingredientes'])}\n"
                f"🛒 **Seleccionados:** {ingredientes_texto}\n"
                f"📊 **Progreso:** {barra_progreso} ({len(self.ingredientes_seleccionados)}/4)\n\n"
                f"{secreto_msg}"
                f"{temp_msg}\n"
                f"{accion}"
            ),
            color=discord.Color.orange()
        )
        
        controles_txt = (
            "🥕 **Vegetales** | 🥩 **Proteína** | 🌾 **Carbohidratos** | 🧂 **Especias**\n"
            "👨‍🍳 **Cocinar:** Prepara el plato (mín. 2 ingredientes)"
        )
        if self.nivel >= 5:
            controles_txt += "\n✨ **Ingrediente Secreto:** Selecciónalo del menú inferior."
        if self.nivel >= 8:
            controles_txt += "\n🌡️ **Ajustar Temperatura:** Presiona el botón para ciclar Baja/Media/Alta."
            
        embed.add_field(
            name="🎮 Controles:",
            value=controles_txt,
            inline=False
        )
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)
    
    async def _completar_trabajo(self, interaction, puntuacion, correctos, faltantes, extras, secreto_multiplier=1.0, secreto_feedback="", secreto_xp_bonus=0, temp_multiplier=1.0, temp_feedback=""):
        # Desactivar todos los botones
        self.agregar_vegetales.disabled = True
        self.agregar_proteina.disabled = True
        self.agregar_carbos.disabled = True
        self.agregar_especias.disabled = True
        self.cocinar_plato.disabled = True
        if self.nivel >= 8:
            self.ciclar_temperatura.disabled = True
        self.stop()
        
        user_id = self.user.id
        tipo_trabajo = 'chef'
        
        recompensa_final, resultado_nivel, has_knife, xp_ganada = await asyncio.to_thread(
            _completar_chef_db, user_id, tipo_trabajo, self.recompensa_base, puntuacion, secreto_multiplier, temp_multiplier, secreto_xp_bonus, self.preparacion_perfecta
        )
        
        # Determinar resultado visual
        if puntuacion >= 95 and temp_multiplier >= 1.0:
            resultado = "🏆 ¡OBRA MAESTRA!"
            color = discord.Color.gold()
        elif puntuacion >= 80 and temp_multiplier >= 1.0:
            resultado = "🌟 ¡Excelente!"
            color = discord.Color.green()
        elif puntuacion >= 60 and temp_multiplier >= 1.0:
            resultado = "✅ Bien hecho"
            color = discord.Color.blue()
        elif puntuacion >= 40 or temp_multiplier < 1.0:
            resultado = "⚠️ Mejorable"
            color = discord.Color.orange()
        else:
            resultado = "❌ ¡Desastre culinario!"
            color = discord.Color.red()
        
        subio_nivel = resultado_nivel["subio_nivel"]
        nivel_nuevo = resultado_nivel["nivel_nuevo"]
        xp_actual = resultado_nivel["xp_actual"]
        xp_para_siguiente = resultado_nivel["xp_para_siguiente"]
        
        xp_ganada_final = resultado_nivel.get("xp_ganada_final", xp_ganada)
        pocion_msg = "\n🧪 **¡Poción de Enfoque usada!** (+50% XP)" if resultado_nivel.get("pocion_usada") else ""
        knife_msg = "\n🔪 **Cuchillo de Chef activo:** +15% Monedas y XP" if has_knife else ""
        
        # Obtener información del nivel para mostrar
        if nivel_nuevo < 10:
            progreso = xp_actual / xp_para_siguiente if xp_para_siguiente > 0 else 1
            barra_progreso = '█' * int(progreso * 10) + '░' * (10 - int(progreso * 10))
            info_nivel = f"**Nivel {nivel_nuevo}** | {barra_progreso} {xp_actual}/{xp_para_siguiente} XP"
        else:
            info_nivel = f"**Nivel {nivel_nuevo}** | ✅ Nivel máximo alcanzado"
        
        # Obtener bonificación de nivel para mostrar
        bonificacion_nivel_porcentaje = int((await asyncio.to_thread(calcular_recompensa, 1, user_id, tipo_trabajo) - 1) * 100)
        
        embed = discord.Embed(
            title=f"👨‍🍳 {resultado}",
            description=(
                f"🍽️ **Plato preparado:** {self.plato_objetivo['nombre']}\n"
                f"📊 **Puntuación:** {puntuacion}/100\n"
                f"✅ **Ingredientes correctos:** {correctos}\n"
                f"❌ **Ingredientes faltantes:** {faltantes}\n"
                f"➕ **Ingredientes extra:** {extras}\n"
                f"{secreto_feedback}"
                f"{temp_feedback}\n"
                f"🌟 **Bonus por nivel:** +{bonificacion_nivel_porcentaje}%\n"
                f"💰 **Recompensa:** {recompensa_final} monedas{knife_msg}\n\n"
                f"📊 {info_nivel}\n"
                f"✨ **XP ganada:** +{xp_ganada_final} XP{pocion_msg}"
            ),
            color=color
        )
        
        if self.preparacion_perfecta and temp_multiplier >= 1.0:
            embed.add_field(
                name="🎉 ¡Bonificación Perfecta!",
                value="¡Preparaste el plato exactamente como se pedía!",
                inline=False
            )
            
        # Añadir mensaje de subida de nivel si corresponde
        if subio_nivel:
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

def _completar_chef_db(user_id, tipo_trabajo, recompensa_base, puntuacion, secreto_multiplier, temp_multiplier, secreto_xp_bonus, preparacion_perfecta):
    recompensa_base_con_nivel = calcular_recompensa(recompensa_base, user_id, tipo_trabajo)
    has_knife = usuario_tiene_mejora(user_id, 7)
    
    multiplicador = puntuacion / 100
    recompensa_final = int(recompensa_base_con_nivel * multiplicador * secreto_multiplier * temp_multiplier)
    if has_knife:
        recompensa_final = int(recompensa_final * 1.15)
        
    xp_ganada = int(puntuacion / 5) + secreto_xp_bonus
    if preparacion_perfecta and temp_multiplier >= 1.0:
        xp_ganada += 10
    if has_knife:
        xp_ganada = int(xp_ganada * 1.15)
        
    resultado_nivel = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
    if recompensa_final > 0:
        saldo_actual = get_balance(user_id)
        set_balance(user_id, saldo_actual + recompensa_final)
        registrar_transaccion(user_id, recompensa_final, "Trabajo: Chef completado")
        
    return recompensa_final, resultado_nivel, has_knife, xp_ganada

def _iniciar_chef_db(user_id, tipo_trabajo):
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    energia_actual = get_energia(user_id)
    energia_base = 20
    energia_requerida = calcular_energia_requerida(energia_base, user_id, tipo_trabajo)
    
    if energia_actual >= energia_requerida:
        set_energia(user_id, energia_actual - energia_requerida)
        
    return nivel_info, energia_actual, energia_requerida

async def iniciar_trabajo_chef(interaction: discord.Interaction):
    """Función principal para iniciar el trabajo de chef."""
    user_id = interaction.user.id
    tipo_trabajo = 'chef'
    
    nivel_info, energia_actual, energia_requerida = await asyncio.to_thread(_iniciar_chef_db, user_id, tipo_trabajo)
    nivel = nivel_info["nivel"]
    
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
    
    # Lista global de platos filtrados por nivel
    platos_todos = [
        # Fácil (Nivel 0-2)
        {
            "nombre": "🥗 Ensalada Simple",
            "ingredientes": ["vegetales", "especias"],
            "dificultad": "Fácil",
            "nivel_min": 0,
            "recompensa_base": 180,
            "pista_temp": "cocción fría (sin fuego)",
            "temp_ideal": "Baja",
            "pista_secreta": "Este plato combina excelente con un toque brillante de oro.",
            "secret_ideal": "oro"
        },
        {
            "nombre": "🥪 Sándwich Clásico",
            "ingredientes": ["proteina", "carbohidratos"],
            "dificultad": "Fácil",
            "nivel_min": 0,
            "recompensa_base": 180,
            "pista_temp": "tostado muy sutil (bajo calor)",
            "temp_ideal": "Baja",
            "pista_secreta": "Para el sándwich, un ingrediente terroso de bosque es genial.",
            "secret_ideal": "trufa"
        },
        {
            "nombre": "🍝 Pasta de la Casa Simple",
            "ingredientes": ["carbohidratos", "especias"],
            "dificultad": "Fácil",
            "nivel_min": 0,
            "recompensa_base": 180,
            "pista_temp": "cocido a fuego estándar",
            "temp_ideal": "Media",
            "pista_secreta": "Esta pasta se enriquece con un toque floral oriental.",
            "secret_ideal": "azafran"
        },
        
        # Medio (Nivel 3-5)
        {
            "nombre": "🍝 Pasta Bolognesa",
            "ingredientes": ["proteina", "carbohidratos", "especias"],
            "dificultad": "Medio",
            "nivel_min": 3,
            "recompensa_base": 280,
            "pista_temp": "cocido a fuego estándar",
            "temp_ideal": "Media",
            "pista_secreta": "Para la boloñesa, los hongos silvestres añaden misterio terroso.",
            "secret_ideal": "trufa"
        },
        {
            "nombre": "🥗 Ensalada Gourmet",
            "ingredientes": ["vegetales", "proteina", "especias"],
            "dificultad": "Medio",
            "nivel_min": 3,
            "recompensa_base": 280,
            "pista_temp": "servido a temperatura ambiente (sin calor)",
            "temp_ideal": "Baja",
            "pista_secreta": "El aderezo gourmet se beneficia de un toque brillante y costoso.",
            "secret_ideal": "oro"
        },
        {
            "nombre": "🍛 Arroz con Pollo",
            "ingredientes": ["proteina", "carbohidratos", "vegetales"],
            "dificultad": "Medio",
            "nivel_min": 3,
            "recompensa_base": 280,
            "pista_temp": "guisado normal de cocina",
            "temp_ideal": "Media",
            "pista_secreta": "El color amarillo y sabor único del arroz requieren flor exótica.",
            "secret_ideal": "azafran"
        },
        {
            "nombre": "🌮 Tacos Especiales",
            "ingredientes": ["proteina", "vegetales", "especias"],
            "dificultad": "Medio",
            "nivel_min": 3,
            "recompensa_base": 280,
            "pista_temp": "carne sellada a fuego muy fuerte",
            "temp_ideal": "Alta",
            "pista_secreta": "Añade un hongo terroso y caro para elevar los tacos.",
            "secret_ideal": "trufa"
        },
        
        # Difícil (Nivel 6-8)
        {
            "nombre": "🍲 Guiso Completo",
            "ingredientes": ["vegetales", "proteina", "carbohidratos", "especias"],
            "dificultad": "Difícil",
            "nivel_min": 6,
            "recompensa_base": 450,
            "pista_temp": "cocción lenta y a fuego suave",
            "temp_ideal": "Baja",
            "pista_secreta": "Un guiso denso combina con la potencia de trufa silvestre.",
            "secret_ideal": "trufa"
        },
        {
            "nombre": "🥘 Paella Valenciana Real",
            "ingredientes": ["vegetales", "proteina", "carbohidratos", "especias"],
            "dificultad": "Difícil",
            "nivel_min": 6,
            "recompensa_base": 450,
            "pista_temp": "cocido tradicional a fuego medio",
            "temp_ideal": "Media",
            "pista_secreta": "No hay paella auténtica sin el aroma de azafrán real.",
            "secret_ideal": "azafran"
        },
        {
            "nombre": "🍜 Ramen Tonkotsu Especial",
            "ingredientes": ["vegetales", "proteina", "carbohidratos", "especias"],
            "dificultad": "Difícil",
            "nivel_min": 6,
            "recompensa_base": 450,
            "pista_temp": "caldo hirviendo a fuego medio",
            "temp_ideal": "Media",
            "pista_secreta": "Para el ramen del emperador, decora con escamas de oro.",
            "secret_ideal": "oro"
        },
        
        # Maestro (Nivel 9-10)
        {
            "nombre": "🥩 Filet Mignon Suprema",
            "ingredientes": ["vegetales", "proteina", "carbohidratos", "especias"],
            "dificultad": "Maestro",
            "nivel_min": 9,
            "recompensa_base": 700,
            "pista_temp": "sellado de carne inmediato a fuego máximo",
            "temp_ideal": "Alta",
            "pista_secreta": "El corte de carne exige un toque terroso y de bosque premium.",
            "secret_ideal": "trufa"
        },
        {
            "nombre": "🍛 Risotto de Oro Imperial",
            "ingredientes": ["vegetales", "proteina", "carbohidratos", "especias"],
            "dificultad": "Maestro",
            "nivel_min": 9,
            "recompensa_base": 700,
            "pista_temp": "cocción suave constante a fuego estándar",
            "temp_ideal": "Media",
            "pista_secreta": "Este plato debe brillar como la realeza y costar una fortuna.",
            "secret_ideal": "oro"
        },
        {
            "nombre": "🍛 Curry Exótico Perfumado",
            "ingredientes": ["vegetales", "proteina", "carbohidratos", "especias"],
            "dificultad": "Maestro",
            "nivel_min": 9,
            "recompensa_base": 700,
            "pista_temp": "infusión lenta a fuego bajo",
            "temp_ideal": "Baja",
            "pista_secreta": "Este curry requiere la especia más fina, cara y aromática de oriente.",
            "secret_ideal": "azafran"
        }
    ]
    
    # Filtrar platos disponibles que el usuario puede hacer según su nivel
    platos_disponibles = [p for p in platos_todos if nivel >= p["nivel_min"]]
    
    # Si por alguna razón queda vacío, usar los básicos
    if not platos_disponibles:
        platos_disponibles = [p for p in platos_todos if p["nivel_min"] == 0]
        
    plato_objetivo = random.choice(platos_disponibles)
    recompensa_base = plato_objetivo["recompensa_base"]
    
    recompensa_con_nivel = await asyncio.to_thread(calcular_recompensa, recompensa_base, user_id, tipo_trabajo)
    
    # Info de nivel para mostrar
    bonificacion_actual = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel, "Sin bonificaciones")
    
    # Ingredientes disponibles
    ingredientes_disponibles = ["vegetales", "proteina", "carbohidratos", "especias"]
    
    secreto_inicial = ""
    if nivel >= 5:
        secreto_inicial = f"✨ **Ingrediente Secreto desbloqueado!**\n💡 *Pista:* {plato_objetivo['pista_secreta']}\n"
    temp_inicial = ""
    if nivel >= 8:
        temp_inicial = f"🌡️ **Ajustar Temperatura desbloqueado!**\n💡 *Cocción:* {plato_objetivo['pista_temp']}\n"
        
    embed = discord.Embed(
        title="👨‍🍳 Trabajo: Chef",
        description=(
            f"🎯 **Plato a preparar:** {plato_objetivo['nombre']}\n"
            f"📋 **Ingredientes necesarios:** {', '.join(plato_objetivo['ingredientes'])}\n"
            f"🏆 **Dificultad:** {plato_objetivo['dificultad']}\n"
            f"💰 **Recompensa:** {recompensa_con_nivel}+ monedas\n"
            f"⏱️ **Tiempo límite:** 2.5 minutos\n\n"
            f"{secreto_inicial}"
            f"{temp_inicial}\n"
            f"📊 **Nivel actual:** {nivel} (XP ganada basada en desempeño)\n"
            f"🌟 **Bonificación de nivel:** {bonificacion_actual}\n\n"
            f"🔍 **Selecciona los ingredientes correctos...**"
        ),
        color=discord.Color.orange()
    )
    
    controles_txt = (
        "🥕 **Vegetales** | 🥩 **Proteína** | 🌾 **Carbohidratos** | 🧂 **Especias**\n"
        "👨‍🍳 **Cocinar:** Prepara el plato (mín. 2 ingredientes)"
    )
    if nivel >= 5:
        controles_txt += "\n✨ **Ingrediente Secreto:** Elige una opción en el menú inferior."
    if nivel >= 8:
        controles_txt += "\n🌡️ **Ajustar Temperatura:** Haz click en el botón de Temperatura."
        
    embed.add_field(
        name="🎮 Cómo jugar:",
        value=controles_txt,
        inline=False
    )
    
    view = ChefView(interaction.user, plato_objetivo, ingredientes_disponibles, recompensa_base, nivel)
    await interaction.response.send_message(embed=embed, view=view)
