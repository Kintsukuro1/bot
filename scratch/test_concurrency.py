import asyncio
import sys
import os

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import db_cursor, ensure_user, get_balance
from src.services.economy_service import EconomyService
from src.services.bank_service import BankService

async def run_concurrent_transfers():
    print("--- Probando Transferencias Concurrentes ---")
    user_a = 999111
    user_b = 999222
    
    # 1. Asegurar usuarios y setear balance
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM Users WHERE UserID IN (%s, %s)", (user_a, user_b))
    
    await asyncio.to_thread(ensure_user, user_a, "UserA")
    await asyncio.to_thread(ensure_user, user_b, "UserB")
    
    # Set balance of User A to 1500 coins
    with db_cursor() as cursor:
        cursor.execute("UPDATE Users SET Balance = 1500 WHERE UserID = %s", (user_a,))
        cursor.execute("UPDATE Users SET Balance = 0 WHERE UserID = %s", (user_b,))
    
    print(f"Saldo inicial User A: {await asyncio.to_thread(get_balance, user_a)}")
    print(f"Saldo inicial User B: {await asyncio.to_thread(get_balance, user_b)}")
    
    # Intentar transferir 1000 monedas dos veces simultáneamente.
    # Solo una de las transferencias debe tener éxito (porque el saldo es 1500).
    print("Enviando dos transferencias concurrentes de 1000 monedas...")
    tasks = [
        EconomyService.transfer_balance(user_a, user_b, 1000, "Trf 1"),
        EconomyService.transfer_balance(user_a, user_b, 1000, "Trf 2")
    ]
    
    results = await asyncio.gather(*tasks)
    
    print(f"Resultados de transferencias: {results}")
    
    final_a = await asyncio.to_thread(get_balance, user_a)
    final_b = await asyncio.to_thread(get_balance, user_b)
    print(f"Saldo final User A: {final_a}")
    print(f"Saldo final User B: {final_b}")
    
    # Una debe ser True y la otra False
    success_count = sum(1 for r in results if r[0] is True)
    if success_count == 1:
        print("[OK] Exito: Solo una transferencia se completó, previniendo sobregiro.")
    else:
        print("[ERROR] Fallo: Se procesaron incorrectamente", success_count, "transferencias.")

async def run_concurrent_loans():
    print("\n--- Probando Préstamos Concurrentes ---")
    user_c = 999333
    
    # Limpiar préstamos previos
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM UserLoans WHERE UserID = %s", (user_c,))
        cursor.execute("DELETE FROM Users WHERE UserID = %s", (user_c,))
    
    await asyncio.to_thread(ensure_user, user_c, "UserC")
    
    # Set user balance to 0 and ensure bank reserves have enough money
    with db_cursor() as cursor:
        cursor.execute("UPDATE Users SET Balance = 0 WHERE UserID = %s", (user_c,))
        cursor.execute("UPDATE BancoCentral SET Reservas = 100000 WHERE ID = 1")
    
    # Solicitar dos préstamos de 10,000 simultáneamente
    print("Solicitando dos préstamos concurrentes de 10,000 monedas...")
    tasks = [
        BankService.request_loan(user_c, 10000),
        BankService.request_loan(user_c, 10000)
    ]
    
    results = await asyncio.gather(*tasks)
    results_safe = [(r[0], r[1].encode('ascii', errors='replace').decode('ascii')) for r in results]
    print(f"Resultados de préstamos: {results_safe}")
    
    # Solo uno debe ser exitoso porque prestige 0 solo permite 1 préstamo activo (Slot 1)
    success_count = sum(1 for r in results if r[0] is True)
    if success_count == 1:
        print("[OK] Exito: Solo un préstamo fue aprobado, previniendo duplicación concurrente de slots.")
    else:
        print("[ERROR] Fallo: Se aprobaron concurrentemente", success_count, "préstamos.")

    # Limpiar datos de prueba
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM UserLoans WHERE UserID = %s", (user_c,))
        cursor.execute("DELETE FROM Users WHERE UserID IN (999111, 999222, 999333)")

async def main():
    try:
        await run_concurrent_transfers()
        await run_concurrent_loans()
    except Exception as e:
        print(f"Error durante la ejecución del test: {e}")
        print("Asegúrate de que la base de datos PostgreSQL local esté iniciada y accesible con la configuración de .env.")

if __name__ == '__main__':
    asyncio.run(main())
