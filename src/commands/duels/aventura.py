import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import math
from src.db import db_cursor, ensure_user, get_user_combat_level
from src.commands.duels.raid.combatant import RaidCombatant

MAPAS_AVENTURA = {
    "bosque": {
        "nombre": "🌲 Bosque Sombrío",
        "level_req": 1,
        "mob_name": "Goblin Silvestre",
        "mob_emoji": "👺",
        "base_hp": 80,
        "base_atk": 12,
        "base_def": 4,
        "bronze_reward": 50,
        "color": discord.Color.green()
    },
    "cripta": {
        "nombre": "🪦 Cripta Olvidada",
        "level_req": 11,
        "mob_name": "Esqueleto Guardián",
        "mob_emoji": "💀",
        "base_hp": 180,
        "base_atk": 25,
        "base_def": 10,
        "bronze_reward": 180,
        "color": discord.Color.dark_grey()
    },
    "volcan": {
        "nombre": "🌋 Furia Volcánica",
        "level_req": 26,
        "mob_name": "Elemental de Magma",
        "mob_emoji": "🔥",
        "base_hp": 380,
        "base_atk": 45,
        "base_def": 18,
        "bronze_reward": 450,
        "color": discord.Color.orange()
    },
    "abismo": {
        "nombre": "🧊 Abismo Helado",
        "level_req": 41,
        "mob_name": "Gólem Glacial",
        "mob_emoji": "❄️",
        "base_hp": 750,
        "base_atk": 75,
        "base_def": 30,
        "bronze_reward": 1000,
        "color": discord.Color.blue()
    },
    "ciudadela": {
        "nombre": "🏰 Ciudadela del Caos",
        "level_req": 61,
        "mob_name": "Caballero del Abismo",
        "mob_emoji": "⚔️",
        "base_hp": 1500,
        "base_atk": 130,
        "base_def": 50,
        "bronze_reward": 2500,
        "color": discord.Color.dark_purple()
    }
}

class AventuraView(discord.ui.View):
    def __init__(self, user_id: int, mapa_key: str, player_combatant: RaidCombatant):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.mapa_key = mapa_key
        self.mapa_info = MAPAS_AVENTURA[mapa_key]
        self.p = player_combatant
        self.current_round = 1
        self.max_rounds = 10
        self.total_bronze_gained = 0
        self.combat_logs = []

    @discord.ui.button(label="⚔️ Siguiente Ronda", style=discord.ButtonStyle.primary)
    async def btn_next_round(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Esta aventura no es tuya.", ephemeral=True)
            return

        await interaction.response.defer()

        # Simular combate de ronda rápida
        mob_mult = 1.0 + ((self.current_round - 1) * 0.15)
        m_hp = int(self.mapa_info["base_hp"] * mob_mult)
        m_atk = int(self.mapa_info["base_atk"] * mob_mult)
        m_def = int(self.mapa_info["base_def"] * mob_mult)
        m_name = f"{self.mapa_info['mob_emoji']} {self.mapa_info['mob_name']} (Ronda {self.current_round})"

        # Ejecutar pet ai si existe
        pet_log = self.p.execute_pet_raid_ai(0.5, False)

        # Daño del jugador
        p_dmg = max(1, self.p.atk - m_def)
        if random.random() < self.p.subclass_extras.get("crit_chance_bonus", 0.05):
            p_dmg = int(p_dmg * 1.5)

        m_hp -= p_dmg

        # Daño del enemigo si sobrevive
        if m_hp > 0:
            m_dmg = max(1, m_atk - self.p.def_stat)
            self.p.hp = max(0, self.p.hp - m_dmg)

        # Recompensas de la ronda
        round_bronze = int(self.mapa_info["bronze_reward"] * mob_mult)
        self.total_bronze_gained += round_bronze

        self.combat_logs.append(f"**Ronda {self.current_round}:** Daño causado: **{p_dmg}** | {m_name} derrotado (+{round_bronze} Bronce 🥉)")
        if pet_log:
            self.combat_logs.append(f"   {pet_log}")

        if self.p.hp <= 0:
            # Jugador cayó
            for child in self.children:
                child.disabled = True

            embed = discord.Embed(
                title=f"💀 Derrota en {self.mapa_info['nombre']}",
                description=f"Has caído en la **Ronda {self.current_round}**.\n\n" + "\n".join(self.combat_logs[-5:]),
                color=discord.Color.red()
            )
            embed.add_field(name="💰 Botín Rescatado", value=f"**{self.total_bronze_gained:,}** Monedas de Bronce 🥉")
            await self._award_recompensa(self.total_bronze_gained)
            await interaction.edit_original_response(embed=embed, view=self)
            return

        if self.current_round >= self.max_rounds:
            # Aventura completada 100%
            for child in self.children:
                child.disabled = True

            embed = discord.Embed(
                title=f"🏆 ¡Aventura Completada en {self.mapa_info['nombre']}!",
                description=f"¡Has superado las 10 rondas con éxito!\n\n" + "\n".join(self.combat_logs[-5:]),
                color=discord.Color.gold()
            )
            embed.add_field(name="💰 Botín Total", value=f"**{self.total_bronze_gained:,}** Monedas de Bronce 🥉")
            await self._award_recompensa(self.total_bronze_gained)
            await interaction.edit_original_response(embed=embed, view=self)
            return

        self.current_round += 1
        embed = self._build_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="🏃 Retirarse con Botín", style=discord.ButtonStyle.secondary)
    async def btn_retreat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return

        await interaction.response.defer()
        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            title=f"🏃 Retirada Estratégica",
            description=f"Te retiraste en la **Ronda {self.current_round}** conservando tu botín.",
            color=discord.Color.light_grey()
        )
        embed.add_field(name="💰 Botín Conseguido", value=f"**{self.total_bronze_gained:,}** Monedas de Bronce 🥉")
        await self._award_recompensa(self.total_bronze_gained)
        await interaction.edit_original_response(embed=embed, view=self)

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.mapa_info['nombre']} — Ronda {self.current_round}/{self.max_rounds}",
            description=f"❤️ **Tu HP:** `{self.p.hp}/{self.p.max_hp}` | ⚔️ **ATK:** `{self.p.atk}` | 🛡️ **DEF:** `{self.p.def_stat}`\n\n"
                        f"💰 **Botín acumulado:** `{self.total_bronze_gained:,}` Bronce 🥉\n\n" +
                        ("\n".join(self.combat_logs[-4:]) if self.combat_logs else "_Presiona **Siguiente Ronda** para combatir._"),
            color=self.mapa_info["color"]
        )
        return embed

    async def _award_recompensa(self, bronze_amount: int):
        if bronze_amount <= 0:
            return
        def _save():
            with db_cursor() as c:
                c.execute("""
                    INSERT INTO CombatWallet (UserID, Bronze)
                    VALUES (%s, %s)
                    ON CONFLICT (UserID) DO UPDATE SET Bronze = CombatWallet.Bronze + EXCLUDED.Bronze
                """, (self.user_id, bronze_amount))
            if self.guild_id:
                pts = 3 if self.current_round >= 10 else 1
                from src.db import add_poblado_resources, record_poblado_contribution
                add_poblado_resources(self.guild_id, puntos=pts)
                record_poblado_contribution(self.guild_id, self.user_id, puntos=pts, materiales=0)

        await asyncio.to_thread(_save)

