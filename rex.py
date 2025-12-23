import simplejson as json
from websocket import create_connection, WebSocketConnectionClosedException
import datetime, os, time, ssl, csv, pickle
from pathlib import Path
import brain, execution
import pattern_learner  # Pattern learning agent
import rex_mt5_executor  # v8: Live MT5 trading
import slack_notifier  # v9: Slack hourly summaries

# Initialize
TIINGO_KEY = os.getenv("TIINGO_KEY")
ws = None  # Will be initialized by connect_websocket()

# v8: LIVE TRADING CONFIG
LIVE_TRADING = os.getenv("REX_LIVE_TRADING", "true").lower() == "true"
mt5 = None  # MT5 executor instance

# ============================================================
# v10: MULTI-CURRENCY SUPPORT
# ============================================================
# Each pair has its own risk parameters based on volatility
CURRENCY_PAIRS = {
    "xauusd": {
        "enabled": True,
        "mt5_symbol": "XAUUSDm",
        "sl_pips": 2.00,      # Gold: $2 SL (200 pips)
        "tp_pips": 6.00,      # Gold: $6 TP (3:1)
        "pip_value": 0.01,    # Gold: 1 pip = $0.01
        "min_volume": 0.01,
        "description": "Gold"
    },
    "eurusd": {
        "enabled": True,
        "mt5_symbol": "EURUSDm",
        "sl_pips": 15,        # EUR/USD: 15 pips SL
        "tp_pips": 45,        # EUR/USD: 45 pips TP (3:1)
        "pip_value": 0.0001,  # Standard forex pair
        "min_volume": 0.01,
        "description": "Euro"
    },
    "gbpusd": {
        "enabled": True,
        "mt5_symbol": "GBPUSDm",
        "sl_pips": 20,        # GBP/USD: 20 pips SL (more volatile)
        "tp_pips": 60,        # GBP/USD: 60 pips TP (3:1)
        "pip_value": 0.0001,
        "min_volume": 0.01,
        "description": "British Pound"
    },
    "audusd": {
        "enabled": True,
        "mt5_symbol": "AUDUSDm",
        "sl_pips": 15,        # AUD/USD: 15 pips SL
        "tp_pips": 45,        # AUD/USD: 45 pips TP (3:1)
        "pip_value": 0.0001,
        "min_volume": 0.01,
        "description": "Australian Dollar"
    },
    "usdchf": {
        "enabled": True,
        "mt5_symbol": "USDCHFm",
        "sl_pips": 15,        # USD/CHF: 15 pips SL
        "tp_pips": 45,        # USD/CHF: 45 pips TP (3:1)
        "pip_value": 0.0001,
        "min_volume": 0.01,
        "description": "Swiss Franc"
    },
    "usdcad": {
        "enabled": True,
        "mt5_symbol": "USDCADm",
        "sl_pips": 15,        # USD/CAD: 15 pips SL
        "tp_pips": 45,        # USD/CAD: 45 pips TP (3:1)
        "pip_value": 0.0001,
        "min_volume": 0.01,
        "description": "Canadian Dollar"
    },
    "nzdusd": {
        "enabled": True,
        "mt5_symbol": "NZDUSDm",
        "sl_pips": 15,        # NZD/USD: 15 pips SL
        "tp_pips": 45,        # NZD/USD: 45 pips TP (3:1)
        "pip_value": 0.0001,
        "min_volume": 0.01,
        "description": "New Zealand Dollar"
    }
}

# Get list of enabled tickers for websocket subscription
def get_enabled_tickers():
    """Return list of tickers to subscribe to."""
    return [pair for pair, config in CURRENCY_PAIRS.items() if config.get("enabled", False)]

# Current trading pair (for single-pair mode, default to gold)
ACTIVE_PAIR = os.getenv("REX_ACTIVE_PAIR", "xauusd").lower()

def get_pair_config(pair_name):
    """Get configuration for a specific pair."""
    return CURRENCY_PAIRS.get(pair_name.lower(), CURRENCY_PAIRS["xauusd"])

# v7.2: STATE PERSISTENCE - Survive network disconnects
STATE_FILE = Path(__file__).parent / ".rex_state.pkl"
STATE_MAX_AGE = 300  # 5 minutes - if state is older, start fresh
RECONNECT_DELAY = 5  # Seconds to wait between reconnection attempts
MAX_RECONNECT_ATTEMPTS = 10  # Max attempts before giving up


def connect_websocket():
    """Connect to Tiingo websocket with retry logic."""
    global ws
    attempts = 0
    
    # v10.1: Get enabled tickers (default to all enabled pairs for multi-currency support)
    single_pair_mode = os.getenv("REX_SINGLE_PAIR", "false").lower() == "true"
    if single_pair_mode:
        tickers = [ACTIVE_PAIR]
    else:
        # Subscribe to all enabled pairs
        tickers = get_enabled_tickers()
        if not tickers:
            # Fallback to active pair if no enabled pairs found
            tickers = [ACTIVE_PAIR]
    
    while attempts < MAX_RECONNECT_ATTEMPTS:
        try:
            print(f"\n[CONNECT] Connecting to Tiingo websocket (attempt {attempts + 1}/{MAX_RECONNECT_ATTEMPTS})...")
            print(f"   Subscribing to: {', '.join(tickers)}")
            ws = create_connection(
                "wss://api.tiingo.com/fx", 
                sslopt={"cert_reqs": ssl.CERT_NONE},
                timeout=30
            )
            ws.send(json.dumps({
                'eventName': 'subscribe', 
                'authorization': TIINGO_KEY, 
                'eventData': {'tickers': tickers}
            }))
            print("[OK] Websocket connected!")
            return True
        except Exception as e:
            attempts += 1
            print(f"[ERR] Connection failed: {e}")
            if attempts < MAX_RECONNECT_ATTEMPTS:
                print(f"   Retrying in {RECONNECT_DELAY} seconds...")
                time.sleep(RECONNECT_DELAY)
    
    print("💀 Max reconnection attempts reached. Exiting.")
    return False


def save_state():
    """Save current state to disk for recovery after disconnect."""
    global closes, candles_history, active_trades, consecutive_losses, last_trade_time
    global warmup_complete, big_trend, failed_trade_levels, sr_levels, rsi_history
    
    state = {
        'timestamp': time.time(),
        'closes': closes[-50:] if len(closes) > 50 else closes,  # Keep last 50
        'candles_history': candles_history[-50:] if len(candles_history) > 50 else candles_history,
        'active_trades': active_trades,
        'consecutive_losses': consecutive_losses,
        'last_trade_time': last_trade_time,
        'warmup_complete': warmup_complete,
        'big_trend': big_trend,
        'failed_trade_levels': failed_trade_levels,
        'sr_levels': sr_levels,
        'rsi_history': rsi_history
    }
    
    try:
        with open(STATE_FILE, 'wb') as f:
            pickle.dump(state, f)
    except Exception as e:
        print(f"⚠️ Failed to save state: {e}")


def load_state():
    """Load state from disk if recent enough."""
    global closes, candles_history, active_trades, consecutive_losses, last_trade_time
    global warmup_complete, big_trend, failed_trade_levels, sr_levels, rsi_history
    
    if not STATE_FILE.exists():
        print("📂 No saved state found - starting fresh")
        return False
    
    try:
        with open(STATE_FILE, 'rb') as f:
            state = pickle.load(f)
        
        # Check if state is too old
        age = time.time() - state.get('timestamp', 0)
        if age > STATE_MAX_AGE:
            print(f"📂 Saved state is {age/60:.1f} minutes old (max {STATE_MAX_AGE/60:.0f}min) - starting fresh")
            STATE_FILE.unlink()  # Delete old state
            return False
        
        # Restore state
        closes = state.get('closes', [])
        candles_history = state.get('candles_history', [])
        active_trades = state.get('active_trades', [])
        consecutive_losses = state.get('consecutive_losses', 0)
        last_trade_time = state.get('last_trade_time', 0)
        warmup_complete = state.get('warmup_complete', False)
        big_trend = state.get('big_trend', 'NEUTRAL')
        failed_trade_levels = state.get('failed_trade_levels', [])
        sr_levels = state.get('sr_levels', {"support": [], "resistance": []})
        rsi_history = state.get('rsi_history', [])
        
        print(f"✅ RESTORED STATE from {age:.0f}s ago:")
        print(f"   - {len(closes)} candles, {len(active_trades)} active trades")
        print(f"   - Warmup: {'COMPLETE' if warmup_complete else f'{len(closes)}/5 candles'}")
        print(f"   - 1H Trend: {big_trend}")
        
        return True
    except Exception as e:
        print(f"⚠️ Failed to load state: {e} - starting fresh")
        return False

# ============================================================
# FAST SCALPING CONFIG - Tuned for quick trend captures
# ============================================================
# v9: 3:1 RISK/REWARD - Profitable at 25% win rate!
# v10: Now uses pair-specific config from CURRENCY_PAIRS
# ============================================================

# v10: Get SL/TP from active pair config (dynamic based on pair)
_pair_config = get_pair_config(ACTIVE_PAIR)
SL_PIPS = _pair_config["sl_pips"]  # Risk per trade (pair-specific)
TP_PIPS = _pair_config["tp_pips"]  # Reward per trade (3:1 ratio)
CURRENT_SYMBOL = _pair_config["mt5_symbol"]  # MT5 symbol for execution

