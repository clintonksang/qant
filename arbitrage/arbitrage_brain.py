"""
Arbitrage Brain - AI Decision Making for Currency Pair Arbitrage
Uses GPT-4 to evaluate divergence signals and make trade decisions
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")

# Initialize LLM
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not set in environment")

llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    api_key=api_key
)


def evaluate_signal(signal, historical_context):
    """
    AI evaluates whether to take an arbitrage trade.
    
    Args:
        signal: Divergence signal from SignalDetector
        historical_context: Analysis from Pinecone (similar past trades)
        
    Returns:
        Dict with action, confidence, and reasoning
    """
    
    # Build context string from historical data
    if historical_context and isinstance(historical_context, dict):
        history_str = f"""
        Similar Past Trades: {historical_context.get('similar_count', 0)}
        Historical Win Rate: {historical_context.get('win_rate', 0)*100:.0f}%
        Average PnL: {historical_context.get('avg_pnl', 0):+.1f} pips
        Mean Reversion Rate: {historical_context.get('mean_reversion_rate', 0)*100:.0f}%
        Same Pair Win Rate: {historical_context.get('same_pair_win_rate', 0)*100:.0f}%
        Recommendation: {'TRADE' if historical_context.get('should_trade', True) else 'SKIP'}
        """
    else:
        history_str = "No historical data available - Learning mode active"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an FX Arbitrage specialist analyzing correlation divergence signals between currency pairs.

Your job is to evaluate whether a divergence signal is likely to revert to mean (profitable) or is a regime change (dangerous).

===== SIGNAL DATA =====
Pair: {pair_name}
Z-Score: {z_score} (Entry threshold: 2.0, Extreme: 3.0+)
Spread: {spread} (Mean: {mean_spread})
Signal Strength: {strength}

Correlation:
- Current: {correlation}
- Expected: {expected_corr}
- Health: {correlation_health}

Proposed Actions:
- {action_a} {pair_a}
- {action_b} {pair_b}

===== HISTORICAL CONTEXT =====
{history}

===== DECISION RULES =====

**TRADE if:**
- Z-Score is between 2.0 and 3.0 (strong but not extreme)
- Correlation health is HEALTHY or DRIFTING (not BROKEN)
- Historical win rate >= 34% (or no history yet - learning mode)
- Mean reversion rate is decent (> 40%)

**SKIP if:**
- Z-Score > 3.5 (extreme - likely regime change, not mean reversion)
- Correlation health is BROKEN (pairs no longer move together)
- Historical win rate < 35% for this setup
- Multiple recent losses on same pair

**REDUCE SIZE if:**
- Z-Score > 3.0 but < 3.5
- Correlation is DRIFTING
- Win rate between 35-45%

===== RESPONSE FORMAT =====
Respond with JSON:
{{
    "action": "TRADE" or "SKIP" or "REDUCE_SIZE",
    "confidence": 1-10,
    "reasoning": "Brief explanation of your decision",
    "risk_level": "LOW" or "MEDIUM" or "HIGH",
    "expected_hold_time": "minutes estimate for mean reversion"
}}
"""),
        ("user", "Evaluate this arbitrage signal and decide whether to trade.")
    ])
    
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "pair_name": signal.get('pair_name', 'UNKNOWN'),
            "z_score": signal.get('z_score', 0),
            "spread": signal.get('spread', 0),
            "mean_spread": signal.get('mean_spread', 0),
            "strength": signal.get('strength', 'UNKNOWN'),
            "correlation": signal.get('correlation', 0),
            "expected_corr": signal.get('expected_corr', 0),
            "correlation_health": signal.get('correlation_health', 'UNKNOWN'),
            "action_a": signal.get('action_a', 'N/A'),
            "pair_a": signal.get('pair_a', 'N/A'),
            "action_b": signal.get('action_b', 'N/A'),
            "pair_b": signal.get('pair_b', 'N/A'),
            "history": history_str
        })
        
        # Ensure required fields exist
        result.setdefault('action', 'SKIP')
        result.setdefault('confidence', 5)
        result.setdefault('reasoning', 'No reasoning provided')
        result.setdefault('risk_level', 'MEDIUM')
        result.setdefault('expected_hold_time', '15-30')
        
        return result
        
    except Exception as e:
        print(f"⚠️ AI Brain Error: {e}")
        return {
            "action": "SKIP",
            "confidence": 0,
            "reasoning": f"Error in AI evaluation: {e}",
            "risk_level": "HIGH",
            "expected_hold_time": "N/A"
        }


