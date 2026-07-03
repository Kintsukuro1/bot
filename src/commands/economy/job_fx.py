"""
job_fx.py — Capa compartida de "sabor" interactivo para los 11 trabajos de /trabajo.

Este módulo NO reemplaza la lógica de cada trabajo (Minero, Pescador, Científico,
etc. siguen teniendo su propio minijuego). Añade una capa reutilizable que se
invoca UNA VEZ, justo antes de que arranque el minijuego de cada trabajo:

    consumido = consumir_energia(user_id, energia_req)
    if not consumido:
        ...
        return
    await fase_previa_trabajo(interaction, user_id, tipo_trabajo)
    # ... el resto del trabajo continúa igual que antes ...

fase_previa_trabajo hace 3 cosas, en este orden, sin apilar varios popups:

  1. Registra la racha diaria del oficio (silenciosa salvo en hitos) y paga
     su bono aparte, sin tocar el cálculo de recompensa interno del trabajo.
  2. Tira UNA sola vez los dados para decidir si aparece un evento especial:
     Turno Dorado (raro, bono grande automático) o Cliente Especial (más
     común, requiere una decisión con Select menu). Nunca aparecen los dos
     a la vez, para no interrumpir al jugador con múltiples decisiones antes
     de haber empezado a trabajar.

Todo el dinero que reparte este módulo se paga con su propia línea de
transacción (registrar_transaccion), así que no hace falta reescribir el
cálculo de recompensa de cada minijuego para integrarlo.
"""

import random
import asyncio
import discord

from src.db import get_balance, set_balance, registrar_transaccion, actualizar_racha_trabajo
from .niveles_trabajo import TIPOS_TRABAJO, add_experiencia_trabajo

# Probabilidades del roll combinado de evento especial (se evalúan en orden).
PROBABILIDAD_TURNO_DORADO = 0.03
PROBABILIDAD_CLIENTE_ESPECIAL = 0.15

# Hitos de racha en los que sí vale la pena interrumpir con un mensaje.
HITOS_RACHA = {2, 3, 5, 7, 14, 21, 30, 60, 100}

# Frases de sabor por trabajo, para que el mismo evento no se sienta genérico.
FLAVOR_CLIENTE = {
    "hacker":            ("🕵️ Un contacto anónimo en la deep web", "te ofrece pagar extra por discreción."),
    "chef":               ("🍽️ Un crítico gastronómico encubierto", "está en el local y quiere probar algo especial."),
    "artista":            ("🎨 Un coleccionista excéntrico", "quiere encargarte una pieza fuera de catálogo."),
    "mecanico":           ("🔧 Un piloto de carreras", "necesita una reparación urgente antes de una carrera."),
    "minero":             ("💰 Un comprador de minerales de mercado negro", "ofrece un trato antes de que bajes al pozo."),
    "pescador":           ("⛵ Un comerciante de puerto", "busca una pieza específica para su restaurante."),
    "piloto":             ("✈️ Un pasajero VIP de último minuto", "pide subir a tu vuelo con una propina generosa."),
    "cazarrecompensas":   ("📜 Un informante callejero", "dice tener información valiosa sobre tu objetivo."),
    "medico":             ("🏥 La familia de un paciente adinerado", "ofrece una donación si todo sale bien."),
    "ladron":             ("🎭 Un contacto del gremio de ladrones", "tiene un dato sobre la caja fuerte de esta noche."),
    "cientifico":         ("🧪 Un representante de un laboratorio rival", "quiere financiar tu experimento en secreto."),
}

