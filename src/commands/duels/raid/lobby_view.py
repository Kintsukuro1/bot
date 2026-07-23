import discord
import asyncio
from src.utils.raid_config import RAID_LOBBY_TIMEOUT, RAID_MAX_PLAYERS, RAID_MIN_PLAYERS, BOSS_ABILITIES, calc_boss_stats
from src.utils.combat_progression import get_combat_rank_emoji
def get_raid_pkg():
    import sys
    return sys.modules["src.commands.duels.raid"]

from src.utils.combat_config import SKILLS_CONFIG
from .combatant import RaidCombatant
from .loot_views import count_mythic_raids_today

class RaidLobbyView(discord.ui.View):
    """Vista de sala de espera para que los jugadores se unan antes de iniciar la raid."""

    def __init__(self, creator: discord.Member, boss_config: dict, cog):
        super().__init__(timeout=RAID_LOBBY_TIMEOUT)
        self.creator = creator
        self.boss_config = boss_config
        self.cog = cog
        self.players: list[discord.Member] = [creator]  # El creador se une automáticamente
        self.player_stats: dict[int, dict] = {}  # user_id -> combat_stats
        self.player_equipments: dict[int, dict] = {}  # user_id -> equipment
        self.difficulty = "normal"
        self.started = False
        self.cancelled = False

    def _build_lobby_embed(self):
        from src.utils.combat_progression import calc_power_level

        boss = self.boss_config
        
        player_powers = {}
        for p in self.players:
            level = self.player_stats.get(p.id, {}).get("level", 1)
            equip = self.player_equipments.get(p.id, {})
            subclass = self.player_stats.get(p.id, {}).get("combat_subclass")
            power = calc_power_level(level, equip, subclass)
            player_powers[p.id] = power

        player_list = "\n".join(
            f"{get_combat_rank_emoji(self.player_stats.get(p.id, {}).get('level', 1))} "
            f"**{p.display_name}** — Nv. {self.player_stats.get(p.id, {}).get('level', 1)} "
            f"(Poder: **{player_powers[p.id]:.1f}**)"
            for p in self.players
        )

        total_power = sum(player_powers[p.id] for p in self.players)
        if boss.get("is_miniboss", False):
            scaled_stats = {
                "hp": boss["hp"],
                "max_hp": boss["hp"],
                "atk": boss["atk"],
                "def_stat": boss["def_stat"],
            }
            stats_label = "**Stats del Miniboss** (Fijos):"
        else:
            scaled_stats = calc_boss_stats(boss, total_power, self.difficulty, num_players=len(self.players))
            stats_label = f"**Stats del Boss** (escalado a {len(self.players)} jugadores · Poder {total_power:.1f}):"


        embed = discord.Embed(
            title=f"{boss['emoji']} Raid — {boss['name']} ({self.difficulty.capitalize()})",
            description=(
                f"*{boss['lore']}*\n\n"
                f"**Elemento:** {boss['element']}\n"
                f"**Dificultad:** {self.difficulty.upper()}\n"
                f"**Habilidad Especial:** {BOSS_ABILITIES[boss['ability']]['emoji']} "
                f"{BOSS_ABILITIES[boss['ability']]['name']}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"**Jugadores ({len(self.players)}/{RAID_MAX_PLAYERS}):**\n{player_list}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{stats_label}\n"
                f"❤️ HP: {scaled_stats['hp']:,} · ⚔️ ATK: {scaled_stats['atk']} · 🛡️ DEF: {scaled_stats['def_stat']}"
            ),
            color=boss["color"]
        )
        embed.set_footer(
            text=f"Mínimo {RAID_MIN_PLAYERS} jugadores para iniciar · "
                 f"Solo {self.creator.display_name} puede iniciar · "
                 f"Lobby expira en {RAID_LOBBY_TIMEOUT}s"
        )
        return embed

    @discord.ui.button(label="✅ Unirse a la Raid", style=discord.ButtonStyle.success, row=0)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        if user.id in [p.id for p in self.players]:
            await interaction.response.send_message("❌ Ya estás en la raid.", ephemeral=True)
            return

        if len(self.players) >= RAID_MAX_PLAYERS:
            await interaction.response.send_message("❌ La raid está llena.", ephemeral=True)
            return

        # Verificar que no esté en otra raid
        if user.id in self.cog.active_raids:
            await interaction.response.send_message("❌ Ya tienes una raid en curso.", ephemeral=True)
            return

        # Si la dificultad es mítica, verificar intentos diarios del que se une
        if self.difficulty == "mitica":
            attempts = await asyncio.to_thread(count_mythic_raids_today, user.id)
            if attempts >= 2:
                await interaction.response.send_message("❌ Ya usaste tus 2 intentos de raid Mítica de hoy. Vuelve mañana.", ephemeral=True)
                return

        # Cargar stats y equipo
        await asyncio.to_thread(get_raid_pkg().ensure_user, user.id, user.name)
        stats = await asyncio.to_thread(get_raid_pkg().get_combat_stats, user.id)
        equip = await asyncio.to_thread(get_raid_pkg().get_user_equipment, user.id)
        
        self.player_stats[user.id] = stats
        self.player_equipments[user.id] = equip

        self.players.append(user)
        self.cog.active_raids.add(user.id)

        embed = self._build_lobby_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶️ Iniciar Raid", style=discord.ButtonStyle.primary, row=0)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.creator.id:
            await interaction.response.send_message(
                "❌ Solo el creador de la raid puede iniciarla.", ephemeral=True
            )
            return

        if len(self.players) < RAID_MIN_PLAYERS:
            await interaction.response.send_message(
                f"❌ Se necesitan al menos **{RAID_MIN_PLAYERS}** jugadores para iniciar.",
                ephemeral=True
            )
            return

        # Si es dificultad Mítica, verificar de nuevo a todos los participantes antes de iniciar
        if self.difficulty == "mitica":
            locked_players = []
            for p in self.players:
                attempts = await asyncio.to_thread(count_mythic_raids_today, p.id)
                if attempts >= 2:
                    locked_players.append(p.display_name)
            if locked_players:
                await interaction.response.send_message(
                    f"❌ No se puede iniciar la raid Mítica: los siguientes jugadores ya usaron sus 2 intentos diarios: {', '.join(locked_players)}.",
                    ephemeral=True
                )
                return

        self.started = True
        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title=f"{self.boss_config['emoji']} ¡Raid Iniciando!",
            description="Preparando la arena de combate...",
            color=self.boss_config["color"]
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, row=0)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.creator.id:
            await interaction.response.send_message(
                "❌ Solo el creador puede cancelar la raid.", ephemeral=True
            )
            return

        self.cancelled = True
        for item in self.children:
            item.disabled = True

        # Liberar jugadores
        for p in self.players:
            self.cog.active_raids.discard(p.id)

        embed = discord.Embed(
            title="❌ Raid Cancelada",
            description=f"{self.creator.display_name} ha cancelado la raid.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.select(
        placeholder="Seleccionar Dificultad",
        options=[
            discord.SelectOption(label="Normal", value="normal", description="Escalado estándar", default=True),
            discord.SelectOption(label="Difícil", value="dificil", description="Enemigo +45% HP y +40% ATK/DEF"),
            discord.SelectOption(label="Mítica", value="mitica", description="¡Desafío extremo! Límite de 2 intentos diarios"),
        ],
        row=1
    )
    async def select_difficulty(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.creator.id:
            await interaction.response.send_message("❌ Solo el creador de la raid puede cambiar la dificultad.", ephemeral=True)
            return

        selected_diff = select.values[0]

        # Validar Mítica
        if selected_diff == "mitica":
            # Verificar intentos del creador
            creator_attempts = await asyncio.to_thread(count_mythic_raids_today, self.creator.id)
            if creator_attempts >= 2:
                await interaction.response.send_message("❌ No puedes seleccionar dificultad Mítica: has alcanzado el límite de 2 intentos diarios.", ephemeral=True)
                return
            # Verificar otros jugadores ya en el lobby
            locked_players = []
            for p in self.players:
                if p.id != self.creator.id:
                    attempts = await asyncio.to_thread(count_mythic_raids_today, p.id)
                    if attempts >= 2:
                        locked_players.append(p.display_name)
            if locked_players:
                await interaction.response.send_message(f"❌ No puedes seleccionar dificultad Mítica: los siguientes jugadores ya usaron sus 2 intentos diarios: {', '.join(locked_players)}.", ephemeral=True)
                return

        # Actualizar opciones por defecto
        for opt in select.options:
            opt.default = (opt.value == selected_diff)

        self.difficulty = selected_diff
        embed = self._build_lobby_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if not self.started and not self.cancelled:
            self.cancelled = True
            for p in self.players:
                self.cog.active_raids.discard(p.id)


def get_combatant_available_skills(combatant: RaidCombatant) -> list[tuple[str, dict]]:
    available = []
    for skill_id, skill in SKILLS_CONFIG.items():
        if skill.get("class") is None:
            # ceguera ("Tierra a los ojos") está disponible para sin clase o nivel < 5
            if combatant.combat_class is None or combatant.level < 5:
                available.append((skill_id, skill))
        else:
            # Habilidad específica de clase
            if combatant.combat_class == skill["class"]:
                req_subclass = skill.get("subclass")
                if req_subclass:
                    # Habilidad de subclase
                    if combatant.combat_subclass == req_subclass and combatant.level >= skill["min_level"]:
                        available.append((skill_id, skill))
                else:
                    # Habilidad de clase base
                    if combatant.level >= skill["min_level"]:
                        available.append((skill_id, skill))

    # Fallback de seguridad: si no tiene habilidades unlocked (ej: nivel 1-4 con clase elegida), incluir ceguera
    if not available:
        ceguera_skill = SKILLS_CONFIG.get("ceguera")
        if ceguera_skill:
            available.append(("ceguera", ceguera_skill))

    return available
