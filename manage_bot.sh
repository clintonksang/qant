#!/bin/bash

# QuantAgent Arbitrage Bot Management Script
# Usage: ./manage_bot.sh {start|stop|restart|status|logs|errors}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PID_FILE="$SCRIPT_DIR/arbitrage.pid"
VENV_DIR="$SCRIPT_DIR/venv"
BOT_DIR="$SCRIPT_DIR/arbitrage"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
            echo "⚠️  Bot is already running (PID: $(cat $PID_FILE))"
            exit 1
        fi
        
        cd "$BOT_DIR"
        
        # Activate virtual environment
        if [ -d "$VENV_DIR" ]; then
            source "$VENV_DIR/bin/activate"
        else
            echo "❌ Virtual environment not found at $VENV_DIR"
            exit 1
        fi
        
        # Start bot in background
        nohup python3 main.py > "$LOG_DIR/arbitrage.log" 2> "$LOG_DIR/arbitrage_error.log" &
        echo $! > "$PID_FILE"
        echo "✅ Bot started (PID: $(cat $PID_FILE))"
        echo "📝 Logs: $LOG_DIR/arbitrage.log"
        echo "📝 Errors: $LOG_DIR/arbitrage_error.log"
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p $PID > /dev/null 2>&1; then
                kill $PID 2>/dev/null
                sleep 1
                # Force kill if still running
                if ps -p $PID > /dev/null 2>&1; then
                    kill -9 $PID 2>/dev/null
                fi
                echo "✅ Bot stopped (PID: $PID)"
            else
                echo "⚠️  Process not found (PID: $PID)"
            fi
            rm -f "$PID_FILE"
        else
            echo "❌ Bot not running (no PID file)"
            # Try to kill by process name
            pkill -f "python3.*arbitrage/main.py" && echo "✅ Killed by process name" || echo "❌ No process found"
        fi
        ;;
    restart)
        echo "🔄 Restarting bot..."
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p $PID > /dev/null 2>&1; then
                echo "✅ Bot is running (PID: $PID)"
                echo "   Uptime: $(ps -p $PID -o etime= | tr -d ' ')"
                echo "   Memory: $(ps -p $PID -o rss= | awk '{printf "%.1f MB", $1/1024}')"
            else
                echo "❌ Bot is not running (stale PID file)"
                rm -f "$PID_FILE"
            fi
        else
            # Check if running by process name
            if pgrep -f "python3.*arbitrage/main.py" > /dev/null; then
                echo "⚠️  Bot appears to be running but no PID file found"
                ps aux | grep "python3.*arbitrage/main.py" | grep -v grep
            else
                echo "❌ Bot is not running"
            fi
        fi
        ;;
    logs)
        if [ -f "$LOG_DIR/arbitrage.log" ]; then
            tail -f "$LOG_DIR/arbitrage.log"
        else
            echo "❌ Log file not found: $LOG_DIR/arbitrage.log"
            echo "   Bot may not have started yet"
        fi
        ;;
    errors)
        if [ -f "$LOG_DIR/arbitrage_error.log" ]; then
            tail -f "$LOG_DIR/arbitrage_error.log"
        else
            echo "❌ Error log file not found: $LOG_DIR/arbitrage_error.log"
        fi
        ;;
    view)
        # View last N lines (default 50)
        LINES=${2:-50}
        if [ -f "$LOG_DIR/arbitrage.log" ]; then
            tail -n $LINES "$LOG_DIR/arbitrage.log"
        else
            echo "❌ Log file not found"
        fi
        ;;
    trades)
        # View trade CSV
        if [ -f "$BOT_DIR/arbitrage_trades.csv" ]; then
            tail -n 20 "$BOT_DIR/arbitrage_trades.csv" | column -t -s','
        else
            echo "❌ Trade log not found: $BOT_DIR/arbitrage_trades.csv"
        fi
        ;;
    *)
        echo "QuantAgent Arbitrage Bot Management"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|errors|view|trades}"
        echo ""
        echo "Commands:"
        echo "  start    - Start the bot in background"
        echo "  stop     - Stop the running bot"
        echo "  restart  - Restart the bot"
        echo "  status   - Check if bot is running"
        echo "  logs     - Follow live logs (Ctrl+C to exit)"
        echo "  errors   - Follow error logs (Ctrl+C to exit)"
        echo "  view [N] - View last N lines of logs (default: 50)"
        echo "  trades   - View recent trades from CSV"
        echo ""
        exit 1
        ;;
esac

