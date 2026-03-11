#!/usr/bin/env python3
"""
Lightweight Domain Scraper
==========================
Nur ExpiredDomains.net - schnell, stabil, ressourcenschonend.
Läuft in unter 60 Sekunden durch.
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import re
import time
import random
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

# Konstanten
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, "expired_domains.db")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

TLD_URLS = [
    ("com", "https://www.expireddomains.net/deleted-com-domains/"),
    ("de", "https://www.expireddomains.net/deleted-de-domains/"),
    ("io", "https://www.expireddomains.net/deleted-io-domains/"),
    ("ai", "https://www.expireddomains.net/deleted-ai-domains/"),
]


def init_database():
    """Verbindet zur existierenden Datenbank."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    return conn


def calculate_score(name: str, tld: str) -> int:
    """Berechnet einen einfachen Valuation-Score (0-100)."""
    score = 50
    
    # Länge
    if len(name) <= 5:
        score += 20
    elif len(name) <= 10:
        score += 10
    
    # Keywords
    keywords = ['ai', 'crypto', 'tech', 'app', 'io', 'cloud', 'data', 'smart', 'auto']
    for kw in keywords:
        if kw in name.lower():
            score += 5
    
    # TLD Bonus
    if tld in ['io', 'ai']:
        score += 10
    elif tld == 'com':
        score += 5
    
    return min(score, 100)


def scrape_tld(tld: str, url: str) -> List[Dict]:
    """Scrapt eine einzelne TLD von ExpiredDomains.net."""
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        domains = []
        
        # Finde die Domain-Tabelle
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                domain_cell = cells[0]
                link = domain_cell.find('a')
                if link:
                    domain_name = link.text.strip()
                    if domain_name and '.' in domain_name:
                        name = domain_name.split('.')[0]
                        domains.append({
                            'domain_name': name,
                            'tld': tld,
                            'valuation_score': calculate_score(name, tld),
                            'source': 'expireddomains.net'
                        })
        
        return domains[:25]  # Max 25 pro TLD
        
    except Exception as e:
        print(f"  ⚠️  Fehler bei {tld}: {e}")
        return []


def save_domains(conn, domains: List[Dict]) -> int:
    """Speichert Domains in die Datenbank."""
    cursor = conn.cursor()
    saved = 0
    now = datetime.now().isoformat()
    
    for d in domains:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO domains 
                (domain_name, tld, source, valuation_score, first_seen, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (d['domain_name'], d['tld'], d['source'], d['valuation_score'], now, now))
            
            if cursor.rowcount > 0:
                saved += 1
            else:
                # Domain existiert - last_updated aktualisieren
                cursor.execute('''
                    UPDATE domains 
                    SET last_updated = ? 
                    WHERE domain_name = ? AND tld = ?
                ''', (now, d['domain_name'], d['tld']))
                
        except Exception as e:
            pass
    
    conn.commit()
    return saved


def get_stats(conn) -> Dict:
    """Holt Datenbank-Statistiken."""
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM domains")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM domains WHERE valuation_score >= 90")
    high_potential = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM domains WHERE first_seen > datetime('now', '-1 day')")
    new_24h = cursor.fetchone()[0]
    
    return {
        'total': total,
        'high_potential': high_potential,
        'new_24h': new_24h
    }


def main():
    print("=" * 60)
    print("🚀 Lightweight Domain Scraper")
    print("=" * 60)
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Datenbank verbinden
    conn = init_database()
    stats_before = get_stats(conn)
    print(f"📊 Vorher: {stats_before['total']} Domains ({stats_before['high_potential']} High-Potential)")
    print()
    
    # Scraping
    all_domains = []
    for tld, url in TLD_URLS:
        print(f"🔍 Scrape .{tld}...", end=" ", flush=True)
        domains = scrape_tld(tld, url)
        all_domains.extend(domains)
        print(f"✓ {len(domains)} gefunden")
        time.sleep(0.5)  # Kurze Pause zwischen Requests
    
    print()
    
    # Speichern
    saved = save_domains(conn, all_domains)
    stats_after = get_stats(conn)
    
    print(f"💾 Gespeichert: {saved} neue Domains")
    print(f"📊 Nachher: {stats_after['total']} Domains ({stats_after['high_potential']} High-Potential)")
    print()
    
    # Top 5 anzeigen
    cursor = conn.cursor()
    cursor.execute('''
        SELECT domain_name, tld, valuation_score 
        FROM domains 
        ORDER BY first_seen DESC 
        LIMIT 5
    ''')
    recent = cursor.fetchall()
    
    if recent:
        print("🆕 Neueste Domains:")
        for name, tld, score in recent:
            print(f"   • {name}.{tld} ({score} Punkte)")
    
    conn.close()
    
    print()
    print(f"✅ Fertig: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
