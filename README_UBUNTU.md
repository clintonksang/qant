# 🚀 Running QuantAgent Arbitrage Bot on Ubuntu Server (Without Docker)

Complete guide for deploying and running the arbitrage trading bot directly on Ubuntu server without Docker.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Server Setup](#server-setup)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Running the Application](#running-the-application)
6. [Systemd Service Setup](#systemd-service-setup)
7. [Monitoring & Management](#monitoring--management)
8. [Troubleshooting](#troubleshooting)
9. [Security Best Practices](#security-best-practices)

---

## Prerequisites

- **Ubuntu 20.04+** server (VPS or dedicated)
- **SSH access** to your server
- **API Keys** ready:
  - Tiingo API key (for real-time FX data)
  - OpenAI API key (for AI decision making)
  - Pinecone API key (for trade history learning)
- **Git** installed on server

---

## Server Setup

### 1. Connect to Your Server

```bash
ssh user@your-server-ip
# Or with key:
ssh -i ~/.ssh/your_key user@your-server-ip
```

### 2. Update System

```bash
sudo apt update && sudo apt upgrade -y
```

### 3. Install Python and Dependencies

```bash
# Install Python 3.11+ and pip
sudo apt install -y python3.11 python3.11-venv python3-pip git

# Verify Python version
python3 --version  # Should be 3.11 or higher

# Install build dependencies (may be needed for some packages)
sudo apt install -y build-essential python3-dev
```

### 4. Create Application Directory

```bash
# Create directory
sudo mkdir -p /opt/quantagent
sudo chown $USER:$USER /opt/quantagent
cd /opt/quantagent
```

---

## Installation

### 1. Clone Repository

**Option A: From GitHub (Recommended)**
```bash
cd /opt/quantagent
git clone https://github.com/clintonksang/qant.git .
```

**Option B: Upload via SCP**
```bash
# From your local machine:
scp -r /path/to/QuantAgent/* user@your-server-ip:/opt/quantagent/
```

### 2. Create Python Virtual Environment

```bash
cd /opt/quantagent

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### 3. Install Python Dependencies

```bash
# Make sure you're in the venv (you should see (venv) in prompt)
pip install -r requirements.txt
```

**Expected output:** All packages should install successfully. If you see errors, check the troubleshooting section.

### 4. Verify Installation

```bash
# Test Python imports
python3 -c "import websocket, openai, pinecone; print('✅ All imports successful')"
```

---

## Configuration

### 1. Create Environment File

```bash
cd /opt/quantagent

# Create .env file
nano .env
```

### 2. Add Your Configuration

Copy and paste this template, then fill in your actual API keys:

```bash
# ============================================================
# API KEYS (REQUIRED)
# ============================================================
TIINGO_KEY=your_tiingo_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_INDEX_NAME=rex-memory
ARBITRAGE_INDEX_NAME=rex-arbitrage

# ============================================================
# TRADING CONFIGURATION
# ============================================================
# Set to true to execute real trades via MT5 API
# Set to false for paper trading (simulation only)
LIVE_TRADING=false

# MT5 API Configuration
MT5_API_URL=https://api.ruthwestlimited.com
MT5_VOLUME=0.01
MT5_MAGIC=123456
```

**Save and exit:** `Ctrl+X`, then `Y`, then `Enter`

### 3. Secure Environment File

```bash
# Restrict permissions (only owner can read/write)
chmod 600 .env

# Verify it's secure
ls -la .env  # Should show -rw------- permissions
```

### 4. Create Logs Directory

```bash
mkdir -p /opt/quantagent/logs
chmod 755 /opt/quantagent/logs
```

---

## Running the Application

### Manual Test Run

First, test that everything works:

```bash
cd /opt/quantagent
source venv/bin/activate
cd arbitrage
python3 main.py
```

**What to expect:**
- You should see connection messages
- "🚀 Arbitrage Bot Starting..."
- WebSocket connection established
- Price data streaming
- Signal detection starting after warmup

**To stop:** Press `Ctrl+C`

If the test run works, proceed to set up the systemd service for automatic startup.

---

## Systemd Service Setup

### 1. Create Systemd Service File

```bash
sudo nano /etc/systemd/system/quantagent-arbitrage.service
```

### 2. Add Service Configuration

Copy and paste this configuration:

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

**Important:** Replace `YOUR_USERNAME` with your actual Ubuntu username (run `whoami` to find it).

### 3. Enable and Start Service

```bash
# Reload systemd to recognize new service
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable quantagent-arbitrage

# Start the service
sudo systemctl start quantagent-arbitrage

# Check status
sudo systemctl status quantagent-arbitrage
```

**Expected output:** You should see `Active: active (running)` in green.

---

## Monitoring & Management

### View Logs

**Live logs (follow in real-time):**
```bash
# Systemd logs
sudo journalctl -u quantagent-arbitrage -f

# Or view log files directly
tail -f /opt/quantagent/logs/arbitrage.log
tail -f /opt/quantagent/logs/arbitrage_error.log
```

**Last N lines:**
```bash
# Last 100 lines
sudo journalctl -u quantagent-arbitrage -n 100

# Last 50 lines of log file
tail -n 50 /opt/quantagent/logs/arbitrage.log
```

### Service Management Commands

| Task                   | Command                                       |
| ---------------------- | --------------------------------------------- |
| **Start**              | `sudo systemctl start quantagent-arbitrage`   |
| **Stop**               | `sudo systemctl stop quantagent-arbitrage`    |
| **Restart**            | `sudo systemctl restart quantagent-arbitrage` |
| **Status**             | `sudo systemctl status quantagent-arbitrage`  |
| **Disable auto-start** | `sudo systemctl disable quantagent-arbitrage` |
| **Enable auto-start**  | `sudo systemctl enable quantagent-arbitrage`  |

### View Trade Logs

```bash
# View all trades
cat /opt/quantagent/arbitrage/arbitrage_trades.csv

# Watch trades in real-time (if CSV is being written)
tail -f /opt/quantagent/arbitrage/arbitrage_trades.csv

# Count total trades
wc -l /opt/quantagent/arbitrage/arbitrage_trades.csv
```

### Check Application Status

```bash
# Check if process is running
ps aux | grep "python3.*main.py"

# Check resource usage
top -p $(pgrep -f "python3.*main.py")
```

---

## Troubleshooting

### Service Won't Start

**Check service status:**
```bash
sudo systemctl status quantagent-arbitrage
```

**View error logs:**
```bash
sudo journalctl -u quantagent-arbitrage -n 50 --no-pager
cat /opt/quantagent/logs/arbitrage_error.log
```

**Common issues:**

1. **Missing .env file:**
   ```bash
   # Verify .env exists
   ls -la /opt/quantagent/.env
   # If missing, create it (see Configuration section)
   ```

2. **Wrong user in service file:**
   ```bash
   # Check your username
   whoami
   # Update service file with correct username
   sudo nano /etc/systemd/system/quantagent-arbitrage.service
   sudo systemctl daemon-reload
   sudo systemctl restart quantagent-arbitrage
   ```

3. **Python path issues:**
   ```bash
   # Verify venv Python exists
   ls -la /opt/quantagent/venv/bin/python3
   # If missing, recreate venv
   cd /opt/quantagent
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Permission issues:**
   ```bash
   # Fix ownership
   sudo chown -R $USER:$USER /opt/quantagent
   # Fix .env permissions
   chmod 600 /opt/quantagent/.env
   ```

### Connection Errors

**Test API connections manually:**
```bash
cd /opt/quantagent
source venv/bin/activate
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('TIINGO_KEY:', 'SET' if os.getenv('TIINGO_KEY') else 'MISSING')
print('OPENAI_API_KEY:', 'SET' if os.getenv('OPENAI_API_KEY') else 'MISSING')
print('PINECONE_API_KEY:', 'SET' if os.getenv('PINECONE_API_KEY') else 'MISSING')
"
```

**Test WebSocket connection:**
```bash
cd /opt/quantagent
source venv/bin/activate
cd arbitrage
python3 -c "
from websocket import create_connection
import ssl
ws = create_connection('wss://api.tiingo.com/fx', sslopt={'cert_reqs': ssl.CERT_NONE})
print('✅ WebSocket connection successful')
ws.close()
"
```

### Missing Dependencies

**Reinstall requirements:**
```bash
cd /opt/quantagent
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

### Service Keeps Restarting

**Check logs for crash reason:**
```bash
sudo journalctl -u quantagent-arbitrage -n 100 --no-pager | grep -i error
```

**Common causes:**
- Invalid API keys
- Network connectivity issues
- Missing environment variables
- Python import errors

### View Container Shell (if needed)

If you need to debug interactively:
```bash
# Stop service
sudo systemctl stop quantagent-arbitrage

# Run manually with output
cd /opt/quantagent
source venv/bin/activate
cd arbitrage
python3 main.py
```

---

## Security Best Practices

### 1. Firewall Setup

```bash
# Install UFW if not present
sudo apt install ufw -y

# Allow SSH (IMPORTANT - do this first!)
sudo ufw allow ssh
sudo ufw allow 22/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

### 2. Secure .env File

```bash
# Already done in Configuration section, but verify:
chmod 600 /opt/quantagent/.env
ls -la /opt/quantagent/.env  # Should show -rw-------
```

### 3. Regular Updates

```bash
# Update system weekly
sudo apt update && sudo apt upgrade -y

# Update application code
cd /opt/quantagent
git pull origin main

# Restart service after updates
sudo systemctl restart quantagent-arbitrage
```

### 4. Backup Trade Logs

Create a backup script:

```bash
nano /opt/quantagent/backup.sh
```

Add:
```bash
#!/bin/bash
BACKUP_DIR="/opt/backups/quantagent"
mkdir -p $BACKUP_DIR
cp /opt/quantagent/arbitrage/arbitrage_trades.csv "$BACKUP_DIR/trades_$(date +%Y%m%d_%H%M%S).csv"
echo "Backup created: $BACKUP_DIR"
```

Make executable:
```bash
chmod +x /opt/quantagent/backup.sh
```

Add to crontab (daily backup at midnight):
```bash
(crontab -l 2>/dev/null; echo "0 0 * * * /opt/quantagent/backup.sh") | crontab -
```

### 5. Monitor Disk Space

```bash
# Check disk usage
df -h

# Clean old logs if needed
find /opt/quantagent/logs -name "*.log" -mtime +30 -delete
```

---

## Enabling Live Trading

**⚠️ WARNING: Only enable after thorough paper trading testing!**

```bash
# Edit .env file
nano /opt/quantagent/.env

# Change this line:
LIVE_TRADING=true

# Save and restart
sudo systemctl restart quantagent-arbitrage

# Monitor closely for first few trades
sudo journalctl -u quantagent-arbitrage -f
```

---

## Updating the Application

```bash
cd /opt/quantagent

# Stop service
sudo systemctl stop quantagent-arbitrage

# Pull latest code
git pull origin main

# Update dependencies (if requirements.txt changed)
source venv/bin/activate
pip install -r requirements.txt

# Restart service
sudo systemctl start quantagent-arbitrage

# Check status
sudo systemctl status quantagent-arbitrage
```

---

## Quick Reference

| Task             | Command                                                                         |
| ---------------- | ------------------------------------------------------------------------------- |
| **Start bot**    | `sudo systemctl start quantagent-arbitrage`                                     |
| **Stop bot**     | `sudo systemctl stop quantagent-arbitrage`                                      |
| **Restart bot**  | `sudo systemctl restart quantagent-arbitrage`                                   |
| **View logs**    | `sudo journalctl -u quantagent-arbitrage -f`                                    |
| **Check status** | `sudo systemctl status quantagent-arbitrage`                                    |
| **View trades**  | `cat /opt/quantagent/arbitrage/arbitrage_trades.csv`                            |
| **Update code**  | `cd /opt/quantagent && git pull && sudo systemctl restart quantagent-arbitrage` |

---

## Support

If you encounter issues:

1. **Check logs first:**
   ```bash
   sudo journalctl -u quantagent-arbitrage -n 100
   ```

2. **Verify configuration:**
   - `.env` file exists and has all required keys
   - Service file has correct user/paths
   - Virtual environment is set up correctly

3. **Test manually:**
   ```bash
   cd /opt/quantagent
   source venv/bin/activate
   cd arbitrage
   python3 main.py
   ```

4. **Check system resources:**
   ```bash
   free -h  # Memory
   df -h    # Disk space
   ```

---

## Next Steps

After successful deployment:

1. ✅ Monitor logs for first hour
2. ✅ Verify trades are being logged to CSV
3. ✅ Check that WebSocket connection is stable
4. ✅ Review trade decisions in logs
5. ✅ Enable live trading only after confidence in paper trading

---

**Happy Trading! 🚀📈**

