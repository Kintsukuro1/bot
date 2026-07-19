import sys
import os
import asyncio
import math
from datetime import datetime, time

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
    deduct_balance,
    ensure_user
)
from src.services.market_service import MarketService, MARKET_ASSETS
from src.utils.economy_config import TRANSACTION_TAX

async def verify_bolsa():
    print("=== STARTING BOLSA SIMULADA VERIFICATION ===")
    
    # 1. Initialize DB and run migrations
    print("\n1. Initializing DB schema and migrations...")
    init_db()
    
    # Verify tables exist
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'marketassets'
            )
        """)
        assets_exist = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'marketpricehistory'
            )
        """)
        history_exist = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'userportfolio'
            )
        """)
        portfolio_exist = cursor.fetchone()[0]
        
        print(f"Table 'MarketAssets' exists? {assets_exist}")
        print(f"Table 'MarketPriceHistory' exists? {history_exist}")
        print(f"Table 'UserPortfolio' exists? {portfolio_exist}")
        
        if not (assets_exist and history_exist and portfolio_exist):
            print("ERROR: Migrations failed to create tables.")
            return

        # Check default assets populated
        cursor.execute("SELECT AssetKey, PrecioActual FROM MarketAssets ORDER BY AssetKey ASC")
        rows = cursor.fetchall()
        print(f"MarketAssets entries in DB (total {len(rows)}):")
        for r in rows:
            print(f"  - {r[0]}: {float(r[1]):.2f}")
            
    # 2. MarketService Loading and Ticking
    print("\n2. Loading prices from DB to memory...")
    MarketService.load_prices_from_db()
    print("Initial cached prices in memory:")
    initial_prices = MarketService.get_all_prices()
    for k, p in initial_prices.items():
        print(f"  - {k}: {p:.4f}")
        
    print("\nSimulating 5 ticks (Geometric Brownian Motion)...")
    for i in range(1, 6):
        MarketService.tick()
        t_prices = MarketService.get_all_prices()
        print(f"Tick {i} prices:")
        for k, p in t_prices.items():
            diff_pct = ((p - initial_prices[k]) / initial_prices[k]) * 100
            print(f"  - {k}: {p:.4f} ({diff_pct:+.4f}%)")
            
    print("\n3. Persisting prices and writing price history...")
    MarketService.persist_prices()
    
    with db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM MarketPriceHistory")
        hist_count = cursor.fetchone()[0]
        print(f"Total entries in MarketPriceHistory: {hist_count}")
        
        cursor.execute("SELECT AssetKey, Precio, Timestamp FROM MarketPriceHistory ORDER BY ID DESC LIMIT 6")
        history_rows = cursor.fetchall()
        print("Last 6 history entries added:")
        for hr in history_rows:
            print(f"  - {hr[0]}: price={float(hr[1]):.2f} at {hr[2]}")

    # 4. User transactions and portfolios
    print("\n4. Performing User Transactions (Buy/Sell/Portfolio/Tax)...")
    test_user_id = 888888777
    
    # Prepare test user balance
    with db_cursor() as cursor:
        cursor.execute("INSERT INTO Users (UserID, UserName, Balance) VALUES (%s, 'Test Bolsa User', 0) ON CONFLICT (UserID) DO UPDATE SET Balance = 0", (test_user_id,))
    
    add_balance(test_user_id, 10000)
    print(f"Test User ID: {test_user_id} | Balance: {get_balance(test_user_id):,}")
    
    # Buy AgroUnion for 5000 coins
    monto_gasto = 5000
    tax_pct = TRANSACTION_TAX.get("bolsa", 0.015)
    monto_neto = monto_gasto * (1 - tax_pct)
    impuesto = monto_gasto - monto_neto
    
    price_before = MarketService.get_price("agrounion")
    qty_purchased = monto_neto / price_before
    
    print(f"\nBuying 'agrounion' for {monto_gasto:,} coins...")
    print(f"Tax: {impuesto:,} coins (1.5%) | Net investment: {monto_neto:,} coins")
    print(f"Price before: {price_before:.4f} | Units to acquire: {qty_purchased:.6f}")
    
    success, bal_after = deduct_balance(test_user_id, monto_gasto)
    if success:
        # Add to portfolio
        with db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO UserPortfolio (UserID, AssetKey, Cantidad, CostoPromedio)
                VALUES (%s, 'agrounion', %s, %s)
            """, (test_user_id, qty_purchased, price_before))
            print(f"Balance after buy: {bal_after:,}")
            
        # Large impact trigger
        MarketService.apply_large_operation_impact("agrounion", qty_purchased, is_buy=True)
    else:
        print("ERROR: Balance deduction failed!")
        return

    # Check Portfolio
    with db_cursor() as cursor:
        cursor.execute("SELECT Cantidad, CostoPromedio FROM UserPortfolio WHERE UserID = %s AND AssetKey = 'agrounion'", (test_user_id,))
        p_row = cursor.fetchone()
        if p_row:
            qty = float(p_row[0])
            cost = float(p_row[1])
            print(f"\nUser Portfolio details: Quantity={qty:.6f} | Average Cost={cost:.4f}")
            
    # Sell half of the units
    sell_qty = qty_purchased / 2.0
    price_sell = MarketService.get_price("agrounion")
    gross_proceeds = sell_qty * price_sell
    tax_sell = gross_proceeds * tax_pct
    net_proceeds = gross_proceeds - tax_sell
    net_proceeds_int = int(net_proceeds)
    
    print(f"\nSelling {sell_qty:.6f} units of 'agrounion' at current price {price_sell:.4f}...")
    print(f"Gross: {gross_proceeds:.2f} | Tax: {tax_sell:.2f} | Net Proceeds: {net_proceeds_int:,}")
    
    with db_cursor() as cursor:
        cursor.execute("SELECT Cantidad, CostoPromedio FROM UserPortfolio WHERE UserID = %s AND AssetKey = 'agrounion' FOR UPDATE", (test_user_id,))
        row = cursor.fetchone()
        current_qty = float(row[0])
        new_qty = current_qty - sell_qty
        cursor.execute("UPDATE UserPortfolio SET Cantidad = %s WHERE UserID = %s AND AssetKey = 'agrounion'", (new_qty, test_user_id))
        add_balance(test_user_id, net_proceeds_int)
        print(f"Portfolio updated: new quantity = {new_qty:.6f}")
        print(f"New Balance: {get_balance(test_user_id):,}")
        
    MarketService.apply_large_operation_impact("agrounion", sell_qty, is_buy=False)

    # 5. Verify Daily Dividend logic calculations
    print("\n5. Testing Daily Dividend distribution logic...")
    # Add obsidianchain to portfolio (non-dividend payer) and tecnocorp (dividend payer)
    with db_cursor() as cursor:
        cursor.execute("INSERT INTO UserPortfolio (UserID, AssetKey, Cantidad, CostoPromedio) VALUES (%s, 'tecnocorp', 10.0, 80.0)", (test_user_id,))
        cursor.execute("INSERT INTO UserPortfolio (UserID, AssetKey, Cantidad, CostoPromedio) VALUES (%s, 'obsidianchain', 5.0, 50.0)", (test_user_id,))
    
    # Read active portfolios that pay dividends
    dividend_assets = {k: v for k, v in MARKET_ASSETS.items() if v["dividendo_pct"] > 0}
    print(f"Dividend Assets: {list(dividend_assets.keys())}")
    
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT UserID, AssetKey, Cantidad 
            FROM UserPortfolio 
            WHERE Cantidad > 0 AND UserID = %s AND AssetKey IN %s
        """, (test_user_id, tuple(dividend_assets.keys())))
        div_rows = cursor.fetchall()
        
        print("Portfolio entries matching dividend payers:")
        for dr in div_rows:
            uid, a_key, qty = dr[0], dr[1], float(dr[2])
            price = MarketService.get_price(a_key)
            pct = dividend_assets[a_key]["dividendo_pct"]
            div_val = qty * price * pct
            print(f"  - User: {uid} | Asset: {a_key} | Qty: {qty} | Price: {price:.2f} | Pct: {pct*100:.1f}% | Estimated Dividend: {div_val:.2f} ({int(div_val)} coins)")

    # 6. Cleaning up test records
    print("\n6. Cleaning up test records from database...")
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM UserPortfolio WHERE UserID = %s", (test_user_id,))
        cursor.execute("DELETE FROM Users WHERE UserID = %s", (test_user_id,))
        cursor.execute("DELETE FROM MarketPriceHistory WHERE AssetKey IN ('agrounion', 'tecnocorp')")
        cursor.execute("DELETE FROM Transactions WHERE UserID = %s", (test_user_id,))
    print("Cleanup complete!")
    print("\n=== BOLSA SIMULADA VERIFICATION COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(verify_bolsa())
