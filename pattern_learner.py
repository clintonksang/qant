"""
Pattern Learning Agent for Gold Trading
Uses LangChain + Pinecone to learn and recognize price patterns
"""
import os
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

load_dotenv(Path(__file__).parent / ".env")

# ===== EMBEDDINGS & VECTOR STORE =====
class TruncatedEmbeddings(OpenAIEmbeddings):
    """Truncate to 512 dimensions to match Pinecone index."""
    def embed_query(self, text: str):
        return super().embed_query(text)[:512]
    def embed_documents(self, texts: list[str]):
        return [e[:512] for e in super().embed_documents(texts)]

embeddings = TruncatedEmbeddings(model="text-embedding-3-small")
pattern_store = PineconeVectorStore(
    index_name=os.getenv("PINECONE_INDEX_NAME"),
    embedding=embeddings,
    namespace="patterns"  # Separate namespace for patterns
)

llm = ChatOpenAI(model="gpt-4o", temperature=0)

# ===== PATTERN DETECTION =====
KNOWN_PATTERNS = {
    "double_bottom": "Bullish reversal - two lows at similar price",
    "double_top": "Bearish reversal - two highs at similar price", 
    "higher_high_higher_low": "Uptrend continuation",
    "lower_high_lower_low": "Downtrend continuation",
    "bullish_engulfing": "Strong bullish candle engulfs previous bearish",
    "bearish_engulfing": "Strong bearish candle engulfs previous bullish",
    "doji": "Indecision - open and close nearly equal",
    "hammer": "Bullish reversal at bottom - long lower wick",
    "shooting_star": "Bearish reversal at top - long upper wick",
    "consolidation_breakout_up": "Price breaks above consolidation range",
    "consolidation_breakout_down": "Price breaks below consolidation range",
}

def detect_candle_pattern(candles):
    """
    Analyze last few candles to detect patterns.
    candles: list of dicts with {open, high, low, close}
    """
    if len(candles) < 3:
        return None, "Insufficient candles"
    
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]  # Previous 3 candles
    
    patterns_found = []
    
    # Doji detection (current candle)
    body_size = abs(c3['close'] - c3['open'])
    total_range = c3['high'] - c3['low']
    if total_range > 0 and body_size / total_range < 0.1:
        patterns_found.append("doji")
    
    # Hammer (long lower wick, small body at top)
    if total_range > 0:
        lower_wick = min(c3['open'], c3['close']) - c3['low']
        upper_wick = c3['high'] - max(c3['open'], c3['close'])
        if lower_wick > body_size * 2 and upper_wick < body_size:
            patterns_found.append("hammer")
        elif upper_wick > body_size * 2 and lower_wick < body_size:
            patterns_found.append("shooting_star")
    
    # Engulfing patterns
    c2_body = abs(c2['close'] - c2['open'])
    c3_body = abs(c3['close'] - c3['open'])
    c2_bullish = c2['close'] > c2['open']
    c3_bullish = c3['close'] > c3['open']
    
    if not c2_bullish and c3_bullish and c3_body > c2_body * 1.5:
        if c3['close'] > c2['open'] and c3['open'] < c2['close']:
            patterns_found.append("bullish_engulfing")
    elif c2_bullish and not c3_bullish and c3_body > c2_body * 1.5:
        if c3['close'] < c2['open'] and c3['open'] > c2['close']:
            patterns_found.append("bearish_engulfing")
    
    # Higher highs/lows or Lower highs/lows
    if c3['high'] > c2['high'] > c1['high'] and c3['low'] > c2['low'] > c1['low']:
        patterns_found.append("higher_high_higher_low")
    elif c3['high'] < c2['high'] < c1['high'] and c3['low'] < c2['low'] < c1['low']:
        patterns_found.append("lower_high_lower_low")
    
    # Double bottom/top detection (need more candles ideally)
    if len(candles) >= 10:
        lows = [c['low'] for c in candles[-10:]]
        highs = [c['high'] for c in candles[-10:]]
        min_low = min(lows)
        max_high = max(highs)
        
        # Find two similar lows (double bottom)
        low_touches = [i for i, l in enumerate(lows) if abs(l - min_low) < 0.5]
        if len(low_touches) >= 2 and low_touches[-1] - low_touches[0] >= 3:
            patterns_found.append("double_bottom")
        
        # Find two similar highs (double top)
        high_touches = [i for i, h in enumerate(highs) if abs(h - max_high) < 0.5]
        if len(high_touches) >= 2 and high_touches[-1] - high_touches[0] >= 3:
            patterns_found.append("double_top")
    
    return patterns_found if patterns_found else None, "No clear pattern"


