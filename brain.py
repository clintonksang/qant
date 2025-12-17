import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

def get_trade_decision(candle_data, historical_context):
    rsi = candle_data.get('rsi', 50.0)
    system_prompt = f"""
    You are Rex v3.2. STRICT CONFLUENCE Sniper.
    RSI: {rsi}
    PAST CONTEXT: {historical_context}
    
    RULES:
    1. NO trade on RSI alone. 
    2. BUY: RSI < 35 + Hammer/Engulfing + Context confirms bounce.
    3. SELL: RSI > 65 + ShootingStar/Engulfing + Context confirms drop.
    4. MATH: SL = $2.00 buffer from wick. TP = 3x that distance.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Candle: {candle_data}"}],
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    except: return None