"""
Slack Integration for Rex Trading Bot
Sends hourly summaries and CSV files to Slack channel
"""
import os
import csv
from pathlib import Path
from datetime import datetime

# Try to import slack_sdk (optional dependency)
try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_SDK_AVAILABLE = True
except ImportError:
    SLACK_SDK_AVAILABLE = False
    print("⚠️ slack-sdk not installed. Run: pip install slack-sdk")

# Initialize Slack client
SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#rex-trading")
slack_client = None

if SLACK_SDK_AVAILABLE and SLACK_TOKEN:
    try:
        slack_client = WebClient(token=SLACK_TOKEN)
        # Test connection
        slack_client.auth_test()
        print(f"✅ Slack connected to channel: {SLACK_CHANNEL}")
    except Exception as e:
        print(f"⚠️ Slack connection failed: {e}")
        slack_client = None
elif not SLACK_TOKEN:
    print("⚠️ SLACK_BOT_TOKEN not set - Slack notifications disabled")


def read_trades_csv(csv_path="rex_trades.csv"):
    """Read trades from CSV file.
    
    CSV format: TradeID, Time, Session, Type, Symbol, Entry, SL, TP, Status, ExitPrice, PnL, Reason
    """
    trades = []
    csv_file = Path(__file__).parent / csv_path
    
    if not csv_file.exists():
        return trades
    
    try:
        with open(csv_file, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip empty rows or rows without TradeID
                if row.get('TradeID') and row.get('TradeID').strip():
                    trades.append(row)
    except Exception as e:
        print(f"⚠️ Error reading CSV: {e}")
    
    return trades


def calculate_pnl_summary(trades):
    """Calculate profit/loss summary from trades."""
    if not trades:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "largest_win": 0,
            "largest_loss": 0,
            "profit_factor": 0,
            "session_breakdown": {}
        }
    
    wins = []
    losses = []
    total_pnl = 0
    
    # v10: Session breakdown
    session_stats = {}
    
    for trade in trades:
        try:
            # CSV column is 'PnL' (capital P, capital L)
            pnl_str = trade.get('PnL', trade.get('pnl', '0'))
            if not pnl_str or pnl_str.strip() == '':
                continue
            pnl = float(pnl_str)
            total_pnl += pnl
            
            if pnl > 0:
                wins.append(pnl)
            elif pnl < 0:
                losses.append(abs(pnl))
            
            # v10: Track session stats
            session = trade.get('Session', 'UNKNOWN')
            if session not in session_stats:
                session_stats[session] = {'trades': 0, 'wins': 0, 'pnl': 0}
            session_stats[session]['trades'] += 1
            session_stats[session]['pnl'] += pnl
            if pnl > 0:
                session_stats[session]['wins'] += 1
                
        except (ValueError, TypeError) as e:
            continue
    
    total_trades = len(trades)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
    
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    largest_win = max(wins) if wins else 0
    largest_loss = max(losses) if losses else 0
    
    # Profit factor = Total wins / Total losses
    total_wins = sum(wins) if wins else 0
    total_losses = sum(losses) if losses else 0
    profit_factor = total_wins / total_losses if total_losses > 0 else (float('inf') if total_wins > 0 else 0)
    
    return {
        "total_trades": total_trades,
        "wins": win_count,
        "losses": loss_count,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "profit_factor": profit_factor,
        "total_wins_amount": total_wins,
        "total_losses_amount": total_losses,
        "session_breakdown": session_stats
    }


