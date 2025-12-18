"""
Pair Memory - Pinecone Vector Storage for Arbitrage Learning
Stores and retrieves historical arbitrage signals and outcomes
"""

import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

# Load environment from parent directory
load_dotenv(Path(__file__).parent.parent / ".env")


class TruncatedEmbeddings(OpenAIEmbeddings):
    """Truncate embeddings to 512 dimensions to match Pinecone index."""
    def embed_query(self, text: str):
        return super().embed_query(text)[:512]
    def embed_documents(self, texts: list[str]):
        return [e[:512] for e in super().embed_documents(texts)]


# Initialize embeddings
embeddings = TruncatedEmbeddings(model="text-embedding-3-small")

# Arbitrage-specific vector store
# Uses separate index: rex-arbitrage
ARBITRAGE_INDEX = os.getenv("ARBITRAGE_INDEX_NAME", "rex-arbitrage")

try:
    vectorstore = PineconeVectorStore(
        index_name=ARBITRAGE_INDEX,
        embedding=embeddings
    )
    print(f"✅ Connected to Pinecone index: {ARBITRAGE_INDEX}")
except Exception as e:
    print(f"⚠️ Pinecone connection error: {e}")
    print(f"   Make sure index '{ARBITRAGE_INDEX}' exists with 512 dimensions")
    vectorstore = None


def save_arbitrage_trade(signal, outcome, pnl_a, pnl_b, hold_time_minutes, 
                          exit_reason, exit_z_score):
    """
    Save completed arbitrage trade with full context for learning.
    
    Args:
        signal: Original signal dict that triggered the trade
        outcome: 'WIN' or 'LOSS'
        pnl_a: PnL from pair A leg
        pnl_b: PnL from pair B leg
        hold_time_minutes: How long position was held
        exit_reason: Why position was closed
        exit_z_score: Z-score at exit
    """
    if vectorstore is None:
        print("⚠️ Vectorstore not available, skipping save")
        return
    
    total_pnl = pnl_a + pnl_b
    
    # Create rich context for semantic search
    context = f"""
    === ARBITRAGE TRADE: {signal['pair_name']} ===
    
    SIGNAL CONTEXT:
    - Signal Type: {signal['signal_type']}
    - Entry Z-Score: {signal['z_score']:.2f} ({signal['strength']})
    - Entry Spread: {signal['spread']:.6f}
    - Mean Spread: {signal['mean_spread']:.6f}
    - Correlation: {signal['correlation']:.3f} (expected: {signal['expected_corr']})
    - Correlation Health: {signal['correlation_health']}
    
    TRADE EXECUTION:
    - Leg A: {signal['action_a']} {signal['pair_a'].upper()} @ {signal['price_a']:.5f}
    - Leg B: {signal['action_b']} {signal['pair_b'].upper()} @ {signal['price_b']:.5f}
    
    RESULT:
    - Outcome: {outcome}
    - Total PnL: {total_pnl:+.2f} pips
    - Leg A PnL: {pnl_a:+.2f} pips
    - Leg B PnL: {pnl_b:+.2f} pips
    - Hold Time: {hold_time_minutes} minutes
    - Exit Reason: {exit_reason}
    - Exit Z-Score: {exit_z_score:.2f}
    
    KEY LESSON: 
    {signal['pair_name']} divergence at Z-Score {signal['z_score']:.1f} with {signal['correlation_health']} correlation = {outcome}
    Entry strength: {signal['strength']} | Mean reversion: {'YES' if exit_reason == 'MEAN_REVERSION' else 'NO'}
    """
    
    doc = Document(
        page_content=context.strip(),
        metadata={
            # Trade identifiers
            "pair_name": signal['pair_name'],
            "pair_a": signal['pair_a'],
            "pair_b": signal['pair_b'],
            
            # Signal metrics
            "entry_z_score": float(signal['z_score']),
            "exit_z_score": float(exit_z_score),
            "spread": float(signal['spread']),
            "correlation": float(signal['correlation']),
            "expected_corr": float(signal['expected_corr']),
            "correlation_health": signal['correlation_health'],
            "signal_strength": signal['strength'],
            
            # Trade actions
            "action_a": signal['action_a'],
            "action_b": signal['action_b'],
            "is_positive_pair": signal['is_positive_pair'],
            
            # Results
            "outcome": outcome,
            "total_pnl": float(total_pnl),
            "pnl_a": float(pnl_a),
            "pnl_b": float(pnl_b),
            "hold_time_min": int(hold_time_minutes),
            "exit_reason": exit_reason,
            
            # Timestamps
            "entry_timestamp": signal.get('timestamp', datetime.now().isoformat()),
            "exit_timestamp": datetime.now().isoformat()
        }
    )
    
    vectorstore.add_documents([doc])
    
    print(f"\n🧠 ARBITRAGE LEARNING SAVED:")
    print(f"   {signal['pair_name']} | Z: {signal['z_score']:.2f} → {exit_z_score:.2f}")
    print(f"   {outcome} | PnL: {total_pnl:+.2f} pips | {hold_time_minutes}min")


