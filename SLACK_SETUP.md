# Slack Integration Setup for Rex Trading Bot

Rex can send hourly trading summaries and CSV files to your Slack channel.

## Required Environment Variables

Add these to your `.env` file:

```bash
# Slack Bot Token (required for notifications)
SLACK_BOT_TOKEN=xoxb-your-bot-token-here

# Slack Channel (optional, defaults to #rex-trading)
SLACK_CHANNEL=#rex-trading

# OpenAI API Key (required for AI summaries)
OPENAI_API_KEY=sk-your-openai-key-here
```

## How to Get Slack Bot Token

### Step 1: Create a Slack App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. Name it (e.g., "Rex Trading Bot") and select your workspace
4. Click **"Create App"**

### Step 2: Configure Bot Permissions

1. In the left sidebar, go to **"OAuth & Permissions"**
2. Scroll to **"Scopes"** → **"Bot Token Scopes"**
3. Add these scopes:
   - `chat:write` - Send messages
   - `files:write` - Upload CSV files
   - `channels:read` - Read channel info (optional)

### Step 3: Install App to Workspace

1. Scroll to **"OAuth Tokens for Your Workspace"**
2. Click **"Install to Workspace"**
3. Authorize the app
4. Copy the **"Bot User OAuth Token"** (starts with `xoxb-`)

### Step 4: Add Bot to Channel

1. In Slack, go to your channel (e.g., `#rex-trading`)
2. Type `/invite @Rex Trading Bot` (or your app name)
3. The bot will join the channel

### Step 5: Add Token to .env

```bash
SLACK_BOT_TOKEN=your_slack_bot_token_here
SLACK_CHANNEL=#rex-trading
```

## What Gets Sent

### Hourly Summary Message

Every hour, Rex sends:
- **Performance Metrics**: Total trades, win rate, total PnL
- **Profitability Stats**: Average win/loss, largest win/loss, profit factor
- **AI Analysis**: GPT-4 generated insights and recommendations

### CSV File Upload

The complete `rex_trades.csv` file is uploaded to Slack for:
- Detailed trade analysis
- Spreadsheet import
- Historical tracking

## Example Summary

```
🟢 REX TRADING BOT - Hourly Summary
Time: 2025-01-22 14:00:00 UTC

📊 Performance Metrics:
• Total Trades: 17
• Win Rate: 41.2% (7W / 10L)
• Total PnL: $+2.50

💰 Profitability:
• Average Win: $2.45
• Average Loss: $-2.00
• Largest Win: $2.57
• Largest Loss: $-2.38
• Profit Factor: 0.86 ⚠️ Marginal

🤖 AI Analysis:
[GPT-4 generated insights about trading performance, 
strengths, weaknesses, and recommendations]
```

## Testing

Test the Slack integration:

```python
# In Python shell
import slack_notifier

# Send test message
slack_notifier.send_slack_message("🧪 Test message from Rex")

# Send full summary
slack_notifier.send_hourly_summary()
```

## Troubleshooting

### "Slack not configured"
- Check `SLACK_BOT_TOKEN` is set in `.env`
- Restart the bot after adding env vars

### "Slack API error: invalid_auth"
- Token is incorrect or expired
- Regenerate token in Slack app settings

### "Slack API error: channel_not_found"
- Bot not invited to channel
- Channel name incorrect (must start with `#`)
- Use channel ID instead: `C1234567890`

### "AI summary failed"
- Check `OPENAI_API_KEY` is set
- Verify OpenAI API has credits

## Disable Slack (Optional)

If you don't want Slack notifications:
- Simply don't set `SLACK_BOT_TOKEN`
- Bot will continue trading, just won't send summaries
- Console output still works normally

