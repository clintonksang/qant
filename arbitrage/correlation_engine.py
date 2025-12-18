"""
Correlation Engine for Currency Pair Arbitrage
Calculates rolling correlations and detects correlation breakdowns
"""

import numpy as np
from datetime import datetime
from config import POSITIVE_PAIRS, NEGATIVE_PAIRS, LOOKBACK_PERIOD, CORRELATION_DRIFT_WARNING, CORRELATION_BREAKDOWN


class CorrelationEngine:
    """
    Calculates and tracks correlations between currency pairs.
    Detects when correlations deviate from expected values.
    """
    
    def __init__(self, lookback=LOOKBACK_PERIOD):
        self.lookback = lookback
        self.correlation_history = {}  # Track correlation over time
        self.last_calculation = {}     # Cache last calculations
    
    def pearson_correlation(self, prices_a, prices_b):
        """
        Calculate Pearson correlation between two price series.
        Uses returns (not prices) for better stationarity.
        
        Args:
            prices_a: List of prices for pair A
            prices_b: List of prices for pair B
            
        Returns:
            Correlation coefficient (-1 to +1) or None if insufficient data
        """
        if len(prices_a) < 10 or len(prices_b) < 10:
            return None
        
        # Align lengths - use the smaller of available data or lookback
        min_len = min(len(prices_a), len(prices_b), self.lookback)
        a = np.array(prices_a[-min_len:])
        b = np.array(prices_b[-min_len:])
        
        # Calculate returns (percentage change) - more stationary than prices
        returns_a = np.diff(a) / a[:-1]
        returns_b = np.diff(b) / b[:-1]
        
        if len(returns_a) < 5:
            return None
        
        # Remove any NaN or inf values
        mask = np.isfinite(returns_a) & np.isfinite(returns_b)
        returns_a = returns_a[mask]
        returns_b = returns_b[mask]
        
        if len(returns_a) < 5:
            return None
        
        # Calculate Pearson correlation
        correlation = np.corrcoef(returns_a, returns_b)[0, 1]
        
        return correlation if np.isfinite(correlation) else None
    
    def calculate_all(self, price_buffers):
        """
        Calculate correlations for all defined pair relationships.
        
        Args:
            price_buffers: Dict of ticker -> list of prices
            
        Returns:
            List of correlation results with deviation analysis
        """
        results = []
        
        all_pairs = POSITIVE_PAIRS + NEGATIVE_PAIRS
        
        for pair_def in all_pairs:
            pair_a = pair_def['pair_a']
            pair_b = pair_def['pair_b']
            
            # Check if we have data for both pairs
            if pair_a not in price_buffers or pair_b not in price_buffers:
                continue
            
            if len(price_buffers[pair_a]) < 10 or len(price_buffers[pair_b]) < 10:
                continue
            
            # Calculate current correlation
            corr = self.pearson_correlation(
                price_buffers[pair_a],
                price_buffers[pair_b]
            )
            
            if corr is None:
                continue
            
            expected = pair_def['expected_corr']
            deviation = corr - expected
            abs_deviation = abs(deviation)
            
            # Determine health status
            if abs_deviation < CORRELATION_DRIFT_WARNING:
                health = "HEALTHY"
            elif abs_deviation < CORRELATION_BREAKDOWN:
                health = "DRIFTING"
            else:
                health = "BROKEN"
            
            # Track correlation history
            pair_name = pair_def['name']
            if pair_name not in self.correlation_history:
                self.correlation_history[pair_name] = []
            self.correlation_history[pair_name].append({
                'correlation': corr,
                'timestamp': datetime.now().isoformat()
            })
            # Keep only last 100 readings
            if len(self.correlation_history[pair_name]) > 100:
                self.correlation_history[pair_name].pop(0)
            
            result = {
                'name': pair_name,
                'pair_a': pair_a,
                'pair_b': pair_b,
                'current_corr': round(corr, 4),
                'expected_corr': expected,
                'deviation': round(deviation, 4),
                'abs_deviation': round(abs_deviation, 4),
                'health': health,
                'is_positive_pair': pair_def in POSITIVE_PAIRS,
                'description': pair_def.get('description', '')
            }
            
            results.append(result)
            self.last_calculation[pair_name] = result
        
        return results
    
    def get_correlation_trend(self, pair_name, periods=10):
        """
        Analyze if correlation is trending up, down, or stable.
        
        Args:
            pair_name: Name of the pair relationship
            periods: Number of recent readings to analyze
            
        Returns:
            Dict with trend analysis
        """
        if pair_name not in self.correlation_history:
            return {'trend': 'UNKNOWN', 'message': 'No history'}
        
        history = self.correlation_history[pair_name]
        if len(history) < periods:
            return {'trend': 'BUILDING', 'message': f'Need {periods} readings, have {len(history)}'}
        
        recent = [h['correlation'] for h in history[-periods:]]
        older = [h['correlation'] for h in history[-periods*2:-periods]] if len(history) >= periods * 2 else recent
        
        recent_avg = np.mean(recent)
        older_avg = np.mean(older)
        change = recent_avg - older_avg
        
        if change > 0.05:
            trend = 'STRENGTHENING'
        elif change < -0.05:
            trend = 'WEAKENING'
        else:
            trend = 'STABLE'
        
        return {
            'trend': trend,
            'recent_avg': round(recent_avg, 4),
            'older_avg': round(older_avg, 4),
            'change': round(change, 4),
            'message': f'Correlation {trend.lower()}: {older_avg:.2f} → {recent_avg:.2f}'
        }
    
    def detect_correlation_breakdown(self, pair_name, current_corr, expected_corr):
        """
        Detect when correlation significantly deviates from expected.
        This is a KEY risk signal - may indicate regime change.
        
        Args:
            pair_name: Name of the pair relationship
            current_corr: Current calculated correlation
            expected_corr: Expected/historical correlation
            
        Returns:
            Dict with breakdown analysis
        """
        deviation = abs(current_corr - expected_corr)
        
        if deviation > CORRELATION_BREAKDOWN:
            severity = 'CRITICAL' if deviation > 0.35 else 'HIGH'
            return {
                'breakdown': True,
                'deviation': round(deviation, 4),
                'severity': severity,
                'message': f"⚠️ {pair_name}: Correlation breakdown! {current_corr:.2f} vs expected {expected_corr:.2f}",
                'recommendation': 'SKIP - Correlation may not revert'
            }
        elif deviation > CORRELATION_DRIFT_WARNING:
            return {
                'breakdown': False,
                'deviation': round(deviation, 4),
                'severity': 'MODERATE',
                'message': f"⚡ {pair_name}: Correlation drifting {current_corr:.2f} vs expected {expected_corr:.2f}",
                'recommendation': 'TRADE with reduced size'
            }
        else:
            return {
                'breakdown': False,
                'deviation': round(deviation, 4),
                'severity': 'LOW',
                'message': f"✅ {pair_name}: Correlation healthy at {current_corr:.2f}",
                'recommendation': 'TRADE normally'
            }
    
    def get_all_health_status(self):
        """Get health status of all tracked correlations."""
        return {
            name: {
                'current': data.get('current_corr'),
                'expected': data.get('expected_corr'),
                'health': data.get('health'),
                'trend': self.get_correlation_trend(name)
            }
            for name, data in self.last_calculation.items()
        }
    
    def print_status(self):
        """Print formatted correlation status."""
        print("\n" + "=" * 60)
        print("📊 CORRELATION STATUS")
        print("=" * 60)
        
        for name, data in self.last_calculation.items():
            health_emoji = {
                'HEALTHY': '✅',
                'DRIFTING': '⚠️',
                'BROKEN': '❌'
            }.get(data['health'], '❓')
            
            print(f"{health_emoji} {name}: {data['current_corr']:.3f} (exp: {data['expected_corr']:.2f}) | {data['health']}")
        
        print("=" * 60)


# Test the engine
if __name__ == "__main__":
    engine = CorrelationEngine()
    
    # Simulate some price data
    import random
    random.seed(42)
    
    # Generate correlated data
    base = [1.0 + i * 0.001 + random.uniform(-0.0005, 0.0005) for i in range(50)]
    correlated = [b + random.uniform(-0.0002, 0.0002) for b in base]  # Highly correlated
    anticorrelated = [2.0 - b + random.uniform(-0.0003, 0.0003) for b in base]  # Negatively correlated
    
    test_buffers = {
        'eurusd': base,
        'gbpusd': correlated,
        'usdchf': anticorrelated
    }
    
    results = engine.calculate_all(test_buffers)
    for r in results:
        print(f"\n{r['name']}:")
        print(f"  Correlation: {r['current_corr']:.4f}")
        print(f"  Expected: {r['expected_corr']}")
        print(f"  Health: {r['health']}")
    
    engine.print_status()

