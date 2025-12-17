import os, requests, pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
import json

load_dotenv()

# Custom Embeddings class to fit 512-dim index
class TruncatedEmbeddings(OpenAIEmbeddings):
    def embed_query(self, text: str):
        return super().embed_query(text)[:512]
    def embed_documents(self, texts: list[str]):
        return [e[:512] for e in super().embed_documents(texts)]

# Setup Vector Stores
embeddings = TruncatedEmbeddings(model="text-embedding-3-small")

# Main trade memory store
vectorstore = PineconeVectorStore(
    index_name=os.getenv("PINECONE_INDEX_NAME"),
    embedding=embeddings
)

# Separate namespace for market conditions/patterns
market_store = PineconeVectorStore(
    index_name=os.getenv("PINECONE_INDEX_NAME"),
    embedding=embeddings,
    namespace="market_conditions"
)

# ============ MARKET SESSION DETECTION ============
def get_market_session(hour_utc):
    """
    Detect which trading session based on UTC hour.
    Gold moves differently in each session.
    """
    if 0 <= hour_utc < 8:
        return "ASIAN"
    elif 8 <= hour_utc < 13:
        return "LONDON"
    elif 13 <= hour_utc < 17:
        return "US_OVERLAP"  # Most volatile for gold
    elif 17 <= hour_utc < 22:
        return "US"
    else:
        return "LATE_US"

def get_day_type(weekday):
    """0=Monday, 4=Friday"""
    if weekday == 0:
        return "MONDAY"  # Often ranging/reversals
    elif weekday == 4:
        return "FRIDAY"  # Often position squaring
    elif weekday == 2:
        return "MIDWEEK"  # Wednesday often sees big moves
    else:
        return "REGULAR"

# ============ PRICE ACTION CONTEXT ============
def calculate_volatility(closes, period=20):
    """Calculate recent volatility (ATR-like)"""
    if len(closes) < period:
        return 0
    recent = closes[-period:]
    ranges = [abs(recent[i] - recent[i-1]) for i in range(1, len(recent))]
    return sum(ranges) / len(ranges) if ranges else 0

def detect_price_action_type(closes, sma):
    """
    Is this a pullback entry, breakout, or chop?
    """
    if len(closes) < 5:
        return "UNKNOWN"
    
    current = closes[-1]
    prev = closes[-2]
    sma_distance = abs(current - sma)
    
    # Check if price just crossed SMA (breakout/breakdown)
    prev_above_sma = closes[-2] > sma if len(closes) >= 2 else False
    curr_above_sma = current > sma
    
    if prev_above_sma != curr_above_sma:
        return "SMA_CROSS"
    
    # Pullback to SMA
    if sma_distance < 1.0:  # Within $1 of SMA
        return "PULLBACK_TO_SMA"
    
    # Extended from SMA
    if sma_distance > 3.0:  # More than $3 from SMA
        return "EXTENDED"
    
    # Check for breakout (new high/low in last 5 candles)
    recent_5 = closes[-5:]
    if current == max(recent_5):
        return "BREAKOUT_HIGH"
    elif current == min(recent_5):
        return "BREAKOUT_LOW"
    
    return "CONSOLIDATION"

def get_1hour_trend():
    """Institutional Filter: Checks last 4 hours on Tiingo."""
    try:
        url = f"https://api.tiingo.com/tiingo/fx/xauusd/prices?resampleFreq=1hour&token={os.getenv('TIINGO_KEY')}"
        data = requests.get(url).json()
        df = pd.DataFrame(data)
        current, past = df['close'].iloc[-1], df['close'].iloc[-4]
        return "BULLISH" if current > past else "BEARISH"
    except Exception as e:
        print(f"⚠️ Trend Error: {e}")
        return "NEUTRAL"

