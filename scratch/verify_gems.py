import sys
import os
import asyncio
from unittest.mock import MagicMock

# Configure UTF-8 encoding for standard output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import (
    init_db, get_user_equipment, equip_item, get_gem_catalog,
    insert_gem, remove_gem, get_combat_wallet, add_combat_currency
)
from src.commands.duels.duelo import Combatant
from src.utils.combat_progression import format_currency, calc_base_stats

def test_gems():
    print("Initializing database...")
    init_db()

    # Retrieve catalog
    print("\nFetching gem catalog...")
    catalog = get_gem_catalog()
    print(f"Total gems in catalog: {len(catalog)}")
    for g in catalog[:3]: # show first 3
        val_str = f"+{g['bonus_value']}" if not g['is_percentage'] else f"+{g['bonus_value']*100}%"
        print(f"- {g['name']} ({val_str}) costs {format_currency(g['price'])}")

    test_user_id = 999999888
    
    # Reset user's equipment and wallet
    print("\nResetting user's equipment and wallet...")
    with sys.modules['src.db'].db_cursor() as cursor:
        cursor.execute("DELETE FROM UserEquipment WHERE UserID = %s", (test_user_id,))
        cursor.execute("DELETE FROM CombatWallet WHERE UserID = %s", (test_user_id,))

    # Give wallet balance
    add_combat_currency(test_user_id, 20000)
    print(f"Initial wallet: {format_currency(get_combat_wallet(test_user_id))}")

    # Equip some items
    print("Equipping test gear...")
    equip_item(test_user_id, 'Cabeza', 'Casco de Hierro', 'Común', 10, 'hp', 15)
    equip_item(test_user_id, 'Arma', 'Espada del Destino', 'Épico', 20, 'atk', 50)

    # 1. Verification of inserting a gem
    print("\nInserting Gema de Vida (Menor) (hp +3, price 300) into Cabeza...")
    success, msg = insert_gem(test_user_id, 'Cabeza', 'gema_menor_vida')
    print(f"Insert success: {success} | Message: {msg}")

    equipment = get_user_equipment(test_user_id)
    print(f"Cabeza equipment info: {equipment.get('Cabeza')}")

    # Create combatant to verify HP bonus
    mock_user = MagicMock()
    mock_user.id = test_user_id
    mock_user.display_name = "TestCombatant"
    
    c = Combatant(mock_user, level=10, equipment=equipment)
    base_hp = calc_base_stats(10)['hp']
    print(f"Combatant HP (Level 10): {c.hp} / Max HP: {c.max_hp} (Base HP: {base_hp}, expected HP: {base_hp + 15 + 3})")

    # 2. Verification of percentage gem & capping
    print("\nInserting Gema de Agilidad (Mayor) (dodge +2%, price 1600) into Arma...")
    success, msg = insert_gem(test_user_id, 'Arma', 'gema_mayor_agilidad')
    print(f"Insert success: {success} | Message: {msg}")

    equipment = get_user_equipment(test_user_id)
    c2 = Combatant(mock_user, level=10, equipment=equipment)
    print(f"Combatant Evasion Bonus (No subclass): {c2.subclass_extras.get('dodge_chance_bonus', 0.0)}")

    # 3. Verification of removing a gem (paying 50% cost)
    print("\nRemoving Gema de Vida (Menor) from Cabeza...")
    # Expected cost is 300 / 2 = 150
    success, msg = remove_gem(test_user_id, 'Cabeza')
    print(f"Remove success: {success} | Message: {msg}")

    equipment_after = get_user_equipment(test_user_id)
    print(f"Cabeza equipment after removal: {equipment_after.get('Cabeza')}")

    # Check wallet balance
    # Started with 20000. Spent 300 (Gema Vida Menor) + 1600 (Gema Agilidad Mayor) + 150 (Removal) = 2050
    # Remaining should be 17950
    final_wallet = get_combat_wallet(test_user_id)
    print(f"Final wallet: {format_currency(final_wallet)} (Raw: {final_wallet}, expected: 17950)")

if __name__ == "__main__":
    test_gems()
