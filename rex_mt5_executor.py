"""
Rex MT5 Executor - Gold (XAU/USD) Trading
Based on arbitrage/mt5_executor.py with dynamic SL management
"""

import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent / ".env")

# MT5 API Configuration
MT5_API_URL = os.getenv("MT5_API_URL", "https://api.ruthwestlimited.com")
MT5_TIMEOUT = 10


class RexMT5Executor:
    """Execute XAU/USD trades via MT5 API with dynamic SL management."""
    
    SYMBOL = "XAUUSDm"  # Gold symbol on MT5
    
    def __init__(self, volume=0.01, magic=789012):
        self.volume = volume
        self.magic = magic
        self.api_url = MT5_API_URL
        self.active_ticket = None
        self.active_side = None
        
        print(f"🥇 Rex MT5 Executor initialized")
        print(f"   API: {self.api_url}")
        print(f"   Volume: {self.volume} lots | Magic: {self.magic}")
    
    def _make_request(self, method, endpoint, data=None, timeout=None):
        """Make HTTP request to MT5 API."""
        url = f"{self.api_url}{endpoint}"
        timeout = timeout or MT5_TIMEOUT
        
        try:
            if method == 'GET':
                response = requests.get(url, params=data, timeout=timeout)
            else:
                response = requests.post(url, json=data, timeout=timeout)
            return response.json()
        except requests.exceptions.Timeout:
            return {"error": "Request timeout", "success": False}
        except requests.exceptions.ConnectionError:
            return {"error": "Connection failed", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}
    
    # =========================================================================
    # TRADE EXECUTION
    # =========================================================================
    
    def open_trade(self, side, sl, tp, comment="REX"):
        """
        Open a XAU/USD trade with SL and TP.
        
        Args:
            side: "BUY" or "SELL"
            sl: Stop loss price
            tp: Take profit price
            
        Returns:
            Dict with success, ticket, entry_price
        """
        payload = {
            "symbol": self.SYMBOL,
            "volume": self.volume,
            "type": side,
            "sl": sl,
            "tp": tp,
            "magic": self.magic,
            "deviation": 30,  # Higher for gold volatility
            "comment": comment[:15]
        }
        
        print(f"\n🚀 MT5: Opening {side} XAU/USD")
        print(f"   SL: {sl:.2f} | TP: {tp:.2f}")
        
        result = self._make_request('POST', '/order', payload)
        
        # Check success (retcode 10009 = trade executed)
        success = result.get('result', {}).get('retcode') == 10009
        
        if success:
            ticket = result['result']['order']
            price = result['result']['price']
            self.active_ticket = ticket
            self.active_side = side
            print(f"   ✅ OPENED: Ticket #{ticket} @ {price:.2f}")
            return {'success': True, 'ticket': ticket, 'entry_price': price}
        else:
            error = result.get('error', result.get('result', {}).get('comment', 'Unknown'))
            print(f"   ❌ FAILED: {error}")
            return {'success': False, 'error': error}
    
    def close_trade(self, ticket=None, side=None):
        """Close the current position."""
        ticket = ticket or self.active_ticket
        side = side or self.active_side
        
        if not ticket or not side:
            return {'success': False, 'error': 'No position to close'}
        
        position_type = 0 if side == 'BUY' else 1
        
        payload = {
            "position": {
                "type": position_type,
                "ticket": ticket,
                "symbol": self.SYMBOL,
                "volume": self.volume
            }
        }
        
        print(f"\n🔒 MT5: Closing {side} Ticket #{ticket}")
        
        result = self._make_request('POST', '/close_position', payload)
        
        success = result.get('result', {}).get('retcode') == 10009 or 'message' in result
        close_price = result.get('result', {}).get('price', 0)
        
        if success:
            print(f"   ✅ CLOSED @ {close_price:.2f}")
            self.active_ticket = None
            self.active_side = None
            return {'success': True, 'close_price': close_price}
        else:
            error = result.get('error', 'Close failed')
            print(f"   ❌ CLOSE FAILED: {error}")
            return {'success': False, 'error': error}
    
    # =========================================================================
    # DYNAMIC STOP LOSS - RUN WITH WINNERS
    # =========================================================================
    
    def modify_sl_tp(self, ticket, new_sl=None, new_tp=None, current_sl=0, current_tp=0):
        """
        Modify stop loss and/or take profit on MT5.
        Uses endpoint: POST /modify_sl_tp
        
        Args:
            ticket: Position ticket
            new_sl: New stop loss (None to keep current)
            new_tp: New take profit (None to keep current)
            current_sl: Current SL if new_sl is None
            current_tp: Current TP if new_tp is None
        """
        sl = new_sl if new_sl is not None else current_sl
        tp = new_tp if new_tp is not None else current_tp
        
        payload = {
            "position": ticket,
            "sl": sl,
            "tp": tp
        }
        
        result = self._make_request('POST', '/modify_sl_tp', payload)
        
        success = result.get('result', {}).get('retcode') == 10009 or result.get('success', False)
        
        if success:
            print(f"🔧 MT5 SL/TP Modified: SL={sl:.2f}, TP={tp:.2f}")
            return {'success': True, 'sl': sl, 'tp': tp}
        else:
            error = result.get('error', 'Modify failed')
            return {'success': False, 'error': error}
    
    def move_to_breakeven(self, ticket, entry_price, side, buffer=0.30):
        """
        Move SL to breakeven + buffer when in profit.
        
        Args:
            ticket: Position ticket
            entry_price: Original entry price
            side: "BUY" or "SELL"
            buffer: Pips to add for guaranteed profit
        """
        if side == "BUY":
            new_sl = entry_price + buffer
        else:
            new_sl = entry_price - buffer
        
        print(f"🔒 Moving SL to breakeven: {new_sl:.2f} (lock ${buffer:.2f})")
        return self.modify_sl_tp(ticket, new_sl=new_sl)
    
    def trail_stop(self, ticket, current_price, side, distance=1.00):
        """
        Trail stop loss behind current price.
        
        Args:
            ticket: Position ticket
            current_price: Current market price
            side: "BUY" or "SELL"
            distance: Distance to trail behind price
        """
        if side == "BUY":
            new_sl = current_price - distance
        else:
            new_sl = current_price + distance
        
        print(f"📈 Trailing SL to {new_sl:.2f} (${distance:.2f} behind)")
        return self.modify_sl_tp(ticket, new_sl=new_sl)
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    def get_price(self):
        """Get current XAU/USD price."""
        return self._make_request('GET', f'/symbol_info_tick/{self.SYMBOL}')
    
    def get_positions(self):
        """Get open Rex positions."""
        result = self._make_request('GET', '/get_positions', {'magic': self.magic})
        if isinstance(result, list):
            return [p for p in result if self.SYMBOL in p.get('symbol', '')]
        return []
    
    def test_connection(self):
        """Test MT5 API connection."""
        try:
            result = self._make_request('GET', f'/symbol_info_tick/{self.SYMBOL}', timeout=5)
            
            if 'error' in result:
                print(f"❌ MT5 Error: {result['error']}")
                return False
            
            if 'bid' in result and 'ask' in result:
                spread = result['ask'] - result['bid']
                print(f"✅ MT5 Connected - XAU: {result['bid']:.2f}/{result['ask']:.2f} (spread: {spread:.2f})")
                return True
            
            return False
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False


# Singleton instance
_executor = None

def get_executor(volume=0.01):
    """Get or create Rex executor instance."""
    global _executor
    if _executor is None:
        _executor = RexMT5Executor(volume=volume)
    return _executor


if __name__ == "__main__":
    print("=" * 50)
    print("Testing Rex MT5 Executor")
    print("=" * 50)
    
    executor = RexMT5Executor(volume=0.01)
    
    if executor.test_connection():
        print("\n✅ Ready for live trading!")
        
        # Show open positions
        positions = executor.get_positions()
        print(f"\n📊 Open Rex positions: {len(positions)}")
        for p in positions:
            print(f"   #{p['ticket']}: {'BUY' if p['type']==0 else 'SELL'} @ {p['price_open']:.2f} | PnL: {p['profit']:.2f}")
    else:
        print("\n❌ Cannot connect to MT5 API")

