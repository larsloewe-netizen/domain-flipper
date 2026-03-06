#!/usr/bin/env python3
"""
Cron-Skript für Full Scrape mit Proxies
Wird alle 6 Stunden ausgeführt
"""

import os
import sys
import json
import logging
from datetime import datetime

# Füge src zum Pfad hinzu
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from scraper import run

# Logging konfigurieren
LOGS_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'full_scrape.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def setup_logging():
    """Richte Logging ein"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info("=" * 70)
    logger.info(f"Full Scrape gestartet: {timestamp}")
    logger.info("=" * 70)


def run_full_scrape():
    """
    Führe Full Scrape mit Proxies durch
    """
    try:
        # Scrape mit Free Proxies
        count = run(
            use_free_proxies=True,
            test_mode=False,
            timeout=15,
            min_delay=2.0,
            max_delay=5.0,
            proxy_rotation_limit=5  # Häufigere Rotation bei vielen Requests
        )
        
        return count
        
    except Exception as e:
        logger.exception(f"Fehler beim Full Scrape: {e}")
        return 0


def log_result(count: int):
    """Logge Ergebnis"""
    status = 'ok' if count > 0 else 'warning'
    
    logger.info("=" * 70)
    logger.info("Full Scrape abgeschlossen:")
    logger.info(f"  Domains gefunden: {count}")
    logger.info(f"  Status: {status}")
    logger.info("=" * 70)
    
    # Speichere auch als JSON für Monitoring
    result = {
        'timestamp': datetime.now().isoformat(),
        'domains_found': count,
        'status': status
    }
    
    result_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'full_scrape_result.json')
    try:
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2)
    except Exception as e:
        logger.error(f"Fehler beim Speichern des Ergebnisses: {e}")


def main():
    """Hauptfunktion"""
    setup_logging()
    
    count = run_full_scrape()
    log_result(count)
    
    # Exit-Code
    if count > 0:
        logger.info(f"OK: {count} Domains gefunden")
        sys.exit(0)
    else:
        logger.warning("Keine Domains gefunden")
        sys.exit(1)


if __name__ == "__main__":
    main()
