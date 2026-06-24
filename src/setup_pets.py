import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.db import db_cursor, init_db

# Asegurarnos de que las tablas existan
init_db()

pets_data = [
    # Normales
    ("Ratón de Casino", "Normal", "🐭", "Roedor", "Curioso", "proc_universal", 0.04, 0.14, 120, "any", "volume", "auto", 0, 0.20, "Se alimenta de las monedas caídas en las ranuras."),
    ("Conejo de Cobre", "Normal", "🐰", "Mamífero", "Asustadizo", "multiplier", 1.02, 1.0, 0, "any", "hot_streak", "win_next_5", 1, 0.25, "Su pata de la suerte es más que un mito."),
    ("Buitre del Fondo", "Normal", "🦅", "Ave", "Oportunista", "proc_derrota", 0.06, 0.20, 180, "any", "cold_streak", "pay", 300, 0.15, "Solo aparece cuando hueles a desesperación."),

    # Raras
    ("Zorro de la Mesa Roja", "Rara", "🦊", "Mamífero", "Astuto", "proc_juego", 0.08, 0.15, 300, "coinflip", "specialized", "play_more", 3, 0.20, "Le encanta apostar a doble o nada."),
    ("Tortuga del Tesoro", "Rara", "🐢", "Reptil", "Conservador", "multiplier_safe", 1.03, 1.0, 0, "any", "wealth", "pay", 1500, 0.10, "Camina lento, pero su caparazón está forrado de oro."),
    ("Polilla de la Ruina", "Rara", "🦋", "Insecto", "Atraído por la luz", "proc_derrota", 0.10, 0.12, 500, "any", "cold_streak", "pay", 2000, 0.15, "Se alimenta del polvo de las billeteras vacías."),

    # Épicas
    ("Lobo del Streak", "Épica", "🐺", "Mamífero", "Depredador", "multiplier_scaling", 1.01, 1.0, 0, "any", "hot_streak", "keep_streak_or_pay", 4000, 0.18, "Un cazador implacable que huele la victoria."),
    ("Ballena Dorada", "Épica", "🐳", "Marino", "Codicioso", "proc_high_roller", 0.12, 0.12, 1500, "any", "wealth", "pay", 7500, 0.20, "Nada en mares de opulencia. Exige grandes apuestas."),
    ("Cuervo del Pacto", "Épica", "🐦‍⬛", "Ave", "Oscuro", "proc_universal", 0.09, 0.14, 900, "any", "ritual", "sacrifice", 0, 0.40, "Un trato en las sombras. No te quedes sin dinero..."),

    # Legendarias
    ("Dragón del Jackpot", "Legendaria", "🐉", "Mítico", "Orgulloso", "proc_juego_y_mult", 0.18, 0.10, 3000, "slots", "specialized", "pay", 15000, 0.15, "Custodia las máquinas tragamonedas más calientes."),
    ("Tiburón del Abismo", "Legendaria", "🦈", "Marino", "Agresivo", "proc_high_roller", 0.20, 0.08, 4000, "any", "volume", "pay", 12000, 0.25, "Huele el miedo y la codicia. Solo respeta a los arriesgados."),

    # Mítica
    ("Fénix de las Cenizas", "Mítica", "🔥", "Mítico", "Protector", "proc_derrota_y_revive", 0.25, 0.07, 5000, "any", "recovery", "pay_and_survive", 20000, 0.05, "Renace de la bancarrota absoluta.")
]

def seed_pets():
    with db_cursor() as cursor:
        # Verificar si ya están
        cursor.execute("SELECT COUNT(*) FROM PetsCatalog")
        count = cursor.fetchone()[0]
        if count == 0:
            query = """
                INSERT INTO PetsCatalog (
                    Name, Rarity, Emoji, Family, Temperament, EffectType, 
                    EffectValue, EffectChance, EffectCap, FavoriteGame, 
                    EncounterType, CaptureType, CaptureConfig, BaseLeaveChance, FlavorText
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            for pet in pets_data:
                cursor.execute(query, pet)
            print("✅ 12 Mascotas insertadas en PetsCatalog")
        else:
            print("⚠️ Las mascotas ya estaban insertadas.")

if __name__ == "__main__":
    seed_pets()
