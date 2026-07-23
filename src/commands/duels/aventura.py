"""
Sistema de Aventura y Modo Campaña (10 Capítulos Narrativos).
Incluye navegación por Nodos (Combate con Mobs, Eventos Narrativos de Elección, Campamento y Bosses de Capítulo).
Permite rescatar NPCs para el Poblado Comunitario (/poblado) y desbloquear Mazmorras Exclusivas.
"""

from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from typing import Optional
from src.db import (
    db_cursor, ensure_user, get_user_combat_level, add_poblado_resources, record_poblado_contribution,
    get_user_consumables, use_consumable, get_consumable_catalog
)
from src.commands.duels.raid.combatant import RaidCombatant
from src.utils.combat.mobs import generate_mob, Mob
from src.utils.combat.adventure_nodes import (
    CHAPTERS_CONFIG, NARRATIVE_EVENTS, AdventureNode, generate_chapter_nodes, get_chapter_thematic_material
)
from src.utils.combat_progression import format_hp_bar, get_combat_rank_emoji
from src.utils.subclass_config import get_subclass_skills
from src.utils.combat_config import SKILLS_CONFIG
from src.commands.duels.raid.lobby_view import get_combatant_available_skills

class AventuraView(discord.ui.View):
    """Vista interactiva para navegar por los Nodos del Capítulo de Aventura."""

    def __init__(self, user_id: int, chapter_id: int, player_combatant: RaidCombatant, guild_id: int = None):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.chapter_id = chapter_id
        self.cfg = CHAPTERS_CONFIG[chapter_id]
        self.p = player_combatant
        self.guild_id = guild_id
        
        self.nodes = generate_chapter_nodes(chapter_id)
        self.current_node_idx = 0  # 0-indexed (0 a 9)
        self.total_bronze_gained = 0
        self.materials_gained = {"madera": 0, "piedra": 0, "cristal": 0, "solar": 0}
        self.combat_logs: list[str] = []
        self.current_event_data: Optional[dict] = None

    @property
    def current_node(self) -> AdventureNode:
        return self.nodes[self.current_node_idx]

    # ── BOTONES DE ACCIÓN PRINCIPALES ──

    @discord.ui.button(label="⚔️ Avanzar al Nodo", style=discord.ButtonStyle.primary, row=0)
    async def btn_advance(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Esta aventura no es tuya.", ephemeral=True)
            return

        await interaction.response.defer()
        node = self.current_node

        if node.node_type in ["combat", "combat_elite"]:
            await self._handle_combat_node(interaction, is_elite=(node.node_type == "combat_elite"))
            return
        elif node.node_type == "event":
            await self._handle_event_node()
        elif node.node_type == "camp":
            await self._handle_camp_node()
        elif node.node_type == "boss":
            await self._handle_boss_node(interaction)
            return

        if self.p.hp <= 0:
            await self._finish_adventure(interaction, victory=False)
            return

        if node.completed and self.current_node_idx >= len(self.nodes) - 1:
            await self._finish_adventure(interaction, victory=True)
            return

        embed = self._build_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="🏃 Retirarse con Botín", style=discord.ButtonStyle.secondary, row=0)
    async def btn_retreat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return

        await interaction.response.defer()
        await self._finish_adventure(interaction, victory=False, retreated=True)

    # ── MANEJADORES DE NODOS ──

    async def _handle_combat_node(self, interaction: discord.Interaction, is_elite: bool = False):
        mob = generate_mob(self.chapter_id, round_num=self.current_node_idx + 1, is_elite=is_elite)
        combat_view = AventuraNodeCombatView(self, mob, is_boss=False)
        embed = combat_view._build_embed()
        await interaction.edit_original_response(embed=embed, view=combat_view)

    async def _handle_event_node(self):
        event = random.choice(NARRATIVE_EVENTS)
        self.current_event_data = event
        
        opt = random.choice(event["options"])
        if opt["effect_type"] == "resource":
            self.p.resource.add(opt["val"])
        elif opt["effect_type"] == "buff_atk":
            self.p.atk = int(self.p.atk * (1.0 + opt["val"]))
            self.p.hp = max(1, int(self.p.hp * 0.90))
        elif opt["effect_type"] in ["materials", "materials_wood"]:
            key, emoji, mat_name = get_chapter_thematic_material(self.chapter_id)
            amount = random.randint(1, 2)
            self.materials_gained[key] += amount
            self.combat_logs.append(f"📜 **{event['title']}:** Extraes recursos valiosos (+{amount} {emoji} {mat_name}).")
            self.current_node.completed = True
            self.current_node_idx += 1
            return
        elif opt["effect_type"] == "heal":
            heal = int(self.p.max_hp * opt["val"])
            self.p.hp = min(self.p.max_hp, self.p.hp + heal)

        self.combat_logs.append(f"📜 **{event['title']}:** {opt['msg']}")
        self.current_node.completed = True
        self.current_node_idx += 1

    async def _handle_camp_node(self):
        heal = int(self.p.max_hp * 0.35)
        self.p.hp = min(self.p.max_hp, self.p.hp + heal)
        self.p.resource.add(50)
        self.combat_logs.append(f"🏕️ **Campamento:** Descansas junto a la fogata (+{heal} HP, +50 Recurso de Clase).")
        self.current_node.completed = True
        self.current_node_idx += 1

    async def _handle_boss_node(self, interaction: discord.Interaction):
        boss_info = self.cfg["boss"]
        boss_mob = Mob(
            name=f"{boss_info['name']}",
            emoji=boss_info["emoji"],
            archetype="guerrero",
            level=self.chapter_id * 10,
            hp=boss_info["hp"],
            atk=boss_info["atk"],
            def_stat=boss_info["def_stat"],
            is_elite=True,
            affix="bastion"
        )
        combat_view = AventuraNodeCombatView(self, boss_mob, is_boss=True)
        embed = combat_view._build_embed()
        await interaction.edit_original_response(embed=embed, view=combat_view)

    # ── CONSTRUCCIÓN DEL EMBED ──

    def _build_embed(self) -> discord.Embed:
        node = self.current_node if self.current_node_idx < len(self.nodes) else self.nodes[-1]
        
        # Barra de recurso de clase
        res_str = self.p.resource.format_display()
        res_line = f"\n{res_str}" if res_str else ""

        # Representación de progreso de nodos (ej: 🟢──🟢──🟡──⚪──⚪)
        progress_icons = []
        for i, n in enumerate(self.nodes):
            if i < self.current_node_idx:
                progress_icons.append("🟢")
            elif i == self.current_node_idx:
                progress_icons.append("🟡")
            else:
                progress_icons.append("⚪")
        progress_bar_str = "──".join(progress_icons)

        mat_parts = []
        if self.materials_gained["madera"] > 0:
            mat_parts.append(f"🌲 {self.materials_gained['madera']}")
        if self.materials_gained["piedra"] > 0:
            mat_parts.append(f"🌋 {self.materials_gained['piedra']}")
        if self.materials_gained["cristal"] > 0:
            mat_parts.append(f"🔮 {self.materials_gained['cristal']}")
        if self.materials_gained["solar"] > 0:
            mat_parts.append(f"☀️ {self.materials_gained['solar']}")
        mat_str = " · ".join(mat_parts) if mat_parts else "Ninguno aún"

        desc = (
            f"**{self.cfg['title']}**\n"
            f"*{self.cfg['desc']}*\n\n"
            f"📍 **Progreso de la Expedición:**\n`[{progress_bar_str}]` (Nodo {self.current_node_idx + 1}/10)\n\n"
            f"❤️ **HP:** `{self.p.hp}/{self.p.max_hp}` | ⚔️ **ATK:** `{self.p.atk}` | 🛡️ **DEF:** `{self.p.def_stat}`{res_line}\n\n"
            f"💰 **Botín Acumulado:** `{self.total_bronze_gained:,}` Bronce 🥉\n"
            f"📦 **Materiales:** {mat_str}\n\n"
            f"📜 **Últimos Acontectimientos:**\n" +
            ("\n".join(self.combat_logs[-4:]) if self.combat_logs else "_Presiona **Avanzar al Nodo** para continuar la historia._")
        )

        embed = discord.Embed(
            title=f"{node.emoji} {node.title}",
            description=desc,
            color=self.cfg["color_code"]
        )
        return embed

    # ── FINALIZACIÓN DE LA ADVENTURA ──

    async def _finish_adventure(self, interaction: discord.Interaction, victory: bool = False, retreated: bool = False):
        for child in self.children:
            child.disabled = True

        npc_info = self.cfg["npc_rescue"]
        dungeon_info = self.cfg["dungeon_unlock"]

        if victory:
            title = f"🏆 ¡Capítulo Completado: {self.cfg['title']}!"
            desc = (
                f"¡Has superado los 10 Nodos del Capítulo {self.chapter_id} y derrotado al Jefe!\n\n"
                f"🎉 **¡RESCATE DE NPC EXITOSO!**\n"
                f"Has rescatado a **{npc_info['emoji']} {npc_info['name']}**.\n"
                f"💬 *\"{npc_info['dialogue']}\"*\n\n"
                f"🔓 **¡NUEVO CONTENIDO DESBLOQUEADO!**\n"
                f"• Edificio habilitado en Poblado: **{npc_info['building']}**\n"
                f"• Mazmorra Narrativa unlocked: **{dungeon_info['name']}** ({dungeon_info['boss']})\n"
            )
            color = discord.Color.gold()
        elif retreated:
            title = f"🏃 Retirada Estratégica"
            desc = f"Te retiraste en el **Nodo {self.current_node_idx + 1}** conservando tu botín acumulado."
            color = discord.Color.light_grey()
        else:
            title = f"💀 Derrota en el Nodo {self.current_node_idx + 1}"
            desc = f"Has caído en combate. Se rescata el 50% del botín acumulado.\n\n" + "\n".join(self.combat_logs[-3:])
            self.total_bronze_gained = int(self.total_bronze_gained * 0.5)
            color = discord.Color.red()

        # Otorgamiento de XP
        xp_gained = (self.current_node_idx * (15 + self.chapter_id * 5)) + (150 + self.chapter_id * 25 if victory else 0)
        xp_res = await self._award_rewards(self.total_bronze_gained, self.materials_gained, victory, xp_gained)

        embed = discord.Embed(title=title, description=desc, color=color)

        xp_notice = f"⭐ **+{xp_gained:,} XP de Combate**"
        if xp_res and xp_res.get('leveled_up'):
            xp_notice += f" 🏆 **¡SUBIDA DE NIVEL!** (Nivel **{xp_res['previous_level']}** ➔ **{xp_res['level']}** — *{xp_res['rank']}*)"

        mat_summary = []
        if self.materials_gained["madera"] > 0:
            mat_summary.append(f"🌲 {self.materials_gained['madera']} Madera")
        if self.materials_gained["piedra"] > 0:
            mat_summary.append(f"🌋 {self.materials_gained['piedra']} Piedra")
        if self.materials_gained["cristal"] > 0:
            mat_summary.append(f"🔮 {self.materials_gained['cristal']} Cristales")
        if self.materials_gained["solar"] > 0:
            mat_summary.append(f"☀️ {self.materials_gained['solar']} Lingotes Solares")
        mat_summary_str = " · ".join(mat_summary) if mat_summary else "Ninguno"

        embed.add_field(
            name="💰 Botín y Experiencia Rescatados",
            value=f"**{self.total_bronze_gained:,}** Monedas de Bronce 🥉 · {xp_notice}\n"
                  f"📦 **Materiales de Expedición:** {mat_summary_str}",
            inline=False
        )

        await interaction.edit_original_response(embed=embed, view=self)

    async def _award_rewards(self, bronze: int, mats: dict, victory: bool, xp_gained: int) -> Optional[dict]:
        from src.db import update_combat_stats_after_duel, complete_user_chapter
        def _save():
            xp_result = None
            if xp_gained > 0:
                xp_result = update_combat_stats_after_duel(self.user_id, xp_gained, is_win=victory, money_change=0)

            if victory:
                complete_user_chapter(self.user_id, self.chapter_id)

            with db_cursor() as c:
                if bronze > 0:
                    c.execute("""
                        INSERT INTO CombatWallet (UserID, Bronze)
                        VALUES (%s, %s)
                        ON CONFLICT (UserID) DO UPDATE SET Bronze = CombatWallet.Bronze + EXCLUDED.Bronze
                    """, (self.user_id, bronze))
            if self.guild_id and (mats["madera"] > 0 or mats["piedra"] > 0 or victory):
                pts = 10 if victory else 3
                add_poblado_resources(
                    self.guild_id,
                    madera=mats["madera"],
                    piedra=mats["piedra"],
                    cristal=mats["cristal"],
                    solar=mats["solar"],
                    puntos=pts
                )
                record_poblado_contribution(self.guild_id, self.user_id, puntos=pts, materiales=sum(mats.values()))
            return xp_result

        return await asyncio.to_thread(_save)


