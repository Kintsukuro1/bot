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

TUNNELS = {
    "izq": {"nombre": "Túnel Izquierdo 🪨", "dureza": 1.0, "mineral_max": 150, "estabilidad_daño": 12},
    "cen": {"nombre": "Túnel Central 💎", "dureza": 1.8, "mineral_max": 350, "estabilidad_daño": 25},
    "der": {"nombre": "Túnel Derecho 🪙", "dureza": 1.4, "mineral_max": 220, "estabilidad_daño": 18}
}

class TunnelSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Túnel Izquierdo 🪨 (Dureza: Baja | Minerales: Pocos)", value="izq"),
            discord.SelectOption(label="Túnel Central 💎 (Dureza: Alta | Minerales: Muchos)", value="cen"),
            discord.SelectOption(label="Túnel Derecho 🪙 (Dureza: Media | Minerales: Medios)", value="der")
        ]
        super().__init__(placeholder="Elige un túnel para excavar...", min_values=1, max_values=1, options=options, row=2)
        
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        self.view.tunel_actual = self.values[0]
        await self.view._actualizar_mensaje(interaction, f"⛏️ **Cambiando al túnel: {TUNNELS[self.view.tunel_actual]['nombre']}**")

class MineroView(discord.ui.View):
    def __init__(self, user, recompensa_base, nivel):
        super().__init__(timeout=180)  # 3 minutos para completar
        self.user = user
        self.recompensa_base = recompensa_base
        self.nivel = nivel
        
        self.tunel_actual = "izq"
        self.estabilidad = 100
        self.mineral_acumulado = 0
        self.vigas_usadas = 0
        self.dinamita_usada = False
        
        # Inicializar cantidad de minerales restantes por túnel
        self.mineral_túneles = {
            "izq": TUNNELS["izq"]["mineral_max"],
            "cen": TUNNELS["cen"]["mineral_max"],
            "der": TUNNELS["der"]["mineral_max"]
        }
        
        # Agregar select menu de túneles
        self.add_item(TunnelSelect())
        
        # Desbloqueos de nivel
        if self.nivel < 5:
            self.remove_item(self.reforzar)
        if self.nivel < 8:
            self.remove_item(self.dinamita)
            
    @discord.ui.button(label="⛏️ Picar Mineral", style=discord.ButtonStyle.primary)
    async def picar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        await interaction.response.defer()
            
        tunel = TUNNELS[self.tunel_actual]
        mineral_restante = self.mineral_túneles[self.tunel_actual]
        
        if mineral_restante <= 0:
            await self._actualizar_mensaje(interaction, f"⚠️ **¡El {tunel['nombre']} ya no tiene más mineral! Elige otro túnel.**")
            return
            
        # Calcular daño de estabilidad y mineral extraído
        daño = int(tunel["estabilidad_daño"] * random.uniform(0.85, 1.15))
        has_mejora = await asyncio.to_thread(usuario_tiene_mejora, self.user.id, 4)
        if has_mejora:
            daño = int(daño * 0.80)
        self.estabilidad = max(0, self.estabilidad - daño)
        
        if self.estabilidad <= 0:
            # Verificar Amuleto de Protección (ID 7)
            has_amuleto = await asyncio.to_thread(usuario_tiene_item, self.user.id, 7)
            if has_amuleto:
                amuleto_usado = await asyncio.to_thread(usar_item_usuario, self.user.id, 7)
                if amuleto_usado:
                    self.estabilidad = 15
                    await self._actualizar_mensaje(interaction, f"🛡️ **¡El Amuleto de Protección se ha roto!** Te salvó de un derrumbe inminente. Estabilidad restaurada al 15%.")
                    return
            
            # Derrumbe
            await self._completar_trabajo(interaction, exito=False)
            return
            
        # Extraer mineral
        mineral_ext = int(random.randint(20, 40) * (1.0 / tunel["dureza"]))
        mineral_ext = min(mineral_ext, mineral_restante)
        
        self.mineral_túneles[self.tunel_actual] -= mineral_ext
        self.mineral_acumulado += mineral_ext
        
        await self._actualizar_mensaje(interaction, f"⛏️ **Picaste en {tunel['nombre']}:** Extraído +{mineral_ext} de mineral. Estabilidad -{daño}%")

    @discord.ui.button(label="🪵 Vigas de Soporte (2 usos)", style=discord.ButtonStyle.secondary, row=1)
    async def reforzar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        if self.vigas_usadas >= 2:
            button.disabled = True
            await self._actualizar_mensaje(interaction, "⚠️ **Ya gastaste todas las vigas de refuerzo!**")
            return
            
        self.vigas_usadas += 1
        self.estabilidad = min(100, self.estabilidad + 30)
        
        usos_restantes = 2 - self.vigas_usadas
        button.label = f"🪵 Vigas de Soporte ({usos_restantes} usos)"
        if usos_restantes == 0:
            button.disabled = True
            button.style = discord.ButtonStyle.danger
            
        await self._actualizar_mensaje(interaction, f"🪵 **Vigas colocadas:** La estabilidad del túnel subió un +30% (Estabilidad actual: {self.estabilidad}%)")

    @discord.ui.button(label="🧨 Detonar Dinamita C4", style=discord.ButtonStyle.secondary, row=1)
    async def dinamita(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        if self.dinamita_usada:
            button.disabled = True
            await self._actualizar_mensaje(interaction, "⚠️ **Ya detonaste tu dinamita en esta excavación!**")
            return
            
        self.dinamita_usada = True
        button.disabled = True
        button.style = discord.ButtonStyle.danger
        button.label = "🧨 Dinamita Detonada"
        
        # Extraer todo el mineral restante del túnel actual sin dañar la estabilidad
        tunel = TUNNELS[self.tunel_actual]
        mineral_restante = self.mineral_túneles[self.tunel_actual]
        
        if mineral_restante <= 0:
            await self._actualizar_mensaje(interaction, "⚠️ **Intentaste detonar un túnel vacío. La carga explotó pero no extrajo nada.**")
            return
            
        self.mineral_túneles[self.tunel_actual] = 0
        self.mineral_acumulado += mineral_restante
        
        await self._actualizar_mensaje(interaction, f"🧨 **¡BOOM! Detonación controlada en {tunel['nombre']}!** Extraído automáticamente +{mineral_restante} de mineral sin alterar la estabilidad.")

    @discord.ui.button(label="🏡 Volver a la Superficie", style=discord.ButtonStyle.success)
    async def volver(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        if self.mineral_acumulado == 0:
            await self._actualizar_mensaje(interaction, "⚠️ **No tienes mineral extraído para vender! Excava un poco primero.**")
            return
            
        await self._completar_trabajo(interaction, exito=True)

    async def _actualizar_mensaje(self, interaction, accion):
        barra_estabilidad = '🟩' * (self.estabilidad // 10) + '🟥' * (10 - (self.estabilidad // 10))
        
        minerales_status = []
        for key, val in self.mineral_túneles.items():
            nombre = TUNNELS[key]["nombre"].split()[0]
            status = f"{nombre}: {val} u." if val > 0 else f"{nombre}: 🚫 vacío"
            minerales_status.append(status)
            
        has_wolf = await asyncio.to_thread(usuario_tiene_mejora, self.user.id, 4)
        wolf_msg = " (Pico de Wolframio activo ⛏️)" if has_wolf else ""
        
        embed = discord.Embed(
            title="⛏️ Trabajo: Minero",
            description=(
                f"⛏️ **Túnel de excavación actual:** {TUNNELS[self.tunel_actual]['nombre']}{wolf_msg}\n"
                f"📊 **Estabilidad de la mina:** {barra_estabilidad} **{self.estabilidad}%**\n"
                f"💰 **Mineral acumulado en bolsa:** `{self.mineral_acumulado}` unidades\n\n"
                f"📦 **Estado de los túneles:**\n"
                f"• {', '.join(minerales_status)}\n\n"
                f"{accion}"
            ),
            color=discord.Color.gold()
        )
        
        controles_txt = (
            "⛏️ **Picar:** Excava y extrae mineral (reduce la estabilidad del túnel)\n"
            "🏡 **Volver:** Sal de la mina con tu mineral acumulado y cobra"
        )
        if self.nivel >= 5:
            controles_txt += "\n🪵 **Vigas de Soporte:** Recupera un +30% de estabilidad del túnel (máx 2 usos)."
        if self.nivel >= 8:
            controles_txt += "\n🧨 **Dinamita C4:** Limpia instantáneamente el mineral restante de un túnel (1 uso)."
            
        embed.add_field(
            name="🎮 Controles:",
            value=controles_txt,
            inline=False
        )
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

def _completar_minero_db(user_id, tipo_trabajo, recompensa_base, mineral_acumulado):
    recompensa_base_con_nivel = calcular_recompensa(recompensa_base, user_id, tipo_trabajo)
    recompensa_final = int(mineral_acumulado * 1.2 * (recompensa_base_con_nivel / 300))
    saldo_actual = get_balance(user_id)
    set_balance(user_id, saldo_actual + recompensa_final)
    registrar_transaccion(user_id, recompensa_final, "Trabajo: Minería completada")
    xp_ganada = int(mineral_acumulado * 0.4) + 10
    resultado_nivel = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
    return recompensa_final, resultado_nivel

    async def _completar_trabajo(self, interaction, exito):
        # Desactivar todos los botones
        self.picar.disabled = True
        self.volver.disabled = True
        if self.nivel >= 5:
            self.reforzar.disabled = True
        if self.nivel >= 8:
            self.dinamita.disabled = True
        self.stop()
        
        user_id = self.user.id
        tipo_trabajo = 'minero'
        
        if exito:
            recompensa_final, resultado_nivel = await asyncio.to_thread(
                _completar_minero_db, user_id, tipo_trabajo, self.recompensa_base, self.mineral_acumulado
            )
            
            subio_nivel = resultado_nivel["subio_nivel"]
            nivel_nuevo = resultado_nivel["nivel_nuevo"]
            xp_actual = resultado_nivel["xp_actual"]
            xp_para_siguiente = resultado_nivel["xp_para_siguiente"]
            
            xp_ganada_final = resultado_nivel.get("xp_ganada_final", int(self.mineral_acumulado * 0.4) + 10)
            pocion_msg = "\n🧪 **¡Poción de Enfoque usada!** (+50% XP)" if resultado_nivel.get("pocion_usada") else ""
            
            if nivel_nuevo < 10:
                progreso = xp_actual / xp_para_siguiente if xp_para_siguiente > 0 else 1
                barra_progreso = '█' * int(progreso * 10) + '░' * (10 - int(progreso * 10))
                info_nivel = f"**Nivel {nivel_nuevo}** | {barra_progreso} {xp_actual}/{xp_para_siguiente} XP"
            else:
                info_nivel = f"**Nivel {nivel_nuevo}** | ✅ Nivel máximo alcanzado"
                
            embed = discord.Embed(
                title="⛏️ ¡Regreso exitoso a la superficie!",
                description=(
                    f"🎉 **¡Lograste salir a tiempo antes del derrumbe!**\n"
                    f"💎 **Mineral total vendido:** {self.mineral_acumulado} unidades\n"
                    f"💰 **Ganancia total:** {recompensa_final} monedas\n\n"
                    f"📊 {info_nivel}\n"
                    f"✨ **XP ganada:** +{xp_ganada_final} XP{pocion_msg}"
                ),
                color=discord.Color.green()
            )
            
            if subio_nivel:
                nueva_bonificacion = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel_nuevo, "Sin bonificación")
                embed.add_field(
                    name="🎊 ¡SUBISTE DE NIVEL!",
                    value=f"Tu nivel de Minero ha subido a **{nivel_nuevo}**\n"
                          f"🌟 **Nueva bonificación:** {nueva_bonificacion}",
                    inline=False
                )
        else:
            # Derrumbe
            embed = discord.Embed(
                title="🚨 ¡DERRUMBE EN LA MINA! 🚨",
                description=(
                    f"❌ **La mina colapsó debido a la baja estabilidad.**\n"
                    f"🎒 Tuviste que soltar tu bolsa de herramientas y mineral para salvarte.\n"
                    f"💸 **Recompensa cobrada:** 0 monedas\n"
                    f"💡 *Tip: Asegúrate de volver a la superficie antes de que la estabilidad llegue a 0%, o usa Vigas de Soporte en nivel 5+!*"
                ),
                color=discord.Color.red()
            )
            
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

def _iniciar_minero_db(user_id, tipo_trabajo):
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    energia_actual = get_energia(user_id)
    energia_base = 25
    energia_requerida = calcular_energia_requerida(energia_base, user_id, tipo_trabajo)
    
    if energia_actual >= energia_requerida:
        set_energia(user_id, energia_actual - energia_requerida)
        
    return nivel_info, energia_actual, energia_requerida

async def iniciar_trabajo_minero(interaction: discord.Interaction):
    """Función principal para iniciar el trabajo de minero."""
    user_id = interaction.user.id
    tipo_trabajo = 'minero'
    
    nivel_info, energia_actual, energia_requerida = await asyncio.to_thread(_iniciar_minero_db, user_id, tipo_trabajo)
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
    
    # Escalabilidad vertical: Recompensas bases por mina
    if nivel <= 2:
        mina_nombre = "Mina de Carbón 🪨"
        recompensa_base = 180
    elif nivel <= 5:
        mina_nombre = "Mina de Hierro ⛓️"
        recompensa_base = 280
    elif nivel <= 8:
        mina_nombre = "Mina de Oro 🪙"
        recompensa_base = 450
    else:
        mina_nombre = "Mina de Diamantes y Gemas 💎"
        recompensa_base = 700
        
    # Mostrar recompensa con bonus de nivel aplicado
    recompensa_con_nivel = await asyncio.to_thread(calcular_recompensa, recompensa_base, user_id, tipo_trabajo)
    
    # Info de nivel para mostrar
    bonificacion_actual = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel, "Sin bonificaciones")
    
    reforzar_inicial = ""
    if nivel >= 5:
        reforzar_inicial = f"🪵 **Vigas de Soporte disponibles!** Podrás asegurar los túneles.\n"
    dinamita_inicial = ""
    if nivel >= 8:
        dinamita_inicial = f"🧨 **Cargas C4 disponibles!** Podrás detonar de manera controlada.\n"
        
    embed = discord.Embed(
        title="⛏️ Trabajo: Minero",
        description=(
            f"🗻 **Zona asignada:** {mina_nombre}\n"
            f"💰 **Recompensa promedio:** {recompensa_con_nivel} monedas\n"
            f"⏱️ **Tiempo límite:** 3 minutos\n\n"
            f"{reforzar_inicial}"
            f"{dinamita_inicial}\n"
            f"📊 **Nivel actual:** {nivel} (XP ganada basada en volumen de mineral extraído)\n"
            f"🌟 **Bonificación de nivel:** {bonificacion_actual}\n\n"
            f"🔍 **¡Escoge un túnel en el menú desplegable para comenzar a excavar!**"
        ),
        color=discord.Color.gold()
    )
    
    controles_txt = (
        "1️⃣ Elige un túnel para explorar en la mina\n"
        "2️⃣ Usa **Picar** para extraer mineral (Cuidado con la estabilidad)\n"
        "3️⃣ Si el túnel está vacío, cámbiate de túnel\n"
        "4️⃣ Presiona **Volver** antes de que la estabilidad llegue a 0%!"
    )
    
    embed.add_field(
        name="🎮 Cómo jugar:",
        value=controles_txt,
        inline=False
    )
    
    view = MineroView(interaction.user, recompensa_base, nivel)
    await interaction.response.send_message(embed=embed, view=view)
