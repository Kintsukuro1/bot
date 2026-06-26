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

class MecanicoView(discord.ui.View):
    def __init__(self, user, vehiculo_objetivo, recompensa_base, nivel):
        super().__init__(timeout=180)  # 3 minutos para completar
        self.user = user
        self.vehiculo_objetivo = vehiculo_objetivo
        self.recompensa_base = recompensa_base
        self.nivel = nivel
        self.problemas_detectados = []
        self.reparaciones_realizadas = []
        self.herramientas_usadas = set()
        self.precision_bonus = 0
        self.tiempo_reparacion = 0
        self.has_mejora_9 = False
        
        # Desbloqueos interactivos
        if self.nivel < 5:
            self.remove_item(self.escaner_obd)
        if self.nivel < 8:
            self.remove_item(self.diagnostico_avanzado)
        
    @discord.ui.button(label="🔍 Diagnosticar", style=discord.ButtonStyle.primary)
    async def diagnosticar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        problemas_posibles = self.vehiculo_objetivo["problemas"]
        
        if len(self.problemas_detectados) >= len(problemas_posibles) + 2:
            await self._actualizar_mensaje(interaction, "🔍 **Ya has analizado en profundidad el vehículo!**")
            return
        
        # 70% chance de detectar un problema real, 30% falso positivo
        if random.random() < 0.7 and len([p for p in self.problemas_detectados if p in problemas_posibles]) < len(problemas_posibles):
            problema_real = random.choice([p for p in problemas_posibles if p not in self.problemas_detectados])
            self.problemas_detectados.append(problema_real)
            self.precision_bonus += 15
            await self._actualizar_mensaje(interaction, f"✅ **Problema detectado: {problema_real.title()}! (+15 precisión)**")
        else:
            problemas_falsos = ["fuga de aceite menor", "ruido en el motor", "vibración extraña", "luz de check engine"]
            falso_problema = random.choice(problemas_falsos)
            if falso_problema not in self.problemas_detectados:
                self.problemas_detectados.append(falso_problema)
                await self._actualizar_mensaje(interaction, f"⚠️ **Posible anomalía: {falso_problema} (requiere verificación)**")
            else:
                await self._actualizar_mensaje(interaction, f"🔍 **Revisando nuevamente el sistema...**")
                
    @discord.ui.button(label="📟 Escáner OBD", style=discord.ButtonStyle.secondary, row=1)
    async def escaner_obd(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        await interaction.response.defer()
            
        button.disabled = True
        button.style = discord.ButtonStyle.success
        button.label = "📟 Escaneo OBD Completo"
        
        # Eliminar falsos positivos
        problemas_reales = self.vehiculo_objetivo["problemas"]
        filtrados = [p for p in self.problemas_detectados if p in problemas_reales]
        eliminados = len(self.problemas_detectados) - len(filtrados)
        self.problemas_detectados = filtrados
        
        await self._actualizar_mensaje(interaction, f"📟 **Escáner OBD:** Limpieza completada. Se eliminaron {eliminados} falsos diagnósticos.")
        
    @discord.ui.button(label="🔬 Diagnóstico Avanzado", style=discord.ButtonStyle.secondary, row=1)
    async def diagnostico_avanzado(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
            
        await interaction.response.defer()
            
        button.disabled = True
        button.style = discord.ButtonStyle.success
        button.label = "🔬 Diagnóstico Avanzado Listo"
        
        # Detectar todos los reales y limpiar falsos
        self.problemas_detectados = list(self.vehiculo_objetivo["problemas"])
        self.precision_bonus += len(self.vehiculo_objetivo["problemas"]) * 10
        
        await self._actualizar_mensaje(interaction, "🔬 **Diagnóstico Avanzado:** Escaneo completo realizado. Todos los problemas reales identificados.")
    
    @discord.ui.button(label="🔧 Llave Inglesa", style=discord.ButtonStyle.secondary)
    async def usar_llave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._usar_herramienta(interaction, "llave_inglesa", "🔧", ["motor", "transmisión", "frenos", "carburador", "cadena", "hélice"])
    
    @discord.ui.button(label="🪛 Destornillador", style=discord.ButtonStyle.secondary)
    async def usar_destornillador(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._usar_herramienta(interaction, "destornillador", "🪛", ["panel eléctrico", "interior", "luces", "batería", "LED"])
    
    @discord.ui.button(label="🔨 Martillo", style=discord.ButtonStyle.secondary)
    async def usar_martillo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._usar_herramienta(interaction, "martillo", "🔨", ["chasis", "carrocería", "escape", "tren de aterrizaje"])
    
    @discord.ui.button(label="⚡ Multímetro", style=discord.ButtonStyle.secondary)
    async def usar_multimetro(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._usar_herramienta(interaction, "multimetro", "⚡", ["panel eléctrico", "batería", "luces", "LED", "combustible"])
    
    @discord.ui.button(label="⚙️ Terminar Reparación", style=discord.ButtonStyle.success)
    async def terminar_reparacion(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        if len(self.problemas_detectados) < 1:
            await self._actualizar_mensaje(interaction, "⚠️ **¡Necesitas diagnosticar al menos un problema primero!**")
            return
        
        if len(self.reparaciones_realizadas) < 1:
            await self._actualizar_mensaje(interaction, "⚠️ **¡Necesitas realizar al menos una reparación!**")
            return
        
        await self._evaluar_reparacion(interaction)
    
    async def _usar_herramienta(self, interaction, herramienta, emoji, problemas_compatibles):
        if not self.problemas_detectados:
            await self._actualizar_mensaje(interaction, "⚠️ **¡Primero necesitas diagnosticar problemas!**")
            return
        
        self.herramientas_usadas.add(herramienta)
        self.tiempo_reparacion += 1
        
        # Verificar si la herramienta es apropiada para algún problema detectado
        problemas_vehiculo = self.vehiculo_objetivo["problemas"]
        problema_reparado = None
        
        for problema in self.problemas_detectados:
            if problema in problemas_vehiculo and any(comp in problema for comp in problemas_compatibles):
                if problema not in self.reparaciones_realizadas:
                    problema_reparado = problema
                    break
        
        if problema_reparado:
            self.reparaciones_realizadas.append(problema_reparado)
            self.precision_bonus += 20
            await self._actualizar_mensaje(interaction, f"✅ **{emoji} ¡Problema '{problema_reparado}' reparado! (+20 precisión)**")
        else:
            if random.random() < 0.3:  # 30% de chance de pequeño progreso
                self.precision_bonus += 5
                await self._actualizar_mensaje(interaction, f"🔧 **{emoji} Trabajo realizado, pequeño progreso... (+5 precisión)**")
            else:
                await self._actualizar_mensaje(interaction, f"⚠️ **{emoji} Herramienta no es la adecuada para este problema...**")
    
    async def _evaluar_reparacion(self, interaction):
        problemas_objetivo = self.vehiculo_objetivo["problemas"]
        problemas_reales_detectados = [p for p in self.problemas_detectados if p in problemas_objetivo]
        problemas_falsos_detectados = [p for p in self.problemas_detectados if p not in problemas_objetivo]
        
        problemas_reparados_correctos = len([p for p in self.reparaciones_realizadas if p in problemas_objetivo])
        precision_reparacion = (problemas_reparados_correctos / len(problemas_objetivo)) * 50
        
        has_precision_tools = self.has_mejora_9
        bonus_diagnostico = len(problemas_reales_detectados) * 10
        penalizacion_falsos = len(problemas_falsos_detectados) * 8  # Aumentada levemente
        if has_precision_tools:
            penalizacion_falsos = int(penalizacion_falsos * 0.5)
        
        bonus_herramientas = min(20, len(self.herramientas_usadas) * 5)
        bonus_eficiencia = max(0, 20 - self.tiempo_reparacion * 2)
        
        puntuacion_total = (precision_reparacion + bonus_diagnostico + bonus_herramientas + 
                           bonus_eficiencia + self.precision_bonus - penalizacion_falsos)
        puntuacion_total = max(10, min(120, puntuacion_total))
        
        await self._completar_trabajo(interaction, puntuacion_total, problemas_reparados_correctos, 
                                    len(problemas_objetivo), len(problemas_falsos_detectados))
    
    async def _actualizar_mensaje(self, interaction, accion):
        problemas_texto = ", ".join([f"**{p.title()}**" for p in self.problemas_detectados]) if self.problemas_detectados else "*Ninguno*"
        reparaciones_texto = ", ".join([f"**{r.title()}**" for r in self.reparaciones_realizadas]) if self.reparaciones_realizadas else "*Ninguna*"
        herramientas_texto = ", ".join([f"**{h.replace('_', ' ').title()}**" for h in self.herramientas_usadas]) if self.herramientas_usadas else "*Ninguna*"
        
        progreso = len(self.reparaciones_realizadas) / max(1, len(self.vehiculo_objetivo["problemas"]))
        barra_progreso = '🔧' * len(self.reparaciones_realizadas) + '⬜' * max(0, len(self.vehiculo_objetivo["problemas"]) - len(self.reparaciones_realizadas))
        
        embed = discord.Embed(
            title="🔧 Trabajo: Mecánico",
            description=(
                f"🚗 **Vehículo:** {self.vehiculo_objetivo['nombre']}\n"
                f"🔍 **Problemas detectados:** {problemas_texto}\n"
                f"✅ **Reparaciones realizadas:** {reparaciones_texto}\n"
                f"🛠️ **Herramientas usadas:** {herramientas_texto}\n"
                f"📊 **Progreso:** {barra_progreso} ({len(self.reparaciones_realizadas)}/{len(self.vehiculo_objetivo['problemas'])})\n"
                f"⚡ **Precisión acumulada:** +{self.precision_bonus}\n\n"
                f"{accion}"
            ),
            color=discord.Color.dark_gray()
        )
        
        controles_txt = (
            "🔍 **Diagnosticar** | 🔧 **Llave** | 🪛 **Destornillador** | 🔨 **Martillo** | ⚡ **Multímetro**\n"
            "⚙️ **Terminar:** Finaliza la reparación (mín. 1 diagnóstico + 1 reparación)"
        )
        if self.nivel >= 5:
            controles_txt += "\n📟 **Escáner OBD:** Limpia los falsos diagnósticos del listado (1 uso)."
        if self.nivel >= 8:
            controles_txt += "\n🔬 **Diagnóstico Avanzado:** Identifica todos los problemas reales de inmediato (1 uso)."
            
        embed.add_field(
            name="🎮 Controles:",
            value=controles_txt,
            inline=False
        )
        
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)
    
    async def _completar_trabajo(self, interaction, puntuacion, reparaciones_correctas, total_problemas, falsos_positivos):
        # Desactivar todos los botones
        self.diagnosticar.disabled = True
        self.usar_llave.disabled = True
        self.usar_destornillador.disabled = True
        self.usar_martillo.disabled = True
        self.usar_multimetro.disabled = True
        self.terminar_reparacion.disabled = True
        if self.nivel >= 5:
            self.escaner_obd.disabled = True
        if self.nivel >= 8:
            self.diagnostico_avanzado.disabled = True
        self.stop()
        
        user_id = self.user.id
        tipo_trabajo = 'mecanico'
        
        # Determinar resultado
        if puntuacion >= 90:
            resultado = "🏆 ¡MECÁNICO EXPERTO!"
            color = discord.Color.gold()
        elif puntuacion >= 75:
            resultado = "🌟 ¡Excelente Trabajo!"
            color = discord.Color.green()
        elif puntuacion >= 60:
            resultado = "✅ Reparación Exitosa"
            color = discord.Color.blue()
        elif puntuacion >= 40:
            resultado = "⚠️ Trabajo Aceptable"
            color = discord.Color.orange()
        else:
            resultado = "❌ Necesitas Más Práctica"
            color = discord.Color.red()
        
        # Añadir experiencia
        xp_ganada = int(puntuacion / 10) * total_problemas
        if reparaciones_correctas == total_problemas:
            xp_ganada += 15
        if falsos_positivos == 0 and reparaciones_correctas > 0:
            xp_ganada += 10
            
        # Registrar progreso y verificar subida de nivel
        recompensa_final, resultado_nivel = await asyncio.to_thread(_completar_mecanico_db, user_id, tipo_trabajo, self.recompensa_base, puntuacion, xp_ganada)
        
        subio_nivel = resultado_nivel["subio_nivel"]
        nivel_nuevo = resultado_nivel["nivel_nuevo"]
        xp_actual = resultado_nivel["xp_actual"]
        xp_para_siguiente = resultado_nivel["xp_para_siguiente"]
        
        xp_ganada_final = resultado_nivel.get("xp_ganada_final", xp_ganada)
        pocion_msg = "\n🧪 **¡Poción de Enfoque usada!** (+50% XP)" if resultado_nivel.get("pocion_usada") else ""
        
        has_precision_tools = self.has_mejora_9
        tools_msg = " (Herramientas de Precisión activas 🛠️)" if has_precision_tools else ""
        
        # Obtener información del nivel para mostrar
        if nivel_nuevo < 10:
            progreso = xp_actual / xp_para_siguiente if xp_para_siguiente > 0 else 1
            barra_progreso = '█' * int(progreso * 10) + '░' * (10 - int(progreso * 10))
            info_nivel = f"**Nivel {nivel_nuevo}** | {barra_progreso} {xp_actual}/{xp_para_siguiente} XP"
        else:
            info_nivel = f"**Nivel {nivel_nuevo}** | ✅ Nivel máximo alcanzado"
            
        embed = discord.Embed(
            title=f"🔧 {resultado}",
            description=(
                f"🚗 **Vehículo reparado:** {self.vehiculo_objetivo['nombre']}\n"
                f"📊 **Puntuación:** {int(puntuacion)}/100\n"
                f"✅ **Problemas solucionados:** {reparaciones_correctas}/{total_problemas}\n"
                f"🛠️ **Herramientas utilizadas:** {len(self.herramientas_usadas)}\n"
                f"⚡ **Precisión total:** +{self.precision_bonus}\n"
                f"❌ **Diagnósticos erróneos:** {falsos_positivos}{tools_msg}\n"
                f"🌟 **Bonus por nivel:** +{int((await asyncio.to_thread(calcular_recompensa, 1, user_id, tipo_trabajo) - 1) * 100)}%\n"
                f"💰 **Recompensa:** {recompensa_final} monedas\n\n"
                f"📊 {info_nivel}\n"
                f"✨ **XP ganada:** +{xp_ganada_final} XP{pocion_msg}"
            ),
            color=color
        )
        
        # Añadir mensaje de subida de nivel si corresponde
        if subio_nivel:
            nueva_bonificacion = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel_nuevo, "Sin bonificación")
            embed.add_field(
                name="🎊 ¡SUBISTE DE NIVEL!",
                value=f"Tu nivel de Mecánico ha subido a **{nivel_nuevo}**\n"
                      f"🌟 **Nueva bonificación:** {nueva_bonificacion}",
                inline=False
            )
        
        if len(self.herramientas_usadas) >= 4:
            embed.add_field(
                name="🛠️ ¡Maestro de Herramientas!",
                value="Usaste todas las herramientas disponibles",
                inline=False
            )
        
        if falsos_positivos == 0 and reparaciones_correctas == total_problemas:
            embed.add_field(
                name="🎯 ¡Precisión Perfecta!",
                value="Sin diagnósticos erróneos y todos los problemas solucionados",
                inline=False
            )
        
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

def _completar_mecanico_db(user_id, tipo_trabajo, recompensa_base, puntuacion, xp_ganada):
    recompensa_base_con_nivel = calcular_recompensa(recompensa_base, user_id, tipo_trabajo)
    multiplicador = puntuacion / 100
    recompensa_final = int(recompensa_base_con_nivel * multiplicador)
    
    resultado_nivel = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
    
    if recompensa_final > 0:
        saldo_actual = get_balance(user_id)
        set_balance(user_id, saldo_actual + recompensa_final)
        registrar_transaccion(user_id, recompensa_final, "Trabajo: Mecánico completado")
        
    return recompensa_final, resultado_nivel

def _iniciar_mecanico_db(user_id, tipo_trabajo):
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    energia_actual = get_energia(user_id)
    energia_base = 30
    energia_requerida = calcular_energia_requerida(energia_base, user_id, tipo_trabajo)
    has_mejora_9 = usuario_tiene_mejora(user_id, 9)
    
    if energia_actual >= energia_requerida:
        set_energia(user_id, energia_actual - energia_requerida)
        
    bonificacion_recompensa = calcular_recompensa(1, user_id, tipo_trabajo) - 1
    bonificacion_energia = calcular_energia_requerida(100, user_id, tipo_trabajo) / 100
        
    return nivel_info, energia_actual, energia_requerida, has_mejora_9, bonificacion_recompensa, bonificacion_energia

async def iniciar_trabajo_mecanico(interaction: discord.Interaction):
    """Función principal para iniciar el trabajo de mecánico."""
    user_id = interaction.user.id
    tipo_trabajo = 'mecanico'
    
    nivel_info, energia_actual, energia_requerida, has_mejora_9, bonificacion_recompensa, bonificacion_energia = await asyncio.to_thread(_iniciar_mecanico_db, user_id, tipo_trabajo)
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
    
    # Vehículos disponibles con rango de nivel
    vehiculos_todos = [
        # Fácil (Nivel 0-2)
        {
            "nombre": "🚗 Sedán Familiar",
            "problemas": ["frenos gastados", "batería descargada"],
            "dificultad": "Fácil",
            "nivel_min": 0,
            "recompensa_base": 350
        },
        {
            "nombre": "🏍️ Motocicleta Clásica",
            "problemas": ["carburador sucio", "cadena floja"],
            "dificultad": "Fácil",
            "nivel_min": 0,
            "recompensa_base": 350
        },
        
        # Medio (Nivel 3-5)
        {
            "nombre": "🚙 SUV Deportivo",
            "problemas": ["motor irregular", "transmisión dura", "luces fundidas"],
            "dificultad": "Medio",
            "nivel_min": 3,
            "recompensa_base": 480
        },
        {
            "nombre": "🏎️ Auto Deportivo",
            "problemas": ["motor sobrecalentado", "panel eléctrico defectuoso", "luces fundidas"],
            "dificultad": "Medio",
            "nivel_min": 3,
            "recompensa_base": 480
        },
        
        # Difícil (Nivel 6-8)
        {
            "nombre": "🚚 Camión de Carga Pesada",
            "problemas": ["frenos de aire", "motor diesel", "escape roto", "chasis dañado"],
            "dificultad": "Difícil",
            "nivel_min": 6,
            "recompensa_base": 650
        },
        
        # Maestro (Nivel 9-10)
        {
            "nombre": "✈️ Avión de Hélice Biplaza",
            "problemas": ["hélice rota", "motor irregular", "panel eléctrico defectuoso", "fuga de combustible", "tren de aterrizaje"],
            "dificultad": "Maestro",
            "nivel_min": 9,
            "recompensa_base": 900
        }
    ]
    
    # Filtrar vehículos disponibles
    vehiculos_disponibles = [v for v in vehiculos_todos if nivel >= v["nivel_min"]]
    if not vehiculos_disponibles:
        vehiculos_disponibles = [v for v in vehiculos_todos if v["nivel_min"] == 0]
        
    vehiculo_objetivo = random.choice(vehiculos_disponibles)
    recompensa_base = vehiculo_objetivo["recompensa_base"]
    
    # Mostrar recompensa con bonus de nivel aplicado
    recompensa_con_nivel = await asyncio.to_thread(calcular_recompensa, recompensa_base, user_id, tipo_trabajo)
    
    # Info de nivel para mostrar
    bonificacion_actual = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel, "Sin bonificaciones")
    
    obd_inicial = ""
    if nivel >= 5:
        obd_inicial = f"📟 **Escáner OBD listo!** Podrás limpiar falsos diagnósticos.\n"
    adv_inicial = ""
    if nivel >= 8:
        adv_inicial = f"🔬 **Diagnóstico Avanzado listo!** Podrás detectar problemas reales al instante.\n"
        
    embed = discord.Embed(
        title="🔧 Trabajo: Mecánico",
        description=(
            f"🚗 **Vehículo a reparar:** {vehiculo_objetivo['nombre']}\n"
            f"🔧 **Problemas reportados:** {len(vehiculo_objetivo['problemas'])} problemas\n"
            f"🏆 **Dificultad:** {vehiculo_objetivo['dificultad']}\n"
            f"💰 **Recompensa:** {recompensa_con_nivel}+ monedas\n"
            f"⏱️ **Tiempo límite:** 3 minutos\n\n"
            f"{obd_inicial}"
            f"{adv_inicial}\n"
            f"📊 **Nivel actual:** {nivel} ({'+' + str(int(bonificacion_recompensa * 100)) + '%' if bonificacion_recompensa > 0 else '0%'} recompensa, {'-' + str(int((1-bonificacion_energia) * 100)) + '%' if bonificacion_energia < 1 else '0%'} energía)\n"
            f"🌟 **Bonificación de nivel:** {bonificacion_actual}\n\n"
            f"🔍 **¡Comienza diagnosticando los problemas!**"
        ),
        color=discord.Color.dark_gray()
    )
    
    controles_txt = (
        "1️⃣ **Diagnostica** para encontrar problemas\n"
        "2️⃣ **Usa herramientas** apropiadas para cada problema\n"
        "3️⃣ **Evita falsos diagnósticos** (penalizan)\n"
        "4️⃣ **Termina** cuando hayas reparado todo"
    )
    if nivel >= 5:
        controles_txt += "\n💡 *Tip:* Si tienes muchos fallos de diagnóstico, usa el Escáner OBD."
        
    embed.add_field(
        name="🎮 Cómo jugar:",
        value=controles_txt,
        inline=False
    )
    
    view = MecanicoView(interaction.user, vehiculo_objetivo, recompensa_base, nivel)
    view.has_mejora_9 = has_mejora_9
    await interaction.response.send_message(embed=embed, view=view)