FIRST_TIME_CLASSES = [
    {
        "name": "Guerrero",
        "emoji": "⚔️",
        "resource": "💥 Furia (0-100)",
        "role": "Tanque / Daño Físico Directo",
        "stats_focus": "Alta Vida (HP) y Defensa (DEF)",
        "desc": (
            "El **Guerrero** es un maestro del combate cuerpo a cuerpo y la resistencia en el frente.\n\n"
            "• **Mecánica de Recurso:** Genera **Furia** al recibir o asestar ataques.\n"
            "• **Efecto de Clase:** Al 100% entra en **Desenfreno**, potenciando sus golpes un **+30% de daño extra**."
        ),
        "color": discord.Color.red()
    },
    {
        "name": "Paladín",
        "emoji": "🛡️",
        "resource": "✝️ Fe (0-5 Stacks)",
        "role": "Defensivo / Mitigación y Escudos",
        "stats_focus": "Máxima Defensa y Absorción de Daño",
        "desc": (
            "El **Paladín** es un guardián sagrado bendecido por la luz divina.\n\n"
            "• **Mecánica de Recurso:** Acumula stacks de **Fe** al defender o bloquear ataques.\n"
            "• **Efecto de Clase:** Consume Fe para crear escudos divinos y potenciar sanaciones un **+25%**."
        ),
        "color": discord.Color.gold()
    },
    {
        "name": "Pícaro",
        "emoji": "🗡️",
        "resource": "👤 Sombras (0-3 Stacks)",
        "role": "Asesino / Golpes Críticos y Evasión",
        "stats_focus": "Alto Ataque, Crítico y Probabilidad de Esquivar",
        "desc": (
            "El **Pícaro** se mueve entre las sombras asestando estocadas letales.\n\n"
            "• **Mecánica de Recurso:** Genera **Sombras** al esquivar golpes enemigos.\n"
            "• **Efecto de Clase:** Con 3 Stacks de Sombras desata un **Golpe Letal (+35% Daño)**."
        ),
        "color": discord.Color.dark_purple()
    },
    {
        "name": "Mago",
        "emoji": "🔮",
        "resource": "🔮 Maná Arcano (0-100)",
        "role": "Daño Mágico de Área / Ráfaga",
        "stats_focus": "Máximo Daño Mágico (MAG)",
        "desc": (
            "El **Mago** domina la energía elemental para devastar grupos de enemigos.\n\n"
            "• **Mecánica de Recurso:** Canaliza **Maná Arcano** con cada hechizo.\n"
            "• **Efecto de Clase:** Al 100% desata **Sobrecarga Arcana**, reduciendo enfriamientos y potenciando hechizos."
        ),
        "color": discord.Color.blue()
    },
    {
        "name": "Clérigo",
        "emoji": "✨",
        "resource": "✨ Luz Sagrada (0-5 Stacks)",
        "role": "Sanador / Curaciones y Disipaciones",
        "stats_focus": "Poder Mágico y Regeneración de Salud",
        "desc": (
            "El **Clérigo** mantiene vivo a su equipo restaurando salud en medio del caos.\n\n"
            "• **Mecánica de Recurso:** Acumula **Luz Sagrada** al realizar curaciones o limpiar estados.\n"
            "• **Efecto de Clase:** Consume Luz para aplicar curación continua (HoT) a sus aliados."
        ),
        "color": discord.Color.light_grey()
    },
    {
        "name": "Arquero",
        "emoji": "🏹",
        "resource": "🏹 Concentración (0-100)",
        "role": "Daño Físico Rápido / Evasión",
        "stats_focus": "Alto Daño Físico y Penetración de Armadura",
        "desc": (
            "El **Arquero** es un tirador certero especializado en objetivos prioritarios.\n\n"
            "• **Mecánica de Recurso:** Acumula **Concentración** al mantenerse a distancia sin recibir daño.\n"
            "• **Efecto of Clase:** Consume Concentración para ignorar armadura enemiga e infligir **+30% daño extra**."
        ),
        "color": discord.Color.green()
    },
    {
        "name": "Monje",
        "emoji": "🐉",
        "resource": "☯️ Chi (0-5 Stacks)",
        "role": "Combos Físicos / Evasión Táctica",
        "stats_focus": "Daño Progresivo por Combos y Evasión",
        "desc": (
            "El **Monje** encadena golpes marciales rítmicos para devastar a sus oponentes.\n\n"
            "• **Mecánica de Recurso:** Genera **Chi** con cada ataque físico asestado.\n"
            "• **Efecto de Clase:** Consume Chi para ejecutar combos letales (1 Chi, 3 Chi o Ráfaga de 5 Chi)."
        ),
        "color": discord.Color.orange()
    },
    {
        "name": "Alquimista",
        "emoji": "🧪",
        "resource": "🧪 Reactivos (0-10 Stacks)",
        "role": "Venenos / Potenciadores y Caos",
        "stats_focus": "Daño Mágico Continuo y Debuffs de Área",
        "desc": (
            "El **Alquimista** destila sustancias químicas y venenos mortales en el campo de batalla.\n\n"
            "• **Mecánica de Recurso:** Destila **Reactivos** con cada turno de combate.\n"
            "• **Efecto de Clase:** Consume Reactivos para lanzar bombas ácidas, venenos y brebajes fortificantes."
        ),
        "color": discord.Color.teal()
    },
    {
        "name": "Invocador",
        "emoji": "👹",
        "resource": "👹 Esencia (0-100)",
        "role": "Criaturas Auxiliares / Esqueletos y Lobos",
        "stats_focus": "Daño Continuo por Criaturas Invocadas",
        "desc": (
            "El **Invocador** convoca criaturas espectrales, demonios y bestias para luchar a su lado.\n\n"
            "• **Mecánica de Recurso:** Acumula **Esencia** al luchar e invocar aliados.\n"
            "• **Efecto de Clase:** Consume Esencia para invocar esqueletos, lobos guardianes o demonios."
        ),
        "color": discord.Color.dark_red()
    },
    {
        "name": "Ingeniero",
        "emoji": "⚙️",
        "resource": "⚙️ Energía (0-100)",
        "role": "Torretas Automáticas / Minas Tácticas",
        "stats_focus": "Control del Campo de Batalla y Dispositivos",
        "desc": (
            "El **Ingeniero** despliega inventos tecnológicos, torretas autoguiadas y minas explosivas.\n\n"
            "• **Mecánica de Recurso:** Canaliza **Energía** para alimentar sus dispositivos.\n"
            "• **Efecto de Clase:** Sobrecarga energía para disparos automáticos dobles y escudos de fuerza."
        ),
        "color": discord.Color.dark_gold()
    },
    {
        "name": "Chamán",
        "emoji": "⭐",
        "resource": "⭐ Tótems (0-3 Stacks)",
        "role": "Tótems Elementales / Auras de Grupo",
        "stats_focus": "Buffs de Grupo, Curaciones y Rayos",
        "desc": (
            "El **Chamán** invoca la fuerza de los elementos mediante tótems ancestrales.\n\n"
            "• **Mecánica de Recurso:** Acumula **Tótems** sintonizándose con los elementos.\n"
            "• **Efecto de Clase:** Planta hasta 3 tótems activos (Mareas, Bastión Pétreo e Ira) para el grupo."
        ),
        "color": discord.Color.dark_blue()
    },
    {
        "name": "Bardo",
        "emoji": "🎭",
        "resource": "🎭 Inspiración (0-100)",
        "role": "Soporte Armónico / Buffs y Auras",
        "stats_focus": "Potenciación de Daño y Curación de Grupo",
        "desc": (
            "El **Bardo** inspira a su escuadrón con canciones de guerra y serenadas sanadoras.\n\n"
            "• **Mecánica de Recurso:** Genera **Inspiración** al mantener auras musicales activas.\n"
            "• **Efecto de Clase:** Desata Crescendos Armónicos que otorgan +35% de potencia a todo el grupo."
        ),
        "color": discord.Color.magenta()
    },
    {
        "name": "Brujo",
        "emoji": "🌑",
        "resource": "🌑 Maná Oscuro (0-100)",
        "role": "Magia de Sombras / Sacrificio de HP",
        "stats_focus": "Máximo Daño Mágico por Drenaje de Vida",
        "desc": (
            "El **Brujo** realiza pactos prohibidos convirtiendo su propia vida en hechicería destructiva.\n\n"
            "• **Mecánica de Recurso:** Acumula **Maná Oscuro** al drenar HP propio.\n"
            "• **Efecto de Clase:** Lanza cataclismos de sombras masivos (+35% MAG) y prisiones de almas."
        ),
        "color": discord.Color.purple()
    },
    {
        "name": "Cronomante",
        "emoji": "⏳",
        "resource": "⏳ Flujo Temporal (0-5 Stacks)",
        "role": "Control del Tiempo / Turnos Extra",
        "stats_focus": "Reducción de Cooldowns y Parálisis",
        "desc": (
            "El **Cronomante** altera la línea del tiempo acelerando aliados y pausando enemigos.\n\n"
            "• **Mecánica de Recurso:** Acumula **Flujo Temporal** con cada turno que transcurre.\n"
            "• **Efecto de Clase:** Reduce cooldowns del grupo, otorga turnos extra y reinicia habilidades."
        ),
        "color": discord.Color.dark_teal()
    },
    {
        "name": "Vampiro",
        "emoji": "🩸",
        "resource": "🩸 Sangre (0-100)",
        "role": "Hemorragia Acumulativa / Robo de Vida",
        "stats_focus": "Daño Progresivo por Sangrado y Autocuración",
        "desc": (
            "El **Vampiro** prospera en los combates prolongados acumulando sangrados fatales.\n\n"
            "• **Mecánica de Recurso:** Genera **Sangre** e inflige stacks de **Hemorragia Acumulativa**.\n"
            "• **Efecto de Clase:** Transforma el sangrado enemigo en escudos e inflige un 40% de Robo de Vida."
        ),
        "color": discord.Color.dark_red()
    }
]


