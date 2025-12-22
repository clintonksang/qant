"""
Arbitrage System Configuration
Defines currency pair correlations and trading parameters
"""

import os

# ============================================================
# LIVE TRADING MODE
# ============================================================
# Set to True to execute real trades via MT5 API
# Set to False for paper trading (simulation only)
LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"

# MT5 API Configuration
MT5_API_URL = os.getenv("MT5_API_URL", "https://api.ruthwestlimited.com")
MT5_VOLUME = float(os.getenv("MT5_VOLUME", "0.01"))  # Lot size (0.01 = micro lot)
MT5_MAGIC = int(os.getenv("MT5_MAGIC", "123456"))    # Magic number for bot identification

# Symbol Mapping: Internal name -> MT5 symbol
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
    "audnzd": "AUDNZDm",  # v3: Added
    "eurchf": "EURCHFm",  # v3: Added
    "gbpchf": "GBPCHFm",  # v3: Added
}

# ============================================================
# CURRENCY PAIR CORRELATIONS (2025 Data)
# ============================================================

# ============================================================
# POSITIVELY CORRELATED PAIRS (move together)
# v3: EXPANDED for more trading opportunities
# ============================================================
POSITIVE_PAIRS = [
    # === MAJOR PAIRS ===
    {
        "pair_a": "eurusd",
        "pair_b": "gbpusd", 
        "expected_corr": 0.95,
        "name": "EUR_GBP",
        "description": "Euro and Pound vs Dollar - deeply intertwined EU/UK economies"
    },
    {
        "pair_a": "audusd",
        "pair_b": "nzdusd",
        "expected_corr": 0.95,
        "name": "COMMODITY_TWINS",
        "description": "Commodity twins - both sensitive to China demand & risk sentiment"
    },
    # === JPY CROSSES - HIGH VOLATILITY, MORE PIPS ===
    {
        "pair_a": "eurjpy",
        "pair_b": "gbpjpy",
        "expected_corr": 0.92,
        "name": "JPY_CROSSES",
        "description": "EUR/JPY and GBP/JPY - high volatility, strong correlation"
    },
    # === CROSS PAIRS ===
    {
        "pair_a": "eurgbp",
        "pair_b": "audnzd",
        "expected_corr": 0.75,
        "name": "CROSS_PAIRS",
        "description": "Cross pairs that often move together during risk events"
    },
]

# ============================================================
# NEGATIVELY CORRELATED PAIRS (move opposite)
# v3: EXPANDED for more trading opportunities
# ============================================================
NEGATIVE_PAIRS = [
    # === MOST STABLE NEGATIVE CORRELATION ===
    {
        "pair_a": "eurusd",
        "pair_b": "usdchf",
        "expected_corr": -0.95,
        "name": "EUR_CHF_MIRROR",
        "description": "Most stable negative correlation - Euro and Swiss Franc both vs Dollar"
    },
    # === USD INDEX MIRRORS ===
    {
        "pair_a": "gbpusd",
        "pair_b": "usdcad",
        "expected_corr": -0.80,
        "name": "GBP_CAD_MIRROR",
        "description": "GBP strength often mirrors CAD weakness vs USD"
    },
    # === COMMODITY INVERSE ===
    {
        "pair_a": "audusd",
        "pair_b": "usdcad",
        "expected_corr": -0.75,
        "name": "COMMODITY_SPLIT",
        "description": "AUD (metals) vs CAD (oil) - can diverge during commodity shifts"
    },
]

# Pairs to skip if they consistently lose
DISABLED_PAIRS = [
    "COMMODITY_SPLIT",
    "GBP_CAD_MIRROR"
]  # v3: Try all pairs, disable based on performance

# All tickers to subscribe to
ALL_TICKERS = list(set(
    [p["pair_a"] for p in POSITIVE_PAIRS + NEGATIVE_PAIRS] +
    [p["pair_b"] for p in POSITIVE_PAIRS + NEGATIVE_PAIRS]
))

# ============================================================
# TRADING PARAMETERS - AGGRESSIVE MODE (v3)
# ============================================================
# Optimized for frequent trading and maximizing pip capture

# Signal Detection - PROFIT MAXIMIZED (v5)
Z_SCORE_ENTRY_THRESHOLD = 1.8      # v4: Good balance of quality signals
Z_SCORE_EXTREME_THRESHOLD = 3.5    # v3: Take stronger signals
Z_SCORE_EXIT_THRESHOLD = 0.3       # v5: Lowered from 0.4 (capture more of the move)
SKIP_EXTREME_ZSCORE = False        # v3: Don't skip extreme - they can be profitable

# Take Profit Enhancement - LET WINNERS RUN (v5)
Z_SCORE_TAKE_PROFIT = 0.2          # Close early if reverted well
MIN_PROFIT_PIPS = 5.0              # v5: Raised from 3.0 (let winners run!)

# v4: LOSS PROTECTION - Cut losers early!
MAX_LOSS_PIPS = -4.0               # v4: Exit if losing more than 4 pips (prevents -6.6 disasters)
LOSS_EXIT_MINUTES = 10             # v4: After 10 min, exit if losing ANY amount

