import discord
import asyncio
from src.utils.combat_config import SKILLS_CONFIG
from src.db import use_consumable, get_consumable_catalog

class PersonalSkillSelectView(discord.ui.View):
    """Menú efímero de un solo select para que un jugador elija su habilidad especial en la raid."""

    def __init__(self, raid_view, player, options: list[discord.SelectOption]):
        super().__init__(timeout=60)
        self.raid_view = raid_view
        self.player = player

        # Crear el select dinámicamente con las opciones del jugador
        select = discord.ui.Select(
            placeholder="✨ Seleccionar Habilidad Especial...",
            min_values=1,
            max_values=1,
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        # Deshabilitar el select para evitar dobles clics, pero NO respondemos todavía —
        # esperamos a saber el resultado final para editar una sola vez.
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True

        # 1. Comprobar condiciones (defensa en profundidad)
        if self.raid_view.game_over:
            await interaction.response.edit_message(content="❌ La raid ya terminó.", view=self)
            return

        user_id = self.player.user.id
        if user_id in self.raid_view.actions:
            await interaction.response.edit_message(content="❌ Ya elegiste tu acción.", view=self)
            return

        selected_value = interaction.data["values"][0]
        if selected_value == "none":
            await interaction.response.edit_message(content="❌ No tienes habilidades especiales disponibles.", view=self)
            return

        # 2. Validar cooldown, clase, nivel y subclase
        req = SKILLS_CONFIG.get(selected_value)
        if not req:
            await interaction.response.edit_message(content="❌ Habilidad desconocida.", view=self)
            return

        if req.get("min_level") == 10:
            cd = self.player.skill10_cooldown
        elif req.get("min_level") == 15:
            cd = self.player.skill15_cooldown
        else:
            cd = self.player.special_cooldown

        if cd > 0:
            await interaction.response.edit_message(
                content=f"❌ Habilidad en enfriamiento ({cd} turnos restantes).", view=self
            )
            return

        if req["class"] is not None:
            if self.player.level < req["min_level"] or self.player.combat_class != req["class"]:
                await interaction.response.edit_message(
                    content=f"❌ Solo los **{req['class']}** de nivel **{req['min_level']}+** pueden usar esta habilidad.",
                    view=self
                )
                return

        if req.get("subclass") is not None:
            if self.player.combat_subclass != req["subclass"]:
                await interaction.response.edit_message(
                    content=f"❌ Solo la subclase **{req['subclass']}** puede usar esta habilidad.", view=self
                )
                return

        # 3. Todo válido — editar el mismo mensaje con la confirmación final
        await interaction.response.edit_message(content=f"✅ Habilidad especial registrada: **{req['name']}**", view=self)

        # 4. Registrar la acción
        await self.raid_view._register_action(interaction, selected_value, is_ephemeral=True)


class PersonalRaidConsumableSelectView(discord.ui.View):
    """Menú efímero de un solo select para que un jugador elija su consumible en una raid."""
    def __init__(self, raid_view, player, options: list[discord.SelectOption]):
        super().__init__(timeout=60)
        self.raid_view = raid_view
        self.player = player

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

        if self.raid_view.game_over:
            await interaction.response.edit_message(content="❌ La raid ya terminó.", view=self)
            return

        user_id = self.player.user.id
        if user_id in self.raid_view.actions:
            await interaction.response.edit_message(content="❌ Ya elegiste tu acción.", view=self)
            return

        selected_value = interaction.data["values"][0]

        # Si el consumible es frasco_silencio y hay esbirros vivos, ir al menú de selección de objetivo
        alive_minions = [m for m in self.raid_view.minions if m["hp"] > 0]
        if selected_value == "frasco_silencio" and alive_minions:
            target_options = [
                discord.SelectOption(
                    label=f"{self.raid_view.boss.name} (Jefe)",
                    value="boss",
                    description=f"HP: {self.raid_view.boss.hp}/{self.raid_view.boss.max_hp}"
                )
            ]
            for idx, m in enumerate(self.raid_view.minions):
                if m["hp"] > 0:
                    target_options.append(
                        discord.SelectOption(
                            label=m["name"],
                            value=f"minion:{idx}",
                            description=f"HP: {m['hp']}/{m['max_hp']}"
                        )
                    )
            view = RaidSilenceTargetSelectView(raid_view=self.raid_view, player=self.player, target_options=target_options)
            await interaction.response.edit_message(content="Elige el objetivo para silenciar:", view=view)
            return

        # Para los demás consumibles (o frasco_silencio sin esbirros), descontar de inmediato
        success = await asyncio.to_thread(use_consumable, user_id, selected_value)
        if not success:
            await interaction.response.edit_message(content="❌ No tienes suficiente cantidad de este consumible.", view=self)
            return

        # Registrar acción
        action_str = f"consumable:{selected_value}"
        if selected_value == "frasco_silencio":
            action_str = "consumable:frasco_silencio:boss"

        # Obtener nombre para confirmación
        catalog = await asyncio.to_thread(get_consumable_catalog)
        c_info = next((item for item in catalog if item['consumable_key'] == selected_value), None)
        c_name = c_info['name'] if c_info else selected_value

        await interaction.response.edit_message(content=f"✅ Consumible registrado: **{c_name}**", view=self)
        await self.raid_view._register_action(interaction, action_str, is_ephemeral=True)


class RaidSilenceTargetSelectView(discord.ui.View):
    """Menú efímero para seleccionar el objetivo de silencio (Boss o esbirro) en raid."""
    def __init__(self, raid_view, player, target_options: list[discord.SelectOption]):
        super().__init__(timeout=60)
        self.raid_view = raid_view
        self.player = player

        select = discord.ui.Select(
            placeholder="🎯 Selecciona el Objetivo...",
            min_values=1,
            max_values=1,
            options=target_options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True

        if self.raid_view.game_over:
            await interaction.response.edit_message(content="❌ La raid ya terminó.", view=self)
            return

        user_id = self.player.user.id
        if user_id in self.raid_view.actions:
            await interaction.response.edit_message(content="❌ Ya elegiste tu acción.", view=self)
            return

        target_value = interaction.data["values"][0]

        # Descontar el consumible
        success = await asyncio.to_thread(use_consumable, user_id, "frasco_silencio")
        if not success:
            await interaction.response.edit_message(content="❌ No tienes suficiente cantidad de este consumible.", view=self)
            return

        # Registrar la acción (e.g. consumable:frasco_silencio:boss o consumable:frasco_silencio:minion:0)
        action_str = f"consumable:frasco_silencio:{target_value}"

        await interaction.response.edit_message(content=f"✅ Consumible registrado: **Frasco de Silencio**", view=self)
        await self.raid_view._register_action(interaction, action_str, is_ephemeral=True)
