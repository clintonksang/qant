"""
MT5 Helper Functions
Symbol mapping and market hours utilities for MT5 integration
"""

from datetime import datetime, timezone

# ============================================================
# SYMBOL MAPPING
# ============================================================

# Map internal symbol names to MT5 format
# Most brokers use "m" suffix (e.g., EURUSDm, GBPUSDm)
MT5_SYMBOL_MAP = {
    "eurusd": "EURUSDm",
    "gbpusd": "GBPUSDm",
    "audusd": "AUDUSDm",
    "nzdusd": "NZDUSDm",
    "usdchf": "USDCHFm",
    "usdcad": "USDCADm",
    "eurjpy": "EURJPYm",
    "gbpjpy": "GBPJPYm",
    "eurgbp": "EURGBPm",
    "audcad": "AUDCADm",
    "nzdcad": "NZDCADm",
    "euraud": "EURAUDm",
    "eurcad": "EURCADm",
    "eurchf": "EURCHFm",
    "audjpy": "AUDJPYm",
    "audnzd": "AUDNZDm",
    "cadjpy": "CADJPYm",
    "cadchf": "CADCHFm",
    "chfjpy": "CHFJPYm",
    "eurnzd": "EURNZDm",
    "xagusd": "XAGUSDm",  # Silver
    "xauusd": "XAUUSDm",  # Gold
}

def get_mt5_symbol(symbol):
    """
    Convert internal symbol name to MT5 format.
    
    Args:
        symbol: Internal symbol (e.g., 'EURUSD', 'eurusd')
        
    Returns:
        MT5 symbol (e.g., 'EURUSDm')
    """
    symbol_lower = symbol.lower()
    
    # Check if already in map
    if symbol_lower in MT5_SYMBOL_MAP:
        return MT5_SYMBOL_MAP[symbol_lower]
    
    # If not in map, try adding 'm' suffix
    # Handle both uppercase and lowercase input
    if symbol.isupper():
        return f"{symbol}m"
    else:
        return f"{symbol.upper()}m"


# ============================================================
# MARKET HOURS CHECK
# ============================================================

def is_forex_market_open(utc_time=None):
    """
    Check if forex market is open.
    Forex market is open 24/5 (Sunday 22:00 UTC to Friday 22:00 UTC).
    
    Args:
        utc_time: datetime object in UTC (default: current UTC time)
        
    Returns:
        bool: True if market is open, False otherwise
    """
    if utc_time is None:
        utc_time = datetime.now(timezone.utc)
    elif utc_time.tzinfo is None:
        # Assume UTC if no timezone info
        utc_time = utc_time.replace(tzinfo=timezone.utc)
    
    # Get weekday (0=Monday, 6=Sunday)
    weekday = utc_time.weekday()
    hour = utc_time.hour
    
    # Market closes Friday at 22:00 UTC
    if weekday == 4 and hour >= 22:  # Friday 22:00+
        return False
    
    # Market closed all day Saturday
    if weekday == 5:  # Saturday
        return False
    
    # Market opens Sunday at 22:00 UTC
    if weekday == 6 and hour < 22:  # Sunday before 22:00
        return False
    
    # Market is open Monday-Friday (except Friday after 22:00)
    # and Sunday after 22:00
    return True


def is_market_open_for_symbol(symbol, utc_time=None):
    """
    Check if market is open for a specific symbol.
    For forex pairs, uses standard forex hours.
    For metals (XAUUSD, XAGUSD), uses same hours.
    
    Args:
        symbol: Symbol name (e.g., 'EURUSD', 'XAUUSD')
        utc_time: datetime object in UTC (default: current UTC time)
        
    Returns:
        bool: True if market is open, False otherwise
    """
    # All forex and metals use same hours (24/5)
    return is_forex_market_open(utc_time)


def get_market_status(symbol, utc_time=None):
    """
    Get detailed market status for a symbol.
    
    Args:
        symbol: Symbol name
        utc_time: datetime object in UTC (default: current UTC time)
        
    Returns:
        dict with status information
    """
    if utc_time is None:
        utc_time = datetime.now(timezone.utc)
    elif utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=timezone.utc)
    
    is_open = is_market_open_for_symbol(symbol, utc_time)
    mt5_symbol = get_mt5_symbol(symbol)
    
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    return {
        'symbol': symbol,
        'mt5_symbol': mt5_symbol,
        'is_open': is_open,
        'utc_time': utc_time.isoformat(),
        'weekday': weekday_names[utc_time.weekday()],
        'hour_utc': utc_time.hour,
        'status': 'OPEN' if is_open else 'CLOSED'
    }


# ============================================================
# TESTING
# ============================================================

if __name__ == "__main__":
    print("Testing MT5 Helpers")
    print("=" * 60)
    
    # Test symbol mapping
    print("\n1. Symbol Mapping:")
    test_symbols = ["EURUSD", "eurusd", "GBPUSD", "XAUUSD", "UNKNOWN"]
    for sym in test_symbols:
        mt5_sym = get_mt5_symbol(sym)
        print(f"   {sym:10} -> {mt5_sym}")
    
    # Test market hours
    print("\n2. Market Hours Check:")
    from datetime import datetime, timedelta
    import pytz
    
    # Test different times
    test_times = [
        datetime.now(timezone.utc),  # Now
        datetime(2025, 12, 22, 10, 0, tzinfo=timezone.utc),  # Monday 10:00 UTC
        datetime(2025, 12, 20, 22, 30, tzinfo=timezone.utc),  # Friday 22:30 UTC (closed)
        datetime(2025, 12, 21, 10, 0, tzinfo=timezone.utc),  # Saturday 10:00 UTC (closed)
        datetime(2025, 12, 22, 22, 30, tzinfo=timezone.utc),  # Sunday 22:30 UTC (open)
    ]
    
    for test_time in test_times:
        is_open = is_forex_market_open(test_time)
        status = get_market_status("EURUSD", test_time)
        print(f"   {test_time.strftime('%Y-%m-%d %H:%M UTC')} ({status['weekday']}): {status['status']}")
    
    print("\n" + "=" * 60)

