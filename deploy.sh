#!/bin/bash
# Deployment script for QuantAgent

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== QuantAgent Deployment ===${NC}"

# Package the application
echo -e "${YELLOW}Creating deployment package...${NC}"
tar -czf quantagent-deploy.tar.gz \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='quantagent-deploy.tar.gz' \
    .

echo -e "${GREEN}✓ Package created: quantagent-deploy.tar.gz${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Copy package to server: scp quantagent-deploy.tar.gz user@server:/path/to/deploy/"
echo "2. SSH to server and run setup commands (see README_DEPLOY.md)"
echo ""
echo -e "${YELLOW}Quick deploy command:${NC}"
echo "scp quantagent-deploy.tar.gz user@YOUR_SERVER:/opt/quantagent/"
