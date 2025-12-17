import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

def get_trade_decision(candle_data, historical_context): # <--- NEW ARGUMENT
    # EXTRACT RSI
    rsi = candle_data.get('rsi', 50.0)
    
    rsi_context = "Neutral"
    if rsi < 30: rsi_context = "OVERSOLD (SCREAMING BUY)"
    elif rsi > 70: rsi_context = "OVERBOUGHT (SCREAMING SELL)"
    elif rsi < 40: rsi_context = "Weak/Bearish"
    elif rsi > 60: rsi_context = "Strong/Bullish"

    system_prompt = f"""
    You are Rex v3.0, a RAG-Augmented Sniper. You MUST use the historical data provided 
    to validate the current signal and strictly adhere to the 1:3 R:R rule.
    
    CURRENT RSI: {rsi} ({rsi_context})
    
    1. HISTORICAL CONTEXT (Pinecone Data):
    {historical_context}
    
    2. STRATEGY & RISK RULES:
       - R:R RULE: Must aim for 3x profit of your risk.
       - SL Buffer: $2.00 minimum from wick (Entry - SL distance).
       - TP Target: (3 * SL Distance).
       - BUY: RSI < 35 OR Hammer on Support, AND past similar events resulted in a bounce.
       - SELL: RSI > 65 OR Shooting Star on Resistance, AND past similar events resulted in a drop.
       
    Output JSON: decision (BUY/SELL/WAIT), entry_price, stop_loss, take_profit, reasoning.
    """

    user_prompt = f"""
    Analyze candle: {candle_data}. Synthesize the best action based on the CURRENT RSI 
    and the OUTCOME of SIMILAR PAST EVENTS. If the historical context conflicts 
    with the pattern, prioritize the historical outcome.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error talking to Brain: {e}")
        return None