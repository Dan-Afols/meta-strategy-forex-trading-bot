#!/bin/bash
# ============================================================
# Forex Trading Bot — Server Management Script
# Usage: sudo bash deploy/manage.sh [command]
# ============================================================
set -euo pipefail

APP_DIR="/opt/trade_fx"
SERVICES=("xvfb" "mt5-terminal" "forex-trading" "forex-dashboard")

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

case "${1:-help}" in

    start)
        echo -e "${GREEN}Starting all services...${NC}"
        for svc in "${SERVICES[@]}"; do
            systemctl start "$svc"
            echo "  ✓ $svc started"
            [ "$svc" = "mt5-terminal" ] && { echo "  ⏳ Waiting 15s for MT5 init..."; sleep 15; }
        done
        echo -e "${GREEN}All services started!${NC}"
        ;;

    stop)
        echo -e "${YELLOW}Stopping all services...${NC}"
        for svc in $(echo "${SERVICES[@]}" | tr ' ' '\n' | tac); do
            systemctl stop "$svc" 2>/dev/null || true
            echo "  ✓ $svc stopped"
        done
        echo -e "${YELLOW}All services stopped.${NC}"
        ;;

    restart)
        echo -e "${YELLOW}Restarting trading bot...${NC}"
        systemctl restart forex-trading
        echo -e "${GREEN}Bot restarted!${NC}"
        ;;

    restart-all)
        echo -e "${YELLOW}Restarting all services...${NC}"
        $0 stop
        sleep 3
        $0 start
        ;;

    status)
        echo "═══════════════════════════════════════"
        echo " Service Status"
        echo "═══════════════════════════════════════"
        for svc in "${SERVICES[@]}"; do
            STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "inactive")
            if [ "$STATUS" = "active" ]; then
                echo -e "  ${GREEN}●${NC} $svc: ${GREEN}$STATUS${NC}"
            else
                echo -e "  ${RED}●${NC} $svc: ${RED}$STATUS${NC}"
            fi
        done
        echo ""
        echo " Health check:"
        HEALTH=$(curl -s http://localhost/health 2>/dev/null || echo '{"status":"unreachable"}')
        echo "  $HEALTH"
        echo ""
        echo " Memory usage:"
        free -h | head -2
        echo ""
        echo " Disk usage:"
        df -h / | tail -1
        ;;

    logs)
        echo "Showing trading bot logs (Ctrl+C to exit)..."
        journalctl -u forex-trading -f --no-hostname
        ;;

    logs-mt5)
        echo "Showing MT5 terminal logs (Ctrl+C to exit)..."
        journalctl -u mt5-terminal -f --no-hostname
        ;;

    logs-dashboard)
        echo "Showing dashboard logs (Ctrl+C to exit)..."
        journalctl -u forex-dashboard -f --no-hostname
        ;;

    logs-all)
        echo "Showing all service logs (Ctrl+C to exit)..."
        journalctl -u forex-trading -u mt5-terminal -u forex-dashboard -f --no-hostname
        ;;

    update)
        echo -e "${YELLOW}Updating application code...${NC}"
        if [ -d "$APP_DIR/.git" ]; then
            cd "$APP_DIR"
            sudo -u trader git pull
        else
            echo "Not a git repo. Copy new files to $APP_DIR manually."
            exit 1
        fi
        echo -e "${YELLOW}Restarting services...${NC}"
        systemctl restart forex-trading
        echo -e "${GREEN}Update complete!${NC}"
        ;;

    backup)
        BACKUP_FILE="/home/trader/backup_$(date +%Y%m%d_%H%M%S).tar.gz"
        echo -e "${YELLOW}Creating backup...${NC}"
        tar -czf "$BACKUP_FILE" \
            -C "$APP_DIR" data/ logs/ .env ml_models/saved/ 2>/dev/null || true
        chown trader:trader "$BACKUP_FILE"
        echo -e "${GREEN}Backup saved: $BACKUP_FILE${NC}"
        ls -lh "$BACKUP_FILE"
        ;;

    env)
        echo "Opening .env file for editing..."
        ${EDITOR:-nano} "$APP_DIR/.env"
        echo -e "${YELLOW}Remember to restart: sudo bash $0 restart${NC}"
        ;;

    health)
        curl -s http://localhost/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "Health check failed"
        ;;

    ssl)
        if [ -z "${2:-}" ]; then
            echo "Usage: $0 ssl yourdomain.com"
            exit 1
        fi
        DOMAIN="$2"
        echo -e "${YELLOW}Setting up SSL for $DOMAIN...${NC}"
        # Update nginx server_name
        sed -i "s/server_name _;/server_name $DOMAIN;/" /etc/nginx/sites-available/forex-trading
        nginx -t && systemctl reload nginx
        certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN" || {
            echo -e "${RED}Certbot failed. Make sure DNS points to this server.${NC}"
            exit 1
        }
        echo -e "${GREEN}SSL enabled for $DOMAIN!${NC}"
        ;;

    help|*)
        echo ""
        echo "Forex Trading Bot — Server Management"
        echo ""
        echo "Usage: sudo bash deploy/manage.sh [command]"
        echo ""
        echo "Commands:"
        echo "  start         Start all services"
        echo "  stop          Stop all services"
        echo "  restart       Restart trading bot only"
        echo "  restart-all   Restart all services"
        echo "  status        Show service status + health check"
        echo "  logs          Follow trading bot logs"
        echo "  logs-mt5      Follow MT5 terminal logs"
        echo "  logs-dashboard Follow dashboard logs"
        echo "  logs-all      Follow all logs"
        echo "  update        Pull latest code and restart"
        echo "  backup        Backup data, logs, .env, models"
        echo "  env           Edit .env configuration"
        echo "  health        Quick health check"
        echo "  ssl DOMAIN    Set up HTTPS with Let's Encrypt"
        echo "  help          Show this help"
        echo ""
        ;;
esac
