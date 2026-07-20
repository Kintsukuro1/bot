import os
import sys

# Asegurar que la raíz del proyecto esté en el path de Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import db_cursor

def reset_economy():
    print("🔄 Iniciando el reinicio completo de la economía y stats...")
    
    # Mapeo de operaciones a realizar
    operations = [
        ("Establecer balance de 100k para todos los usuarios", "UPDATE Users SET Balance = 100000, BankBalance = 0;"),
        ("Eliminar préstamos activos (Banco)", "DELETE FROM UserLoans;"),
        ("Reiniciar reservas del Banco Central", "UPDATE BancoCentral SET Reservas = 0;"),
        ("Eliminar inversiones activas (Plazo fijo)", "DELETE FROM UserInvestments;"),
        ("Eliminar portafolio de bolsa de valores", "DELETE FROM UserPortfolio;"),
        ("Eliminar boletos de lotería comprados", "DELETE FROM LotteryTickets;"),
        ("Reiniciar pozo acumulado y fechas del loto", "UPDATE LotteryState SET JackpotPool = 10000, LastDrawDate = NULL, NextDrawDate = NULL;"),
        ("Limpiar todos los objetos del inventario estándar", "DELETE FROM UserItems;"),
        ("Limpiar todos los consumibles de combate", "DELETE FROM UserConsumables;"),
        ("Limpiar todo el equipamiento de combate", "DELETE FROM UserEquipment;"),
        ("Reiniciar todos los niveles y progreso de trabajos", "DELETE FROM joblevels;"),
        ("Reiniciar todos los niveles y estadísticas de robo", "DELETE FROM RoboStats;"),
        ("Limpiar el historial de transacciones (opcional)", "DELETE FROM Transactions;")
    ]
    
    try:
        with db_cursor() as cursor:
            for desc, query in operations:
                print(f"Executing: {desc}...")
                cursor.execute(query)
        print("\n✅ ¡Reinicio de economía y estadísticas completado con éxito!")
    except Exception as e:
        print(f"\n❌ Error durante el reinicio: {e}")

if __name__ == "__main__":
    # Mensaje de confirmación de seguridad
    confirm = input("⚠️ ¿Estás seguro de que deseas reiniciar la economía? Esto no se puede deshacer. (s/n): ")
    if confirm.lower() == 's':
        reset_economy()
    else:
        print("❌ Operación cancelada por el usuario.")
