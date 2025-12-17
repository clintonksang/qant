import simplejson as json
from websocket import create_connection
import datetime
import os
import time
import ssl
import requests
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec # <--- PINE CONE IMPORT
import brain
import execution

# 1. TRADING CONFIGURATION
load_dotenv()
TIINGO_KEY = os.getenv("TIINGO_KEY")
TIINGO_WS_URL = "wss://api.tiingo.com/fx"
TIINGO_HIST_URL = "https://api.tiingo.com/tiingo/fx/xauusd/prices"
TICKER = "xauusd"

# RAG CONFIGURATION
OPENAI_KEY = os.getenv("OPENAI_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY") # <--- NEW
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "rex-trading-history")
EMBEDDING_MODEL = "text-embedding-3-small"
openai_client = OpenAI(api_key=OPENAI_KEY)

# RISK & DISCIPLINE
MIN_MOVE_TO_WAKE_AI = 0.50 
COOLDOWN_SECONDS = 900  
last_trade_time = 0

# STATE
closes = [] 
RSI_PERIOD = 14
active_trades = [] 

# --- RAG FUNCTIONS ---
def initialize_pinecone():
    """Initializes Pinecone connection and index object."""
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        
        # Check if the index exists. If not, inform the user they must create it.
        if PINECONE_INDEX_NAME not in pc.list_indexes().names:
             print(f"⚠️ Pinecone Index '{PINECONE_INDEX_NAME}' not found.")
             print("RAG will be disabled. Create the index to enable full context.")
             return None

        return pc.Index(PINECONE_INDEX_NAME)
        
    except Exception as e:
        print(f"⚠️ Pinecone Initialization Failed (Check Key/Name): {e}")
        return None

def get_pinecone_context(current_candle, pinecone_index):
    """Generates query, embeds it, and retrieves context from Pinecone."""
    if pinecone_index is None:
        return "Historical Context: RAG disabled. No historical context available."
    
    query_text = (
        f"The current 1-minute candle closed at {current_candle['close']}. "
        f"RSI is {current_candle['rsi']}. Imbalance is {current_candle.get('volume_imbalance', 'Neutral')}. "
        f"Find historical market events with similar RSI and recent price action on XAUUSD."
    )
    
    try:
        # 1. Create a vector embedding of the query
        query_embedding = openai_client.embeddings.create(
            input=[query_text],
            model=EMBEDDING_MODEL
        ).data[0].embedding
        
        # 2. Search Pinecone for top 3 matches
        results = pinecone_index.query(
            vector=query_embedding,
            top_k=3,
            include_metadata=True
        )
        
        # 3. Format results for the LLM prompt
        context = "Historical Context:\n"
        if not results['matches']:
            return "Historical Context: No highly relevant past events found."
            
        for i, match in enumerate(results['matches']):
            metadata = match['metadata']
            context += (
                f"- Match {i+1} (Similarity: {round(match['score'], 4)}):\n"
                f"  Past Description: {metadata.get('description', 'No description')}\n"
                f"  Past Outcome: {metadata.get('outcome', 'No outcome recorded')}\n"
            )
            
        return context
        
    except Exception as e:
        return f"Historical Context: RAG search failed with error: {e}"


# --- UTILITY FUNCTIONS ---
def get_historical_data():
    # ... (same as before) ...
    print("⏳ Downloading recent market history...")
    headers = {'Content-Type': 'application/json', 'Authorization': f'Token {TIINGO_KEY}'}
    params = {'resampleFreq': '1min', 'token': TIINGO_KEY}
    
    try:
        response = requests.get(TIINGO_HIST_URL, params=params, headers=headers, timeout=10)
        data = response.json()
        if isinstance(data, list):
            hist_closes = [d['close'] for d in data]
            print(f"✅ Loaded {len(hist_closes)} historical candles.")
            return hist_closes[-100:]
        return []
    except:
        return []
        
