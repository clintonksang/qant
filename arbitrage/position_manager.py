"""
Position Manager for Currency Pair Arbitrage
Manages hedged positions across multiple currency pairs
"""

import time
import csv
from datetime import datetime
from pathlib import Path
from config import (
    MAX_CONCURRENT_TRADES,
    MAX_HOLD_MINUTES,
    STOP_LOSS_ZSCORE,
    Z_SCORE_EXIT_THRESHOLD,
    CONSECUTIVE_LOSS_PAUSE,
    MIN_MINUTES_BETWEEN_TRADES,
    PAIR_INFO
)


def get_pip_multiplier(pair):
    """Get the correct pip multiplier for a currency pair."""
    pip_value = PAIR_INFO.get(pair, {}).get('pip_value', 0.0001)
    # Convert to pips: if pip_value is 0.0001, multiply by 10000
    # if pip_value is 0.01 (JPY pairs), multiply by 100
    return 1 / pip_value

# CSV for trade logging
CSV_FILE = Path(__file__).parent / "arbitrage_trades.csv"
CSV_HEADERS = [
    "TradeID", "Timestamp", "PairName", 
    "PairA", "ActionA", "EntryA", "ExitA", "PnlA",
    "PairB", "ActionB", "EntryB", "ExitB", "PnlB",
    "EntryZScore", "ExitZScore", "TotalPnL", 
    "HoldMinutes", "Status", "ExitReason"
]


