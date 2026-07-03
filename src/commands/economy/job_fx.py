"""
job_fx.py — Capa compartida de "sabor" interactivo para los 11 trabajos de /trabajo.

Este módulo NO reemplaza la lógica de cada trabajo (Minero, Pescador, Científico,
etc. siguen teniendo su propio minijuego). Añade una capa reutilizable que se
puede invocar desde cualquiera de los 11 trabajos para:

  1. Dar variedad de INTERACCIÓN (Select menu de decisión, no solo botones).
  2. Introducir una decisión de riesgo/recompensa ANTES de empezar el trabajo.
  3. Hacerlo sin tocar el balance económico interno de cada minijuego: el
     bono/penalización de este evento se paga aparte, con su propia línea de
     transacción, así que no hay que reescribir el cálculo de recompensa de
     cada trabajo para integrarlo.

Uso típico dentro de iniciar_trabajo_X(interaction):

    from .job_fx import tal_vez_cliente_especial
    ...
    consumido = consumir_energia(user_id, energia_req)
    if not consumido:
        await interaction.followup.send("❌ Alguien más ya usó esa energía...", ephemeral=True)
        return
    await tal_vez_cliente_especial(interaction, user_id, tipo_trabajo)
    # ... el resto del trabajo continúa igual que antes ...
"""

import random
import asyncio
import discord

from src.db import get_balance, set_balance, registrar_transaccion
from .niveles_trabajo import TIPOS_TRABAJO, add_experiencia_trabajo

# Probabilidad de que aparezca el evento al iniciar cualquier trabajo.
PROBABILIDAD_CLIENTE_ESPECIAL = 0.15

# Frases de sabor por trabajo, para que el mismo evento no se sienta genérico.
FLAVOR_CLIENTE = {
    "hacker":            ("🕵️ Un contacto anónimo en la deep web", "te ofrece pagar extra por discreción."),
    "chef":               ("🍽️ Un crítico gastronómico encubierto", "está en el local y quiere probar algo especial."),
    "artista":            ("🖼️ Un coleccionista excéntrico", "quiere encargarte una pieza fuera de catálogo."),
    "mecanico":           ("🏎️ Un piloto de carreras", "necesita una reparación urgente antes de una carrera."),
    "minero":             ("💰 Un comprador de minerales de mercado negro", "ofrece un trato antes de que bajes al pozo."),
    "pescador":           ("⛵ Un comerciante de puerto", "busca una pieza específica para su restaurante."),
    "piloto":             ("✈️ Un pasajero VIP de último minuto", "pide subir a tu vuelo con una propina generosa."),
    "cazarrecompensas":   ("📜 Un informante callejero", "dice tener información valiosa sobre tu objetivo."),
    "medico":             ("🏥 La familia de un paciente adinerado", "ofrece una donación si todo sale bien."),
    "ladron":             ("🎭 Un contacto del gremio de ladrones", "tiene un dato sobre la caja fuerte de esta noche."),
    "cientifico":         ("🧪 Un representante de un laboratorio rival", "quiere financiar tu experimento en secreto."),
}


class ClienteEspecialView(discord.ui.View):
    """Vista de una sola decisión (Select menu) para el evento de Cliente Especial."""

    def __init__(self, user_id: int):
        super().__init__(timeout=12.0)
        self.user_id = user_id
        self.eleccion = None  # "arriesgar" | "seguro" | "rechazar" | None (timeout)
        self.resuelto = False

        select = discord.ui.Select(
            placeholder="¿Qué haces con el cliente?",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Negociar un trato arriesgado",
                    value="arriesgar",
                    emoji="🎲",
                    description="Puede pagar mucho más... o irse sin dejar nada."
                ),
                discord.SelectOption(
                    label="Aceptar el precio estándar",
                    value="seguro",
                    emoji="🤝",
                    description="Una propina pequeña, pero segura."
                ),
                discord.SelectOption(
                    label="Rechazar y concentrarte en el trabajo",
                    value="rechazar",
                    emoji="🚪",
                    description="Sin propina, sin riesgo. Vas directo al trabajo."
                ),
            ],
        )
        select.callback = self._callback
        self.add_item(select)

    async def _callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Este cliente no vino a buscarte a ti.", ephemeral=True)
            return
        if self.resuelto:
            await interaction.response.defer()
            return

        self.resuelto = True
        self.eleccion = interaction.data["values"][0]
        for item in self.children:
            item.disabled = True
        await interaction.response.defer()
        self.stop()

    async def on_timeout(self):
        if not self.resuelto:
            self.resuelto = True
            self.eleccion = None
            for item in self.children:
                item.disabled = True


