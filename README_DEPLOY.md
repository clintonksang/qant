# QuantAgent Deployment Guide

## Option 1: Deploy with PM2 (Recommended for monitoring)

### On your Mac (package and upload):
```bash
# 1. Package the application
chmod +x deploy.sh
./deploy.sh

# 2. Copy to server
scp quantagent-deploy.tar.gz user@YOUR_SERVER_IP:/tmp/
scp ecosystem.config.js user@YOUR_SERVER_IP:/tmp/
```

### On Linux Server:
```bash
# 1. Install dependencies
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nodejs npm

# 2. Install PM2
sudo npm install -g pm2

# 3. Create deployment directory
sudo mkdir -p /opt/quantagent/logs
sudo useradd -r -s /bin/bash quantagent
sudo chown -R quantagent:quantagent /opt/quantagent

# 4. Extract application
cd /opt/quantagent
sudo tar -xzf /tmp/quantagent-deploy.tar.gz -C /opt/quantagent
sudo mv /tmp/ecosystem.config.js /opt/quantagent/
sudo chown -R quantagent:quantagent /opt/quantagent

# 5. Set up Python environment
sudo -u quantagent python3 -m venv venv
sudo -u quantagent /opt/quantagent/venv/bin/pip install -r requirements.txt

# 6. Create .env file with your credentials
sudo -u quantagent nano /opt/quantagent/.env
# Add:
# TIINGO_KEY=your_key_here
# OPENAI_API_KEY=your_key_here
# PINECONE_API_KEY=your_key_here

# 7. Start with PM2
cd /opt/quantagent
pm2 start ecosystem.config.js
pm2 save
pm2 startup  # Follow the command it outputs
```

### PM2 Monitoring Commands:
```bash
# View logs (like you do now)
pm2 logs quantagent

# View real-time logs with only errors
pm2 logs quantagent --err

# View only output logs
pm2 logs quantagent --out

# View logs with lines
pm2 logs quantagent --lines 100

# Monitor resources
pm2 monit

# Check status
pm2 status

# Restart
pm2 restart quantagent

# Stop
pm2 stop quantagent

# View detailed info
pm2 info quantagent
```

## Option 2: Deploy with systemd (Alternative)

### On Linux Server:
```bash
# Follow steps 1-6 from Option 1, then:

# 7. Copy and install systemd service
sudo cp /opt/quantagent/quantagent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable quantagent
sudo systemctl start quantagent
```

### systemd Monitoring Commands:
```bash
# View logs
sudo journalctl -u quantagent -f

# View last 100 lines
sudo journalctl -u quantagent -n 100

# Check status
sudo systemctl status quantagent

# Restart
sudo systemctl restart quantagent

# Stop
sudo systemctl stop quantagent
```

## Port 8000 Note
Your application doesn't currently expose a web interface on port 8000. If you need to add a REST API or web dashboard:

1. Add Flask/FastAPI to requirements.txt
2. Create an API wrapper around your trading bot
3. Update the ecosystem config to expose PORT=8000

Currently, the bot runs as a background process connecting to WebSocket streams (no HTTP server).

## Security Recommendations
- Never commit `.env` file to git
- Use SSH keys for server access
- Configure firewall: `sudo ufw allow 22 && sudo ufw allow 8000 && sudo ufw enable`
- Keep secrets in environment variables
- Regular backups of trade logs and CSV files

## Monitoring Trade Logs
```bash
# Watch CSV updates in real-time
tail -f /opt/quantagent/rex_trades.csv

# Watch application logs
pm2 logs quantagent --lines 50
```
