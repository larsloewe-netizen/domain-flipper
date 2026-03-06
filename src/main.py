#!/usr/bin/env python3
"""
Domain Flipper - Main Runner
Kombiniert Scraper, Valuator und Checker zu einem Workflow.
"""

import sys
import os
import sqlite3
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import DB_PATH, TOP_N_DOMAINS, REPORT_OUTPUT_PATH


def init_database():
    """Initialisiert die SQLite-Datenbank."""
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
    
    conn.commit()
    conn.close()
    print(f"✓ Datenbank initialisiert: {DB_PATH}")


def run_scraper():
    """Führt den Domain-Scraper aus."""
    print("\n=== SCRAPER ===")
    # Wird vom Sub-Agent domain-scraper implementiert
    try:
        import scraper
        scraper.run()
    except Exception as e:
        print(f"Scraper-Fehler: {e}")


def run_valuator():
    """Führt die Bewertung aus."""
    print("\n=== VALUATOR ===")
    try:
        import valuator
        valuator.run()
    except Exception as e:
        print(f"Valuator-Fehler: {e}")


def run_checker():
    """Führt Domain-Checks aus."""
    print("\n=== CHECKER ===")
    try:
        import domain_checker
        domain_checker.run()
    except Exception as e:
        print(f"Checker-Fehler: {e}")


def generate_report():
    """Generiert den Daily Report."""
    print("\n=== REPORT ===")
    
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
    
    # Report schreiben
    report_lines = [
        f"Domain Flipper - Daily Report",
        f"Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"Statistiken:",
        f"- Neue Domains heute: {total_today}",
        f"- High Potential Gesamt: {high_potential}",
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
    
    report_text = "\n".join(report_lines)
    
    # Speichern
    os.makedirs(os.path.dirname(REPORT_OUTPUT_PATH), exist_ok=True)
    with open(REPORT_OUTPUT_PATH, 'w') as f:
        f.write(report_text)
    
    print(report_text)
    print(f"\n✓ Report gespeichert: {REPORT_OUTPUT_PATH}")
    
    conn.close()


def main():
    """Haupt-Workflow."""
    print("=" * 60)
    print("Domain Flipper MVP")
    print("=" * 60)
    
    # Init
    init_database()
    
    # Workflow
    run_scraper()
    run_checker()
    run_valuator()
    generate_report()
    
    print("\n" + "=" * 60)
    print("✓ Durchlauf abgeschlossen")
    print("=" * 60)


if __name__ == "__main__":
    main()
