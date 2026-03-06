#!/usr/bin/env python3
"""
Cron-Skript zur Überwachung und Wartung der Proxies
Wird alle 2 Stunden ausgeführt
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Tuple

# Füge src zum Pfad hinzu
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from proxy_manager import ProxyManager, WORKING_PROXIES_FILE

# Logging konfigurieren
LOGS_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'proxy_check.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Konstanten
MIN_PROXIES = 3  # Minimale Anzahl an Proxies


def setup_logging():
    """Richte Logging ein"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info("=" * 60)
    logger.info(f"Proxy-Check gestartet: {timestamp}")
    logger.info("=" * 60)


def check_and_maintain_proxies() -> Tuple[int, int, int]:
    """
    Hauptfunktion: Prüfe Proxies und hole neue wenn nötig
    
    Returns:
        Tuple[int, int, int]: (working_before, removed, added)
    """
    pm = ProxyManager(auto_fetch=False)
    
    # Aktuelle Anzahl
    working_before = len(pm.working_proxies)
    logger.info(f"Aktuell {working_before} gespeicherte Proxies")
    
    # Validiere alle Proxies
    still_working, dead_count = pm.validate_all_proxies()
    logger.info(f"{still_working} Proxies funktionieren, {dead_count} entfernt")
    
    # Prüfe ob neue Proxies nötig
    added = 0
    if still_working < MIN_PROXIES:
        logger.warning(f"Nur {still_working} Proxies verfügbar (< {MIN_PROXIES}), hole neue...")
        
        # Hole neue Proxies
        new_proxies = pm.fetch_proxies_from_sources()
        working_new = pm.test_proxies(new_proxies)
        
        # Füge neue hinzu
        existing = set(pm.working_proxies)
        for proxy in working_new:
            if proxy not in existing:
                pm.working_proxies.append(proxy)
                added += 1
        
        # Speichere
        pm._save_working_proxies()
        logger.info(f"{added} neue Proxies hinzugefügt")
    else:
        logger.info(f"Genügend Proxies verfügbar ({still_working} >= {MIN_PROXIES})")
    
    return working_before, dead_count, added


def log_result(working_before: int, removed: int, added: int):
    """Logge Ergebnis"""
    working_now = working_before - removed + added
    
    logger.info("=" * 60)
    logger.info("Proxy-Check abgeschlossen:")
    logger.info(f"  Vorher: {working_before} Proxies")
    logger.info(f"  Entfernt: {removed} Proxies")
    logger.info(f"  Hinzugefügt: {added} Proxies")
    logger.info(f"  Jetzt: {working_now} Proxies")
    logger.info("=" * 60)
    
    # Speichere auch als JSON für Monitoring
    result = {
        'timestamp': datetime.now().isoformat(),
        'working_before': working_before,
        'removed': removed,
        'added': added,
        'working_now': working_now,
        'status': 'ok' if working_now >= MIN_PROXIES else 'warning'
    }
    
    result_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'proxy_check_result.json')
    try:
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2)
    except Exception as e:
        logger.error(f"Fehler beim Speichern des Ergebnisses: {e}")


def main():
    """Hauptfunktion"""
    setup_logging()
    
    try:
        working_before, removed, added = check_and_maintain_proxies()
        log_result(working_before, removed, added)
        
        # Exit-Code basierend auf Ergebnis
        working_now = working_before - removed + added
        if working_now < MIN_PROXIES:
            logger.error(f"KRITISCH: Nur {working_now} Proxies verfügbar!")
            sys.exit(1)
        else:
            logger.info(f"OK: {working_now} Proxies verfügbar")
            sys.exit(0)
            
    except Exception as e:
        logger.exception(f"Fehler beim Proxy-Check: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
