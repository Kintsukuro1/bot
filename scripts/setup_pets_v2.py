import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.db import db_cursor

pets_data = [
    ("Maneki-neko", "Rara", "🐱", "Felino", "Suertudo", "multiplier", 1.10, 0.1, "hot_streak", "Gato de la fortuna"),
    ("Cuervo de la Ruina", "Épica", "🐦‍⬛", "Ave", "Oscuro", "refund", 0.15, 0.1, "cold_streak", "Ave del infortunio"),
    ("Perro Sabueso", "Normal", "🐕", "Canino", "Fiel", "energy_reduction", 0.95, 0.05, "volume", "El mejor amigo del hombre")
]

def seed_pets():
    with db_cursor() as cursor:
        cursor.execute("TRUNCATE TABLE PetsCatalog CASCADE")
        cursor.execute("TRUNCATE TABLE UserPets CASCADE")
        
        query = """
            INSERT INTO PetsCatalog (
                Name, Rarity, Emoji, Family, Temperament, EffectType, 
                EffectValue, EffectChance, EncounterType, FlavorText
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        for pet in pets_data:
            cursor.execute(query, pet)
        print("✅ 3 Mascotas (V2) insertadas en PetsCatalog")

if __name__ == "__main__":
    seed_pets()