def analyze_price_sequence(closes):
    """
    Create a text description of price movement for embedding.
    """
    if len(closes) < 10:
        return "Insufficient data for analysis"
    
    # Calculate key metrics
    recent = closes[-5:]
    older = closes[-10:-5]
    
    recent_change = recent[-1] - recent[0]
    older_change = older[-1] - older[0]
    total_change = closes[-1] - closes[-10]
    
    volatility = max(closes[-10:]) - min(closes[-10:])
    
    # Determine trend
    if total_change > 2:
        trend = "STRONG_UPTREND"
    elif total_change > 0.5:
        trend = "MILD_UPTREND"
    elif total_change < -2:
        trend = "STRONG_DOWNTREND"
    elif total_change < -0.5:
        trend = "MILD_DOWNTREND"
    else:
        trend = "SIDEWAYS"
    
    # Momentum
    if recent_change > older_change:
        momentum = "ACCELERATING"
    elif recent_change < older_change:
        momentum = "DECELERATING"
    else:
        momentum = "STEADY"
    
    description = f"""
    Price Sequence Analysis:
    - Current: {closes[-1]:.2f}
    - 10-period change: {total_change:+.2f}
    - Trend: {trend}
    - Momentum: {momentum}
    - Volatility (range): {volatility:.2f}
    - Recent 5-bar move: {recent_change:+.2f}
    - Previous 5-bar move: {older_change:+.2f}
    """
    return description.strip()


# ===== PATTERN STORAGE & RETRIEVAL =====
def save_pattern(pattern_name, context, outcome, price_at_pattern, result_pnl):
    """
    Save a recognized pattern with its outcome to vector store.
    This allows the agent to learn which patterns work and which don't.
    """
    doc_content = f"""
    Pattern: {pattern_name}
    Context: {context}
    Price at detection: {price_at_pattern}
    Outcome: {outcome}
    PnL Result: {result_pnl:+.2f}
    Timestamp: {datetime.now().isoformat()}
    """
    
    doc = Document(
        page_content=doc_content,
        metadata={
            "pattern": pattern_name,
            "outcome": outcome,  # "WIN" or "LOSS"
            "pnl": float(result_pnl),
            "price": float(price_at_pattern),
            "timestamp": datetime.now().isoformat()
        }
    )
    pattern_store.add_documents([doc])
    print(f"📚 Saved pattern: {pattern_name} -> {outcome} ({result_pnl:+.2f})")


def get_similar_patterns(current_context, k=5):
    """
    Find similar historical patterns to inform current decision.
    """
    docs = pattern_store.similarity_search(current_context, k=k)
    
    if not docs:
        return None, "No similar patterns found"
    
    # Analyze pattern performance
    wins = sum(1 for d in docs if d.metadata.get("outcome") == "WIN")
    losses = len(docs) - wins
    avg_pnl = sum(d.metadata.get("pnl", 0) for d in docs) / len(docs) if docs else 0
    
    pattern_summary = f"""
    Found {len(docs)} similar historical patterns:
    - Win rate: {wins}/{len(docs)} ({100*wins/len(docs):.0f}%)
    - Avg PnL: {avg_pnl:+.2f}
    
    Recent similar situations:
    """
    for d in docs[:3]:
        pattern_summary += f"\n    - {d.metadata.get('pattern', 'Unknown')}: {d.metadata.get('outcome', 'Unknown')} ({d.metadata.get('pnl', 0):+.2f})"
    
    return {
        "win_rate": wins / len(docs) if docs else 0,
        "avg_pnl": avg_pnl,
        "similar_count": len(docs),
        "summary": pattern_summary
    }, docs


# ===== AI PATTERN ANALYZER =====
def ai_analyze_pattern(candles, closes, trend_info):
    """
    Use GPT to analyze price action and identify patterns.
    """
    # Prepare data
    recent_candles = candles[-5:] if len(candles) >= 5 else candles
    price_description = analyze_price_sequence(closes) if len(closes) >= 10 else "Insufficient data"
    
    # Detect technical patterns
    detected_patterns, _ = detect_candle_pattern(candles) if len(candles) >= 3 else (None, "")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert technical analyst specializing in Gold (XAUUSD) price patterns.

Analyze the given price data and identify:
1. Any chart patterns (double top/bottom, head & shoulders, triangles, etc.)
2. Candlestick patterns (engulfing, doji, hammer, etc.)
3. Key support/resistance levels
4. Likely next move direction and confidence

PRICE DATA:
{price_description}

DETECTED TECHNICAL PATTERNS: {detected_patterns}

TREND INFO:
{trend_info}

RECENT CANDLES (last 5):
{candles}