MAX_TRADES = 1  # Only 1 trade at a time
MAX_CONSECUTIVE_LOSSES = 3  # Pause trading after 3 losses
MIN_MINUTES_BETWEEN_TRADES = 5  # Quality over quantity

# v9: TP EXTENSION - When near TP, extend instead of closing!
# Scales with the pair's TP size
TP_EXTENSION_THRESHOLD = 0.85  # When at 85% of TP, extend!
TP_EXTENSION_AMOUNT = SL_PIPS * 1.5  # Extend by 1.5x SL (e.g., $3 for gold)
TP_EXTENSION_LOCK = SL_PIPS * 2.0    # Lock 2R profit when extending

# Trailing Stop Parameters (kicks in at 1R profit)
TRAILING_TRIGGER = SL_PIPS  # When up 1R, start trailing
TRAILING_STEP = SL_PIPS * 0.25  # Trail in 0.25R increments
MAX_HOLD_MINUTES = 15  # v9: Longer hold for 3:1 targets
BREAKEVEN_BUFFER = SL_PIPS * 0.5  # Lock 0.5R minimum when trailing starts

# v6: EXHAUSTION PROTECTION - Don't trade after massive moves
EXHAUSTION_THRESHOLD = 20.0   # If price moved $20+ in 10min, market is exhausted
EXHAUSTION_RSI_LOW = 15       # RSI below this = extremely oversold, don't sell
EXHAUSTION_RSI_HIGH = 85      # RSI above this = extremely overbought, don't buy

# v7.1: RSI DANGER ZONES - ONLY for counter-trend trades (fixed over-filtering)
# Issue: Original v7 blocked ALL low-RSI sells, even during strong downtrends
# Fix: Only apply RSI filter when trading AGAINST the structure
RSI_OVERSOLD_DANGER = 28      # Was 35 - too restrictive (missed $14 drop)
RSI_OVERBOUGHT_DANGER = 72    # Was 65 - too restrictive
RSI_RECOVERY_LOOKBACK = 3     # Check if RSI is recovering from extreme

# v7.1: SUPPORT/RESISTANCE DETECTION (relaxed from v7)
SR_ZONE_SIZE = 2.00           # Was 1.50 - give more room
SR_TOUCHES_THRESHOLD = 3      # Was 2 - need more confirmation
SR_ZONE_AVOID_BUFFER = 0.30   # Was 0.50 - less restrictive

# v7.1: FAILED LEVEL TRACKING - Don't repeat mistakes at same price
FAILED_LEVEL_MEMORY = 3       # Was 5 - shorter memory
FAILED_LEVEL_COOLDOWN = 10    # Was 15 - shorter cooldown

# Technical Parameters
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
SMA_TOUCH_TOLERANCE = 2.50  # Price must be within $2.50 of SMA for pullback entry

# v7.2: WARMUP CONFIG - Reduced from 15 to 5 minutes
WARMUP_CANDLES = 5  # Only need 5 candles (5 min) to start trading
# Note: RSI won't be accurate until 15 candles, but we can trade with less data

closes = []
candles_history = []  # Store full candle data for pattern detection
current_min = None
current_hour = None  # Track for hourly review
current_session = None  # v10: Track current trading session for Slack notifications
candle = {"high": 0, "low": 99999, "close": 0, "open": 0}
last_trend_time = 0
big_trend = "NEUTRAL"
active_trades = []  # Track multiple open positions
consecutive_losses = 0  # Track losing streak
last_trade_time = 0  # Prevent rapid-fire trades
warmup_complete = False  # Wait for enough data before trading
last_hourly_review = 0  # Track when we last did hourly review

# v7: FAILED LEVEL TRACKING - Learn from mistakes
# Format: [(price, side, timestamp), ...]
failed_trade_levels = []

# v7: SUPPORT/RESISTANCE TRACKING
# Format: {"support": [price1, price2, ...], "resistance": [price1, price2, ...]}
sr_levels = {"support": [], "resistance": []}
price_bounces = []  # Track price bounces for S/R detection
rsi_history = []  # Track RSI for recovery detection

# ===== MOMENTUM PROTECTION (NEW) =====
# Prevents selling into rallies / buying into dumps
MOMENTUM_THRESHOLD = 5.0      # If price moved $5+ in last 10 mins, strong momentum
MOMENTUM_LOOKBACK = 10        # Minutes to check for momentum
TREND_REFRESH_FAST = 300      # 5 min refresh during volatile sessions
TREND_REFRESH_SLOW = 900      # 15 min refresh during calm sessions

# ===== PRICE MOVEMENT LOGGING (v5: added 1m/3m trends) =====
PRICE_LOG_FILE = Path(__file__).parent / "price_movements.csv"
PRICE_LOG_HEADERS = [
    "Timestamp", "Price", "Open", "High", "Low", "Close",
    "Change_1min", "Change_3min", "Change_5min", "Change_10min", "Change_15min",
    "SMA8", "RSI", "Trend_1H", "Trend_1m", "Trend_3m", "Trend_5m", "Trend_15m",
    "Momentum", "Structure", "Session"
]

def init_price_log():
    """Initialize price movement CSV for learning."""
    if not PRICE_LOG_FILE.exists():
        with open(PRICE_LOG_FILE, 'w', newline='') as f:
            csv.writer(f).writerow(PRICE_LOG_HEADERS)

def log_price_movement(timestamp, price, candle_data, closes_list, sma, rsi, 
                        trend_1h, trend_analysis, session):
    """Log price movement for learning patterns (v5: includes 1m/3m)."""
    try:
        # Calculate price changes over different periods
        change_1m = closes_list[-1] - closes_list[-2] if len(closes_list) >= 2 else 0
        change_3m = closes_list[-1] - closes_list[-4] if len(closes_list) >= 4 else 0
        change_5m = closes_list[-1] - closes_list[-6] if len(closes_list) >= 6 else 0
        change_10m = closes_list[-1] - closes_list[-11] if len(closes_list) >= 11 else 0
        change_15m = closes_list[-1] - closes_list[-16] if len(closes_list) >= 16 else 0
        
        row = [
            timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            f"{price:.2f}",
            f"{candle_data['open']:.2f}",
            f"{candle_data['high']:.2f}",
            f"{candle_data['low']:.2f}",
            f"{candle_data['close']:.2f}",
            f"{change_1m:.2f}",
            f"{change_3m:.2f}",
            f"{change_5m:.2f}",
            f"{change_10m:.2f}",
            f"{change_15m:.2f}",
            f"{sma:.2f}",
            f"{rsi:.0f}",
            trend_1h,
            trend_analysis.get('trend_1m', 'N/A'),    # NEW
            trend_analysis.get('trend_3m', 'N/A'),    # NEW
            trend_analysis.get('short_trend', 'N/A'),  # 5m
            trend_analysis.get('medium_trend', 'N/A'), # 15m
            trend_analysis.get('momentum', 'N/A'),
            trend_analysis.get('structure', 'N/A'),
            session
        ]
        
        with open(PRICE_LOG_FILE, 'a', newline='') as f:
            csv.writer(f).writerow(row)
    except Exception as e:
        pass  # Don't let logging errors affect trading

def check_momentum_override(side, closes_list):
    """
    Check if strong momentum should override the trade decision.
    Returns (should_block, reason)
    
    KEY FIX: Don't SELL during strong rallies, don't BUY during strong dumps
    """
    if len(closes_list) < MOMENTUM_LOOKBACK + 1:
        return False, "Not enough data for momentum check"
    
    # Calculate price change over lookback period
    recent_change = closes_list[-1] - closes_list[-(MOMENTUM_LOOKBACK + 1)]
    
    # Strong upward momentum
    if recent_change > MOMENTUM_THRESHOLD:
        if side == "SELL":
            return True, f"🚫 BLOCKED: Price up ${recent_change:.2f} in {MOMENTUM_LOOKBACK}min - DON'T SELL INTO RALLY"
        else:
            return False, f"✅ BUY aligns with rally (+${recent_change:.2f})"
    
    # Strong downward momentum
    if recent_change < -MOMENTUM_THRESHOLD:
        if side == "BUY":
            return True, f"🚫 BLOCKED: Price down ${abs(recent_change):.2f} in {MOMENTUM_LOOKBACK}min - DON'T BUY INTO DUMP"
        else:
            return False, f"✅ SELL aligns with dump (-${abs(recent_change):.2f})"
    
    return False, f"Momentum OK (${recent_change:+.2f} in {MOMENTUM_LOOKBACK}min)"


