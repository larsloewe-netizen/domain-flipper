#!/usr/bin/env python3
"""
Domain Flipper - Main Runner
Kombiniert Scraper, Valuator und Checker zu einem Workflow.
"""

import sys
import os
import sqlite3
import logging
import traceback
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import DB_PATH, TOP_N_DOMAINS, REPORT_OUTPUT_PATH

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'logs', 'main.log'))
    ]
)
logger = logging.getLogger(__name__)


def init_database():
    """Initialisiert die SQLite-Datenbank."""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain_name TEXT UNIQUE NOT NULL,
                tld TEXT,
                age_days INTEGER,
                backlinks INTEGER,
                authority_score INTEGER,
                current_price REAL,
                auction_status TEXT,
                valuation_score INTEGER,
                estimated_sell_price REAL,
                status TEXT DEFAULT 'new',
                found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_domains INTEGER,
                high_potential_count INTEGER,
                top_domain TEXT,
                top_score INTEGER
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scrape_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT,
                domain TEXT,
                error_message TEXT,
                traceback TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"✓ Datenbank initialisiert: {DB_PATH}")
        return True
    except Exception as e:
        logger.error(f"✗ Datenbank-Initialisierung fehlgeschlagen: {e}")
        logger.error(traceback.format_exc())
        return False


def log_scrape_error(source, domain, error_message):
    """Loggt Parser-Fehler in die Datenbank."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO scrape_errors (source, domain, error_message, traceback)
            VALUES (?, ?, ?, ?)
        ''', (source, domain, error_message, traceback.format_exc()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Konnte Fehler nicht loggen: {e}")


def run_scraper():
    """Führt den Domain-Scraper aus."""
    print("\n=== SCRAPER ===")
    logger.info("Starte Scraper...")
    
    try:
        import scraper
        count = scraper.run(test_mode=False)
        logger.info(f"Scraper abgeschlossen. {count} Domains gefunden.")
        return count
    except Exception as e:
        error_msg = f"Scraper-Fehler: {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        log_scrape_error('scraper', None, str(e))
        return 0


def run_valuator():
    """Führt die Bewertung aus."""
    print("\n=== VALUATOR ===")
    logger.info("Starte Valuator...")
    
    try:
        import valuator
        valuator.run()
        logger.info("Valuator abgeschlossen.")
        return True
    except Exception as e:
        error_msg = f"Valuator-Fehler: {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        log_scrape_error('valuator', None, str(e))
        return False


def run_checker():
    """Führt Domain-Checks aus."""
    print("\n=== CHECKER ===")
    logger.info("Starte Checker...")
    
    try:
        import domain_checker
        domain_checker.run()
        logger.info("Checker abgeschlossen.")
        return True
    except Exception as e:
        error_msg = f"Checker-Fehler: {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        log_scrape_error('checker', None, str(e))
        return False


def generate_report():
    """Generiert den Daily Report."""
    print("\n=== REPORT ===")
    logger.info("Generiere Report...")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Top Domains
        cursor.execute('''
            SELECT domain_name, tld, current_price, valuation_score, estimated_sell_price
            FROM domains
            WHERE valuation_score >= 70
            ORDER BY valuation_score DESC, estimated_sell_price DESC
            LIMIT ?
        ''', (TOP_N_DOMAINS,))
        
        top_domains = cursor.fetchall()
        
        # Statistiken
        cursor.execute('SELECT COUNT(*) FROM domains WHERE DATE(found_at) = DATE("now")')
        total_today = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM domains WHERE valuation_score >= 70')
        high_potential = cursor.fetchone()[0]
        
        # Letzte Fehler
        cursor.execute('''
            SELECT COUNT(*) FROM scrape_errors 
            WHERE DATE(error_time) = DATE("now")
        ''')
        error_count = cursor.fetchone()[0]
        
        # Report schreiben
        report_lines = [
            f"Domain Flipper - Daily Report",
            f"Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"Statistiken:",
            f"- Neue Domains heute: {total_today}",
            f"- High Potential Gesamt: {high_potential}",
            f"- Parser-Fehler heute: {error_count}",
            f"",
            f"Top {TOP_N_DOMAINS} Domains:",
            f"{'Domain':<30} {'TLD':<6} {'Preis':<10} {'Score':<8} {'Sell-Preis':<10}",
            f"{'-'*70}",
        ]
        
        for domain in top_domains:
            name, tld, price, score, sell_price = domain
            report_lines.append(
                f"{name:<30} {tld:<6} ${price or 0:<9.2f} {score or 0:<8} ${sell_price or 0:<9.2f}"
            )
        
        # Letzte Fehler anzeigen (wenn vorhanden)
        if error_count > 0:
            report_lines.extend([
                f"",
                f"Letzte Fehler:",
                f"{'-'*70}",
            ])
            cursor.execute('''
                SELECT source, domain, error_message 
                FROM scrape_errors 
                WHERE DATE(error_time) = DATE("now")
                ORDER BY error_time DESC
                LIMIT 5
            ''')
            for row in cursor.fetchall():
                report_lines.append(f"- {row[0]} | {row[1] or 'N/A'} | {row[2][:50]}...")
        
        report_text = "\n".join(report_lines)
        
        # Speichern
        os.makedirs(os.path.dirname(REPORT_OUTPUT_PATH), exist_ok=True)
        with open(REPORT_OUTPUT_PATH, 'w') as f:
            f.write(report_text)
        
        print(report_text)
        print(f"\n✓ Report gespeichert: {REPORT_OUTPUT_PATH}")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Report-Generierung fehlgeschlagen: {e}")
        logger.error(traceback.format_exc())
        return False


def show_recent_domains(limit=10):
    """Zeigt die neuesten geparsten Domains."""
    print(f"\n=== LETZTE {limit} DOMAINS ===")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT domain_name, tld, source, found_at
            FROM domains
            ORDER BY found_at DESC
            LIMIT ?
        ''', (limit,))
        
        domains = cursor.fetchall()
        conn.close()
        
        print(f"{'Domain':<35} {'TLD':<8} {'Source':<20} {'Zeit'}")
        print("-" * 80)
        
        for d in domains:
            domain, tld, source, found_at = d
            # Prüfe auf doppelte TLDs
            status = "✓" if ".." not in domain else "✗ DOPPELTLD!"
            print(f"{domain:<35} {tld:<8} {source:<20} {status}")
        
        return domains
        
    except Exception as e:
        logger.error(f"Fehler beim Anzeigen der Domains: {e}")
        return []


def main():
    """Haupt-Workflow."""
    print("=" * 60)
    print("Domain Flipper MVP")
    print("=" * 60)
    
    # Init
    if not init_database():
        print("✗ Datenbank-Initialisierung fehlgeschlagen. Abbruch.")
        return
    
    # Workflow
    try:
        run_scraper()
        run_checker()
        run_valuator()
        generate_report()
        
        # Zeige die letzten geparsten Domains
        show_recent_domains(10)
        
    except KeyboardInterrupt:
        logger.info("Abbruch durch Benutzer.")
    except Exception as e:
        logger.error(f"Unbekannter Fehler im Workflow: {e}")
        logger.error(traceback.format_exc())
    
    print("\n" + "=" * 60)
    print("✓ Durchlauf abgeschlossen")
    print("=" * 60)


if __name__ == "__main__":
    main()
