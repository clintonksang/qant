# 🚀 Running Arbitrage Bot Detached & Viewing Logs

Complete guide for running the bot in the background and checking logs later.

---

## Option 1: Systemd Service (Recommended for Production)

### Setup (One-time)

**1. Create service file:**
```bash
sudo nano /etc/systemd/system/quantagent-arbitrage.service
```

**2. Add this configuration:**
```ini
[Unit]
Description=QuantAgent Arbitrage Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
Group=YOUR_USERNAME
WorkingDirectory=/opt/quantagent/arbitrage
Environment="PATH=/opt/quantagent/venv/bin"
ExecStart=/opt/quantagent/venv/bin/python3 /opt/quantagent/arbitrage/main.py
Restart=always
RestartSec=10
StandardOutput=append:/opt/quantagent/logs/arbitrage.log
StandardError=append:/opt/quantagent/logs/arbitrage_error.log

[Install]
WantedBy=multi-user.target
```

**Replace `YOUR_USERNAME` with your actual username** (run `whoami` to find it).

**3. Create logs directory:**
```bash
mkdir -p /opt/quantagent/logs
chmod 755 /opt/quantagent/logs
```

**4. Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable quantagent-arbitrage
sudo systemctl start quantagent-arbitrage
```

### Running Commands

| Task | Command |
|------|---------|
| **Start** | `sudo systemctl start quantagent-arbitrage` |
| **Stop** | `sudo systemctl stop quantagent-arbitrage` |
| **Restart** | `sudo systemctl restart quantagent-arbitrage` |
| **Status** | `sudo systemctl status quantagent-arbitrage` |
| **Enable auto-start** | `sudo systemctl enable quantagent-arbitrage` |
| **Disable auto-start** | `sudo systemctl disable quantagent-arbitrage` |

### Viewing Logs

**Live logs (follow in real-time):**
```bash
# Systemd journal logs
sudo journalctl -u quantagent-arbitrage -f

# Or view log files directly
tail -f /opt/quantagent/logs/arbitrage.log
tail -f /opt/quantagent/logs/arbitrage_error.log
```

**Last N lines:**
```bash
# Last 100 lines from journal
sudo journalctl -u quantagent-arbitrage -n 100

# Last 50 lines from log file
tail -n 50 /opt/quantagent/logs/arbitrage.log

# Last 50 error lines
tail -n 50 /opt/quantagent/logs/arbitrage_error.log
```

**Search logs:**
```bash
# Search for errors
sudo journalctl -u quantagent-arbitrage | grep -i error

# Search for trades
sudo journalctl -u quantagent-arbitrage | grep -i "OPENED\|CLOSED"

# Search for specific pair
sudo journalctl -u quantagent-arbitrage | grep "EUR_GBP"
```

**Logs since specific time:**
```bash
# Since 1 hour ago
sudo journalctl -u quantagent-arbitrage --since "1 hour ago"

# Since today
sudo journalctl -u quantagent-arbitrage --since today

# Since specific date
sudo journalctl -u quantagent-arbitrage --since "2025-12-22 08:00:00"
```

---

## Option 2: nohup (Simple Background)

### Running Detached

```bash
cd /opt/quantagent
source venv/bin/activate
cd arbitrage

# Run in background with nohup
nohup python3 main.py > ../logs/arbitrage.log 2> ../logs/arbitrage_error.log &

# Note the process ID (PID) that's printed
# Example: [1] 12345
```

**Save the PID** for later reference:
```bash
echo $! > /opt/quantagent/arbitrage.pid
```

### Managing the Process

**Check if running:**
```bash
# Using PID file
ps -p $(cat /opt/quantagent/arbitrage.pid)

# Or find by process name
ps aux | grep "python3.*main.py"
```

**Stop the process:**
```bash
# Using PID file
kill $(cat /opt/quantagent/arbitrage.pid)

# Or find and kill
pkill -f "python3.*main.py"
```

**Restart:**
```bash
# Stop first
kill $(cat /opt/quantagent/arbitrage.pid)

# Start again
cd /opt/quantagent/arbitrage
source ../venv/bin/activate
nohup python3 main.py > ../logs/arbitrage.log 2> ../logs/arbitrage_error.log &
echo $! > /opt/quantagent/arbitrage.pid
```

### Viewing Logs

```bash
# Live logs
tail -f /opt/quantagent/logs/arbitrage.log

# Last 100 lines
tail -n 100 /opt/quantagent/logs/arbitrage.log

# Errors only
tail -f /opt/quantagent/logs/arbitrage_error.log

# Search logs
grep -i "error" /opt/quantagent/logs/arbitrage.log
grep "OPENED" /opt/quantagent/logs/arbitrage.log
```

---

## Option 3: tmux (Interactive Session)

### Setup

**1. Install tmux (if not installed):**
```bash
sudo apt install tmux -y
```

**2. Start a detached session:**
```bash
cd /opt/quantagent
source venv/bin/activate
cd arbitrage

# Start new detached session
tmux new-session -d -s arbitrage 'python3 main.py'
```

### Managing Session

| Task | Command |
|------|---------|
| **List sessions** | `tmux list-sessions` |
| **Attach to session** | `tmux attach-session -t arbitrage` |
| **Detach from session** | Press `Ctrl+B`, then `D` |
| **Kill session** | `tmux kill-session -t arbitrage` |
| **Restart session** | `tmux kill-session -t arbitrage && tmux new-session -d -s arbitrage 'cd /opt/quantagent/arbitrage && source ../venv/bin/activate && python3 main.py'` |

### Viewing Logs

**Option A: Attach to session and scroll:**
```bash
# Attach to see live output
tmux attach-session -t arbitrage