def _resolver_pago(user_id: int, tipo_trabajo: str, eleccion: str):
    """Calcula y aplica el pago del evento. Se ejecuta en un hilo aparte (bloqueante)."""
    recompensa_base = TIPOS_TRABAJO.get(tipo_trabajo, {}).get("recompensa_base", 200)

    if eleccion == "arriesgar":
        if random.random() < 0.5:
            monto = int(recompensa_base * random.uniform(0.35, 0.55))
            exito = True
        else:
            monto = 0
            exito = False
    elif eleccion == "seguro":
        monto = int(recompensa_base * random.uniform(0.08, 0.14))
        exito = True
    else:
        return None  # rechazado o timeout: no hay pago que registrar

    if monto > 0:
        saldo_actual = get_balance(user_id)
        set_balance(user_id, saldo_actual + monto)
        registrar_transaccion(user_id, monto, f"Propina: Cliente Especial ({tipo_trabajo})")
        add_experiencia_trabajo(user_id, tipo_trabajo, 3)

    return {"exito": exito, "monto": monto}


async def tal_vez_cliente_especial(interaction: discord.Interaction, user_id: int, tipo_trabajo: str) -> None:
    """Punto de entrada único. Con PROBABILIDAD_CLIENTE_ESPECIAL de probabilidad,
    muestra el evento de Cliente Especial antes de que arranque el trabajo.
    Si no se activa, no hace nada (no envía ningún mensaje) y el trabajo
    continúa exactamente como antes."""
    if random.random() >= PROBABILIDAD_CLIENTE_ESPECIAL:
        return

    apodo, gancho = FLAVOR_CLIENTE.get(tipo_trabajo, ("🎭 Un cliente inesperado", "quiele hacer un trato contigo."))

    embed = discord.Embed(
        title=f"{apodo}",
        description=f"Justo antes de empezar, {gancho}\n\n¿Qué decides?",
        color=discord.Color.gold(),
    )
    embed.set_footer(text="Tienes 12 segundos para decidir. Si no eliges, se cancela sin costo.")

    view = ClienteEspecialView(user_id)
    msg = await interaction.followup.send(embed=embed, view=view, wait=True)
    await view.wait()

    if view.eleccion in (None, "rechazar"):
        texto = "🚪 Decidiste no perder el tiempo y fuiste directo al trabajo." if view.eleccion == "rechazar" \
            else "⌛ El cliente se cansó de esperar y se fue."
        embed_res = discord.Embed(description=texto, color=discord.Color.greyple())
        await msg.edit(embed=embed_res, view=None)
        await asyncio.sleep(1.2)
        return

    resultado = await asyncio.to_thread(_resolver_pago, user_id, tipo_trabajo, view.eleccion)

    if view.eleccion == "seguro":
        embed_res = discord.Embed(
            title="🤝 Trato cerrado",
            description=f"El cliente pagó el precio estándar.\n💰 **+{resultado['monto']}** monedas de propina.",
            color=discord.Color.green(),
        )
    elif resultado["exito"]:
        embed_res = discord.Embed(
            title="🎲 ¡El riesgo valió la pena!",
            description=f"El cliente pagó mucho más de lo esperado.\n💰 **+{resultado['monto']}** monedas de propina.",
            color=discord.Color.gold(),
        )
    else:
        embed_res = discord.Embed(
            title="🎲 El cliente se arrepintió",
            description="Negociaste demasiado y se fue sin pagar nada. Al menos no perdiste tiempo extra.",
            color=discord.Color.red(),
        )

    await msg.edit(embed=embed_res, view=None)
    await asyncio.sleep(1.4)
