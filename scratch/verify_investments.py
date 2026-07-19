import sys
import os
import asyncio
from datetime import datetime, timedelta

# Configure UTF-8 encoding for standard output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import (
    init_db,
    db_cursor,
    get_balance,
    add_balance,
    start_investment_db,
    resolve_matured_investments_db,
    get_active_investment_db
)

def verify_investments():
    print("Initializing DB schema...")
    init_db()
    
    test_user_id = 999999888
    
    # 1. Prepare user balance
    with db_cursor() as cursor:
        cursor.execute("INSERT INTO Users (UserID, Balance) VALUES (%s, 0) ON CONFLICT (UserID) DO UPDATE SET Balance = 0", (test_user_id,))
    
    print(f"Adding 50,000 coins to test user {test_user_id}...")
    add_balance(test_user_id, 50000)
    bal = get_balance(test_user_id)
    print(f"Initial Balance: {bal:,} coins")
    
    # 2. Check no active investments
    inv = get_active_investment_db(test_user_id)
    print(f"Active investment (should be None): {inv}")
    
    # 3. Start investment
    print("Starting investment of 10,000 coins...")
    success, msg = start_investment_db(test_user_id, 10000)
    print(f"Start investment success? {success} | Message: {msg}")
    
    bal_after_inv = get_balance(test_user_id)
    print(f"Balance after investment: {bal_after_inv:,} coins")
    
    inv = get_active_investment_db(test_user_id)
    print(f"Active investment details: {inv}")
    
    # 4. Force maturity by setting FechaVencimiento 10 days ago
    print("Forcing investment maturity (setting FechaVencimiento to 10 days ago)...")
    past_date = datetime.now() - timedelta(days=10)
    with db_cursor() as cursor:
        cursor.execute(
            "UPDATE UserInvestments SET FechaVencimiento = %s WHERE UserID = %s",
            (past_date, test_user_id)
        )
        
    # Check that the dates are updated
    inv = get_active_investment_db(test_user_id)
    print(f"Active investment details after date shift: {inv}")
    
    # 5. Resolve matured investments
    print("Resolving matured investments...")
    res = resolve_matured_investments_db()
    print(f"Resolution outcome: {res}")
    
    # 6. Verify new balance and status
    bal_after_res = get_balance(test_user_id)
    print(f"Balance after resolution: {bal_after_res:,} coins")
    
    inv_final = get_active_investment_db(test_user_id)
    print(f"Active investment after resolution (should be None): {inv_final}")
    
    with db_cursor() as cursor:
        cursor.execute("SELECT Resuelto, Monto FROM UserInvestments WHERE UserID = %s", (test_user_id,))
        row = cursor.fetchone()
        print(f"Investment record in DB: Resuelto={row[0]} | Monto={row[1]}")
        
        # Check transaction history
        cursor.execute("SELECT Amount, TransactionType FROM Transactions WHERE UserID = %s ORDER BY Date DESC LIMIT 2", (test_user_id,))
        rows = cursor.fetchall()
        print("Last two transactions:")
        for r in rows:
            print(f"  Amount: {r[0]:,} | Type: {r[1]}")

    # Clean up test user
    print("Cleaning up test records...")
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM UserInvestments WHERE UserID = %s", (test_user_id,))
        cursor.execute("DELETE FROM Transactions WHERE UserID = %s", (test_user_id,))
        cursor.execute("DELETE FROM Users WHERE UserID = %s", (test_user_id,))
    print("Verification completed successfully!")

if __name__ == "__main__":
    verify_investments()
