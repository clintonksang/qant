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
        ("system", """You are Rex, an aggressive Gold Scalper. You WANT to trade. Your job is to find opportunities.

===== CURRENT MARKET =====
1H TREND: {trend}
15min TREND: {medium_trend} (moved ${medium_change})
5min TREND: {short_trend} (moved ${short_change})
MOMENTUM: {momentum}
STRUCTURE: {structure}
STRENGTH: {strength}/100

===== PRICE =====
Price: {close} | SMA8: {sma8} ({sma_status}) | RSI: {rsi}

===== SIMPLE RULES =====

**BUY when:**
- 1H is BULLISH (or NEUTRAL with other bullish signs)
- Price is ABOVE or NEAR SMA8
- RSI is NOT overbought (< 70)

**SELL when:**
- 1H is BEARISH (or NEUTRAL with other bearish signs)
- Price is BELOW or NEAR SMA8  
- RSI is NOT oversold (> 30)

**WAIT only when:**
- Trends are completely conflicting (1H BULLISH but everything else BEARISH)
- RSI is extreme (> 75 or < 25)
- Structure is EXPANDING (very volatile)

IMPORTANT: You should trade more often than you wait. If 1H trend aligns with SMA position, TAKE THE TRADE.
NEUTRAL trends are OK to trade if 1H trend is clear.

Respond: {{"decision": "BUY" or "SELL" or "WAIT", "reasoning": "brief", "confidence": 1-10}}
"""),
        ("user", "Decision now:")
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
