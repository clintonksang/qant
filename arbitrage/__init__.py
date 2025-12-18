"""
Currency Pair Arbitrage System

Monitors correlated FX pairs for divergence opportunities.
Uses statistical arbitrage (pairs trading) to profit from mean reversion.

Modules:
- config: Trading parameters and pair definitions
- correlation_engine: Calculates rolling correlations
- signal_detector: Detects divergence signals via Z-score
- pair_memory: Pinecone storage for learning
- arbitrage_brain: AI decision making
- position_manager: Hedged position management
- main: WebSocket listener and main loop
"""

from .config import (
    POSITIVE_PAIRS,
    NEGATIVE_PAIRS,
    ALL_TICKERS,
    get_session
)

from .correlation_engine import CorrelationEngine
from .signal_detector import SignalDetector
from .position_manager import PositionManager

__version__ = "1.0.0"
__author__ = "QuantAgent"

__all__ = [
    'POSITIVE_PAIRS',
    'NEGATIVE_PAIRS', 
    'ALL_TICKERS',
    'get_session',
    'CorrelationEngine',
    'SignalDetector',
    'PositionManager'
]

