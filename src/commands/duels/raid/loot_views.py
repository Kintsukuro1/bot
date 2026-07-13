import discord
import asyncio
import random
import logging
import psycopg2.extras
def resolve_db_func(name):
    import sys
    import unittest.mock
    pkg = sys.modules.get("src.commands.duels.raid")
    if pkg and hasattr(pkg, name):
        val = getattr(pkg, name)
        if isinstance(val, unittest.mock.Mock):
            return val
    import src.db as db
    return getattr(db, name)


from src.utils.combat_progression import (
    LOOT_TIMEOUT_SECONDS, SLOT_EMOJIS, ALL_STATS, format_item_stats_display,
    format_stat_type, calc_sell_price, format_currency, RARITY_COLORS
)
from src.utils.raid_config import MINION_ARCHETYPES
from .combatant import RaidCombatant

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# VISTA: DROP DE LOOT DE RAID
# ══════════════════════════════════════════════

class RaidLootView(discord.ui.View):
    """Vista de comparación para decidir si equipar o vender un drop de raid."""

    def __init__(self, user: discord.Member, loot: dict, current_piece: dict | None):
        super().__init__(timeout=LOOT_TIMEOUT_SECONDS)
        self.user = user
        self.loot = loot
        self.current_piece = current_piece
        self.message = None
        self.resolved = False

    def build_embed(self):
        loot = self.loot
        embed = discord.Embed(
            title=f"{loot['rarity_color']} {loot['name']}",
            description=(
                f"**{loot['rarity']}** · Nivel {loot['item_level']} · "
                f"{SLOT_EMOJIS.get(loot['slot'], '🔹')} {loot['slot']}\n"
                f"*Drop de Raid*"
            ),
            color=loot['rarity_hex']
        )

        new_stats_text = format_item_stats_display(loot)
        embed.add_field(name="🆕 Nuevo", value=new_stats_text, inline=True)

        if self.current_piece:
            cp = self.current_piece
            curr_stats_text = format_item_stats_display(cp)
            embed.add_field(name="📦 Actual", value=curr_stats_text, inline=True)

            diff_lines = []
            for stat in ALL_STATS:
                loot_val = loot['stats_summary'].get(stat, 0)
                cp_summary = {cp['primary_stat']: cp['primary_value']}
                for sec in cp.get('secondaries', []):
                    cp_summary[sec['stat']] = cp_summary.get(sec['stat'], 0) + sec['value']
                cp_val = cp_summary.get(stat, 0)

                if loot_val > 0 or cp_val > 0:
                    diff = loot_val - cp_val
                    if diff != 0:
                        sign = "+" if diff > 0 else ""
                        color = "🟢" if diff > 0 else "🔴"
                        diff_lines.append(f"{color} {sign}{diff} {format_stat_type(stat)}")

            if diff_lines:
                embed.add_field(name="📊 Diferencia", value="\n".join(diff_lines), inline=True)
            else:
                embed.add_field(name="📊 Diferencia", value="Stats idénticas", inline=True)
        else:
            embed.add_field(name="📦 Actual", value="— Vacío —", inline=True)

        embed.add_field(
            name="💰 Precio de venta",
            value=f"{loot['sell_price']:,} monedas",
            inline=False
        )
        embed.set_footer(text=f"Si no respondes en {LOOT_TIMEOUT_SECONDS}s, se vende automáticamente.")
        return embed

    @discord.ui.button(label="🔧 Equipar", style=discord.ButtonStyle.success)
    async def equip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Este drop no es para ti.", ephemeral=True)
            return
        if self.resolved:
            return

        loot = self.loot

        # Validar restricciones de clase
        c_stats = await asyncio.to_thread(resolve_db_func("get_combat_stats"), self.user.id)
        player_level = c_stats['level']
        combat_class = c_stats.get('combat_class')

        if player_level >= 5 and combat_class:
            slot = loot['slot']
            material = loot.get('material')

            is_armor = slot in ("Cabeza", "Hombros", "Pecho", "Pantalones", "Botas")
            if is_armor and material:
                class_materials = {
                    "Guerrero": ["Hierro"], "Paladín": ["Hierro"],
                    "Pícaro": ["Cuero"], "Mago": ["Tela"], "Clérigo": ["Tela"]
                }
                allowed = class_materials.get(combat_class, [])
                if material not in allowed:
                    await interaction.response.send_message(
                        f"❌ Como **{combat_class}**, solo puedes equipar armaduras de **{', '.join(allowed)}** "
                        f"(este objeto es de {material}).",
                        ephemeral=True
                    )
                    return

            if slot in ("Arma", "Escudo", "Bastón mágico"):
                class_weapons = {
                    "Guerrero": ["Arma", "Escudo"], "Paladín": ["Arma", "Escudo"],
                    "Pícaro": ["Arma"], "Mago": ["Bastón mágico"], "Clérigo": ["Bastón mágico"]
                }
                allowed_w = class_weapons.get(combat_class, [])
                if slot not in allowed_w:
                    await interaction.response.send_message(
                        f"❌ Como **{combat_class}**, no puedes equipar un **{slot}** "
                        f"(permitidos: {', '.join(allowed_w)}).",
                        ephemeral=True
                    )
                    return

        self.resolved = True
        await interaction.response.defer()

        old = await asyncio.to_thread(
            resolve_db_func("equip_item"), self.user.id,
            loot['slot'], loot['name'], loot['rarity'],
            loot['item_level'], loot['primary_stat'], loot['primary_value'],
            loot['secondaries'], loot['passive'],
            loot.get('mini_affix', {}).get('key') if loot.get('mini_affix') else None,
            loot.get('mini_affix', {}).get('value') if loot.get('mini_affix') else None,
            loot.get('weapon_subtype')
        )

        sell_msg = ""
        if old:
            old_sell = calc_sell_price(old['rarity'], old['item_level'])
            await asyncio.to_thread(resolve_db_func("add_combat_currency"), self.user.id, old_sell)
            sell_msg = f"\n💰 Vendiste **{old['item_name']}** por **{format_currency(old_sell)}**."

        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title="✅ ¡Equipado!",
            description=f"Equipaste **{loot['name']}** en {loot['slot']}.{sell_msg}",
            color=loot['rarity_hex']
        )
        await interaction.edit_original_response(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="💰 Vender", style=discord.ButtonStyle.secondary)
    async def sell_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Este drop no es para ti.", ephemeral=True)
            return
        if self.resolved:
            return

        self.resolved = True
        await interaction.response.defer()
        await self._sell(interaction)

    async def _sell(self, interaction=None):
        loot = self.loot
        await asyncio.to_thread(resolve_db_func("add_combat_currency"), self.user.id, loot['sell_price'])

        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title="💰 Vendido",
            description=f"Vendiste **{loot['name']}** por **{format_currency(loot['sell_price'])}**.",
            color=discord.Color.light_grey()
        )

        if interaction:
            await interaction.edit_original_response(embed=embed, view=self)
        elif self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass
        self.stop()

    async def on_timeout(self):
        if not self.resolved:
            self.resolved = True
            await self._sell()