class AventuraSkillSelectView(discord.ui.View):
    """Menú efímero de selección de habilidad especial para el combate de Aventura."""

    def __init__(self, combat_view: "AventuraNodeCombatView", options: list[discord.SelectOption]):
        super().__init__(timeout=60)
        self.combat_view = combat_view

        select = discord.ui.Select(
            placeholder="✨ Seleccionar Habilidad Especial...",
            min_values=1,
            max_values=1,
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True

        selected_skill_id = interaction.data["values"][0]
        skill = SKILLS_CONFIG.get(selected_skill_id)
        if not skill:
            await interaction.response.edit_message(content="❌ Habilidad desconocida.", view=self)
            return

        await interaction.response.edit_message(content=f"✅ Habilidad registrada: **{skill['name']}**", view=self)
        await self.combat_view._execute_player_skill(interaction, skill)


class AventuraConsumableSelectView(discord.ui.View):
    """Menú efímero de selección de consumible para el combate de Aventura."""

    def __init__(self, combat_view: "AventuraNodeCombatView", options: list[discord.SelectOption]):
        super().__init__(timeout=60)
        self.combat_view = combat_view

        select = discord.ui.Select(
            placeholder="🧪 Seleccionar Consumible...",
            min_values=1,
            max_values=1,
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True

        selected_key = interaction.data["values"][0]
        user_id = self.combat_view.adv.user_id

        success = await asyncio.to_thread(use_consumable, user_id, selected_key)
        if not success:
            await interaction.response.edit_message(content="❌ No tienes suficiente cantidad de este consumible.", view=self)
            return

        catalog = await asyncio.to_thread(get_consumable_catalog)
        c_info = next((item for item in catalog if item['consumable_key'] == selected_key), None)
        c_name = c_info['name'] if c_info else selected_key

        await interaction.response.edit_message(content=f"✅ Consumible registrado: **{c_name}**", view=self)
        await self.combat_view._execute_player_consumable(interaction, selected_key, c_name)


class AventuraNodeCombatView(discord.ui.View):
    """Vista de combate interactiva turno por turno para Nodos de Aventura (Estilo Raid)."""

    def __init__(self, main_adventure_view: "AventuraView", mob: Mob, is_boss: bool = False):
        super().__init__(timeout=180)
        self.adv = main_adventure_view
        self.mob = mob
        self.is_boss = is_boss
        self.turn = 1
        self.game_over = False
        self.logs: list[str] = [f"⚔️ ¡Un {mob.emoji} **{mob.name}** ha aparecido! Prepárate para combatir."]

    def _build_embed(self) -> discord.Embed:
        p = self.adv.p
        m = self.mob
        rank_emoji = get_combat_rank_emoji(p.level)

        if m.hp <= 0:
            title = f"🏆 ¡Raid Completada — {m.name} Derrotado!"
            header_desc = f"¡Los héroes han triunfado sobre {m.emoji} **{m.name}**!"
            color = discord.Color.gold()
        elif p.hp <= 0:
            title = f"💀 Derrota en la Aventura — {m.name}"
            header_desc = f"Has caído en combate en el **Nodo {self.adv.current_node_idx + 1}**."
            color = discord.Color.red()
        else:
            title = f"⚔️ COMBATE EN CURSO: {m.emoji} {m.name}" if not self.is_boss else f"{m.emoji} Raid — {m.name}"
            header_desc = (
                f"📍 **Nodo {self.adv.current_node_idx + 1}/10** · *Capítulo {self.adv.chapter_id}*\n"
                f"⚔️ **Ronda {self.turn}** · Combate en tiempo real"
            )
            if self.is_boss:
                header_desc += f"\n👑 **¡ENFRENTAMIENTO CONTRA EL JEFE DEL CAPÍTULO!**"
            color = discord.Color.dark_red() if self.is_boss else discord.Color.orange()

        embed = discord.Embed(
            title=title,
            description=header_desc,
            color=color
        )

        # Campo del Enemigo (Estilo Raid Boss)
        m_status = f" · *{m.affix.title()}*" if m.affix else ""
        if m.shield > 0:
            m_status += f" 🛡️({m.shield})"

        m_hp_bar = format_hp_bar(max(0, m.hp), m.max_hp, size=20)

        embed.add_field(
            name=f"{m.emoji} {m.name}{m_status}",
            value=f"{m_hp_bar}",
            inline=False
        )

        # Campo del Jugador (Estilo Raid Combatant - Image 2 style)
        p_status = " 🟢" if p.hp > 0 else " 💀"
        p_hp_bar = format_hp_bar(max(0, p.hp), p.max_hp, size=15)
        res_display = p.resource.format_display()
        res_line = f"\n{res_display}" if res_display else ""

        class_tag = f" [{p.combat_subclass}]" if p.combat_subclass else (f" [{p.combat_class}]" if p.combat_class else "")

        embed.add_field(
            name=f"{p_status} {rank_emoji} **{p.user.display_name}**{class_tag} (Nv. {p.level})",
            value=(
                f"{p_hp_bar}{res_line}\n"
                f"⚔️ {p.atk} ATK · 🛡️ {p.def_stat} DEF"
            ),
            inline=False
        )

        # Campo de Últimas acciones
        logs_str = "\n".join(self.logs[-6:]) if self.logs else "_Preparando el primer asalto..._"
        embed.add_field(
            name="📜 Últimas acciones",
            value=logs_str,
            inline=False
        )

        embed.set_footer(text=f"Duración: {self.turn} rondas · Capítulo {self.adv.chapter_id} (Nodo {self.adv.current_node_idx + 1}/10)")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.adv.user_id:
            await interaction.response.send_message("❌ Este combate pertenece a otro jugador.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚔️ Atacar", style=discord.ButtonStyle.danger, row=0)
    async def btn_attack(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over:
            await interaction.response.send_message("❌ El combate ya terminó.", ephemeral=True)
            return

        await interaction.response.defer()
        p = self.adv.p
        m = self.mob

        # 1. Turno del Jugador: Ataque básico
        raw_dmg = max(1, p.atk - m.def_stat)
        is_crit = random.random() < p.subclass_extras.get("crit_chance_bonus", 0.05)
        if is_crit:
            raw_dmg = int(raw_dmg * 1.5)

        # Evento de Recurso
        res_log = p.resource.on_attack_dealt(raw_dmg, is_crit)
        if res_log:
            self.logs.append(f"   {res_log}")

        dmg_dealt, event_log = m.take_damage(raw_dmg)
        crit_txt = " **¡CRÍTICO!**" if is_crit else ""
        self.logs.append(f"⚔️ **{p.user.display_name}** ataca a {m.emoji} {m.name}{crit_txt} infligiendo **{dmg_dealt}** daño.")
        self.logs.append(f"➡️ **Daño al enemigo:** **{dmg_dealt}** daño.")
        if event_log:
            self.logs.append(f"   {event_log}")

        await self._resolve_turn(interaction)

    @discord.ui.button(label="🛡️ Defender", style=discord.ButtonStyle.primary, row=0)
    async def btn_defend(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over:
            await interaction.response.send_message("❌ El combate ya terminó.", ephemeral=True)
            return

        await interaction.response.defer()
        p = self.adv.p
        heal = max(1, int(p.max_hp * 0.12))
        p.hp = min(p.max_hp, p.hp + heal)
        p.resource.add(15)

        self.logs.append(f"🛡️ **{p.user.display_name}** se defiende y recupera **{heal}** HP.")
        await self._resolve_turn(interaction, is_defending=True)

    @discord.ui.button(label="✨ Habilidad Especial", style=discord.ButtonStyle.secondary, row=1)
    async def btn_skill_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over:
            await interaction.response.send_message("❌ El combate ya terminó.", ephemeral=True)
            return

        p = self.adv.p
        available_skills = get_combatant_available_skills(p)
        if not available_skills:
            await interaction.response.send_message("❌ No tienes habilidades especiales disponibles.", ephemeral=True)
            return

        options = [
            discord.SelectOption(
                label=f"{skill['name']} (Nvl. {skill['min_level']})",
                value=skill_id,
                emoji=skill['emoji'],
                description=skill['desc'][:100]
            ) for skill_id, skill in available_skills
        ]

        view = AventuraSkillSelectView(combat_view=self, options=options)
        await interaction.response.send_message("Elige tu habilidad especial:", view=view, ephemeral=True)

    @discord.ui.button(label="🧪 Usar Consumible", style=discord.ButtonStyle.success, row=1)
    async def btn_consumable_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over:
            await interaction.response.send_message("❌ El combate ya terminó.", ephemeral=True)
            return

        user_id = self.adv.user_id
        inventory = await asyncio.to_thread(get_user_consumables, user_id)
        if not inventory:
            await interaction.response.send_message("❌ No tienes consumibles en tu inventario.", ephemeral=True)
            return

        catalog = await asyncio.to_thread(get_consumable_catalog)
        options = []
        for key, qty in inventory.items():
            if qty > 0:
                c_info = next((item for item in catalog if item['consumable_key'] == key), None)
                c_name = c_info['name'] if c_info else key
                c_desc = c_info['description'] if (c_info and c_info.get('description')) else f"Disponible: {qty} en inventario"
                c_emoji = c_info.get('emoji', '🧪') if c_info else "🧪"
                options.append(
                    discord.SelectOption(
                        label=f"{c_name} (Tienes: {qty})",
                        value=key,
                        emoji=c_emoji,
                        description=c_desc[:100]
                    )
                )

        if not options:
            await interaction.response.send_message("❌ No tienes consumibles disponibles.", ephemeral=True)
            return

        view = AventuraConsumableSelectView(combat_view=self, options=options)
        await interaction.response.send_message("Elige tu consumible:", view=view, ephemeral=True)

    @discord.ui.button(label="🏃 Huir", style=discord.ButtonStyle.grey, row=2)
    async def btn_flee(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.adv._finish_adventure(interaction, victory=False, retreated=True)

    async def _execute_player_skill(self, interaction: discord.Interaction, skill: dict):
        p = self.adv.p
        m = self.mob

        mult, boost_log = p.resource.try_consume_and_boost()
        if boost_log:
            self.logs.append(f"   {boost_log}")

        base_mult = skill.get("damage_mult", 1.8)
        total_mult = base_mult * mult
        dmg_stat = skill.get("damage_stat", "mag")
        stat_val = getattr(p, dmg_stat, p.atk)

        raw_dmg = int(max(1, stat_val * total_mult) - (m.def_stat * 0.25))
        res_log = p.resource.on_spell_cast()
        if res_log:
            self.logs.append(f"   {res_log}")

        dmg_dealt, event_log = m.take_damage(raw_dmg, is_magic=(dmg_stat == "mag"))
        skill_emoji = skill.get('emoji', '✨')
        self.logs.append(f"{skill_emoji} **{skill['name']}**: **{p.user.display_name}** causa **{dmg_dealt}** daño e inflige habilidades sobre {m.name}!")
        self.logs.append(f"➡️ **Daño al enemigo:** **{dmg_dealt}** daño.")
        if event_log:
            self.logs.append(f"   {event_log}")

        await self._resolve_turn(interaction)

    async def _execute_player_consumable(self, interaction: discord.Interaction, consumable_key: str, consumable_name: str):
        p = self.adv.p

        if "salud" in consumable_key or "hp" in consumable_key or "pocion" in consumable_key:
            heal = int(p.max_hp * 0.35)
            p.hp = min(p.max_hp, p.hp + heal)
            self.logs.append(f"🧪 **{p.user.display_name}** usa **{consumable_name}** y recupera **{heal}** HP.")
        elif "fuerza" in consumable_key or "atk" in consumable_key:
            p.atk = int(p.atk * 1.25)
            self.logs.append(f"🧪 **{p.user.display_name}** usa **{consumable_name}** e incrementa su ATK un **+25%**.")
        else:
            heal = int(p.max_hp * 0.25)
            p.hp = min(p.max_hp, p.hp + heal)
            self.logs.append(f"🧪 **{p.user.display_name}** usa **{consumable_name}** restaurando energía de combate.")

        await self._resolve_turn(interaction, is_defending=True)

    async def _resolve_turn(self, interaction: discord.Interaction, is_defending: bool = False):
        p = self.adv.p
        m = self.mob

        # 2. Verificación si el Mob murió
        if m.hp <= 0:
            for child in self.children:
                child.disabled = True

            round_bronze = int(35 * self.adv.chapter_id * (2.5 if self.is_boss else (1.5 if m.is_elite else 1.0)))
            self.adv.total_bronze_gained += round_bronze

            # Otorgamiento dinámico de materiales temáticos por capítulo (máximo ~5-9 por campaña)
            key, emoji, mat_name = get_chapter_thematic_material(self.adv.chapter_id)
            mat_dropped = 0
            if self.is_boss:
                mat_dropped = random.randint(2, 3)
            elif m.is_elite:
                mat_dropped = 1
            elif random.random() < 0.50:
                mat_dropped = 1

            if mat_dropped > 0:
                self.adv.materials_gained[key] += mat_dropped
                mat_text = f", +{mat_dropped} {emoji} {mat_name}"
            else:
                mat_text = ""

            self.game_over = True
            for child in self.children:
                child.disabled = True

            self.logs.append(f"🎉 **¡{m.name} ha sido derrotado!**")
            self.adv.combat_logs.append(f"⚔️ **Nodo {self.adv.current_node_idx + 1}:** Derrotado {m.emoji} **{m.name}** (+{round_bronze:,} Bronce 🥉{mat_text}).")
            self.adv.current_node.completed = True
            self.adv.current_node_idx += 1

            if self.adv.current_node_idx >= len(self.adv.nodes):
                await self.adv._finish_adventure(interaction, victory=True)
            else:
                embed = self.adv._build_embed()
                await interaction.edit_original_response(embed=embed, view=self.adv)
            return

        # 3. Turno del Mob (si sigue vivo)
        m_log = m.perform_action(p)
        if is_defending:
            m_log += " *(Daño reducido por postura defensiva)*"
        self.logs.append(f"   {m_log}")

        res_dmg_log = p.resource.on_damage_taken(m.atk)
        if res_dmg_log:
            self.logs.append(f"   {res_dmg_log}")

        # 4. Verificación si el Jugador murió
        if p.hp <= 0:
            await self.adv._finish_adventure(interaction, victory=False)
            return

        self.turn += 1
        embed = self._build_embed()
        await interaction.edit_original_response(embed=embed, view=self)


class ClassSelectionCarouselView(discord.ui.View):
    """Vista de carrusel interactivo para la elección de clase inicial de un jugador."""

    def __init__(self, user_id: int, capitulo: int, guild_id: Optional[int] = None):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.capitulo = capitulo
        self.guild_id = guild_id
        self.current_idx = 0

    def _build_embed(self) -> discord.Embed:
        c_data = FIRST_TIME_CLASSES[self.current_idx]
        total_cls = len(FIRST_TIME_CLASSES)
        embed = discord.Embed(
            title=f"⚔️ Bienvenida a la Campaña — Elige tu Clase ({self.current_idx + 1}/{total_cls})",
            description=(
                f"¡Bienvenido, aventurero! Antes de emprender la historia, debes seleccionar tu **Clase de Combate Inicial**.\n\n"
                f"### {c_data['emoji']} **{c_data['name']}**\n"
                f"🎭 **Rol:** `{c_data['role']}`\n"
                f"⚡ **Recurso Único:** `{c_data['resource']}`\n"
                f"📊 **Enfoque:** `{c_data['stats_focus']}`\n\n"
                f"{c_data['desc']}\n\n"
                f"_Navega con ◀️ y ▶️ para ver las demás clases o presiona **Elegir esta Clase** para comenzar._"
            ),
            color=c_data["color"]
        )
        embed.set_footer(text=f"Clase {self.current_idx + 1} de {total_cls} · {c_data['name']}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Esta selección pertenece a otro jugador.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_idx = (self.current_idx - 1) % len(FIRST_TIME_CLASSES)
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="Elegir esta Clase", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True

        chosen = FIRST_TIME_CLASSES[self.current_idx]

        # Guardar clase en CombatStats
        def _save_class():
            with db_cursor() as c:
                c.execute("""
                    INSERT INTO CombatStats (UserID, CombatClass)
                    VALUES (%s, %s)
                    ON CONFLICT (UserID) DO UPDATE SET CombatClass = EXCLUDED.CombatClass
                """, (self.user_id, chosen["name"]))

        await asyncio.to_thread(_save_class)

        # Preparar combatiente con la nueva clase
        def _setup():
            with db_cursor() as c:
                c.execute("SELECT CombatLevel, CombatClass, CombatSubclass FROM CombatStats WHERE UserID = %s", (self.user_id,))
                row = c.fetchone()
                lvl = row[0] if row else 1
                c_class = row[1] or chosen["name"]
                c_subclass = row[2] if row else None

                c.execute("SELECT Slot, ItemName, Rarity, ItemLevel, PrimaryStat, PrimaryValue, Secondaries, Passive, MiniAffixKey, MiniAffixValue, WeaponSubtype, GemKey FROM UserEquipment WHERE UserID = %s", (self.user_id,))
                eq_rows = c.fetchall()
                equipment = {}
                for eq in eq_rows:
                    equipment[eq[0]] = {
                        "name": eq[1], "rarity": eq[2], "level": eq[3],
                        "primary_stat": eq[4], "primary_value": eq[5],
                        "secondaries": eq[6] or [], "passive": eq[7],
                        "mini_affix_key": eq[8], "mini_affix_value": eq[9],
                        "weapon_subtype": eq[10], "gem_key": eq[11]
                    }
                return lvl, c_class, c_subclass, equipment

        lvl, c_class, c_subclass, equipment = await asyncio.to_thread(_setup)

        combatant = RaidCombatant(interaction.user, lvl, equipment, c_class, c_subclass)
        adventure_view = AventuraView(self.user_id, self.capitulo, combatant, self.guild_id)
        embed = adventure_view._build_embed()
        embed.set_author(name=f"¡Has elegido la clase {chosen['name']} {chosen['emoji']}! Comenzando Aventura...")

        await interaction.response.edit_message(embed=embed, view=adventure_view)

    @discord.ui.button(label="Siguiente", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_idx = (self.current_idx + 1) % len(FIRST_TIME_CLASSES)
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


class Aventura(commands.Cog):
    """Cog para el Modo Aventura y Campaña Narrativa de 10 Capítulos."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="aventura", description="Inicia o continúa tu expedición en la Campaña Narrativa (10 Capítulos).")
    @app_commands.describe(capitulo="Selecciona el Capítulo de la historia a explorar")
    @app_commands.choices(capitulo=[
        app_commands.Choice(name="Capítulo 1: El Incendio del Valle (Nv. 1+)", value=1),
        app_commands.Choice(name="Capítulo 2: Las Criptas del Juramento (Nv. 11+)", value=2),
        app_commands.Choice(name="Capítulo 3: Furia de las Tierras Ígneas (Nv. 21+)", value=3),
        app_commands.Choice(name="Capítulo 4: El Glaciar de los Lamentos (Nv. 31+)", value=4),
        app_commands.Choice(name="Capítulo 5: Fortaleza de la Tempestad (Nv. 41+)", value=5),
        app_commands.Choice(name="Capítulo 6: Ciudadela de las Sombras (Nv. 51+)", value=6),
        app_commands.Choice(name="Capítulo 7: Las Arenas del Olvido (Nv. 61+)", value=7),
        app_commands.Choice(name="Capítulo 8: Profundidades Abisales (Nv. 71+)", value=8),
        app_commands.Choice(name="Capítulo 9: La Falla Etérea (Nv. 81+)", value=9),
        app_commands.Choice(name="Capítulo 10: El Juicio del Dios Dragón (Nv. 91+)", value=10),
    ])
    async def aventura_cmd(self, interaction: discord.Interaction, capitulo: int = 1):
        await interaction.response.defer()
        user_id = interaction.user.id

        cfg = CHAPTERS_CONFIG.get(capitulo)
        if not cfg:
            await interaction.followup.send("❌ Capítulo no válido.", ephemeral=True)
            return

        from src.db import get_user_max_unlocked_chapter
        max_unlocked = await asyncio.to_thread(get_user_max_unlocked_chapter, user_id)
        if capitulo > max_unlocked:
            await interaction.followup.send(
                f"🔒 **Capítulo Bloqueado:** Debes completar el **Capítulo {max_unlocked - 1 if max_unlocked > 1 else 1}** para acceder a esta parte de la historia.",
                ephemeral=True
            )
            return

        def _setup_player():
            with db_cursor() as c:
                c.execute("SELECT CombatLevel, CombatClass, CombatSubclass FROM CombatStats WHERE UserID = %s", (user_id,))
                row = c.fetchone()
                lvl = row[0] if row else 1
                c_class = row[1] if row else None
                c_subclass = row[2] if row else None

                c.execute("SELECT Slot, ItemName, Rarity, ItemLevel, PrimaryStat, PrimaryValue, Secondaries, Passive, MiniAffixKey, MiniAffixValue, WeaponSubtype, GemKey FROM UserEquipment WHERE UserID = %s", (user_id,))
                eq_rows = c.fetchall()
                equipment = {}
                for eq in eq_rows:
                    equipment[eq[0]] = {
                        "name": eq[1], "rarity": eq[2], "level": eq[3],
                        "primary_stat": eq[4], "primary_value": eq[5],
                        "secondaries": eq[6] or [], "passive": eq[7],
                        "mini_affix_key": eq[8], "mini_affix_value": eq[9],
                        "weapon_subtype": eq[10], "gem_key": eq[11]
                    }
                return lvl, c_class, c_subclass, equipment

        lvl, c_class, c_subclass, equipment = await asyncio.to_thread(_setup_player)

        # Si el jugador no ha seleccionado clase (primera vez), lanzar el carrusel de selección
        if not c_class:
            carousel = ClassSelectionCarouselView(user_id, capitulo, interaction.guild_id)
            embed = carousel._build_embed()
            await interaction.followup.send(embed=embed, view=carousel)
            return

        if lvl < cfg["level_req"]:
            await interaction.followup.send(f"❌ Requieres Nivel de Combate **{cfg['level_req']}** para acceder al {cfg['title']}.", ephemeral=True)
            return

        combatant = RaidCombatant(interaction.user, lvl, equipment, c_class, c_subclass)
        view = AventuraView(user_id, capitulo, combatant, interaction.guild_id)
        embed = view._build_embed()
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Aventura(bot))
    print("Aventura cog loaded successfully with 10 Chapters campaign engine and first-time onboarding.")
