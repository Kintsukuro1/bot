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
from src.db import db_cursor, ensure_user, get_user_combat_level, add_poblado_resources, record_poblado_contribution
from src.commands.duels.raid.combatant import RaidCombatant
from src.utils.combat.mobs import generate_mob, Mob
from src.utils.combat.adventure_nodes import (
    CHAPTERS_CONFIG, NARRATIVE_EVENTS, AdventureNode, generate_chapter_nodes
)

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
            await self._handle_combat_node(is_elite=(node.node_type == "combat_elite"))
        elif node.node_type == "event":
            await self._handle_event_node()
        elif node.node_type == "camp":
            await self._handle_camp_node()
        elif node.node_type == "boss":
            await self._handle_boss_node()

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

    async def _handle_combat_node(self, is_elite: bool = False):
        mob = generate_mob(self.chapter_id, round_num=self.current_node_idx + 1, is_elite=is_elite)
        
        # Ejecutar acción de mascota
        pet_log = self.p.execute_pet_raid_ai(0.5, False)
        if pet_log:
            self.combat_logs.append(f"   {pet_log}")

        # Daño infligido por el jugador
        p_dmg = max(1, self.p.atk - mob.def_stat)
        is_crit = random.random() < self.p.subclass_extras.get("crit_chance_bonus", 0.05)
        if is_crit:
            p_dmg = int(p_dmg * 1.5)

        # Evento de Recurso de Clase al atacar
        res_log = self.p.resource.on_attack_dealt(p_dmg, is_crit)
        if res_log:
            self.combat_logs.append(f"   {res_log}")

        mob_dmg_taken, mob_event = mob.take_damage(p_dmg)
        if mob_event:
            self.combat_logs.append(f"   {mob_event}")

        # Daño infligido por el mob si sobrevive
        if mob.hp > 0:
            mob_log = mob.perform_action(self.p)
            self.combat_logs.append(f"   {mob_log}")
            # Recibir daño otorga Furia / Fe
            res_dmg_log = self.p.resource.on_damage_taken(mob.atk)
            if res_dmg_log:
                self.combat_logs.append(f"   {res_dmg_log}")

        # Recompensas de la ronda
        round_bronze = int(35 * self.chapter_id * (1.5 if is_elite else 1.0))
        self.total_bronze_gained += round_bronze
        self.materials_gained["madera"] += random.randint(1, 3)
        self.materials_gained["piedra"] += random.randint(1, 2)

        self.combat_logs.append(f"**Nodo {self.current_node_idx + 1}:** Derrotado {mob.emoji} **{mob.name}** (+{round_bronze} Bronce 🥉)")
        self.current_node.completed = True
        self.current_node_idx += 1

    async def _handle_event_node(self):
        event = random.choice(NARRATIVE_EVENTS)
        self.current_event_data = event
        
        # Seleccionar una opción por defecto / aleatoria en la resolución rápida
        opt = random.choice(event["options"])
        if opt["effect_type"] == "resource":
            self.p.resource.add(opt["val"])
        elif opt["effect_type"] == "buff_atk":
            self.p.atk = int(self.p.atk * (1.0 + opt["val"]))
            self.p.hp = max(1, int(self.p.hp * 0.90))
        elif opt["effect_type"] == "materials":
            self.materials_gained["cristal"] += opt["val"]
        elif opt["effect_type"] == "materials_wood":
            self.materials_gained["madera"] += opt["val"]
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

    async def _handle_boss_node(self):
        boss_info = self.cfg["boss"]
        boss_mob = Mob(
            name=f"👑 {boss_info['name']}",
            emoji=boss_info["emoji"],
            archetype="guerrero",
            level=self.chapter_id * 10,
            hp=boss_info["hp"],
            atk=boss_info["atk"],
            def_stat=boss_info["def_stat"],
            is_elite=True,
            affix="bastion"
        )

        p_dmg = max(1, self.p.atk - boss_mob.def_stat)
        boss_mob.take_damage(p_dmg)

        if boss_mob.hp > 0:
            b_log = boss_mob.perform_action(self.p)
            self.combat_logs.append(f"   {b_log}")

        reward = boss_info["reward_bronze"]
        self.total_bronze_gained += reward
        self.materials_gained["solar"] += 2
        
        self.combat_logs.append(f"👑 **¡JEFE DERROTADO!** Has derrotado a {boss_info['emoji']} **{boss_info['name']}** (+{reward:,} Bronce 🥉).")
        self.current_node.completed = True

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

        desc = (
            f"**{self.cfg['title']}**\n"
            f"*{self.cfg['desc']}*\n\n"
            f"📍 **Progreso de la Expedición:**\n`[{progress_bar_str}]` (Nodo {self.current_node_idx + 1}/10)\n\n"
            f"❤️ **HP:** `{self.p.hp}/{self.p.max_hp}` | ⚔️ **ATK:** `{self.p.atk}` | 🛡️ **DEF:** `{self.p.def_stat}`{res_line}\n\n"
            f"💰 **Botín Acumulado:** `{self.total_bronze_gained:,}` Bronce 🥉\n"
            f"📦 **Materiales:** 🌲 {self.materials_gained['madera']} · 🌋 {self.materials_gained['piedra']} · 🔮 {self.materials_gained['cristal']}\n\n"
            f"📜 **Últimos Acontecimientos:**\n" +
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

        embed.add_field(
            name="💰 Botín y Experiencia Rescatados",
            value=f"**{self.total_bronze_gained:,}** Monedas de Bronce 🥉 · {xp_notice}\n"
                  f"🌲 {self.materials_gained['madera']} Madera · 🌋 {self.materials_gained['piedra']} Piedra · 🔮 {self.materials_gained['cristal']} Cristales",
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
        embed = discord.Embed(
            title=f"⚔️ Bienvenida a la Campaña — Elige tu Clase ({self.current_idx + 1}/5)",
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
        embed.set_footer(text=f"Clase {self.current_idx + 1} de {len(FIRST_TIME_CLASSES)} · {c_data['name']}")
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
