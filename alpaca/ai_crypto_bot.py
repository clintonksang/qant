#!/usr/bin/env python3
"""
AI-Driven Crypto Trading Bot
Uses TradingGraph AI analysis to make trading decisions and executes via Alpaca
"""

import time
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any

# Add parent directory to path to import web_interface modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Hardcode OpenAI API Key BEFORE importing web_interface
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY_HERE"
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
print(f"✓ OpenAI API key set (hardcoded): {OPENAI_API_KEY[:8]}...")

import pandas as pd
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest

# Import the trading analyzer from web_interface (after setting API key)
from web_interface import WebTradingAnalyzer


class AICryptoTrader:
    """AI-driven crypto trading bot using TradingGraph analysis"""
    
    def __init__(self, api_key, api_secret, paper=True, trade_notional=250.0):
        """
        Initialize AI Crypto Trader
        
        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            paper: Paper trading mode (default: True)
            trade_notional: USD amount per order (default: 250.0)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper = paper
        self.trade_notional = trade_notional
        
        # Initialize Alpaca clients
        self.trading_client = TradingClient(
            api_key=api_key, 
            secret_key=api_secret, 
            paper=paper
        )
        self.data_client = CryptoHistoricalDataClient()
        
        # Initialize AI analyzer (from web_interface)
        # The API key should already be in os.environ from the top of the file
        self.analyzer = WebTradingAnalyzer()
        
        # Update analyzer's config with the API key from environment
        if "OPENAI_API_KEY" in os.environ:
            api_key = os.environ["OPENAI_API_KEY"]
            self.analyzer.config["api_key"] = api_key
            self.analyzer.trading_graph.config["api_key"] = api_key
            # Refresh LLMs with the new API key
            self.analyzer.trading_graph.refresh_llms()
            print(f"✓ Analyzer config updated with API key: {api_key[:8]}...")
        else:
            print(f"⚠️  Warning: OPENAI_API_KEY not found in environment")
        
        # Track last decision to avoid duplicate trades
        self.last_decisions = {}  # {symbol: last_decision}
    
    def get_crypto_bars_data(self, symbol, timeframe="15m", days_back=1):
        """
        Get historical crypto bars data using analyzer's yfinance method
        
        Args:
            symbol: Crypto pair (e.g., "BTC/USD")
            timeframe: Timeframe string (e.g., "15m", "1h")
            days_back: Days of historical data
            
        Returns:
            DataFrame with Datetime, Open, High, Low, Close columns
        """
        # Convert Alpaca symbol to yfinance format (BTC/USD -> BTC-USD)
        # The analyzer's yfinance_symbols maps "BTC" to "BTC-USD"
        base_symbol = symbol.split('/')[0] if '/' in symbol else symbol
        base_symbol = base_symbol.split('-')[0] if '-' in base_symbol else base_symbol
        
        # Calculate date range
        end_datetime = datetime.now()
        start_datetime = end_datetime - timedelta(days=days_back)
        
        # Use analyzer's data fetching method (which uses yfinance)
        # Pass base symbol (e.g., "BTC") and analyzer will map to "BTC-USD"
        df = self.analyzer.fetch_yfinance_data_with_datetime(
            symbol=base_symbol,
            interval=timeframe,
            start_datetime=start_datetime,
            end_datetime=end_datetime
        )
        
        return df
    
    def get_current_position(self, symbol):
        """Get current position for a symbol. Returns quantity or 0."""
        try:
            positions = self.trading_client.get_all_positions()
            for position in positions:
                if position.symbol == symbol:
                    return float(position.qty)
            return 0.0
        except Exception as e:
            print(f"  Error getting position: {e}")
            return 0.0
    
    def get_ai_decision(self, symbol, timeframe="15m"):
        """
        Get AI trading decision from TradingGraph analysis
        
        Args:
            symbol: Crypto pair (e.g., "BTC/USD")
            timeframe: Timeframe for analysis (default: "15m")
            
        Returns:
            dict with decision, risk_reward_ratio, justification, etc.
        """
        try:
            print(f"  🤖 Running AI analysis for {symbol}...")
            
            # Get historical data
            df = self.get_crypto_bars_data(symbol, timeframe, days_back=1)
            
            if df.empty or len(df) < 20:
                print(f"  ⚠️  Not enough data for analysis")
                return None
            
            # Convert symbol for display (BTC/USD -> BTC, BTC-USD -> BTC)
            display_symbol = symbol.split('/')[0] if '/' in symbol else symbol
            display_symbol = display_symbol.split('-')[0] if '-' in display_symbol else display_symbol
            
            # Run AI analysis using the analyzer
            results = self.analyzer.run_analysis(df, display_symbol, timeframe)
            
            if not results.get("success"):
                print(f"  ❌ Analysis failed: {results.get('error', 'Unknown error')}")
                return None
            
            # Extract decision
            formatted_results = self.analyzer.extract_analysis_results(results)
            
            if not formatted_results.get("success"):
                print(f"  ❌ Failed to extract results")
                return None
            
            final_decision = formatted_results.get("final_decision", {})
            
            if isinstance(final_decision, dict) and "decision" in final_decision:
                decision_data = {
                    "decision": final_decision.get("decision", "").upper(),
                    "risk_reward_ratio": final_decision.get("risk_reward_ratio", "1.5"),
                    "forecast_horizon": final_decision.get("forecast_horizon", ""),
                    "justification": final_decision.get("justification", ""),
                    "current_price": formatted_results.get("current_price"),
                    "signal_confidence": formatted_results.get("signal_confidence", "Medium"),
                }
                return decision_data
            else:
                print(f"  ⚠️  No valid decision in analysis results")
                return None
                
        except Exception as e:
            print(f"  ❌ Error getting AI decision: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def calculate_stop_loss(self, entry_price, decision, risk_reward_ratio):
        """
        Calculate stop loss price based on risk/reward ratio
        
        Args:
            entry_price: Entry price
            decision: "LONG" or "SHORT"
            risk_reward_ratio: Risk/reward ratio (e.g., "1.5" or "1:2")
            
        Returns:
            stop_loss_price
        """
        try:
            # Parse risk/reward ratio (handle formats like "1.5" or "1:2")
            if isinstance(risk_reward_ratio, str):
                if ":" in risk_reward_ratio:
                    risk, reward = map(float, risk_reward_ratio.split(":"))
                    rr_ratio = reward / risk
                else:
                    rr_ratio = float(risk_reward_ratio)
            else:
                rr_ratio = float(risk_reward_ratio)
            
            # Use 2% risk per trade (adjustable)
            risk_percent = 0.02
            
            if decision == "LONG":
                # Stop loss below entry
                stop_loss = entry_price * (1 - risk_percent)
            else:  # SHORT
                # Stop loss above entry
                stop_loss = entry_price * (1 + risk_percent)
            
            return round(stop_loss, 2)
        except Exception as e:
            print(f"  ⚠️  Error calculating stop loss: {e}")
            # Default to 2% stop loss
            if decision == "LONG":
                return entry_price * 0.98
            else:
                return entry_price * 1.02
    
    def place_order(self, symbol, decision, risk_reward_ratio, notional=None):
        """
        Place order based on AI decision
        
        Args:
            symbol: Crypto pair
            decision: "LONG" or "SHORT"
            risk_reward_ratio: Risk/reward ratio
            notional: USD amount (default: uses self.trade_notional)
        """
        try:
            notional = notional or self.trade_notional
            current_qty = self.get_current_position(symbol)
            
            # Get current price for stop loss calculation
            try:
                df = self.get_crypto_bars_data(symbol, "15m", days_back=1)
                if df.empty:
                    print(f"  ⚠️  Cannot get current price")
                    return None
                current_price = float(df['Close'].iloc[-1])
            except Exception as e:
                print(f"  ⚠️  Error getting current price: {e}")
                return None
            
            if decision == "LONG":
                # Check if we already have a long position
                if current_qty > 0:
                    print(f"  ⚠️  Already have LONG position of {current_qty} coins. Skipping.")
                    return None
                
                # Place buy order
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    notional=notional,
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.GTC
                )
                order = self.trading_client.submit_order(order_data=order_data)
                print(f"  ✅ LONG order placed: {order.id} | Status: {order.status}")
                
                # Wait a moment for order to fill, then set stop loss
                time.sleep(2)
                updated_position = self.get_current_position(symbol)
                if updated_position > 0:
                    stop_loss_price = self.calculate_stop_loss(current_price, "LONG", risk_reward_ratio)
                    print(f"  🛡️  Setting stop loss at ${stop_loss_price:.2f}...")
                    
                    stop_order = StopOrderRequest(
                        symbol=symbol,
                        qty=updated_position,
                        side=OrderSide.SELL,
                        stop_price=stop_loss_price,
                        time_in_force=TimeInForce.GTC
                    )
                    self.trading_client.submit_order(order_data=stop_order)
                    print(f"  ✅ Stop loss order placed")
                
                return order
                
            elif decision == "SHORT":
                # For SHORT, we need to close any long position first
                if current_qty > 0:
                    print(f"  📉 Closing LONG position before SHORT...")
                    sell_order = MarketOrderRequest(
                        symbol=symbol,
                        qty=abs(current_qty),
                        side=OrderSide.SELL,
                        type=OrderType.MARKET,
                        time_in_force=TimeInForce.GTC
                    )
                    self.trading_client.submit_order(order_data=sell_order)
                    print(f"  ✅ Closed LONG position")
                
                # Note: Alpaca crypto doesn't support shorting directly
                # So SHORT means "close position" or "don't buy"
                print(f"  📉 SHORT signal: No position taken (crypto shorting not available)")
                return None
                
        except Exception as e:
            print(f"  ❌ Error placing order: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def execute_trade(self, symbol, timeframe="15m"):
        """
        Execute a complete trade cycle: analyze and trade
        
        Args:
            symbol: Crypto pair to trade
            timeframe: Timeframe for analysis
        """
        try:
            print(f"\n{'='*70}")
            print(f"📊 Processing {symbol} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*70}")
            
            # Get AI decision
            decision_data = self.get_ai_decision(symbol, timeframe)
            
            if not decision_data:
                print(f"  ⚠️  No decision available")
                return
            
            decision = decision_data.get("decision", "").upper()
            risk_reward = decision_data.get("risk_reward_ratio", "1.5")
            justification = decision_data.get("justification", "")
            current_price = decision_data.get("current_price")
            confidence = decision_data.get("signal_confidence", "Medium")
            
            print(f"\n  🤖 AI Decision: {decision}")
            print(f"  📈 Risk/Reward: {risk_reward}")
            print(f"  💰 Current Price: ${current_price:.2f}" if current_price else "")
            print(f"  🎯 Confidence: {confidence}")
            print(f"  📝 Reasoning: {justification[:100]}..." if len(justification) > 100 else f"  📝 Reasoning: {justification}")
            
            # Check current position
            current_position = self.get_current_position(symbol)
            if current_position != 0:
                print(f"  📊 Current Position: {current_position} coins")
            
            # Execute trade based on signal
            if decision == "LONG":
                # Only place LONG order if we don't already have a position
                if current_position > 0:
                    print(f"  ⏸️  Already in LONG position. No action.")
                else:
                    # Check if we just placed a LONG order (avoid duplicate)
                    last_decision = self.last_decisions.get(symbol)
                    if last_decision == "LONG":
                        print(f"  ⏸️  LONG signal unchanged. No action.")
                    else:
                        print(f"  📈 Executing LONG order...")
                        self.last_decisions[symbol] = decision
                        self.place_order(symbol, decision, risk_reward)
                        
            elif decision == "SHORT":
                # For SHORT, always close any existing LONG position
                if current_position > 0:
                    print(f"  📉 SHORT signal: Closing existing LONG position...")
                    self.last_decisions[symbol] = decision
                    self.place_order(symbol, decision, risk_reward)
                else:
                    # No position to close, just note the SHORT signal
                    print(f"  📉 SHORT signal: No position to close (crypto shorting not available)")
                    self.last_decisions[symbol] = decision
            else:
                print(f"  ⏸️  HOLD - No action taken")
                
        except Exception as e:
            print(f"  ❌ Error executing trade: {e}")
            import traceback
            traceback.print_exc()
    
    def get_account_info(self):
        """Get account information"""
        try:
            account = self.trading_client.get_account()
            return {
                'status': account.status,
                'buying_power': float(account.buying_power),
                'cash': float(account.cash),
                'portfolio_value': float(account.portfolio_value),
                'equity': float(account.equity)
            }
        except Exception as e:
            print(f"Error getting account info: {e}")
            return None


def run_ai_trading_bot(symbols, timeframe="15m", check_interval=60, continuous=True):
    """
    Run the AI trading bot
    
    Args:
        symbols: List of crypto pairs to trade (e.g., ["BTC/USD"])
        timeframe: Timeframe for analysis (default: "15m")
        check_interval: Seconds between checks (default: 60 = 1 minute)
        continuous: If True, runs in infinite loop
    """
    # API Credentials - Load from environment variables or use defaults
    API_KEY = os.getenv("ALPACA_API_KEY", "PKSSKMLQBGOFAEL4ATO7LBEKHW")
    API_SECRET = os.getenv("ALPACA_SECRET_KEY", "2TdAfF2h6x65XptsAMeFetGRz2B3kvnexG64GeF2xBAX")
    PAPER = True
    TRADE_NOTIONAL = 250.0
    
    # OpenAI API key is already set at module level (hardcoded)
    
    # Initialize trader
    trader = AICryptoTrader(
        api_key=API_KEY,
        api_secret=API_SECRET,
        paper=PAPER,
        trade_notional=TRADE_NOTIONAL
    )
    
    print("="*70)
    print("AI-DRIVEN CRYPTO TRADING BOT")
    print("="*70)
    print(f"Mode: {'PAPER TRADING' if PAPER else 'LIVE TRADING'}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Timeframe: {timeframe}")
    print(f"Trade Notional: ${TRADE_NOTIONAL:.2f} per order")
    print(f"Check Interval: {check_interval} seconds (every minute)")
    print("="*70)
    
    # Display account info
    account_info = trader.get_account_info()
    if account_info:
        print(f"\nAccount Status: {account_info['status']}")
        print(f"Buying Power: ${account_info['buying_power']:,.2f}")
        print(f"Cash: ${account_info['cash']:,.2f}")
        print(f"Portfolio Value: ${account_info['portfolio_value']:,.2f}")
    
    iteration = 0
    
    try:
        while True:
            iteration += 1
            print(f"\n{'='*70}")
            print(f"Iteration #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*70}")
            
            # Process each symbol
            for symbol in symbols:
                trader.execute_trade(symbol, timeframe)
            
            if not continuous:
                print(f"\n{'='*70}")
                print("Single run completed. Exiting.")
                print(f"{'='*70}")
                break
            
            print(f"\n⏳ Waiting {check_interval} seconds until next check...")
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("Bot stopped by user (Ctrl+C)")
        print("="*70)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Configuration
    CRYPTO_SYMBOLS = ["BTC/USD"]  # Symbols to trade
    TIMEFRAME = "15m"  # Analysis timeframe
    CHECK_INTERVAL = 60  # Check every minute
    
    run_ai_trading_bot(
        symbols=CRYPTO_SYMBOLS,
        timeframe=TIMEFRAME,
        check_interval=CHECK_INTERVAL,
        continuous=True
    )

