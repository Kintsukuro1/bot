import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from src.db import get_balance, ensure_user
from .energia import get_energia

class PatchedInteractionResponse:
    def __init__(self, original_response, patched_interaction):
        self._original = original_response
        self._patched_interaction = patched_interaction

    def __getattr__(self, name):
        return getattr(self._original, name)

    async def send_message(self, *args, **kwargs):
        if self._original.is_done():
            kwargs.pop('delete_after', None)
            msg = await self._patched_interaction.followup.send(*args, **kwargs)
            # Track this message so edit_original_response can target it
            self._patched_interaction.__dict__['_followup_message'] = msg
            return msg
        return await self._original.send_message(*args, **kwargs)

    async def defer(self, *args, **kwargs):
        if self._original.is_done():
            return  # Already deferred, skip silently
        return await self._original.defer(*args, **kwargs)

class PatchedInteraction:
    def __init__(self, original_interaction):
        self.__dict__['_original'] = original_interaction
        self.__dict__['_response'] = PatchedInteractionResponse(original_interaction.response, self)
        self.__dict__['_followup_message'] = None

    def __getattr__(self, name):
        return getattr(self._original, name)

    def __setattr__(self, name, value):
        setattr(self._original, name, value)

    @property
    def response(self):
        return self._response

    async def edit_original_response(self, **kwargs):
        """If a followup message was created, edit that instead of the original."""
        if self.__dict__['_followup_message'] is not None:
            return await self.__dict__['_followup_message'].edit(**kwargs)
        return await self._original.edit_original_response(**kwargs)


def _get_energia_menu_data(user_id):
    from .energia import tiempo_hasta_recarga_completa
    from .niveles_trabajo import get_energia_trabajo, TIPOS_TRABAJO

    energia_actual = get_energia(user_id)
    tiempo_recarga = tiempo_hasta_recarga_completa(user_id)
    requerimientos = [
        (TIPOS_TRABAJO[tipo]['emoji'], TIPOS_TRABAJO[tipo]['nombre'], get_energia_trabajo(tipo, user_id))
        for tipo in TIPOS_TRABAJO.keys()
    ]
    return energia_actual, tiempo_recarga, requerimientos

def _get_trabajo_dashboard_data(user_id, user_name):
    from .niveles_trabajo import TIPOS_TRABAJO, get_energia_trabajo, get_recompensa_trabajo

    ensure_user(user_id, user_name)
    saldo_actual = get_balance(user_id)
    energia_actual = get_energia(user_id)
    trabajos = []

    for tipo, info in TIPOS_TRABAJO.items():
        energia_req = get_energia_trabajo(tipo, user_id)
        recompensa_ajustada = get_recompensa_trabajo(tipo, user_id)
        trabajos.append((tipo, info, energia_req, recompensa_ajustada))

    return saldo_actual, energia_actual, trabajos