# Scroll up: Ctrl+B, then [
# Use arrow keys to scroll
# Press 'q' to exit scroll mode
```

**Option B: Capture output to file:**
```bash
# Start session with logging
tmux new-session -d -s arbitrage 'python3 main.py 2>&1 | tee /opt/quantagent/logs/arbitrage.log'

# Then view logs normally
tail -f /opt/quantagent/logs/arbitrage.log
```

---

## Option 4: screen (Alternative to tmux)

### Setup

**1. Install screen:**
```bash
sudo apt install screen -y
```

**2. Start detached:**
```bash
cd /opt/quantagent
source venv/bin/activate
cd arbitrage

# Start new screen session
screen -dmS arbitrage python3 main.py
```

### Managing Session

| Task | Command |
|------|---------|
| **List sessions** | `screen -ls` |
| **Attach to session** | `screen -r arbitrage` |
| **Detach from session** | Press `Ctrl+A`, then `D` |
| **Kill session** | `screen -X -S arbitrage quit` |

### Viewing Logs

Same as tmux - attach to see output, or redirect to log file:
```bash
screen -dmS arbitrage bash -c 'python3 main.py 2>&1 | tee /opt/quantagent/logs/arbitrage.log'
```

---

## Quick Reference: All Methods

### Start Detached

| Method | Command |
|--------|---------|
| **systemd** | `sudo systemctl start quantagent-arbitrage` |
| **nohup** | `nohup python3 main.py > logs/arbitrage.log 2>&1 &` |
| **tmux** | `tmux new-session -d -s arbitrage 'python3 main.py'` |
| **screen** | `screen -dmS arbitrage python3 main.py` |

### View Logs

| Method | Command |
|--------|---------|
| **systemd** | `sudo journalctl -u quantagent-arbitrage -f` |
| **nohup** | `tail -f logs/arbitrage.log` |
| **tmux** | `tmux attach-session -t arbitrage` |
| **screen** | `screen -r arbitrage` |

### Stop

| Method | Command |
|--------|---------|
| **systemd** | `sudo systemctl stop quantagent-arbitrage` |
| **nohup** | `kill $(cat arbitrage.pid)` or `pkill -f "python3.*main.py"` |
| **tmux** | `tmux kill-session -t arbitrage` |
| **screen** | `screen -X -S arbitrage quit` |

---

## Recommended Setup Script

Create a helper script for easy management:

```bash
nano /opt/quantagent/manage_bot.sh
```

Add:
```bash
#!/bin/bash

SCRIPT_DIR="/opt/quantagent"
LOG_DIR="$SCRIPT_DIR/logs"
PID_FILE="$SCRIPT_DIR/arbitrage.pid"

case "$1" in
    start)
        cd "$SCRIPT_DIR/arbitrage"
        source ../venv/bin/activate
        nohup python3 main.py > "$LOG_DIR/arbitrage.log" 2> "$LOG_DIR/arbitrage_error.log" &
        echo $! > "$PID_FILE"
        echo "✅ Bot started (PID: $(cat $PID_FILE))"
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            kill $(cat "$PID_FILE") 2>/dev/null
            rm "$PID_FILE"
            echo "✅ Bot stopped"
        else
            echo "❌ Bot not running (no PID file)"
        fi
        ;;
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        if [ -f "$PID_FILE" ] && ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
            echo "✅ Bot is running (PID: $(cat $PID_FILE))"
        else
            echo "❌ Bot is not running"
        fi
        ;;
    logs)
        tail -f "$LOG_DIR/arbitrage.log"
        ;;
    errors)
        tail -f "$LOG_DIR/arbitrage_error.log"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|errors}"
        exit 1
        ;;
esac
```

Make executable:
```bash
chmod +x /opt/quantagent/manage_bot.sh
```

**Usage:**
```bash
# Start
/opt/quantagent/manage_bot.sh start

# Stop
/opt/quantagent/manage_bot.sh stop

# Restart
/opt/quantagent/manage_bot.sh restart

# Check status
/opt/quantagent/manage_bot.sh status

# View logs
/opt/quantagent/manage_bot.sh logs

# View errors
/opt/quantagent/manage_bot.sh errors
```

---

## Best Practice: Systemd (Production)

For production servers, **systemd is recommended** because:
- ✅ Auto-restarts on crash
- ✅ Auto-starts on boot
- ✅ Better log management
- ✅ Process monitoring
- ✅ Resource limits (if needed)

---

## Troubleshooting

### Bot Not Starting

```bash
# Check if already running
ps aux | grep "python3.*main.py"

# Check logs for errors
tail -50 /opt/quantagent/logs/arbitrage_error.log

# Check .env file exists
ls -la /opt/quantagent/.env

# Test manually
cd /opt/quantagent/arbitrage
source ../venv/bin/activate
python3 main.py
```

### Logs Not Appearing

```bash
# Check log directory permissions
ls -la /opt/quantagent/logs

# Check disk space
df -h

# Check if process is writing
lsof | grep arbitrage.log
```

### Process Keeps Dying

```bash
# Check systemd status
sudo systemctl status quantagent-arbitrage

# Check for memory issues
free -h

# Check for Python errors
sudo journalctl -u quantagent-arbitrage -n 100 | grep -i error
```

---

**Happy Trading! 🚀📈**

