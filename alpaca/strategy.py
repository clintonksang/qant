#!/usr/bin/env python3
"""
Shared Trading Strategy Functions
Contains the SMA crossover strategy logic used by both stock and crypto bots
"""

import pandas as pd


def simple_moving_average_strat(df, fast_period=5, slow_period=20):
    """
    Simple Moving Average Crossover Strategy
    
    Args:
        df: DataFrame with 'close' prices
        fast_period: Fast SMA period (default: 5)
        slow_period: Slow SMA period (default: 20)
        
    Returns:
        str: "buy", "sell", or "hold"
    """
    # Calculate fast and slow SMAs
    df["sma_fast"] = df['close'].rolling(window=fast_period).mean()
    df['sma_slow'] = df['close'].rolling(window=slow_period).mean()
    
    # Need at least slow_period data points for valid signals
    if len(df) < slow_period:
        return "hold"
    
    # Get the most recent values
    fast_sma_current = df["sma_fast"].iloc[-1]
    slow_sma_current = df["sma_slow"].iloc[-1]
    
    # Get previous values to detect crossover
    if len(df) > 1:
        fast_sma_prev = df["sma_fast"].iloc[-2]
        slow_sma_prev = df["sma_slow"].iloc[-2]
        
        # Buy signal: Fast SMA crosses above Slow SMA
        if fast_sma_current > slow_sma_current and fast_sma_prev <= slow_sma_prev:
            return "buy"
        
        # Sell signal: Fast SMA crosses below Slow SMA
        elif fast_sma_current < slow_sma_current and fast_sma_prev >= slow_sma_prev:
            return "sell"
    
    # Hold if fast SMA is above slow SMA (already in position)
    if fast_sma_current > slow_sma_current:
        return "hold"
    
    # Hold if fast SMA is below slow SMA (no position)
    return "hold"