class TrabajoView(discord.ui.View):
    """Vista interactiva para seleccionar trabajos disponibles."""
    
    def __init__(self, user):
        super().__init__(timeout=60)
        self.user = user

    async def _iniciar_trabajo_safe(self, interaction: discord.Interaction, iniciar_func):
        await interaction.response.defer()
        await iniciar_func(PatchedInteraction(interaction))

    @discord.ui.button(label="💻 Hacker", style=discord.ButtonStyle.primary, emoji="💻", row=0)
    async def trabajo_hacker(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .hacker import iniciar_trabajo_hacker
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_hacker)

    @discord.ui.button(label="👨‍🍳 Chef", style=discord.ButtonStyle.secondary, emoji="👨‍🍳", row=0)
    async def trabajo_chef(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .chef import iniciar_trabajo_chef
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_chef)

    @discord.ui.button(label="🎨 Artista", style=discord.ButtonStyle.secondary, emoji="🎨", row=0)
    async def trabajo_artista(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .artista import iniciar_trabajo_artista
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_artista)

    @discord.ui.button(label="🔧 Mecánico", style=discord.ButtonStyle.secondary, emoji="🔧", row=0)
    async def trabajo_mecanico(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .mecanico import iniciar_trabajo_mecanico
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_mecanico)

    @discord.ui.button(label="⛏️ Minero", style=discord.ButtonStyle.secondary, emoji="⛏️", row=0)
    async def trabajo_minero(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .minero import iniciar_trabajo_minero
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_minero)

    @discord.ui.button(label="🎣 Pescador", style=discord.ButtonStyle.secondary, emoji="🎣", row=1)
    async def trabajo_pescador(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .pescador import iniciar_trabajo_pescador
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_pescador)

    @discord.ui.button(label="✈️ Piloto", style=discord.ButtonStyle.secondary, emoji="✈️", row=1)
    async def trabajo_piloto(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .piloto import iniciar_trabajo_piloto
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_piloto)

    @discord.ui.button(label="🗡️ Cazarrecompensas", style=discord.ButtonStyle.secondary, emoji="🗡️", row=1)
    async def trabajo_cazarrecompensas(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .cazarrecompensas import iniciar_trabajo_cazarrecompensas
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_cazarrecompensas)

    @discord.ui.button(label="⚕️ Médico", style=discord.ButtonStyle.secondary, emoji="⚕️", row=1)
    async def trabajo_medico(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .medico import iniciar_trabajo_medico
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_medico)

    @discord.ui.button(label="🥷 Ladrón", style=discord.ButtonStyle.secondary, emoji="🥷", row=1)
    async def trabajo_ladron(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .ladron import iniciar_trabajo_ladron
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_ladron)

    @discord.ui.button(label="🔬 Científico", style=discord.ButtonStyle.secondary, emoji="🔬", row=2)
    async def trabajo_cientifico(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        from .cientifico import iniciar_trabajo_cientifico
        await self._iniciar_trabajo_safe(interaction, iniciar_trabajo_cientifico)

    @discord.ui.button(label="⚡ Ver Energía", style=discord.ButtonStyle.success, emoji="⚡", row=3)
    async def ver_energia(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
            
        user_id = interaction.user.id
        energia_actual, tiempo_recarga, requerimientos = await asyncio.to_thread(
            _get_energia_menu_data, user_id
        )
        
        # Crear barra de energía visual
        porcentaje = energia_actual / 100
        barra_energia = '🟩' * int(porcentaje * 10) + '⬜' * (10 - int(porcentaje * 10))
        
        if tiempo_recarga > 0:
            horas = tiempo_recarga // 60
            minutos = tiempo_recarga % 60
            tiempo_texto = f"{horas}h {minutos}m" if horas > 0 else f"{minutos}m"
            recarga_info = f"⏱️ **Recarga completa en:** {tiempo_texto}"
        else:
            recarga_info = "✅ **Energía al máximo!**"
        
        # Añadir información sobre requerimientos de energía para cada trabajo
        embed = discord.Embed(
            title="⚡ Estado de Energía",
            description=(
                f"🔋 **Energía actual:** {energia_actual}/100\n"
                f"📊 {barra_energia} {energia_actual}%\n\n"
                f"{recarga_info}\n"
                f"💡 *Recuperas 1 punto cada 3 minutos*"
            ),
            color=discord.Color.yellow() if energia_actual > 50 else discord.Color.orange() if energia_actual > 20 else discord.Color.red()
        )
        
        # Añadir información sobre requerimientos de energía para cada trabajo
        embed.add_field(
            name="🔋 Requerimientos de Energía",
            value="\n".join([
                f"{emoji} **{nombre}**: {energia_req} energía"
                for emoji, nombre, energia_req in requerimientos
            ]),
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="📊 Niveles", style=discord.ButtonStyle.success, emoji="📊", row=3)
    async def ver_niveles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        
        # Importar las funciones de niveles de trabajo
        from .niveles_trabajo import (
            get_todos_niveles_trabajo, 
            TIPOS_TRABAJO,
            get_resumen_nivel
        )
        
        # Obtener los niveles del usuario
        niveles = get_todos_niveles_trabajo(interaction.user.id)
        
        # Crear embed para mostrar los niveles
        embed = discord.Embed(
            title=f"📊 Niveles de Trabajo de {interaction.user.display_name}",
            description=(
                "Tu progreso en los distintos trabajos.\n"
                "Sube de nivel para obtener mejores recompensas y gastar menos energía."
            ),
            color=discord.Color.gold()
        )
        
        # Añadir campo para cada tipo de trabajo
        for tipo, info in niveles.items():
            if tipo in TIPOS_TRABAJO:
                # Usar la nueva función get_resumen_nivel para obtener datos completos
                resumen = get_resumen_nivel(interaction.user.id, tipo)
                trabajo_info = TIPOS_TRABAJO[tipo]
                nivel = resumen["nivel"]
                
                # Crear barra de progreso para la XP
                if nivel < 10:
                    info_progreso = f"{resumen['barra_progreso']} {resumen['xp_actual']}/{resumen['xp_necesaria']} XP"
                else:
                    info_progreso = "✅ Nivel máximo alcanzado"
                
                # Bonificaciones actuales en porcentaje
                bonus_recompensa = f"+{int((resumen['recompensa_multiplicador'] - 1) * 100)}%"
                reduccion_energia = f"-{int(resumen['energia_reduccion'] * 100)}%"
                
                # Añadir campo para este trabajo
                embed.add_field(
                    name=f"{trabajo_info['emoji']} {trabajo_info['nombre']} - Nivel {nivel}",
                    value=(
                        f"👔 **Trabajos completados:** {resumen['trabajos_totales']}\n"
                        f"💰 **Bonus recompensa:** {bonus_recompensa}\n"
                        f"⚡ **Reducción energía:** {reduccion_energia}\n"
                        f"⭐ **Bonificación actual:** {resumen['bonificacion_actual']}\n"
                        f"⏭️ **Siguiente nivel:** {resumen['bonificacion_siguiente'] if nivel < 10 else 'N/A'}\n"
                        f"📈 **Progreso:** {info_progreso}"
                    ),
                    inline=False
                )
        
        embed.set_footer(text="💡 Tip: Usa los botones para ver información detallada de cada trabajo")
        
        # Crear vista con botones para detalles
        view = BotonesDetallesView(interaction.user)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class BotonDetallesTrabajo(discord.ui.Button):
    def __init__(self, tipo_trabajo, nombre_trabajo):
        super().__init__(style=discord.ButtonStyle.secondary, label=f"Detalles {nombre_trabajo}")
        self.tipo_trabajo = tipo_trabajo
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from .niveles_trabajo import (
            get_resumen_nivel, 
            crear_embed_nivel,
            calcular_trabajos_para_nivel,
            TIPOS_TRABAJO
        )
        
        # Obtener información detallada del nivel
        resumen = get_resumen_nivel(interaction.user.id, self.tipo_trabajo)
        nivel_actual = resumen["nivel"]
        
        # Crear embed principal con la información del nivel
        embed = crear_embed_nivel(interaction.user.id, self.tipo_trabajo)
        
        # Añadir información sobre trabajos necesarios para niveles futuros
        if nivel_actual < 10:
            trabajos_info = calcular_trabajos_para_nivel(self.tipo_trabajo, nivel_actual)
            
            # Mostrar info para los próximos 3 niveles o hasta nivel máximo
            niveles_mostrar = min(3, 10 - nivel_actual)
            niveles_txt = []
            
            for i in range(1, niveles_mostrar + 1):
                nivel_objetivo = nivel_actual + i
                if nivel_objetivo in trabajos_info:
                    info = trabajos_info[nivel_objetivo]
                    niveles_txt.append(
                        f"**Nivel {nivel_objetivo}:** {info['trabajos_para_este_nivel']} trabajos "
                        f"({info['xp_necesaria']} XP)"
                    )
            
            if niveles_txt:
                embed.add_field(
                    name="🔮 Próximos Niveles",
                    value="\n".join(niveles_txt),
                    inline=False
                )
        
        # Añadir información sobre energía y recompensa
        info_trabajo = TIPOS_TRABAJO[self.tipo_trabajo]
        energia_base = info_trabajo.get('energia_base', 20)
        recompensa_base = info_trabajo.get('recompensa_base', 200)
        
        from .niveles_trabajo import calcular_energia_requerida, calcular_recompensa
        
        energia_actual = calcular_energia_requerida(energia_base, interaction.user.id, self.tipo_trabajo)
        recompensa_actual = calcular_recompensa(recompensa_base, interaction.user.id, self.tipo_trabajo)
        
        embed.add_field(
            name="💼 Información de Trabajo",
            value=(
                f"⚡ **Energía requerida:** {energia_actual} (base: {energia_base})\n"
                f"💰 **Recompensa promedio:** {recompensa_actual} (base: {recompensa_base})\n"
                f"📈 **Tier Económico:** {info_trabajo.get('tier_economico', 'N/A')}\n"
                f"🎯 **Riesgo de fallo:** {info_trabajo.get('riesgo', 'N/A')}\n"
                f"✨ **XP por trabajo:** {info_trabajo.get('xp_por_trabajo', 10)}"
            ),
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

class BotonTablaProgresion(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="📋 Ver Tabla de Progresión")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from .niveles_trabajo import crear_embed_progresion_global
        embed = crear_embed_progresion_global()
        await interaction.followup.send(embed=embed, ephemeral=True)

class BotonesDetallesView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=60)
        self.user = user
        
        # Añadir un botón para cada tipo de trabajo
        from .niveles_trabajo import TIPOS_TRABAJO
        for tipo_trabajo, info_trabajo in TIPOS_TRABAJO.items():
            self.add_item(BotonDetallesTrabajo(tipo_trabajo, info_trabajo['nombre']))
            
        # Añadir botón para ver la tabla de progresión global
        self.add_item(BotonTablaProgresion())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este menú.", ephemeral=True)
            return False
        return True

class Trabajo(commands.Cog):
    """Sistema principal de trabajos interactivos."""
    
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="trabajo", description="Explora los trabajos disponibles y gana dinero")
    async def trabajo(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        user_name = interaction.user.name
        saldo_actual, energia_actual, trabajos = await asyncio.to_thread(
            _get_trabajo_dashboard_data, user_id, user_name
        )
        
        # Crear embed principal
        embed = discord.Embed(
            title="💼 Centro de Trabajos",
            description=(
                "Selecciona un trabajo para empezar a ganar dinero.\n"
                "Cada trabajo requiere energía y habilidades específicas.\n\n"
                "🎯 **Trabajos disponibles:**"
            ),
            color=discord.Color.blue()
        )
        
        # Usar la información de TIPOS_TRABAJO
        for _tipo, info, energia_req, recompensa_ajustada in trabajos:
            # Calcular rango de recompensa
            recompensa_min = int(recompensa_ajustada * 0.8)
            recompensa_max = int(recompensa_ajustada * 1.2)
            rango_recompensa = f"{recompensa_min}-{recompensa_max}"
            
            # Obtener métricas
            tier_economico = info.get('tier_economico', 'N/A')
            riesgo = info.get('riesgo', 'N/A')
            
            embed.add_field(
                name=f"{info['emoji']} **{info['nombre']}**",
                value=(
                    f"{info['descripcion']}\n"
                    f"⚡ Energía: {energia_req}\n"
                    f"💰 Recompensa: {rango_recompensa}\n"
                    f"📈 Tier: {tier_economico}\n"
                    f"🎯 Riesgo: {riesgo}"
                ),
                inline=True
            )
        
        # Información del usuario
        embed.add_field(
            name="👤 Tu Estado",
            value=(
                f"💰 **Saldo:** {saldo_actual} monedas\n"
                f"⚡ **Energía:** {energia_actual}/100\n"
                f"📊 **Estado:** {'Listo para trabajar' if energia_actual >= 15 else 'Necesitas descansar'}"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 Tip: La energía se recarga automáticamente con el tiempo")
        
        # Crear vista con botones
        view = TrabajoView(interaction.user)
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Trabajo(bot))
    print("Trabajo system cog loaded successfully.")
