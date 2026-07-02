"""Cooldowns nativos de Discord para mitigar spam en comandos económicos."""

import discord.app_commands as app_commands

# Comandos que mueven dinero o consumen recursos limitados
ECONOMY_COOLDOWN = app_commands.checks.cooldown(1, 3.0, key=lambda i: i.user.id)

# Juegos de casino (rondas rápidas)
CASINO_COOLDOWN = app_commands.checks.cooldown(1, 2.0, key=lambda i: i.user.id)
