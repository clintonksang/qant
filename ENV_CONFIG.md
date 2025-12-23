# Environment Variables Configuration

## Required for Rex Trading Bot

### Trading Configuration
```bash
# Tiingo API Key (for price data)
TIINGO_KEY=your_tiingo_api_key_here

# MT5 API Base URL
MT5_API_BASE_URL=https://api.ruthwestlimited.com

# Live Trading Mode (true/false)
REX_LIVE_TRADING=true

# MT5 Trading Volume
MT5_VOLUME=0.01
```

### Slack Integration (Optional but Recommended)
```bash
# Slack Bot Token (starts with xoxb-)
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token-here

# Slack Channel (defaults to #rex-trading if not set)
SLACK_CHANNEL=#rex-trading
```

### AI Summary Generation (Optional)
```bash
# OpenAI API Key (for AI-generated trading summaries)
OPENAI_API_KEY=sk-your-openai-api-key-here
```

## Complete .env Example

```bash
# ============================================
# REX TRADING BOT CONFIGURATION
# ============================================

# Price Data
TIINGO_KEY=your_tiingo_key_here

# MT5 Trading
MT5_API_BASE_URL=https://api.ruthwestlimited.com
REX_LIVE_TRADING=true
MT5_VOLUME=0.01

# Slack Notifications (Hourly Summaries)
SLACK_BOT_TOKEN=your_slack_bot_token_here
SLACK_CHANNEL=#rex-trading

# AI Analysis (for Slack summaries)
OPENAI_API_KEY=sk-proj-your-openai-key-here
```

## What Each Variable Does

| Variable           | Required   | Purpose                                    |
| ------------------ | ---------- | ------------------------------------------ |
| `TIINGO_KEY`       | ✅ Yes      | Real-time gold price data via WebSocket    |
| `MT5_API_BASE_URL` | ✅ Yes      | MT5 API endpoint for trade execution       |
| `REX_LIVE_TRADING` | ⚠️ Optional | Enable live trading (default: false)       |
| `MT5_VOLUME`       | ⚠️ Optional | Trade size in lots (default: 0.01)         |
| `SLACK_BOT_TOKEN`  | ⚠️ Optional | Slack bot token for notifications          |
| `SLACK_CHANNEL`    | ⚠️ Optional | Slack channel name (default: #rex-trading) |
| `OPENAI_API_KEY`   | ⚠️ Optional | AI summaries in Slack (default: disabled)  |

## Setup Instructions

1. **Copy `.env.example` to `.env`** (if exists)
2. **Add your API keys** to `.env`
3. **For Slack**: Follow `SLACK_SETUP.md` to create bot and get token
4. **Restart the bot** after adding env vars

## Docker Usage

All env vars are automatically loaded from `.env` when using `docker-compose`:

```bash
# Start Rex bot
docker-compose up -d rex-bot

# View logs
docker-compose logs -f rex-bot
```

## Testing Configuration

Test your configuration:

```python
# Test Slack
import slack_notifier
slack_notifier.send_slack_message("🧪 Test message")

# Test CSV reading
import slack_notifier
trades = slack_notifier.read_trades_csv()
print(f"Found {len(trades)} trades")
```

## Security Notes

⚠️ **Never commit `.env` to git!**

- `.env` is in `.gitignore`
- Use `.env.example` for documentation
- Rotate API keys if exposed
- Use different keys for dev/prod