def get_similar_divergences(signal, k=8):
    """
    Find historically similar divergence patterns.
    
    Args:
        signal: Current signal to match against
        k: Number of similar results to return
        
    Returns:
        Tuple of (analysis_dict, summary_string)
    """
    if vectorstore is None:
        return None, "Vectorstore not available"
    
    # Build semantic query
    query = f"""
    {signal['pair_name']} divergence 
    z-score {signal['z_score']:.1f} 
    correlation {signal['correlation']:.2f} 
    {signal['correlation_health']} correlation health
    {signal['strength']} signal strength
    """
    
    try:
        docs = vectorstore.similarity_search(query, k=k)
    except Exception as e:
        print(f"⚠️ Similarity search error: {e}")
        return None, f"Search error: {e}"
    
    if not docs:
        return None, "No similar divergences found in history"
    
    # Analyze historical performance
    wins = sum(1 for d in docs if d.metadata.get("outcome") == "WIN")
    losses = len(docs) - wins
    total_pnl = sum(d.metadata.get("total_pnl", 0) for d in docs)
    avg_pnl = total_pnl / len(docs) if docs else 0
    avg_hold = sum(d.metadata.get("hold_time_min", 0) for d in docs) / len(docs) if docs else 0
    
    # Filter for same pair
    same_pair = [d for d in docs if d.metadata.get("pair_name") == signal['pair_name']]
    same_pair_wins = sum(1 for d in same_pair if d.metadata.get("outcome") == "WIN")
    
    # Performance by Z-score range
    similar_z = [d for d in docs if abs(d.metadata.get("entry_z_score", 0) - abs(signal['z_score'])) < 0.5]
    similar_z_wins = sum(1 for d in similar_z if d.metadata.get("outcome") == "WIN")
    
    # Mean reversion success rate
    mean_reversion = [d for d in docs if d.metadata.get("exit_reason") == "MEAN_REVERSION"]
    
    analysis = {
        "similar_count": len(docs),
        "win_rate": wins / len(docs) if docs else 0,
        "avg_pnl": avg_pnl,
        "total_pnl": total_pnl,
        "avg_hold_time": avg_hold,
        
        # Same pair stats
        "same_pair_count": len(same_pair),
        "same_pair_win_rate": same_pair_wins / len(same_pair) if same_pair else 0,
        
        # Similar Z-score stats
        "similar_z_count": len(similar_z),
        "similar_z_win_rate": similar_z_wins / len(similar_z) if similar_z else 0,
        
        # Mean reversion stats
        "mean_reversion_count": len(mean_reversion),
        "mean_reversion_rate": len(mean_reversion) / len(docs) if docs else 0,
        
        # Trading recommendation
        "should_trade": wins / len(docs) >= 0.45 if docs else True,
        "confidence": min(100, int((wins / len(docs)) * 100 + len(docs) * 2)) if docs else 50
    }
    
    summary = f"""
    📊 HISTORICAL ANALYSIS ({len(docs)} similar setups):
    ├─ Win Rate: {wins}/{len(docs)} ({analysis['win_rate']*100:.0f}%)
    ├─ Avg PnL: {avg_pnl:+.2f} pips
    ├─ Avg Hold: {avg_hold:.0f} min
    ├─ Mean Reversion Rate: {analysis['mean_reversion_rate']*100:.0f}%
    │
    ├─ Same Pair ({signal['pair_name']}): {same_pair_wins}/{len(same_pair)} wins
    ├─ Similar Z-Score: {similar_z_wins}/{len(similar_z)} wins
    │
    └─ Recommendation: {'✅ TRADE' if analysis['should_trade'] else '⛔ SKIP'}
    """
    
    return analysis, summary


