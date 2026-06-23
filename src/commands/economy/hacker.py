import discord
import random
from src.db import get_balance, set_balance, registrar_transaccion, usuario_tiene_mejora
from .energia import get_energia, set_energia
from .niveles_trabajo import (
    add_experiencia_trabajo, 
    calcular_energia_requerida, 
    calcular_recompensa, 
    get_nivel_trabajo,
    get_energia_trabajo,
    get_resumen_nivel,
    TIPOS_TRABAJO
)
import asyncio

class HackerView(discord.ui.View):
    def __init__(self, user, codigo_secreto, recompensa_base, nivel):
        super().__init__(timeout=120)  # 2 minutos para completar
        self.user = user
        self.codigo_secreto = codigo_secreto
        self.recompensa_base = recompensa_base
        self.nivel = nivel
        self.intentos = 3
        self.codigo_descifrado = ['?'] * len(codigo_secreto)
        self.posicion_actual = 0
        self.bypass_activo = False
        self.bypass_usado = False
        self.inyeccion_usada = False
        self.has_mejora_6 = False
        
        # Remover botones si no se cumple el nivel requerido
        if self.nivel < 5:
            self.remove_item(self.bypass_cortafuegos)
        if self.nivel < 8:
            self.remove_item(self.inyeccion_sql)
        
    @discord.ui.button(label="🔍 Escanear", style=discord.ButtonStyle.primary)
    async def escanear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        await interaction.response.defer()
            
        # Desactivar el botón para que solo se use una vez
        button.disabled = True
        button.style = discord.ButtonStyle.secondary
        button.label = "🔍 Escaneo Usado"
            
        # Revelar 1-2 dígitos aleatorios
        posiciones_disponibles = [i for i, char in enumerate(self.codigo_descifrado) if char == '?']
        if posiciones_disponibles:
            revelar = random.randint(1, min(2, len(posiciones_disponibles)))
            posiciones_revelar = random.sample(posiciones_disponibles, revelar)
            
            for pos in posiciones_revelar:
                self.codigo_descifrado[pos] = self.codigo_secreto[pos]
        
        await self._actualizar_mensaje(interaction, f"🔍 **Escaneando sistema... ¡Revelados {revelar} dígitos!**")
    
    @discord.ui.button(label="💻 Hackear", style=discord.ButtonStyle.success)
    async def hackear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        await interaction.response.defer()
            
        if '?' not in self.codigo_descifrado:
            # Código completamente descifrado
            await self._completar_trabajo(interaction, True)
            return
            
        # Revelar siguiente dígito
        posiciones_disponibles = [i for i, char in enumerate(self.codigo_descifrado) if char == '?']
        if posiciones_disponibles:
            pos = posiciones_disponibles[0]
            
            # Chance de éxito: 95% si bypass está activo, de lo contrario 70% (80% con Procesador Cuántico)
            base_chance = 0.80 if self.has_mejora_6 else 0.70
            exito_chance = 0.95 if self.bypass_activo else base_chance
            self.bypass_activo = False  # Resetear bypass
            
            # Si el nivel es 5 o más, actualizar texto del botón de bypass una vez consumido
            if self.nivel >= 5 and self.bypass_usado:
                self.bypass_cortafuegos.label = "⚡ Bypass Usado"
                self.bypass_cortafuegos.style = discord.ButtonStyle.secondary
                self.bypass_cortafuegos.disabled = True
            
            if random.random() < exito_chance:
                self.codigo_descifrado[pos] = self.codigo_secreto[pos]
                await self._actualizar_mensaje(interaction, f"✅ **Dígito {pos + 1} descifrado!**")
            else:
                self.intentos -= 1
                if self.intentos <= 0:
                    await self._completar_trabajo(interaction, False)
                    return
                await self._actualizar_mensaje(interaction, f"❌ **Falló el hackeo! Intentos restantes: {self.intentos}**")
    
    @discord.ui.button(label="⚡ Bypass Cortafuegos", style=discord.ButtonStyle.secondary, row=1)
    async def bypass_cortafuegos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        self.bypass_activo = True
        self.bypass_usado = True
        button.disabled = True
        button.style = discord.ButtonStyle.success
        button.label = "⚡ Bypass Activo"
        await self._actualizar_mensaje(interaction, "⚡ **Bypass Cortafuegos activado! Siguiente hackeo con 95% de éxito.**")

    @discord.ui.button(label="💉 Inyección SQL", style=discord.ButtonStyle.secondary, row=1)
    async def inyeccion_sql(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        self.inyeccion_usada = True
        button.disabled = True
        button.style = discord.ButtonStyle.danger
        button.label = "💉 Inyección Ejecutada"
        
        # 1. Revelar 1 dígito aleatorio no descifrado (si hay)
        posiciones_disponibles = [i for i, char in enumerate(self.codigo_descifrado) if char == '?']
        revelado_msg = ""
        if posiciones_disponibles:
            pos = random.choice(posiciones_disponibles)
            self.codigo_descifrado[pos] = self.codigo_secreto[pos]
            revelado_msg = f"Revelado dígito en posición {pos + 1} (`{self.codigo_secreto[pos]}`). "
            posiciones_disponibles.remove(pos)
        
        # 2. Mostrar la paridad de los demás dígitos restantes
        paridad_txts = []
        for pos in posiciones_disponibles:
            digit = int(self.codigo_secreto[pos])
            paridad = "Par" if digit % 2 == 0 else "Impar"
            paridad_txts.append(f"Pos {pos + 1}: {paridad}")
        
        paridad_msg = ""
        if paridad_txts:
            paridad_msg = "Paridades: " + ", ".join(paridad_txts)
        else:
            paridad_msg = "No quedan más dígitos para analizar paridad."
            
        await self._actualizar_mensaje(interaction, f"💉 **Inyección SQL exitosa!** {revelado_msg}{paridad_msg}")

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
        
        has_quant = self.has_mejora_6
        hack_pct = "80%" if has_quant else "70%"
        quant_bonus = " (Procesador Cuántico activo ⚙️)" if has_quant else ""
        controles_txt = (
            "🔍 **Escanear:** Revela 1-2 dígitos aleatorios (1 uso)\n"
            f"💻 **Hackear:** Intenta descifrar el siguiente dígito ({hack_pct} éxito){quant_bonus}\n"
            "🎯 **Adivinar:** Introduce el código completo"
        )
        if self.nivel >= 5:
            controles_txt += "\n⚡ **Bypass Cortafuegos:** Siguiente hackeo tiene 95% éxito (1 uso)"
        if self.nivel >= 8:
            controles_txt += "\n💉 **Inyección SQL:** Revela 1 dígito y muestra paridad de los demás (1 uso)"
            
        embed.add_field(
            name="🎮 Controles:",
            value=controles_txt,
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
        if self.nivel >= 5:
            self.bypass_cortafuegos.disabled = True
        if self.nivel >= 8:
            self.inyeccion_sql.disabled = True
        self.stop()
            
        if exito:
            digitos_restantes = self.codigo_descifrado.count('?')
            bonus_eficiencia = 1.0 + (digitos_restantes * 0.1)  # +10% por cada dígito sin revelar
            
            user_id = self.user.id
            tipo_trabajo = 'hacker'
            
            xp_ganada = len(self.codigo_secreto) * 10
            if digitos_restantes > 0:
                xp_ganada += digitos_restantes * 5
                
            recompensa_final, resultado_nivel = await asyncio.to_thread(
                _completar_hacker_db, user_id, tipo_trabajo, self.recompensa_base, bonus_eficiencia, xp_ganada
            )
            
            subio_nivel = resultado_nivel["subio_nivel"]
            nivel_nuevo = resultado_nivel["nivel_nuevo"]
            xp_actual = resultado_nivel["xp_actual"]
            xp_para_siguiente = resultado_nivel["xp_para_siguiente"]
            
            xp_ganada_final = resultado_nivel.get("xp_ganada_final", xp_ganada)
            pocion_msg = "\n🧪 **¡Poción de Enfoque usada!** (+50% XP)" if resultado_nivel.get("pocion_usada") else ""
            
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
                    f"💵 **Total ganado:** {recompensa_final} monedas\n\n"
                    f"📊 {info_nivel}\n"
                    f"✨ **XP ganada:** +{xp_ganada_final} XP{pocion_msg}"
                ),
                color=discord.Color.green()
            )
            
            # Añadir mensaje de subida de nivel si corresponde
            if subio_nivel:
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
        max_length=8
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

