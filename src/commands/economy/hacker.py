import discord
import random
from src.db import get_balance, set_balance, registrar_transaccion
from .energia import get_energia, set_energia
from .niveles_trabajo import (
    add_experiencia_trabajo, 
    calcular_energia_requerida, 
    calcular_recompensa, 
    get_nivel_trabajo,
    get_energia_trabajo,
    get_resumen_nivel
)

class HackerView(discord.ui.View):
    def __init__(self, user, codigo_secreto, recompensa_base):
        super().__init__(timeout=120)  # 2 minutos para completar
        self.user = user
        self.codigo_secreto = codigo_secreto
        self.recompensa_base = recompensa_base
        self.intentos = 3
        self.codigo_descifrado = ['?'] * len(codigo_secreto)
        self.posicion_actual = 0
        
    @discord.ui.button(label="🔍 Escanear", style=discord.ButtonStyle.primary)
    async def escanear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        # Revelar 1-2 dígitos aleatorios
        posiciones_disponibles = [i for i, char in enumerate(self.codigo_descifrado) if char == '?']
        if posiciones_disponibles:
            revelar = min(2, len(posiciones_disponibles))
            posiciones_revelar = random.sample(posiciones_disponibles, revelar)
            
            for pos in posiciones_revelar:
                self.codigo_descifrado[pos] = self.codigo_secreto[pos]
        
        await self._actualizar_mensaje(interaction, "🔍 **Escaneando sistema...**")
    
    @discord.ui.button(label="💻 Hackear", style=discord.ButtonStyle.success)
    async def hackear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        if '?' not in self.codigo_descifrado:
            # Código completamente descifrado
            await self._completar_trabajo(interaction, True)
            return
            
        # Revelar siguiente dígito
        posiciones_disponibles = [i for i, char in enumerate(self.codigo_descifrado) if char == '?']
        if posiciones_disponibles:
            pos = posiciones_disponibles[0]
            
            # 70% chance de éxito
            if random.random() < 0.7:
                self.codigo_descifrado[pos] = self.codigo_secreto[pos]
                await self._actualizar_mensaje(interaction, f"✅ **Dígito {pos + 1} descifrado!**")
            else:
                self.intentos -= 1
                if self.intentos <= 0:
                    await self._completar_trabajo(interaction, False)
                    return
                await self._actualizar_mensaje(interaction, f"❌ **Falló el hackeo! Intentos restantes: {self.intentos}**")
    
    @discord.ui.button(label="🎯 Adivinar", style=discord.ButtonStyle.secondary)
    async def adivinar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        modal = CodigoModal(self.codigo_secreto, self)
        await interaction.response.send_modal(modal)
    
    async def _actualizar_mensaje(self, interaction, accion):
        codigo_display = ''.join(self.codigo_descifrado)
        progreso = (len(self.codigo_secreto) - self.codigo_descifrado.count('?')) / len(self.codigo_secreto)
        barra_progreso = '█' * int(progreso * 10) + '░' * (10 - int(progreso * 10))
        
        embed = discord.Embed(
            title="💻 Trabajo: Hacker",
            description=(
                f"🎯 **Objetivo:** Descifra el código de acceso\n"
                f"🔐 **Código:** `{codigo_display}`\n"
                f"📊 **Progreso:** {barra_progreso} {int(progreso * 100)}%\n"
                f"🔄 **Intentos restantes:** {self.intentos}\n\n"
                f"{accion}"
            ),
            color=discord.Color.blue()
        )
        embed.add_field(
            name="🎮 Controles:",
            value=(
                "🔍 **Escanear:** Revela 1-2 dígitos aleatorios\n"
                "💻 **Hackear:** Intenta descifrar el siguiente dígito (70% éxito)\n"
                "🎯 **Adivinar:** Introduce el código completo"
            ),
            inline=False
        )
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)
    
    async def _completar_trabajo(self, interaction, exito):
        # Desactivar todos los botones
        self.escanear.disabled = True
        self.hackear.disabled = True
        self.adivinar.disabled = True
        self.stop()
            
        if exito:
            # Calcular recompensa basada en eficiencia
            digitos_restantes = self.codigo_descifrado.count('?')
            bonus_eficiencia = 1.0 + (digitos_restantes * 0.1)  # +10% por cada dígito sin revelar
            
            # Obtener bonificación por nivel
            user_id = self.user.id
            tipo_trabajo = 'hacker'
            
            # Aplicar bonificación de nivel a la recompensa base
            recompensa_base_con_nivel = calcular_recompensa(self.recompensa_base, user_id, tipo_trabajo)
            recompensa_final = int(recompensa_base_con_nivel * bonus_eficiencia)
            
            # Actualizar balance
            saldo_actual = get_balance(user_id)
            set_balance(user_id, saldo_actual + recompensa_final)
            registrar_transaccion(user_id, recompensa_final, "Trabajo: Hacker completado")
            
            # Añadir experiencia (depende de la dificultad y éxito)
            xp_ganada = len(self.codigo_secreto) * 10  # 10 XP por dígito
            if digitos_restantes > 0:
                xp_ganada += digitos_restantes * 5  # 5 XP extra por cada dígito sin revelar (bonus de eficiencia)
            
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
            
            embed = discord.Embed(
                title="💻 Trabajo Completado - ¡Éxito!",
                description=(
                    f"🎉 **¡Sistema hackeado exitosamente!**\n"
                    f"🔐 **Código:** `{self.codigo_secreto}`\n"
                    f"💰 **Recompensa base:** {self.recompensa_base} monedas\n"
                    f"⚡ **Bonus eficiencia:** +{int((bonus_eficiencia - 1) * 100)}%\n"
                    f"🌟 **Bonus por nivel:** +{int((calcular_recompensa(1, user_id, tipo_trabajo) - 1) * 100)}%\n"
                    f"💵 **Total ganado:** {recompensa_final} monedas\n\n"
                    f"📊 {info_nivel}\n"
                    f"✨ **XP ganada:** +{xp_ganada} XP"
                ),
                color=discord.Color.green()
            )
            
            # Añadir mensaje de subida de nivel si corresponde
            if subio_nivel:
                from .niveles_trabajo import TIPOS_TRABAJO
                nueva_bonificacion = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel_nuevo, "Sin bonificación")
                embed.add_field(
                    name="🎊 ¡SUBISTE DE NIVEL!",
                    value=f"Tu nivel de Hacker ha subido a **{nivel_nuevo}**\n"
                          f"🌟 **Nueva bonificación:** {nueva_bonificacion}",
                    inline=False
                )
        else:
            embed = discord.Embed(
                title="💻 Trabajo Fallido",
                description=(
                    f"❌ **Sistema de seguridad activado!**\n"
                    f"🔐 **El código era:** `{self.codigo_secreto}`\n"
                    f"💸 **Recompensa:** 0 monedas\n"
                    f"🔄 **Inténtalo de nuevo más tarde**"
                ),
                color=discord.Color.red()
            )
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