def calculate_rsi(prices, period=14):
    # ... (same as before) ...
    if len(prices) < period + 1: return 50.0 
    series = pd.Series(prices)
    delta = series.diff().dropna()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.iloc[:period].mean()
    avg_loss = loss.iloc[:period].mean()
    for i in range(period, len(gain)):
        avg_gain = ((avg_gain * (period - 1)) + gain.iloc[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + loss.iloc[i]) / period
    if avg_loss == 0: return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


# --- INITIALIZATION ---
print(f"🔥 Rex v3.0 (RAG Enabled) starting up. Target: {TICKER}")

# RAG Initialization
pinecone_index = initialize_pinecone()

# Core Initialization
closes = get_historical_data()
current_rsi = calculate_rsi(closes)
execution.initialize_exness() 

ws = create_connection(TIINGO_WS_URL, sslopt={"cert_reqs": ssl.CERT_NONE})
subscribe = {'eventName': 'subscribe', 'authorization': TIINGO_KEY, 'eventData': {'thresholdLevel': 5, 'tickers': [TICKER]}}
ws.send(json.dumps(subscribe))

current_minute = None
candle = {"symbol": TICKER, "open": None, "high": -float('inf'), "low": float('inf'), "close": None, "rsi": current_rsi}
print(f"📊 Initial RSI: {current_rsi}")


# --- MAIN LOOP ---
while True:
    try:
        response = ws.recv()
        msg = json.loads(response)
        
        if msg.get('messageType') == 'A' and 'data' in msg:
            data = msg['data']
            if data[0] == 'Q':
                dt_obj = datetime.datetime.fromisoformat(data[2])
                this_minute = dt_obj.minute
                mid_price = data[5]

                # A. LIVE TRADE MONITOR
                for trade in active_trades[:]:
                    # ... (SL/TP check logic remains here) ...
                    if trade['type'] == 'BUY':
                        if mid_price >= trade['tp']:
                            execution.close_trade(trade['id'], mid_price, "TP HIT", "BUY", trade['entry'], trade['volume'])
                            active_trades.remove(trade)
                        elif mid_price <= trade['sl']:
                            execution.close_trade(trade['id'], mid_price, "SL HIT", "BUY", trade['entry'], trade['volume'])
                            active_trades.remove(trade)
                            
                    elif trade['type'] == 'SELL':
                        if mid_price <= trade['tp']:
                            execution.close_trade(trade['id'], mid_price, "TP HIT", "SELL", trade['entry'], trade['volume'])
                            active_trades.remove(trade)
                        elif mid_price >= trade['sl']:
                            execution.close_trade(trade['id'], mid_price, "SL HIT", "SELL", trade['entry'], trade['volume'])
                            active_trades.remove(trade)


                # B. CANDLE LOGIC
                if current_minute is None: current_minute = this_minute
                    
                if this_minute != current_minute:
                    # Update History & RSI
                    closes.append(candle['close'])
                    if len(closes) > 100: closes.pop(0)
                    rsi_val = calculate_rsi(closes)
                    candle['rsi'] = rsi_val 
                    
                    candle_size = round(candle['high'] - candle['low'], 2)
                    print(f"\n[CANDLE CLOSED] Size: ${candle_size} | RSI: {rsi_val}")

                    # DECISION TIME (Check Volatility & Cooldown)
                    if candle_size >= MIN_MOVE_TO_WAKE_AI:
                        if (time.time() - last_trade_time) < COOLDOWN_SECONDS:
                            print(f"⏳ Cooldown active... ({int(COOLDOWN_SECONDS - (time.time() - last_trade_time))}s left)")
                        else:
                            # 1. RAG Retrieval
                            historical_context = get_pinecone_context(candle, pinecone_index)
                            print(f"🔎 RAG Context Retrieved:\n{historical_context}")
                            
                            # 2. Call RAG-Aware Brain
                            ai_response = brain.get_trade_decision(candle, historical_context)
                            
                            if ai_response:
                                import json as j
                                try:
                                    d = j.loads(ai_response)
                                    action = d.get("decision", "WAIT").upper()
                                    sl = d.get("stop_loss", 0.0)
                                    tp = d.get("take_profit", 0.0)
                                    reason = d.get("reasoning", "")

                                    print(f"🤖 AI Decision: {action} | {reason}")

                                    if action in ["BUY", "SELL"]:
                                        t_id = execution.place_trade(action, TICKER, 0.01, sl, tp, mid_price)
                                        active_trades.append({'id': t_id, 'type': action, 'entry': mid_price, 'sl': sl, 'tp': tp, 'volume': 0.01})
                                        last_trade_time = time.time()
                                        
                                except Exception as e:
                                    print(f"Error parsing AI: {e}")
                    else:
                        print("💤 Flat. Holding.")

                    # Reset Candle
                    current_minute = this_minute
                    candle["open"] = mid_price
                    candle["high"] = mid_price
                    candle["low"] = mid_price
                    candle["close"] = mid_price
                
                else:
                    # Live Candle Updates
                    if candle["open"] is None: candle["open"] = mid_price
                    if mid_price > candle["high"]: candle["high"] = mid_price
                    if mid_price < candle["low"]: candle["low"] = mid_price
                    candle["close"] = mid_price
                    
                    pnl_tracker = f"Open Trades: {len(active_trades)}"
                    print(f"Live: {mid_price} | RSI: {candle['rsi']} | {pnl_tracker}   ", end="\r")

    except KeyboardInterrupt:
        print("\nStopping...")
        break
    except Exception as e:
        print(e)
        break

execution.shutdown()