class PositionManager:
    """
    Manages arbitrage positions (hedged pairs trades).
    Each position consists of two legs: one for each currency pair.
    """
    
    def __init__(self):
        self.active_positions = []
        self.closed_positions = []
        self.consecutive_losses = 0
        self.last_trade_time = {}  # Per-pair cooldown
        self.total_pnl = 0
        
        # Initialize CSV
        self._init_csv()
    
    def _init_csv(self):
        """Initialize trade log CSV."""
        if not CSV_FILE.exists():
            with open(CSV_FILE, 'w', newline='') as f:
                csv.writer(f).writerow(CSV_HEADERS)
    
    def can_open_position(self, pair_name):
        """
        Check if we can open a new position.
        
        Args:
            pair_name: Name of the pair relationship
            
        Returns:
            Tuple of (can_open: bool, reason: str)
        """
        # Check max concurrent trades
        if len(self.active_positions) >= MAX_CONCURRENT_TRADES:
            return False, f"Max positions reached ({MAX_CONCURRENT_TRADES})"
        
        # Check consecutive loss pause
        if self.consecutive_losses >= CONSECUTIVE_LOSS_PAUSE:
            return False, f"Paused after {self.consecutive_losses} consecutive losses"
        
        # Check per-pair cooldown
        if pair_name in self.last_trade_time:
            elapsed = (time.time() - self.last_trade_time[pair_name]) / 60
            if elapsed < MIN_MINUTES_BETWEEN_TRADES:
                remaining = MIN_MINUTES_BETWEEN_TRADES - elapsed
                return False, f"Cooldown: {remaining:.1f}min remaining for {pair_name}"
        
        # Check if already have position in this pair
        for pos in self.active_positions:
            if pos['pair_name'] == pair_name:
                return False, f"Already have open position in {pair_name}"
        
        return True, "OK"
    
    def open_position(self, signal, ai_decision):
        """
        Open a new hedged arbitrage position.
        
        Args:
            signal: Divergence signal from SignalDetector
            ai_decision: Decision from ArbitrageBrain
            
        Returns:
            Position dict if opened, None if not
        """
        pair_name = signal['pair_name']
        
        # Verify we can open
        can_open, reason = self.can_open_position(pair_name)
        if not can_open:
            print(f"⛔ Cannot open position: {reason}")
            return None
        
        trade_id = int(time.time() * 100) % 10000000000
        
        position = {
            'id': trade_id,
            'pair_name': pair_name,
            'open_time': time.time(),
            'timestamp': datetime.now().isoformat(),
            
            # Leg A
            'pair_a': signal['pair_a'],
            'action_a': signal['action_a'],
            'entry_a': signal['price_a'],
            
            # Leg B
            'pair_b': signal['pair_b'],
            'action_b': signal['action_b'],
            'entry_b': signal['price_b'],
            
            # Signal context
            'entry_z_score': signal['z_score'],
            'entry_spread': signal['spread'],
            'entry_correlation': signal['correlation'],
            'signal_strength': signal['strength'],
            
            # AI context
            'ai_confidence': ai_decision.get('confidence', 5),
            'ai_risk_level': ai_decision.get('risk_level', 'MEDIUM'),
            
            # Status
            'status': 'OPEN',
            'current_pnl': 0
        }
        
        self.active_positions.append(position)
        self.last_trade_time[pair_name] = time.time()
        
        # Log opening
        print(f"\n{'='*60}")
        print(f"📈 OPENED ARBITRAGE POSITION #{len(self.active_positions)}")
        print(f"{'='*60}")
        print(f"   Pair: {pair_name}")
        print(f"   Z-Score: {signal['z_score']:.2f} ({signal['strength']})")
        print(f"   Correlation: {signal['correlation']:.3f}")
        print(f"   ")
        print(f"   LEG A: {signal['action_a']} {signal['pair_a'].upper()} @ {signal['price_a']:.5f}")
        print(f"   LEG B: {signal['action_b']} {signal['pair_b'].upper()} @ {signal['price_b']:.5f}")
        print(f"   ")
        print(f"   AI Confidence: {ai_decision.get('confidence', 'N/A')}/10")
        print(f"   Risk Level: {ai_decision.get('risk_level', 'N/A')}")
        print(f"{'='*60}")
        
        return position
    
    def check_exits(self, price_buffers, signal_detector):
        """
        Check all positions for exit conditions.
        
        Args:
            price_buffers: Current prices for all pairs
            signal_detector: SignalDetector instance for Z-score calculation
            
        Returns:
            List of positions that were closed
        """
        positions_to_close = []
        
        for position in self.active_positions:
            pair_a = position['pair_a']
            pair_b = position['pair_b']
            
            # Get current prices
            current_a = price_buffers.get(pair_a, [0])[-1] if price_buffers.get(pair_a) else 0
            current_b = price_buffers.get(pair_b, [0])[-1] if price_buffers.get(pair_b) else 0
            
            if current_a == 0 or current_b == 0:
                continue
            
            # Calculate current P&L for each leg (using correct pip multiplier)
            pip_mult_a = get_pip_multiplier(pair_a)
            pip_mult_b = get_pip_multiplier(pair_b)
            
            if position['action_a'] == 'BUY':
                pnl_a = (current_a - position['entry_a']) * pip_mult_a
            else:
                pnl_a = (position['entry_a'] - current_a) * pip_mult_a
            
            if position['action_b'] == 'BUY':
                pnl_b = (current_b - position['entry_b']) * pip_mult_b
            else:
                pnl_b = (position['entry_b'] - current_b) * pip_mult_b
            
            position['current_pnl'] = pnl_a + pnl_b
            
            # Calculate current Z-score
            is_positive = position.get('entry_correlation', 0.95) > 0
            spread, z_score, _, _ = signal_detector.calculate_spread(
                price_buffers.get(pair_a, []),
                price_buffers.get(pair_b, []),
                is_positive
            )
            
            if z_score is None:
                continue
            
            # Check exit conditions
            exit_reason = None
            
            # 1. Mean reversion - take profit
            if abs(z_score) < Z_SCORE_EXIT_THRESHOLD:
                exit_reason = "MEAN_REVERSION"
            
            # 2. Time-based exit
            hold_minutes = (time.time() - position['open_time']) / 60
            if hold_minutes >= MAX_HOLD_MINUTES:
                exit_reason = "TIME_EXIT"
            
            # 3. Stop loss - Z-score went further against us
            entry_z = position['entry_z_score']
            if entry_z > 0 and z_score > STOP_LOSS_ZSCORE:
                exit_reason = "STOP_LOSS"
            elif entry_z < 0 and z_score < -STOP_LOSS_ZSCORE:
                exit_reason = "STOP_LOSS"
            
            if exit_reason:
                self._close_position(
                    position, 
                    current_a, current_b, 
                    pnl_a, pnl_b, 
                    z_score, 
                    exit_reason
                )
                positions_to_close.append(position)
        
        # Remove closed positions
        for pos in positions_to_close:
            self.active_positions.remove(pos)
        
        return positions_to_close
    
    def _close_position(self, position, exit_a, exit_b, pnl_a, pnl_b, exit_z, reason):
        """
        Close a position and log the result.
        """
        hold_minutes = int((time.time() - position['open_time']) / 60)
        total_pnl = pnl_a + pnl_b
        
        # Determine outcome
        if total_pnl > 0:
            outcome = "WIN"
            self.consecutive_losses = 0
            emoji = "✅"
        else:
            outcome = "LOSS"
            self.consecutive_losses += 1
            emoji = "❌"
        
        self.total_pnl += total_pnl
        
        # Update position
        position['status'] = 'CLOSED'
        position['exit_a'] = exit_a
        position['exit_b'] = exit_b
        position['pnl_a'] = pnl_a
        position['pnl_b'] = pnl_b
        position['exit_z_score'] = exit_z
        position['exit_reason'] = reason
        position['hold_minutes'] = hold_minutes
        position['outcome'] = outcome
        
        self.closed_positions.append(position)
        
        # Log to CSV
        self._log_trade(position)
        
        # Print result
        print(f"\n{'='*60}")
        print(f"{emoji} CLOSED POSITION: {position['pair_name']}")
        print(f"{'='*60}")
        print(f"   Reason: {reason}")
        print(f"   Hold Time: {hold_minutes} minutes")
        print(f"   Z-Score: {position['entry_z_score']:.2f} → {exit_z:.2f}")
        print(f"   ")
        print(f"   LEG A: {pnl_a:+.1f} pips ({position['entry_a']:.5f} → {exit_a:.5f})")
        print(f"   LEG B: {pnl_b:+.1f} pips ({position['entry_b']:.5f} → {exit_b:.5f})")
        print(f"   ")
        print(f"   TOTAL PnL: {total_pnl:+.1f} pips")
        print(f"   Session Total: {self.total_pnl:+.1f} pips")
        
        if self.consecutive_losses > 0:
            print(f"   ⚠️ Consecutive Losses: {self.consecutive_losses}")
        
        print(f"{'='*60}")
        
        return position
    
    def _log_trade(self, position):
        """Log closed trade to CSV."""
        row = [
            position['id'],
            position['timestamp'],
            position['pair_name'],
            position['pair_a'],
            position['action_a'],
            f"{position['entry_a']:.5f}",
            f"{position.get('exit_a', 0):.5f}",
            f"{position.get('pnl_a', 0):.1f}",
            position['pair_b'],
            position['action_b'],
            f"{position['entry_b']:.5f}",
            f"{position.get('exit_b', 0):.5f}",
            f"{position.get('pnl_b', 0):.1f}",
            f"{position['entry_z_score']:.2f}",
            f"{position.get('exit_z_score', 0):.2f}",
            f"{position.get('pnl_a', 0) + position.get('pnl_b', 0):.1f}",
            position.get('hold_minutes', 0),
            position.get('outcome', 'UNKNOWN'),
            position.get('exit_reason', 'UNKNOWN')
        ]
        
        with open(CSV_FILE, 'a', newline='') as f:
            csv.writer(f).writerow(row)
    
    def force_close_all(self, price_buffers, reason="MANUAL"):
        """Force close all positions (e.g., for shutdown)."""
        for position in self.active_positions[:]:  # Copy list to iterate
            pair_a = position['pair_a']
            pair_b = position['pair_b']
            
            current_a = price_buffers.get(pair_a, [position['entry_a']])[-1]
            current_b = price_buffers.get(pair_b, [position['entry_b']])[-1]
            
            # Use correct pip multiplier
            pip_mult_a = get_pip_multiplier(pair_a)
            pip_mult_b = get_pip_multiplier(pair_b)
            
            if position['action_a'] == 'BUY':
                pnl_a = (current_a - position['entry_a']) * pip_mult_a
            else:
                pnl_a = (position['entry_a'] - current_a) * pip_mult_a
            
            if position['action_b'] == 'BUY':
                pnl_b = (current_b - position['entry_b']) * pip_mult_b
            else:
                pnl_b = (position['entry_b'] - current_b) * pip_mult_b
            
            self._close_position(
                position, current_a, current_b,
                pnl_a, pnl_b, 0, reason
            )
            self.active_positions.remove(position)
    
    def get_status(self):
        """Get current position manager status."""
        return {
            "active_positions": len(self.active_positions),
            "closed_today": len(self.closed_positions),
            "total_pnl": self.total_pnl,
            "consecutive_losses": self.consecutive_losses,
            "positions": [
                {
                    "pair": p['pair_name'],
                    "z_score": p['entry_z_score'],
                    "pnl": p.get('current_pnl', 0),
                    "hold_min": int((time.time() - p['open_time']) / 60)
                }
                for p in self.active_positions
            ]
        }
    
    def print_status(self):
        """Print formatted status."""
        status = self.get_status()
        
        print(f"\n{'='*50}")
        print(f"📊 POSITION STATUS")
        print(f"{'='*50}")
        print(f"   Active: {status['active_positions']}/{MAX_CONCURRENT_TRADES}")
        print(f"   Closed Today: {status['closed_today']}")
        print(f"   Session PnL: {status['total_pnl']:+.1f} pips")
        
        if status['consecutive_losses'] > 0:
            print(f"   ⚠️ Consecutive Losses: {status['consecutive_losses']}")
        
        if status['positions']:
            print(f"\n   OPEN POSITIONS:")
            for p in status['positions']:
                emoji = '🟢' if p['pnl'] > 0 else '🔴'
                print(f"   {emoji} {p['pair']}: Z={p['z_score']:.2f} | PnL: {p['pnl']:+.1f} | {p['hold_min']}min")
        
        print(f"{'='*50}")
    
    def reset_loss_counter(self):
        """Reset consecutive loss counter (call after successful trade or manual reset)."""
        self.consecutive_losses = 0
        print("✅ Loss counter reset")


# Test
if __name__ == "__main__":
    pm = PositionManager()
    
    # Test opening
    test_signal = {
        'pair_name': 'EUR_GBP',
        'pair_a': 'eurusd',
        'pair_b': 'gbpusd',
        'price_a': 1.0850,
        'price_b': 1.2704,
        'z_score': 2.35,
        'spread': 0.0023,
        'correlation': 0.92,
        'strength': 'MODERATE',
        'action_a': 'SELL',
        'action_b': 'BUY'
    }
    
    test_decision = {
        'action': 'TRADE',
        'confidence': 7,
        'risk_level': 'MEDIUM'
    }
    
    pos = pm.open_position(test_signal, test_decision)
    pm.print_status()
    
    print("\nTesting can_open_position...")
    can_open, reason = pm.can_open_position('EUR_GBP')
    print(f"Can open EUR_GBP: {can_open} - {reason}")

