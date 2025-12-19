"""
Currency Pair Arbitrage Bot - Main Entry Point
Monitors multiple currency pairs for correlation divergence opportunities

Uses WebSocket connection to Tiingo for real-time FX data
"""

import simplejson as json
from websocket import create_connection
import datetime
import os
import time
import ssl
from pathlib import Path
from dotenv import load_dotenv

# Load environment from parent directory
load_dotenv(Path(__file__).parent.parent / ".env")

# Import our modules
from config import (
    ALL_TICKERS, 
    POSITIVE_PAIRS, 
    NEGATIVE_PAIRS,
    BUFFER_SIZE,
    MIN_DATA_POINTS,
    LEARNING_TRADES_REQUIRED,
    LIVE_TRADING,
    MT5_API_URL,
    MT5_VOLUME,
    get_session
)
from correlation_engine import CorrelationEngine
from signal_detector import SignalDetector
from arbitrage_brain import evaluate_signal, analyze_market_regime
from position_manager import PositionManager
import pair_memory

# ============================================================
# INITIALIZATION
# ============================================================

TIINGO_KEY = os.getenv("TIINGO_KEY")
if not TIINGO_KEY:
    raise ValueError("TIINGO_KEY not set in environment")

print("🚀 Arbitrage Bot Starting...")

# ============================================================
# WEBSOCKET CONNECTION MANAGEMENT
# ============================================================

