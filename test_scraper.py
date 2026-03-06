#!/usr/bin/env python3
"""
Schneller Test des Domain Scrapers
"""

import sys
sys.path.insert(0, '/root/.openclaw/workspace/projects/domain-flipper/src')

from scraper import DomainScraper

print("=" * 60)
print("Domain Scraper - Schnelltest")
print("=" * 60)

scraper = DomainScraper()
stats = scraper.get_stats()

print(f"\nAktuelle Datenbank-Statistik:")
print(f"  - Gesamte Domains: {stats['total_domains']}")
print(f"  - Nach Quelle: {stats['by_source']}")

print("\nDatenbank und Scraper sind bereit!")
print("\nUm den vollständigen Scraper zu starten:")
print("  python3 src/scraper.py")
print("\nCronjob einrichten (alle 6 Stunden):")
print("  crontab -e")
print("  0 */6 * * * /root/.openclaw/workspace/projects/domain-flipper/cron/run_scraper.sh")
