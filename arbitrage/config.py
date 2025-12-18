"""
Arbitrage System Configuration
Defines currency pair correlations and trading parameters
"""

# ============================================================
# CURRENCY PAIR CORRELATIONS (2025 Data)
# ============================================================

# Positively Correlated Pairs (move together)
# When one moves up, the other typically follows
POSITIVE_PAIRS = [
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
    {
        "pair_a": "eurjpy",
        "pair_b": "gbpjpy",
        "expected_corr": 0.90,
        "name": "JPY_CROSSES",
        "description": "JPY crosses - driven by risk-on/risk-off sentiment"
    },
]

# Negatively Correlated Pairs (move opposite)
# When one moves up, the other typically moves down
NEGATIVE_PAIRS = [
    {
        "pair_a": "eurusd",
        "pair_b": "usdchf",
        "expected_corr": -0.95,
        "name": "EUR_CHF_MIRROR",
        "description": "Most stable negative correlation - Euro and Swiss Franc both vs Dollar"
    },
    # DISABLED: COMMODITY_SPLIT has 0% win rate - not mean reverting
    # {
    #     "pair_a": "audusd",
    #     "pair_b": "usdcad",
    #     "expected_corr": -0.85,
    #     "name": "COMMODITY_SPLIT",
    #     "description": "AUD (metals) vs CAD (oil) - different commodity exposures"
    # },
]

# Pairs to skip based on historical performance
DISABLED_PAIRS = ["COMMODITY_SPLIT"]  # 0% win rate - not mean reverting

# All tickers to subscribe to
ALL_TICKERS = list(set(
    [p["pair_a"] for p in POSITIVE_PAIRS + NEGATIVE_PAIRS] +
    [p["pair_b"] for p in POSITIVE_PAIRS + NEGATIVE_PAIRS]
))

# ============================================================
# TRADING PARAMETERS
# ============================================================

# Signal Detection
Z_SCORE_ENTRY_THRESHOLD = 2.0      # Minimum Z-score to generate signal
Z_SCORE_EXTREME_THRESHOLD = 3.0    # Extreme divergence - may be regime change
Z_SCORE_EXIT_THRESHOLD = 0.5       # Close when spread normalizes
SKIP_EXTREME_ZSCORE = True         # Skip trades with Z-score > 3.0 (regime changes)

# Correlation Health
CORRELATION_DRIFT_WARNING = 0.15   # Warn if correlation drifts by this much
CORRELATION_BREAKDOWN = 0.25       # Skip trades if correlation broken by this much

# Position Management
MAX_CONCURRENT_TRADES = 3          # Max arbitrage positions at once
MAX_HOLD_MINUTES = 60              # Force close after this time
STOP_LOSS_ZSCORE = 3.5             # Stop if Z-score goes further against us

# Risk Management
CONSECUTIVE_LOSS_PAUSE = 3         # Pause after this many losses
MIN_MINUTES_BETWEEN_TRADES = 5     # Cooldown between trades on same pair

# Data Requirements
LOOKBACK_PERIOD = 30               # Minutes of data for correlation
MIN_DATA_POINTS = 15               # Minimum data points before trading
BUFFER_SIZE = 60                   # Price buffer size (minutes)

# Learning Mode
LEARNING_TRADES_REQUIRED = 20      # Build this much history before filtering

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
# PAIR METADATA
# ============================================================
PAIR_INFO = {
    "eurusd": {"pip_value": 0.0001, "name": "EUR/USD", "liquidity": "HIGH"},
    "gbpusd": {"pip_value": 0.0001, "name": "GBP/USD", "liquidity": "HIGH"},
    "audusd": {"pip_value": 0.0001, "name": "AUD/USD", "liquidity": "MEDIUM"},
    "nzdusd": {"pip_value": 0.0001, "name": "NZD/USD", "liquidity": "MEDIUM"},
    "usdchf": {"pip_value": 0.0001, "name": "USD/CHF", "liquidity": "MEDIUM"},
    "usdcad": {"pip_value": 0.0001, "name": "USD/CAD", "liquidity": "MEDIUM"},
    "eurjpy": {"pip_value": 0.01, "name": "EUR/JPY", "liquidity": "HIGH"},
    "gbpjpy": {"pip_value": 0.01, "name": "GBP/JPY", "liquidity": "HIGH"},
}

