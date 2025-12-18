"""
Signal Detector for Currency Pair Arbitrage
Identifies divergence opportunities between correlated pairs
"""

import numpy as np
from datetime import datetime
from config import (
    Z_SCORE_ENTRY_THRESHOLD, 
    Z_SCORE_EXTREME_THRESHOLD,
    Z_SCORE_EXIT_THRESHOLD,
    MIN_DATA_POINTS
)


class SignalDetector:
    """
    Detects tradeable divergence signals between correlated currency pairs.
    Uses Z-score to identify when spreads deviate from their historical mean.
    """
    
    def __init__(self):
        self.active_signals = {}  # Track active signals for exit detection
        self.signal_history = []  # Log of all signals generated
    
    def calculate_spread(self, prices_a, prices_b, is_positive_pair):
        """
        Calculate the normalized spread between two pairs.
        
        For positive correlation: spread = norm_a - norm_b (should be ~0)
        For negative correlation: spread = norm_a + norm_b - 2 (should be ~0)
        
        Args:
            prices_a: List of prices for pair A
            prices_b: List of prices for pair B
            is_positive_pair: True if pairs are positively correlated
            
        Returns:
            Tuple of (current_spread, z_score, mean_spread, std_spread)
        """
        if len(prices_a) < MIN_DATA_POINTS or len(prices_b) < MIN_DATA_POINTS:
            return None, None, None, None
        
        # Use the smaller available window
        window = min(len(prices_a), len(prices_b), 30)
        
        # Normalize prices (percentage from start of window)
        norm_a = np.array(prices_a[-window:]) / prices_a[-window]
        norm_b = np.array(prices_b[-window:]) / prices_b[-window]
        
        # Calculate spread based on correlation type
        if is_positive_pair:
            # Positive correlation: A and B should move together
            # Spread = A - B, should be near 0
            spread = norm_a - norm_b
        else:
            # Negative correlation: A and B should move opposite
            # When A goes up, B goes down (and vice versa)
            # Spread = A + B - 2, should be near 0 if perfectly negatively correlated
            spread = norm_a + norm_b - 2
        
        # Calculate Z-score of current spread vs historical
        if len(spread) < 5:
            return None, None, None, None
        
        # Use all but last value for mean/std (to avoid look-ahead bias)
        historical_spread = spread[:-1]
        current_spread = spread[-1]
        
        mean_spread = np.mean(historical_spread)
        std_spread = np.std(historical_spread)
        
        # Avoid division by zero
        if std_spread < 0.0001:
            std_spread = 0.0001
        
        z_score = (current_spread - mean_spread) / std_spread
        
        return current_spread, z_score, mean_spread, std_spread
    
    def check_divergences(self, correlations, price_buffers):
        """
        Check all pairs for tradeable divergence signals.
        
        Args:
            correlations: List of correlation results from CorrelationEngine
            price_buffers: Dict of ticker -> list of prices
            
        Returns:
            List of signal dicts for pairs that exceed Z-score threshold
        """
        signals = []
        
        for corr_data in correlations:
            pair_a = corr_data['pair_a']
            pair_b = corr_data['pair_b']
            pair_name = corr_data['name']
            
            # Skip if correlation is broken (regime change)
            if corr_data['health'] == 'BROKEN':
                continue
            
            # Calculate spread and Z-score
            spread, z_score, mean, std = self.calculate_spread(
                price_buffers[pair_a],
                price_buffers[pair_b],
                corr_data['is_positive_pair']
            )
            
            if z_score is None:
                continue
            
            # Check if Z-score exceeds entry threshold
            if abs(z_score) > Z_SCORE_ENTRY_THRESHOLD:
                # Determine trading direction based on Z-score sign
                # Positive Z-score: Pair A overvalued relative to B → SELL A, BUY B
                # Negative Z-score: Pair B overvalued relative to A → BUY A, SELL B
                
                if z_score > 0:
                    action_a = 'SELL'
                    action_b = 'BUY'
                else:
                    action_a = 'BUY'
                    action_b = 'SELL'
                
                # Determine signal strength
                if abs(z_score) > Z_SCORE_EXTREME_THRESHOLD:
                    strength = 'EXTREME'
                    warning = 'Extreme divergence - may be regime change!'
                else:
                    strength = 'STRONG' if abs(z_score) > 2.5 else 'MODERATE'
                    warning = None
                
                signal = {
                    'timestamp': datetime.now().isoformat(),
                    'pair_name': pair_name,
                    'pair_a': pair_a,
                    'pair_b': pair_b,
                    'price_a': price_buffers[pair_a][-1],
                    'price_b': price_buffers[pair_b][-1],
                    'spread': round(spread, 6),
                    'z_score': round(z_score, 3),
                    'mean_spread': round(mean, 6),
                    'std_spread': round(std, 6),
                    'correlation': corr_data['current_corr'],
                    'expected_corr': corr_data['expected_corr'],
                    'correlation_health': corr_data['health'],
                    'is_positive_pair': corr_data['is_positive_pair'],
                    'signal_type': 'DIVERGENCE',
                    'strength': strength,
                    'warning': warning,
                    
                    # Trading actions
                    'action_a': action_a,
                    'action_b': action_b,
                    
                    # For position sizing
                    'volatility': std,
                }
                
                signals.append(signal)
                self.signal_history.append(signal)
                
                # Log the signal
                self._log_signal(signal)
        
        return signals
    
    def check_exit_signal(self, pair_name, prices_a, prices_b, is_positive_pair, entry_z_score):
        """
        Check if a position should be closed.
        Exit when spread returns to mean (Z-score approaches 0).
        
        Args:
            pair_name: Name of the pair relationship
            prices_a: Current prices for pair A
            prices_b: Current prices for pair B
            is_positive_pair: Correlation type
            entry_z_score: Z-score when position was opened
            
        Returns:
            Dict with exit signal if criteria met, None otherwise
        """
        spread, z_score, mean, std = self.calculate_spread(
            prices_a, prices_b, is_positive_pair
        )
        
        if z_score is None:
            return None
        
        # Exit conditions:
        # 1. Z-score has reverted to near zero (take profit)
        # 2. Z-score has moved further against us (stop loss)
        
        # Take profit: Z-score close to 0
        if abs(z_score) < Z_SCORE_EXIT_THRESHOLD:
            return {
                'exit_type': 'MEAN_REVERSION',
                'z_score': z_score,
                'message': f'✅ Spread reverted to mean (Z: {z_score:.2f})'
            }
        
        # Stop loss: Z-score went further in same direction
        # (divergence got worse instead of reverting)
        if entry_z_score > 0 and z_score > entry_z_score + 1.0:
            return {
                'exit_type': 'STOP_LOSS',
                'z_score': z_score,
                'message': f'❌ Divergence worsened (Z: {entry_z_score:.2f} → {z_score:.2f})'
            }
        elif entry_z_score < 0 and z_score < entry_z_score - 1.0:
            return {
                'exit_type': 'STOP_LOSS',
                'z_score': z_score,
                'message': f'❌ Divergence worsened (Z: {entry_z_score:.2f} → {z_score:.2f})'
            }
        
        return None
    
    def get_current_spreads(self, correlations, price_buffers):
        """
        Get current spread status for all pairs (for monitoring).
        
        Returns:
            Dict of pair_name -> spread info
        """
        spreads = {}
        
        for corr_data in correlations:
            pair_a = corr_data['pair_a']
            pair_b = corr_data['pair_b']
            pair_name = corr_data['name']
            
            spread, z_score, mean, std = self.calculate_spread(
                price_buffers.get(pair_a, []),
                price_buffers.get(pair_b, []),
                corr_data['is_positive_pair']
            )
            
            if z_score is not None:
                spreads[pair_name] = {
                    'spread': round(spread, 6),
                    'z_score': round(z_score, 3),
                    'mean': round(mean, 6),
                    'std': round(std, 6),
                    'status': self._get_status(z_score)
                }
        
        return spreads
    
    def _get_status(self, z_score):
        """Get status label based on Z-score."""
        abs_z = abs(z_score)
        if abs_z < 1.0:
            return 'NORMAL'
        elif abs_z < Z_SCORE_ENTRY_THRESHOLD:
            return 'ELEVATED'
        elif abs_z < Z_SCORE_EXTREME_THRESHOLD:
            return 'SIGNAL'
        else:
            return 'EXTREME'
    
    def _log_signal(self, signal):
        """Print formatted signal to console."""
        emoji = '🔴' if signal['action_a'] == 'SELL' else '🟢'
        
        print(f"\n{'='*60}")
        print(f"{emoji} DIVERGENCE SIGNAL: {signal['pair_name']}")
        print(f"{'='*60}")
        print(f"   Z-Score: {signal['z_score']:.2f} ({signal['strength']})")
        print(f"   Spread: {signal['spread']:.6f} (mean: {signal['mean_spread']:.6f})")
        print(f"   Correlation: {signal['correlation']:.3f} ({signal['correlation_health']})")
        print(f"   ")
        print(f"   📈 ACTION:")
        print(f"      → {signal['action_a']} {signal['pair_a'].upper()} @ {signal['price_a']:.5f}")
        print(f"      → {signal['action_b']} {signal['pair_b'].upper()} @ {signal['price_b']:.5f}")
        
        if signal['warning']:
            print(f"   ")
            print(f"   ⚠️  {signal['warning']}")
        
        print(f"{'='*60}")
    
    def get_signal_stats(self):
        """Get statistics about generated signals."""
        if not self.signal_history:
            return {'total_signals': 0}
        
        return {
            'total_signals': len(self.signal_history),
            'by_pair': self._count_by_field('pair_name'),
            'by_strength': self._count_by_field('strength'),
            'avg_z_score': round(np.mean([abs(s['z_score']) for s in self.signal_history]), 2)
        }
    
    def _count_by_field(self, field):
        """Count signals grouped by a field."""
        counts = {}
        for s in self.signal_history:
            val = s.get(field, 'UNKNOWN')
            counts[val] = counts.get(val, 0) + 1
        return counts


# Test the detector
if __name__ == "__main__":
    detector = SignalDetector()
    
    # Simulate diverging prices
    import random
    random.seed(42)
    
    # Base price that trends up
    base = [1.0 + i * 0.001 for i in range(40)]
    
    # Pair B should follow but lags behind (creating divergence)
    diverging = [1.0 + (i - 3) * 0.001 for i in range(40)]  # 3 periods behind
    
    test_buffers = {
        'eurusd': base,
        'gbpusd': diverging
    }
    
    # Fake correlation data
    test_correlations = [{
        'name': 'EUR_GBP',
        'pair_a': 'eurusd',
        'pair_b': 'gbpusd',
        'current_corr': 0.92,
        'expected_corr': 0.95,
        'health': 'HEALTHY',
        'is_positive_pair': True
    }]
    
    signals = detector.check_divergences(test_correlations, test_buffers)
    print(f"\nGenerated {len(signals)} signals")
    
    for sig in signals:
        print(f"  {sig['pair_name']}: Z={sig['z_score']:.2f}, {sig['action_a']} {sig['pair_a']}")