# ══════════════════════════════════════════════
# VISTA: LOOT ROLL GRUPAL (Need/Greed/Pass)
# ══════════════════════════════════════════════

LOOT_ROLL_TIMEOUT = 45  # Segundos para decidir


class RaidLootRollView(discord.ui.View):
    """Vista de tirada de dados grupal para drops Épico/Legendario.

    Cada jugador elegible puede:
      🎯 Need  – Necesito este objeto (tira 1-100, +20 bonus).
      💰 Greed – Lo quiero para vender (tira 1-100).
      ❌ Pass  – No lo quiero.

    Al finalizar, el jugador con la tirada más alta gana el item.
    Si nadie tira, se vende y el oro se reparte.
    """

    def __init__(self, loot: dict, eligible_players: list[RaidCombatant], channel):
        super().__init__(timeout=LOOT_ROLL_TIMEOUT)
        self.loot = loot
        self.eligible_players = eligible_players
        self.eligible_ids = {p.user.id for p in eligible_players}
        self.channel = channel
        self.message = None
        self.resolved = False

        # Almacenar decisiones: user_id -> {"choice": "need"/"greed"/"pass", "roll": int}
        self.rolls: dict[int, dict] = {}

    def build_embed(self) -> discord.Embed:
        loot = self.loot
        embed = discord.Embed(
            title=f"🎲 ¡Loot Roll! — {loot['rarity_color']} {loot['name']}",
            description=(
                f"**{loot['rarity']}** · Nivel {loot['item_level']} · "
                f"{SLOT_EMOJIS.get(loot['slot'], '🔹')} {loot['slot']}\n\n"
                f"Elige tu opción:\n"
                f"🎯 **Need** — Lo necesito (+20 bonus a la tirada)\n"
                f"💰 **Greed** — Lo quiero para vender\n"
                f"❌ **Pass** — No lo quiero\n"
            ),
            color=loot['rarity_hex']
        )

        new_stats_text = format_item_stats_display(loot)
        embed.add_field(name="📊 Stats", value=new_stats_text, inline=False)

        # Mostrar quiénes ya tiraron
        status_lines = []
        for p in self.eligible_players:
            if p.user.id in self.rolls:
                r = self.rolls[p.user.id]
                choice_emoji = {"need": "🎯", "greed": "💰", "pass": "❌"}
                status_lines.append(
                    f"{choice_emoji.get(r['choice'], '❓')} **{p.user.display_name}** — "
                    f"{r['choice'].capitalize()}"
                    + (f" (🎲 {r['roll']})" if r['choice'] != 'pass' else "")
                )
            else:
                status_lines.append(f"⏳ **{p.user.display_name}** — Decidiendo...")

        embed.add_field(name="🎲 Tiradas", value="\n".join(status_lines) or "—", inline=False)
        embed.set_footer(text=f"Tiempo: {LOOT_ROLL_TIMEOUT}s · Si nadie tira, se vende y se reparte el oro.")
        return embed

    async def _check_all_rolled(self, interaction: discord.Interaction):
        """Verifica si todos ya tiraron y resuelve si es así."""
        if len(self.rolls) >= len(self.eligible_players):
            await self._resolve(interaction)

    @discord.ui.button(label="🎯 Need", style=discord.ButtonStyle.success, row=0)
    async def need_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_roll(interaction, "need")

    @discord.ui.button(label="💰 Greed", style=discord.ButtonStyle.primary, row=0)
    async def greed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_roll(interaction, "greed")

    @discord.ui.button(label="❌ Pass", style=discord.ButtonStyle.secondary, row=0)
    async def pass_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_roll(interaction, "pass")

    async def _handle_roll(self, interaction: discord.Interaction, choice: str):
        user_id = interaction.user.id

        if user_id not in self.eligible_ids:
            await interaction.response.send_message("❌ No participaste en esta raid.", ephemeral=True)
            return

        if user_id in self.rolls:
            await interaction.response.send_message("❌ Ya elegiste tu opción.", ephemeral=True)
            return

        if self.resolved:
            await interaction.response.send_message("❌ Este loot roll ya terminó.", ephemeral=True)
            return

        if choice == "pass":
            roll_val = 0
        elif choice == "need":
            roll_val = random.randint(1, 100) + 20  # Bonus de +20
        else:  # greed
            roll_val = random.randint(1, 100)

        self.rolls[user_id] = {"choice": choice, "roll": roll_val}

        # Actualizar el embed
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

        # Verificar si todos votaron
        await self._check_all_rolled(interaction)

    async def _resolve(self, interaction: discord.Interaction = None):
        if self.resolved:
            return
        self.resolved = True

        loot = self.loot

        # Filtrar los que NO hicieron pass
        active_rolls = {
            uid: data for uid, data in self.rolls.items()
            if data["choice"] != "pass"
        }

        # Desactivar botones
        for item in self.children:
            item.disabled = True

        if not active_rolls:
            # Nadie quiso el item → vender y repartir
            sell_price = loot['sell_price']
            share = sell_price // len(self.eligible_players)
            for p in self.eligible_players:
                await asyncio.to_thread(resolve_db_func("add_combat_currency"), p.user.id, share)

            embed = discord.Embed(
                title="💰 Nadie reclamó el loot",
                description=(
                    f"**{loot['rarity_color']} {loot['name']}** se vendió automáticamente por "
                    f"**{format_currency(sell_price)}**.\n"
                    f"Cada jugador recibió **{format_currency(share)}**."
                ),
                color=discord.Color.light_grey()
            )
        else:
            # El de mayor tirada gana
            winner_id = max(active_rolls, key=lambda uid: active_rolls[uid]["roll"])
            winner_data = active_rolls[winner_id]
            winner_player = next(p for p in self.eligible_players if p.user.id == winner_id)

            # Equipar o dar el item al ganador
            equipment = await asyncio.to_thread(resolve_db_func("get_user_equipment"), winner_id)
            current_piece = equipment.get(loot["slot"])

            # Enviar vista individual al ganador para decidir equipar/vender
            try:
                loot_view = RaidLootView(winner_player.user, loot, current_piece)
                loot_embed = loot_view.build_embed()
                await self.channel.send(
                    content=f"🎁 {winner_player.user.mention} — ¡Ganaste la tirada! Decide qué hacer:",
                    embed=loot_embed,
                    view=loot_view,
                )
            except Exception as exc:
                logger.warning("Error al enviar loot al ganador del roll: %r", exc)

            # Construir resultado
            result_lines = []
            for p in self.eligible_players:
                if p.user.id in self.rolls:
                    r = self.rolls[p.user.id]
                    choice_emoji = {"need": "🎯", "greed": "💰", "pass": "❌"}
                    is_winner = " 👑" if p.user.id == winner_id else ""
                    result_lines.append(
                        f"{choice_emoji.get(r['choice'], '❓')} **{p.user.display_name}** — "
                        f"{r['choice'].capitalize()}"
                        + (f" (🎲 {r['roll']})" if r['choice'] != 'pass' else "")
                        + is_winner
                    )
                else:
                    result_lines.append(f"❌ **{p.user.display_name}** — No respondió (Pass)")

            embed = discord.Embed(
                title=f"🎲 Loot Roll — Resultado",
                description=(
                    f"**{loot['rarity_color']} {loot['name']}**\n\n"
                    f"🏆 **¡{winner_player.user.display_name}** gana con una tirada de "
                    f"**{winner_data['roll']}** ({winner_data['choice'].capitalize()})!\n\n"
                    + "\n".join(result_lines)
                ),
                color=loot['rarity_hex']
            )

        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass
        self.stop()

    async def on_timeout(self):
        """Cuando expira el tiempo, los que no votaron se marcan como Pass."""
        if self.resolved:
            return

        # Marcar como Pass a los que no votaron
        for p in self.eligible_players:
            if p.user.id not in self.rolls:
                self.rolls[p.user.id] = {"choice": "pass", "roll": 0}

        await self._resolve()