def check_rsi_danger_zone(side, rsi, closes_list, structure=""):
    """
    v7.1: SMART RSI protection - only blocks COUNTER-TREND trades.
    
    KEY FIX: v7 was too aggressive - blocked ALL low-RSI sells even during downtrends.
    The $14 drop (01:00-01:30) was missed because RSI was 16-37 but structure was DOWNTREND.
    
    NEW RULE: If trading WITH the trend structure, allow even at extreme RSI.
    Only block RSI extremes for counter-trend or consolidation trades.
    
    Returns (should_block, reason)
    """
    # Track RSI history for recovery detection
    global rsi_history
    rsi_history.append(rsi)
    if len(rsi_history) > 10:
        rsi_history = rsi_history[-10:]
    
    # v7.1: CHECK IF TRADING WITH TREND - if so, skip RSI restrictions
    is_downtrend = "LOWER_HIGHS_LOWS" in structure
    is_uptrend = "HIGHER_HIGHS_LOWS" in structure
    is_consolidating = "CONSOLIDATING" in structure or "EXPANDING" in structure or "Building" in structure
    
    if side == "SELL":
        # ✅ ALLOW: SELL during downtrend - trading WITH the trend
        if is_downtrend:
            return False, f"✅ RSI {rsi:.0f} OK - SELL with DOWNTREND structure"
        
        # ❌ BLOCK: SELL during uptrend with low RSI - COUNTER-TREND danger
        if is_uptrend and rsi < RSI_OVERSOLD_DANGER:
            return True, f"🛑 RSI {rsi:.0f} + UPTREND: Don't SELL oversold during uptrend (bounce likely)"
        
        # ⚠️ CAUTION: SELL during consolidation with low RSI
        if is_consolidating and rsi < RSI_OVERSOLD_DANGER:
            # Check if RSI is recovering (bouncing)
            if len(rsi_history) >= RSI_RECOVERY_LOOKBACK:
                recent_rsi = rsi_history[-RSI_RECOVERY_LOOKBACK:]
                min_recent = min(recent_rsi)
                if min_recent < 25 and rsi > min_recent + 3:  # RSI bouncing from extreme
                    return True, f"🛑 RSI RECOVERING in consolidation: {min_recent:.0f} → {rsi:.0f} - wait for direction"
            
            # Check if price is bouncing
            if len(closes_list) >= 3:
                recent_change = closes_list[-1] - closes_list[-3]
                if recent_change > 0.80:  # Strong bounce
                    return True, f"🛑 RSI {rsi:.0f} + BOUNCE ${recent_change:.2f} in consolidation - DON'T SELL"
    
    if side == "BUY":
        # ✅ ALLOW: BUY during uptrend - trading WITH the trend
        if is_uptrend:
            return False, f"✅ RSI {rsi:.0f} OK - BUY with UPTREND structure"
        
        # ❌ BLOCK: BUY during downtrend with high RSI - COUNTER-TREND danger
        if is_downtrend and rsi > RSI_OVERBOUGHT_DANGER:
            return True, f"🛑 RSI {rsi:.0f} + DOWNTREND: Don't BUY overbought during downtrend (pullback likely)"
        
        # ⚠️ CAUTION: BUY during consolidation with high RSI
        if is_consolidating and rsi > RSI_OVERBOUGHT_DANGER:
            # Check if RSI is falling
            if len(rsi_history) >= RSI_RECOVERY_LOOKBACK:
                recent_rsi = rsi_history[-RSI_RECOVERY_LOOKBACK:]
                max_recent = max(recent_rsi)
                if max_recent > 75 and rsi < max_recent - 3:  # RSI falling from extreme
                    return True, f"🛑 RSI FALLING in consolidation: {max_recent:.0f} → {rsi:.0f} - wait for direction"
            
            # Check if price is dropping
            if len(closes_list) >= 3:
                recent_change = closes_list[-1] - closes_list[-3]
                if recent_change < -0.80:  # Strong drop
                    return True, f"🛑 RSI {rsi:.0f} + DROP ${abs(recent_change):.2f} in consolidation - DON'T BUY"
    
    return False, f"RSI {rsi:.0f} OK for {side}"


def detect_support_resistance(closes_list, highs, lows):
    """
    v7: Detect support and resistance levels from recent price action.
    
    KEY FINDING: User shorted 3x at 4327-4329 (support zone) and all failed.
    Market was clearly defending this level.
    """
    global sr_levels, price_bounces
    
    if len(closes_list) < 20:
        return sr_levels
    
    # Detect bounces (price reversals)
    recent_closes = closes_list[-20:]
    
    for i in range(2, len(recent_closes) - 1):
        prev_move = recent_closes[i-1] - recent_closes[i-2]
        curr_move = recent_closes[i] - recent_closes[i-1]
        next_move = recent_closes[i+1] - recent_closes[i] if i+1 < len(recent_closes) else 0
        
        # Detect bottom (support touch): price was falling, then bounced up
        if prev_move < -0.30 and curr_move > 0.30:
            bounce_price = recent_closes[i-1]  # The low point
            price_bounces.append(("support", bounce_price, time.time()))
        
        # Detect top (resistance touch): price was rising, then reversed down
        if prev_move > 0.30 and curr_move < -0.30:
            bounce_price = recent_closes[i-1]  # The high point
            price_bounces.append(("resistance", bounce_price, time.time()))
    
    # Clean old bounces (older than 30 min)
    current_time = time.time()
    price_bounces[:] = [(t, p, ts) for t, p, ts in price_bounces if current_time - ts < 1800]
    
    # Group bounces into zones and count touches
    support_zones = {}
    resistance_zones = {}
    
    for bounce_type, price, ts in price_bounces:
        # Round to nearest SR_ZONE_SIZE
        zone_price = round(price / SR_ZONE_SIZE) * SR_ZONE_SIZE
        
        if bounce_type == "support":
            support_zones[zone_price] = support_zones.get(zone_price, 0) + 1
        else:
            resistance_zones[zone_price] = resistance_zones.get(zone_price, 0) + 1
    
    # Identify established S/R levels (2+ touches)
    sr_levels["support"] = [p for p, count in support_zones.items() if count >= SR_TOUCHES_THRESHOLD]
    sr_levels["resistance"] = [p for p, count in resistance_zones.items() if count >= SR_TOUCHES_THRESHOLD]
    
    return sr_levels


def check_sr_zone_conflict(side, price, sr_levels):
    """
    v7: Don't trade at established support/resistance zones.
    
    KEY FINDING: 3 SELL trades at 4327-4329 all failed because it was support.
    """
    # Don't SELL near support (price will bounce up)
    if side == "SELL":
        for support in sr_levels.get("support", []):
            if abs(price - support) < SR_ZONE_AVOID_BUFFER + SR_ZONE_SIZE:
                return True, f"🛑 SUPPORT ZONE: ${support:.2f} - DON'T SELL near support (3 trades failed here)"
    
    # Don't BUY near resistance (price will reverse down)
    if side == "BUY":
        for resistance in sr_levels.get("resistance", []):
            if abs(price - resistance) < SR_ZONE_AVOID_BUFFER + SR_ZONE_SIZE:
                return True, f"🛑 RESISTANCE ZONE: ${resistance:.2f} - DON'T BUY near resistance"
    
    return False, "Not at S/R zone"


def track_failed_level(side, price, pnl):
    """
    v7: Track price levels where trades failed.
    
    KEY FINDING: User made the same mistake 3 times at 4327-4329.
    This function remembers failed levels to avoid repeating mistakes.
    """
    global failed_trade_levels
    
    if pnl < 0:  # Trade was a loss
        failed_trade_levels.append((price, side, time.time()))
        
        # Keep only last N failed levels
        if len(failed_trade_levels) > FAILED_LEVEL_MEMORY:
            failed_trade_levels = failed_trade_levels[-FAILED_LEVEL_MEMORY:]


def check_failed_level(side, price):
    """
    v7: Check if we're trying to trade at a recently failed level.
    
    Returns (should_block, reason)
    """
    global failed_trade_levels
    
    current_time = time.time()
    
    # Clean expired entries
    failed_trade_levels[:] = [
        (p, s, ts) for p, s, ts in failed_trade_levels 
        if current_time - ts < FAILED_LEVEL_COOLDOWN * 60
    ]
    
    # Check if current price is near a failed level
    for failed_price, failed_side, timestamp in failed_trade_levels:
        if abs(price - failed_price) < SR_ZONE_SIZE:
            if failed_side == side:
                mins_ago = int((current_time - timestamp) / 60)
                cooldown_left = FAILED_LEVEL_COOLDOWN - mins_ago
                return True, f"🛑 FAILED LEVEL: {side} lost at ${failed_price:.2f} ({mins_ago}min ago) - AVOID for {cooldown_left}min"
    
    return False, "No recent failures at this level"


def check_accelerating_trend_conflict(side, trend_analysis):
    """
    v7.1: ONLY block clear counter-trend trades against strong momentum.
    
    KEY FIX: v7 was too aggressive - blocked sells during ACCEL_UP even in downtrend structure.
    Now we check structure first - if trading WITH structure, allow regardless of momentum.
    """
    momentum = trend_analysis.get('momentum', 'STABLE')
    medium_trend = trend_analysis.get('medium_trend', 'NEUTRAL')
    structure = trend_analysis.get('structure', '')
    
    is_downtrend = "LOWER_HIGHS_LOWS" in structure
    is_uptrend = "HIGHER_HIGHS_LOWS" in structure
    
    if side == "SELL":
        # ✅ ALLOW: SELL during downtrend structure (even if short-term momentum is up)
        if is_downtrend:
            return False, f"✅ SELL OK - DOWNTREND structure overrides momentum"
        
        # ❌ BLOCK: SELL during uptrend + ACCELERATING_UP (strong counter-trend)
        if is_uptrend and momentum == "ACCELERATING_UP":
            return True, f"🛑 UPTREND + ACCEL_UP: Strong rally - DON'T SELL"
        
        # ⚠️ CAUTION: SELL during ACCELERATING_UP in consolidation
        if momentum == "ACCELERATING_UP" and medium_trend == "BULLISH":
            return True, f"🛑 ACCEL_UP + BULLISH 15m: Momentum building - DON'T SELL into rally"
    
    if side == "BUY":
        # ✅ ALLOW: BUY during uptrend structure (even if short-term momentum is down)
        if is_uptrend:
            return False, f"✅ BUY OK - UPTREND structure overrides momentum"
        
        # ❌ BLOCK: BUY during downtrend + ACCELERATING_DOWN (strong counter-trend)
        if is_downtrend and momentum == "ACCELERATING_DOWN":
            return True, f"🛑 DOWNTREND + ACCEL_DOWN: Strong dump - DON'T BUY"
        
        # ⚠️ CAUTION: BUY during ACCELERATING_DOWN in consolidation
        if momentum == "ACCELERATING_DOWN" and medium_trend == "BEARISH":
            return True, f"🛑 ACCEL_DOWN + BEARISH 15m: Momentum building - DON'T BUY into dump"
    
    return False, f"Momentum {momentum} OK for {side}"