Respond with JSON:
{{
    "patterns_found": ["list of patterns"],
    "support_level": price or null,
    "resistance_level": price or null,
    "prediction": "UP" or "DOWN" or "SIDEWAYS",
    "confidence": 1-10,
    "reasoning": "brief explanation",
    "suggested_action": "BUY" or "SELL" or "WAIT"
}}
"""),
        ("user", "Analyze this price action now.")
    ])
    
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "price_description": price_description,
            "detected_patterns": detected_patterns or "None detected",
            "trend_info": json.dumps(trend_info) if trend_info else "No trend data",
            "candles": json.dumps(recent_candles)
        })
        return result
    except Exception as e:
        print(f"AI Pattern Analysis Error: {e}")
        return {
            "patterns_found": [],
            "prediction": "SIDEWAYS",
            "confidence": 0,
            "reasoning": f"Analysis error: {e}",
            "suggested_action": "WAIT"
        }


# ===== LEARNING FROM TRADES =====
def learn_from_trade(entry_candles, entry_closes, entry_trend, trade_side, entry_price, exit_price, pnl):
    """
    After a trade closes, analyze what happened and store the learning.
    This is how the agent improves over time.
    """
    # What was the context at entry?
    entry_context = analyze_price_sequence(entry_closes)
    detected_patterns, _ = detect_candle_pattern(entry_candles)
    
    outcome = "WIN" if pnl > 0 else "LOSS"
    
    # Create a detailed record
    learning_content = f"""
    Trade Analysis:
    - Side: {trade_side}
    - Entry: {entry_price:.2f}
    - Exit: {exit_price:.2f}
    - PnL: {pnl:+.2f}
    - Outcome: {outcome}
    
    Entry Context:
    {entry_context}
    
    Patterns at entry: {detected_patterns or 'None detected'}
    Trend at entry: {json.dumps(entry_trend)}
    
    Lesson: {'Pattern worked - consider similar setups' if pnl > 0 else 'Pattern failed - be cautious with similar setups'}
    """
    
    doc = Document(
        page_content=learning_content,
        metadata={
            "type": "trade_learning",
            "side": trade_side,
            "outcome": outcome,
            "pnl": float(pnl),
            "entry_price": float(entry_price),
            "patterns": str(detected_patterns),
            "timestamp": datetime.now().isoformat()
        }
    )
    pattern_store.add_documents([doc])
    
    # Also save individual patterns if any were detected
    if detected_patterns:
        for pattern in detected_patterns:
            save_pattern(pattern, entry_context, outcome, entry_price, pnl)
    
    print(f"🧠 Learned from trade: {trade_side} {outcome} ({pnl:+.2f})")
    return True


# ===== PREDICTION BASED ON LEARNED PATTERNS =====
def predict_with_patterns(candles, closes, trend_info):
    """
    Make a prediction using both AI analysis and historical pattern matching.
    """
    # 1. AI Analysis
    ai_analysis = ai_analyze_pattern(candles, closes, trend_info)
    
    # 2. Find similar historical patterns
    current_context = analyze_price_sequence(closes) if len(closes) >= 10 else ""
    pattern_match, similar_docs = get_similar_patterns(current_context, k=5)
    
    # 3. Combine insights
    combined_confidence = ai_analysis.get("confidence", 5)
    suggested_action = ai_analysis.get("suggested_action", "WAIT")
    
    # Adjust based on historical pattern performance
    if pattern_match and pattern_match["similar_count"] > 0:
        win_rate = pattern_match["win_rate"]
        
        # If historical patterns show poor performance, reduce confidence
        if win_rate < 0.4:
            combined_confidence = max(1, combined_confidence - 3)
            if suggested_action != "WAIT":
                suggested_action = "WAIT"  # Override to wait
        elif win_rate > 0.7:
            combined_confidence = min(10, combined_confidence + 2)
    
    return {
        "ai_analysis": ai_analysis,
        "pattern_history": pattern_match,
        "final_action": suggested_action,
        "final_confidence": combined_confidence,
        "reasoning": f"AI: {ai_analysis.get('reasoning', 'N/A')} | History: {pattern_match['summary'] if pattern_match else 'No history'}"
    }


# ===== UTILITY FUNCTIONS =====
def get_pattern_stats():
    """Get statistics about learned patterns."""
    # This would query Pinecone for all patterns and summarize
    # For now, return a placeholder
    return {
        "total_patterns_learned": "Query Pinecone for count",
        "best_performing": "To be implemented",
        "worst_performing": "To be implemented"
    }


if __name__ == "__main__":
    # Test the pattern detection
    test_candles = [
        {"open": 4310, "high": 4312, "low": 4308, "close": 4309},
        {"open": 4309, "high": 4311, "low": 4307, "close": 4308},
        {"open": 4308, "high": 4315, "low": 4307, "close": 4314},  # Bullish engulfing?
    ]
    
    patterns, msg = detect_candle_pattern(test_candles)
    print(f"Detected patterns: {patterns}")
    print(f"Message: {msg}")
    
    # Test price sequence analysis
    test_closes = [4300, 4302, 4305, 4303, 4307, 4310, 4308, 4312, 4315, 4318]
    analysis = analyze_price_sequence(test_closes)
    print(f"\n{analysis}")
