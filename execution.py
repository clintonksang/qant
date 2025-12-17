import csv
import time
import os
from datetime import datetime

CSV_FILE = "rex_trades.csv"

def initialize_exness():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["TradeID", "Time", "Type", "Symbol", "Entry", "SL", "TP", "Status", "ExitPrice", "PnL", "Reason"])
    return True

def place_trade(decision, symbol, volume, sl, tp, price):
    trade_id = int(time.time())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([trade_id, timestamp, decision, symbol, price, sl, tp, "OPEN", 0, 0, "-"])
    return trade_id

def close_trade(trade_id, exit_price, reason, trade_type, entry_price, volume=0.01):
    contract_size = 100 
    pnl = round(((exit_price - entry_price) if trade_type == "BUY" else (entry_price - exit_price)) * contract_size * volume, 2)
    
    rows = []
    with open(CSV_FILE, mode='r') as f:
        reader = list(csv.reader(f))
        for row in reader:
            if row[0] == str(trade_id):
                row[7], row[8], row[9], row[10] = "CLOSED", exit_price, pnl, reason
            rows.append(row)
            
    with open(CSV_FILE, mode='w', newline='') as f:
        csv.writer(f).writerows(rows)
    print(f"💰 Result: {reason} | PnL: ${pnl}")

def shutdown():
    pass