def check_short_term_trend_conflict(side, trend_analysis, big_trend="NEUTRAL", price=0, sma=0, rsi=50):
    """
    v5: Enhanced trend conflict check with 1m and 3m ultra-short trends.
    Prevents entering against immediate price direction.
    """
    trend_1m = trend_analysis.get('trend_1m', 'NEUTRAL')
    trend_3m = trend_analysis.get('trend_3m', 'NEUTRAL')
    change_1m = trend_analysis.get('change_1m', 0)
    change_3m = trend_analysis.get('change_3m', 0)
    short_trend = trend_analysis.get('short_trend', 'NEUTRAL')  # 5m
    medium_trend = trend_analysis.get('medium_trend', 'NEUTRAL')  # 15m
    momentum = trend_analysis.get('momentum', 'STABLE')
    structure = trend_analysis.get('structure', '')
    
    # ===== CRITICAL: 1m and 3m ULTRA-SHORT CONFLICT =====
    # If the last 1-3 minutes are moving against your trade, WAIT
    if side == "SELL":
        # Don't SELL if price just bounced UP
        if trend_1m == "BULLISH" and change_1m > 0.50:
            return True, f"🚫 1M BOUNCE: Price up ${change_1m:.2f} in last minute - don't SELL into bounce"
        if trend_3m == "BULLISH" and change_3m > 1.00:
            return True, f"🚫 3M RALLY: Price up ${change_3m:.2f} in last 3min - don't SELL into rally"
        # Don't SELL if 1m AND 3m are both BULLISH
        if trend_1m == "BULLISH" and trend_3m == "BULLISH":
            return True, f"🚫 MICRO UPTREND: 1m & 3m both BULLISH - wait for pullback to SELL"
    
    if side == "BUY":
        # Don't BUY if price just dumped
        if trend_1m == "BEARISH" and change_1m < -0.50:
            return True, f"🚫 1M DUMP: Price down ${abs(change_1m):.2f} in last minute - don't BUY into dump"
        if trend_3m == "BEARISH" and change_3m < -1.00:
            return True, f"🚫 3M CRASH: Price down ${abs(change_3m):.2f} in last 3min - don't BUY into crash"
        # Don't BUY if 1m AND 3m are both BEARISH
        if trend_1m == "BEARISH" and trend_3m == "BEARISH":
            return True, f"🚫 MICRO DOWNTREND: 1m & 3m both BEARISH - wait for bounce to BUY"
    
    # ===== COUNTER-TREND: Stricter requirements when trading against 1H =====
    if big_trend == "BULLISH" and side == "SELL":
        # Only allow SELL against BULLISH 1H if ALL short-term confirms bearish
        if not (medium_trend == "BEARISH" and short_trend == "BEARISH" and 
                trend_3m == "BEARISH" and momentum == "ACCELERATING_DOWN"):
            return True, f"🚫 FIGHTING 1H BULLISH: Need 15m+5m+3m BEARISH + ACCEL_DOWN to SELL"
        # Also check RSI
        if rsi > 45:
            return True, f"🚫 RSI {rsi:.0f} too high for counter-trend SELL"
    
    if big_trend == "BEARISH" and side == "BUY":
        # Only allow BUY against BEARISH 1H if ALL short-term confirms bullish
        if not (medium_trend == "BULLISH" and short_trend == "BULLISH" and 
                trend_3m == "BULLISH" and momentum == "ACCELERATING_UP"):
            return True, f"🚫 FIGHTING 1H BEARISH: Need 15m+5m+3m BULLISH + ACCEL_UP to BUY"
        # Also check RSI
        if rsi < 55:
            return True, f"🚫 RSI {rsi:.0f} too low for counter-trend BUY"
    
    # ===== STRUCTURE: Don't trade against strong structure =====
    if side == "SELL" and "HIGHER_HIGHS_LOWS" in structure:
        if not (medium_trend == "BEARISH" and short_trend == "BEARISH" and trend_3m == "BEARISH"):
            return True, f"🚫 UPTREND STRUCTURE: Need all timeframes BEARISH to SELL against uptrend"
    
    if side == "BUY" and "LOWER_HIGHS_LOWS" in structure:
        if not (medium_trend == "BULLISH" and short_trend == "BULLISH" and trend_3m == "BULLISH"):
            return True, f"🚫 DOWNTREND STRUCTURE: Need all timeframes BULLISH to BUY against downtrend"
    
    # ===== CHOPPY: Avoid low-conviction setups =====
    if "CONSOLIDATING" in structure or "Range" in structure:
        if momentum == "STABLE":
            return True, f"🚫 CHOPPY: Consolidating with STABLE momentum - wait for breakout"
        # v6: Even with momentum, be careful in consolidation
        strength = trend_analysis.get('strength', 50)
        if strength < 40:
            return True, f"🚫 WEAK: Consolidating with only {strength}% strength"
    
    # v6: MIXED SIGNALS - Avoid when timeframes conflict
    bullish_count = sum(1 for t in [trend_1m, trend_3m, short_trend, medium_trend] if t == "BULLISH")
    bearish_count = sum(1 for t in [trend_1m, trend_3m, short_trend, medium_trend] if t == "BEARISH")
    
    # If signals are mixed (e.g., 2 bullish, 2 bearish), skip
    if bullish_count >= 2 and bearish_count >= 2:
        return True, f"🚫 MIXED SIGNALS: {bullish_count} bullish vs {bearish_count} bearish timeframes - no clear direction"
    
    return False, "No trend conflict"

# ===== TECHNICAL INDICATORS =====
def calculate_rsi(prices, period=14):
    """Calculate RSI from price list."""
    if len(prices) < period + 1:
        return 50  # Neutral if not enough data
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    recent_deltas = deltas[-(period):]
    
    gains = [d if d > 0 else 0 for d in recent_deltas]
    losses = [-d if d < 0 else 0 for d in recent_deltas]
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def analyze_price_trend(prices):
    """
    Analyze price trend across multiple timeframes.
    Returns a dict with trend info for the AI brain.
    v5: Added 1m and 3m ultra-short trends for better entry timing
    """
    if len(prices) < 8:
        return {
            "trend_1m": "NEUTRAL",
            "trend_3m": "NEUTRAL",
            "short_trend": "NEUTRAL",
            "medium_trend": "NEUTRAL", 
            "momentum": "NEUTRAL",
            "strength": 50,
            "structure": "Building data",
            "change_1m": 0,
            "change_3m": 0,
            "short_change": 0,
            "medium_change": 0,
            "description": "Building data"
        }
    
    # ===== ULTRA-SHORT: 1-minute trend (last candle vs previous) =====
    if len(prices) >= 2:
        change_1m = prices[-1] - prices[-2]
        # Very sensitive: $0.15 move is significant for scalping
        trend_1m = "BULLISH" if change_1m > 0.15 else "BEARISH" if change_1m < -0.15 else "NEUTRAL"
    else:
        change_1m = 0
        trend_1m = "NEUTRAL"
    
    # ===== ULTRA-SHORT: 3-minute trend (last 3 candles) =====
    if len(prices) >= 4:
        change_3m = prices[-1] - prices[-4]
        # $0.25 move over 3 minutes
        trend_3m = "BULLISH" if change_3m > 0.25 else "BEARISH" if change_3m < -0.25 else "NEUTRAL"
    else:
        change_3m = 0
        trend_3m = "NEUTRAL"
    
    # Short-term (last 3-5 candles) - 5min trend
    short_len = min(5, len(prices))
    short_prices = prices[-short_len:]
    short_change = short_prices[-1] - short_prices[0]
    # Lower thresholds for gold scalping (0.30 = $0.30 move)
    short_trend = "BULLISH" if short_change > 0.30 else "BEARISH" if short_change < -0.30 else "NEUTRAL"
    
    # Medium-term (last 8-15 candles) - 15min trend
    medium_len = min(15, len(prices))
    medium_prices = prices[-medium_len:]
    medium_change = medium_prices[-1] - medium_prices[0]
    # Lower thresholds (0.80 = $0.80 move)
    medium_trend = "BULLISH" if medium_change > 0.80 else "BEARISH" if medium_change < -0.80 else "NEUTRAL"
    
    # Calculate momentum (rate of change)
    if len(prices) >= 6:
        recent_avg = sum(prices[-3:]) / 3
        older_avg = sum(prices[-6:-3]) / 3
        momentum_change = recent_avg - older_avg
        # Lower thresholds for momentum
        momentum = "ACCELERATING_UP" if momentum_change > 0.50 else "ACCELERATING_DOWN" if momentum_change < -0.50 else "STABLE"
    else:
        momentum = "STABLE"
    
    # Trend strength (0-100)
    # Based on how many of recent candles moved in trend direction
    check_len = min(8, len(prices) - 1)
    if check_len >= 3:
        ups = sum(1 for i in range(1, check_len + 1) if prices[-i] > prices[-i-1])
        if medium_trend == "BULLISH":
            strength = int((ups / check_len) * 100)
        elif medium_trend == "BEARISH":
            strength = int(((check_len - ups) / check_len) * 100)
        else:
            strength = 50
    else:
        strength = 50
    
    # Higher highs / Lower lows detection
    if len(prices) >= 8:
        half = len(prices) // 2
        recent_high = max(prices[-half:])
        older_high = max(prices[:-half])
        recent_low = min(prices[-half:])
        older_low = min(prices[:-half])
        
        if recent_high > older_high and recent_low > older_low:
            structure = "HIGHER_HIGHS_LOWS (Uptrend)"
        elif recent_high < older_high and recent_low < older_low:
            structure = "LOWER_HIGHS_LOWS (Downtrend)"
        elif recent_high > older_high and recent_low < older_low:
            structure = "EXPANDING (Volatile)"
        else:
            structure = "CONSOLIDATING (Range)"
    else:
        structure = "Building"
    
    # Build description for AI
    description = f"{medium_trend} trend with {momentum.lower().replace('_', ' ')} momentum. {structure}. Strength: {strength}/100"
    
    return {
        "trend_1m": trend_1m,           # NEW: Ultra-short 1-min
        "trend_3m": trend_3m,           # NEW: Ultra-short 3-min
        "change_1m": round(change_1m, 2),  # NEW: 1-min price change
        "change_3m": round(change_3m, 2),  # NEW: 3-min price change
        "short_trend": short_trend,     # 5-min trend
        "medium_trend": medium_trend,   # 15-min trend
        "momentum": momentum,
        "strength": strength,
        "structure": structure,
        "short_change": round(short_change, 2),
        "medium_change": round(medium_change, 2),
        "description": description
    }