class CodigoModal(discord.ui.Modal, title="🎯 Adivinar Código"):
    def __init__(self, codigo_correcto, view):
        super().__init__()
        self.codigo_correcto = codigo_correcto
        self.view = view
    
    codigo = discord.ui.TextInput(
        label="Código de acceso",
        placeholder="Introduce el código completo...",
        required=True,
        max_length=6
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.codigo.value == self.codigo_correcto:
            await self.view._completar_trabajo(interaction, True)
        else:
            self.view.intentos -= 1
            if self.view.intentos <= 0:
                await self.view._completar_trabajo(interaction, False)
            else:
                await self.view._actualizar_mensaje(interaction, f"❌ **Código incorrecto! Intentos restantes: {self.view.intentos}**")

async def iniciar_trabajo_hacker(interaction: discord.Interaction):
    """Función principal para iniciar el trabajo de hacker."""
    user_id = interaction.user.id
    tipo_trabajo = 'hacker'
    
    # Obtener nivel del trabajo y bonificaciones
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel = nivel_info["nivel"]
    
    # Verificar energía del usuario - aplicar bonificación por nivel
    energia_actual = get_energia(user_id)
    energia_base = 25
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
    
    # Generar código aleatorio (4-6 dígitos)
    longitud_codigo = random.randint(4, 6)
    codigo_secreto = ''.join([str(random.randint(0, 9)) for _ in range(longitud_codigo)])
    
    # Calcular recompensa base según dificultad
    recompensa_base = longitud_codigo * 50  # 50 monedas por dígito
    
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
        title="💻 Trabajo: Hacker",
        description=(
            f"🎯 **Objetivo:** Descifra el código de acceso al sistema\n"
            f"🔐 **Código:** `{'?' * longitud_codigo}`\n"
            f"💰 **Recompensa:** {recompensa_con_nivel}+ monedas\n"
            f"⏱️ **Tiempo límite:** 2 minutos\n\n"
            f"📊 **Nivel actual:** {nivel_actual} ({'+' + str(int(bonificacion_recompensa * 100)) + '%' if bonificacion_recompensa > 0 else '0%'} recompensa, {'-' + str(int((1-bonificacion_energia) * 100)) + '%' if bonificacion_energia < 1 else '0%'} energía)\n"
            f"🌟 **Bonificación de nivel:** {bonificacion_actual}\n\n"
            f"🔍 **Iniciando escaneo de vulnerabilidades...**"
        ),
        color=discord.Color.blue()
    )
    embed.add_field(
        name="🎮 Controles:",
        value=(
            "🔍 **Escanear:** Revela 1-2 dígitos aleatorios\n"
            "💻 **Hackear:** Intenta descifrar el siguiente dígito (70% éxito)\n"
            "🎯 **Adivinar:** Introduce el código completo"
        ),
        inline=False
    )
    
    view = HackerView(interaction.user, codigo_secreto, recompensa_base)
    await interaction.response.send_message(embed=embed, view=view)