def generate_ai_summary(summary_data, trades):
    """Use AI to generate a trading summary."""
    try:
        # Build context for AI
        context = f"""
        REX TRADING BOT - Performance Summary
        
        Total Trades: {summary_data['total_trades']}
        Win Rate: {summary_data['win_rate']:.1f}%
        Total PnL: ${summary_data['total_pnl']:.2f}
        
        Wins: {summary_data['wins']} trades, Total: ${summary_data['total_wins_amount']:.2f}
        Losses: {summary_data['losses']} trades, Total: ${summary_data['total_losses_amount']:.2f}
        
        Average Win: ${summary_data['avg_win']:.2f}
        Average Loss: ${summary_data['avg_loss']:.2f}
        Largest Win: ${summary_data['largest_win']:.2f}
        Largest Loss: ${summary_data['largest_loss']:.2f}
        Profit Factor: {summary_data['profit_factor']:.2f}
        
        Recent Trades (last 5):
        """
        
        # Add last 5 trades (CSV columns: Type, Entry, ExitPrice, PnL, Reason)
        for trade in trades[-5:]:
            side = trade.get('Type', 'N/A')
            entry = trade.get('Entry', 'N/A')
            exit_price = trade.get('ExitPrice', 'N/A')
            pnl = trade.get('PnL', '0')
            reason = trade.get('Reason', 'N/A')
            context += f"\n- {side} @ {entry} | Exit: {exit_price} | PnL: ${pnl} | Reason: {reason}"
        
        # Check if OpenAI is available
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.prompts import ChatPromptTemplate
        except ImportError:
            return "⚠️ OpenAI libraries not available - install langchain-openai"
        
        # Check for API key
        if not os.getenv("OPENAI_API_KEY"):
            return "⚠️ OPENAI_API_KEY not set - AI summary disabled"
        
        # Generate AI summary
        llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a trading analyst reviewing Rex (Gold Trading Bot) performance.
            
            Analyze the trading data and provide:
            1. Overall performance assessment (profitable/not profitable)
            2. Key strengths (what's working)
            3. Key weaknesses (what needs improvement)
            4. Risk assessment (profit factor, win rate, risk/reward)
            5. Actionable recommendations (what to adjust)
            
            Be concise, specific, and data-driven. Use emojis sparingly for clarity."""),
            ("user", context)
        ])
        
        chain = prompt | llm
        ai_summary = chain.invoke({}).content
        
        return ai_summary
        
    except Exception as e:
        print(f"⚠️ AI summary generation failed: {e}")
        return f"⚠️ Could not generate AI summary: {e}"


def format_summary_message(summary_data, ai_summary=None):
    """Format the summary as a Slack message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Determine status emoji
    if summary_data['total_pnl'] > 0:
        status_emoji = "🟢"
    elif summary_data['total_pnl'] < 0:
        status_emoji = "🔴"
    else:
        status_emoji = "🟡"
    
    # Profit factor interpretation
    pf = summary_data['profit_factor']
    if pf >= 2.0:
        pf_status = "✅ Excellent"
    elif pf >= 1.5:
        pf_status = "✅ Good"
    elif pf >= 1.0:
        pf_status = "⚠️ Marginal"
    else:
        pf_status = "❌ Poor"
    
    message = f"""
{status_emoji} *REX TRADING BOT - Hourly Summary*
*Time:* {timestamp}

*📊 Performance Metrics:*
• Total Trades: {summary_data['total_trades']}
• Win Rate: {summary_data['win_rate']:.1f}% ({summary_data['wins']}W / {summary_data['losses']}L)
• Total PnL: *${summary_data['total_pnl']:.2f}*

*💰 Profitability:*
• Average Win: ${summary_data['avg_win']:.2f}
• Average Loss: ${summary_data['avg_loss']:.2f}
• Largest Win: ${summary_data['largest_win']:.2f}
• Largest Loss: ${summary_data['largest_loss']:.2f}
• Profit Factor: {summary_data['profit_factor']:.2f} {pf_status}

*📈 Risk/Reward:*
• Total Wins: ${summary_data['total_wins_amount']:.2f}
• Total Losses: ${summary_data['total_losses_amount']:.2f}
"""
    
    # v10: Add session breakdown
    session_stats = summary_data.get('session_breakdown', {})
    if session_stats:
        message += "\n*🌍 SESSION BREAKDOWN:*\n"
        for session, stats in session_stats.items():
            if stats['trades'] > 0:
                win_rate = (stats['wins'] / stats['trades'] * 100)
                pnl_emoji = "🟢" if stats['pnl'] > 0 else "🔴" if stats['pnl'] < 0 else "🟡"
                message += f"• {session}: {stats['trades']} trades | {win_rate:.0f}% win | {pnl_emoji} ${stats['pnl']:.2f}\n"
    
    if ai_summary:
        message += f"\n*🤖 AI Analysis:*\n{ai_summary}\n"
    
    return message


def send_slack_message(message, channel=None):
    """Send a text message to Slack."""
    if not SLACK_SDK_AVAILABLE:
        print("⚠️ slack-sdk not installed - message not sent")
        return False
    if not slack_client:
        print("⚠️ Slack not configured - message not sent")
        return False
    
    channel = channel or SLACK_CHANNEL
    
    try:
        response = slack_client.chat_postMessage(
            channel=channel,
            text=message,
            mrkdwn=True
        )
        print(f"✅ Slack message sent to {channel}")
        return True
    except SlackApiError as e:
        print(f"❌ Slack API error: {e.response['error']}")
        return False


def upload_csv_to_slack(csv_path="rex_trades.csv", channel=None):
    """Upload CSV file to Slack."""
    if not SLACK_SDK_AVAILABLE:
        print("⚠️ slack-sdk not installed - CSV not uploaded")
        return False
    if not slack_client:
        print("⚠️ Slack not configured - CSV not uploaded")
        return False
    
    csv_file = Path(__file__).parent / csv_path
    
    if not csv_file.exists():
        print(f"⚠️ CSV file not found: {csv_file}")
        return False
    
    channel = channel or SLACK_CHANNEL
    
    try:
        response = slack_client.files_upload_v2(
            channel=channel,
            file=str(csv_file),
            title=f"Rex Trades - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            initial_comment="📎 Complete trade history CSV"
        )
        print(f"✅ CSV uploaded to {channel}")
        return True
    except SlackApiError as e:
        print(f"❌ Slack upload error: {e.response['error']}")
        return False


def send_hourly_summary(csv_path="rex_trades.csv", channel=None, include_ai=True):
    """
    Main function: Send hourly summary with CSV to Slack.
    
    Args:
        csv_path: Path to trades CSV file
        channel: Slack channel (defaults to SLACK_CHANNEL env var)
        include_ai: Whether to include AI-generated analysis
    """
    if not SLACK_SDK_AVAILABLE:
        print("⚠️ slack-sdk not installed - summary not sent")
        return False
    if not slack_client:
        print("⚠️ Slack not configured - summary not sent")
        return False
    
    # Read trades
    trades = read_trades_csv(csv_path)
    
    if not trades:
        send_slack_message(
            f"⚠️ *REX Hourly Summary*\nNo trades recorded yet.",
            channel
        )
        return False
    
    # Calculate summary
    summary_data = calculate_pnl_summary(trades)
    
    # Generate AI summary if requested
    ai_summary = None
    if include_ai:
        try:
            ai_summary = generate_ai_summary(summary_data, trades)
        except Exception as e:
            print(f"⚠️ AI summary failed: {e}")
    
    # Format and send message
    message = format_summary_message(summary_data, ai_summary)
    send_slack_message(message, channel)
    
    # Upload CSV
    upload_csv_to_slack(csv_path, channel)
    
    return True