class Aventura(commands.Cog):
    """Cog para el Modo Aventura (PvE rápido de 1 a 10 rondas)."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="aventura", description="Inicia una expedición PvE de combate rápido (1-10 rondas).")
    @app_commands.describe(mapa="Selecciona la locación de la aventura")
    @app_commands.choices(mapa=[
        app_commands.Choice(name="🌲 Bosque Sombrío (Nv. 1+)", value="bosque"),
        app_commands.Choice(name="🪦 Cripta Olvidada (Nv. 11+)", value="cripta"),
        app_commands.Choice(name="🌋 Furia Volcánica (Nv. 26+)", value="volcan"),
        app_commands.Choice(name="🧊 Abismo Helado (Nv. 41+)", value="abismo"),
        app_commands.Choice(name="🏰 Ciudadela del Caos (Nv. 61+)", value="ciudadela")
    ])
    async def aventura_cmd(self, interaction: discord.Interaction, mapa: str):
        await interaction.response.defer()
        user_id = interaction.user.id
        
        mapa_info = MAPAS_AVENTURA.get(mapa)
        if not mapa_info:
            await interaction.followup.send("❌ Mapa no válido.", ephemeral=True)
            return

        def _setup_player():
            with db_cursor() as c:
                c.execute("SELECT CombatLevel, CombatClass, CombatSubclass FROM CombatStats WHERE UserID = %s", (user_id,))
                row = c.fetchone()
                lvl = row[0] if row else 1
                c_class = row[1] if row else "Guerrero"
                c_subclass = row[2] if row else None
                
                # Cargar equipo
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

        if lvl < mapa_info["level_req"]:
            await interaction.followup.send(f"❌ Requieres Nivel de Combate **{mapa_info['level_req']}** para ingresar a {mapa_info['nombre']}.", ephemeral=True)
            return

        combatant = RaidCombatant(interaction.user, lvl, equipment, c_class, c_subclass)
        view = AventuraView(user_id, mapa, combatant, interaction.guild_id)
        embed = view._build_embed()
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Aventura(bot))
    print("Aventura cog loaded successfully.")
