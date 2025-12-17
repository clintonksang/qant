import csv
import time
import os
from datetime import datetime

CSV_FILE = "rex_trades.csv"

def initialize_exness():
    """Initializes the CSV file for trade logging."""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["TradeID", "Time", "Type", "Symbol", "Entry", "SL", "TP", "Status", "ExitPrice", "PnL", "Reason"])
    print(f"✅ Paper Trading Active. Logging to: {CSV_FILE}")
    return True

def place_trade(decision, symbol, volume, sl, tp, price):
    """Logs a NEW trade to the CSV and returns the Trade ID."""
    trade_id = int(time.time())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(CSV_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([trade_id, timestamp, decision, symbol, price, sl, tp, "OPEN", 0, 0, "-"])
    
    print(f"\n📝 Trade {trade_id} Logged to CSV: {decision} @ {price}")
    return trade_id

def close_trade(trade_id, exit_price, reason, trade_type, entry_price, volume=0.01):
    """Updates the existing CSV row with Exit Price and PnL."""
    contract_size = 100 
    
    if trade_type == "BUY":
        pnl = (exit_price - entry_price) * contract_size * volume
    else: # SELL
        pnl = (entry_price - exit_price) * contract_size * volume
        
    pnl = round(pnl, 2)
    
    updated_rows = []
    found = False
    
    with open(CSV_FILE, mode='r') as file:
        reader = csv.reader(file)
        header = next(reader)
        updated_rows.append(header)
        
        for row in reader:
            if str(row[0]) == str(trade_id):
                row[7] = "CLOSED"
                row[8] = exit_price
                row[9] = pnl
                row[10] = reason
                found = True
            updated_rows.append(row)
    
    if found:
        with open(CSV_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerows(updated_rows)
        
        emoji = "✅" if pnl > 0 else "❌"
        print(f"{emoji} Trade {trade_id} Closed. PnL: ${pnl} ({reason})")

def shutdown():
    print("🛑 CSV Logger Closed")