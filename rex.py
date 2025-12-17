import simplejson as json
from websocket import create_connection
import datetime, os, time, ssl, csv
from pathlib import Path
import brain, execution
import pattern_learner  # Pattern learning agent

# Initialize
TIINGO_KEY = os.getenv("TIINGO_KEY")
ws = create_connection("wss://api.tiingo.com/fx", sslopt={"cert_reqs": ssl.CERT_NONE})
ws.send(json.dumps({'eventName':'subscribe', 'authorization':TIINGO_KEY, 'eventData':{'tickers':["xauusd"]}}))

# Risk Parameters
SL_PIPS = 2.50  # Stop Loss in dollars
TP_PIPS = 5.00  # Take Profit in dollars (2:1 R:R)
MAX_TRADES = 2  # Max concurrent trades (reduced to prevent over-exposure)
MAX_CONSECUTIVE_LOSSES = 4  # Pause trading after this many losses
MIN_MINUTES_BETWEEN_TRADES = 5  # Don't stack trades too quickly

# Technical Parameters
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
SMA_TOUCH_TOLERANCE = 2.50  # Price must be within $2.50 of SMA for pullback entry

closes = []
candles_history = []  # Store full candle data for pattern detection
current_min = None
candle = {"high": 0, "low": 99999, "close": 0, "open": 0}
last_trend_time = 0
big_trend = "NEUTRAL"
active_trades = []  # Track multiple open positions
consecutive_losses = 0  # Track losing streak
last_trade_time = 0  # Prevent rapid-fire trades
warmup_complete = False  # Wait for enough data before trading

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
    """
    if len(prices) < 8:
        return {
            "short_trend": "NEUTRAL",
            "medium_trend": "NEUTRAL", 
            "momentum": "NEUTRAL",
            "strength": 50,
            "structure": "Building data",
            "short_change": 0,
            "medium_change": 0,
            "description": "Building data"
        }
    
    # Short-term (last 3-5 candles) - for scalping
    short_len = min(5, len(prices))
    short_prices = prices[-short_len:]
    short_change = short_prices[-1] - short_prices[0]
    # Lower thresholds for gold scalping (0.30 = $0.30 move)
    short_trend = "BULLISH" if short_change > 0.30 else "BEARISH" if short_change < -0.30 else "NEUTRAL"
    
    # Medium-term (last 8-15 candles) - for direction  
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
        "short_trend": short_trend,
        "medium_trend": medium_trend,
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
    
    # 0. Warmup check - need enough data
    if not warmup_complete:
        return False, f"Warming up (need {RSI_PERIOD + 1} candles)"
    
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
    
    # RSI and Pullback filters REMOVED - we follow trends only!
    # The AI brain decides based on 1H trend, not RSI
    
    return True, "All filters passed"

# CSV Setup
CSV_FILE = Path(__file__).parent / "rex_trades.csv"
CSV_HEADERS = ["TradeID", "Time", "Type", "Symbol", "Entry", "SL", "TP", "Status", "ExitPrice", "PnL", "Reason"]

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
            row[7] = status
            row[8] = f"{exit_price:.2f}"
            row[9] = f"{pnl:.2f}"
            row[10] = reason
            break
    
    with open(CSV_FILE, 'w', newline='') as f:
        csv.writer(f).writerows(rows)

def open_trade(side, entry_price, timestamp, trend_analysis, rsi, sma, detected_patterns=None):
    global active_trades, last_trade_time
    trade_id = int(time.time() * 100) % 10000000000
    last_trade_time = time.time()  # Record trade time for cooldown
    
    if side == "BUY":
        sl = entry_price - SL_PIPS
        tp = entry_price + TP_PIPS
    else:  # SELL
        sl = entry_price + SL_PIPS
        tp = entry_price - TP_PIPS
    
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
        "entry": entry_price,
        "sl": sl,
        "tp": tp,
        "time": timestamp,
        "open_timestamp": time.time(),  # For hold time calculation
        
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
    print(f"\n{'='*60}")
    print(f"📈 OPENED {side} #{len(active_trades)} @ {entry_price:.2f}")
    print(f"   SL: {sl:.2f} | TP: {tp:.2f} | R:R 1:{rr_ratio:.1f}")
    print(f"   Session: {session} | Entry: {price_action_type}")
    print(f"   Context: 1H {big_trend} | RSI {rsi:.0f} | SMA {sma_position}")
    print(f"{'='*60}")
    return new_trade

def check_trade_exit(current_price):
    """Check if any active trades hit SL or TP."""
    global active_trades, consecutive_losses
    trades_to_close = []
    
    for trade in active_trades:
        side = trade["side"]
        entry = trade["entry"]
        sl = trade["sl"]
        tp = trade["tp"]
        
        exit_reason = None
        exit_price = None
        
        if side == "BUY":
            if current_price <= sl:
                exit_reason = "SL HIT"
                exit_price = sl
            elif current_price >= tp:
                exit_reason = "TP HIT"
                exit_price = tp
        else:  # SELL
            if current_price >= sl:
                exit_reason = "SL HIT"
                exit_price = sl
            elif current_price <= tp:
                exit_reason = "TP HIT"
                exit_price = tp
        
        if exit_reason:
            if side == "BUY":
                pnl = exit_price - entry
            else:
                pnl = entry - exit_price
            
            # Track consecutive losses
            if pnl < 0:
                consecutive_losses += 1
            else:
                consecutive_losses = 0  # Reset on win
            
            update_trade_in_csv(trade["id"], "CLOSED", exit_price, pnl, exit_reason)
            
            # Calculate hold time
            hold_time_minutes = int((time.time() - trade.get("open_timestamp", time.time())) / 60)
            
            # Get entry context from trade object
            entry_trend = trade.get("entry_trend", {})
            
            # === ENHANCED LEARNING: Save comprehensive trade data ===
            try:
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
                    price_change_15m=entry_trend.get("medium_change", 0)
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
            print(f"\n{emoji} CLOSED {side} @ {exit_price:.2f} | PnL: {pnl:+.2f} ({rr_achieved:.1f}R) | {exit_reason}")
            print(f"   Hold: {hold_time_minutes}min | Session: {trade.get('entry_session', 'N/A')}{streak_info}")
            trades_to_close.append(trade)
    
    # Remove closed trades
    for trade in trades_to_close:
        active_trades.remove(trade)

init_csv()
print("🚀 Rex v2 (LangChain Edition) is Live...")

while True:
    try:
        msg = json.loads(ws.recv())
        if 'data' not in msg or msg['data'][0] != 'Q': continue
        
        # 1. Process Tick
        price = msg['data'][5]
        timestamp = datetime.datetime.fromisoformat(msg['data'][2])
        
        if current_min is None: current_min = timestamp.minute
        
        # 2. Check if active trade hit SL/TP
        check_trade_exit(price)
        
        # 3. End of Minute: Process Strategy
        if timestamp.minute != current_min:
            # Refresh 1H Trend every 15 mins
            if (time.time() - last_trend_time) > 900:
                big_trend = execution.get_1hour_trend()
                last_trend_time = time.time()

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
            
            # Check warmup status
            if len(closes) >= RSI_PERIOD + 1 and not warmup_complete:
                warmup_complete = True
                print(f"\n✅ WARMUP COMPLETE - {len(closes)} candles collected, RSI active")
            
            # Fetch AI Context (RAG)
            history = execution.get_memory(f"Gold price at {price} in {big_trend} trend")
            
            # AI Decision (with full trend context)
            trade = brain.get_decision(candle, history, big_trend, sma8, rsi, trend_analysis)
            sma_pos = "ABOVE" if candle['close'] > sma8 else "BELOW"
            warmup_status = "" if warmup_complete else f" | ⏳ Warmup {len(closes)}/{RSI_PERIOD + 1}"
            
            # Enhanced logging with trend info
            confidence = trade.get('confidence', 5)
            print(f"\n{'='*60}")
            print(f"📊 Close: {candle['close']:.2f} | SMA8: {sma8:.2f} ({sma_pos}) | RSI: {rsi:.0f}")
            print(f"📈 1H: {big_trend} | 15m: {trend_analysis['medium_trend']} | 5m: {trend_analysis['short_trend']}")
            print(f"💨 Momentum: {trend_analysis['momentum']} | Structure: {trend_analysis['structure']}")
            print(f"🤖 AI: {trade['decision']} (Confidence: {confidence}/10){warmup_status}")
            
            # Open new trade if under max limit AND filters pass
            if trade['decision'] != "WAIT" and len(active_trades) < MAX_TRADES:
                can_trade, filter_reason = check_filters(trade['decision'], candle['close'], sma8, rsi, timestamp)
                
                if can_trade:
                    # Get market context for pre-trade analysis
                    session = execution.get_market_session(timestamp.hour)
                    price_action = execution.detect_price_action_type(closes, sma8) if len(closes) >= 5 else "UNKNOWN"
                    
                    # === COMPREHENSIVE PRE-TRADE ANALYSIS ===
                    pre_trade_ok = True
                    try:
                        pre_analysis = execution.get_comprehensive_pre_trade_analysis(
                            side=trade['decision'],
                            trend_1h=big_trend,
                            trend_15m=trend_analysis['medium_trend'],
                            structure=trend_analysis['structure'],
                            momentum=trend_analysis['momentum'],
                            session=session,
                            price_action=price_action,
                            patterns=detected_patterns
                        )
                        
                        print(f"\n📊 PRE-TRADE ANALYSIS:")
                        print(f"   Confidence: {pre_analysis['confidence']}/100")
                        
                        if pre_analysis['advantages']:
                            print(f"   ✅ {' | '.join(pre_analysis['advantages'][:2])}")
                        if pre_analysis['warnings']:
                            print(f"   ⚠️  {' | '.join(pre_analysis['warnings'][:2])}")
                        
                        print(f"   {pre_analysis.get('recommendation', 'No recommendation')}")
                        
                        # Block trade if analysis says no
                        if not pre_analysis.get('should_trade', True):
                            print(f"⛔ BLOCKED BY HISTORY: {pre_analysis.get('recommendation', 'Low confidence')}")
                            pre_trade_ok = False
                            
                    except Exception as analysis_err:
                        # Continue without pre-trade analysis if it fails
                        print(f"⚠️ Pre-trade analysis unavailable: {analysis_err}")
                    
                    # Check pattern history (existing code)
                    pattern_prediction = None
                    if len(closes) >= 10 and pre_trade_ok:
                        try:
                            pattern_prediction = pattern_learner.predict_with_patterns(
                                candles_history, closes, trend_analysis
                            )
                            if pattern_prediction and pattern_prediction.get('pattern_history'):
                                win_rate = pattern_prediction['pattern_history'].get('win_rate', 0.5)
                                print(f"📚 Pattern History: {win_rate*100:.0f}% win rate on similar setups")
                                
                                # If history shows poor performance, skip this trade
                                if win_rate < 0.35:
                                    print(f"⛔ PATTERN FILTER: Historical win rate too low ({win_rate*100:.0f}%)")
                                    pre_trade_ok = False
                        except Exception as pattern_err:
                            pass  # Continue without pattern check
                    
                    if pre_trade_ok:
                        print(f"\n🎯 SIGNAL: {trade['decision']} - {trade['reasoning']}")
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

    except Exception as e:
        if str(e) != "0":  # Ignore subscription confirmation
            print(f"\nLoop Error: {e}")
        time.sleep(1)
