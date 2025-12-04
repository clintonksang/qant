#!/usr/bin/env python3
"""
Simple Moving Average (SMA) Crossover Trading Bot
Main orchestrator that can run stock and/or crypto trading bots

This bot implements a simple SMA crossover strategy:
- Fast SMA (5 periods) vs Slow SMA (20 periods)
- Buy signal: Fast SMA crosses above Slow SMA
- Sell signal: Fast SMA crosses below Slow SMA
"""

import time
from datetime import datetime
from stock_trader import StockTrader
from crypto_trader import CryptoTrader

# ============================================================================
# Configuration
# ============================================================================

# API Credentials - Replace with your own paper trading keys
# Get them from: https://alpaca.markets/
API_KEY = "PKSSKMLQBGOFAEL4ATO7LBEKHW"
API_SECRET = "2TdAfF2h6x65XptsAMeFetGRz2B3kvnexG64GeF2xBAX"

# Paper trading mode (set to False for live trading)
PAPER = True

# Trading parameters
STOCK_TRADE_QUANTITY = 1  # Number of shares per order (for stocks)
CRYPTO_TRADE_NOTIONAL = 250.0  # USD amount per order (for crypto)
FAST_SMA_PERIOD = 5  # Fast SMA period
SLOW_SMA_PERIOD = 20  # Slow SMA period
CHECK_INTERVAL = 60  # Seconds between checks (60 = 1 minute)

# Separate lists for stocks and crypto
STOCK_TICKERS = ["AAPL", "MSFT", "INTC"]  # Stock symbols
CRYPTO_TICKERS = ["BTC/USD", "ETH/USD", "SOL/USD"]  # Crypto pairs

# ============================================================================
# Initialize Traders
# ============================================================================

# Initialize stock trader
stock_trader = StockTrader(
    api_key=API_KEY,
    api_secret=API_SECRET,
    paper=PAPER,
    trade_quantity=STOCK_TRADE_QUANTITY,
    fast_sma=FAST_SMA_PERIOD,
    slow_sma=SLOW_SMA_PERIOD
)

# Initialize crypto trader
crypto_trader = CryptoTrader(
    api_key=API_KEY,
    api_secret=API_SECRET,
    paper=PAPER,
    trade_notional=CRYPTO_TRADE_NOTIONAL,
    fast_sma=FAST_SMA_PERIOD,
    slow_sma=SLOW_SMA_PERIOD
)


# ============================================================================
# Main Trading Loop
# ============================================================================

def run_trading_bot(continuous=True):
    """
    Run the trading bot
    
    Args:
        continuous: If True, runs in infinite loop. If False, runs once.
    """
    print("="*70)
    print("SIMPLE MOVING AVERAGE CROSSOVER TRADING BOT")
    print("="*70)
    print(f"Mode: {'PAPER TRADING' if PAPER else 'LIVE TRADING'}")
    print(f"Fast SMA: {FAST_SMA_PERIOD} | Slow SMA: {SLOW_SMA_PERIOD}")
    print(f"Check Interval: {CHECK_INTERVAL} seconds")
    print("-"*70)
    print(f"STOCKS:")
    print(f"  Tickers: {', '.join(STOCK_TICKERS) if STOCK_TICKERS else 'None'}")
    print(f"  Trade Quantity: {STOCK_TRADE_QUANTITY} shares per order")
    print("-"*70)
    print(f"CRYPTO:")
    print(f"  Tickers: {', '.join(CRYPTO_TICKERS) if CRYPTO_TICKERS else 'None'}")
    print(f"  Trade Notional: ${CRYPTO_TRADE_NOTIONAL:.2f} per order")
    print("="*70)
    
    # Display account info
    try:
        account_info = stock_trader.get_account_info()
        if account_info:
            print(f"\nAccount Status: {account_info['status']}")
            print(f"Buying Power: ${account_info['buying_power']:,.2f}")
            print(f"Cash: ${account_info['cash']:,.2f}")
            print(f"Portfolio Value: ${account_info['portfolio_value']:,.2f}")
    except Exception as e:
        print(f"Error getting account info: {e}")
    
    iteration = 0
    
    while True:
        iteration += 1
        print(f"\n{'='*70}")
        print(f"Iteration #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
        # Process stocks
        if STOCK_TICKERS:
            print(f"\n{'─'*70}")
            print("PROCESSING STOCKS")
            print(f"{'─'*70}")
            for ticker in STOCK_TICKERS:
                stock_trader.analyze_and_trade(ticker)
        
        # Process crypto
        if CRYPTO_TICKERS:
            print(f"\n{'─'*70}")
            print("PROCESSING CRYPTO")
            print(f"{'─'*70}")
            for ticker in CRYPTO_TICKERS:
                crypto_trader.analyze_and_trade(ticker)
        
        if not continuous:
            print(f"\n{'='*70}")
            print("Single run completed. Exiting.")
            print(f"{'='*70}")
            break
        
        print(f"\n⏳ Waiting {CHECK_INTERVAL} seconds until next check...")
        time.sleep(CHECK_INTERVAL)


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    # Run the bot continuously
    # Set continuous=False to run once
    try:
        run_trading_bot(continuous=True)
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("Bot stopped by user (Ctrl+C)")
        print("="*70)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
