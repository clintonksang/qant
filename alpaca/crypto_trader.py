#!/usr/bin/env python3
"""
Crypto Trading Module
Handles all crypto-specific trading operations using Alpaca API
"""

import pandas as pd
from datetime import datetime, timedelta
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from strategy import simple_moving_average_strat


class CryptoTrader:
    """Crypto trading bot using SMA crossover strategy"""
    
    def __init__(self, api_key, api_secret, paper=True, trade_notional=250.0,
                 fast_sma=5, slow_sma=20):
        """
        Initialize Crypto Trader
        
        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            paper: Paper trading mode (default: True)
            trade_notional: USD amount per order (default: 250.0)
            fast_sma: Fast SMA period (default: 5)
            slow_sma: Slow SMA period (default: 20)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper = paper
        self.trade_notional = trade_notional
        self.fast_sma = fast_sma
        self.slow_sma = slow_sma
        
        # Initialize clients
        self.trading_client = TradingClient(
            api_key=api_key, 
            secret_key=api_secret, 
            paper=paper
        )
        # Crypto data client doesn't require API keys for market data
        self.data_client = CryptoHistoricalDataClient()
    
    def get_bars_data(self, symbol, timeframe=TimeFrame.Day, days_back=1, limit=100):
        """
        Get historical crypto bars data
        
        Args:
            symbol: Crypto pair symbol (e.g., "BTC/USD")
            timeframe: TimeFrame enum (default: Day)
            days_back: Number of days to look back
            limit: Maximum number of bars to return
            
        Returns:
            DataFrame with bars data
        """
        start_time = datetime.now() - timedelta(days=days_back)
        
        request_params = CryptoBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=timeframe,
            start=start_time,
            limit=limit
        )
        
        bars = self.data_client.get_crypto_bars(request_params)
        df = bars.df
        
        # Reset index if multi-index
        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index(level='symbol', drop=True)
        
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
    
    def place_order(self, signal, symbol, notional=None):
        """
        Place a market order for crypto
        
        Args:
            signal: "buy" or "sell"
            symbol: Crypto pair symbol (e.g., "BTC/USD")
            notional: USD amount to trade (default: uses self.trade_notional)
        """
        try:
            notional = notional or self.trade_notional
            
            if signal == "buy":
                # Check if we already have a position
                current_qty = self.get_current_position(symbol)
                if current_qty > 0:
                    print(f"  ⚠️  Already have position of {current_qty} coins. Skipping buy.")
                    return None
                
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    notional=notional,
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.GTC
                )
                order = self.trading_client.submit_order(order_data=order_data)
                print(f"  ✅ BUY order placed: {order.id} | Status: {order.status}")
                return order
                
            elif signal == "sell":
                # Check if we have a position to sell
                current_qty = self.get_current_position(symbol)
                if current_qty == 0:
                    print(f"  ⚠️  No position to sell. Skipping sell.")
                    return None
                
                # Sell the entire position
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=abs(current_qty),  # Use absolute value
                    side=OrderSide.SELL,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.GTC
                )
                order = self.trading_client.submit_order(order_data=order_data)
                print(f"  ✅ SELL order placed: {order.id} | Status: {order.status}")
                return order
                
        except Exception as e:
            print(f"  ❌ Error placing order: {e}")
            return None
    
    def analyze_and_trade(self, symbol, timeframe=TimeFrame.Day, days_back=1, limit=100):
        """
        Analyze a crypto pair and execute trades based on SMA crossover signals
        
        Args:
            symbol: Crypto pair symbol (e.g., "BTC/USD")
            timeframe: TimeFrame for data (default: Day)
            days_back: Days of historical data (default: 1)
            limit: Max bars to fetch (default: 100)
            
        Returns:
            dict with analysis results
        """
        try:
            print(f"\n📊 Analyzing CRYPTO: {symbol}...")
            
            # Get historical bars
            df = self.get_bars_data(symbol, timeframe, days_back, limit)
            
            # Check if we have enough data
            if len(df) < self.slow_sma:
                print(f"  ⚠️  Not enough data (have {len(df)}, need {self.slow_sma})")
                return None
            
            # Get trading signal
            signal = simple_moving_average_strat(df, self.fast_sma, self.slow_sma)
            
            # Get current price and SMAs
            current_price = df['close'].iloc[-1]
            fast_sma = df['sma_fast'].iloc[-1]
            slow_sma = df['sma_slow'].iloc[-1]
            
            print(f"  Current Price: ${current_price:.2f}")
            print(f"  Fast SMA ({self.fast_sma}): ${fast_sma:.2f}")
            print(f"  Slow SMA ({self.slow_sma}): ${slow_sma:.2f}")
            print(f"  Signal: {signal.upper()}")
            
            # Check current position
            position = self.get_current_position(symbol)
            if position != 0:
                print(f"  Current Position: {position} coins")
            
            # Place order based on signal
            order = None
            if signal in ["buy", "sell"]:
                order = self.place_order(signal, symbol)
            else:
                print(f"  ⏸️  HOLD - No action taken")
            
            return {
                'symbol': symbol,
                'price': current_price,
                'fast_sma': fast_sma,
                'slow_sma': slow_sma,
                'signal': signal,
                'position': position,
                'order': order
            }
            
        except Exception as e:
            print(f"  ❌ Error processing {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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

