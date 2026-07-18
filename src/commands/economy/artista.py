import discord
import random
from src.db import get_balance, set_balance, registrar_transaccion, usuario_tiene_mejora, consumir_energia, pagar_recompensa_trabajo
from .energia import get_energia, set_energia
from .niveles_trabajo import (
    add_experiencia_trabajo, 
    calcular_energia_requerida, 
    calcular_recompensa, 
    get_nivel_trabajo,
    TIPOS_TRABAJO
)
import asyncio

class ArtStyleSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Ninguno 🎨", value="ninguno", description="No usar estilo específico"),
            discord.SelectOption(label="Impresionismo 🖌️", value="impresionismo", description="Bono: +20% por cada color correcto"),
            discord.SelectOption(label="Cubismo 🔲", value="cubismo", description="Bono: +10% por pincelada (máx +50%)"),
            discord.SelectOption(label="Realismo 🖼️", value="realismo", description="Bono: +35% por precisión exacta de colores y pinceladas")
        ]
        super().__init__(placeholder="Elige un estilo de obra...", min_values=1, max_values=1, options=options, row=2)
        
    async def callback(self, interaction: discord.Interaction):
        self.view.estilo_seleccionado = self.values[0]
        label_estilo = self.values[0].title()
        if self.values[0] == "impresionismo":
            label_estilo = "Impresionismo 🖌️"
        elif self.values[0] == "cubismo":
            label_estilo = "Cubismo 🔲"
        elif self.values[0] == "realismo":
            label_estilo = "Realismo 🖼️"
        else:
            label_estilo = "Ninguno 🎨"
        await self.view._actualizar_mensaje(interaction, f"✨ **Estilo seleccionado: {label_estilo}**")