def analyze_market_regime(correlations, price_buffers):
    """
    AI analyzes overall market regime to adjust strategy.
    Call this periodically (every 15-30 min).
    
    Args:
        correlations: Current correlation data for all pairs
        price_buffers: Recent price data
        
    Returns:
        Dict with regime analysis
    """
    
    # Summarize correlations
    corr_summary = []
    for c in correlations:
        corr_summary.append(
            f"- {c['name']}: {c['current_corr']:.2f} (expected {c['expected_corr']}) - {c['health']}"
        )
    corr_str = "\n".join(corr_summary)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an FX market analyst evaluating the current market regime for pairs trading.

===== CORRELATION STATUS =====
{correlations}

===== YOUR TASK =====
Analyze the market conditions and determine:
1. Is the market favorable for pairs/arbitrage trading?
2. Are correlations stable or breaking down?
3. Any pairs to avoid right now?
4. Overall risk level for arbitrage strategies?

Respond with JSON:
{{
    "regime": "NORMAL" or "VOLATILE" or "CORR_BREAKDOWN" or "TRENDING",
    "arb_favorable": true or false,
    "avoid_pairs": ["list of pair names to avoid"],
    "risk_level": "LOW" or "MEDIUM" or "HIGH",
    "notes": "Brief market observation"
}}
"""),
        ("user", "Analyze current market regime for arbitrage trading.")
    ])
    
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({"correlations": corr_str})
        return result
    except Exception as e:
        print(f"⚠️ Regime analysis error: {e}")
        return {
            "regime": "UNKNOWN",
            "arb_favorable": True,
            "avoid_pairs": [],
            "risk_level": "MEDIUM",
            "notes": f"Analysis error: {e}"
        }


def get_exit_recommendation(position, current_z_score, hold_time_minutes):
    """
    AI recommends whether to exit a position.
    
    Args:
        position: Current position data
        current_z_score: Current Z-score of the spread
        hold_time_minutes: How long position has been held
        
    Returns:
        Dict with exit recommendation
    """
    
    entry_z = position.get('entry_z_score', 0)
    z_change = current_z_score - entry_z
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are managing an arbitrage position. Decide if it's time to exit.

===== POSITION =====
Pair: {pair_name}
Entry Z-Score: {entry_z}
Current Z-Score: {current_z}
Z-Score Change: {z_change}
Hold Time: {hold_time} minutes
Entry Actions: {action_a} {pair_a} + {action_b} {pair_b}

===== EXIT RULES =====
- CLOSE if Z-Score has reverted toward 0 (target: < 0.5)
- CLOSE if position held too long (> 60 min) - likely not reverting
- CLOSE if Z-Score went further against us (stop loss)
- HOLD if Z-Score is moving in right direction

Respond with JSON:
{{
    "action": "HOLD" or "CLOSE",
    "reason": "Brief explanation",
    "urgency": "LOW" or "MEDIUM" or "HIGH"
}}
"""),
        ("user", "Should we exit this position?")
    ])
    
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "pair_name": position.get('pair_name', 'UNKNOWN'),
            "entry_z": entry_z,
            "current_z": current_z_score,
            "z_change": f"{z_change:+.2f}",
            "hold_time": hold_time_minutes,
            "action_a": position.get('action_a', 'N/A'),
            "pair_a": position.get('pair_a', 'N/A'),
            "action_b": position.get('action_b', 'N/A'),
            "pair_b": position.get('pair_b', 'N/A')
        })
        return result
    except Exception as e:
        return {
            "action": "HOLD",
            "reason": f"Error: {e}",
            "urgency": "LOW"
        }


# Test
if __name__ == "__main__":
    # Test signal evaluation
    test_signal = {
        'pair_name': 'EUR_GBP',
        'pair_a': 'eurusd',
        'pair_b': 'gbpusd',
        'z_score': 2.35,
        'spread': 0.0023,
        'mean_spread': 0.0005,
        'strength': 'MODERATE',
        'correlation': 0.92,
        'expected_corr': 0.95,
        'correlation_health': 'HEALTHY',
        'action_a': 'SELL',
        'action_b': 'BUY'
    }
    
    test_history = {
        'similar_count': 8,
        'win_rate': 0.625,
        'avg_pnl': 12.5,
        'mean_reversion_rate': 0.75,
        'same_pair_win_rate': 0.70,
        'should_trade': True
    }
    
    print("Testing AI Signal Evaluation...")
    result = evaluate_signal(test_signal, test_history)
    print(f"\nResult: {result}")

