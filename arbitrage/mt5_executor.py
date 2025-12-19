"""
MT5 Executor - MetaTrader 5 Trade Execution for Arbitrage
Handles real trade execution via the MT5 API
"""

import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")

# MT5 API Configuration
MT5_API_URL = os.getenv("MT5_API_URL", "https://api.ruthwestlimited.com")
MT5_TIMEOUT = 10  # seconds


class MT5Executor:
    """
    Executes real trades via MetaTrader 5 REST API.
    Handles both legs of arbitrage trades atomically.
    """
    
    # Symbol mapping: internal name -> MT5 symbol
    SYMBOL_MAP = {
        "eurusd": "EURUSDm",
        "gbpusd": "GBPUSDm",
        "audusd": "AUDUSDm",
        "nzdusd": "NZDUSDm",
        "usdchf": "USDCHFm",
        "usdcad": "USDCADm",
        "eurjpy": "EURJPYm",
        "gbpjpy": "GBPJPYm",
        "eurgbp": "EURGBPm",
        "audcad": "AUDCADm",
        "nzdcad": "NZDCADm",
    }
    
    def __init__(self, volume=0.01, magic=123456):
        """
        Initialize MT5 Executor.
        
        Args:
            volume: Trade volume in lots (0.01 = micro lot)
            magic: Magic number to identify bot trades
        """
        self.volume = volume
        self.magic = magic
        self.api_url = MT5_API_URL
        
        print(f"🔌 MT5 Executor initialized")
        print(f"   API: {self.api_url}")
        print(f"   Volume: {self.volume} lots")
        print(f"   Magic: {self.magic}")
    
    def _get_mt5_symbol(self, pair):
        """
        Convert internal symbol to MT5 format.
        
        Args:
            pair: Internal pair name (e.g., 'eurusd')
            
        Returns:
            MT5 symbol (e.g., 'EURUSDm')
        """
        return self.SYMBOL_MAP.get(pair.lower(), pair.upper() + "m")
    
    def _make_request(self, method, endpoint, data=None, timeout=None):
        """
        Make HTTP request to MT5 API.
        
        Args:
            method: 'GET' or 'POST'
            endpoint: API endpoint (e.g., '/order')
            data: Request body for POST
            timeout: Request timeout
            
        Returns:
            Response JSON or error dict
        """
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
            return {"error": "Connection failed - is MT5 API running?", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}
    
    def execute_arbitrage_entry(self, signal):
        """
        Execute BOTH legs of an arbitrage trade.
        Ensures atomic execution - if one leg fails, closes the other.
        
        Args:
            signal: Divergence signal from SignalDetector
            
        Returns:
            Dict with success status, tickets, and execution prices
        """
        pair_a = signal['pair_a']
        pair_b = signal['pair_b']
        action_a = signal['action_a']  # "BUY" or "SELL"
        action_b = signal['action_b']
        pair_name = signal['pair_name']
        
        print(f"\n🚀 EXECUTING ARBITRAGE TRADE: {pair_name}")
        print(f"   Leg A: {action_a} {pair_a.upper()}")
        print(f"   Leg B: {action_b} {pair_b.upper()}")
        
        # Execute Leg A
        result_a = self._place_order(
            symbol=self._get_mt5_symbol(pair_a),
            order_type=action_a,
            comment=f"ARB_{pair_name}_A"
        )
        
        # Check if Leg A succeeded
        success_a = result_a.get('result', {}).get('retcode') == 10009
        
        if not success_a:
            error_msg = result_a.get('error', result_a.get('result', {}).get('comment', 'Unknown error'))
            print(f"   ❌ Leg A FAILED: {error_msg}")
            return {
                'success': False,
                'error': f"Leg A failed: {error_msg}",
                'result_a': result_a,
                'result_b': None
            }
        
        ticket_a = result_a['result']['order']
        price_a = result_a['result']['price']
        print(f"   ✅ Leg A: Ticket #{ticket_a} @ {price_a}")
        
        # Execute Leg B
        result_b = self._place_order(
            symbol=self._get_mt5_symbol(pair_b),
            order_type=action_b,
            comment=f"ARB_{pair_name}_B"
        )
        
        # Check if Leg B succeeded
        success_b = result_b.get('result', {}).get('retcode') == 10009
        
        if not success_b:
            error_msg = result_b.get('error', result_b.get('result', {}).get('comment', 'Unknown error'))
            print(f"   ❌ Leg B FAILED: {error_msg}")
            print(f"   ⚠️ Emergency closing Leg A...")
            
            # Emergency close Leg A
            self._emergency_close(ticket_a, pair_a, action_a)
            
            return {
                'success': False,
                'error': f"Leg B failed: {error_msg}",
                'result_a': result_a,
                'result_b': result_b
            }
        
        ticket_b = result_b['result']['order']
        price_b = result_b['result']['price']
        print(f"   ✅ Leg B: Ticket #{ticket_b} @ {price_b}")
        
        print(f"\n   ✅ ARBITRAGE TRADE EXECUTED SUCCESSFULLY")
        
        return {
            'success': True,
            'ticket_a': ticket_a,
            'ticket_b': ticket_b,
            'price_a': price_a,
            'price_b': price_b,
            'result_a': result_a,
            'result_b': result_b
        }
    
    def _place_order(self, symbol, order_type, comment=""):
        """
        Place a single market order.
        
        Args:
            symbol: MT5 symbol (e.g., 'EURUSDm')
            order_type: 'BUY' or 'SELL'
            comment: Order comment (max 15 chars in MT5)
            
        Returns:
            API response dict
        """
        payload = {
            "symbol": symbol,
            "volume": self.volume,
            "type": order_type,
            "magic": self.magic,
            "comment": comment[:15]  # MT5 truncates comments
        }
        
        return self._make_request('POST', '/order', payload)
    
    def close_arbitrage_position(self, position):
        """
        Close BOTH legs of an arbitrage position.
        
        Args:
            position: Position dict with ticket_a, ticket_b, pair_a, pair_b, action_a, action_b
            
        Returns:
            Dict with close results for both legs
        """
        pair_name = position.get('pair_name', 'UNKNOWN')
        print(f"\n🔒 CLOSING ARBITRAGE POSITION: {pair_name}")
        
        # Determine position types (0=BUY, 1=SELL)
        type_a = 0 if position['action_a'] == 'BUY' else 1
        type_b = 0 if position['action_b'] == 'BUY' else 1
        
        # Close Leg A
        result_a = self._close_position(
            ticket=position['ticket_a'],
            symbol=self._get_mt5_symbol(position['pair_a']),
            volume=self.volume,
            position_type=type_a
        )
        
        success_a = result_a.get('result', {}).get('retcode') == 10009 or 'message' in result_a
        if success_a:
            print(f"   ✅ Leg A closed: Ticket #{position['ticket_a']}")
        else:
            print(f"   ❌ Leg A close failed: {result_a}")
        
        # Close Leg B
        result_b = self._close_position(
            ticket=position['ticket_b'],
            symbol=self._get_mt5_symbol(position['pair_b']),
            volume=self.volume,
            position_type=type_b
        )
        
        success_b = result_b.get('result', {}).get('retcode') == 10009 or 'message' in result_b
        if success_b:
            print(f"   ✅ Leg B closed: Ticket #{position['ticket_b']}")
        else:
            print(f"   ❌ Leg B close failed: {result_b}")
        
        return {
            'success': success_a and success_b,
            'result_a': result_a,
            'result_b': result_b
        }
    
    def _close_position(self, ticket, symbol, volume, position_type):
        """
        Close a single position.
        
        Args:
            ticket: Position ticket number
            symbol: MT5 symbol
            volume: Position volume
            position_type: 0 for BUY, 1 for SELL
            
        Returns:
            API response dict
        """
        payload = {
            "position": {
                "type": position_type,
                "ticket": ticket,
                "symbol": symbol,
                "volume": volume
            }
        }
        
        return self._make_request('POST', '/close_position', payload)
    
    def _emergency_close(self, ticket, pair, action):
        """
        Emergency close a single leg if the other leg failed.
        
        Args:
            ticket: Ticket to close
            pair: Currency pair
            action: 'BUY' or 'SELL'
        """
        symbol = self._get_mt5_symbol(pair)
        position_type = 0 if action == 'BUY' else 1
        
        result = self._close_position(ticket, symbol, self.volume, position_type)
        
        if result.get('result', {}).get('retcode') == 10009:
            print(f"   ✅ Emergency close successful: Ticket #{ticket}")
        else:
            print(f"   ❌ Emergency close FAILED: {result}")
            print(f"   ⚠️ MANUAL INTERVENTION REQUIRED: Close ticket #{ticket}")
        
        return result
    
    def get_current_price(self, pair):
        """
        Get current bid/ask for a currency pair.
        
        Args:
            pair: Internal pair name (e.g., 'eurusd')
            
        Returns:
            Dict with bid, ask, or error
        """
        symbol = self._get_mt5_symbol(pair)
        return self._make_request('GET', f'/symbol_info_tick/{symbol}')
    
    def get_open_positions(self):
        """
        Get all open positions from MT5.
        Optionally filtered by magic number.
        
        Returns:
            List of position dicts
        """
        result = self._make_request('GET', '/get_positions', {'magic': self.magic})
        
        if isinstance(result, list):
            return result
        elif 'error' in result:
            print(f"⚠️ Failed to get positions: {result['error']}")
            return []
        return []
    
    def get_positions_total(self):
        """Get total number of open positions."""
        result = self._make_request('GET', '/positions_total')
        return result.get('total', 0)
    
    def close_all_positions(self, order_type='all'):
        """
        Close all open positions.
        
        Args:
            order_type: 'BUY', 'SELL', or 'all'
            
        Returns:
            API response
        """
        payload = {"order_type": order_type}
        if self.magic:
            payload["magic"] = self.magic
        
        return self._make_request('POST', '/close_all_positions', payload)
    
    def test_connection(self):
        """
        Test connection to MT5 API.
        
        Returns:
            True if connected, False otherwise
        """
        try:
            result = self._make_request('GET', '/symbol_info_tick/EURUSDm', timeout=5)
            
            if 'error' in result:
                print(f"❌ MT5 API Error: {result['error']}")
                return False
            
            if 'bid' in result and 'ask' in result:
                print(f"✅ MT5 API Connected")
                print(f"   EUR/USD: Bid {result['bid']:.5f} | Ask {result['ask']:.5f}")
                return True
            
            print(f"❌ Unexpected response: {result}")
            return False
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False


# Test the executor
if __name__ == "__main__":
    print("Testing MT5 Executor...")
    print("=" * 60)
    
    executor = MT5Executor(volume=0.01)
    
    # Test connection
    print("\n1. Testing connection...")
    if executor.test_connection():
        print("   Connection OK!")
    else:
        print("   Connection FAILED!")
        exit(1)
    
    # Get current positions
    print("\n2. Getting open positions...")
    positions = executor.get_open_positions()
    print(f"   Found {len(positions)} open positions")
    
    for pos in positions:
        print(f"   - Ticket #{pos['ticket']}: {pos['symbol']} {'BUY' if pos['type']==0 else 'SELL'} | PnL: {pos['profit']:.2f}")
    
    # Test price fetch
    print("\n3. Getting EUR/USD price...")
    price = executor.get_current_price('eurusd')
    if 'bid' in price:
        print(f"   Bid: {price['bid']:.5f} | Ask: {price['ask']:.5f}")
    else:
        print(f"   Error: {price}")
    
    print("\n" + "=" * 60)
    print("Test complete!")