def _completar_hacker_db(user_id, tipo_trabajo, recompensa_base, bonus_eficiencia, xp_ganada):
    recompensa_base_con_nivel = calcular_recompensa(recompensa_base, user_id, tipo_trabajo)
    recompensa_final = int(recompensa_base_con_nivel * bonus_eficiencia)
    saldo_actual = get_balance(user_id)
    set_balance(user_id, saldo_actual + recompensa_final)
    registrar_transaccion(user_id, recompensa_final, "Trabajo: Hacker completado")
    resultado_nivel = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
    return recompensa_final, resultado_nivel

def _iniciar_hacker_db(user_id, tipo_trabajo):
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    energia_actual = get_energia(user_id)
    energia_base = 25
    energia_requerida = calcular_energia_requerida(energia_base, user_id, tipo_trabajo)
    has_mejora = usuario_tiene_mejora(user_id, 6)
    
    if energia_actual >= energia_requerida:
        set_energia(user_id, energia_actual - energia_requerida)
        
    bonificacion_recompensa = calcular_recompensa(1, user_id, tipo_trabajo) - 1
    bonificacion_energia = calcular_energia_requerida(100, user_id, tipo_trabajo) / 100
        
    return nivel_info, energia_actual, energia_requerida, has_mejora, bonificacion_recompensa, bonificacion_energia

