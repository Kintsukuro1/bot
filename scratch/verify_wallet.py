import sys
import os

# Configure UTF-8 encoding for standard output to avoid UnicodeEncodeError in Windows terminal
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import init_db, get_combat_wallet, add_combat_currency, spend_combat_currency
from src.utils.combat_progression import format_currency

def test_wallet():
    # Initialize DB (which will create the CombatWallet table if it doesn't exist)
    print("Initializing database...")
    init_db()
    
    test_user_id = 999999888
    
    # 1. Check initial balance
    balance = get_combat_wallet(test_user_id)
    print(f"Initial balance for {test_user_id}: {balance} ({format_currency(balance)})")
    
    # 2. Add currency
    print("Adding 10500 Bronze...")
    add_combat_currency(test_user_id, 10500)
    balance = get_combat_wallet(test_user_id)
    print(f"New balance: {balance} ({format_currency(balance)})")
    
    # 3. Spend currency (success case)
    print("Spending 500 Bronze...")
    success, new_balance = spend_combat_currency(test_user_id, 500)
    print(f"Spend success? {success}, New balance: {new_balance} ({format_currency(new_balance)})")
    
    # 4. Spend currency (insufficient balance case)
    print("Trying to spend 20000 Bronze...")
    success, current_balance = spend_combat_currency(test_user_id, 20000)
    print(f"Spend success? {success}, Current balance: {current_balance} ({format_currency(current_balance)})")
    
    # 5. Clean up (subtract balance to return to initial or 0)
    print("Resetting balance by subtracting remaining...")
    add_combat_currency(test_user_id, -current_balance)
    final_balance = get_combat_wallet(test_user_id)
    print(f"Final balance: {final_balance} ({format_currency(final_balance)})")
    
    # test format_currency cases
    print("\nTesting format_currency:")
    print(f"35 -> {format_currency(35)}")
    print(f"210 -> {format_currency(210)}")
    print(f"10425 -> {format_currency(10425)}")
    print(f"0 -> {format_currency(0)}")

if __name__ == "__main__":
    test_wallet()