def save_trade_enhanced(trade_id, side, entry, exit_price, sl, tp, pnl, reason,
                        # Trend context
                        trend_1h, trend_15m, trend_5m, momentum, structure,
                        # Technical indicators
                        rsi, sma, sma_position,
                        # Patterns & price action
                        patterns_detected, price_action_type, volatility,
                        # Time context  
                        hour_utc, weekday, session,
                        # Trade metrics
                        hold_time_minutes,
                        # Extra context
                        price_change_5m=0, price_change_15m=0):
    """
    COMPREHENSIVE trade storage for maximum learning.
    This stores EVERYTHING needed to understand what works.
    """
    outcome = "WIN" if pnl > 0 else "LOSS"
    
    # Calculate Risk:Reward metrics
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr_ratio = reward / risk if risk > 0 else 0
    
    # Calculate how much of target was achieved
    if side == "BUY":
        max_favorable = exit_price - entry
        max_adverse = entry - exit_price if exit_price < entry else 0
    else:  # SELL
        max_favorable = entry - exit_price
        max_adverse = exit_price - entry if exit_price > entry else 0
    
    target_achieved_pct = (max_favorable / reward * 100) if reward > 0 else 0
    
    # Determine if trade was with or against the trend
    trend_alignment = "WITH_TREND" if (
        (side == "BUY" and trend_1h == "BULLISH") or 
        (side == "SELL" and trend_1h == "BEARISH")
    ) else "COUNTER_TREND"
    
    # Rich context description for semantic search
    context = f"""
    === TRADE RESULT: {outcome} ({pnl:+.2f}) ===
    
    EXECUTION:
    - Action: {side} Gold at ${entry:.2f}
    - Exit: ${exit_price:.2f} ({reason})
    - SL: ${sl:.2f} | TP: ${tp:.2f}
    - Risk:Reward = 1:{rr_ratio:.1f}
    - Hold Time: {hold_time_minutes} minutes
    - Target Achieved: {target_achieved_pct:.0f}%
    
    TREND CONTEXT:
    - 1H Trend: {trend_1h} ({trend_alignment})
    - 15m Trend: {trend_15m} (moved ${price_change_15m})
    - 5m Trend: {trend_5m} (moved ${price_change_5m})
    - Momentum: {momentum}
    - Structure: {structure}
    
    TECHNICAL INDICATORS:
    - RSI: {rsi}
    - SMA8: ${sma:.2f} (Price {sma_position})
    - Volatility: ${volatility:.2f}/candle
    
    PRICE ACTION:
    - Entry Type: {price_action_type}
    - Patterns: {patterns_detected or 'None'}
    
    TIME CONTEXT:
    - Session: {session}
    - Hour (UTC): {hour_utc}
    - Day: {['MON','TUE','WED','THU','FRI','SAT','SUN'][weekday]}
    
    KEY LESSON: {side} {trend_alignment} in {structure} structure during {session} session = {outcome}
    """
    
    doc = Document(
        page_content=context.strip(),
        metadata={
            # Trade identifiers
            "trade_id": str(trade_id),
            "side": side,
            "outcome": outcome,
            
            # Prices
            "entry": float(entry),
            "exit": float(exit_price),
            "sl": float(sl),
            "tp": float(tp),
            "pnl": float(pnl),
            
            # Risk metrics
            "risk_amount": float(risk),
            "reward_amount": float(reward),
            "rr_ratio": float(rr_ratio),
            "target_achieved_pct": float(target_achieved_pct),
            
            # Trend context
            "trend_1h": trend_1h,
            "trend_15m": trend_15m,
            "trend_5m": trend_5m,
            "trend_alignment": trend_alignment,
            "momentum": momentum,
            "structure": structure,
            
            # Technical
            "rsi": int(rsi) if rsi else 50,
            "sma_position": sma_position,
            "volatility": float(volatility),
            
            # Price action
            "price_action_type": price_action_type,
            "patterns": str(patterns_detected),
            
            # Time
            "hour_utc": int(hour_utc),
            "weekday": int(weekday),
            "session": session,
            "hold_time_min": int(hold_time_minutes),
            
            # Exit
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
    )
    vectorstore.add_documents([doc])
    
    print(f"\n🧠 LEARNING SAVED:")
    print(f"   {side} {outcome} ({pnl:+.2f}) | R:R 1:{rr_ratio:.1f} | {hold_time_minutes}min hold")
    print(f"   {trend_alignment} in {session} | {price_action_type} entry")

def save_trade(trade_id, side, entry, pnl, reason):
    """Basic trade save (backwards compatible)."""
    doc = Document(
        page_content=f"Gold {side} at {entry}. Result: {reason}. PnL: {pnl}",
        metadata={"id": str(trade_id), "side": side, "pnl": float(pnl)}
    )
    vectorstore.add_documents([doc])

def save_market_snapshot(price, trend_1h, trend_15m, trend_5m, momentum, 
                          structure, rsi, patterns, hour_of_day):
    """
    Save market conditions periodically (every 15-30 min).
    This builds a database of "what the market looked like" at different times.
    """
    snapshot = f"""
    MARKET SNAPSHOT at {datetime.now().strftime('%Y-%m-%d %H:%M')}
    Price: {price:.2f}
    1H Trend: {trend_1h}, 15m: {trend_15m}, 5m: {trend_5m}
    Momentum: {momentum}, Structure: {structure}
    RSI: {rsi}, Hour: {hour_of_day}
    Patterns: {patterns or 'None'}
    """
    
    doc = Document(
        page_content=snapshot.strip(),
        metadata={
            "type": "market_snapshot",
            "price": float(price),
            "trend_1h": trend_1h,
            "momentum": momentum,
            "structure": structure,
            "hour": hour_of_day,
            "timestamp": datetime.now().isoformat()
        }
    )
    market_store.add_documents([doc])

def get_memory(query, k=5):
    """Retrieves similar past trades."""
    docs = vectorstore.similarity_search(query, k=k)
    return "\n".join([f"- {d.page_content}" for d in docs])

def get_similar_conditions(trend_1h, trend_15m, structure, momentum, session=None, price_action=None, k=8):
    """
    Find past trades in SIMILAR market conditions.
    This is the KEY function for learning from history.
    Now includes session and entry type for better matching.
    """
    # Build comprehensive query
    query_parts = [f"{trend_1h} trend", f"{structure} structure", f"{momentum} momentum"]
    if session:
        query_parts.append(f"{session} session")
    if price_action:
        query_parts.append(f"{price_action} entry")
    
    query = " ".join(query_parts)
    docs = vectorstore.similarity_search(query, k=k)
    
    if not docs:
        return None, "No similar past trades found"
    
    # Analyze past performance
    wins = sum(1 for d in docs if d.metadata.get("outcome") == "WIN")
    losses = len(docs) - wins
    total_pnl = sum(d.metadata.get("pnl", 0) for d in docs)
    avg_pnl = total_pnl / len(docs) if docs else 0
    
    # Performance by side
    buy_trades = [d for d in docs if d.metadata.get("side") == "BUY"]
    sell_trades = [d for d in docs if d.metadata.get("side") == "SELL"]
    buy_wins = sum(1 for d in buy_trades if d.metadata.get("outcome") == "WIN")
    sell_wins = sum(1 for d in sell_trades if d.metadata.get("outcome") == "WIN")
    
    # R:R analysis
    avg_rr = sum(d.metadata.get("rr_ratio", 2.0) for d in docs) / len(docs) if docs else 2.0
    avg_target_achieved = sum(d.metadata.get("target_achieved_pct", 50) for d in docs) / len(docs) if docs else 50
    
    # Hold time analysis
    avg_hold_time = sum(d.metadata.get("hold_time_min", 10) for d in docs) / len(docs) if docs else 10
    
    # Session breakdown
    session_perf = {}
    for d in docs:
        s = d.metadata.get("session", "UNKNOWN")
        if s not in session_perf:
            session_perf[s] = {"wins": 0, "total": 0}
        session_perf[s]["total"] += 1
        if d.metadata.get("outcome") == "WIN":
            session_perf[s]["wins"] += 1
    
    analysis = {
        "total_similar": len(docs),
        "win_rate": wins / len(docs) if docs else 0,
        "avg_pnl": avg_pnl,
        "total_pnl": total_pnl,
        "buy_win_rate": buy_wins / len(buy_trades) if buy_trades else 0,
        "sell_win_rate": sell_wins / len(sell_trades) if sell_trades else 0,
        "buy_count": len(buy_trades),
        "sell_count": len(sell_trades),
        "recommended_side": "BUY" if (buy_wins / max(len(buy_trades), 1)) > (sell_wins / max(len(sell_trades), 1)) else "SELL",
        "avg_rr": avg_rr,
        "avg_target_achieved": avg_target_achieved,
        "avg_hold_time": avg_hold_time,
        "session_performance": session_perf,
        "should_trade": wins / len(docs) >= 0.40 if docs else True  # Don't trade if <40% win rate
    }
    
    # Build summary
    summary = f"""
    📊 HISTORICAL ANALYSIS ({len(docs)} similar setups):
    ├─ Win Rate: {wins}/{len(docs)} ({analysis['win_rate']*100:.0f}%)
    ├─ Avg PnL: {avg_pnl:+.2f}
    ├─ Avg Hold: {avg_hold_time:.0f} min
    ├─ Avg Target Achieved: {avg_target_achieved:.0f}%
    ├─ BUY: {buy_wins}/{len(buy_trades)} wins ({analysis['buy_win_rate']*100:.0f}%)
    ├─ SELL: {sell_wins}/{len(sell_trades)} wins ({analysis['sell_win_rate']*100:.0f}%)
    └─ Recommendation: {'✅ TRADE' if analysis['should_trade'] else '⛔ AVOID'} - {analysis['recommended_side']} preferred
    """
    
    return analysis, summary

def get_session_performance(session, k=15):
    """
    How do we perform in a specific session?
    """
    query = f"{session} session gold trading"
    docs = vectorstore.similarity_search(query, k=k)
    
    session_trades = [d for d in docs if d.metadata.get("session") == session]
    
    if not session_trades:
        return None, f"No history for {session} session"
    
    wins = sum(1 for d in session_trades if d.metadata.get("outcome") == "WIN")
    total_pnl = sum(d.metadata.get("pnl", 0) for d in session_trades)
    
    return {
        "session": session,
        "trades": len(session_trades),
        "win_rate": wins / len(session_trades),
        "total_pnl": total_pnl,
        "should_trade": wins / len(session_trades) >= 0.40
    }, f"{session}: {wins}/{len(session_trades)} ({wins/len(session_trades)*100:.0f}%) | PnL: {total_pnl:+.2f}"

def get_entry_type_performance(entry_type, k=15):
    """
    How do we perform with specific entry types (pullback, breakout, etc)?
    """
    query = f"{entry_type} entry gold trading"
    docs = vectorstore.similarity_search(query, k=k)
    
    entry_trades = [d for d in docs if d.metadata.get("price_action_type") == entry_type]
    
    if not entry_trades:
        return None, f"No history for {entry_type} entries"
    
    wins = sum(1 for d in entry_trades if d.metadata.get("outcome") == "WIN")
    total_pnl = sum(d.metadata.get("pnl", 0) for d in entry_trades)
    avg_rr = sum(d.metadata.get("rr_ratio", 2.0) for d in entry_trades) / len(entry_trades)
    
    return {
        "entry_type": entry_type,
        "trades": len(entry_trades),
        "win_rate": wins / len(entry_trades),
        "total_pnl": total_pnl,
        "avg_rr": avg_rr
    }, f"{entry_type}: {wins}/{len(entry_trades)} ({wins/len(entry_trades)*100:.0f}%) | Avg R:R 1:{avg_rr:.1f}"

def get_pattern_performance(pattern_name, k=10):
    """
    Check how a specific pattern performed historically.
    """
    query = f"Pattern: {pattern_name}"
    docs = vectorstore.similarity_search(query, k=k)
    
    pattern_trades = [d for d in docs if pattern_name.lower() in str(d.metadata.get("patterns", "")).lower()]
    
    if not pattern_trades:
        return None, f"No history for pattern: {pattern_name}"
    
    wins = sum(1 for d in pattern_trades if d.metadata.get("outcome") == "WIN")
    win_rate = wins / len(pattern_trades)
    avg_pnl = sum(d.metadata.get("pnl", 0) for d in pattern_trades) / len(pattern_trades)
    
    return {
        "pattern": pattern_name,
        "trades": len(pattern_trades),
        "win_rate": win_rate,
        "avg_pnl": avg_pnl
    }, f"{pattern_name}: {win_rate*100:.0f}% win rate over {len(pattern_trades)} trades"

def get_comprehensive_pre_trade_analysis(side, trend_1h, trend_15m, structure, momentum, 
                                          session, price_action, patterns=None):
    """
    MASTER function: Call this BEFORE taking a trade.
    Returns comprehensive analysis with go/no-go recommendation.
    """
    results = {
        "should_trade": True,
        "confidence": 50,
        "warnings": [],
        "advantages": []
    }
    
    # 1. Check similar conditions
    cond_analysis, cond_summary = get_similar_conditions(
        trend_1h, trend_15m, structure, momentum, session, price_action
    )
    if cond_analysis:
        results["conditions"] = cond_analysis
        if not cond_analysis.get("should_trade", True):
            results["should_trade"] = False
            results["warnings"].append(f"Low win rate ({cond_analysis['win_rate']*100:.0f}%) in similar conditions")
        
        # Check if proposed side matches history
        if cond_analysis["recommended_side"] != side:
            results["warnings"].append(f"History suggests {cond_analysis['recommended_side']} works better here")
            results["confidence"] -= 15
        else:
            results["advantages"].append(f"{side} has {cond_analysis[side.lower()+'_win_rate']*100:.0f}% win rate in similar setups")
            results["confidence"] += 10
    
    # 2. Check session performance
    session_perf, session_summary = get_session_performance(session)
    if session_perf:
        results["session"] = session_perf
        if not session_perf.get("should_trade", True):
            results["warnings"].append(f"Poor performance in {session} session ({session_perf['win_rate']*100:.0f}% win rate)")
            results["confidence"] -= 10
        elif session_perf["win_rate"] > 0.55:
            results["advantages"].append(f"Strong {session} session ({session_perf['win_rate']*100:.0f}% win rate)")
            results["confidence"] += 10
    
    # 3. Check entry type
    entry_perf, entry_summary = get_entry_type_performance(price_action)
    if entry_perf:
        results["entry_type"] = entry_perf
        if entry_perf["win_rate"] < 0.40:
            results["warnings"].append(f"{price_action} entries have low win rate ({entry_perf['win_rate']*100:.0f}%)")
            results["confidence"] -= 10
        elif entry_perf["win_rate"] > 0.55:
            results["advantages"].append(f"{price_action} entries work well ({entry_perf['win_rate']*100:.0f}% win rate)")
            results["confidence"] += 10
    
    # 4. Check patterns
    if patterns:
        for pattern in patterns[:3]:  # Check top 3 patterns
            pattern_perf, _ = get_pattern_performance(pattern)
            if pattern_perf and pattern_perf["win_rate"] < 0.35:
                results["warnings"].append(f"Pattern '{pattern}' has poor history ({pattern_perf['win_rate']*100:.0f}%)")
            elif pattern_perf and pattern_perf["win_rate"] > 0.55:
                results["advantages"].append(f"Pattern '{pattern}' is profitable ({pattern_perf['win_rate']*100:.0f}%)")
    
    # 5. Final decision
    if len(results["warnings"]) >= 3:
        results["should_trade"] = False
        results["recommendation"] = "⛔ AVOID - Too many warning signals"
    elif results["confidence"] >= 60 and len(results["advantages"]) >= 2:
        results["recommendation"] = "✅ HIGH CONFIDENCE - Multiple positive factors"
    elif results["confidence"] >= 45:
        results["recommendation"] = "⚠️ MODERATE - Proceed with caution"
    else:
        results["should_trade"] = False
        results["recommendation"] = "⛔ LOW CONFIDENCE - Consider waiting"
    
    return results


# ============ HOURLY STRATEGY REVIEW ============
def get_hourly_performance_review():
    """
    Generate a comprehensive review of the last hour's trading performance.
    Call this every hour to track learning progress.
    """
    from datetime import timedelta
    
    # Get all recent trades
    query = "Gold trade result"
    docs = vectorstore.similarity_search(query, k=50)
    
    if not docs:
        return {
            "total_trades": 0,
            "message": "No trades recorded yet. Keep collecting data."
        }
    
    # Overall stats
    total = len(docs)
    wins = sum(1 for d in docs if d.metadata.get("outcome") == "WIN")
    total_pnl = sum(d.metadata.get("pnl", 0) for d in docs)
    
    # By side
    buys = [d for d in docs if d.metadata.get("side") == "BUY"]
    sells = [d for d in docs if d.metadata.get("side") == "SELL"]
    buy_wins = sum(1 for d in buys if d.metadata.get("outcome") == "WIN")
    sell_wins = sum(1 for d in sells if d.metadata.get("outcome") == "WIN")
    
    # By session
    session_stats = {}
    for d in docs:
        s = d.metadata.get("session", "UNKNOWN")
        if s not in session_stats:
            session_stats[s] = {"wins": 0, "total": 0, "pnl": 0}
        session_stats[s]["total"] += 1
        session_stats[s]["pnl"] += d.metadata.get("pnl", 0)
        if d.metadata.get("outcome") == "WIN":
            session_stats[s]["wins"] += 1
    
    # By trend alignment
    with_trend = [d for d in docs if d.metadata.get("trend_alignment") == "WITH_TREND"]
    counter_trend = [d for d in docs if d.metadata.get("trend_alignment") == "COUNTER_TREND"]
    with_trend_wins = sum(1 for d in with_trend if d.metadata.get("outcome") == "WIN")
    counter_trend_wins = sum(1 for d in counter_trend if d.metadata.get("outcome") == "WIN")
    
    review = {
        "total_trades": total,
        "win_rate": wins / total if total > 0 else 0,
        "total_pnl": total_pnl,
        "buy_stats": {
            "total": len(buys),
            "win_rate": buy_wins / len(buys) if buys else 0
        },
        "sell_stats": {
            "total": len(sells),
            "win_rate": sell_wins / len(sells) if sells else 0
        },
        "session_stats": session_stats,
        "with_trend_win_rate": with_trend_wins / len(with_trend) if with_trend else 0,
        "counter_trend_win_rate": counter_trend_wins / len(counter_trend) if counter_trend else 0,
        "learning_progress": f"{total}/20 trades" if total < 20 else "Learning complete"
    }
    
    # Generate insights
    insights = []
    
    # Best/worst side
    if buys and sells:
        buy_wr = buy_wins / len(buys)
        sell_wr = sell_wins / len(sells)
        if buy_wr > sell_wr + 0.15:
            insights.append(f"\u2705 BUY is significantly better ({buy_wr*100:.0f}% vs {sell_wr*100:.0f}%)")
        elif sell_wr > buy_wr + 0.15:
            insights.append(f"\u2705 SELL is significantly better ({sell_wr*100:.0f}% vs {buy_wr*100:.0f}%)")
    
    # Best session
    if session_stats:
        best_session = max(session_stats.items(), 
                          key=lambda x: x[1]["wins"]/x[1]["total"] if x[1]["total"] >= 3 else 0)
        if best_session[1]["total"] >= 3:
            wr = best_session[1]["wins"] / best_session[1]["total"]
            if wr > 0.55:
                insights.append(f"\u2705 {best_session[0]} session is profitable ({wr*100:.0f}% win rate)")
    
    # Worst session
    if session_stats:
        worst_session = min(session_stats.items(),
                           key=lambda x: x[1]["wins"]/x[1]["total"] if x[1]["total"] >= 3 else 1)
        if worst_session[1]["total"] >= 3:
            wr = worst_session[1]["wins"] / worst_session[1]["total"]
            if wr < 0.40:
                insights.append(f"\u26a0\ufe0f  {worst_session[0]} session is losing ({wr*100:.0f}% win rate)")
    
    # Trend following effectiveness
    if with_trend and counter_trend:
        wt_wr = with_trend_wins / len(with_trend)
        ct_wr = counter_trend_wins / len(counter_trend)
        if wt_wr > ct_wr:
            insights.append(f"\u2705 Trend-following works ({wt_wr*100:.0f}% vs counter-trend {ct_wr*100:.0f}%)")
        else:
            insights.append(f"\u26a0\ufe0f  Counter-trend is beating trend-following!")
    
    review["insights"] = insights
    
    return review


def print_hourly_review():
    """
    Print a formatted hourly review to the console.
    """
    review = get_hourly_performance_review()
    
    print("\n" + "="*60)
    print("\ud83d\udcca HOURLY STRATEGY REVIEW")
    print("="*60)
    
    if review["total_trades"] == 0:
        print("No trades recorded yet. Keep collecting data.")
        return review
    
    print(f"\n\ud83d\udcc8 OVERALL: {review['total_trades']} trades | {review['win_rate']*100:.0f}% win rate | PnL: {review['total_pnl']:+.2f}")
    print(f"   Learning: {review['learning_progress']}")
    
    print(f"\n\ud83d\udfe2 BUY: {review['buy_stats']['total']} trades | {review['buy_stats']['win_rate']*100:.0f}% win rate")
    print(f"\ud83d\udd34 SELL: {review['sell_stats']['total']} trades | {review['sell_stats']['win_rate']*100:.0f}% win rate")
    
    if review.get('with_trend_win_rate'):
        print(f"\n\ud83c\udfaf With-Trend: {review['with_trend_win_rate']*100:.0f}% | Counter-Trend: {review['counter_trend_win_rate']*100:.0f}%")
    
    print("\n\ud83d\udd52 SESSION BREAKDOWN:")
    for session, stats in review.get("session_stats", {}).items():
        wr = stats["wins"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"   {session}: {stats['total']} trades | {wr:.0f}% | PnL: {stats['pnl']:+.2f}")
    
    if review.get("insights"):
        print("\n\ud83d\udca1 INSIGHTS:")
        for insight in review["insights"]:
            print(f"   {insight}")
    
    print("="*60 + "\n")
    
    return review
