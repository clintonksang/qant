import simplejson as json
from websocket import create_connection
import datetime, os, time, ssl, requests, pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone
import brain, execution

load_dotenv()
TIINGO_KEY = os.getenv("TIINGO_KEY")
TICKER = "xauusd"
last_trade_time = 0

openai_client = OpenAI(api_key=os.getenv("OPENAI_KEY"))
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return 50.0
    delta = pd.Series(prices).diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return round(100 - (100 / (1 + rs.iloc[-1])), 2)

def get_pinecone_context(candle):
    query = f"PA: H:{candle['high']} L:{candle['low']} C:{candle['close']} RSI:{candle['rsi']}"
    xq = openai_client.embeddings.create(input=query, model="text-embedding-3-small").data[0].embedding
    res = index.query(vector=xq, top_k=3, include_metadata=True)
    context = "Past Outcomes:\n"
    for m in res['matches']:
        context += f"- {m['metadata']['description']} Resulted in {m['metadata']['outcome']}\n"
    return context

# --- START BOT ---
execution.initialize_exness()
ws = create_connection("wss://api.tiingo.com/fx", sslopt={"cert_reqs": ssl.CERT_NONE})
ws.send(json.dumps({'eventName':'subscribe', 'authorization':TIINGO_KEY, 'eventData':{'tickers':[TICKER]}}))

active_trades = []
closes = []
candle = {"high":-1, "low":99999, "close":0, "rsi":50}
current_min = None

while True:
    data = json.loads(ws.recv())['data']
    mid = data[5]
    this_min = datetime.datetime.fromisoformat(data[2]).minute
    
    if current_min is None: current_min = this_min
    if this_min != current_min:
        closes.append(candle['close'])
        candle['rsi'] = calculate_rsi(closes)
        
        # Monitor SL/TP
        for t in active_trades[:]:
            if (t['type']=='BUY' and (mid>=t['tp'] or mid<=t['sl'])) or \
               (t['type']=='SELL' and (mid<=t['tp'] or mid>=t['sl'])):
                reason = "TP HIT" if (t['type']=='BUY' and mid>=t['tp']) or (t['type']=='SELL' and mid<=t['tp']) else "SL HIT"
                execution.close_trade(t['id'], mid, reason, t['type'], t['entry'])
                active_trades.remove(t)

        if (time.time() - last_trade_time) > 900:
            ctx = get_pinecone_context(candle)
            dec = json.loads(brain.get_trade_decision(candle, ctx))
            if dec['decision'] != "WAIT":
                t_id = execution.place_trade(dec['decision'], TICKER, 0.01, dec['stop_loss'], dec['take_profit'], mid)
                active_trades.append({'id':t_id, 'type':dec['decision'], 'entry':mid, 'sl':dec['stop_loss'], 'tp':dec['take_profit']})
                last_trade_time = time.time()
        
        current_min = this_min
        candle = {"high":mid, "low":mid, "close":mid, "rsi":candle['rsi']}
    else:
        candle['high'] = max(candle['high'], mid)
        candle['low'] = min(candle['low'], mid)
        candle['close'] = mid
    print(f"LIVE: {mid} | RSI: {candle['rsi']} | Open: {len(active_trades)}", end="\r")