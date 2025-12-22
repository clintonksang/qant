"""
Position Manager for Currency Pair Arbitrage
Manages hedged positions across multiple currency pairs
Integrates with MT5 for live trade execution
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
    PAIR_INFO,
    PAIR_MAX_HOLD,
    LIVE_TRADING,
    MT5_VOLUME,
    MT5_MAGIC,
    MIN_PROFIT_PIPS,      # v3: New profit threshold
    MAX_LOSS_PIPS,        # v4: Maximum loss before exit
    LOSS_EXIT_MINUTES,    # v4: Exit losers after this time
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
    "PairA", "ActionA", "EntryA", "ExitA", "PnlA", "TicketA",
    "PairB", "ActionB", "EntryB", "ExitB", "PnlB", "TicketB",
    "EntryZScore", "ExitZScore", "TotalPnL", 
    "HoldMinutes", "Status", "ExitReason", "LiveTrade"
]


class PositionManager:
    """
    Manages arbitrage positions (hedged pairs trades).
    Each position consists of two legs: one for each currency pair.
    Supports both paper trading and live MT5 execution.
    """
    
    def __init__(self):
        self.active_positions = []
        self.closed_positions = []
        self.consecutive_losses = 0
        self.last_trade_time = {}  # Per-pair cooldown
        self.total_pnl = 0
        self.live_trading = LIVE_TRADING
        
        # Initialize MT5 Executor for live trading
        self.executor = None
        if self.live_trading:
            try:
                from mt5_executor import MT5Executor
                self.executor = MT5Executor(volume=MT5_VOLUME, magic=MT5_MAGIC)
                
                # Test connection
                if self.executor.test_connection():
                    print(f"🟢 LIVE TRADING MODE ENABLED")
                else:
                    print(f"⚠️ MT5 connection failed - falling back to paper trading")
                    self.live_trading = False
                    self.executor = None
            except Exception as e:
                print(f"⚠️ Failed to initialize MT5 Executor: {e}")
                print(f"📝 Running in PAPER TRADING mode")
                self.live_trading = False
                self.executor = None
        else:
            print(f"📝 PAPER TRADING MODE (set LIVE_TRADING=true to enable live trades)")
        
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
        
        # Initialize position with signal data
        position = {
            'id': trade_id,
            'pair_name': pair_name,
            'open_time': time.time(),
            'timestamp': datetime.now().isoformat(),
            
            # Leg A
            'pair_a': signal['pair_a'],
            'action_a': signal['action_a'],
            'entry_a': signal['price_a'],
            'ticket_a': None,  # MT5 ticket
            
            # Leg B
            'pair_b': signal['pair_b'],
            'action_b': signal['action_b'],
            'entry_b': signal['price_b'],
            'ticket_b': None,  # MT5 ticket
            
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
            'current_pnl': 0,
            'is_live': self.live_trading
        }
        
        # ============================================================
        # EXECUTE LIVE TRADES VIA MT5
        # ============================================================
        if self.live_trading and self.executor:
            print(f"\n🚀 EXECUTING LIVE TRADE...")
            
            broker_result = self.executor.execute_arbitrage_entry(signal)
            
            if not broker_result['success']:
                print(f"❌ BROKER EXECUTION FAILED: {broker_result.get('error', 'Unknown error')}")
                print(f"📝 Trade will NOT be recorded")
                return None
            
            # Store broker tickets and actual execution prices
            position['ticket_a'] = broker_result['ticket_a']
            position['ticket_b'] = broker_result['ticket_b']
            position['entry_a'] = broker_result['price_a']  # Use actual execution price
            position['entry_b'] = broker_result['price_b']  # Use actual execution price
            
            print(f"✅ LIVE TRADE EXECUTED")
            print(f"   Ticket A: #{position['ticket_a']} @ {position['entry_a']:.5f}")
            print(f"   Ticket B: #{position['ticket_b']} @ {position['entry_b']:.5f}")
        
        # Add position to active list
        self.active_positions.append(position)
        self.last_trade_time[pair_name] = time.time()
        
        # Log opening
        trade_mode = "🟢 LIVE" if self.live_trading else "📝 PAPER"
        print(f"\n{'='*60}")
        print(f"📈 OPENED ARBITRAGE POSITION #{len(self.active_positions)} ({trade_mode})")
        print(f"{'='*60}")
        print(f"   Pair: {pair_name}")
        print(f"   Z-Score: {signal['z_score']:.2f} ({signal['strength']})")
        print(f"   Correlation: {signal['correlation']:.3f}")
        print(f"   ")
        print(f"   LEG A: {signal['action_a']} {signal['pair_a'].upper()} @ {position['entry_a']:.5f}")
        if position['ticket_a']:
            print(f"          Ticket: #{position['ticket_a']}")
        print(f"   LEG B: {signal['action_b']} {signal['pair_b'].upper()} @ {position['entry_b']:.5f}")
        if position['ticket_b']:
            print(f"          Ticket: #{position['ticket_b']}")
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
            total_pnl = pnl_a + pnl_b
            hold_minutes = (time.time() - position['open_time']) / 60
            pair_name = position['pair_name']
            max_hold = PAIR_MAX_HOLD.get(pair_name, MAX_HOLD_MINUTES)
            
            # 1. Mean reversion - take profit (spread normalized)
            if abs(z_score) < Z_SCORE_EXIT_THRESHOLD:
                exit_reason = "MEAN_REVERSION"
            
            # 2. v3: PROFIT TARGET - Exit if we hit minimum profit threshold
            elif total_pnl >= MIN_PROFIT_PIPS:
                exit_reason = "PROFIT_TARGET"
            
            # 3. v4: MAX LOSS PROTECTION - Cut losses early! (prevents -6.6 disasters)
            elif total_pnl <= MAX_LOSS_PIPS:
                exit_reason = "MAX_LOSS"
            
            # 4. v4: TIMED LOSS EXIT - After LOSS_EXIT_MINUTES, exit any loser
            elif hold_minutes >= LOSS_EXIT_MINUTES and total_pnl < 0:
                exit_reason = "TIMED_LOSS"
            
            # 5. Time-based exit - strict max hold (no more 1.5x buffer!)
            elif hold_minutes >= max_hold:
                if total_pnl > 0:
                    exit_reason = "TIME_EXIT_PROFIT"
                else:
                    exit_reason = "TIME_EXIT"  # v4: Exit immediately at max hold
            
            # 6. Stop loss - Z-score went further against us
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
        Executes live close via MT5 if in live trading mode.
        """
        hold_minutes = int((time.time() - position['open_time']) / 60)
        total_pnl = pnl_a + pnl_b
        
        # ============================================================
        # CLOSE LIVE TRADES VIA MT5
        # ============================================================
        actual_exit_a = exit_a  # Default to WebSocket price
        actual_exit_b = exit_b  # Default to WebSocket price
        
        if position.get('is_live') and self.executor and position.get('ticket_a'):
            print(f"\n🔒 CLOSING LIVE POSITION: {position['pair_name']}")
            
            close_result = self.executor.close_arbitrage_position(position)
            
            if close_result['success']:
                print(f"✅ LIVE POSITION CLOSED SUCCESSFULLY")
                
                # v4: USE ACTUAL MT5 CLOSE PRICES instead of WebSocket prices!
                if close_result.get('close_price_a', 0) > 0:
                    actual_exit_a = close_result['close_price_a']
                    print(f"   📊 Actual close A: {actual_exit_a:.5f} (was {exit_a:.5f})")
                    
                if close_result.get('close_price_b', 0) > 0:
                    actual_exit_b = close_result['close_price_b']
                    print(f"   📊 Actual close B: {actual_exit_b:.5f} (was {exit_b:.5f})")
                    
                # v4: Recalculate PnL with ACTUAL MT5 prices
                pair_a = position['pair_a']
                pair_b = position['pair_b']
                action_a = position['action_a']
                action_b = position['action_b']
                
                # Recalculate leg A PnL
                pip_mult_a = get_pip_multiplier(pair_a)
                if action_a == "BUY":
                    pnl_a = (actual_exit_a - position['entry_a']) * pip_mult_a
                else:
                    pnl_a = (position['entry_a'] - actual_exit_a) * pip_mult_a
                
                # Recalculate leg B PnL
                pip_mult_b = get_pip_multiplier(pair_b)
                if action_b == "BUY":
                    pnl_b = (actual_exit_b - position['entry_b']) * pip_mult_b
                else:
                    pnl_b = (position['entry_b'] - actual_exit_b) * pip_mult_b
                    
                # Update exit prices to actuals
                exit_a = actual_exit_a
                exit_b = actual_exit_b
                total_pnl = pnl_a + pnl_b
                
                print(f"   📊 Actual PnL: {pnl_a:+.1f} + {pnl_b:+.1f} = {total_pnl:+.1f} pips")
            else:
                print(f"⚠️ LIVE CLOSE HAD ISSUES - Check MT5 manually")
                print(f"   Ticket A: #{position['ticket_a']}")
                print(f"   Ticket B: #{position['ticket_b']}")
        
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
        trade_mode = "🟢 LIVE" if position.get('is_live') else "📝 PAPER"
        print(f"\n{'='*60}")
        print(f"{emoji} CLOSED POSITION: {position['pair_name']} ({trade_mode})")
        print(f"{'='*60}")
        print(f"   Reason: {reason}")
        print(f"   Hold Time: {hold_minutes} minutes")
        print(f"   Z-Score: {position['entry_z_score']:.2f} → {exit_z:.2f}")
        print(f"   ")
        print(f"   LEG A: {pnl_a:+.1f} pips ({position['entry_a']:.5f} → {exit_a:.5f})")
        if position.get('ticket_a'):
            print(f"          Ticket: #{position['ticket_a']}")
        print(f"   LEG B: {pnl_b:+.1f} pips ({position['entry_b']:.5f} → {exit_b:.5f})")
        if position.get('ticket_b'):
            print(f"          Ticket: #{position['ticket_b']}")
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
            position.get('ticket_a', ''),
            position['pair_b'],
            position['action_b'],
            f"{position['entry_b']:.5f}",
            f"{position.get('exit_b', 0):.5f}",
            f"{position.get('pnl_b', 0):.1f}",
            position.get('ticket_b', ''),
            f"{position['entry_z_score']:.2f}",
            f"{position.get('exit_z_score', 0):.2f}",
            f"{position.get('pnl_a', 0) + position.get('pnl_b', 0):.1f}",
            position.get('hold_minutes', 0),
            position.get('outcome', 'UNKNOWN'),
            position.get('exit_reason', 'UNKNOWN'),
            position.get('is_live', False)
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
            "live_trading": self.live_trading,
            "positions": [
                {
                    "pair": p['pair_name'],
                    "z_score": p['entry_z_score'],
                    "pnl": p.get('current_pnl', 0),
                    "hold_min": int((time.time() - p['open_time']) / 60),
                    "ticket_a": p.get('ticket_a'),
                    "ticket_b": p.get('ticket_b'),
                    "is_live": p.get('is_live', False)
                }
                for p in self.active_positions
            ]
        }
    
    def print_status(self):
        """Print formatted status."""
        status = self.get_status()
        
        trade_mode = "🟢 LIVE" if status['live_trading'] else "📝 PAPER"
        print(f"\n{'='*50}")
        print(f"📊 POSITION STATUS ({trade_mode})")
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
                live_tag = " [LIVE]" if p['is_live'] else ""
                print(f"   {emoji} {p['pair']}: Z={p['z_score']:.2f} | PnL: {p['pnl']:+.1f} | {p['hold_min']}min{live_tag}")
                if p.get('ticket_a'):
                    print(f"      Tickets: A=#{p['ticket_a']} B=#{p['ticket_b']}")
        
        print(f"{'='*50}")
    
    def reset_loss_counter(self):
        """Reset consecutive loss counter (call after successful trade or manual reset)."""
        self.consecutive_losses = 0
        print("✅ Loss counter reset")
    
    def sync_with_mt5(self):
        """
        Sync local positions with MT5 positions.
        Useful for recovery after restart.
        """
        if not self.executor:
            print("⚠️ MT5 Executor not available")
            return
        
        print("\n🔄 Syncing with MT5...")
        mt5_positions = self.executor.get_open_positions()
        
        print(f"   Found {len(mt5_positions)} positions in MT5")
        
        for pos in mt5_positions:
            print(f"   - Ticket #{pos['ticket']}: {pos['symbol']} {'BUY' if pos['type']==0 else 'SELL'}")
            print(f"     Entry: {pos['price_open']:.5f} | Current: {pos['price_current']:.5f}")
            print(f"     PnL: {pos['profit']:.2f}")


# Test
if __name__ == "__main__":
    print("Testing Position Manager...")
    print("=" * 60)
    
    pm = PositionManager()
    
    # Test with paper trading signal
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
    
    print("\nOpening test position...")
    pos = pm.open_position(test_signal, test_decision)
    
    print("\nPosition Status:")
    pm.print_status()
    
    print("\nTesting can_open_position...")
    can_open, reason = pm.can_open_position('EUR_GBP')
    print(f"Can open EUR_GBP: {can_open} - {reason}")
    
    if pm.live_trading:
        print("\n🔄 Syncing with MT5...")
        pm.sync_with_mt5()
