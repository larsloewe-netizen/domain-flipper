#!/bin/bash
# Domain Scraper Cron Script
# Dieses Script wird alle 6 Stunden ausgeführt
# 
# CRON Eintrag (crontab -e):
# 0 */6 * * * /root/.openclaw/workspace/projects/domain-flipper/cron/run_scraper.sh >> /root/.openclaw/workspace/projects/domain-flipper/data/scraper.log 2>&1

PROJECT_DIR="/root/.openclaw/workspace/projects/domain-flipper"
PYTHON="/usr/bin/python3"

echo "========================================"
echo "Domain Scraper - $(date)"
echo "========================================"

# Ins Projektverzeichnis wechseln
cd "$PROJECT_DIR" || exit 1

# Python-Umgebung prüfen
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

# Abhängigkeiten prüfen
echo "Prüfe Abhängigkeiten..."
$PYTHON -c "import requests, bs4" 2>/dev/null || {
    echo "Installiere fehlende Abhängigkeiten..."
    pip3 install -r requirements.txt --quiet
}

# Scraper ausführen
echo "Starte Scraper..."
$PYTHON src/scraper.py

EXIT_CODE=$?

echo "Exit Code: $EXIT_CODE"
echo "Fertig: $(date)"
echo ""

exit $EXIT_CODE
