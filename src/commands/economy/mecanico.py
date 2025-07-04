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

class MecanicoView(discord.ui.View):
    def __init__(self, user, vehiculo_objetivo, recompensa_base):
        super().__init__(timeout=180)  # 3 minutos para completar
        self.user = user
        self.vehiculo_objetivo = vehiculo_objetivo
        self.recompensa_base = recompensa_base
        self.problemas_detectados = []
        self.reparaciones_realizadas = []
        self.herramientas_usadas = set()
        self.precision_bonus = 0
        self.tiempo_reparacion = 0
        
    @discord.ui.button(label="🔍 Diagnosticar", style=discord.ButtonStyle.primary)
    async def diagnosticar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        problemas_posibles = self.vehiculo_objetivo["problemas"]
        
        if len(self.problemas_detectados) >= len(problemas_posibles):
            await self._actualizar_mensaje(interaction, "🔍 **Ya diagnosticaste todos los problemas posibles!**")
            return
        
        # 70% chance de detectar un problema real, 30% falso positivo
        if random.random() < 0.7 and len(self.problemas_detectados) < len(problemas_posibles):
            problema_real = random.choice([p for p in problemas_posibles if p not in self.problemas_detectados])
            self.problemas_detectados.append(problema_real)
            self.precision_bonus += 15
            await self._actualizar_mensaje(interaction, f"✅ **Problema detectado: {problema_real}! (+15 precisión)**")
        else:
            problemas_falsos = ["fuga de aceite menor", "ruido en el motor", "vibración extraña", "luz de check engine"]
            falso_problema = random.choice(problemas_falsos)
            if falso_problema not in self.problemas_detectados:
                self.problemas_detectados.append(falso_problema)
                await self._actualizar_mensaje(interaction, f"⚠️ **Posible problema: {falso_problema} (requiere verificación)**")
            else:
                await self._actualizar_mensaje(interaction, f"🔍 **Revisando nuevamente el sistema...**")
    
    @discord.ui.button(label="🔧 Llave Inglesa", style=discord.ButtonStyle.secondary)
    async def usar_llave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._usar_herramienta(interaction, "llave_inglesa", "🔧", ["motor", "transmisión", "frenos"])
    
    @discord.ui.button(label="🪛 Destornillador", style=discord.ButtonStyle.secondary)
    async def usar_destornillador(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._usar_herramienta(interaction, "destornillador", "🪛", ["panel eléctrico", "interior", "luces"])
    
    @discord.ui.button(label="🔨 Martillo", style=discord.ButtonStyle.secondary)
    async def usar_martillo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._usar_herramienta(interaction, "martillo", "🔨", ["chasis", "carrocería", "escape"])
    
    @discord.ui.button(label="⚡ Multímetro", style=discord.ButtonStyle.secondary)
    async def usar_multimetro(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await self._usar_herramienta(interaction, "multimetro", "⚡", ["panel eléctrico", "batería", "luces"])
    
    @discord.ui.button(label="🔧 Terminar Reparación", style=discord.ButtonStyle.success)
    async def terminar_reparacion(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
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
            # Herramienta incorrecta o problema ya reparado
            if random.random() < 0.3:  # 30% chance de pequeño progreso
                self.precision_bonus += 5
                await self._actualizar_mensaje(interaction, f"🔧 **{emoji} Trabajo realizado, pequeño progreso... (+5 precisión)**")
            else:
                await self._actualizar_mensaje(interaction, f"⚠️ **{emoji} Herramienta no es la ideal para este problema...**")
    
    async def _evaluar_reparacion(self, interaction):
        problemas_objetivo = self.vehiculo_objetivo["problemas"]
        problemas_reales_detectados = [p for p in self.problemas_detectados if p in problemas_objetivo]
        problemas_falsos_detectados = [p for p in self.problemas_detectados if p not in problemas_objetivo]
        
        # Puntuación base por problemas reparados correctamente
        problemas_reparados_correctos = len([p for p in self.reparaciones_realizadas if p in problemas_objetivo])
        precision_reparacion = (problemas_reparados_correctos / len(problemas_objetivo)) * 50
        
        # Bonificación por diagnóstico preciso
        bonus_diagnostico = len(problemas_reales_detectados) * 10
        
        # Penalización por falsos positivos
        penalizacion_falsos = len(problemas_falsos_detectados) * 5
        
        # Bonificación por variedad de herramientas
        bonus_herramientas = min(20, len(self.herramientas_usadas) * 5)
        
        # Bonificación por eficiencia (menos tiempo = mejor)
        bonus_eficiencia = max(0, 20 - self.tiempo_reparacion * 2)
        
        puntuacion_total = (precision_reparacion + bonus_diagnostico + bonus_herramientas + 
                           bonus_eficiencia + self.precision_bonus - penalizacion_falsos)
        puntuacion_total = max(10, min(100, puntuacion_total))  # Entre 10 y 100
        
        await self._completar_trabajo(interaction, puntuacion_total, problemas_reparados_correctos, 
                                    len(problemas_objetivo), len(problemas_falsos_detectados))
    
    async def _actualizar_mensaje(self, interaction, accion):
        problemas_texto = ", ".join([f"**{p}**" for p in self.problemas_detectados]) if self.problemas_detectados else "*Ninguno*"
        reparaciones_texto = ", ".join([f"**{r}**" for r in self.reparaciones_realizadas]) if self.reparaciones_realizadas else "*Ninguna*"
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
        embed.add_field(
            name="🎮 Controles:",
            value=(
                "🔍 **Diagnosticar** | 🔧 **Llave** | 🪛 **Destornillador** | 🔨 **Martillo** | ⚡ **Multímetro**\n"
                "🔧 **Terminar:** Finaliza la reparación (mín. 1 diagnóstico + 1 reparación)"
            ),
            inline=False
        )
        
        try:
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
        self.stop()
        
        # Obtener bonificación por nivel
        user_id = self.user.id
        tipo_trabajo = 'mecanico'
            
        # Aplicar bonificación de nivel a la recompensa base
        recompensa_base_con_nivel = calcular_recompensa(self.recompensa_base, user_id, tipo_trabajo)
            
        # Calcular recompensa final con multiplicador de puntuación
        multiplicador = puntuacion / 100
        recompensa_final = int(recompensa_base_con_nivel * multiplicador)
        
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
        
        # Añadir experiencia (depende de la dificultad y éxito)
        xp_ganada = int(puntuacion / 10) * total_problemas  # XP base según puntuación y problemas totales
        
        if reparaciones_correctas == total_problemas:
            xp_ganada += 15  # Bonus por completar todos los problemas
        
        if falsos_positivos == 0 and reparaciones_correctas > 0:
            xp_ganada += 10  # Bonus por precisión
            
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
            registrar_transaccion(user_id, recompensa_final, "Trabajo: Mecánico completado")
        
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
                f"❌ **Diagnósticos erróneos:** {falsos_positivos}\n"
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
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

async def iniciar_trabajo_mecanico(interaction: discord.Interaction):
    """Función principal para iniciar el trabajo de mecánico."""
    user_id = interaction.user.id
    tipo_trabajo = 'mecanico'
    
    # Obtener nivel del trabajo y bonificaciones
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel = nivel_info["nivel"]
    
    # Verificar energía del usuario - aplicar bonificación por nivel
    energia_actual = get_energia(user_id)
    energia_base = 30
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
    
    # Vehículos disponibles
    vehiculos_disponibles = [
        {
            "nombre": "🚗 Sedán Familiar",
            "problemas": ["frenos gastados", "batería descargada"],
            "dificultad": "Fácil"
        },
        {
            "nombre": "🚙 SUV Deportivo",
            "problemas": ["motor irregular", "transmisión dura", "luces fundidas"],
            "dificultad": "Medio"
        },
        {
            "nombre": "🏎️ Auto Deportivo",
            "problemas": ["motor sobrecalentado", "panel eléctrico defectuoso"],
            "dificultad": "Medio"
        },
        {
            "nombre": "🚚 Camión de Carga",
            "problemas": ["frenos de aire", "motor diesel", "escape roto", "chasis dañado"],
            "dificultad": "Difícil"
        },
        {
            "nombre": "🏍️ Motocicleta Clásica",
            "problemas": ["carburador sucio", "cadena floja", "luces LED"],
            "dificultad": "Medio"
        }
    ]
    
    # Seleccionar vehículo aleatorio
    vehiculo_objetivo = random.choice(vehiculos_disponibles)
    
    # Calcular recompensa base según dificultad
    if vehiculo_objetivo["dificultad"] == "Fácil":
        recompensa_base = 200
    elif vehiculo_objetivo["dificultad"] == "Medio":
        recompensa_base = 300
    else:  # Difícil
        recompensa_base = 450
    
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
        title="🔧 Trabajo: Mecánico",
        description=(
            f"🚗 **Vehículo a reparar:** {vehiculo_objetivo['nombre']}\n"
            f"🔧 **Problemas reportados:** {len(vehiculo_objetivo['problemas'])} problemas\n"
            f"🏆 **Dificultad:** {vehiculo_objetivo['dificultad']}\n"
            f"💰 **Recompensa:** {recompensa_con_nivel}+ monedas\n"
            f"⏱️ **Tiempo límite:** 3 minutos\n\n"
            f"📊 **Nivel actual:** {nivel_actual} ({'+' + str(int(bonificacion_recompensa * 100)) + '%' if bonificacion_recompensa > 0 else '0%'} recompensa, {'-' + str(int((1-bonificacion_energia) * 100)) + '%' if bonificacion_energia < 1 else '0%'} energía)\n"
            f"🌟 **Bonificación de nivel:** {bonificacion_actual}\n\n"
            f"🔍 **¡Comienza diagnosticando los problemas!**"
        ),
        color=discord.Color.dark_gray()
    )
    embed.add_field(
        name="🎮 Cómo jugar:",
        value=(
            "1️⃣ **Diagnostica** para encontrar problemas\n"
            "2️⃣ **Usa herramientas** apropiadas para cada problema\n"
            "3️⃣ **Evita falsos diagnósticos** (penalizan)\n"
            "4️⃣ **Termina** cuando hayas reparado todo"
        ),
        inline=False
    )
    
    view = MecanicoView(interaction.user, vehiculo_objetivo, recompensa_base)
    await interaction.response.send_message(embed=embed, view=view)
