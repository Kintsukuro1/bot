import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from src.db import (
    get_balance, set_balance, ensure_user, registrar_transaccion, 
    agregar_item_usuario, usuario_tiene_item, get_user_items
)

TIENDA = [
    {"id": 1, "nombre": "Rol personalizado (7 días)", "precio": 2000, "descripcion": "Crea un rol con el nombre y color que quieras por 7 días.", "caracteristica": "neutral"},
    {"id": 2, "nombre": "Color de nombre personalizado (7 días)", "precio": 1000, "descripcion": "Elige un color para tu nombre por 7 días.", "caracteristica": "neutral"},
    {"id": 4, "nombre": "Ticket de suerte (doble premio en slots)", "precio": 1500, "descripcion": "Duplica tu premio si ganas en slots (1 uso).", "caracteristica": "positiva"},
    {"id": 11, "nombre": "Special Mute", "precio": 800, "descripcion": "Usa el comando /specialmute una vez. Solo permite tiempos de 5, 10 o 30 min y no puedes mutear al mismo usuario más de una vez al día.", "caracteristica": "neutral"},
    {"id": 12, "nombre": "Multiplicador x2 (1 hora)", "precio": 3000, "descripcion": "Duplica todas tus ganancias de casino por 1 hora.", "caracteristica": "positiva"},
]

class Tienda(commands.Cog):
    """Cog para la tienda de artículos temporales."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tienda", description="Muestra los artículos disponibles para comprar.")
    async def tienda(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 Tienda de premios",
            description="¡Compra artículos únicos para personalizar tu experiencia!",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/263/263142.png")
        for item in TIENDA:
            embed.add_field(
                name=f"{item['nombre']} — {item['precio']} 🪙",
                value=f"`ID:` `{item['id']}`\n{item['descripcion']}",
                inline=False
            )
        embed.set_footer(text="Usa /comprar <ID> para adquirir un artículo.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="inventario", description="Muestra los artículos que posees")
    async def inventario(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_name = interaction.user.name
        ensure_user(user_id, user_name)
        
        # Obtener inventario del usuario
        items = get_user_items(user_id)
        
        embed = discord.Embed(
            title="🎒 Tu Inventario",
            description="Artículos que posees actualmente:",
            color=discord.Color.blue()
        )
        
        if not items:
            embed.description = "No tienes ningún artículo en tu inventario."
        else:
            for user_item in items:
                item_id = user_item['item_id']
                item_info = next((i for i in TIENDA if i["id"] == item_id), None)
                
                if item_info:
                    nombre = item_info['nombre']
                    expiry_text = ""
                    if user_item['expiry']:
                        expiry_date = user_item['expiry']
                        if isinstance(expiry_date, str):
                            try:
                                # Intentar convertir si viene como string
                                expiry_date = datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S")
                            except ValueError:
                                expiry_date = None
                        
                        if expiry_date:
                            days_left = (expiry_date - datetime.now()).days
                            expiry_text = f" (Caduca en {days_left} días)"
                    
                    embed.add_field(
                        name=f"{nombre}{expiry_text}",
                        value=f"Cantidad: {user_item['quantity']}",
                        inline=False
                    )
        
        embed.set_footer(text="Usa estos artículos en los comandos correspondientes.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="comprar", description="Compra un artículo de la tienda por su ID.")
    @app_commands.describe(articulo_id="ID del artículo a comprar")
    async def comprar(self, interaction: discord.Interaction, articulo_id: int):
        user_id = interaction.user.id
        user_name = interaction.user.name
        ensure_user(user_id, user_name)
        balance = get_balance(user_id)
        item = next((i for i in TIENDA if i["id"] == articulo_id), None)
        
        if not item:
            await interaction.response.send_message("❌ Artículo no encontrado.", ephemeral=True)
            return
            
        if balance < item["precio"]:
            await interaction.response.send_message("❌ No tienes suficiente saldo para comprar este artículo.", ephemeral=True)
            return
        
        # Cobrar al usuario
        set_balance(user_id, balance - item["precio"])
        registrar_transaccion(user_id, -item["precio"], f"Compra tienda: {item['nombre']}")
        
        # Calcular fecha de expiración si es necesario
        expiry_date = None
        if "7 días" in item["nombre"]:
            expiry_date = datetime.now() + timedelta(days=7)
        elif "1 hora" in item["nombre"]:
            expiry_date = datetime.now() + timedelta(hours=1)
        
        # Agregar el artículo al inventario del usuario
        success = agregar_item_usuario(user_id, item["id"], quantity=1, expiry=expiry_date)
        
        if not success:
            # Si falla, reembolsar al usuario
            set_balance(user_id, balance)
            await interaction.response.send_message("❌ Error al agregar el artículo a tu inventario. Tu dinero ha sido reembolsado.", ephemeral=True)
            return
        
        # Lógica personalizada por ítem para mensajes
        if item["id"] == 1:
            msg = "¡Has comprado un rol personalizado! Contacta a un admin para configurarlo."
        elif item["id"] == 2:
            msg = "¡Has comprado un color personalizado! Contacta a un admin para configurarlo."
        elif item["id"] == 4:
            msg = "¡Has comprado un ticket de suerte! Tu próximo premio en slots se duplicará."
        elif item["id"] == 11:
            msg = "¡Has comprado un Special Mute! Puedes usar /specialmute una vez para mutear a otro usuario por 5, 10 o 30 minutos (aleatorio). No puedes mutear al mismo usuario más de una vez al día."
        elif item["id"] == 12:
            msg = "¡Has comprado un multiplicador x2! Tus ganancias de casino se duplicarán por 1 hora."
        else:
            msg = "¡Compra realizada!"
            
        # Información sobre la expiración
        if expiry_date:
            expiry_text = expiry_date.strftime("%d/%m/%Y a las %H:%M")
            msg += f"\n\nEste artículo caducará el {expiry_text}."
        
        embed = discord.Embed(
            title="✅ Compra exitosa",
            description=msg,
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Inventario", 
            value="Puedes revisar tus artículos usando `/inventario`",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Helper para crear ítems estándar
def crear_item(id, nombre, precio, descripcion, caracteristica):
    """
    Crea un diccionario de ítem con formato estándar.
    caracteristica: 'positiva', 'negativa' o 'neutral'
    """
    return {
        "id": id,
        "nombre": nombre,
        "precio": precio,
        "descripcion": descripcion,
        "caracteristica": caracteristica
    }

async def setup(bot):
    await bot.add_cog(Tienda(bot))
    print("Tienda cog loaded successfully.")
