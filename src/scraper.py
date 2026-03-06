#!/usr/bin/env python3
"""
Domain Scraper für Domain-Flipping Projekt
Sammelt expired Domains von verschiedenen Quellen
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import json
import re
import time
import random
from datetime import datetime
from urllib.parse import urljoin, urlparse
import os
import logging

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Konstanten
DB_PATH = "/root/.openclaw/workspace/projects/domain-flipper/data/expired_domains.db"
DATA_DIR = "/root/.openclaw/workspace/projects/domain-flipper/data"

# User Agents für Rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]


class DomainScraper:
    def __init__(self):
        self.session = requests.Session()
        self.domains = []
        self._init_db()
    
    def _get_headers(self):
        """Zufälligen User-Agent zurückgeben"""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
        }
    
    def _init_db(self):
        """SQLite Datenbank initialisieren"""
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain_name TEXT NOT NULL,
                tld TEXT NOT NULL,
                age_years INTEGER,
                backlinks INTEGER,
                estimated_traffic INTEGER,
                price TEXT,
                auction_status TEXT,
                domain_authority INTEGER,
                page_authority INTEGER,
                source TEXT NOT NULL,
                auction_url TEXT,
                expiry_date TEXT,
                first_seen TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                UNIQUE(domain_name, source)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scrape_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scrape_time TEXT NOT NULL,
                source TEXT NOT NULL,
                domains_found INTEGER,
                domains_new INTEGER,
                error TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Datenbank initialisiert")
    
    def _save_domain(self, domain_data):
        """Domain in Datenbank speichern"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        try:
            cursor.execute('''
                INSERT INTO domains 
                (domain_name, tld, age_years, backlinks, estimated_traffic, price, 
                 auction_status, domain_authority, page_authority, source, auction_url,
                 expiry_date, first_seen, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain_name, source) DO UPDATE SET
                age_years=excluded.age_years,
                backlinks=excluded.backlinks,
                estimated_traffic=excluded.estimated_traffic,
                price=excluded.price,
                auction_status=excluded.auction_status,
                domain_authority=excluded.domain_authority,
                page_authority=excluded.page_authority,
                auction_url=excluded.auction_url,
                expiry_date=excluded.expiry_date,
                last_updated=excluded.last_updated
            ''', (
                domain_data['domain_name'],
                domain_data['tld'],
                domain_data.get('age_years'),
                domain_data.get('backlinks'),
                domain_data.get('estimated_traffic'),
                domain_data.get('price'),
                domain_data.get('auction_status'),
                domain_data.get('domain_authority'),
                domain_data.get('page_authority'),
                domain_data['source'],
                domain_data.get('auction_url'),
                domain_data.get('expiry_date'),
                now, now
            ))
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")
            return 0
        finally:
            conn.close()
    
    def _log_scrape(self, source, found, new, error=None):
        """Scrape-Vorgang loggen"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO scrape_log (scrape_time, source, domains_found, domains_new, error)
            VALUES (?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), source, found, new, error))
        conn.commit()
        conn.close()
    
    def _extract_tld(self, domain):
        """TLD aus Domain extrahieren"""
        parts = domain.split('.')
        return '.' + '.'.join(parts[1:]) if len(parts) > 1 else '.com'
    
    def scrape_expired_domains_net(self, limit=100):
        """
        ExpiredDomains.net scrapen
        Diese Seite hat verschiedene Listen für deleted/expired domains
        """
        logger.info("Scraping ExpiredDomains.net...")
        domains_found = []
        new_count = 0
        
        # Verschiedene Listen-URLs
        list_urls = [
            "https://www.expireddomains.net/deleted-domains/",
            "https://www.expireddomains.net/expired-domains/",
        ]
        
        for list_url in list_urls:
            try:
                time.sleep(random.uniform(2, 5))  # Rate limiting
                
                response = self.session.get(list_url, headers=self._get_headers(), timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Tabelle mit Domains finden
                table = soup.find('table', {'class': 'base1'})
                if not table:
                    table = soup.find('table')
                
                if table:
                    rows = table.find_all('tr')[1:]  # Header überspringen
                    
                    for row in rows[:limit]:
                        cells = row.find_all('td')
                        if len(cells) >= 3:
                            domain_cell = cells[0].find('a')
                            if domain_cell:
                                domain_name = domain_cell.text.strip()
                                
                                # Alter extrahieren (wenn verfügbar)
                                age = None
                                if len(cells) > 2:
                                    age_text = cells[2].text.strip()
                                    age_match = re.search(r'(\d+)', age_text)
                                    if age_match:
                                        age = int(age_match.group(1))
                                
                                # Backlinks (wenn verfügbar)
                                backlinks = None
                                if len(cells) > 5:
                                    bl_text = cells[5].text.strip().replace(',', '')
                                    try:
                                        backlinks = int(bl_text)
                                    except:
                                        pass
                                
                                domain_data = {
                                    'domain_name': domain_name,
                                    'tld': self._extract_tld(domain_name),
                                    'age_years': age,
                                    'backlinks': backlinks,
                                    'source': 'expireddomains.net',
                                    'auction_status': 'deleted'
                                }
                                
                                domains_found.append(domain_data)
                                if self._save_domain(domain_data):
                                    new_count += 1
                
            except Exception as e:
                logger.error(f"Fehler beim Scraping von {list_url}: {e}")
                continue
        
        self._log_scrape('expireddomains.net', len(domains_found), new_count)
        logger.info(f"ExpiredDomains.net: {len(domains_found)} Domains gefunden, {new_count} neu")
        return domains_found
    
    def scrape_dynadot(self, limit=50):
        """
        Dynadot Expired Auctions scrapen
        """
        logger.info("Scraping Dynadot Expired Auctions...")
        domains_found = []
        new_count = 0
        
        url = "https://www.dynadot.com/market/expired-domain-auction.html"
        
        try:
            time.sleep(random.uniform(2, 5))
            
            response = self.session.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Domain-Items finden
            domain_items = soup.find_all('div', class_=re.compile('domain|auction|listing', re.I))
            
            for item in domain_items[:limit]:
                try:
                    # Domain-Name
                    domain_link = item.find('a', href=re.compile('auction|domain', re.I))
                    if not domain_link:
                        continue
                    
                    domain_name = domain_link.text.strip()
                    auction_url = urljoin(url, domain_link.get('href', ''))
                    
                    # Preis finden
                    price_elem = item.find(text=re.compile(r'\$[\d,]+'))
                    price = price_elem.strip() if price_elem else None
                    
                    domain_data = {
                        'domain_name': domain_name,
                        'tld': self._extract_tld(domain_name),
                        'price': price,
                        'auction_status': 'active',
                        'source': 'dynadot',
                        'auction_url': auction_url
                    }
                    
                    domains_found.append(domain_data)
                    if self._save_domain(domain_data):
                        new_count += 1
                        
                except Exception as e:
                    continue
            
            # Alternative: JSON API fallback
            if len(domains_found) == 0:
                logger.info("Versuche Dynadot API-Endpoint...")
                api_url = "https://api.dynadot.com/api3.json"
                # Hier könnte ein API-Call erfolgen, wenn API-Key verfügbar
                
        except Exception as e:
            logger.error(f"Fehler beim Scraping von Dynadot: {e}")
        
        self._log_scrape('dynadot', len(domains_found), new_count)
        logger.info(f"Dynadot: {len(domains_found)} Domains gefunden, {new_count} neu")
        return domains_found
    
    def scrape_namecheap(self, limit=50):
        """
        Namecheap Marketplace scrapen
        """
        logger.info("Scraping Namecheap Marketplace...")
        domains_found = []
        new_count = 0
        
        url = "https://www.namecheap.com/market/"
        
        try:
            time.sleep(random.uniform(2, 5))
            
            response = self.session.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Suche nach Domain-Listings
            listings = soup.find_all(['div', 'tr', 'article'], class_=re.compile('listing|domain|item', re.I))
            
            for listing in listings[:limit]:
                try:
                    # Domain-Name extrahieren
                    domain_elem = listing.find(text=re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}$'))
                    if not domain_elem:
                        domain_link = listing.find('a', href=re.compile('domain', re.I))
                        if domain_link:
                            domain_elem = domain_link.text.strip()
                    
                    if domain_elem and isinstance(domain_elem, str):
                        domain_name = domain_elem.strip()
                        
                        # Preis
                        price_elem = listing.find(text=re.compile(r'\$[\d,]+\.?\d*'))
                        price = price_elem.strip() if price_elem else None
                        
                        domain_data = {
                            'domain_name': domain_name,
                            'tld': self._extract_tld(domain_name),
                            'price': price,
                            'auction_status': 'listed',
                            'source': 'namecheap'
                        }
                        
                        domains_found.append(domain_data)
                        if self._save_domain(domain_data):
                            new_count += 1
                            
                except Exception as e:
                    continue
                    
        except Exception as e:
            logger.error(f"Fehler beim Scraping von Namecheap: {e}")
        
        self._log_scrape('namecheap', len(domains_found), new_count)
        logger.info(f"Namecheap: {len(domains_found)} Domains gefunden, {new_count} neu")
        return domains_found
    
    def scrape_godaddy(self, limit=50):
        """
        GoDaddy Auctions scrapen
        """
        logger.info("Scraping GoDaddy Auctions...")
        domains_found = []
        new_count = 0
        
        # GoDaddy Auctions erfordert Login für vollständigen Zugriff
        # Wir versuchen die öffentlich verfügbaren Seiten
        url = "https://auctions.godaddy.com/"
        
        try:
            time.sleep(random.uniform(2, 5))
            
            response = self.session.get(url, headers=self._get_headers(), timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Suche nach Domain-Listings
                listings = soup.find_all(['div', 'tr'], class_=re.compile('listing|auction|domain', re.I))
                
                for listing in listings[:limit]:
                    try:
                        domain_elem = listing.find(text=re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-]*\.[a-zA-Z]{2,}$'))
                        if domain_elem:
                            domain_name = domain_elem.strip()
                            
                            price_elem = listing.find(text=re.compile(r'\$[\d,]+'))
                            price = price_elem.strip() if price_elem else None
                            
                            domain_data = {
                                'domain_name': domain_name,
                                'tld': self._extract_tld(domain_name),
                                'price': price,
                                'auction_status': 'auction',
                                'source': 'godaddy'
                            }
                            
                            domains_found.append(domain_data)
                            if self._save_domain(domain_data):
                                new_count += 1
                                
                    except Exception:
                        continue
                        
        except Exception as e:
            logger.error(f"Fehler beim Scraping von GoDaddy: {e}")
        
        self._log_scrape('godaddy', len(domains_found), new_count)
        logger.info(f"GoDaddy: {len(domains_found)} Domains gefunden, {new_count} neu")
        return domains_found
    
    def run_all_scrapers(self):
        """Alle Scraper ausführen"""
        logger.info("=" * 60)
        logger.info("Starte Domain-Scraping...")
        logger.info(f"Zeit: {datetime.now().isoformat()}")
        logger.info("=" * 60)
        
        total_domains = 0
        total_new = 0
        
        # ExpiredDomains.net
        try:
            domains = self.scrape_expired_domains_net(limit=100)
            total_domains += len(domains)
        except Exception as e:
            logger.error(f"ExpiredDomains.net scraper failed: {e}")
        
        # Dynadot
        try:
            domains = self.scrape_dynadot(limit=50)
            total_domains += len(domains)
        except Exception as e:
            logger.error(f"Dynadot scraper failed: {e}")
        
        # Namecheap
        try:
            domains = self.scrape_namecheap(limit=50)
            total_domains += len(domains)
        except Exception as e:
            logger.error(f"Namecheap scraper failed: {e}")
        
        # GoDaddy (optional)
        try:
            domains = self.scrape_godaddy(limit=50)
            total_domains += len(domains)
        except Exception as e:
            logger.error(f"GoDaddy scraper failed: {e}")
        
        logger.info("=" * 60)
        logger.info(f"Scraping abgeschlossen!")
        logger.info(f"Gesamt: {total_domains} Domains verarbeitet")
        logger.info("=" * 60)
        
        return total_domains
    
    def get_stats(self):
        """Statistiken aus der Datenbank abrufen"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM domains")
        total_domains = cursor.fetchone()[0]
        
        cursor.execute("SELECT source, COUNT(*) FROM domains GROUP BY source")
        by_source = cursor.fetchall()
        
        cursor.execute("""
            SELECT source, domains_found, domains_new, scrape_time 
            FROM scrape_log 
            ORDER BY scrape_time DESC 
            LIMIT 10
        """)
        recent_logs = cursor.fetchall()
        
        conn.close()
        
        return {
            'total_domains': total_domains,
            'by_source': by_source,
            'recent_logs': recent_logs
        }


def main():
    """Hauptfunktion"""
    scraper = DomainScraper()
    
    # Optional: Statistiken vor dem Scraping anzeigen
    stats = scraper.get_stats()
    logger.info(f"Aktuelle Datenbank-Statistik: {stats['total_domains']} Domains gespeichert")
    
    # Alle Scraper ausführen
    total = scraper.run_all_scrapers()
    
    # Aktualisierte Statistiken
    stats = scraper.get_stats()
    logger.info(f"Neue Gesamtstatistik: {stats['total_domains']} Domains in Datenbank")
    
    return total


if __name__ == "__main__":
    main()


def run():
    """Hauptfunktion für main.py Integration"""
    logger.info("Starte Domain Scraper...")
    scraper = DomainScraper()
    count = scraper.run_all_scrapers()
    logger.info(f"Scraper fertig. {count} Domains gefunden.")
    return count
