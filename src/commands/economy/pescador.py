import discord
import random
from src.db import get_balance, set_balance, registrar_transaccion, usuario_tiene_mejora, usuario_tiene_item, usar_item_usuario
from .energia import get_energia, set_energia
from .niveles_trabajo import (
    add_experiencia_trabajo, 
    calcular_energia_requerida, 
    calcular_recompensa, 
    get_nivel_trabajo,
    TIPOS_TRABAJO
)
import asyncio

PECADO_ZONAS = {
    "laguna": {"nombre": "Laguna Tranquila 🌊", "peces": ["🐠 Pejerrey", "🐟 Trucha Común"], "zona_size": 50, "recompensa_base": 150},
    "rio": {"nombre": "Río Turbulento 🌊", "peces": ["🐟 Salmón Salvaje", "🐡 Pez Gato"], "zona_size": 40, "recompensa_base": 250},
    "mar": {"nombre": "Mar Abierto 🦈", "peces": ["🦈 Tiburón Martillo", "🐟 Atún Aleta Azul"], "zona_size": 35, "recompensa_base": 420},
    "abisal": {"nombre": "Fosa Abisal 🦑", "peces": ["🦑 Calamar Gigante", "🐡 Pez Linterna Abisal"], "zona_size": 25, "recompensa_base": 680}
}

