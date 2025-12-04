#!/usr/bin/env python3
"""
Main entry point for AI-Driven Crypto Trading Bot
Runs every minute and executes trades based on AI analysis
"""

from ai_crypto_bot import run_ai_trading_bot

if __name__ == "__main__":
    # Configuration
    CRYPTO_SYMBOLS = ["BTC/USD", "ETH/USD"]  # Symbols to trade
    TIMEFRAME = "15m"  # Analysis timeframe (15 minutes)
    CHECK_INTERVAL = 60  # Check every minute (60 seconds)
    
    print("🚀 Starting AI-Driven Crypto Trading Bot...")
    print("📊 The bot will analyze and trade every minute")
    print("🤖 Using TradingGraph AI for decision making")
    print("💰 Executing trades via Alpaca API")
    print()
    
    run_ai_trading_bot(
        symbols=CRYPTO_SYMBOLS,
        timeframe=TIMEFRAME,
        check_interval=CHECK_INTERVAL,
        continuous=True
    )

