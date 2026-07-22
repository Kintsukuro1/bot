# -*- coding: utf-8 -*-
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.db import db_cursor, init_db

init_db()

pets_data = [
    # --- NORMALES (10) ---
    ("Ratón de Casino", "Normal", "🐭", "Roedor", "Curioso", "proc_universal", 0.04, 0.14, 120, "any", "volume", "auto", 0, 0.20, "Se alimenta de las monedas caídas en las ranuras."),
    ("Conejo de Cobre", "Normal", "🐰", "Mamífero", "Asustadizo", "multiplier", 1.02, 1.0, 0, "any", "hot_streak", "win_next_5", 1, 0.25, "Su pata de la suerte es más que un mito."),
    ("Buitre del Fondo", "Normal", "🦅", "Ave", "Oportunista", "proc_derrota", 0.06, 0.20, 180, "any", "cold_streak", "pay", 300, 0.15, "Solo aparece cuando hueles a desesperación."),
    ("Gato de la Fortuna", "Normal", "🐱", "Felino", "Tranquilo", "multiplier", 1.03, 1.0, 0, "trabajo", "volume", "auto", 0, 0.20, "Mueve su pata atrayendo moneditas y buena fortuna."),
    ("Dron Chismoso", "Normal", "🛰️", "Tecnología", "Curioso", "proc_universal", 0.05, 0.10, 150, "robar", "volume", "auto", 0, 0.15, "Escanea saldos ajenos e informa de objetivos vulnerables."),
    ("Escarabajo Neón", "Normal", "🪲", "Insecto", "Brillante", "proc_universal", 0.03, 0.15, 100, "any", "volume", "auto", 0, 0.20, "Genera Balance continuo con la energía estática del casino."),
    ("Cuervo Transmisor", "Normal", "📡", "Tecnología", "Vigilante", "proc_universal", 0.04, 0.12, 130, "any", "volume", "auto", 0, 0.15, "Transmite alertas tempranas de movimientos sospechosos."),
    ("Abeja Obrera", "Normal", "🐝", "Insecto", "Trabajador", "multiplier", 1.05, 1.0, 0, "trabajo", "volume", "auto", 0, 0.20, "Aumenta la producción en todos los oficios manuales."),
    ("Pez Neón Flotante", "Normal", "🐠", "Marino", "Pacífico", "proc_universal", 0.04, 0.12, 140, "pesca", "volume", "auto", 0, 0.20, "Atrae especies de peces exóticos con su fulgor bioluminiscente."),
    ("Mapache Reciclador", "Normal", "🦝", "Mamífero", "Ingenioso", "proc_derrota", 0.10, 0.10, 200, "mines", "cold_streak", "auto", 0, 0.20, "Rebusca entre los restos para rescatar fichas perdidas."),

    # --- RARAS (15) ---
    ("Zorro de la Mesa Roja", "Rara", "🦊", "Mamífero", "Astuto", "proc_juego", 0.08, 0.15, 300, "coinflip", "specialized", "play_more", 3, 0.20, "Le encanta apostar a doble o nada."),
    ("Tortuga del Tesoro", "Rara", "🐢", "Piedra", "Conservador", "multiplier_safe", 1.03, 1.0, 0, "any", "wealth", "pay", 1500, 0.10, "Camina lento, pero su caparazón está forrado de oro."),
    ("Polilla de la Ruina", "Rara", "🦋", "Insecto", "Atraído por la luz", "proc_derrota", 0.10, 0.12, 500, "any", "cold_streak", "pay", 2000, 0.15, "Se alimenta del polvo de las billeteras vacías."),
    ("Búho Místico", "Rara", "🦉", "Ave", "Sabio", "proc_universal", 0.07, 0.15, 400, "any", "volume", "auto", 0, 0.15, "Sus ojos ven a través del destino y disipan debuffs."),
    ("Gólem de Obsidiana", "Rara", "🗿", "Piedra", "Resistente", "multiplier_safe", 1.04, 1.0, 0, "any", "wealth", "pay", 2500, 0.10, "Forjado en roca volcánica para absorber impactos y comisiones."),
    ("Ciber-Gato 9000", "Rara", "🤖", "Tecnología", "Calculador", "proc_juego", 0.10, 0.12, 350, "slots", "specialized", "auto", 0, 0.15, "Filtra algoritmos de las tragaperras para dar procs frecuentes."),
    ("Perro Biónico", "Rara", "🐕", "Tecnología", "Leal", "proc_universal", 0.06, 0.15, 300, "robar", "volume", "auto", 0, 0.15, "Guardián cibernético con sensor de presencia de ladrones."),
    ("Cerdito Gourmet", "Rara", "🐷", "Mamífero", "Glotón", "multiplier", 1.04, 1.0, 0, "any", "volume", "auto", 0, 0.15, "Potencia los efectos nutritivos de los consumibles."),
    ("Topo Minero", "Rara", "⛏️", "Roedor", "Trabajador", "proc_universal", 0.08, 0.12, 450, "mineria", "volume", "auto", 0, 0.15, "Excava túneles profundos en busca de gemas raras."),
    ("Sombra Errante", "Rara", "👻", "Sombra", "Furtivo", "proc_universal", 0.09, 0.14, 500, "robar", "specialized", "auto", 0, 0.15, "Se desliza inadvertida durante los asaltos nocturnos."),
    ("Murciélago Vampírico", "Rara", "🦇", "Mamífero", "Nocturno", "proc_universal", 0.08, 0.12, 400, "duelo", "volume", "auto", 0, 0.15, "Drena la energía del oponente en duelos de combate."),
    ("Salamandra de Fuego", "Rara", "🔥", "Reptil", "Ferviente", "proc_universal", 0.07, 0.15, 380, "any", "volume", "auto", 0, 0.15, "Resiste las llamas de las pérdidas continuas."),
    ("Medusa de Cristal", "Rara", "🪼", "Marino", "Reflejante", "proc_derrota", 0.12, 0.10, 600, "robar", "cold_streak", "auto", 0, 0.15, "Refleja los intentos de asalto con su veneno paralizante."),
    ("Panda Sabio", "Rara", "🐼", "Mamífero", "Pacífico", "multiplier_safe", 1.05, 1.0, 0, "any", "wealth", "auto", 0, 0.10, "Equilibra el chi financiero reduciendo multas bancarias."),
    ("Camaleón Ilusorio", "Rara", "🦎", "Reptil", "Evasivo", "proc_universal", 0.08, 0.14, 420, "any", "volume", "auto", 0, 0.15, "Se mimetiza con el saldo para engañar a los estafadores."),

    # --- ÉPICAS (12) ---
    ("Lobo del Streak", "Épica", "🐺", "Lobo", "Depredador", "multiplier_scaling", 1.01, 1.0, 0, "any", "hot_streak", "keep_streak_or_pay", 4000, 0.18, "Un cazador implacable que huele la victoria."),
    ("Ballena Dorada", "Épica", "🐳", "Marino", "Codicioso", "proc_high_roller", 0.12, 0.12, 1500, "any", "wealth", "pay", 7500, 0.20, "Nada en mares de opulencia. Exige grandes apuestas."),
    ("Cuervo del Pacto", "Épica", "🐦‍⬛", "Ave", "Oscuro", "proc_universal", 0.09, 0.14, 900, "any", "ritual", "sacrifice", 0, 0.40, "Un trato en las sombras. No te quedes sin dinero..."),
    ("Grifo de Tormenta", "Épica", "🦅", "Ave", "Imponente", "proc_universal", 0.11, 0.12, 1000, "raid", "volume", "auto", 0, 0.20, "Desata ráfagas de viento que aceleran el trabajo y aturden a los jefes."),
    ("Basilisco de Esmeralda", "Épica", "🐍", "Reptil", "Venenoso", "proc_derrota", 0.15, 0.10, 1200, "any", "cold_streak", "pay", 5000, 0.20, "Sombra petrificante que reduce el impacto de las pérdidas."),
    ("Mantícora de Sombras", "Épica", "🦂", "Sombra", "Agresivo", "proc_high_roller", 0.14, 0.10, 1300, "robar", "specialized", "pay", 6000, 0.20, "Afecta a sus presas con un veneno corrosivo e implacable."),
    ("Pegaso Rúnico", "Épica", "🐴", "Mítico", "Ágil", "multiplier", 1.08, 1.0, 0, "any", "hot_streak", "auto", 0, 0.15, "Galopa por los cielos recortando cooldowns de robos y batallas."),
    ("Pulpo Subterráneo", "Épica", "🐙", "Marino", "Astuto", "proc_juego", 0.14, 0.10, 1100, "crash", "specialized", "auto", 0, 0.20, "Especialista en hackear operaciones de bolsa y casino."),
    ("Búho Erudito", "Épica", "📜", "Ave", "Erudito", "multiplier", 1.10, 1.0, 0, "trabajo", "volume", "auto", 0, 0.15, "Guarda compendios de conocimiento que aceleran el nivel de oficio."),
    ("Espectro Codicioso", "Épica", "👹", "Sombra", "Desalmado", "proc_universal", 0.12, 0.12, 1400, "robar", "specialized", "auto", 0, 0.25, "Extrae fragmentos de fortuna adicional en cada atraco."),
    ("Íncubo de Furia", "Épica", "😈", "Furia", "Indomable", "proc_juego_y_mult", 0.15, 0.10, 1250, "blackjack", "specialized", "auto", 0, 0.20, "Alimenta su fuego interno con la tensión de las grandes apuestas."),
    ("Axolote Astral", "Épica", "🦎", "Mítico", "Místico", "proc_universal", 0.10, 0.15, 1150, "any", "volume", "auto", 0, 0.15, "Ser místico capaz de sanar la lealtad y vida de aliados."),

    # --- LEGENDARIAS (9) ---
    ("Dragón del Jackpot", "Legendaria", "🐉", "Furia", "Orgulloso", "proc_juego_y_mult", 0.18, 0.10, 3000, "slots", "specialized", "pay", 15000, 0.15, "Custodia las máquinas tragamonedas más calientes."),
    ("Tiburón del Abismo", "Legendaria", "🦈", "Marino", "Agresivo", "proc_high_roller", 0.20, 0.08, 4000, "any", "volume", "pay", 12000, 0.25, "Huele el miedo y la codicia. Solo respeta a los arriesgados."),
    ("Quimera Oscura", "Legendaria", "🦁", "Sombra", "Furtivo", "proc_universal", 0.15, 0.10, 3500, "robar", "specialized", "pay", 14000, 0.20, "Acecha en la penumbra para garantizar golpes limpios."),
    ("Kirin del Firmamento", "Legendaria", "🦄", "Mítico", "Noble", "multiplier", 1.12, 1.0, 0, "any", "hot_streak", "pay", 16000, 0.10, "Bestia sagrada que restaura la lealtad de la party y otorga bendición."),
    ("Behemoth de Piedra", "Legendaria", "🦣", "Piedra", "Colosal", "multiplier_safe", 1.10, 1.0, 0, "any", "wealth", "pay", 18000, 0.10, "Coloso legendario que protege grandes fortunas ante asaltos."),
    ("Kraken del Abismo", "Legendaria", "🦑", "Marino", "Monstruoso", "proc_juego", 0.22, 0.08, 4500, "crash", "specialized", "pay", 17000, 0.20, "Gigante de las profundidades que atrapa grandes multiplicadores."),
    ("Cerbero del Infierno", "Legendaria", "🐕‍🦺", "Furia", "Feroz", "proc_universal", 0.18, 0.10, 3800, "robar", "specialized", "pay", 15500, 0.20, "Tres cabezas que velan por tu saldo e imponen quemadura en Raids."),
    ("Zorro del Firmamento", "Legendaria", "🦊", "Mítico", "Celestial", "proc_universal", 0.16, 0.12, 3200, "loteria", "volume", "pay", 14500, 0.15, "Nueve colas de luz que manipulan la probabilidad del destino."),
    ("Oso del Helero", "Legendaria", "🧊", "Gólem", "Implacable", "multiplier_safe", 1.08, 1.0, 0, "raid", "wealth", "pay", 13500, 0.15, "Guardián de hielo que congela jefes y mantiene la estabilidad."),

    # --- MÍTICAS (4) ---
    ("Fénix de las Cenizas", "Mítica", "🔥", "Fénix", "Protector", "proc_derrota_y_revive", 0.25, 0.07, 5000, "any", "recovery", "pay_and_survive", 20000, 0.05, "Renace de la bancarrota absoluta."),
    ("Hidra de Siete Cabezas", "Mítica", "🐍", "Furia", "Insaciable", "proc_derrota", 0.30, 0.06, 6000, "any", "cold_streak", "pay_and_survive", 25000, 0.05, "Cada cabeza que cae resurge con un ataque feroz e incesante."),
    ("Dragón Estelar", "Mítica", "🌟", "Mítico", "Cosmico", "multiplier", 1.20, 1.0, 0, "any", "wealth", "pay_and_survive", 30000, 0.05, "Entidad astral que altera la realidad financiera de toda la economía."),
    ("Llama Sagrada", "Mítica", "🦙", "Mítico", "Divino", "proc_universal", 0.25, 0.08, 5500, "any", "ritual", "pay_and_survive", 22000, 0.05, "Ser divino que concede bonificaciones astronómicas y protección total.")
]

def reseed_pets():
    print("Reseeding pets catalog with 50 pets...")
    with db_cursor() as cursor:
        cursor.connection.set_client_encoding('UTF8')
        
        query = """
            INSERT INTO PetsCatalog (
                Name, Rarity, Emoji, Family, Temperament, EffectType, 
                EffectValue, EffectChance, EffectCap, FavoriteGame, 
                EncounterType, CaptureType, CaptureConfig, BaseLeaveChance, FlavorText
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        inserted_count = 0
        for pet in pets_data:
            cursor.execute("SELECT 1 FROM PetsCatalog WHERE Name = %s", (pet[0],))
            if not cursor.fetchone():
                cursor.execute(query, pet)
                inserted_count += 1
            
        print(f"OK: {inserted_count} Mascotas agregadas / 50 listas en PetsCatalog!")

if __name__ == "__main__":
    reseed_pets()