class PescadorView(discord.ui.View):
    def __init__(self, user, zona_info, recompensa_base, nivel):
        super().__init__(timeout=120)
        self.user = user
        self.zona_info = zona_info
        self.recompensa_base = recompensa_base
        self.nivel = nivel
        
        self.turnos = 0
        self.max_turnos = 4
        self.tension = 50
        self.cebo_activo = False
        
        # Seleccionar pez
        self.pez_objetivo = random.choice(zona_info["peces"])
        
        # Configurar Zona Segura según dificultad de la zona
        size = zona_info["zona_size"]
        self.zona_min = 50 - (size // 2)
        self.zona_max = 50 + (size // 2)
        
        # La mejora se verifica antes de crear la clase
        self.has_mejora_5 = False
        
        # Desbloqueos de nivel
        if self.nivel < 5:
            self.remove_item(self.cebo)
        if self.nivel < 8:
            self.remove_item(self.red_arrastre)
            
    @discord.ui.button(label="🎣 Recoger Hilo", style=discord.ButtonStyle.primary)
    async def recoger(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        await interaction.response.defer()
            
        # Acción: Recoger aumenta tensión
        cambio_jugador = random.randint(18, 25)
        self.tension += cambio_jugador
        
        # El pez forcejea: Tira aleatoriamente (-12% a +12%)
        tiron_pez = random.randint(-12, 12)
        self.tension += tiron_pez
        
        self.turnos += 1
        
        # Validar límites
        if self.tension >= 100 or self.tension <= 0:
            has_amuleto = await asyncio.to_thread(usuario_tiene_item, self.user.id, 7)
            if has_amuleto:
                amuleto_usado = await asyncio.to_thread(usar_item_usuario, self.user.id, 7)
                if amuleto_usado:
                    self.tension = 50
                    await self._actualizar_mensaje(
                        interaction, 
                        f"🛡️ **¡El Amuleto de Protección se ha roto!** Evitó que tu línea se rompiera o el pez escapara. Tensión reajustada al 50%."
                    )
                    return
            await self._completar_trabajo(interaction, exito=False, motivo="rotura" if self.tension >= 100 else "escape")
            return
            
        if self.turnos >= self.max_turnos:
            # Fin del minijuego, verificar zona
            if self.zona_min <= self.tension <= self.zona_max:
                await self._completar_trabajo(interaction, exito=True)
            else:
                await self._completar_trabajo(interaction, exito=False, motivo="fuera_de_zona")
            return
            
        # Actualizar estado
        await self._actualizar_mensaje(
            interaction, 
            f"🎣 **Recogiste hilo (+{cambio_jugador}%):** El pez forcejeó ({'+' if tiron_pez >= 0 else ''}{tiron_pez}%)."
        )

    @discord.ui.button(label="🌊 Soltar Hilo", style=discord.ButtonStyle.secondary)
    async def soltar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        await interaction.response.defer()
            
        # Acción: Soltar reduce tensión
        cambio_jugador = random.randint(18, 25)
        self.tension -= cambio_jugador
        
        # El pez forcejea
        tiron_pez = random.randint(-12, 12)
        self.tension += tiron_pez
        
        self.turnos += 1
        
        # Validar límites
        if self.tension >= 100 or self.tension <= 0:
            has_amuleto = await asyncio.to_thread(usuario_tiene_item, self.user.id, 7)
            if has_amuleto:
                amuleto_usado = await asyncio.to_thread(usar_item_usuario, self.user.id, 7)
                if amuleto_usado:
                    self.tension = 50
                    await self._actualizar_mensaje(
                        interaction, 
                        f"🛡️ **¡El Amuleto de Protección se ha roto!** Evitó que tu línea se rompiera o el pez escapara. Tensión reajustada al 50%."
                    )
                    return
            await self._completar_trabajo(interaction, exito=False, motivo="rotura" if self.tension >= 100 else "escape")
            return
            
        if self.turnos >= self.max_turnos:
            if self.zona_min <= self.tension <= self.zona_max:
                await self._completar_trabajo(interaction, exito=True)
            else:
                await self._completar_trabajo(interaction, exito=False, motivo="fuera_de_zona")
            return
            
        await self._actualizar_mensaje(
            interaction, 
            f"🌊 **Soltaste hilo (-{cambio_jugador}%):** El pez forcejeó ({'+' if tiron_pez >= 0 else ''}{tiron_pez}%)."
        )

    @discord.ui.button(label="✨ Cebo Premium", style=discord.ButtonStyle.secondary, row=1)
    async def cebo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        self.cebo_activo = True
        button.disabled = True
        button.style = discord.ButtonStyle.success
        button.label = "✨ Cebo Aplicado"
        
        # Expandir la zona segura
        self.zona_min = max(0, self.zona_min - 7)
        self.zona_max = min(100, self.zona_max + 8)
        
        await self._actualizar_mensaje(interaction, "✨ **Cebo Premium:** Zona segura expandida un +15% para esta batalla.")

    @discord.ui.button(label="🕸️ Red de Arrastre", style=discord.ButtonStyle.secondary, row=1)
    async def red_arrastre(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        button.disabled = True
        button.style = discord.ButtonStyle.danger
        button.label = "🕸️ Red Desplegada"
        self.stop()
        
        await self._finalizar_con_red(interaction)

    async def _actualizar_mensaje(self, interaction, accion):
        # Crear barra gráfica de tensión de 20 caracteres
        # La zona segura está marcada visualmente
        barra = []
        for i in range(20):
            porc = i * 5
            if porc == self.tension // 5 * 5:
                barra.append("🔴") # Indicador de tensión actual
            elif self.zona_min <= porc <= self.zona_max:
                barra.append("🟩") # Zona segura
            else:
                barra.append("⬜") # Fuera de rango
                
        barra_txt = "".join(barra)
        
        has_rod = self.has_mejora_5
        rod_msg = " (Caña de Fibra activa 🎣)" if has_rod else ""
        
        embed = discord.Embed(
            title="🎣 Trabajo: Pescador",
            description=(
                f"🐟 **Pez enganchado:** {self.pez_objetivo}{rod_msg}\n"
                f"⏱️ **Turnos restantes:** {self.max_turnos - self.turnos}\n\n"
                f"⚙️ **Tensión de línea:** {barra_txt} `{self.tension}%`\n"
                f"🎯 **Zona segura de tensión:** `{self.zona_min}%` a `{self.zona_max}%`\n\n"
                f"{accion}"
            ),
            color=discord.Color.teal()
        )
        
        controles_txt = (
            "🎣 **Recoger Hilo:** Aumenta la tensión de la línea (+18% a +25%)\n"
            "🌊 **Soltar Hilo:** Disminuye la tensión de la línea (-18% a -25%)"
        )
        if self.nivel >= 5:
            controles_txt += "\n✨ **Cebo Premium:** Expande la zona segura de tensión (1 uso)."
        if self.nivel >= 8:
            controles_txt += "\n🕸️ **Red de Arrastre:** Captura cardumen garantizado 1.0x sin minijuego."
            
        embed.add_field(
            name="🎮 Controles:",
            value=controles_txt,
            inline=False
        )
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

    async def _completar_trabajo(self, interaction, exito, motivo=None):
        self.recoger.disabled = True
        self.soltar.disabled = True
        if self.nivel >= 5:
            self.cebo.disabled = True
        if self.nivel >= 8:
            self.red_arrastre.disabled = True
        self.stop()
        
        user_id = self.user.id
        tipo_trabajo = 'pescador'
        
        if exito:
            centro = (self.zona_min + self.zona_max) / 2
            desviacion = abs(self.tension - centro)
            rango = (self.zona_max - self.zona_min) / 2
            precision = max(0.5, 1.0 - (desviacion / (rango * 1.5)))
            
            recompensa_final, resultado_nivel = await asyncio.to_thread(
                _completar_pescador_db, user_id, tipo_trabajo, self.recompensa_base, precision, self.pez_objetivo
            )
            
            subio_nivel = resultado_nivel["subio_nivel"]
            nivel_nuevo = resultado_nivel["nivel_nuevo"]
            xp_actual = resultado_nivel["xp_actual"]
            xp_para_siguiente = resultado_nivel["xp_para_siguiente"]
            
            xp_ganada = int(self.recompensa_base * 0.08) + (20 if precision > 0.9 else 10)
            
            xp_ganada_final = resultado_nivel.get("xp_ganada_final", xp_ganada)
            pocion_msg = "\n🧪 **¡Poción de Enfoque usada!** (+50% XP)" if resultado_nivel.get("pocion_usada") else ""
            
            if nivel_nuevo < 10:
                progreso = xp_actual / xp_para_siguiente if xp_para_siguiente > 0 else 1
                barra_progreso = '█' * int(progreso * 10) + '░' * (10 - int(progreso * 10))
                info_nivel = f"**Nivel {nivel_nuevo}** | {barra_progreso} {xp_actual}/{xp_para_siguiente} XP"
            else:
                info_nivel = f"**Nivel {nivel_nuevo}** | ✅ Nivel máximo alcanzado"
                
            embed = discord.Embed(
                title=f"🎣 ¡Pesca Exitosa! Capturaste un {self.pez_objetivo}",
                description=(
                    f"🎉 **¡Lograste agotar al pez y subirlo a la cubierta!**\n"
                    f"🎯 **Precisión de captura:** {int(precision * 100)}%\n"
                    f"💰 **Recompensa base:** {self.recompensa_base} monedas\n"
                    f"💵 **Total ganado:** {recompensa_final} monedas\n\n"
                    f"📊 {info_nivel}\n"
                    f"✨ **XP ganada:** +{xp_ganada_final} XP{pocion_msg}"
                ),
                color=discord.Color.green()
            )
            
            if subio_nivel:
                nueva_bonificacion = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel_nuevo, "Sin bonificación")
                embed.add_field(
                    name="🎊 ¡SUBISTE DE NIVEL!",
                    value=f"Tu nivel de Pescador ha subido a **{nivel_nuevo}**\n"
                          f"🌟 **Nueva bonificación:** {nueva_bonificacion}",
                    inline=False
                )
        else:
            if motivo == "rotura":
                desc = "❌ **¡La tensión superó el 100%! La línea se rompió bruscamente y el pez se llevó el anzuelo.**"
            elif motivo == "escape":
                desc = "❌ **¡La tensión bajó a 0%! La línea quedó floja y el pez se soltó limpiamente.**"
            else:
                desc = "❌ **No lograste mantener la tensión en la zona segura al final de la batalla y el pez se escapó.**"
                
            embed = discord.Embed(
                title="🎣 El pez ha escapado...",
                description=(
                    f"{desc}\n"
                    f"💸 **Recompensa:** 0 monedas\n"
                    f"💡 *Tip: Trata de equilibrar Recoger y Soltar hilo para mantener el medidor de tensión en la zona verde.*"
                ),
                color=discord.Color.red()
            )
            
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

    async def _finalizar_con_red(self, interaction):
        user_id = self.user.id
        tipo_trabajo = 'pescador'
        
        recompensa_final, resultado_nivel = await asyncio.to_thread(
            _finalizar_con_red_db, user_id, tipo_trabajo, self.recompensa_base
        )
        
        subio_nivel = resultado_nivel["subio_nivel"]
        nivel_nuevo = resultado_nivel["nivel_nuevo"]
        xp_actual = resultado_nivel["xp_actual"]
        xp_para_siguiente = resultado_nivel["xp_para_siguiente"]
        
        xp_ganada_final = resultado_nivel.get("xp_ganada_final", xp_ganada)
        pocion_msg = "\n🧪 **¡Poción de Enfoque usada!** (+50% XP)" if resultado_nivel.get("pocion_usada") else ""
        
        if nivel_nuevo < 10:
            progreso = xp_actual / xp_para_siguiente if xp_para_siguiente > 0 else 1
            barra_progreso = '█' * int(progreso * 10) + '░' * (10 - int(progreso * 10))
            info_nivel = f"**Nivel {nivel_nuevo}** | {barra_progreso} {xp_actual}/{xp_para_siguiente} XP"
        else:
            info_nivel = f"**Nivel {nivel_nuevo}** | ✅ Nivel máximo alcanzado"
            
        embed = discord.Embed(
            title="🕸️ Pesca con Red de Arrastre",
            description=(
                f"🚢 **Desplegaste la red en la zona:** {self.zona_info['nombre']}\n"
                f"🐟 **Capturado:** Cardumen de peces pequeños comerciales.\n"
                f"💰 **Recompensa garantizada:** {recompensa_final} monedas\n\n"
                f"📊 {info_nivel}\n"
                f"✨ **XP ganada:** +{xp_ganada_final} XP{pocion_msg}"
            ),
            color=discord.Color.blue()
        )
        
        if subio_nivel:
            nueva_bonificacion = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel_nuevo, "Sin bonificación")
            embed.add_field(
                name="🎊 ¡SUBISTE DE NIVEL!",
                value=f"Tu nivel de Pescador ha subido a **{nivel_nuevo}**\n"
                      f"🌟 **Nueva bonificación:** {nueva_bonificacion}",
                inline=False
            )
            
        await interaction.response.edit_message(embed=embed, view=self)

def _completar_pescador_db(user_id, tipo_trabajo, recompensa_base, precision, pez_objetivo):
    recompensa_base_con_nivel = calcular_recompensa(recompensa_base, user_id, tipo_trabajo)
    recompensa_final = int(recompensa_base_con_nivel * precision)
    saldo_actual = get_balance(user_id)
    set_balance(user_id, saldo_actual + recompensa_final)
    registrar_transaccion(user_id, recompensa_final, f"Trabajo: Capturado {pez_objetivo}")
    xp_ganada = int(recompensa_base * 0.08) + (20 if precision > 0.9 else 10)
    resultado_nivel = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
    return recompensa_final, resultado_nivel

def _finalizar_con_red_db(user_id, tipo_trabajo, recompensa_base):
    recompensa_base_con_nivel = calcular_recompensa(recompensa_base, user_id, tipo_trabajo)
    recompensa_final = int(recompensa_base_con_nivel * 0.95)
    saldo_actual = get_balance(user_id)
    set_balance(user_id, saldo_actual + recompensa_final)
    registrar_transaccion(user_id, recompensa_final, "Trabajo: Pesca con Red de Arrastre")
    xp_ganada = int(recompensa_base * 0.04) + 5
    resultado_nivel = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
    return recompensa_final, resultado_nivel

def _iniciar_pescador_db(user_id, tipo_trabajo):
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    energia_actual = get_energia(user_id)
    energia_base = 20
    energia_requerida = calcular_energia_requerida(energia_base, user_id, tipo_trabajo)
    has_mejora = usuario_tiene_mejora(user_id, 5)
    
    if energia_actual >= energia_requerida:
        set_energia(user_id, energia_actual - energia_requerida)
        
    return nivel_info, energia_actual, energia_requerida, has_mejora

async def iniciar_trabajo_pescador(interaction: discord.Interaction):
    """Función principal para iniciar el trabajo de pescador."""
    user_id = interaction.user.id
    tipo_trabajo = 'pescador'
    
    nivel_info, energia_actual, energia_requerida, has_mejora = await asyncio.to_thread(_iniciar_pescador_db, user_id, tipo_trabajo)
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
    
    # Escalabilidad vertical: Zonas de pesca por nivel
    if nivel <= 2:
        zona_id = "laguna"
    elif nivel <= 5:
        zona_id = "rio"
    elif nivel <= 8:
        zona_id = "mar"
    else:
        zona_id = "abisal"
        
    zona_info = PECADO_ZONAS[zona_id]
    recompensa_base = zona_info["recompensa_base"]
    
    recompensa_con_nivel = await asyncio.to_thread(calcular_recompensa, recompensa_base, user_id, tipo_trabajo)
    
    # Info de nivel para mostrar
    bonificacion_actual = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel, "Sin bonificaciones")
    
    cebo_inicial = ""
    if nivel >= 5:
        cebo_inicial = f"✨ **Cebo Premium disponible!** Podrás expandir la zona de seguridad.\n"
    red_inicial = ""
    if nivel >= 8:
        red_inicial = f"🕸️ **Red de Arrastre disponible!** Podrás capturar peces automáticamente.\n"
        
    embed = discord.Embed(
        title="🎣 Trabajo: Pescador",
        description=(
            f"🌊 **Zona de Pesca:** {zona_info['nombre']}\n"
            f"💰 **Recompensa promedio:** {recompensa_con_nivel} monedas\n"
            f"⏱️ **Tiempo límite:** 2 minutos\n\n"
            f"{cebo_inicial}"
            f"{red_inicial}\n"
            f"📊 **Nivel actual:** {nivel} (XP ganada basada en la precisión de la tensión final)\n"
            f"🌟 **Bonificación de nivel:** {bonificacion_actual}\n\n"
            f"🎣 **¡Lanzaste el anzuelo al agua... Un pez picó de inmediato! ¡Empieza la batalla!**"
        ),
        color=discord.Color.teal()
    )
    
    controles_txt = (
        "1️⃣ Mantén la tensión en la zona segura (verde)\n"
        "2️⃣ Usa **Recoger Hilo** para aumentar la tensión\n"
        "3️⃣ Usa **Soltar Hilo** para reducir la tensión\n"
        "4️⃣ Sobrevive los 4 turnos de pelea para capturar al pez"
    )
    
    embed.add_field(
        name="🎮 Cómo jugar:",
        value=controles_txt,
        inline=False
    )
    
    view = PescadorView(interaction.user, zona_info, recompensa_base, nivel)
    view.has_mejora_5 = has_mejora
    if has_mejora:
        view.zona_min = max(0, view.zona_min - 5)
        view.zona_max = min(100, view.zona_max + 5)
    
    await interaction.response.send_message(embed=embed, view=view)
