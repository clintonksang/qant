# 🚀 Deploying QuantAgent to Ubuntu Server

Complete guide for deploying the arbitrage bot on an Ubuntu server using Docker.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Server Setup](#server-setup)
3. [Deploy the Bot](#deploy-the-bot)
4. [Management Commands](#management-commands)
5. [Monitoring](#monitoring)
6. [Troubleshooting](#troubleshooting)
7. [Security Best Practices](#security-best-practices)

---

## Prerequisites

- Ubuntu 20.04+ server (VPS or dedicated)
- SSH access to your server
- Your API keys ready:
  - Tiingo API key
  - OpenAI API key
  - Pinecone API key
- Git installed locally

---

## Server Setup

### 1. Connect to Your Server

```bash
ssh root@your-server-ip
# Or with a user:
ssh user@your-server-ip
```

### 2. Update System

```bash
sudo apt update && sudo apt upgrade -y
```

### 3. Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group (if not root)
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

### 4. Install Git

```bash
sudo apt install git -y
```

### 5. Create Application Directory

```bash
mkdir -p /opt/quantagent
cd /opt/quantagent
```

---

## Deploy the Bot

### 1. Clone Your Repository

**Option A: From GitHub (recommended)**
```bash
cd /opt/quantagent
git clone https://github.com/yourusername/QuantAgent.git .
```

**Option B: Upload via SCP**
```bash
# From your local machine:
scp -r /path/to/QuantAgent/* user@your-server-ip:/opt/quantagent/
```

### 2. Create Environment File

```bash
cd /opt/quantagent

# Copy example config
cp .env.example .env

# Edit with your API keys
nano .env
```

**Fill in your `.env` file:**
```bash
# Required API Keys
TIINGO_KEY=your_actual_tiingo_key
OPENAI_API_KEY=your_actual_openai_key
PINECONE_API_KEY=your_actual_pinecone_key
PINECONE_INDEX_NAME=rex-memory
ARBITRAGE_INDEX_NAME=rex-arbitrage

# Trading Mode (start with paper trading!)
LIVE_TRADING=false
MT5_API_URL=https://api.ruthwestlimited.com
MT5_VOLUME=0.01
MT5_MAGIC=123456
```

Save and exit: `Ctrl+X`, then `Y`, then `Enter`

### 3. Build and Start (Paper Trading)

```bash
cd /opt/quantagent

# Build the Docker image
docker compose build

# Start in detached mode
docker compose up -d

# Check if running
docker compose ps
```

### 4. View Logs

```bash
# Follow live logs
docker compose logs -f arbitrage-bot

# Last 100 lines
docker compose logs --tail=100 arbitrage-bot
```

---

## Management Commands

### Start/Stop/Restart

```bash
cd /opt/quantagent

# Start
docker compose up -d

# Stop
docker compose down

# Restart
docker compose restart

# Rebuild after code changes
docker compose up -d --build --force-recreate
```

### Enable Live Trading

```bash
# Edit .env
nano .env

# Change LIVE_TRADING to true
LIVE_TRADING=true

# Restart the bot
docker compose restart
```

### Check Status

```bash
# Container status
docker compose ps

# Resource usage
docker stats quantagent-arbitrage

# View trade log
cat arbitrage/arbitrage_trades.csv
```

### Pull Updates

```bash
cd /opt/quantagent

# Stop bot
docker compose down

# Pull latest code
git pull origin main

# Rebuild and start
docker compose up -d --build
```

---

## Monitoring

### Create a Simple Monitor Script

```bash
nano /opt/quantagent/monitor.sh
```

Add this content:
```bash
#!/bin/bash

echo "============================================"
echo "QuantAgent Arbitrage Bot Monitor"
echo "============================================"
echo ""

# Check if container is running
if docker ps | grep -q quantagent-arbitrage; then
    echo "✅ Container Status: RUNNING"
else
    echo "❌ Container Status: STOPPED"
    echo "   Run: docker compose up -d"
    exit 1
fi

echo ""

# Show resource usage
echo "📊 Resource Usage:"
docker stats quantagent-arbitrage --no-stream --format "   CPU: {{.CPUPerc}} | Memory: {{.MemUsage}}"

echo ""

# Show last 5 log lines
echo "📜 Recent Logs:"
docker compose logs --tail=5 arbitrage-bot 2>/dev/null | sed 's/^/   /'

echo ""

# Show trade count
TRADE_COUNT=$(wc -l < /opt/quantagent/arbitrage/arbitrage_trades.csv 2>/dev/null || echo "0")
echo "📈 Total Trades Logged: $((TRADE_COUNT - 1))"

echo ""
echo "============================================"
```

Make it executable:
```bash
chmod +x /opt/quantagent/monitor.sh
```

Run it:
```bash
/opt/quantagent/monitor.sh
```

### Set Up Automatic Restart (Optional)

Create a systemd service as backup:

```bash
sudo nano /etc/systemd/system/quantagent.service
```

Add:
```ini
[Unit]
Description=QuantAgent Arbitrage Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/quantagent
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
```

Enable auto-start on boot:
```bash
sudo systemctl daemon-reload
sudo systemctl enable quantagent
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs for errors
docker compose logs arbitrage-bot

# Common issues:
# - Missing .env file
# - Invalid API keys
# - Network issues
```

### Connection Errors

```bash
# Check if container can reach internet
docker exec quantagent-arbitrage ping -c 3 google.com

# Check Tiingo connection
docker exec quantagent-arbitrage curl -s "https://api.tiingo.com/fx" | head
```

### View Container Shell

```bash
# Enter container
docker exec -it quantagent-arbitrage /bin/bash

# Run Python manually
python main.py
```

### Reset Everything

```bash
cd /opt/quantagent

# Stop and remove containers
docker compose down -v

# Remove images
docker rmi quantagent-arbitrage-bot

# Rebuild fresh
docker compose up -d --build
```

### Check Disk Space

```bash
# Disk usage
df -h

# Docker disk usage
docker system df

# Clean up unused Docker data
docker system prune -a
```

---

## Security Best Practices

### 1. Firewall Setup

```bash
# Install UFW
sudo apt install ufw -y

# Allow SSH
sudo ufw allow ssh

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

### 2. Secure .env File

```bash
# Restrict permissions
chmod 600 /opt/quantagent/.env

# Make it owned by root
sudo chown root:root /opt/quantagent/.env
```

### 3. Regular Updates

```bash
# Update system weekly
sudo apt update && sudo apt upgrade -y

# Update Docker images
docker compose pull
docker compose up -d
```

### 4. Backup Trade Logs

```bash
# Create backup script
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

```bash
chmod +x /opt/quantagent/backup.sh

# Add to crontab (daily backup at midnight)
(crontab -l 2>/dev/null; echo "0 0 * * * /opt/quantagent/backup.sh") | crontab -
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Start bot | `docker compose up -d` |
| Stop bot | `docker compose down` |
| View logs | `docker compose logs -f` |
| Check status | `docker compose ps` |
| Restart | `docker compose restart` |
| Rebuild | `docker compose up -d --build` |
| Enter container | `docker exec -it quantagent-arbitrage bash` |
| View trades | `cat arbitrage/arbitrage_trades.csv` |

---

## Support

If you encounter issues:

1. Check logs: `docker compose logs -f`
2. Verify `.env` file has all required keys
3. Ensure MT5 API is accessible
4. Check container status: `docker compose ps`

---

**Happy Trading! 🚀📈**