def is_pullback_entry(price, sma, side):
    """Check if price has pulled back to SMA (good entry)."""
    distance = abs(price - sma)
    if distance > SMA_TOUCH_TOLERANCE:
        return False  # Too far from SMA
    
    # For BUY: price should be at or slightly above SMA (bouncing up)
    # For SELL: price should be at or slightly below SMA (bouncing down)
    if side == "BUY":
        return price >= sma - SMA_TOUCH_TOLERANCE and price <= sma + SMA_TOUCH_TOLERANCE
    else:  # SELL
        return price >= sma - SMA_TOUCH_TOLERANCE and price <= sma + SMA_TOUCH_TOLERANCE

def check_filters(side, price, sma, rsi, timestamp):
    """Check all entry filters. Returns (can_trade, reason)."""
    global consecutive_losses, last_trade_time, warmup_complete, active_trades
    
    # 0. Warmup check - need enough data (v7.2: reduced to 5 min)
    if not warmup_complete:
        return False, f"Warming up (need {WARMUP_CANDLES} candles)"
    
    # 1. Losing streak check
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return False, f"⏸️ PAUSED: {consecutive_losses} consecutive losses"
    
    # 2. Prevent rapid-fire trades (don't stack within X minutes)
    current_time = time.time()
    if (current_time - last_trade_time) < (MIN_MINUTES_BETWEEN_TRADES * 60):
        mins_left = MIN_MINUTES_BETWEEN_TRADES - int((current_time - last_trade_time) / 60)
        return False, f"Cooldown ({mins_left}min remaining)"
    
    # 3. Prevent conflicting positions (no BUY if SELL open, vice versa)
    for t in active_trades:
        if t['side'] != side:
            return False, f"Conflicting {t['side']} position open"
    
    # v6: EXHAUSTION FILTER - Don't trade at extremes after big moves
    if len(closes) >= 10:
        price_change_10m = closes[-1] - closes[-10]
        
        # Don't SELL after massive crash (market due for bounce)
        if side == "SELL" and price_change_10m < -EXHAUSTION_THRESHOLD:
            return False, f"🛑 EXHAUSTED: -${abs(price_change_10m):.0f} in 10min, bounce likely"
        
        # Don't BUY after massive rally (market due for pullback)
        if side == "BUY" and price_change_10m > EXHAUSTION_THRESHOLD:
            return False, f"🛑 EXHAUSTED: +${price_change_10m:.0f} in 10min, pullback likely"
    
    # v6: EXTREME RSI FILTER - Don't fight extreme readings
    if side == "SELL" and rsi < EXHAUSTION_RSI_LOW:
        return False, f"🛑 RSI {rsi:.0f} extremely oversold, don't SELL"
    if side == "BUY" and rsi > EXHAUSTION_RSI_HIGH:
        return False, f"🛑 RSI {rsi:.0f} extremely overbought, don't BUY"
    
    # v6: FINAL HOUR FILTER - Reduce trading frequency 17:00-18:00 UTC
    if timestamp.hour == 17:
        # During final hour, require stronger cooldown
        if (current_time - last_trade_time) < (8 * 60):  # 8 min cooldown instead of 5
            return False, f"⏰ Final hour: extended cooldown"
    
    return True, "All filters passed"

# CSV Setup
CSV_FILE = Path(__file__).parent / "rex_trades.csv"
CSV_HEADERS = ["TradeID", "Time", "Session", "Type", "Symbol", "Entry", "SL", "TP", "Status", "ExitPrice", "PnL", "Reason"]

def init_csv():
    if not CSV_FILE.exists():
        with open(CSV_FILE, 'w', newline='') as f:
            csv.writer(f).writerow(CSV_HEADERS)

def log_trade(trade_data):
    with open(CSV_FILE, 'a', newline='') as f:
        csv.writer(f).writerow(trade_data)

def update_trade_in_csv(trade_id, status, exit_price, pnl, reason):
    """Update an existing trade row when it closes."""
    rows = []
    with open(CSV_FILE, 'r', newline='') as f:
        rows = list(csv.reader(f))
    
    for row in rows:
        if row[0] == str(trade_id):
            # Updated indices for new Session column
            row[8] = status      # Status (was 7)
            row[9] = f"{exit_price:.2f}"   # ExitPrice (was 8)
            row[10] = f"{pnl:.2f}"         # PnL (was 9)
            row[11] = reason               # Reason (was 10)
            break
    
    with open(CSV_FILE, 'w', newline='') as f:
        csv.writer(f).writerows(rows)

def open_trade(side, entry_price, timestamp, trend_analysis, rsi, sma, detected_patterns=None):
    global active_trades, last_trade_time, mt5
    trade_id = int(time.time() * 100) % 10000000000
    last_trade_time = time.time()  # Record trade time for cooldown
    
    if side == "BUY":
        sl = entry_price - SL_PIPS
        tp = entry_price + TP_PIPS
    else:  # SELL
        sl = entry_price + SL_PIPS
        tp = entry_price - TP_PIPS
    
    # v8: EXECUTE ON MT5
    mt5_ticket = None
    actual_entry = entry_price
    if LIVE_TRADING and mt5:
        result = mt5.open_trade(side, sl, tp, comment="REX")
        if result['success']:
            mt5_ticket = result['ticket']
            actual_entry = result['entry_price']
        else:
            print(f"   ⚠️ MT5 failed: {result.get('error')} - Paper only")
    
    # Get market context for learning
    hour_utc = timestamp.hour
    weekday = timestamp.weekday()
    session = execution.get_market_session(hour_utc)
    price_action_type = execution.detect_price_action_type(closes, sma) if len(closes) >= 5 else "UNKNOWN"
    volatility = execution.calculate_volatility(closes) if len(closes) >= 20 else 0
    sma_position = "ABOVE" if entry_price > sma else "BELOW"
    
    new_trade = {
        "id": trade_id,
        "side": side,
        "entry": actual_entry,  # v8: Use MT5 price if available
        "sl": sl,
        "tp": tp,
        # v9: Store original risk & target distance so learning/R:R stays correct
        "original_tp_distance": TP_PIPS,
        "original_risk": SL_PIPS,
        "time": timestamp,
        "open_timestamp": time.time(),  # For hold time calculation
        "mt5_ticket": mt5_ticket,  # v8: MT5 ticket for live trades
        "is_live": mt5_ticket is not None,  # v8: Track if live
        
        # Store FULL context for learning when trade closes
        "entry_candles": candles_history.copy()[-20:] if len(candles_history) >= 20 else candles_history.copy(),
        "entry_closes": closes.copy()[-20:] if len(closes) >= 20 else closes.copy(),
        "entry_trend": trend_analysis,
        
        # Technical context at entry
        "entry_rsi": rsi,
        "entry_sma": sma,
        "entry_sma_position": sma_position,
        "entry_volatility": volatility,
        "entry_price_action": price_action_type,
        "entry_patterns": detected_patterns or [],
        
        # Time context
        "entry_hour_utc": hour_utc,
        "entry_weekday": weekday,
        "entry_session": session,
        
        # 1H trend at entry
        "entry_trend_1h": big_trend
    }
    active_trades.append(new_trade)
    
    trade_row = [
        trade_id,
        timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        session,  # v10: Added session column (LONDON, US, ASIAN, etc.)
        side,
        "xauusd",
        f"{entry_price:.2f}",
        f"{sl:.2f}",
        f"{tp:.2f}",
        "OPEN",
        "",
        "",
        ""
    ]
    log_trade(trade_row)
    
    # Enhanced logging
    rr_ratio = TP_PIPS / SL_PIPS
    live_tag = " 🔥LIVE" if mt5_ticket else " 📝PAPER"
    print(f"\n{'='*60}")
    print(f"📈 OPENED {side}{live_tag} #{len(active_trades)} @ {actual_entry:.2f}")
    if mt5_ticket:
        print(f"   🎫 MT5 Ticket: #{mt5_ticket}")
    print(f"   SL: {sl:.2f} | TP: {tp:.2f} | R:R 1:{rr_ratio:.1f}")
    print(f"   🔒 Trail at +${TRAILING_TRIGGER} | ⏱️ Max hold: {MAX_HOLD_MINUTES}min")
    print(f"   Session: {session} | Entry: {price_action_type}")
    print(f"   Context: 1H {big_trend} | RSI {rsi:.0f} | SMA {sma_position}")
    print(f"{'='*60}")
    
    # v7.2: Save state after trade opens (for recovery)
    save_state()
    
    return new_trade