FLAVOR_DORADO = {
    "hacker":            "El sistema que vulneraste resultó tener una recompensa por bug bounty activa.",
    "chef":               "Un food-blogger viral publicó tu plato antes de que terminaras de cocinarlo.",
    "artista":            "Tu obra se volvió tendencia en redes justo antes de exhibirla.",
    "mecanico":           "El cliente resultó ser el dueño del taller de la competencia, y pagó de más para ficharte",
    "minero":             "Encontraste una veta que nadie había registrado todavía.",
    "pescador":           "Un comprador de temporada está pagando el triple por pesca fresca hoy.",
    "piloto":             "La aerolínea añadió un bono por vuelo sin incidentes reportados este mes.",
    "cazarrecompensas":   "Resulta que había una recompensa adicional por el mismo objetivo.",
    "medico":             "El hospital tiene un bono por turno de alta demanda hoy.",
    "ladron":             "Un comprador del mercado negro paga extra por artículos de esta zona hoy.",
    "cientifico":         "Tu instituto recibió una subvención inesperada este mes.",
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


def _pagar_bono(user_id: int, tipo_trabajo: str, monto: int, motivo: str, xp: int = 0):
    if monto > 0:
        saldo_actual = get_balance(user_id)
        set_balance(user_id, saldo_actual + monto)
        registrar_transaccion(user_id, monto, motivo)
    if xp > 0:
        add_experiencia_trabajo(user_id, tipo_trabajo, xp)


def _resolver_pago_cliente(user_id: int, tipo_trabajo: str, eleccion: str):
    """Se ejecuta en un hilo aparte (bloqueante)."""
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

    _pagar_bono(user_id, tipo_trabajo, monto, f"Propina: Cliente Especial ({tipo_trabajo})", xp=3)
    return {"exito": exito, "monto": monto}


def _resolver_racha_y_dorado(user_id: int, tipo_trabajo: str):
    """Combina en un solo hilo bloqueante: registrar racha diaria + decidir y
    pagar Turno Dorado si corresponde. Retorna toda la info que la parte
    async necesita para dibujar los embeds."""
    racha_info = actualizar_racha_trabajo(user_id, tipo_trabajo)
    bono_racha = 0
    if racha_info["es_nueva_hoy"] and racha_info["racha"] >= 2:
        recompensa_base = TIPOS_TRABAJO.get(tipo_trabajo, {}).get("recompensa_base", 200)
        porcentaje = min(0.04 * racha_info["racha"], 0.40)
        bono_racha = int(recompensa_base * porcentaje)
        _pagar_bono(user_id, tipo_trabajo, bono_racha, f"Bono de Racha x{racha_info['racha']} ({tipo_trabajo})")
    racha_info["bono"] = bono_racha

    evento = None
    roll = random.random()
    if roll < PROBABILIDAD_TURNO_DORADO:
        recompensa_base = TIPOS_TRABAJO.get(tipo_trabajo, {}).get("recompensa_base", 200)
        monto = recompensa_base  # bono equivalente a duplicar la paga promedio de este trabajo
        _pagar_bono(user_id, tipo_trabajo, monto, f"🌟 Turno Dorado ({tipo_trabajo})", xp=8)
        evento = {"tipo": "dorado", "monto": monto}
    elif roll < PROBABILIDAD_TURNO_DORADO + PROBABILIDAD_CLIENTE_ESPECIAL:
        evento = {"tipo": "cliente"}

    return racha_info, evento


async def fase_previa_trabajo(interaction: discord.Interaction, user_id: int, tipo_trabajo: str) -> None:
    """Punto de entrada único. Se llama justo después de consumir energía y
    antes de que arranque el minijuego de cualquiera de los 11 trabajos."""

    racha_info, evento = await asyncio.to_thread(_resolver_racha_y_dorado, user_id, tipo_trabajo)

    # 1. Mostrar la racha solo si es un hito (para no spamear cada vez que se trabaja)
    if racha_info["es_nueva_hoy"] and racha_info["racha"] in HITOS_RACHA:
        texto_bono = f"\n💰 **Bono de racha:** +{racha_info['bono']} monedas" if racha_info["bono"] > 0 else ""
        embed_racha = discord.Embed(
            title=f"🔥 ¡{racha_info['racha']} días seguidos trabajando de {TIPOS_TRABAJO.get(tipo_trabajo, {}).get('nombre', tipo_trabajo)}!",
            description=f"Sigue así para aumentar tu bono diario.{texto_bono}",
            color=discord.Color.orange()
        )
        msg_racha = await interaction.followup.send(embed=embed_racha, wait=True)
        await asyncio.sleep(1.6)

    if evento is None:
        return

    if evento["tipo"] == "dorado":
        nombre_trabajo = TIPOS_TRABAJO.get(tipo_trabajo, {}).get("nombre", tipo_trabajo)
        gancho = FLAVOR_DORADO.get(tipo_trabajo, "Hoy es tu día de suerte.")
        embed_dorado = discord.Embed(
            title="🌟 ¡TURNO DORADO!",
            description=f"{gancho}\n\n💰 **Bono instantáneo:** +{evento['monto']} monedas antes de siquiera empezar.",
            color=discord.Color.gold()
        )
        embed_dorado.set_footer(text=f"Que no se te note el buen humor durante el turno de {nombre_trabajo}.")
        await interaction.followup.send(embed=embed_dorado)
        await asyncio.sleep(1.8)
        return

    # evento["tipo"] == "cliente"
    apodo, gancho = FLAVOR_CLIENTE.get(tipo_trabajo, ("🎭 Un cliente inesperado", "quiere hacer un trato contigo."))

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

    resultado = await asyncio.to_thread(_resolver_pago_cliente, user_id, tipo_trabajo, view.eleccion)

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


# Alias retrocompatible: los 11 trabajos ya integrados llaman a este nombre.
tal_vez_cliente_especial = fase_previa_trabajo