# v5: PROFIT PROTECTION - Lock in gains!
BREAKEVEN_TRIGGER_PIPS = 1.0       # v5: Move SL to breakeven at +1 pip
TRAILING_STOP_TRIGGER = 2.5        # v5: Start trailing after +2.5 pips profit
TRAILING_STOP_DISTANCE = 1.0       # v5: Trail by 1 pip

# Correlation Health - RELAXED
CORRELATION_DRIFT_WARNING = 0.20   # v3: Relaxed from 0.15
CORRELATION_BREAKDOWN = 0.30       # v3: Relaxed from 0.25 (trade more pairs)

# Position Management - BALANCED (v4: Tighter risk control)
MAX_CONCURRENT_TRADES = 3          # v4: Reduced to 3 (less exposure)
MAX_HOLD_MINUTES = 15              # v4: Reduced from 20 (cut losers faster)
STOP_LOSS_ZSCORE = 3.5             # v4: Tightened from 4.0 (less room to bleed)

# Risk Management - BALANCED (v4: Don't rush into trades)
CONSECUTIVE_LOSS_PAUSE = 4         # v4: Reduced from 5 (pause after fewer losses)
MIN_MINUTES_BETWEEN_TRADES = 3     # v4: Increased from 2 (don't rush re-entry)

# v5: Per-pair hold limits - EXTENDED FOR WINNERS (losers protected by MAX_LOSS/TIMED_LOSS)
PAIR_MAX_HOLD = {
    "EUR_GBP": 15,          # v5: Extended from 10 (losers cut by -4 pip or 10min rule)
    "EUR_CHF_MIRROR": 20,   # v5: Extended (star performer - let it run!)
    "COMMODITY_TWINS": 18,  # v5: Extended from 12
    "JPY_CROSSES": 15,      # v5: Extended (high volatility = bigger moves)
    "CROSS_PAIRS": 12,      # v5: Slight extension
}

# Data Requirements - FASTER WARMUP
LOOKBACK_PERIOD = 20               # v3: Reduced from 30 (faster startup)
MIN_DATA_POINTS = 10               # v3: Reduced from 15 (trade sooner)
BUFFER_SIZE = 45                   # v3: Reduced from 60

# Learning Mode - FASTER
LEARNING_TRADES_REQUIRED = 10      # v3: Reduced from 20 (learn faster)

# ============================================================
# TRADING SESSIONS (UTC)
# ============================================================
SESSIONS = {
    "ASIAN": (0, 8),       # 00:00 - 08:00 UTC
    "LONDON": (8, 13),     # 08:00 - 13:00 UTC  
    "US_OVERLAP": (13, 17), # 13:00 - 17:00 UTC (Most volatile)
    "US": (17, 22),        # 17:00 - 22:00 UTC
    "LATE_US": (22, 24),   # 22:00 - 00:00 UTC
}

def get_session(hour_utc):
    """Get current trading session."""
    for session, (start, end) in SESSIONS.items():
        if start <= hour_utc < end:
            return session
    return "ASIAN"  # Wrap around

# ============================================================
# PAIR METADATA - v3: EXPANDED
# ============================================================
PAIR_INFO = {
    # Major pairs (0.0001 pip value)
    "eurusd": {"pip_value": 0.0001, "name": "EUR/USD", "liquidity": "HIGH"},
    "gbpusd": {"pip_value": 0.0001, "name": "GBP/USD", "liquidity": "HIGH"},
    "audusd": {"pip_value": 0.0001, "name": "AUD/USD", "liquidity": "MEDIUM"},
    "nzdusd": {"pip_value": 0.0001, "name": "NZD/USD", "liquidity": "MEDIUM"},
    "usdchf": {"pip_value": 0.0001, "name": "USD/CHF", "liquidity": "MEDIUM"},
    "usdcad": {"pip_value": 0.0001, "name": "USD/CAD", "liquidity": "MEDIUM"},
    # JPY pairs (0.01 pip value) - MORE PIPS!
    "eurjpy": {"pip_value": 0.01, "name": "EUR/JPY", "liquidity": "HIGH"},
    "gbpjpy": {"pip_value": 0.01, "name": "GBP/JPY", "liquidity": "HIGH"},
    "audjpy": {"pip_value": 0.01, "name": "AUD/JPY", "liquidity": "MEDIUM"},
    "nzdjpy": {"pip_value": 0.01, "name": "NZD/JPY", "liquidity": "MEDIUM"},
    "cadjpy": {"pip_value": 0.01, "name": "CAD/JPY", "liquidity": "MEDIUM"},
    "chfjpy": {"pip_value": 0.01, "name": "CHF/JPY", "liquidity": "MEDIUM"},
    # Cross pairs (0.0001 pip value)
    "eurgbp": {"pip_value": 0.0001, "name": "EUR/GBP", "liquidity": "HIGH"},
    "audnzd": {"pip_value": 0.0001, "name": "AUD/NZD", "liquidity": "MEDIUM"},
    "eurchf": {"pip_value": 0.0001, "name": "EUR/CHF", "liquidity": "MEDIUM"},
    "gbpchf": {"pip_value": 0.0001, "name": "GBP/CHF", "liquidity": "MEDIUM"},
    "audcad": {"pip_value": 0.0001, "name": "AUD/CAD", "liquidity": "MEDIUM"},
    "nzdcad": {"pip_value": 0.0001, "name": "NZD/CAD", "liquidity": "MEDIUM"},
}