# ══════════════════════════════════════════════
# Funciones auxiliares movidas de raid.py
# ══════════════════════════════════════════════

def log_raid(boss_name: str, participants: list, result: str, turns: int, total_level: int, difficulty: str = "normal"):
    """Registra una raid completada en la base de datos."""
    with resolve_db_func("db_cursor")() as cursor:
        # Crear tabla si no existe
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS RaidLog (
                ID SERIAL PRIMARY KEY,
                BossName VARCHAR(50),
                Participants JSONB,
                Result VARCHAR(10),
                Turns INT,
                TotalLevel INT,
                Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                Difficulty VARCHAR(10) DEFAULT 'normal'
            )
        """)
        cursor.execute("ALTER TABLE RaidLog ADD COLUMN IF NOT EXISTS Difficulty VARCHAR(10) DEFAULT 'normal'")
        cursor.execute("""
            INSERT INTO RaidLog (BossName, Participants, Result, Turns, TotalLevel, Difficulty)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (boss_name, psycopg2.extras.Json(participants), result, turns, total_level, difficulty))


def count_mythic_raids_today(user_id: int) -> int:
    """Cuenta cuántas raids Míticas ha iniciado o participado un usuario hoy (hora del servidor/DB)."""
    with resolve_db_func("db_cursor")() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM RaidLog
            WHERE Difficulty = 'mitica'
              AND Timestamp::date = CURRENT_DATE
              AND Participants @> %s
        """, (psycopg2.extras.Json([{"user_id": user_id}]),))
        return cursor.fetchone()[0]


def build_minions_from_pool(boss_config) -> list[dict]:
    if isinstance(boss_config, dict):
        pool = boss_config.get("minion_pool")
    else:
        pool = getattr(boss_config, "minion_pool", None)
    if pool is None:  # Caso Abyssus: 2 random
        pool = random.sample(list(MINION_ARCHETYPES.keys()), 2)
    minions = []
    for key in pool:
        arch = MINION_ARCHETYPES[key]
        minions.append({
            "name": arch["name"], "archetype": key, "hp": arch["hp"], "max_hp": arch["hp"],
            "def_stat": arch["def_stat"],
            "stun_turns": 0, "weakness_turns": 0, "weakness_pct": 0.0,
            "fragility_turns": 0, "fragility_pct": 0.0, "vulnerability_turns": 0, "vulnerability_pct": 0.0,
            "burn_turns": 0, "poison_turns": 0, "poison_damage": 0,
            "frozen_turns": 0, "silence_turns": 0, "bleed_turns": 0, "bleed_source_pct": 0.06,
            "last_physical_damage_taken": 0,
            "fuse_counter": 0,  # Solo usado por Explosivo
        })
    return minions


def build_miniboss_config(miniboss_key: str, miniboss_dict: dict) -> dict:
    return {
        "name": miniboss_dict["name"],
        "emoji": miniboss_dict["emoji"],
        "element": miniboss_dict.get("element", "Neutral"),
        "color": miniboss_dict.get("color", 0x8B4513),
        "base_hp": miniboss_dict.get("hp", 0),
        "base_atk": miniboss_dict.get("atk", 0),
        "base_def": miniboss_dict.get("def_stat", 0),
        "hp": miniboss_dict.get("hp", 0),
        "atk": miniboss_dict.get("atk", 0),
        "def_stat": miniboss_dict.get("def_stat", 0),
        "ability": miniboss_dict.get("ability", "none"),
        "lore": miniboss_dict["lore"],
        "minion_pool": [],
        "is_miniboss": True,
        "miniboss_key": miniboss_key,
        "guaranteed_loot": miniboss_dict.get("guaranteed_loot", False),
        "invisibility_pattern": miniboss_dict.get("invisibility_pattern", False),
        "is_shop": miniboss_dict.get("is_shop", False),
    }



def roll_unique_item(boss_name: str) -> dict | None:
    """8% de probabilidad ya se evalúa antes de llamar esto. Retorna un ítem del catálogo o None."""
    from src.utils.combat_progression import RARITY_COLORS, calc_sell_price

    with resolve_db_func("db_cursor")() as cursor:
        cursor.execute("""
            SELECT ItemKey, Name, Slot, Rarity, PrimaryStat, PrimaryValue, Secondaries, Passive, Lore
            FROM UniqueItemCatalog
            WHERE BossSource = %s OR BossSource IS NULL
        """, (boss_name,))
        rows = cursor.fetchall()
    if not rows:
        return None

    # Seleccionar uno al azar
    row = random.choice(rows)
    item_key, name, slot, rarity, primary_stat, primary_value, secondaries, passive, lore = row

    # Armar stats_summary para que coincida con generate_loot()
    stats_summary = {primary_stat: primary_value}
    for sec in secondaries:
        stats_summary[sec["stat"]] = stats_summary.get(sec["stat"], 0) + sec["value"]

    rarity_hex = RARITY_COLORS.get(rarity, 0xff8800)
    sell_price = calc_sell_price(rarity, 35)

    return {
        "slot": slot,
        "name": name,
        "rarity": rarity,
        "rarity_color": "🟧",  # Color de Legendario
        "rarity_hex": rarity_hex,
        "item_level": 35,
        "primary_stat": primary_stat,
        "primary_value": primary_value,
        "secondaries": secondaries,
        "passive": passive,
        "sell_price": sell_price,
        "stats_summary": stats_summary,
        "item_key": item_key,  # Guardar referencia
        "lore": lore
    }