async def iniciar_trabajo_hacker(interaction: discord.Interaction):
    """Función principal para iniciar el trabajo de hacker."""
    user_id = interaction.user.id
    tipo_trabajo = 'hacker'
    
    nivel_info, energia_actual, energia_requerida, has_mejora, bonificacion_recompensa, bonificacion_energia = await asyncio.to_thread(_iniciar_hacker_db, user_id, tipo_trabajo)
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
    
    # Escalabilidad vertical: Longitud de código y recompensa base por nivel
    if nivel <= 2:
        longitud_codigo = 4
        recompensa_base = 200
    elif nivel <= 5:
        longitud_codigo = 5
        recompensa_base = 300
    elif nivel <= 8:
        longitud_codigo = 6
        recompensa_base = 450
    else:
        longitud_codigo = 7
        recompensa_base = 650
        
    codigo_secreto = ''.join([str(random.randint(0, 9)) for _ in range(longitud_codigo)])
    
    recompensa_con_nivel = await asyncio.to_thread(calcular_recompensa, recompensa_base, user_id, tipo_trabajo)
    
    # Info de nivel para mostrar
    bonificacion_actual = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel, "Sin bonificaciones")
    
    embed = discord.Embed(
        title="💻 Trabajo: Hacker",
        description=(
            f"🎯 **Objetivo:** Descifra el código de acceso al sistema\n"
            f"🔐 **Código:** `{'?' * longitud_codigo}`\n"
            f"💰 **Recompensa:** {recompensa_con_nivel}+ monedas\n"
            f"⏱️ **Tiempo límite:** 2 minutos\n\n"
            f"📊 **Nivel actual:** {nivel} ({'+' + str(int(bonificacion_recompensa * 100)) + '%' if bonificacion_recompensa > 0 else '0%'} recompensa, {'-' + str(int((1-bonificacion_energia) * 100)) + '%' if bonificacion_energia < 1 else '0%'} energía)\n"
            f"🌟 **Bonificación de nivel:** {bonificacion_actual}\n\n"
            f"🔍 **Iniciando escaneo de vulnerabilidades...**"
        ),
        color=discord.Color.blue()
    )
    
    controles_txt = (
        "🔍 **Escanear:** Revela 1-2 dígitos aleatorios (1 uso)\n"
        "💻 **Hackear:** Intenta descifrar el siguiente dígito (70% éxito)\n"
        "🎯 **Adivinar:** Introduce el código completo"
    )
    if nivel >= 5:
        controles_txt += "\n⚡ **Bypass Cortafuegos:** Siguiente hackeo tiene 95% éxito (1 uso)"
    if nivel >= 8:
        controles_txt += "\n💉 **Inyección SQL:** Revela 1 dígito y muestra paridad de los demás (1 uso)"
        
    embed.add_field(
        name="🎮 Controles:",
        value=controles_txt,
        inline=False
    )
    
    view = HackerView(interaction.user, codigo_secreto, recompensa_base, nivel)
    view.has_mejora_6 = has_mejora
    await interaction.response.send_message(embed=embed, view=view)
