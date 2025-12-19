# MetaTrader 5 Trading API Documentation

**Base URL:** `https://api.ruthwestlimited.com`

All endpoints return JSON responses and require `Content-Type: application/json` header for POST requests.

---

## Table of Contents

1. [Opening a Trade](#opening-a-trade)
2. [Closing a Trade](#closing-a-trade)
3. [Viewing Positions](#viewing-positions)
4. [Modifying Positions](#modifying-positions)
5. [Symbol Information](#symbol-information)
6. [Error Handling](#error-handling)

---

## Opening a Trade

### POST `/order`

Execute a market order to open a new trading position.

**Request Body:**
```json
{
  "symbol": "string (required)",
  "volume": "number (required)",
  "type": "string (required) - 'BUY' or 'SELL'",
  "deviation": "integer (optional, default: 20)",
  "magic": "integer (optional, default: 0)",
  "comment": "string (optional)",
  "sl": "number (optional) - Stop Loss price",
  "tp": "number (optional) - Take Profit price",
  "type_filling": "string (optional) - 'ORDER_FILLING_IOC', 'ORDER_FILLING_FOK', 'ORDER_FILLING_RETURN'"
}
```

**Example: Open a SELL Position**
```bash
curl -X POST "https://api.ruthwestlimited.com/order" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "GBPUSDm",
    "volume": 0.01,
    "type": "SELL",
    "comment": "Manual short trade"
  }'
```

**Example: Open a SELL Position with Stop Loss and Take Profit**
```bash
curl -X POST "https://api.ruthwestlimited.com/order" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "GBPUSDm",
    "volume": 0.01,
    "type": "SELL",
    "sl": 1.3420,
    "tp": 1.3350,
    "comment": "Short trade with SL/TP"
  }'
```

**Example: Open a BUY Position with Stop Loss and Take Profit**
```bash
curl -X POST "https://api.ruthwestlimited.com/order" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURGBPm",
    "volume": 0.01,
    "type": "BUY",
    "sl": 0.8500,
    "tp": 0.8600,
    "comment": "Long trade with SL/TP"
  }'
```

**Important Notes for SL/TP:**
- **For SELL positions**: SL should be **above** entry price (price goes up = loss), TP should be **below** entry price (price goes down = profit)
- **For BUY positions**: SL should be **below** entry price (price goes down = loss), TP should be **above** entry price (price goes up = profit)
- Always check current market price using `/symbol_info_tick/<symbol>` before setting SL/TP levels
- Adjust SL/TP prices based on your risk tolerance and market conditions

**Success Response (200):**
```json
{
  "message": "Order executed successfully",
  "result": {
    "ask": 1.33874,
    "bid": 1.33864,
    "comment": "Manual short tra",
    "deal": 1642934395,
    "order": 2091763752,
    "price": 1.33864,
    "request": [1, 0, 0, "GBPUSDm", 0.01, 1.33864, 0.0, 0.0, 0.0, 20, 1, 1, 0, 0, "Manual short trade", 0, 0],
    "request_id": 3397159819,
    "retcode": 10009,
    "retcode_external": 0,
    "volume": 0.01
  }
}
```

**Example: Open a BUY Position with Stop Loss and Take Profit**
```bash
curl -X POST "https://api.ruthwestlimited.com/order" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURGBPm",
    "volume": 0.01,
    "type": "BUY",
    "sl": 0.8500,
    "tp": 0.8600,
    "comment": "Long trade with protection"
  }'
```

**Error Responses:**

**400 - AutoTrading Disabled:**
```json
{
  "error": "Order failed: AutoTrading disabled by client",
  "mt5_error": "Success",
  "result": {
    "ask": 0.0,
    "bid": 0.0,
    "comment": "AutoTrading disabled by client",
    "deal": 0,
    "order": 0,
    "price": 0.0,
    "request": [1, 0, 0, "GBPUSDm", 0.01, 1.33865, 0.0, 0.0, 0.0, 20, 1, 1, 0, 0, "Manual short trade", 0, 0],
    "request_id": 0,
    "retcode": 10027,
    "retcode_external": 0,
    "volume": 0.0
  }
}
```

**400 - Failed to Get Symbol Price:**
```json
{
  "error": "Failed to get symbol price"
}
```

**400 - Missing Required Fields:**
```json
{
  "error": "Missing required fields"
}
```

**Response Fields:**
- `order`: The order ticket number (use this to track/close the position)
- `deal`: The deal ticket number
- `price`: Execution price
- `retcode`: Return code (10009 = success)
- `volume`: Executed volume

---

## Closing a Trade

### POST `/close_position`

Close a specific open position.

**Request Body:**
```json
{
  "position": {
    "type": "integer (required) - 0 for BUY, 1 for SELL",
    "ticket": "integer (required) - Position ticket number",
    "symbol": "string (required) - Symbol name",
    "volume": "number (required) - Position volume"
  }
}
```

**Example: Close a SELL Position**
```bash
curl -X POST "https://api.ruthwestlimited.com/close_position" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "position": {
      "type": 1,
      "ticket": 2091763752,
      "symbol": "GBPUSDm",
      "volume": 0.01
    }
  }'
```

**Success Response (200):**
```json
{
  "message": "Position closed successfully",
  "result": {
    "ask": 1.33893,
    "bid": 1.33883,
    "comment": "",
    "deal": 1642961017,
    "order": 2091795057,
    "price": 1.33893,
    "request": [1, 0, 0, "GBPUSDm", 0.01, 1.33893, 0.0, 0.0, 0.0, 20, 0, 1, 0, 0, "", 2091763752, 0],
    "request_id": 3388975922,
    "retcode": 10009,
    "retcode_external": 0,
    "volume": 0.01
  }
}
```

**Error Response (400):**
```json
{
  "error": "Failed to close position"
}
```

---

### POST `/close_all_positions`

Close all open positions, optionally filtered by order type or magic number.

**Request Body (Optional):**
```json
{
  "order_type": "string (optional) - 'BUY', 'SELL', or 'all' (default: 'all')",
  "magic": "integer (optional) - Filter by magic number"
}
```

**Example: Close All Positions**
```bash
curl -X POST "https://api.ruthwestlimited.com/close_all_positions" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Example: Close Only SELL Positions**
```bash
curl -X POST "https://api.ruthwestlimited.com/close_all_positions" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "order_type": "SELL"
  }'
```

**Success Response (200):**
```json
{
  "message": "Closed 2 positions",
  "results": [
    {
      "retcode": 10009,
      "order": 2091795057,
      "price": 1.33893,
      "symbol": "GBPUSDm",
      "volume": 0.01
    }
  ]
}
```

---

## Viewing Positions

### GET `/get_positions`

Retrieve all open trading positions.

**Query Parameters:**
- `magic` (optional, integer): Filter positions by magic number

**Example: Get All Positions**
```bash
curl -X GET "https://api.ruthwestlimited.com/get_positions" \
  -H "accept: application/json"
```

**Success Response (200):**
```json
[
  {
    "comment": "Manual short tra",
    "external_id": "",
    "identifier": 2091763752,
    "magic": 0,
    "price_current": 1.33861,
    "price_open": 1.33864,
    "profit": 0.03,
    "reason": 3,
    "sl": 0.0,
    "swap": 0.0,
    "symbol": "GBPUSDm",
    "ticket": 2091763752,
    "time": 1766172862,
    "time_msc": 1766172862816,
    "time_update": 1766172862,
    "time_update_msc": 1766172862816,
    "tp": 0.0,
    "type": 1,
    "volume": 0.01
  }
]
```

**Example: Get Positions with Profit/Loss**
```bash
curl -X GET "https://api.ruthwestlimited.com/get_positions" \
  -H "accept: application/json"
```

**Response with Loss:**
```json
[
  {
    "comment": "Manual short tra",
    "external_id": "",
    "identifier": 2091763752,
    "magic": 0,
    "price_current": 1.3389,
    "price_open": 1.33864,
    "profit": -0.26,
    "reason": 3,
    "sl": 0.0,
    "swap": 0.0,
    "symbol": "GBPUSDm",
    "ticket": 2091763752,
    "time": 1766172862,
    "time_msc": 1766172862816,
    "time_update": 1766172862,
    "time_update_msc": 1766172862816,
    "tp": 0.0,
    "type": 1,
    "volume": 0.01
  }
]
```

**Empty Response (No Open Positions):**
```json
[]
```

**Response Fields:**
- `ticket`: Position ticket number (use this to close the position)
- `symbol`: Trading symbol
- `type`: Position type (0 = BUY, 1 = SELL)
- `volume`: Position size
- `price_open`: Entry price
- `price_current`: Current market price
- `profit`: Current profit/loss in account currency
- `sl`: Stop Loss price (0.0 if not set)
- `tp`: Take Profit price (0.0 if not set)
- `time`: Position open time (Unix timestamp)
- `comment`: Position comment

---

### GET `/positions_total`

Get the total number of open positions.

**Example:**
```bash
curl -X GET "https://api.ruthwestlimited.com/positions_total" \
  -H "accept: application/json"
```

**Success Response (200):**
```json
{
  "total": 1
}
```

---

## Modifying Positions

### POST `/modify_sl_tp`

Modify the Stop Loss (SL) and/or Take Profit (TP) levels for an existing position.

**Request Body:**
```json
{
  "position": "integer (required) - Position ticket number",
  "sl": "number (optional) - New Stop Loss price",
  "tp": "number (optional) - New Take Profit price"
}
```

**Example: Add Stop Loss and Take Profit**
```bash
curl -X POST "https://api.ruthwestlimited.com/modify_sl_tp" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "position": 2091763752,
    "sl": 1.3420,
    "tp": 1.3350
  }'
```

**Example: Modify Only Stop Loss**
```bash
curl -X POST "https://api.ruthwestlimited.com/modify_sl_tp" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "position": 2091763752,
    "sl": 1.3420
  }'
```

**Success Response (200):**
```json
{
  "message": "SL/TP modified successfully",
  "result": {
    "retcode": 10009,
    "order": 2091795057,
    "price": 1.33893,
    "symbol": "GBPUSDm"
  }
}
```

**Error Response (400):**
```json
{
  "error": "Failed to modify SL/TP: [error message]"
}
```

---

## Symbol Information

### GET `/symbol_info_tick/<symbol>`

Get the latest tick (price) information for a symbol.

**Example:**
```bash
curl -X GET "https://api.ruthwestlimited.com/symbol_info_tick/GBPUSDm" \
  -H "accept: application/json"
```

**Success Response (200):**
```json
{
  "ask": 1.33884,
  "bid": 1.33874,
  "flags": 6,
  "last": 0,
  "time": 1766172080,
  "time_msc": 1766172080080,
  "volume": 0,
  "volume_real": 0
}
```

**Response Fields:**
- `ask`: Ask price (price to buy)
- `bid`: Bid price (price to sell)
- `time`: Tick time (Unix timestamp)
- `time_msc`: Tick time in milliseconds

---

### GET `/symbol_info/<symbol>`

Get detailed information about a trading symbol.

**Example:**
```bash
curl -X GET "https://api.ruthwestlimited.com/symbol_info/GBPUSDm" \
  -H "accept: application/json"
```

**Success Response (200):**
```json
{
  "name": "GBPUSDm",
  "description": "British Pound vs US Dollar",
  "volume_min": 0.01,
  "volume_max": 100.0,
  "volume_step": 0.01,
  "price_digits": 5,
  "spread": 10,
  "points": 1,
  "trade_mode": 4
}
```

---

## Error Handling

### Common Error Codes

| HTTP Status | Error Message                                    | Description                              |
| ----------- | ------------------------------------------------ | ---------------------------------------- |
| 400         | `"Failed to get symbol price"`                   | Symbol not found or MT5 connection issue |
| 400         | `"Order failed: AutoTrading disabled by client"` | Enable AutoTrading in MT5 terminal       |
| 400         | `"Missing required fields"`                      | Required parameters missing in request   |
| 400         | `"Invalid order type. Use 'BUY' or 'SELL'"`      | Invalid order type specified             |
| 400         | `"Failed to close position"`                     | Position not found or already closed     |
| 500         | `"Internal server error"`                        | Server-side error occurred               |

### MT5 Return Codes

| Code  | Description                    |
| ----- | ------------------------------ |
| 10009 | Request executed successfully  |
| 10027 | AutoTrading disabled by client |

### Best Practices

1. **Always check position status** before closing:
   ```bash
   # First, get positions
   curl -X GET "https://api.ruthwestlimited.com/get_positions"
   
   # Then close using the ticket from the response
   ```

2. **Set Stop Loss and Take Profit** when opening trades:
   ```json
   {
     "symbol": "GBPUSDm",
     "volume": 0.01,
     "type": "SELL",
     "sl": 1.3420,
     "tp": 1.3350
   }
   ```

3. **Monitor positions regularly**:
   ```bash
   # Check profit/loss
   curl -X GET "https://api.ruthwestlimited.com/get_positions"
   ```

4. **Handle errors gracefully**:
   - Check `retcode` in responses
   - Verify `AutoTrading` is enabled in MT5
   - Ensure symbol names include the "m" suffix (e.g., `GBPUSDm`, `EURGBPm`)

---

## Complete Trading Workflow Example

### 1. Check Current Price
```bash
curl -X GET "https://api.ruthwestlimited.com/symbol_info_tick/GBPUSDm"
```

### 2. Open a Trade
```bash
curl -X POST "https://api.ruthwestlimited.com/order" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "GBPUSDm",
    "volume": 0.01,
    "type": "SELL",
    "sl": 1.3420,
    "tp": 1.3350,
    "comment": "Short GBPUSD"
  }'
```

### 3. Monitor Position
```bash
curl -X GET "https://api.ruthwestlimited.com/get_positions"
```

### 4. Modify SL/TP if Needed
```bash
curl -X POST "https://api.ruthwestlimited.com/modify_sl_tp" \
  -H "Content-Type: application/json" \
  -d '{
    "position": 2091763752,
    "sl": 1.3410,
    "tp": 1.3340
  }'
```

### 5. Close Position
```bash
curl -X POST "https://api.ruthwestlimited.com/close_position" \
  -H "Content-Type: application/json" \
  -d '{
    "position": {
      "type": 1,
      "ticket": 2091763752,
      "symbol": "GBPUSDm",
      "volume": 0.01
    }
  }'
```

---

## Notes

- **Symbol Naming**: Most brokers use symbols with an "m" suffix (e.g., `GBPUSDm`, `EURGBPm`, `EURUSDm`)
- **Position Types**: `type: 0` = BUY position, `type: 1` = SELL position
- **Volume**: Minimum volume is typically 0.01 (micro lot)
- **AutoTrading**: Must be enabled in MetaTrader 5 terminal for orders to execute
- **Price Precision**: Prices use 5 decimal places for most forex pairs
- **Time Format**: All timestamps are Unix timestamps (seconds since epoch)

---

## Support

For issues or questions, check:
- MT5 terminal logs
- API response error messages
- Ensure AutoTrading is enabled in MT5
- Verify symbol names are correct (include "m" suffix if required)



 