class AuctionView(discord.ui.View):
    def __init__(self, user, recompensa_obra, xp_ganada, obra_nombre, puntuacion_total, colores_correctos, colores_objetivo_total, pinceladas, creatividad_bonus, estilo_feedback):
        super().__init__(timeout=90)
        self.user = user
        self.recompensa_obra = recompensa_obra
        self.xp_ganada = xp_ganada
        self.obra_nombre = obra_nombre
        self.puntuacion_total = puntuacion_total
        self.colores_correctos = colores_correctos
        self.colores_objetivo_total = colores_objetivo_total
        self.pinceladas = pinceladas
        self.creatividad_bonus = creatividad_bonus
        self.estilo_feedback = estilo_feedback
        
        # NPC Offers: Conservador (0.7x a 1.3x), Arriesgado (0.4x a 2.0x), Salvaje (0.1x a 3.0x)
        self.mult1 = round(random.uniform(0.7, 1.3), 2)
        self.mult2 = round(random.uniform(0.4, 2.0), 2)
        self.mult3 = round(random.uniform(0.1, 3.0), 2)
        
    @discord.ui.button(label="🖼️ Venta Directa (1.0x)", style=discord.ButtonStyle.primary)
    async def venta_directa(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes participar en esta subasta.", ephemeral=True)
            return
        await interaction.response.defer()
        await self._finalizar_con_multiplicador(interaction, 1.0, "Galería Nacional (Venta Directa)")
        
    @discord.ui.button(label="🏛️ Oferta de Mecenas", style=discord.ButtonStyle.secondary)
    async def oferta_mecenas(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes participar en esta subasta.", ephemeral=True)
            return
        await interaction.response.defer()
        await self._finalizar_con_multiplicador(interaction, self.mult1, "Mecenas Moderno (Conservador)")
        
    @discord.ui.button(label="🎭 Oferta de Coleccionista", style=discord.ButtonStyle.secondary)
    async def oferta_coleccionista(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes participar en esta subasta.", ephemeral=True)
            return
        await interaction.response.defer()
        await self._finalizar_con_multiplicador(interaction, self.mult2, "Coleccionista Excéntrico (Arriesgado)")
        
    @discord.ui.button(label="🕵️ Oferta Anónima", style=discord.ButtonStyle.secondary)
    async def oferta_anonima(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes participar en esta subasta.", ephemeral=True)
            return
        await interaction.response.defer()
        await self._finalizar_con_multiplicador(interaction, self.mult3, "Comprador Anónimo (Salvaje)")

    async def _finalizar_con_multiplicador(self, interaction, mult, comprador):
        self.venta_directa.disabled = True
        self.oferta_mecenas.disabled = True
        self.oferta_coleccionista.disabled = True
        self.oferta_anonima.disabled = True
        self.stop()
        
        recompensa_final = int(self.recompensa_obra * mult)
        user_id = self.user.id
        
        resultado_nivel, has_easel, has_prestige = await asyncio.to_thread(
            _finalizar_artista_db, user_id, recompensa_final, self.xp_ganada, f"subastado a {comprador}"
        )
            
        subio_nivel = resultado_nivel["subio_nivel"]
        nivel_nuevo = resultado_nivel["nivel_nuevo"]
        xp_actual = resultado_nivel["xp_actual"]
        xp_para_siguiente = resultado_nivel["xp_para_siguiente"]
        
        xp_ganada_final = resultado_nivel.get("xp_ganada_final", self.xp_ganada)
        pocion_msg = "\n🧪 **¡Poción de Enfoque usada!** (+50% XP)" if resultado_nivel.get("pocion_usada") else ""
        
        easel_msg = ""
        if has_prestige:
            easel_msg = "\n🖼️ **Caballete Divino Prestigio activo:** +20 creatividad base"
        elif has_easel:
            easel_msg = "\n🖼️ **Caballete de Oro activo:** +10 creatividad base"
        
        if nivel_nuevo < 10:
            progreso = xp_actual / xp_para_siguiente if xp_para_siguiente > 0 else 1
            barra_progreso = '█' * int(progreso * 10) + '░' * (10 - int(progreso * 10))
            info_nivel = f"**Nivel {nivel_nuevo}** | {barra_progreso} {xp_actual}/{xp_para_siguiente} XP"
        else:
            info_nivel = f"**Nivel {nivel_nuevo}** | ✅ Nivel máximo alcanzado"
            
        puntuacion = self.puntuacion_total
        if puntuacion >= 90:
            resultado = "🏆 ¡OBRA MAESTRA!"
            color = discord.Color.gold()
        elif puntuacion >= 75:
            resultado = "🌟 ¡Arte Excepcional!"
            color = discord.Color.purple()
        elif puntuacion >= 60:
            resultado = "✅ Buen Trabajo"
            color = discord.Color.blue()
        else:
            resultado = "⚠️ Arte Amateur"
            color = discord.Color.orange()
            
        embed = discord.Embed(
            title=f"🎨 {resultado} - ¡Vendido por Subasta!",
            description=(
                f"🖼️ **Obra creada:** {self.obra_nombre}\n"
                f"👥 **Comprador final:** {comprador}\n"
                f"📈 **Oferta aceptada:** `{mult}x`\n"
                f"📊 **Puntuación:** {int(puntuacion)}/100\n"
                f"🎯 **Precisión de colores:** {self.colores_correctos}/{self.colores_objetivo_total}\n"
                f"🖌️ **Pinceladas totales:** {self.pinceladas}\n"
                f"✨ **Bonus creatividad:** +{self.creatividad_bonus}{easel_msg}\n"
                f"{self.estilo_feedback}\n"
                f"💰 **Recompensa Base:** {self.recompensa_obra} monedas\n"
                f"💵 **Ganancia final:** {recompensa_final} monedas\n\n"
                f"📊 {info_nivel}\n"
                f"✨ **XP ganada:** +{xp_ganada_final} XP{pocion_msg}"
            ),
            color=color
        )
        
        if subio_nivel:
            nueva_bonificacion = TIPOS_TRABAJO['artista']['bonificaciones'].get(nivel_nuevo, "Sin bonificación")
            embed.add_field(
                name="🎊 ¡SUBISTE DE NIVEL!",
                value=f"Tu nivel de Artista ha subido a **{nivel_nuevo}**\n"
                      f"🌟 **Nueva bonificación:** {nueva_bonificacion}",
                inline=False
            )
            
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)

class ArtistaView(discord.ui.View):
    def __init__(self, user, obra_objetivo, recompensa_base, nivel):
        super().__init__(timeout=120)  # 2 minutos para completar
        self.user = user
        self.obra_objetivo = obra_objetivo
        self.recompensa_base = recompensa_base
        self.nivel = nivel
        self.colores_seleccionados = []
        self.tecnicas_usadas = []
        self.has_mejora_8 = False
        self.creatividad_bonus = 0
        self.pinceladas = 0
        self.estilo_seleccionado = "ninguno"
        
        # Desbloqueos interactivos
        if self.nivel >= 5:
            self.add_item(ArtStyleSelect())
        
    @discord.ui.button(label="🔴 Rojo", style=discord.ButtonStyle.danger)
    async def color_rojo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._usar_color(interaction, "rojo", "🔴")
    
    @discord.ui.button(label="🔵 Azul", style=discord.ButtonStyle.primary)
    async def color_azul(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._usar_color(interaction, "azul", "🔵")
    
    @discord.ui.button(label="🟡 Amarillo", style=discord.ButtonStyle.secondary)
    async def color_amarillo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._usar_color(interaction, "amarillo", "🟡")
    
    @discord.ui.button(label="🟢 Verde", style=discord.ButtonStyle.success)
    async def color_verde(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self._usar_color(interaction, "verde", "🟢")
    
    @discord.ui.button(label="🖌️ Pincelar", style=discord.ButtonStyle.secondary)
    async def pincelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        if not self.colores_seleccionados:
            await self._actualizar_mensaje(interaction, "⚠️ **¡Necesitas seleccionar al menos un color primero!**")
            return
        
        self.pinceladas += 1
        
        # Posibilidad de técnica especial
        if random.random() < 0.35:  # 35% chance
            tecnica = random.choice(["difuminado", "textura", "sombras", "luces"])
            if tecnica not in self.tecnicas_usadas:
                self.tecnicas_usadas.append(tecnica)
                self.creatividad_bonus += 12
                await self._actualizar_mensaje(interaction, f"✨ **¡Técnica especial: {tecnica.title()}! (+12 creatividad)**")
            else:
                await self._actualizar_mensaje(interaction, f"🖌️ **Pincelada aplicada... ({self.pinceladas} total)**")
        else:
            await self._actualizar_mensaje(interaction, f"🖌️ **Pincelada aplicada... ({self.pinceladas} total)**")
    
    @discord.ui.button(label="🎨 Finalizar Obra", style=discord.ButtonStyle.success)
    async def finalizar_obra(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este trabajo.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        if len(self.colores_seleccionados) < 2:
            await self._actualizar_mensaje(interaction, "⚠️ **Necesitas al menos 2 colores para finalizar la obra!**")
            return
            
        min_pinceladas = 3
        if self.nivel >= 6:
            min_pinceladas = 5
        elif self.nivel >= 3:
            min_pinceladas = 4
        
        if self.pinceladas < min_pinceladas:
            await self._actualizar_mensaje(interaction, f"⚠️ **Necesitas al menos {min_pinceladas} pinceladas para esta obra!**")
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
        colores = set(self.colores_seleccionados)
        if {"rojo", "azul", "amarillo"}.issubset(colores):
            return 25  # Colores primarios
        elif {"rojo", "azul"}.issubset(colores):
            return 12  # Contraste frío-cálido
        elif {"amarillo", "verde"}.issubset(colores):
            return 12  # Naturaleza
        elif {"rojo", "amarillo"}.issubset(colores):
            return 12  # Calidez
        return 0
    
    async def _evaluar_obra(self, interaction):
        colores_objetivo = self.obra_objetivo["colores"]
        colores_correctos = len(set(self.colores_seleccionados) & set(colores_objetivo))
        
        # Puntuación base
        precision_colores = (colores_correctos / len(colores_objetivo)) * 60
        bonus_tecnica = min(30, self.pinceladas * 3)
        bonus_creatividad = min(40, self.creatividad_bonus)
        
        puntuacion_total = precision_colores + bonus_tecnica + bonus_creatividad
        puntuacion_total = min(100, puntuacion_total)
        
        # Estilo de obra (Nivel >= 5)
        estilo_multiplier = 1.0
        estilo_feedback = ""
        
        if self.nivel >= 5 and self.estilo_seleccionado != "ninguno":
            if self.estilo_seleccionado == "impresionismo":
                bonus = colores_correctos * 0.20
                estilo_multiplier = 1.0 + bonus
                estilo_feedback = f"\n🖌️ **Estilo Impresionista:** +{int(bonus * 100)}% por {colores_correctos} colores correctos."
            elif self.estilo_seleccionado == "cubismo":
                bonus = min(0.50, self.pinceladas * 0.10)
                estilo_multiplier = 1.0 + bonus
                estilo_feedback = f"\n🔲 **Estilo Cubista:** +{int(bonus * 100)}% por {self.pinceladas} pinceladas."
            elif self.estilo_seleccionado == "realismo":
                exact_pinceladas = 5 if self.nivel >= 6 else 4 if self.nivel >= 3 else 3
                if colores_correctos == len(colores_objetivo) and self.pinceladas == exact_pinceladas:
                    estilo_multiplier = 1.35
                    estilo_feedback = f"\n🎨 **Estilo Realista Perfecto:** +35% de recompensa."
                else:
                    estilo_multiplier = 0.70
                    estilo_feedback = f"\n❌ **Estilo Realista Defectuoso:** Penalización por desbalance. (-30% monedas)"
                    
        # XP y Recompensa Base con Nivel
        xp_ganada = int(puntuacion_total / 10) * len(colores_objetivo)
        if colores_correctos == len(colores_objetivo):
            xp_ganada += 15
        if self.creatividad_bonus >= 30:
            xp_ganada += 10
            
        recompensa_base_con_nivel = await asyncio.to_thread(calcular_recompensa, self.recompensa_base, self.user.id, 'artista')
        recompensa_obra = int(recompensa_base_con_nivel * (puntuacion_total / 100) * estilo_multiplier)
        
        # Nivel >= 8: Iniciar Subasta de Arte interactiva
        if self.nivel >= 8:
            embed = discord.Embed(
                title="🎭 Subasta de Arte Activa",
                description=(
                    f"🎨 **Obra completada:** {self.obra_objetivo['nombre']}\n"
                    f"💰 **Valores estimados de mercado:** {recompensa_obra} monedas\n\n"
                    f"NPCs y coleccionistas están listos para pujar por tu pintura.\n"
                    f"Puedes tomar la oferta segura del museo o tentar tu suerte con subastas de alto riesgo."
                ),
                color=discord.Color.gold()
            )
            view = AuctionView(
                self.user, recompensa_obra, xp_ganada, self.obra_objetivo['nombre'],
                puntuacion_total, colores_correctos, len(colores_objetivo),
                self.pinceladas, self.creatividad_bonus, estilo_feedback
            )
            try:
                if interaction.response.is_done():
                    await interaction.edit_original_response(embed=embed, view=view)
                else:
                    await interaction.response.edit_message(embed=embed, view=view)
            except discord.InteractionResponded:
                await interaction.edit_original_response(embed=embed, view=view)
        else:
            # Flujo estándar sin subasta (Nivel < 8)
            await self._completar_trabajo_estandar(interaction, puntuacion_total, colores_correctos, len(colores_objetivo), recompensa_obra, xp_ganada, estilo_feedback)
            
    async def _completar_trabajo_estandar(self, interaction, puntuacion, colores_correctos, colores_objetivo_total, recompensa_final, xp_ganada, estilo_feedback):
        self.color_rojo.disabled = True
        self.color_azul.disabled = True
        self.color_amarillo.disabled = True
        self.color_verde.disabled = True
        self.pincelar.disabled = True
        self.finalizar_obra.disabled = True
        self.stop()
        
        user_id = self.user.id
        
        resultado_nivel, has_easel, has_prestige = await asyncio.to_thread(
            _finalizar_artista_db, user_id, recompensa_final, xp_ganada, "Venta estándar"
        )
            
        subio_nivel = resultado_nivel["subio_nivel"]
        nivel_nuevo = resultado_nivel["nivel_nuevo"]
        xp_actual = resultado_nivel["xp_actual"]
        xp_para_siguiente = resultado_nivel["xp_para_siguiente"]
        
        xp_ganada_final = resultado_nivel.get("xp_ganada_final", xp_ganada)
        pocion_msg = "\n🧪 **¡Poción de Enfoque usada!** (+50% XP)" if resultado_nivel.get("pocion_usada") else ""
        
        easel_msg = ""
        if has_prestige:
            easel_msg = "\n🖼️ **Caballete Divino Prestigio activo:** +20 creatividad base"
        elif has_easel:
            easel_msg = "\n🖼️ **Caballete de Oro activo:** +10 creatividad base"
        
        if nivel_nuevo < 10:
            progreso = xp_actual / xp_para_siguiente if xp_para_siguiente > 0 else 1
            barra_progreso = '█' * int(progreso * 10) + '░' * (10 - int(progreso * 10))
            info_nivel = f"**Nivel {nivel_nuevo}** | {barra_progreso} {xp_actual}/{xp_para_siguiente} XP"
        else:
            info_nivel = f"**Nivel {nivel_nuevo}** | ✅ Nivel máximo alcanzado"
            
        if puntuacion >= 90:
            resultado = "🏆 ¡OBRA MAESTRA!"
            color = discord.Color.gold()
        elif puntuacion >= 75:
            resultado = "🌟 ¡Arte Excepcional!"
            color = discord.Color.purple()
        elif puntuacion >= 60:
            resultado = "✅ Buen Trabajo"
            color = discord.Color.blue()
        else:
            resultado = "⚠️ Arte Amateur"
            color = discord.Color.orange()
            
        embed = discord.Embed(
            title=f"🎨 {resultado}",
            description=(
                f"🖼️ **Obra creada:** {self.obra_objetivo['nombre']}\n"
                f"📊 **Puntuación:** {int(puntuacion)}/100\n"
                f"🎯 **Precisión de colores:** {colores_correctos}/{colores_objetivo_total}\n"
                f"🖌️ **Pinceladas totales:** {self.pinceladas}\n"
                f"✨ **Bonus creatividad:** +{self.creatividad_bonus}{easel_msg}\n"
                f"{estilo_feedback}\n"
                f"🌟 **Bonus por nivel:** +{int((await asyncio.to_thread(calcular_recompensa, 1, user_id, 'artista') - 1) * 100)}%\n"
                f"💰 **Recompensa:** {recompensa_final} monedas\n\n"
                f"📊 {info_nivel}\n"
                f"✨ **XP ganada:** +{xp_ganada_final} XP{pocion_msg}"
            ),
            color=color
        )
        
        if subio_nivel:
            nueva_bonificacion = TIPOS_TRABAJO['artista']['bonificaciones'].get(nivel_nuevo, "Sin bonificación")
            embed.add_field(
                name="🎊 ¡SUBISTE DE NIVEL!",
                value=f"Tu nivel de Artista ha subido a **{nivel_nuevo}**\n"
                      f"🌟 **Nueva bonificación:** {nueva_bonificacion}",
                inline=False
            )
            
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)
            
    async def _actualizar_mensaje(self, interaction, accion):
        progreso_colores = len(self.colores_seleccionados) / 4
        barra_colores = '🎨' * len(self.colores_seleccionados) + '⬜' * (4 - len(self.colores_seleccionados))
        
        colores_texto = ", ".join([f"**{color.title()}**" for color in self.colores_seleccionados]) if self.colores_seleccionados else "*Ninguno*"
        tecnicas_texto = ", ".join([f"**{tec.title()}**" for tec in self.tecnicas_usadas]) if self.tecnicas_usadas else "*Ninguna*"
        
        estilo_msg = ""
        if self.nivel >= 5:
            label_estilo = self.estilo_seleccionado.title()
            if self.estilo_seleccionado == "impresionismo":
                label_estilo = "Impresionismo 🖌️"
            elif self.estilo_seleccionado == "cubismo":
                label_estilo = "Cubismo 🔲"
            elif self.estilo_seleccionado == "realismo":
                label_estilo = "Realismo 🖼️"
            else:
                label_estilo = "Ninguno 🎨"
            estilo_msg = f"✨ **Estilo de Obra:** {label_estilo}\n"
            
        embed = discord.Embed(
            title="🎨 Trabajo: Artista",
            description=(
                f"🖼️ **Obra objetivo:** {self.obra_objetivo['nombre']}\n"
                f"🎯 **Colores sugeridos:** {', '.join(self.obra_objetivo['colores'])}\n"
                f"🎨 **Colores usados:** {colores_texto}\n"
                f"🖌️ **Pinceladas:** {self.pinceladas}\n"
                f"✨ **Técnicas:** {tecnicas_texto}\n"
                f"📊 **Progreso:** {barra_colores} ({len(self.colores_seleccionados)}/4)\n"
                f"🌟 **Creatividad:** +{self.creatividad_bonus}{' (Caballete de Oro activo 🖼️)' if self.has_mejora_8 else ''}\n\n"
                f"{estilo_msg}"
                f"{accion}"
            ),
            color=discord.Color.purple()
        )
        
        controles_txt = (
            "🔴🔵🟡🟢 **Colores** | 🖌️ **Pincelar** (técnicas especiales)\n"
            "🎨 **Finalizar:** Completa tu obra"
        )
        if self.nivel >= 5:
            controles_txt += "\n✨ **Estilo de Obra:** Elígelo desde el menú inferior para obtener bonos."
        if self.nivel >= 8:
            controles_txt += "\n🎭 **Subasta de Arte:** Al finalizar, decide a quién vender tu obra."
            
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

def _finalizar_artista_db(user_id, recompensa_final, xp_ganada, comprador_msg):
    if recompensa_final > 0:
        pagar_recompensa_trabajo(user_id, recompensa_final, 'artista')
        
    resultado_nivel = add_experiencia_trabajo(user_id, 'artista', xp_ganada)
    has_prestige = usuario_tiene_mejora(user_id, 15)
    has_easel = usuario_tiene_mejora(user_id, 8)
    return resultado_nivel, has_easel, has_prestige

def _iniciar_artista_db(user_id, tipo_trabajo):
    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    energia_actual = get_energia(user_id)
    energia_base = 15
    energia_requerida = calcular_energia_requerida(energia_base, user_id, tipo_trabajo)
    has_prestige_mejora = usuario_tiene_mejora(user_id, 15)
    has_mejora_8 = usuario_tiene_mejora(user_id, 8)
    
    energia_consumida = False
    if energia_actual >= energia_requerida:
        energia_consumida = consumir_energia(user_id, energia_requerida)
        
    return nivel_info, energia_actual, energia_requerida, has_mejora_8, has_prestige_mejora, energia_consumida

async def iniciar_trabajo_artista(interaction: discord.Interaction):
    """Función principal para iniciar el trabajo de artista."""
    user_id = interaction.user.id
    tipo_trabajo = 'artista'
    
    nivel_info, energia_actual, energia_requerida, has_mejora_8, has_prestige_mejora, energia_consumida = await asyncio.to_thread(_iniciar_artista_db, user_id, tipo_trabajo)
    nivel = nivel_info["nivel"]
    
    if energia_actual < energia_requerida or not energia_consumida:
        embed = discord.Embed(
            title="⚡ Sin Energía",
            description=(
                f"❌ No tienes suficiente energía para trabajar (o alguien más la consumió justo antes).\n"
                f"🔋 **Energía actual:** {energia_actual}/100\n"
                f"⚡ **Energía requerida:** {energia_requerida}\n\n"
                f"💡 *La energía se recarga automáticamente*"
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not interaction.response.is_done():
        await interaction.response.defer()
    from .job_fx import tal_vez_cliente_especial
    await tal_vez_cliente_especial(interaction, user_id, tipo_trabajo)
    
    # Obras disponibles ordenadas por rango de nivel (Escalabilidad Vertical)
    obras_todas = [
        # Fácil (Nivel 0-2)
        {
            "nombre": "🌅 Amanecer en el Campo",
            "colores": ["amarillo", "rojo", "verde"],
            "dificultad": "Fácil",
            "nivel_min": 0,
            "recompensa_base": 130
        },
        {
            "nombre": "🌊 Océano Tormentoso",
            "colores": ["azul", "verde"],
            "dificultad": "Fácil",
            "nivel_min": 0,
            "recompensa_base": 130
        },
        
        # Medio (Nivel 3-5)
        {
            "nombre": "🍂 Bosque Otoñal",
            "colores": ["rojo", "amarillo", "verde"],
            "dificultad": "Medio",
            "nivel_min": 3,
            "recompensa_base": 200
        },
        {
            "nombre": "🌆 Ciudad al Atardecer",
            "colores": ["rojo", "amarillo", "azul"],
            "dificultad": "Medio",
            "nivel_min": 3,
            "recompensa_base": 200
        },
        
        # Difícil (Nivel 6-8)
        {
            "nombre": "🎭 Retrato Cubista Abstracto",
            "colores": ["rojo", "azul", "amarillo", "verde"],
            "dificultad": "Difícil",
            "nivel_min": 6,
            "recompensa_base": 320
        },
        {
            "nombre": "🌌 Noche de Galaxia Estrellada",
            "colores": ["azul", "amarillo", "verde"],
            "dificultad": "Difícil",
            "nivel_min": 6,
            "recompensa_base": 320
        },
        
        # Maestro (Nivel 9-10)
        {
            "nombre": "🏛️ Fresco de la Capilla Imperial",
            "colores": ["rojo", "azul", "amarillo", "verde"],
            "dificultad": "Maestro",
            "nivel_min": 9,
            "recompensa_base": 550
        }
    ]
    
    # Filtrar obras disponibles
    obras_disponibles = [o for o in obras_todas if nivel >= o["nivel_min"]]
    if not obras_disponibles:
        obras_disponibles = [o for o in obras_todas if o["nivel_min"] == 0]
        
    obra_objetivo = random.choice(obras_disponibles)
    recompensa_base = obra_objetivo["recompensa_base"]
    
    # Requisitos mínimos de pinceladas según nivel
    min_pinceladas = 3
    if nivel >= 6:
        min_pinceladas = 5
    elif nivel >= 3:
        min_pinceladas = 4
        
    # Mostrar recompensa con bonus de nivel
    recompensa_con_nivel = await asyncio.to_thread(calcular_recompensa, recompensa_base, user_id, tipo_trabajo)
    
    # Info de nivel
    bonificacion_actual = TIPOS_TRABAJO[tipo_trabajo]['bonificaciones'].get(nivel, "Sin bonificaciones")
    
    estilo_inicial = ""
    if nivel >= 5:
        estilo_inicial = f"✨ **Estilos de Obra desbloqueados!** Elige el tuyo al pintar.\n"
    subasta_inicial = ""
    if nivel >= 8:
        subasta_inicial = f"🎭 **Subastas de Arte activas!** Podrás subastar esta obra al finalizar.\n"
        
    embed = discord.Embed(
        title="🎨 Trabajo: Artista",
        description=(
            f"🖼️ **Obra a crear:** {obra_objetivo['nombre']}\n"
            f"🎯 **Colores sugeridos:** {', '.join(obra_objetivo['colores'])}\n"
            f"🏆 **Dificultad:** {obra_objetivo['dificultad']}\n"
            f"🖌️ **Pinceladas mínimas requeridas:** {min_pinceladas}\n"
            f"💰 **Recompensa:** {recompensa_con_nivel}+ monedas\n"
            f"⏱️ **Tiempo límite:** 2 minutos\n\n"
            f"{estilo_inicial}"
            f"{subasta_inicial}\n"
            f"📊 **Nivel actual:** {nivel} (XP ganada basada en creatividad y colores)\n"
            f"🌟 **Bonificación de nivel:** {bonificacion_actual}\n\n"
            f"🎨 **¡Deja volar tu creatividad!**"
        ),
        color=discord.Color.purple()
    )
    
    controles_txt = (
        "1️⃣ Selecciona colores para tu paleta\n"
        "2️⃣ Usa pinceladas para aplicar técnicas\n"
        "3️⃣ Busca combinaciones especiales (+bonus)\n"
        "4️⃣ ¡Finaliza cuando estés satisfecho!"
    )
    if nivel >= 5:
        controles_txt += "\n💡 *Tip:* Recuerda seleccionar un estilo artístico antes de finalizar."
        
    embed.add_field(
        name="🎮 Cómo jugar:",
        value=controles_txt,
        inline=False
    )
    
    view = ArtistaView(interaction.user, obra_objetivo, recompensa_base, nivel)
    view.has_mejora_8 = has_mejora_8
    view.has_mejora_15 = has_prestige_mejora
    
    if has_prestige_mejora:
        view.creatividad_bonus = 20
    elif has_mejora_8:
        view.creatividad_bonus = 10
    else:
        view.creatividad_bonus = 0
        
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed, view=view)