def check_trade_exit(current_price):
    """Check if any active trades hit SL or TP, with trailing stop and time exit."""
    global active_trades, consecutive_losses, mt5
    trades_to_close = []
    
    for trade in active_trades:
        side = trade["side"]
        entry = trade["entry"]
        sl = trade["sl"]
        tp = trade["tp"]
        mt5_ticket = trade.get("mt5_ticket")
        is_live = trade.get("is_live", False)
        
        exit_reason = None
        exit_price = None
        
        # Calculate current P&L
        if side == "BUY":
            current_pnl = current_price - entry
        else:
            current_pnl = entry - current_price
        
        hold_minutes = (time.time() - trade.get("open_timestamp", time.time())) / 60
        
        # === v9: DYNAMIC SL + TP EXTENSION - RUN WITH WINNERS ===
        sl_updated = False
        tp_updated = False
        original_tp_distance = trade.get("original_tp_distance", TP_PIPS)
        
        # 0. v9: TP EXTENSION - When near TP (85%), EXTEND instead of closing!
        # This is the key to letting winners run
        tp_progress = current_pnl / original_tp_distance  # What % of TP have we reached?
        
        if tp_progress >= TP_EXTENSION_THRESHOLD and not trade.get("tp_extended"):
            # We're at 85%+ of TP - EXTEND the target!
            old_tp = trade["tp"]
            old_sl = trade["sl"]
            
            if side == "BUY":
                new_tp = trade["tp"] + TP_EXTENSION_AMOUNT  # Extend TP by $3
                new_sl = entry + TP_EXTENSION_LOCK  # Lock in $4 profit (2R)
                trade["tp"] = new_tp
                trade["sl"] = new_sl
            else:  # SELL
                new_tp = trade["tp"] - TP_EXTENSION_AMOUNT
                new_sl = entry - TP_EXTENSION_LOCK
                trade["tp"] = new_tp
                trade["sl"] = new_sl
            
            tp = trade["tp"]
            sl = trade["sl"]
            trade["tp_extended"] = True
            trade["extension_count"] = trade.get("extension_count", 0) + 1
            sl_updated = True
            tp_updated = True
            
            print(f"\n🚀 TP EXTENSION #{trade['extension_count']}! Progress: {tp_progress*100:.0f}%")
            print(f"   TP: {old_tp:.2f} → {new_tp:.2f} (+${TP_EXTENSION_AMOUNT})")
            print(f"   SL: {old_sl:.2f} → {new_sl:.2f} (locked ${TP_EXTENSION_LOCK} profit)")
        
        # 1. FULL TRAILING: After 1R profit ($2.00), trail aggressively
        if current_pnl >= TRAILING_TRIGGER:
            if side == "BUY":
                new_sl = entry + BREAKEVEN_BUFFER + ((current_pnl - TRAILING_TRIGGER) // TRAILING_STEP) * TRAILING_STEP
                if new_sl > trade["sl"]:
                    old_sl = trade["sl"]
                    trade["sl"] = new_sl
                    sl = new_sl
                    sl_updated = True
                    if not trade.get("trailing_logged"):
                        print(f"\n📈 TRAILING: SL {old_sl:.2f} → {new_sl:.2f} (lock ${new_sl - entry:.2f})")
                        trade["trailing_logged"] = True
            else:  # SELL
                new_sl = entry - BREAKEVEN_BUFFER - ((current_pnl - TRAILING_TRIGGER) // TRAILING_STEP) * TRAILING_STEP
                if new_sl < trade["sl"]:
                    old_sl = trade["sl"]
                    trade["sl"] = new_sl
                    sl = new_sl
                    sl_updated = True
                    if not trade.get("trailing_logged"):
                        print(f"\n📈 TRAILING: SL {old_sl:.2f} → {new_sl:.2f} (lock ${entry - new_sl:.2f})")
                        trade["trailing_logged"] = True
        
        # 2. BREAKEVEN: +$1.00 profit (0.5R) - protect the win
        elif current_pnl >= 1.00 and not trade.get("breakeven_set"):
            if side == "BUY":
                new_sl = entry + 0.30  # Lock $0.30 profit
                if new_sl > trade["sl"]:
                    old_sl = trade["sl"]
                    trade["sl"] = new_sl
                    sl = new_sl
                    sl_updated = True
                    trade["breakeven_set"] = True
                    print(f"\n🔒 BREAKEVEN: SL {old_sl:.2f} → {new_sl:.2f} (protected)")
            else:
                new_sl = entry - 0.30
                if new_sl < trade["sl"]:
                    old_sl = trade["sl"]
                    trade["sl"] = new_sl
                    sl = new_sl
                    sl_updated = True
                    trade["breakeven_set"] = True
                    print(f"\n🔒 BREAKEVEN: SL {old_sl:.2f} → {new_sl:.2f} (protected)")
        
        # v9: Update SL and/or TP on MT5 if changed
        if (sl_updated or tp_updated) and is_live and mt5 and mt5_ticket:
            mt5.modify_sl_tp(mt5_ticket, new_sl=sl, new_tp=tp if tp_updated else None)
        
        # === v8: TIME EXIT - ONLY FOR LOSERS ===
        if hold_minutes >= MAX_HOLD_MINUTES:
            if current_pnl <= 0:  # v8: Only time exit LOSERS
                exit_reason = f"TIME EXIT ({int(hold_minutes)}min)"
                exit_price = current_price
            elif current_pnl > 0 and not trade.get("time_warning"):
                # Winner at time limit - just warn, keep running with trailing SL
                print(f"\n⏰ TIME LIMIT: +${current_pnl:.2f} profit - running with trail!")
                trade["time_warning"] = True
        
        # === STANDARD SL/TP CHECK ===
        if exit_reason is None:
            if side == "BUY":
                if current_price <= sl:
                    # Distinguish between full SL, breakeven SL, and trailing SL
                    if trade.get("trailing_logged"):
                        exit_reason = "TRAILING SL"
                    elif trade.get("breakeven_set"):
                        exit_reason = "BREAKEVEN SL"
                    else:
                        exit_reason = "SL HIT"
                    exit_price = sl
                elif current_price >= tp:
                    exit_reason = "TP HIT"
                    exit_price = tp
            else:  # SELL
                if current_price >= sl:
                    if trade.get("trailing_logged"):
                        exit_reason = "TRAILING SL"
                    elif trade.get("breakeven_set"):
                        exit_reason = "BREAKEVEN SL"
                    else:
                        exit_reason = "SL HIT"
                    exit_price = sl
                elif current_price <= tp:
                    exit_reason = "TP HIT"
                    exit_price = tp
        
        if exit_reason:
            # v8: CLOSE ON MT5 FIRST
            if is_live and mt5 and mt5_ticket:
                close_result = mt5.close_trade(mt5_ticket, side)
                if close_result['success']:
                    exit_price = close_result.get('close_price', exit_price)
                    print(f"   🔥 MT5 CLOSED @ {exit_price:.2f}")
                else:
                    print(f"   ⚠️ MT5 close failed: {close_result.get('error')}")
            
            if side == "BUY":
                pnl = exit_price - entry
            else:
                pnl = entry - exit_price
            
            # Track consecutive losses
            if pnl < 0:
                consecutive_losses += 1
                # v7: Track failed price level to avoid repeating mistakes
                track_failed_level(side, entry, pnl)
            else:
                consecutive_losses = 0  # Reset on win
            
            update_trade_in_csv(trade["id"], "CLOSED", exit_price, pnl, exit_reason)
            
            # Calculate hold time
            hold_time_minutes = int((time.time() - trade.get("open_timestamp", time.time())) / 60)
            
            # Get entry context from trade object
            entry_trend = trade.get("entry_trend", {})
            
            # === ENHANCED LEARNING: Save comprehensive trade data ===
            try:
                # Use original_risk for correct R:R in learning (not the moved SL)
                original_risk = trade.get("original_risk", SL_PIPS)
                execution.save_trade_enhanced(
                    trade_id=trade["id"],
                    side=side,
                    entry=entry,
                    exit_price=exit_price,
                    sl=sl,
                    tp=tp,
                    pnl=pnl,
                    reason=exit_reason,
                    
                    # Trend context (stored at entry)
                    trend_1h=trade.get("entry_trend_1h", big_trend),
                    trend_15m=entry_trend.get("medium_trend", "NEUTRAL"),
                    trend_5m=entry_trend.get("short_trend", "NEUTRAL"),
                    momentum=entry_trend.get("momentum", "STABLE"),
                    structure=entry_trend.get("structure", "UNKNOWN"),
                    
                    # Technical indicators at entry
                    rsi=trade.get("entry_rsi", 50),
                    sma=trade.get("entry_sma", entry),
                    sma_position=trade.get("entry_sma_position", "NEUTRAL"),
                    
                    # Price action context
                    patterns_detected=trade.get("entry_patterns", []),
                    price_action_type=trade.get("entry_price_action", "UNKNOWN"),
                    volatility=trade.get("entry_volatility", 0),
                    
                    # Time context
                    hour_utc=trade.get("entry_hour_utc", 12),
                    weekday=trade.get("entry_weekday", 2),
                    session=trade.get("entry_session", "UNKNOWN"),
                    
                    # Trade metrics
                    hold_time_minutes=hold_time_minutes,
                    price_change_5m=entry_trend.get("short_change", 0),
                    price_change_15m=entry_trend.get("medium_change", 0),
                    risk_override=original_risk
                )
            except Exception as save_err:
                print(f"⚠️ Enhanced save error: {save_err}")
                # Fallback to basic save
                execution.save_trade(trade["id"], side, entry, pnl, exit_reason)
            
            # Learn from this trade (pattern learning)
            try:
                pattern_learner.learn_from_trade(
                    entry_candles=trade.get("entry_candles", []),
                    entry_closes=trade.get("entry_closes", []),
                    entry_trend=entry_trend,
                    trade_side=side,
                    entry_price=entry,
                    exit_price=exit_price,
                    pnl=pnl
                )
            except Exception as learn_err:
                print(f"⚠️ Learning error: {learn_err}")
            
            emoji = "✅" if pnl > 0 else "❌"
            streak_info = f" | Losses: {consecutive_losses}" if consecutive_losses > 0 else ""
            rr_achieved = abs(pnl) / SL_PIPS
            trail_info = " (TRAILED)" if trade.get("trailing_logged") else ""
            live_tag = " 🔥LIVE" if is_live else ""
            print(f"\n{emoji} CLOSED {side}{live_tag} @ {exit_price:.2f} | PnL: {pnl:+.2f} ({rr_achieved:.1f}R) | {exit_reason}{trail_info}")
            print(f"   Hold: {hold_time_minutes}min | Session: {trade.get('entry_session', 'N/A')}{streak_info}")
            trades_to_close.append(trade)
    
    # Remove closed trades
    for trade in trades_to_close:
        active_trades.remove(trade)
    
    # v7.2: Save state after trade closes (important for recovery)
    if trades_to_close:
        save_state()

init_csv()
init_price_log()  # Initialize price movement logging

# v8: Initialize MT5 for live trading
if LIVE_TRADING:
    mt5 = rex_mt5_executor.get_executor(volume=0.01)
    if mt5.test_connection():
        print("🔥 LIVE TRADING ENABLED")
    else:
        print("⚠️ MT5 connection failed - paper trading only")
        LIVE_TRADING = False
        mt5 = None

print("="*60)
print("REX v10.0 - Multi-Currency Scalping Bot")
print("="*60)
print(f"   ACTIVE PAIR: {ACTIVE_PAIR.upper()} ({_pair_config['description']})")
print(f"   MT5 SYMBOL:  {CURRENT_SYMBOL}")
print(f"   RISK/REWARD: SL {SL_PIPS} / TP {TP_PIPS} (3:1 ratio)")
print(f"   LIVE TRADING: {'ENABLED' if LIVE_TRADING else 'DISABLED'}")
print(f"   ")
print(f"   AVAILABLE PAIRS:")
for pair, cfg in CURRENCY_PAIRS.items():
    status = "[ON]" if cfg.get("enabled") else "[OFF]"
    print(f"      {status} {pair.upper()}: {cfg['description']} (SL:{cfg['sl_pips']} TP:{cfg['tp_pips']})")
print(f"   ")
print(f"   SETTINGS:")
print(f"      - MAX_HOLD: {MAX_HOLD_MINUTES}min | COOLDOWN: {MIN_MINUTES_BETWEEN_TRADES}min")
print(f"      - Trailing: +{TRAILING_TRIGGER} trigger | +{TRAILING_STEP} steps")
print(f"      - TP Extension: at {TP_EXTENSION_THRESHOLD*100:.0f}% TP")
print("="*60)

# v7.2: Load saved state if available (for recovery after disconnect)
state_loaded = load_state()

# v7.2: Connect to websocket with retry logic
if not connect_websocket():
    print("❌ Failed to connect. Exiting.")
    exit(1)

# v10: Initialize current session on startup
import datetime as dt
startup_time = dt.datetime.now(dt.timezone.utc)
current_session = execution.get_market_session(startup_time.hour)
print(f"\n🌍 INITIAL SESSION: {current_session} ({startup_time.strftime('%H:%M UTC')})")

# v10: Send startup session notification to Slack
try:
    slack_notifier.send_slack_message(
        f"🚀 *REX Bot Started*\n"
        f"Session: {current_session}\n"
        f"Time: {startup_time.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Pair: {ACTIVE_PAIR.upper()}\n"
        f"Live Trading: {'ENABLED' if LIVE_TRADING else 'DISABLED'}"
    )
except Exception as e:
    print(f"[WARN] Startup notification error: {e}")

last_state_save = time.time()
STATE_SAVE_INTERVAL = 30  # Save state every 30 seconds

while True:
    try:
        msg = json.loads(ws.recv())
        if 'data' not in msg or msg['data'][0] != 'Q': continue
        
        # 1. Process Tick
        price = msg['data'][5]
        timestamp = datetime.datetime.fromisoformat(msg['data'][2])
        
        if current_min is None: current_min = timestamp.minute
        if current_hour is None: current_hour = timestamp.hour
        
        # 2. Check if active trade hit SL/TP
        check_trade_exit(price)
        
        # === HOURLY STRATEGY REVIEW ===
        if timestamp.hour != current_hour:
            current_hour = timestamp.hour
            try:
                print("\n" + "="*60)
                print("HOURLY STRATEGY REVIEW")
                print("="*60)
                
                # Try hourly review with encoding safety
                try:
                    execution.print_hourly_review()
                except UnicodeEncodeError as enc_err:
                    print(f"[Encoding issue in review - skipping display]")
                
                # v9: Send Slack summary
                try:
                    slack_notifier.send_hourly_summary(
                        csv_path="rex_trades.csv",
                        include_ai=True
                    )
                    print("[OK] Slack hourly summary sent")
                except Exception as slack_err:
                    print(f"[WARN] Slack summary error: {slack_err}")
            except Exception as review_err:
                print(f"[WARN] Hourly review error: {review_err}")
        
        # 3. End of Minute: Process Strategy
        if timestamp.minute != current_min:
            # Refresh 1H Trend - faster during volatile sessions (US_OVERLAP)
            session = execution.get_market_session(timestamp.hour)
            
            # v10: Session change detection - send Slack notification
            if current_session is not None and session != current_session:
                # Session changed!
                try:
                    slack_notifier.send_session_notification(
                        old_session=current_session,
                        new_session=session,
                        timestamp=timestamp
                    )
                except Exception as sess_err:
                    print(f"[WARN] Session notification error: {sess_err}")
            
            # Update current session
            if current_session != session:
                current_session = session
                print(f"\n🌍 SESSION: {session} ({timestamp.strftime('%H:%M UTC')})")
            
            refresh_interval = TREND_REFRESH_FAST if session in ["US_OVERLAP", "LONDON"] else TREND_REFRESH_SLOW
            
            if (time.time() - last_trend_time) > refresh_interval:
                big_trend = execution.get_1hour_trend()
                last_trend_time = time.time()
                print(f"\n🔄 1H Trend refreshed: {big_trend} (interval: {refresh_interval//60}min)")

            closes.append(candle['close'])
            candles_history.append(candle.copy())  # Store full candle for pattern detection
            sma8 = sum(closes[-8:]) / 8 if len(closes) >= 8 else price
            rsi = calculate_rsi(closes, RSI_PERIOD)
            
            # Analyze price trend (multi-timeframe)
            trend_analysis = analyze_price_trend(closes)
            
            # Detect patterns
            detected_patterns, _ = pattern_learner.detect_candle_pattern(candles_history) if len(candles_history) >= 3 else (None, "")
            if detected_patterns:
                print(f"📍 Patterns detected: {', '.join(detected_patterns)}")
            
            # Check warmup status (v7.2: reduced to 5 min)
            if len(closes) >= WARMUP_CANDLES and not warmup_complete:
                warmup_complete = True
                rsi_status = "RSI active" if len(closes) >= RSI_PERIOD + 1 else f"RSI needs {RSI_PERIOD + 1 - len(closes)} more"
                print(f"\n✅ WARMUP COMPLETE - {len(closes)} candles collected, {rsi_status}")
            
            # Fetch AI Context (RAG)
            history = execution.get_memory(f"Gold price at {price} in {big_trend} trend")
            
            # AI Decision (with full trend context)
            trade = brain.get_decision(candle, history, big_trend, sma8, rsi, trend_analysis)
            sma_pos = "ABOVE" if candle['close'] > sma8 else "BELOW"
            warmup_status = "" if warmup_complete else f" | ⏳ Warmup {len(closes)}/{WARMUP_CANDLES}"
            
            # Enhanced logging with trend info
            confidence = trade.get('confidence', 5)
            print(f"\n{'='*60}")
            print(f"📊 Close: {candle['close']:.2f} | SMA8: {sma8:.2f} ({sma_pos}) | RSI: {rsi:.0f}")
            # v5: Show all timeframes including 1m and 3m
            print(f"📈 1H: {big_trend} | 15m: {trend_analysis['medium_trend']} | 5m: {trend_analysis['short_trend']} | 3m: {trend_analysis.get('trend_3m', 'N/A')} | 1m: {trend_analysis.get('trend_1m', 'N/A')}")
            print(f"💨 Momentum: {trend_analysis['momentum']} | 1m: ${trend_analysis.get('change_1m', 0):+.2f} | 3m: ${trend_analysis.get('change_3m', 0):+.2f}")
            
            # v7: Show RSI zone status
            rsi_zone = "🟢 SAFE" if RSI_OVERSOLD_DANGER <= rsi <= RSI_OVERBOUGHT_DANGER else "🔴 DANGER"
            print(f"📉 RSI Zone: {rsi_zone} | Structure: {trend_analysis['structure'][:20]}")
            
            # v7: Show S/R levels if any
            if sr_levels.get("support") or sr_levels.get("resistance"):
                sup_str = f"S:{sr_levels['support']}" if sr_levels.get("support") else ""
                res_str = f"R:{sr_levels['resistance']}" if sr_levels.get("resistance") else ""
                print(f"📍 S/R: {sup_str} {res_str}")
            
            # v7: Show failed levels if any
            if failed_trade_levels:
                recent_fails = [f"${p:.0f}({s})" for p, s, _ in failed_trade_levels[-3:]]
                print(f"⚠️ Failed Levels: {', '.join(recent_fails)}")
            
            print(f"🤖 AI: {trade['decision']} (Confidence: {confidence}/10){warmup_status}")
            
            # Log price movement for learning
            try:
                log_price_movement(
                    timestamp, candle['close'], candle, closes, sma8, rsi,
                    big_trend, trend_analysis, session
                )
            except Exception as log_err:
                pass
            
            # Open new trade if under max limit AND filters pass
            if trade['decision'] != "WAIT" and len(active_trades) < MAX_TRADES:
                can_trade, filter_reason = check_filters(trade['decision'], candle['close'], sma8, rsi, timestamp)
                
                if can_trade:
                    # ===== v7.1: RSI DANGER ZONE CHECK (NOW TREND-AWARE) =====
                    # v7.1 FIX: Now allows trading WITH trend even at extreme RSI
                    structure = trend_analysis.get('structure', '')
                    rsi_blocked, rsi_reason = check_rsi_danger_zone(trade['decision'], rsi, closes, structure)
                    if rsi_blocked:
                        print(f"\n{rsi_reason}")
                        can_trade = False
                        filter_reason = rsi_reason
                    
                    # ===== v7: ACCELERATING TREND CHECK =====
                    # Don't fight accelerating momentum
                    if can_trade:
                        accel_blocked, accel_reason = check_accelerating_trend_conflict(trade['decision'], trend_analysis)
                        if accel_blocked:
                            print(f"\n{accel_reason}")
                            can_trade = False
                            filter_reason = accel_reason
                    
                    # ===== v7: SUPPORT/RESISTANCE ZONE CHECK =====
                    # Based on backtest: 3 sells at 4327-4329 (support) all failed
                    if can_trade:
                        # Update S/R levels
                        highs = [c.get('high', c.get('close', 0)) for c in candles_history[-20:]] if len(candles_history) >= 20 else []
                        lows = [c.get('low', c.get('close', 0)) for c in candles_history[-20:]] if len(candles_history) >= 20 else []
                        detect_support_resistance(closes, highs, lows)
                        
                        sr_blocked, sr_reason = check_sr_zone_conflict(trade['decision'], candle['close'], sr_levels)
                        if sr_blocked:
                            print(f"\n{sr_reason}")
                            can_trade = False
                            filter_reason = sr_reason
                    
                    # ===== v7: FAILED LEVEL CHECK =====
                    # Don't repeat the same mistake at the same price
                    if can_trade:
                        failed_blocked, failed_reason = check_failed_level(trade['decision'], candle['close'])
                        if failed_blocked:
                            print(f"\n{failed_reason}")
                            can_trade = False
                            filter_reason = failed_reason
                    
                    # ===== MOMENTUM PROTECTION =====
                    if can_trade:
                        momentum_blocked, momentum_reason = check_momentum_override(trade['decision'], closes)
                        if momentum_blocked:
                            print(f"\n{momentum_reason}")
                            can_trade = False
                            filter_reason = momentum_reason
                    
                    # ===== SHORT-TERM TREND CONFLICT CHECK (v5: with 1m/3m ultra-short) =====
                    if can_trade:
                        trend_blocked, trend_reason = check_short_term_trend_conflict(
                            trade['decision'], trend_analysis, big_trend, candle['close'], sma8, rsi
                        )
                        if trend_blocked:
                            print(f"\n{trend_reason}")
                            can_trade = False
                            filter_reason = trend_reason
                
                if can_trade:
                    # Get market context
                    session = execution.get_market_session(timestamp.hour)
                    price_action = execution.detect_price_action_type(closes, sma8) if len(closes) >= 5 else "UNKNOWN"
                    
                    # === LEARNING MODE: Take trades to build history ===
                    # Check how much history we have
                    total_history = 0
                    try:
                        cond_analysis, _ = execution.get_similar_conditions(
                            trend_1h=big_trend,
                            trend_15m=trend_analysis['medium_trend'],
                            structure=trend_analysis['structure'],
                            momentum=trend_analysis['momentum'],
                            session=session,
                            price_action=price_action
                        )
                        if cond_analysis:
                            total_history = cond_analysis.get('total_similar', 0)
                    except:
                        pass
                    
                    learning_mode = total_history < 20
                    
                    if learning_mode:
                        # LEARNING MODE: No blocking, just log and take trades
                        print(f"\n📚 LEARNING MODE ({total_history}/20 trades)")
                        print(f"🎯 SIGNAL: {trade['decision']} - {trade['reasoning']}")
                        open_trade(
                            trade['decision'], 
                            candle['close'], 
                            timestamp, 
                            trend_analysis,
                            rsi,
                            sma8,
                            detected_patterns
                        )
                    else:
                        # ADAPTIVE MODE: Use history to filter
                        pre_trade_ok = True
                        try:
                            if cond_analysis:
                                side_win_rate = cond_analysis.get(
                                    'buy_win_rate' if trade['decision'] == 'BUY' else 'sell_win_rate', 0.5
                                )
                                print(f"\n🧠 ADAPTIVE MODE ({total_history} trades)")
                                print(f"   {trade['decision']} win rate: {side_win_rate*100:.0f}%")
                                print(f"   Recommended: {cond_analysis.get('recommended_side', 'N/A')}")
                                
                                # Only block if win rate is really bad
                                if side_win_rate < 0.25:
                                    print(f"⛔ BLOCKED: {trade['decision']} has <25% win rate")
                                    pre_trade_ok = False
                        except Exception as e:
                            pass
                        
                        if pre_trade_ok:
                            print(f"🎯 SIGNAL: {trade['decision']} - {trade['reasoning']}")
                            open_trade(
                                trade['decision'], 
                                candle['close'], 
                                timestamp, 
                                trend_analysis,
                                rsi,
                                sma8,
                                detected_patterns
                            )
                else:
                    print(f"⛔ FILTERED: {trade['decision']} - {filter_reason}")
            elif trade['decision'] == "WAIT":
                print(f"⏸️ WAIT: {trade['reasoning']}")

            # Reset Candle
            current_min = timestamp.minute
            candle = {"open": price, "high": price, "low": price, "close": price}
        else:
            candle['high'] = max(candle['high'], price)
            candle['low'] = min(candle['low'], price)
            candle['close'] = price
            # Show live price with trade status if active
            trade_info = ""
            if active_trades:
                total_pnl = 0
                for t in active_trades:
                    unrealized = (price - t['entry']) if t['side'] == "BUY" else (t['entry'] - price)
                    total_pnl += unrealized
                trade_info = f" | {len(active_trades)} trades PnL: {total_pnl:+.2f}"
            print(f"\r💰 {price:.2f} | H: {candle['high']:.2f} L: {candle['low']:.2f}{trade_info}    ", end="", flush=True)

        # v7.2: Periodically save state (inside try block for successful ticks)
        if time.time() - last_state_save > STATE_SAVE_INTERVAL:
            save_state()
            last_state_save = time.time()

    except WebSocketConnectionClosedException as e:
        print(f"\n🔌 Websocket disconnected: {e}")
        save_state()  # Save state before reconnecting
        print("💾 State saved. Attempting to reconnect...")
        if not connect_websocket():
            print("❌ Failed to reconnect. Exiting.")
            break
        print("✅ Reconnected! Resuming with saved state...")

    except Exception as e:
        error_str = str(e)
        if error_str == "0":  # Ignore subscription confirmation
            continue
        
        # Check if it's a connection-related error
        if any(x in error_str.lower() for x in ['connection', 'socket', 'timeout', 'broken pipe', 'reset']):
            print(f"\n🔌 Network error: {e}")
            save_state()
            print("💾 State saved. Attempting to reconnect...")
            if not connect_websocket():
                print("❌ Failed to reconnect. Exiting.")
                break
            print("✅ Reconnected! Resuming with saved state...")
        else:
            print(f"\nLoop Error: {e}")
            time.sleep(1)
