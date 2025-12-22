#!/usr/bin/env python3
"""
Calculate profit/loss from arbitrage trades CSV
Given: 0.5 lot size, $200 account, 1:400 leverage
"""

import csv
from pathlib import Path

# Configuration
LOT_SIZE = 0.5  # 0.5 lots
ACCOUNT_BALANCE = 300  # USD
LEVERAGE = 400  # 1:400

# Pip value per standard lot (approximate)
# For standard pairs (EUR/USD, GBP/USD, AUD/USD, NZD/USD, USD/CHF): $10 per pip per lot
# For JPY pairs: varies with exchange rate, using approximate values
PIP_VALUES = {
    # Standard pairs (pip = 0.0001)
    'eurusd': 10.0,
    'gbpusd': 10.0,
    'audusd': 10.0,
    'nzdusd': 10.0,
    'usdchf': 10.0,
    # JPY pairs (pip = 0.01) - approximate based on current rates
    'eurjpy': 5.5,   # ~$5.49 at 182 rate
    'gbpjpy': 4.8,   # ~$4.81 at 208 rate
}

def get_pip_value_for_pair(pair_name, pair_a, pair_b):
    """Get pip value for the pair combination."""
    # For arbitrage, we need to consider both pairs
    # Use the average or the pair that dominates
    pair_a_lower = pair_a.lower()
    pair_b_lower = pair_b.lower()
    
    # If both are standard pairs, use $10
    if pair_a_lower not in ['eurjpy', 'gbpjpy'] and pair_b_lower not in ['eurjpy', 'gbpjpy']:
        return 10.0
    # If both are JPY pairs, use average JPY pip value
    elif pair_a_lower in ['eurjpy', 'gbpjpy'] and pair_b_lower in ['eurjpy', 'gbpjpy']:
        return 5.15  # Average of EUR/JPY and GBP/JPY
    # Mixed: use weighted average (approximate)
    else:
        return 7.5  # Approximate middle value

def calculate_profit_loss(csv_file):
    """Calculate total profit/loss from CSV."""
    trades = []
    total_pips = 0
    total_profit_usd = 0
    
    with open(csv_file, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or len(row) < 19:  # Skip empty rows or incomplete rows
                continue
            
            try:
                trade_id = row[0]
                pair_name = row[2]
                pair_a = row[3]
                pair_b = row[8]
                pips_a = float(row[7]) if row[7] else 0
                pips_b = float(row[12]) if row[12] else 0
                net_pips = float(row[15]) if row[15] else 0  # Column 16 (0-indexed 15)
                result = row[17] if len(row) > 17 else 'UNKNOWN'
                exit_reason = row[18] if len(row) > 18 else 'UNKNOWN'
                
                # Get pip value for this pair combination
                pip_value_per_lot = get_pip_value_for_pair(pair_name, pair_a, pair_b)
                
                # Calculate profit in USD
                # For 0.5 lot: pip_value = pip_value_per_lot * 0.5
                pip_value_05_lot = pip_value_per_lot * LOT_SIZE
                profit_usd = net_pips * pip_value_05_lot
                
                trades.append({
                    'id': trade_id,
                    'pair': pair_name,
                    'net_pips': net_pips,
                    'profit_usd': profit_usd,
                    'result': result,
                    'exit_reason': exit_reason
                })
                
                total_pips += net_pips
                total_profit_usd += profit_usd
                
            except (ValueError, IndexError) as e:
                print(f"Error parsing row: {row[:5]}... - {e}")
                continue
    
    return trades, total_pips, total_profit_usd

# Main calculation
csv_file = Path(__file__).parent / "arbitrage" / "arbitrage_trades_beta.csv"
trades, total_pips, total_profit_usd = calculate_profit_loss(csv_file)

# Print results
print("=" * 80)
print("ARBITRAGE TRADES PROFIT/LOSS CALCULATION")
print("=" * 80)
print(f"\nConfiguration:")
print(f"  Lot Size: {LOT_SIZE} lots")
print(f"  Account Balance: ${ACCOUNT_BALANCE}")
print(f"  Leverage: 1:{LEVERAGE}")
print(f"\nTotal Trades: {len(trades)}")
print(f"\nTrade Breakdown:")
print("-" * 80)
print(f"{'ID':<12} {'Pair':<20} {'Net Pips':<12} {'Profit (USD)':<15} {'Result':<8} {'Exit Reason':<20}")
print("-" * 80)

wins = 0
losses = 0
for trade in trades:
    result_icon = "✅" if trade['result'] == 'WIN' else "❌"
    print(f"{trade['id']:<12} {trade['pair']:<20} {trade['net_pips']:>+10.2f} {trade['profit_usd']:>+13.2f} {result_icon:<8} {trade['exit_reason']:<20}")
    if trade['result'] == 'WIN':
        wins += 1
    elif trade['result'] == 'LOSS':
        losses += 1

print("-" * 80)
print(f"\nSummary:")
print(f"  Total Net Pips: {total_pips:+.2f}")
print(f"  Total Profit/Loss: ${total_profit_usd:+.2f}")
print(f"  Wins: {wins}")
print(f"  Losses: {losses}")
print(f"  Win Rate: {(wins/(wins+losses)*100):.1f}%" if (wins+losses) > 0 else "N/A")

# Account projection
final_balance = ACCOUNT_BALANCE + total_profit_usd
return_pct = (total_profit_usd / ACCOUNT_BALANCE) * 100

print(f"\nAccount Projection:")
print(f"  Starting Balance: ${ACCOUNT_BALANCE:.2f}")
print(f"  Profit/Loss: ${total_profit_usd:+.2f}")
print(f"  Final Balance: ${final_balance:.2f}")
print(f"  Return: {return_pct:+.2f}%")

# Risk analysis
max_drawdown = min([t['profit_usd'] for t in trades] + [0])
largest_win = max([t['profit_usd'] for t in trades] + [0])
largest_loss = min([t['profit_usd'] for t in trades] + [0])

print(f"\nRisk Metrics:")
print(f"  Largest Win: ${largest_win:.2f}")
print(f"  Largest Loss: ${largest_loss:.2f}")
print(f"  Max Drawdown: ${max_drawdown:.2f}")

print("=" * 80)


