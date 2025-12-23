import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# 1. Load variables immediately - use explicit path to ensure .env is found
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# 2. Check for API key before initializing
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError(
        f"OPENAI_API_KEY environment variable is not set. "
        f"Please set it in your .env file at {env_path} or export it in your shell."
    )

# 3. Pass the key explicitly to ensure the validator sees it
llm = ChatOpenAI(
    model="gpt-4o", 
    temperature=0,
    api_key=api_key
)
def get_decision(candle, history, trend, sma8, rsi=50, trend_analysis=None):
    """
    Enhanced decision making with full trend context.
    trend_analysis contains: short_trend, medium_trend, momentum, strength, structure, description
    """
    price = candle['close']
    above_sma = price > sma8
    sma_status = "ABOVE SMA8 (Rocket)" if above_sma else "BELOW SMA8 (Dumpster)"
    
    # Default trend analysis if not provided
    if trend_analysis is None:
        trend_analysis = {
            "short_trend": "NEUTRAL",
            "medium_trend": trend,
            "momentum": "NEUTRAL",
            "strength": 50,
            "structure": "Unknown",
            "description": f"{trend} trend"
        }
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are Rex v3, a momentum-aware Gold Scalper. KEY RULE: Never fight strong momentum!

===== TRENDS =====
1H TREND: {trend}
15min: {medium_trend} (moved ${medium_change})
5min: {short_trend} (moved ${short_change})
Momentum: {momentum}
Structure: {structure}
Strength: {strength}/100

===== PRICE =====
Price: {close} | SMA8: {sma8} ({sma_status})
RSI: {rsi}

===== MOMENTUM-FIRST DECISION LOGIC =====

**CRITICAL: MOMENTUM OVERRIDES 1H TREND!**

If 15m moved +$3.00 or more (strong rally):
- DON'T SELL even if 1H is BEARISH
- BUY or WAIT only

If 15m moved -$3.00 or more (strong dump):
- DON'T BUY even if 1H is BULLISH
- SELL or WAIT only

**ALIGNMENT TRADING (Best trades):**
- BUY when: 1H BULLISH + 5m/15m BULLISH + momentum ACCELERATING_UP
- SELL when: 1H BEARISH + 5m/15m BEARISH + momentum ACCELERATING_DOWN
- These are HIGH confidence trades (8-10)

**COUNTER-TREND REDUCTION (v10.1):**
- When 1H is BEARISH: REDUCE SELL trades - prefer WAIT or BUY (only sell if very strong bearish alignment)
- When 1H is BULLISH: REDUCE BUY trades - prefer WAIT or SELL (only buy if very strong bullish alignment)
- Counter-trend trades should have LOWER confidence (4-6) and require exceptional alignment
- With-trend trades (BUY in BULLISH, SELL in BEARISH) are preferred but still need alignment

**WAIT when:**
- 1H trend conflicts with 5m+15m trend (e.g., 1H BEARISH but 5m+15m BULLISH)
- Momentum is ACCELERATING opposite to intended trade
- Structure shows "Volatile" or "Expanding"
- 1H is NEUTRAL AND 15m is NEUTRAL
- Counter-trend trade without exceptional alignment (e.g., SELL in BEARISH 1H without strong bearish confirmation)

===== CRITICAL RULES =====
1. NEVER trade against strong recent momentum ($3+ move in 15min)
2. Best trades = all timeframes aligned
3. When in doubt, WAIT
4. Confidence 1-5 = weak signal, 6-7 = moderate, 8-10 = strong alignment

Respond: {{"decision": "BUY" or "SELL" or "WAIT", "reasoning": "brief", "confidence": 1-10}}
"""),
        ("user", "Trade decision:")
    ])
    
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "trend": trend,
            "short_trend": trend_analysis.get("short_trend", "NEUTRAL"),
            "medium_trend": trend_analysis.get("medium_trend", "NEUTRAL"),
            "momentum": trend_analysis.get("momentum", "NEUTRAL"),
            "structure": trend_analysis.get("structure", "Unknown"),
            "strength": trend_analysis.get("strength", 50),
            "short_change": trend_analysis.get("short_change", 0),
            "medium_change": trend_analysis.get("medium_change", 0),
            "sma_status": sma_status,
            "sma8": round(sma8, 2),
            "rsi": round(rsi),
            "history": history if history else "No relevant history found.",
            "high": candle['high'],
            "low": candle['low'],
            "close": candle['close']
        })
        # Ensure confidence is returned
        if "confidence" not in result:
            result["confidence"] = 5
        return result
    except Exception as e:
        print(f"AI Error: {e}")
        return {"decision": "WAIT", "reasoning": "Chain Error", "confidence": 0}
