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
        ("system", """You are Rex, a disciplined Gold Scalper. You trade WITH the trend, not against it.

===== MARKET ANALYSIS =====
1H TREND (from Tiingo): {trend}
SHORT-TERM (5min): {short_trend} (moved ${short_change})
MEDIUM-TERM (15min): {medium_trend} (moved ${medium_change})
MOMENTUM: {momentum}
STRUCTURE: {structure}
TREND STRENGTH: {strength}/100

===== PRICE ACTION =====
Current Price: {close}
SMA8: {sma8} ({sma_status})
RSI: {rsi}

===== PAST TRADE MEMORIES =====
{history}

===== TRADING RULES (STRICT) =====

**HIGH PROBABILITY SETUPS (Take these):**
1. BUY: 1H BULLISH + Medium BULLISH + Price ABOVE SMA8 + RSI < 70
2. SELL: 1H BEARISH + Medium BEARISH + Price BELOW SMA8 + RSI > 30
3. Strong momentum in trend direction (ACCELERATING)

**AVOID THESE (WAIT):**
1. Conflicting trends (1H says BULLISH but short-term BEARISH)
2. EXPANDING/Choppy structure (volatile, unpredictable)
3. Weak trend strength (< 40)
4. Price extended too far from SMA8 (overextended)
5. RSI extreme (overbought > 70 for buys, oversold < 30 for sells)

**SPECIAL RULES:**
- If structure is CONSOLIDATING, prefer WAIT unless breakout is clear
- If momentum is ACCELERATING opposite to intended trade, WAIT
- Use memories to avoid repeating recent losing patterns

Respond with JSON: {{"decision": "BUY" or "SELL" or "WAIT", "reasoning": "brief explanation", "confidence": 1-10}}
"""),
        ("user", "Make your trading decision now.")
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
