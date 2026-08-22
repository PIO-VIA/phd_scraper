#!/usr/bin/env bash
set -e

# Colors for terminal output
GREEN='\033[0;32m'
NC='\033[0m' # No Color
YELLOW='\033[1;33m'
CYAN='\033[0;36m'

echo -e "${CYAN}====================================================${NC}"
echo -e "${CYAN}   🚀 PhD Scraper — Contabo VPS Automated Deploy   ${NC}"
echo -e "${CYAN}====================================================${NC}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 1. Environment file setup
if [ ! -f .env ]; then
    echo -e "${YELLOW}[!] .env file not found. Creating from .env.example...${NC}"
    cp .env.example .env
    echo -e "${GREEN}[✓] Created .env file.${NC}"
    echo -e "${YELLOW}[!] IMPORTANT: Please edit .env with your Telegram BOT token and CHAT ID before running scan!${NC}"
else
    echo -e "${GREEN}[✓] .env file exists.${NC}"
fi

# Create data and logs directory
mkdir -p data logs

# 2. Deployment Mode Selection
echo ""
echo -e "${CYAN}Select deployment method:${NC}"
echo "  1) System Python 3 + Virtualenv + Crontab / Systemd (Recommended - Low footprint)"
echo "  2) Docker Compose"
read -p "Choice [1/2] (default: 1): " CHOICE
CHOICE=${CHOICE:-1}

if [ "$CHOICE" = "1" ]; then
    echo -e "\n${CYAN}--- Mode 1: Python Virtualenv ---${NC}"
    
    # Check Python 3
    if ! command -v python3 &> /dev/null; then
        echo "[!] python3 could not be found. Installing python3, python3-venv, python3-pip..."
        sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
    fi

    # Create virtualenv if not exists
    if [ ! -d .venv ]; then
        echo -e "${YELLOW}[+] Creating virtual environment in .venv...${NC}"
        python3 -m venv .venv
    fi

    # Install requirements
    echo -e "${YELLOW}[+] Installing Python dependencies...${NC}"
    .venv/bin/pip install --upgrade pip -q
    .venv/bin/pip install -r requirements.txt -q

    echo -e "${GREEN}[✓] Dependencies installed successfully.${NC}"

    # Setup Cron or Systemd
    echo -e "\n${CYAN}Setup Scheduling:${NC}"
    echo "  a) Systemd Timer (Recommended for VPS)"
    echo "  b) User Crontab"
    echo "  c) Skip scheduling setup"
    read -p "Scheduling choice [a/b/c] (default: a): " SCHED_CHOICE
    SCHED_CHOICE=${SCHED_CHOICE:-a}

    if [ "$SCHED_CHOICE" = "a" ]; then
        echo -e "${YELLOW}[+] Installing Systemd timer...${NC}"
        # Copy unit files with proper working dir path
        SED_DIR=$(echo "$PROJECT_DIR" | sed 's/\//\\\//g')
        sed "s/\/opt\/phd-scraper/$SED_DIR/g" systemd/phd-scraper.service | sudo tee /etc/systemd/system/phd-scraper.service > /dev/null
        sudo cp systemd/phd-scraper.timer /etc/systemd/system/
        
        sudo systemctl daemon-reload
        sudo systemctl enable --now phd-scraper.timer
        echo -e "${GREEN}[✓] Systemd timer activated! Check status with: sudo systemctl status phd-scraper.timer${NC}"

    elif [ "$SCHED_CHOICE" = "b" ]; then
        CRON_CMD="0 7 * * * cd $PROJECT_DIR && $PROJECT_DIR/.venv/bin/python -m scraper.run scan >> $PROJECT_DIR/logs/cron.log 2>&1"
        (crontab -l 2>/dev/null | grep -v "phd-scraper" ; echo "$CRON_CMD") | crontab -
        echo -e "${GREEN}[✓] Added to crontab successfully (runs daily at 07:00).${NC}"
    fi

elif [ "$CHOICE" = "2" ]; then
    echo -e "\n${CYAN}--- Mode 2: Docker Compose ---${NC}"
    if ! command -v docker &> /dev/null; then
        echo -e "${YELLOW}[!] Docker not found. Installing docker & docker-compose plugin...${NC}"
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        rm get-docker.sh
    fi

    echo -e "${YELLOW}[+] Building Docker container...${NC}"
    docker compose build

    echo -e "${GREEN}[✓] Docker image built successfully.${NC}"
    echo -e "${CYAN}To run scan manually via Docker:${NC}"
    echo "  docker compose run --rm phd-scraper scan"
    
    # Adding cron entry for Docker
    CRON_CMD="0 7 * * * cd $PROJECT_DIR && docker compose run --rm phd-scraper scan >> $PROJECT_DIR/logs/cron.log 2>&1"
    (crontab -l 2>/dev/null | grep -v "phd-scraper" ; echo "$CRON_CMD") | crontab -
    echo -e "${GREEN}[✓] Crontab entry added for Docker execution daily at 07:00.${NC}"
fi

echo -e "\n${GREEN}====================================================${NC}"
echo -e "${GREEN} 🎉 Deployment setup completed successfully!        ${NC}"
echo -e "${GREEN}====================================================${NC}"
echo -e "To test your Telegram bot notification:"
echo -e "  ${CYAN}.venv/bin/python -m scraper.run test-notify${NC} (Native)"
echo -e "  or ${CYAN}docker compose run --rm phd-scraper test-notify${NC} (Docker)"
