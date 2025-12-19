# Currency Pair Arbitrage System - Comprehensive Guide

## Table of Contents
1. [Overview](#overview)
2. [How Arbitrage Works](#how-arbitrage-works)
3. [System Architecture](#system-architecture)
4. [Signal Detection](#signal-detection)
5. [Trade Execution](#trade-execution)
6. [Risk Management](#risk-management)
7. [Learning System](#learning-system)
8. [Configuration](#configuration)
9. [Workflow Example](#workflow-example)

---

## Overview

This arbitrage system exploits temporary price divergences between **correlated currency pairs**. Instead of traditional arbitrage (buying low and selling high simultaneously), this system uses **statistical arbitrage** based on mean reversion - betting that correlated pairs that have temporarily diverged will revert to their normal relationship.

### Key Concept: Correlation Divergence

When two currency pairs are highly correlated (they typically move together), any temporary divergence creates an opportunity. The system:
1. **Detects** when pairs diverge beyond normal statistical bounds
2. **Evaluates** whether the divergence is likely to revert (mean reversion) or a regime change
3. **Executes** hedged trades betting on reversion
4. **Exits** when the spread normalizes or risk limits are hit

---

## How Arbitrage Works

### 1. Correlation Types

The system monitors two types of correlated pairs:

#### **Positively Correlated Pairs** (Move Together)
- **EUR/USD ↔ GBP/USD** (Expected correlation: 0.95)
  - Both European currencies vs Dollar
  - Deeply intertwined EU/UK economies
  
- **AUD/USD ↔ NZD/USD** (Expected correlation: 0.95)
  - Commodity twins
  - Both sensitive to China demand & risk sentiment

#### **Negatively Correlated Pairs** (Move Opposite)
- **EUR/USD ↔ USD/CHF** (Expected correlation: -0.95)
  - Most stable negative correlation
  - Euro and Swiss Franc both vs Dollar

### 2. Spread Calculation

For each pair relationship, the system calculates a **normalized spread**:

**Positive Correlation:**
```
spread = normalized_price_A - normalized_price_B
```
- Should be near 0 when pairs are in sync
- Positive spread = A overvalued relative to B
- Negative spread = B overvalued relative to A

**Negative Correlation:**
```
spread = normalized_price_A + normalized_price_B - 2
```
- Should be near 0 when pairs move opposite as expected
- Deviation indicates one pair is out of sync

### 3. Z-Score Detection

The system uses **Z-scores** to identify statistically significant divergences:

```
Z-Score = (Current_Spread - Mean_Spread) / StdDev_Spread
```

**Interpretation:**
- **|Z| < 1.0**: Normal (no signal)
- **|Z| 1.0-2.0**: Elevated (monitoring)
- **|Z| 2.0-3.0**: **TRADEABLE SIGNAL** ✅
- **|Z| > 3.0**: Extreme (likely regime change, skip)

### 4. Mean Reversion Strategy

When Z-score exceeds 2.0:
- **Positive Z-score**: Pair A overvalued → **SELL A, BUY B**
- **Negative Z-score**: Pair B overvalued → **BUY A, SELL B**

The bet: The spread will revert to its mean (Z-score → 0), generating profit from both legs.

---

## System Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────┐
│                    MAIN LOOP                              │
│  (WebSocket → Price Updates → Signal Detection)          │
└─────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Correlation  │  │   Signal     │  │  Position    │
│   Engine     │  │  Detector    │  │  Manager     │
└──────────────┘  └──────────────┘  └──────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                          ▼
                  ┌──────────────┐
                  │ Arbitrage    │
                  │    Brain     │
                  │   (GPT-4)    │
                  └──────────────┘
                          │
                          ▼
                  ┌──────────────┐
                  │ Pair Memory  │
                  │  (Pinecone)  │
                  └──────────────┘
```

### Data Flow

1. **Price Feed** (Tiingo WebSocket)
   - Real-time FX quotes for all pairs
   - Updates every tick
   - Stored in rolling buffers (60 minutes)

2. **Correlation Engine**
   - Calculates rolling correlations (30-minute window)
   - Tracks correlation health (HEALTHY/DRIFTING/BROKEN)
   - Detects correlation breakdowns

3. **Signal Detector**
   - Calculates spreads and Z-scores every minute
   - Identifies tradeable divergences (Z > 2.0)
   - Filters extreme signals (Z > 3.0)

4. **Arbitrage Brain (AI)**
   - Evaluates signals using GPT-4
   - Considers historical context from Pinecone
   - Makes trade/no-trade decisions

5. **Position Manager**
   - Opens hedged positions (2 legs)
   - Monitors exits (mean reversion, time, stop loss)
   - Tracks P&L and risk limits

6. **Pair Memory**
   - Stores completed trades in Pinecone
   - Enables similarity search for learning
   - Provides historical context for decisions

---

## Signal Detection

### Step-by-Step Process

#### 1. **Price Normalization**
```python
# Normalize prices to percentage from window start
norm_a = prices_a[-window:] / prices_a[-window]
norm_b = prices_b[-window:] / prices_b[-window]
```

#### 2. **Spread Calculation**
```python
if is_positive_pair:
    spread = norm_a - norm_b  # Should be ~0
else:
    spread = norm_a + norm_b - 2  # Should be ~0
```

#### 3. **Z-Score Calculation**
```python
# Use historical spread (excluding current) to avoid look-ahead bias
historical_spread = spread[:-1]
current_spread = spread[-1]

mean_spread = np.mean(historical_spread)
std_spread = np.std(historical_spread)
z_score = (current_spread - mean_spread) / std_spread
```

#### 4. **Signal Generation**

A signal is generated when:
- `|z_score| > 2.0` (entry threshold)
- `|z_score| < 3.0` (skip extreme - regime changes)
- Correlation health is not "BROKEN"

**Signal Contains:**
- Pair names and current prices
- Z-score and spread metrics
- Correlation status
- Trading actions (BUY/SELL for each leg)
- Signal strength (MODERATE/STRONG)

### Example Signal

```
🔴 DIVERGENCE SIGNAL: EUR_GBP
============================================================
   Z-Score: 2.35 (MODERATE)
   Spread: 0.002300 (mean: 0.000500)
   Correlation: 0.920 (HEALTHY)
   
   📈 ACTION:
      → SELL eurusd @ 1.08500
      → BUY gbpusd @ 1.27040
============================================================
```

---

## Trade Execution

### Pre-Trade Checks

Before opening a position, the system verifies:

1. **Position Limits**
   - Max concurrent trades: **2** (reduced from 3 for quality focus)
   - No existing position in same pair

2. **Cooldown Period**
   - Minimum 8 minutes between trades on same pair
   - Prevents overtrading

3. **Loss Protection**
   - Pause after 3 consecutive losses
   - Prevents revenge trading

4. **Correlation Health**
   - Skip if correlation is "BROKEN" (deviation > 0.25)
   - Trade with caution if "DRIFTING" (deviation 0.15-0.25)

### AI Decision Making

When a signal is detected, the **Arbitrage Brain (GPT-4)** evaluates it:

**Inputs:**
- Signal metrics (Z-score, spread, correlation)
- Historical context from Pinecone (similar past trades)
- Correlation health status

**AI Decision Criteria:**

**✅ TRADE if:**
- Z-Score between 2.0-3.0 (strong but not extreme)
- Correlation health is HEALTHY or DRIFTING
- Historical win rate ≥ 45% (or learning mode)
- Mean reversion rate > 40%

**⛔ SKIP if:**
- Z-Score > 3.5 (extreme - regime change)
- Correlation health is BROKEN
- Historical win rate < 35%
- Multiple recent losses on same pair

**⚠️ REDUCE_SIZE if:**
- Z-Score > 3.0 but < 3.5
- Correlation is DRIFTING
- Win rate between 35-45%

**AI Output:**
```json
{
    "action": "TRADE" | "SKIP" | "REDUCE_SIZE",
    "confidence": 1-10,
    "reasoning": "Brief explanation",
    "risk_level": "LOW" | "MEDIUM" | "HIGH",
    "expected_hold_time": "minutes estimate"
}
```

### Position Opening

If AI approves, a **hedged position** is opened:

**Example:**
```
📈 OPENED ARBITRAGE POSITION #1
============================================================
   Pair: EUR_GBP
   Z-Score: 2.35 (MODERATE)
   Correlation: 0.920
   
   LEG A: SELL eurusd @ 1.08500
   LEG B: BUY gbpusd @ 1.27040
   
   AI Confidence: 7/10
   Risk Level: MEDIUM
============================================================
```

**Position Structure:**
- **Trade ID**: Unique identifier
- **Entry prices**: For both legs
- **Entry Z-score**: For exit comparison
- **Entry correlation**: For health tracking
- **AI context**: Confidence and risk level

---

## Risk Management

### Exit Conditions

Positions are monitored every tick and closed when:

#### 1. **Mean Reversion (Take Profit)**
```
|current_z_score| < 0.5
```
- Spread has reverted to mean
- Target achieved

#### 2. **Time-Based Exit**
- **Per-pair hold limits:**
  - EUR_GBP: 10 minutes (underperforming - faster exit)
  - EUR_CHF_MIRROR: 15 minutes (star performer)
  - COMMODITY_TWINS: 12 minutes (moderate)
- **Global max**: 15 minutes (reduced from 60)
- If spread hasn't reverted, likely not mean reverting

#### 3. **Stop Loss**
```
|current_z_score| > 3.5
```
- Divergence worsened instead of reverting
- Likely regime change, not mean reversion
- Cut losses early

### Position Monitoring

**Real-time P&L Calculation:**
```python
# For each leg, calculate P&L in pips
if action == 'BUY':
    pnl = (current_price - entry_price) * pip_multiplier
else:  # SELL
    pnl = (entry_price - current_price) * pip_multiplier

total_pnl = pnl_leg_a + pnl_leg_b
```

**Pip Multipliers:**
- Standard pairs (EUR/USD, GBP/USD, etc.): `1 / 0.0001 = 10,000`
- JPY pairs (EUR/JPY, GBP/JPY): `1 / 0.01 = 100`

### Risk Limits

1. **Max Concurrent Trades**: 2
2. **Max Hold Time**: 15 minutes (per-pair limits apply)
3. **Stop Loss Z-Score**: 3.5
4. **Consecutive Loss Pause**: 3 losses → pause trading
5. **Cooldown**: 8 minutes between trades on same pair

### Position Closure Example

```
✅ CLOSED POSITION: EUR_GBP
============================================================
   Reason: MEAN_REVERSION
   Hold Time: 8 minutes
   Z-Score: 2.35 → 0.42
   
   LEG A: +12.3 pips (1.08500 → 1.08377)
   LEG B: +8.7 pips (1.27040 → 1.27127)
   
   TOTAL PnL: +21.0 pips
   Session Total: +45.2 pips
============================================================
```

---

## Learning System

### Pair Memory (Pinecone Vector Store)

Every completed trade is saved to Pinecone with rich context:

**Stored Information:**
- Signal context (Z-score, spread, correlation)
- Trade execution (prices, actions)
- Results (outcome, P&L, hold time, exit reason)
- Key lessons (mean reversion success, pair performance)

### Similarity Search

When a new signal appears, the system searches for similar historical setups:

**Query:**
```
{pair_name} divergence 
z-score {z_score} 
correlation {correlation} 
{correlation_health} correlation health
{strength} signal strength
```

**Analysis Returns:**
- Similar trade count
- Win rate for similar setups
- Average P&L
- Mean reversion rate
- Same-pair performance
- Trading recommendation

**Example Output:**
```
📊 HISTORICAL ANALYSIS (8 similar setups):
├─ Win Rate: 5/8 (62.5%)
├─ Avg PnL: +12.5 pips
├─ Avg Hold: 8 min
├─ Mean Reversion Rate: 75.0%
│
├─ Same Pair (EUR_GBP): 7/10 wins
├─ Similar Z-Score: 4/5 wins
│
└─ Recommendation: ✅ TRADE
```

### Learning Mode

**Phase 1: Learning Mode** (< 20 trades)
- Takes trades to build history
- No filtering based on win rate
- AI still evaluates but with lower threshold

**Phase 2: Adaptive Mode** (≥ 20 trades)
- Uses historical context for filtering
- Skips trades with < 35% win rate
- Reduces size for 35-45% win rate

### Performance Tracking

The system tracks:
- Win rate by pair
- Win rate by Z-score range
- Mean reversion success rate
- Average hold times
- Best/worst trades

---

## Configuration

### Trading Parameters

```python
# Signal Detection
Z_SCORE_ENTRY_THRESHOLD = 2.0      # Minimum Z-score to generate signal
Z_SCORE_EXTREME_THRESHOLD = 3.0    # Extreme divergence - skip
Z_SCORE_EXIT_THRESHOLD = 0.5       # Close when spread normalizes
SKIP_EXTREME_ZSCORE = True         # Skip trades with Z > 3.0

# Correlation Health
CORRELATION_DRIFT_WARNING = 0.15   # Warn if correlation drifts by this much
CORRELATION_BREAKDOWN = 0.25       # Skip trades if correlation broken

# Position Management
MAX_CONCURRENT_TRADES = 2          # Max open positions
MAX_HOLD_MINUTES = 15              # Global max hold time
STOP_LOSS_ZSCORE = 3.5             # Stop if Z-score goes further against us

# Risk Management
CONSECUTIVE_LOSS_PAUSE = 3         # Pause after this many losses
MIN_MINUTES_BETWEEN_TRADES = 8     # Cooldown between trades

# Per-pair hold limits
PAIR_MAX_HOLD = {
    "EUR_GBP": 10,          # Faster exit
    "EUR_CHF_MIRROR": 15,   # Star performer - give it room
    "COMMODITY_TWINS": 12,  # Moderate
}

# Data Requirements
LOOKBACK_PERIOD = 30               # Minutes for correlation calculation
MIN_DATA_POINTS = 15               # Minimum data points before trading
BUFFER_SIZE = 60                   # Price buffer size (minutes)

# Learning Mode
LEARNING_TRADES_REQUIRED = 20      # Build this much history before filtering
```

### Currency Pairs

**Active Pairs:**
- **EUR_GBP**: EUR/USD ↔ GBP/USD (positive, 0.95)
- **COMMODITY_TWINS**: AUD/USD ↔ NZD/USD (positive, 0.95)
- **EUR_CHF_MIRROR**: EUR/USD ↔ USD/CHF (negative, -0.95)

**Disabled:**
- **COMMODITY_SPLIT**: AUD/USD ↔ USD/CAD (0% win rate - not mean reverting)

---

## Workflow Example

### Complete Trade Lifecycle

#### **Step 1: Price Update**
```
💱 EURUSD: 1.08500
💱 GBPUSD: 1.27040
```

#### **Step 2: Correlation Check** (Every 60 seconds)
```
📊 CORRELATION STATUS
============================================================
✅ EUR_GBP: 0.920 (exp: 0.95) | HEALTHY
✅ COMMODITY_TWINS: 0.940 (exp: 0.95) | HEALTHY
✅ EUR_CHF_MIRROR: -0.930 (exp: -0.95) | HEALTHY
============================================================
```

#### **Step 3: Signal Detection** (Every 60 seconds)
```
🔴 DIVERGENCE SIGNAL: EUR_GBP
============================================================
   Z-Score: 2.35 (MODERATE)
   Spread: 0.002300 (mean: 0.000500)
   Correlation: 0.920 (HEALTHY)
   
   📈 ACTION:
      → SELL eurusd @ 1.08500
      → BUY gbpusd @ 1.27040
============================================================
```

#### **Step 4: Historical Context**
```
📊 HISTORICAL ANALYSIS (8 similar setups):
├─ Win Rate: 5/8 (62.5%)
├─ Avg PnL: +12.5 pips
├─ Mean Reversion Rate: 75.0%
└─ Recommendation: ✅ TRADE
```

#### **Step 5: AI Evaluation**
```
🤖 AI Decision: TRADE (Confidence: 7/10)
   Reason: Strong divergence with healthy correlation. 
           Historical win rate 62.5% supports trade.
   History: 8 similar, 62.5% win rate
```

#### **Step 6: Position Opening**
```
📈 OPENED ARBITRAGE POSITION #1
============================================================
   Pair: EUR_GBP
   Z-Score: 2.35 (MODERATE)
   Correlation: 0.920
   
   LEG A: SELL eurusd @ 1.08500
   LEG B: BUY gbpusd @ 1.27040
   
   AI Confidence: 7/10
   Risk Level: MEDIUM
============================================================
```

#### **Step 7: Position Monitoring** (Every tick)
```
💱 EURUSD: 1.08450 | Positions: 1 | PnL: +5.2
💱 GBPUSD: 1.27080 | Positions: 1 | PnL: +8.7
```

#### **Step 8: Exit Detection**
```
Current Z-Score: 0.42 (< 0.5 threshold)
→ MEAN_REVERSION exit triggered
```

#### **Step 9: Position Closure**
```
✅ CLOSED POSITION: EUR_GBP
============================================================
   Reason: MEAN_REVERSION
   Hold Time: 8 minutes
   Z-Score: 2.35 → 0.42
   
   LEG A: +12.3 pips (1.08500 → 1.08377)
   LEG B: +8.7 pips (1.27040 → 1.27127)
   
   TOTAL PnL: +21.0 pips
   Session Total: +45.2 pips
============================================================
```

#### **Step 10: Learning Save**
```
🧠 ARBITRAGE LEARNING SAVED:
   EUR_GBP | Z: 2.35 → 0.42
   WIN | PnL: +21.0 pips | 8min
```

---

## Key Insights

### Why This Works

1. **Statistical Edge**: Correlated pairs have a strong tendency to revert to mean
2. **Hedged Positions**: Market direction risk is minimized (betting on spread, not direction)
3. **AI Filtering**: GPT-4 evaluates context that pure algorithms miss
4. **Learning System**: Improves over time by learning from past trades
5. **Risk Management**: Multiple layers prevent catastrophic losses

### Common Pitfalls Avoided

1. **Regime Changes**: Extreme Z-scores (>3.0) are skipped (not mean reverting)
2. **Correlation Breakdown**: Trades skipped when correlation deviates >25%
3. **Overtrading**: Cooldowns and position limits prevent excessive trading
4. **Revenge Trading**: Pause after 3 consecutive losses
5. **Holding Too Long**: Per-pair time limits prevent holding losing trades

### Performance Optimization

- **v2 Improvements:**
  - Reduced max concurrent trades: 3 → 2 (quality over quantity)
  - Reduced max hold: 60min → 15min (faster exits)
  - Increased cooldown: 5min → 8min (reduce overtrading)
  - Per-pair hold limits (faster exits for underperformers)

---

## Summary

This arbitrage system combines:
- **Statistical methods** (Z-scores, correlations)
- **AI decision-making** (GPT-4 evaluation)
- **Machine learning** (Pinecone similarity search)
- **Risk management** (multiple safety layers)

To create a robust, adaptive trading system that exploits temporary divergences between correlated currency pairs while managing risk through multiple filters and exit conditions.

The system is **self-improving** - it learns from every trade and uses that knowledge to make better decisions in the future.