def get_pair_performance(pair_name, k=20):
    """
    Get historical performance for a specific pair.
    
    Args:
        pair_name: Name of the pair relationship (e.g., 'EUR_GBP')
        k: Number of results to analyze
        
    Returns:
        Dict with performance stats
    """
    if vectorstore is None:
        return None
    
    query = f"{pair_name} arbitrage divergence trade"
    
    try:
        docs = vectorstore.similarity_search(query, k=k)
    except:
        return None
    
    # Filter for exact pair match
    pair_trades = [d for d in docs if d.metadata.get("pair_name") == pair_name]
    
    if not pair_trades:
        return {"pair_name": pair_name, "trades": 0, "message": "No history"}
    
    wins = sum(1 for d in pair_trades if d.metadata.get("outcome") == "WIN")
    total_pnl = sum(d.metadata.get("total_pnl", 0) for d in pair_trades)
    
    # Best/worst trades
    pnls = [d.metadata.get("total_pnl", 0) for d in pair_trades]
    
    return {
        "pair_name": pair_name,
        "trades": len(pair_trades),
        "wins": wins,
        "losses": len(pair_trades) - wins,
        "win_rate": wins / len(pair_trades),
        "total_pnl": total_pnl,
        "avg_pnl": total_pnl / len(pair_trades),
        "best_trade": max(pnls),
        "worst_trade": min(pnls),
        "should_trade": wins / len(pair_trades) >= 0.40
    }


def get_z_score_performance(z_score_min, z_score_max, k=20):
    """
    Get performance for trades in a specific Z-score range.
    
    Args:
        z_score_min: Minimum Z-score
        z_score_max: Maximum Z-score
        k: Number of results to analyze
    """
    if vectorstore is None:
        return None
    
    query = f"divergence z-score between {z_score_min} and {z_score_max}"
    
    try:
        docs = vectorstore.similarity_search(query, k=k)
    except:
        return None
    
    # Filter for Z-score range
    in_range = [d for d in docs if z_score_min <= abs(d.metadata.get("entry_z_score", 0)) <= z_score_max]
    
    if not in_range:
        return {"range": f"{z_score_min}-{z_score_max}", "trades": 0}
    
    wins = sum(1 for d in in_range if d.metadata.get("outcome") == "WIN")
    
    return {
        "range": f"{z_score_min}-{z_score_max}",
        "trades": len(in_range),
        "win_rate": wins / len(in_range),
        "avg_pnl": sum(d.metadata.get("total_pnl", 0) for d in in_range) / len(in_range)
    }


def get_learning_progress():
    """Check how many trades are in the learning database."""
    if vectorstore is None:
        return {"total_trades": 0, "status": "DISCONNECTED"}
    
    try:
        docs = vectorstore.similarity_search("arbitrage trade", k=100)
        return {
            "total_trades": len(docs),
            "status": "LEARNING" if len(docs) < 20 else "ADAPTIVE"
        }
    except:
        return {"total_trades": 0, "status": "ERROR"}


def print_performance_summary():
    """Print a formatted summary of all pair performances."""
    from config import POSITIVE_PAIRS, NEGATIVE_PAIRS
    
    print("\n" + "=" * 60)
    print("📊 ARBITRAGE PERFORMANCE SUMMARY")
    print("=" * 60)
    
    progress = get_learning_progress()
    print(f"\n📚 Learning Progress: {progress['total_trades']} trades ({progress['status']})")
    
    all_pairs = POSITIVE_PAIRS + NEGATIVE_PAIRS
    
    for pair_def in all_pairs:
        perf = get_pair_performance(pair_def['name'])
        if perf and perf['trades'] > 0:
            emoji = '✅' if perf['win_rate'] >= 0.5 else '⚠️' if perf['win_rate'] >= 0.4 else '❌'
            print(f"\n{emoji} {perf['pair_name']}:")
            print(f"   Trades: {perf['trades']} | Win Rate: {perf['win_rate']*100:.0f}%")
            print(f"   Total PnL: {perf['total_pnl']:+.1f} pips | Avg: {perf['avg_pnl']:+.1f}")
    
    print("\n" + "=" * 60)


# Test
if __name__ == "__main__":
    progress = get_learning_progress()
    print(f"Learning Progress: {progress}")
    
    # Test with a fake signal
    test_signal = {
        'pair_name': 'EUR_GBP',
        'pair_a': 'eurusd',
        'pair_b': 'gbpusd',
        'price_a': 1.0850,
        'price_b': 1.2704,
        'spread': 0.0023,
        'z_score': 2.35,
        'mean_spread': 0.0005,
        'correlation': 0.92,
        'expected_corr': 0.95,
        'correlation_health': 'HEALTHY',
        'is_positive_pair': True,
        'signal_type': 'DIVERGENCE',
        'strength': 'MODERATE',
        'action_a': 'SELL',
        'action_b': 'BUY',
        'timestamp': datetime.now().isoformat()
    }
    
    analysis, summary = get_similar_divergences(test_signal)
    print(summary)