def connect_websocket(max_retries=5, retry_delay=5):
    """
    Connect to Tiingo WebSocket with automatic retry.
    
    Args:
        max_retries: Maximum connection attempts
        retry_delay: Initial delay between retries (seconds)
        
    Returns:
        WebSocket connection object or None if failed
    """
    for attempt in range(1, max_retries + 1):
        try:
            print(f"📡 Connecting to Tiingo WebSocket... (Attempt {attempt}/{max_retries})")
            ws = create_connection(
                "wss://api.tiingo.com/fx",
                sslopt={"cert_reqs": ssl.CERT_NONE},
                timeout=10
            )
            
            # Subscribe to all currency pairs
            print(f"📈 Subscribing to {len(ALL_TICKERS)} pairs: {', '.join(ALL_TICKERS)}")
            ws.send(json.dumps({
                'eventName': 'subscribe',
                'authorization': TIINGO_KEY,
                'eventData': {'tickers': ALL_TICKERS}
            }))
            
            print(f"✅ WebSocket connected successfully!")
            return ws
            
        except Exception as e:
            if attempt < max_retries:
                wait_time = retry_delay * attempt  # Exponential backoff
                print(f"⚠️ Connection failed: {e}")
                print(f"   Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"❌ Failed to connect after {max_retries} attempts: {e}")
                return None
    
    return None

def reconnect_websocket(ws, max_retries=5, retry_delay=5):
    """
    Reconnect to WebSocket if connection is lost.
    Preserves existing positions and state.
    """
    try:
        if ws:
            ws.close()
    except:
        pass
    
    print(f"\n🔄 Reconnecting WebSocket...")
    return connect_websocket(max_retries, retry_delay)

# Initial WebSocket connection
ws = connect_websocket()
if not ws:
    print("❌ Cannot start bot without WebSocket connection")
    exit(1)

# Initialize components
correlation_engine = CorrelationEngine()
signal_detector = SignalDetector()
position_manager = PositionManager()

# Price buffers for each ticker (rolling window)
price_buffers = {ticker: [] for ticker in ALL_TICKERS}
candle_buffers = {ticker: {"high": 0, "low": 99999, "close": 0, "open": 0} for ticker in ALL_TICKERS}

# State tracking
current_minute = None
last_correlation_check = 0
last_regime_check = 0
warmup_complete = False
ticks_received = {ticker: 0 for ticker in ALL_TICKERS}

CORRELATION_CHECK_INTERVAL = 60      # Check correlations every 60 seconds
REGIME_CHECK_INTERVAL = 900          # Check market regime every 15 minutes
STATUS_PRINT_INTERVAL = 300          # Print status every 5 minutes
last_status_print = 0
last_tick_time = time.time()  # Track last successful tick

print(f"\n{'='*60}")
print(f"🎯 ARBITRAGE BOT INITIALIZED")
print(f"{'='*60}")

# Display trading mode
trade_mode = "🟢 LIVE TRADING" if LIVE_TRADING else "📝 PAPER TRADING"
print(f"\n   Mode: {trade_mode}")
if LIVE_TRADING:
    print(f"   MT5 API: {MT5_API_URL}")
    print(f"   Volume: {MT5_VOLUME} lots")

print(f"\n   Monitoring Pairs:")
for p in POSITIVE_PAIRS:
    print(f"   + {p['name']}: {p['pair_a'].upper()}/{p['pair_b'].upper()} (corr: {p['expected_corr']})")
for p in NEGATIVE_PAIRS:
    print(f"   - {p['name']}: {p['pair_a'].upper()}/{p['pair_b'].upper()} (corr: {p['expected_corr']})")
print(f"{'='*60}")
print(f"\n⏳ Warming up... Need {MIN_DATA_POINTS} data points per pair\n")

# ============================================================
# MAIN LOOP
# ============================================================

while True:
    try:
        # Check if WebSocket is connected
        if not ws:
            print("⚠️ WebSocket not connected, attempting reconnect...")
            ws = reconnect_websocket(None, max_retries=5, retry_delay=5)
            if not ws:
                print("❌ Cannot continue without WebSocket. Waiting 10 seconds...")
                time.sleep(10)
                continue
        
        # Receive WebSocket message
        msg = json.loads(ws.recv())
        
        # Skip non-quote messages
        if 'data' not in msg or msg['data'][0] != 'Q':
            continue
        
        # Parse tick data
        ticker = msg['data'][1].lower()
        price = msg['data'][5]
        timestamp = datetime.datetime.fromisoformat(msg['data'][2])
        
        # Skip unknown tickers
        if ticker not in price_buffers:
            continue
        
        ticks_received[ticker] += 1
        last_tick_time = time.time()  # Update last successful tick time
        
        # Update candle
        candle = candle_buffers[ticker]
        if candle['open'] == 0:
            candle['open'] = price
        candle['high'] = max(candle['high'], price)
        candle['low'] = min(candle['low'], price)
        candle['close'] = price
        
        # Initialize minute tracking
        if current_minute is None:
            current_minute = timestamp.minute
        
        # ============================================================
        # CHECK POSITION EXITS (Every tick)
        # ============================================================
        if position_manager.active_positions:
            closed = position_manager.check_exits(price_buffers, signal_detector)
            
            # Save closed positions to Pinecone for learning
            for pos in closed:
                try:
                    # Reconstruct signal from position
                    signal_for_learning = {
                        'pair_name': pos['pair_name'],
                        'pair_a': pos['pair_a'],
                        'pair_b': pos['pair_b'],
                        'price_a': pos['entry_a'],
                        'price_b': pos['entry_b'],
                        'spread': pos.get('entry_spread', 0),
                        'z_score': pos['entry_z_score'],
                        'mean_spread': 0,  # Not stored
                        'correlation': pos.get('entry_correlation', 0.95),
                        'expected_corr': 0.95,
                        'correlation_health': 'HEALTHY',
                        'is_positive_pair': True,
                        'signal_type': 'DIVERGENCE',
                        'strength': pos.get('signal_strength', 'MODERATE'),
                        'action_a': pos['action_a'],
                        'action_b': pos['action_b'],
                        'timestamp': pos['timestamp']
                    }
                    
                    pair_memory.save_arbitrage_trade(
                        signal=signal_for_learning,
                        outcome=pos['outcome'],
                        pnl_a=pos['pnl_a'],
                        pnl_b=pos['pnl_b'],
                        hold_time_minutes=pos['hold_minutes'],
                        exit_reason=pos['exit_reason'],
                        exit_z_score=pos['exit_z_score']
                    )
                except Exception as e:
                    print(f"⚠️ Failed to save learning: {e}")
        
        # ============================================================
        # END OF MINUTE PROCESSING
        # ============================================================
        if timestamp.minute != current_minute:
            
            # Store candle close prices
            for t in ALL_TICKERS:
                if candle_buffers[t]['close'] > 0:
                    price_buffers[t].append(candle_buffers[t]['close'])
                    # Trim buffer
                    if len(price_buffers[t]) > BUFFER_SIZE:
                        price_buffers[t].pop(0)
            
            # Check warmup status
            min_data = min(len(price_buffers[t]) for t in ALL_TICKERS)
            if not warmup_complete and min_data >= MIN_DATA_POINTS:
                warmup_complete = True
                print(f"\n✅ WARMUP COMPLETE - All pairs have {min_data}+ data points")
                print(f"🎯 Arbitrage detection ACTIVE\n")
            
            # ============================================================
            # CORRELATION & SIGNAL DETECTION (Every minute after warmup)
            # ============================================================
            if warmup_complete and (current_time - last_correlation_check) > CORRELATION_CHECK_INTERVAL:
                last_correlation_check = current_time
                
                # Calculate correlations
                correlations = correlation_engine.calculate_all(price_buffers)
                
                # Check for divergence signals
                signals = signal_detector.check_divergences(correlations, price_buffers)
                
                # Process each signal
                for signal in signals:
                    # Check if we can open a position
                    can_open, reason = position_manager.can_open_position(signal['pair_name'])
                    if not can_open:
                        print(f"⛔ Cannot trade {signal['pair_name']}: {reason}")
                        continue
                    
                    # Get historical context from Pinecone
                    history_analysis, history_summary = pair_memory.get_similar_divergences(signal)
                    
                    # Check learning mode
                    learning_progress = pair_memory.get_learning_progress()
                    learning_mode = learning_progress.get('total_trades', 0) < LEARNING_TRADES_REQUIRED
                    
                    if learning_mode:
                        print(f"\n📚 LEARNING MODE ({learning_progress.get('total_trades', 0)}/{LEARNING_TRADES_REQUIRED} trades)")
                        # In learning mode, take trades to build history
                        ai_decision = {
                            'action': 'TRADE',
                            'confidence': 6,
                            'reasoning': 'Learning mode - building history',
                            'risk_level': 'MEDIUM'
                        }
                    else:
                        # AI evaluation with historical context
                        ai_decision = evaluate_signal(signal, history_analysis)
                        print(f"\n🤖 AI Decision: {ai_decision['action']} (Confidence: {ai_decision['confidence']}/10)")
                        print(f"   Reason: {ai_decision['reasoning']}")
                        
                        if history_analysis:
                            print(f"   History: {history_analysis['similar_count']} similar, {history_analysis['win_rate']*100:.0f}% win rate")
                    
                    # Execute trade if AI says go
                    if ai_decision['action'] in ['TRADE', 'REDUCE_SIZE']:
                        position_manager.open_position(signal, ai_decision)
            
            # ============================================================
            # MARKET REGIME CHECK (Every 15 minutes)
            # ============================================================
            if warmup_complete and (current_time - last_regime_check) > REGIME_CHECK_INTERVAL:
                last_regime_check = current_time
                
                correlations = correlation_engine.calculate_all(price_buffers)
                regime = analyze_market_regime(correlations, price_buffers)
                
                print(f"\n🌍 MARKET REGIME: {regime.get('regime', 'UNKNOWN')}")
                print(f"   Arb Favorable: {'✅' if regime.get('arb_favorable', True) else '⛔'}")
                if regime.get('avoid_pairs'):
                    print(f"   Avoid: {', '.join(regime['avoid_pairs'])}")
                print(f"   Notes: {regime.get('notes', 'N/A')}")
            
            # ============================================================
            # PERIODIC STATUS PRINT
            # ============================================================
            if warmup_complete and (current_time - last_status_print) > STATUS_PRINT_INTERVAL:
                last_status_print = current_time
                
                session = get_session(timestamp.hour)
                print(f"\n{'='*60}")
                print(f"📊 STATUS UPDATE - {timestamp.strftime('%H:%M')} UTC ({session})")
                print(f"{'='*60}")
                
                # Correlation status
                correlation_engine.print_status()
                
                # Position status
                position_manager.print_status()
                
                # Spread status
                if correlations:
                    spreads = signal_detector.get_current_spreads(correlations, price_buffers)
                    print(f"\n📈 SPREAD STATUS:")
                    for name, data in spreads.items():
                        z = data['z_score']
                        status = data['status']
                        emoji = '🔴' if status == 'SIGNAL' else '🟡' if status == 'ELEVATED' else '🟢'
                        print(f"   {emoji} {name}: Z={z:.2f} ({status})")
                
                # Correlation trends
                print(f"\n📉 CORRELATION TRENDS:")
                for corr in correlations:
                    trend = correlation_engine.get_correlation_trend(corr['name'], periods=10)
                    if trend['trend'] not in ['UNKNOWN', 'BUILDING']:
                        trend_emoji = '📈' if trend['trend'] == 'STRENGTHENING' else '📉' if trend['trend'] == 'WEAKENING' else '➡️'
                        print(f"   {trend_emoji} {corr['name']}: {trend['message']}")
            
            # Reset candles for new minute
            current_minute = timestamp.minute
            for t in ALL_TICKERS:
                candle_buffers[t] = {"high": 0, "low": 99999, "close": 0, "open": 0}
        
        # ============================================================
        # LIVE PRICE DISPLAY (Tick level)
        # ============================================================
        else:
            # Show live prices
            if warmup_complete:
                pos_info = ""
                if position_manager.active_positions:
                    status = position_manager.get_status()
                    live_tag = " [LIVE]" if status.get('live_trading') else ""
                    pos_info = f" | Positions: {status['active_positions']}{live_tag} | PnL: {status['total_pnl']:+.1f}"
                
                mode_icon = "🟢" if LIVE_TRADING else "📝"
                print(f"\r{mode_icon} {ticker.upper()}: {price:.5f}{pos_info}    ", end="", flush=True)
            else:
                # During warmup, show progress
                min_data = min(len(price_buffers[t]) for t in ALL_TICKERS if ticks_received[t] > 0)
                print(f"\r⏳ Warming up: {min_data}/{MIN_DATA_POINTS} points | {ticker.upper()}: {price:.5f}    ", end="", flush=True)
    
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        if position_manager.active_positions:
            print(f"⚠️ Closing {len(position_manager.active_positions)} open positions...")
            position_manager.force_close_all(price_buffers, "SHUTDOWN")
        try:
            ws.close()
        except:
            pass
        print("👋 Goodbye!")
        break
    
    except (ConnectionError, OSError, BrokenPipeError, ConnectionResetError) as e:
        # WebSocket connection lost - attempt reconnection
        print(f"\n⚠️ WebSocket connection lost: {e}")
        print(f"   Active positions: {len(position_manager.active_positions)}")
        print(f"   Preserving state and reconnecting...")
        
        # Reconnect with exponential backoff
        ws = reconnect_websocket(ws, max_retries=10, retry_delay=3)
        
        if not ws:
            print("❌ Failed to reconnect. Retrying in 30 seconds...")
            time.sleep(30)
            ws = reconnect_websocket(None, max_retries=10, retry_delay=3)
        
        if ws:
            print("✅ Reconnected! Resuming operations...")
            # Reset warmup if we lost too much data
            min_data = min(len(price_buffers[t]) for t in ALL_TICKERS if price_buffers[t])
            if min_data < MIN_DATA_POINTS:
                warmup_complete = False
                print(f"⏳ Re-warming up... Need {MIN_DATA_POINTS} data points (have {min_data})")
        else:
            print("❌ Critical: Cannot reconnect. Exiting...")
            break
    
    except Exception as e:
        error_str = str(e)
        # Ignore subscription confirmations and empty messages
        if error_str not in ["0", "", "'NoneType' object has no attribute 'recv'"]:
            print(f"\n⚠️ Error: {e}")
            print(f"   Type: {type(e).__name__}")
            
            # Check if WebSocket is still alive
            try:
                ws.ping()
            except:
                print("   WebSocket appears dead, will reconnect on next iteration...")
                ws = None
        
        time.sleep(1)

