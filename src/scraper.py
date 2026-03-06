#!/usr/bin/env python3
"""
Domain Scraper für Domain-Flipping Projekt
Sammelt expired Domains von verschiedenen Quellen

Verbesserungen v2.0:
- Proxy-Rotation mit Thread-Safety
- Retry-Logik mit Exponential Backoff
- Paralleles Scraping mit ThreadPoolExecutor
- Aktivierte Quellen: ExpiredDomains.net, Dynadot API, GoDaddy Auctions
- User-Agent Rotation (15+)
- Smartes Rate-Limiting
- Verbesserte Fehlerbehandlung
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import json
import re
import time
import random
import argparse
import logging
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import os
import sys
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'logs', 'scraper.log'))
    ]
)
logger = logging.getLogger(__name__)

# Konstanten
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
LOGS_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
DB_PATH = os.path.join(DATA_DIR, "expired_domains.db")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'scraper.yaml')

# Erweiterte User-Agent Liste (15 verschiedene realistische User-Agents)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Importiere den ProxyManager
try:
    from proxy_manager import ProxyManager, get_proxy_manager, WORKING_PROXIES_FILE
except ImportError:
    # Fallback wenn proxy_manager nicht verfügbar
    WORKING_PROXIES_FILE = os.path.join(DATA_DIR, 'working_proxies.json')
    
    class ProxyManager:
        def __init__(self, **kwargs):
            self.working_proxies = []
            self.proxy_list = kwargs.get('proxy_list', [])
            
        def get_proxy(self):
            if self.proxy_list:
                proxy = random.choice(self.proxy_list)
                return {'http': proxy, 'https': proxy}
            return None
            
        def mark_failed(self, proxy):
            pass
    
    def get_proxy_manager(**kwargs):
        return ProxyManager(**kwargs)


class RateLimiter:
    """Smartes Rate-Limiting mit variablen Delays"""
    
    def __init__(self, min_delay: float = 1.0, max_delay: float = 3.0, 
                 error_threshold: int = 5, pause_duration: int = 60):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.error_count = 0
        self.error_threshold = error_threshold
        self.pause_duration = pause_duration
        self.last_request_time = None
        self.consecutive_errors = 0
        self._lock = Lock()
    
    def wait(self):
        """Warte vor dem nächsten Request"""
        with self._lock:
            delay = random.uniform(self.min_delay, self.max_delay)
            
            if self.consecutive_errors > 3:
                delay *= 2
                logger.info(f"Erhöhte Pause wegen Fehlern: {delay:.2f}s")
            
            if self.error_count >= self.error_threshold:
                logger.warning(f"Zu viele Fehler ({self.error_count}). Pause für {self.pause_duration}s...")
                time.sleep(self.pause_duration)
                self.error_count = 0
            
            if self.last_request_time:
                time_since_last = (datetime.now() - self.last_request_time).total_seconds()
                if time_since_last < delay:
                    remaining = delay - time_since_last
                    time.sleep(remaining)
            
            self.last_request_time = datetime.now()
    
    def report_success(self):
        """Meldet einen erfolgreichen Request"""
        with self._lock:
            self.consecutive_errors = 0
    
    def report_error(self):
        """Meldet einen fehlgeschlagenen Request"""
        with self._lock:
            self.error_count += 1
            self.consecutive_errors += 1


class RetrySession:
    """Session mit Retry-Logik und Exponential Backoff"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0,
                 timeout: int = 10, proxy_manager: Optional[ProxyManager] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self.proxy_manager = proxy_manager
        self.rate_limiter = rate_limiter or RateLimiter()
        self.session = requests.Session()
        self.robots_parsers = {}
        self._session_lock = Lock()
        
    def _get_backoff_delay(self, attempt: int, status_code: Optional[int] = None) -> float:
        """Berechne Delay mit Exponential Backoff"""
        delay = self.base_delay * (2 ** attempt)
        
        if status_code == 429:
            delay *= 3
            logger.warning("429 Too Many Requests - erhöhe Wartezeit")
        elif status_code == 503:
            delay *= 2
            logger.warning("503 Service Unavailable - erhöhe Wartezeit")
        
        jitter = delay * 0.2 * (2 * random.random() - 1)
        return delay + jitter
    
    def _get_headers(self) -> Dict[str, str]:
        """Generiere Headers mit zufälligem User-Agent"""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
    
    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Führe Request mit Retry-Logik aus"""
        self.rate_limiter.wait()
        
        last_exception = None
        proxy = None
        
        for attempt in range(self.max_retries):
            try:
                headers = self._get_headers()
                if 'headers' in kwargs:
                    headers.update(kwargs.pop('headers'))
                
                # Proxy wählen (bei jedem Retry ein neuer)
                if self.proxy_manager:
                    proxy = self.proxy_manager.get_proxy()
                
                logger.debug(f"Request {attempt + 1}/{self.max_retries}: {url}")
                
                with self._session_lock:
                    response = self.session.request(
                        method=method,
                        url=url,
                        headers=headers,
                        timeout=self.timeout,
                        proxies=proxy,
                        **kwargs
                    )
                
                if response.status_code in [429, 503]:
                    if attempt < self.max_retries - 1:
                        delay = self._get_backoff_delay(attempt, response.status_code)
                        logger.warning(f"Status {response.status_code}, warte {delay:.2f}s...")
                        time.sleep(delay)
                        continue
                
                response.raise_for_status()
                self.rate_limiter.report_success()
                return response
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(f"Timeout bei Request zu {url} (Versuch {attempt + 1}/{self.max_retries})")
                self.rate_limiter.report_error()
                
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                logger.warning(f"Connection Error bei {url} (Versuch {attempt + 1}/{self.max_retries})")
                self.rate_limiter.report_error()
                if proxy and self.proxy_manager:
                    self.proxy_manager.mark_failed(proxy)
                
            except requests.exceptions.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code if e.response else None
                logger.warning(f"HTTP Error {status_code} bei {url} (Versuch {attempt + 1}/{self.max_retries})")
                self.rate_limiter.report_error()
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"Request Error bei {url}: {e} (Versuch {attempt + 1}/{self.max_retries})")
                self.rate_limiter.report_error()
                if proxy and self.proxy_manager:
                    self.proxy_manager.mark_failed(proxy)
            
            if attempt < self.max_retries - 1:
                delay = self._get_backoff_delay(attempt)
                logger.info(f"Warte {delay:.2f}s vor Retry...")
                time.sleep(delay)
        
        logger.error(f"Alle {self.max_retries} Versuche für {url} fehlgeschlagen")
        if last_exception:
            raise last_exception
        raise requests.RequestException(f"Max retries exceeded for {url}")
    
    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request('GET', url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request('POST', url, **kwargs)
    
    def close(self):
        with self._session_lock:
            self.session.close()


class DomainScraper:
    """Haupt-Scraper Klasse mit parallelem Scraping"""
    
    def __init__(self, use_proxies: bool = False, proxy_list: Optional[List[str]] = None,
                 use_free_proxies: bool = False, test_mode: bool = False,
                 timeout: int = 10, min_delay: float = 1.0, max_delay: float = 3.0,
                 proxy_rotation_limit: int = 10, max_workers: int = 3):
        """
        Initialisiere Domain Scraper
        
        Args:
            use_proxies: Aktiviere Proxy-Support
            proxy_list: Liste von Proxy-URLs
            use_free_proxies: Verwende kostenlose Proxies
            test_mode: Test-Modus mit weniger Domains
            timeout: Request Timeout in Sekunden
            min_delay: Minimale Pause zwischen Requests
            max_delay: Maximale Pause zwischen Requests
            proxy_rotation_limit: Rotiere Proxy nach X Requests
            max_workers: Maximale parallele Worker für Scraping
        """
        self.test_mode = test_mode
        self.domains = []
        self.max_workers = max_workers
        self._db_lock = Lock()
        
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(LOGS_DIR, exist_ok=True)
        
        # Proxy Manager
        proxy_manager = None
        if use_proxies or proxy_list or use_free_proxies:
            if use_free_proxies:
                logger.info("Verwende Free Proxy Manager...")
                proxy_manager = get_proxy_manager(
                    rotation_limit=proxy_rotation_limit,
                    test_before_use=True,
                    auto_fetch=True,
                    min_proxies=3
                )
            else:
                proxy_manager = ProxyManager(proxy_list=proxy_list)
                if proxy_list:
                    logger.info(f"{len(proxy_list)} manuelle Proxies konfiguriert")
            
            if proxy_manager and hasattr(proxy_manager, 'working_proxies'):
                logger.info(f"{len(proxy_manager.working_proxies)} funktionierende Proxies verfügbar")
        
        # Rate Limiter
        rate_limiter = RateLimiter(min_delay=min_delay, max_delay=max_delay)
        
        # Retry Session
        self.retry_session = RetrySession(
            max_retries=3,
            base_delay=1.0,
            timeout=timeout,
            proxy_manager=proxy_manager,
            rate_limiter=rate_limiter
        )
        
        self._init_db()
    
    def _init_db(self):
        """SQLite Datenbank initialisieren"""
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
        """Domain in Datenbank speichern (Thread-Safe)"""
        with self._db_lock:
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
        """Scrape-Vorgang loggen (Thread-Safe)"""
        with self._db_lock:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scrape_log (scrape_time, source, domains_found, domains_new, error)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), source, found, new, error))
            conn.commit()
            conn.close()
    
    def _clean_domain(self, domain):
        """Bereinigt Domain-Namen"""
        if not domain:
            return None
        
        domain = domain.lower().strip()
        domain = re.sub(r'^(https?://)?(www\.)?', '', domain)
        domain = domain.lstrip('.')
        
        while '..' in domain:
            domain = domain.replace('..', '.')
        
        for _ in range(3):
            match = re.search(r'^(.*?[a-z0-9])((?:\.[a-z]+)+)\2$', domain)
            if match:
                domain = match.group(1) + match.group(2)
            else:
                break
        
        parts = domain.split('.')
        if len(parts) >= 3:
            if parts[-1] == parts[-2] and len(parts[-1]) <= 4:
                parts = parts[:-1]
                domain = '.'.join(parts)
        
        domain = domain.rstrip('.')
        
        # Validiere Domain-Format
        # Prüfe auf ungültige Zeichenfolgen am Anfang/Ende des Labels
        if not re.match(r'^[a-z0-9][a-z0-9\-]*\.[a-z]+(\.[a-z]+)*$', domain):
            logger.warning(f"Ungültiges Domain-Format nach Bereinigung: {domain}")
            return None
        
        # Zusätzliche Prüfung: Domain-Labels dürfen nicht mit - beginnen oder enden
        labels = domain.split('.')
        for label in labels[:-1]:  # TLD auslassen
            if label.startswith('-') or label.endswith('-'):
                logger.warning(f"Domain-Label beginnt/endet mit -: {domain}")
                return None
        
        return domain
    
    def _extract_tld(self, domain):
        """TLD aus Domain extrahieren"""
        if not domain or '.' not in domain:
            return '.com'
        
        multi_level_tlds = [
            '.co.uk', '.ac.uk', '.gov.uk', '.org.uk', '.net.uk',
            '.com.au', '.net.au', '.org.au', '.gov.au',
            '.co.nz', '.net.nz', '.org.nz',
            '.co.jp', '.ne.jp', '.or.jp',
            '.com.br', '.net.br', '.org.br',
            '.co.in', '.net.in', '.org.in',
        ]
        
        domain_lower = domain.lower()
        
        for tld in multi_level_tlds:
            if domain_lower.endswith(tld):
                return tld
        
        parts = domain.split('.')
        if len(parts) >= 2:
            return '.' + parts[-1]
        
        return '.com'
    
    def _get_test_limit(self, default_limit: int) -> int:
        """Gibt Limit zurück - im Test-Modus reduziert"""
        return 5 if self.test_mode else default_limit
    
    # ==================== SCRAPER METHODS ====================
    
    def scrape_expired_domains_net(self, limit=200):
        """ExpiredDomains.net scrapen"""
        limit = self._get_test_limit(limit)
        logger.info(f"Scraping ExpiredDomains.net... (Limit: {limit})")
        domains_found = []
        new_count = 0
        
        target_tlds = ['.com', '.io', '.ai', '.de']
        
        list_urls = [
            "https://www.expireddomains.net/deleted-com-domains/",
            "https://www.expireddomains.net/deleted-de-domains/",
            "https://www.expireddomains.net/deleted-io-domains/",
            "https://www.expireddomains.net/deleted-ai-domains/",
        ]
        
        for list_url in list_urls:
            try:
                logger.info(f"Scraping: {list_url}")
                response = self.retry_session.get(list_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', {'class': 'base1'}) or soup.find('table')
                
                if not table:
                    logger.warning(f"Keine Tabelle gefunden auf {list_url}")
                    continue
                
                rows = table.find_all('tr')[1:]
                logger.info(f"Gefunden: {len(rows)} Zeilen auf {list_url}")
                
                for row in rows[:limit]:
                    try:
                        cells = row.find_all('td')
                        if len(cells) < 2:
                            continue
                        
                        domain_cell = cells[0].find('a')
                        if not domain_cell:
                            continue
                        
                        raw_domain = domain_cell.text.strip()
                        domain_name = self._clean_domain(raw_domain)
                        if not domain_name:
                            continue
                        
                        tld = self._extract_tld(domain_name)
                        if tld not in target_tlds:
                            continue
                        
                        # Extrahiere Metriken
                        age = None
                        if len(cells) > 2:
                            age_text = cells[2].text.strip()
                            age_match = re.search(r'(\d+)', age_text.replace(',', ''))
                            if age_match:
                                age = int(age_match.group(1))
                        
                        backlinks = None
                        for idx in [4, 5, 6, 7]:
                            if len(cells) > idx:
                                bl_text = cells[idx].text.strip().replace(',', '').replace('.', '')
                                if bl_text.isdigit():
                                    backlinks = int(bl_text)
                                    break
                        
                        authority = None
                        for idx in [3, 4, 5]:
                            if len(cells) > idx:
                                auth_text = cells[idx].text.strip()
                                if auth_text.isdigit():
                                    authority = int(auth_text)
                                    break
                        
                        domain_data = {
                            'domain_name': domain_name,
                            'tld': tld,
                            'age_years': age,
                            'backlinks': backlinks,
                            'domain_authority': authority,
                            'estimated_traffic': None,
                            'source': 'expireddomains.net',
                            'auction_status': 'deleted'
                        }
                        
                        domains_found.append(domain_data)
                        if self._save_domain(domain_data):
                            new_count += 1
                            
                    except Exception as e:
                        logger.debug(f"Fehler beim Parsen einer Zeile: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Fehler beim Scraping von {list_url}: {e}")
                continue
        
        self._log_scrape('expireddomains.net', len(domains_found), new_count)
        logger.info(f"ExpiredDomains.net: {len(domains_found)} Domains gefunden, {new_count} neu")
        return domains_found
    
    def scrape_dynadot(self, limit=50):
        """Dynadot Auctions scrapen"""
        limit = self._get_test_limit(limit)
        logger.info(f"Scraping Dynadot Auctions... (Limit: {limit})")
        domains_found = []
        new_count = 0
        
        target_tlds = ['.com', '.io', '.ai', '.de', '.net', '.org']
        
        try:
            # Dynadot expired domains page
            url = "https://www.dynadot.com/market/expired-domains"
            response = self.retry_session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Suche Domain-Elemente
            domain_elements = soup.find_all('div', class_=['domain-name', 'domain-item'])
            
            for elem in domain_elements[:limit]:
                try:
                    domain_link = elem.find('a')
                    if not domain_link:
                        continue
                    
                    raw_domain = domain_link.text.strip()
                    domain_name = self._clean_domain(raw_domain)
                    if not domain_name:
                        continue
                    
                    tld = self._extract_tld(domain_name)
                    if tld not in target_tlds:
                        continue
                    
                    # Versuche Preis zu extrahieren
                    price = None
                    price_elem = elem.find('span', class_=['price', 'domain-price'])
                    if price_elem:
                        price = price_elem.text.strip()
                    
                    domain_data = {
                        'domain_name': domain_name,
                        'tld': tld,
                        'source': 'dynadot.com',
                        'auction_status': 'auction',
                        'price': price,
                        'auction_url': f"https://www.dynadot.com/domain/{domain_name}"
                    }
                    
                    domains_found.append(domain_data)
                    if self._save_domain(domain_data):
                        new_count += 1
                        
                except Exception as e:
                    logger.debug(f"Fehler beim Parsen: {e}")
                    continue
            
            logger.info(f"Dynadot: {len(domains_found)} Domains gefunden")
            
        except Exception as e:
            logger.error(f"Fehler beim Dynadot Scraping: {e}")
        
        self._log_scrape('dynadot.com', len(domains_found), new_count)
        return domains_found
    
    def scrape_godaddy(self, limit=50):
        """GoDaddy Auctions scrapen"""
        limit = self._get_test_limit(limit)
        logger.info(f"Scraping GoDaddy Auctions... (Limit: {limit})")
        domains_found = []
        new_count = 0
        
        target_tlds = ['.com', '.io', '.ai', '.de', '.net', '.org']
        
        try:
            # GoDaddy auctions API/Seite
            # Hinweis: GoDaddy erfordert oft API-Key für vollen Zugriff
            url = "https://auctions.godaddy.com/beta/trpAuctionListing.aspx"
            
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'X-Requested-With': 'XMLHttpRequest'
            }
            
            response = self.retry_session.get(url, headers=headers)
            
            try:
                data = response.json()
                auctions = data.get('auctions', [])
            except:
                # Fallback: HTML Parsing
                soup = BeautifulSoup(response.text, 'html.parser')
                auctions = []
                rows = soup.find_all('tr', class_=['auction-row', 'listing-row'])
                for row in rows:
                    domain_cell = row.find('td', class_='domain')
                    if domain_cell:
                        auctions.append({'domain': domain_cell.text.strip()})
            
            for auction in auctions[:limit]:
                try:
                    raw_domain = auction.get('domain', '')
                    if not raw_domain:
                        continue
                    
                    domain_name = self._clean_domain(raw_domain)
                    if not domain_name:
                        continue
                    
                    tld = self._extract_tld(domain_name)
                    if tld not in target_tlds:
                        continue
                    
                    price = auction.get('price') or auction.get('currentPrice')
                    
                    domain_data = {
                        'domain_name': domain_name,
                        'tld': tld,
                        'source': 'godaddy.com',
                        'auction_status': 'auction',
                        'price': str(price) if price else None,
                        'auction_url': f"https://auctions.godaddy.com/trpItemListing.aspx?miid={auction.get('id', '')}"
                    }
                    
                    domains_found.append(domain_data)
                    if self._save_domain(domain_data):
                        new_count += 1
                        
                except Exception as e:
                    logger.debug(f"Fehler beim Parsen: {e}")
                    continue
            
            logger.info(f"GoDaddy: {len(domains_found)} Domains gefunden")
            
        except Exception as e:
            logger.error(f"Fehler beim GoDaddy Scraping: {e}")
        
        self._log_scrape('godaddy.com', len(domains_found), new_count)
        return domains_found
    
    def scrape_namecheap(self, limit=50):
        """Namecheap Marketplace scrapen"""
        limit = self._get_test_limit(limit)
        logger.info(f"Scraping Namecheap Marketplace... (Limit: {limit})")
        domains_found = []
        new_count = 0
        
        target_tlds = ['.com', '.io', '.ai', '.de', '.net', '.org']
        
        try:
            url = "https://www.namecheap.com/market/"
            response = self.retry_session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            domain_items = soup.find_all('div', class_=['domain-item', 'marketplace-item'])
            
            for item in domain_items[:limit]:
                try:
                    domain_elem = item.find('span', class_='domain-name') or item.find('h3')
                    if not domain_elem:
                        continue
                    
                    raw_domain = domain_elem.text.strip()
                    domain_name = self._clean_domain(raw_domain)
                    if not domain_name:
                        continue
                    
                    tld = self._extract_tld(domain_name)
                    if tld not in target_tlds:
                        continue
                    
                    price_elem = item.find('span', class_='price')
                    price = price_elem.text.strip() if price_elem else None
                    
                    domain_data = {
                        'domain_name': domain_name,
                        'tld': tld,
                        'source': 'namecheap.com',
                        'auction_status': 'marketplace',
                        'price': price
                    }
                    
                    domains_found.append(domain_data)
                    if self._save_domain(domain_data):
                        new_count += 1
                        
                except Exception as e:
                    logger.debug(f"Fehler beim Parsen: {e}")
                    continue
            
            logger.info(f"Namecheap: {len(domains_found)} Domains gefunden")
            
        except Exception as e:
            logger.error(f"Fehler beim Namecheap Scraping: {e}")
        
        self._log_scrape('namecheap.com', len(domains_found), new_count)
        return domains_found
    
    # ==================== PARALLEL SCRAPING ====================
    
    def run_all_scrapers_parallel(self):
        """Alle Scraper parallel ausführen"""
        logger.info("=" * 60)
        logger.info("Starte paralleles Domain-Scraping...")
        logger.info(f"Zeit: {datetime.now().isoformat()}")
        logger.info(f"Modus: {'TEST' if self.test_mode else 'PRODUCTION'}")
        logger.info(f"Max Workers: {self.max_workers}")
        logger.info("=" * 60)
        
        # Definiere alle Scraper
        scrapers = [
            ('expireddomains.net', self.scrape_expired_domains_net, 200),
            ('dynadot.com', self.scrape_dynadot, 50),
            ('godaddy.com', self.scrape_godaddy, 50),
            ('namecheap.com', self.scrape_namecheap, 50),
        ]
        
        results = {}
        total_domains = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Starte alle Scrapers
            future_to_source = {
                executor.submit(scraper[1], scraper[2]): scraper[0] 
                for scraper in scrapers
            }
            
            # Sammle Ergebnisse
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    domains = future.result()
                    results[source] = len(domains)
                    total_domains += len(domains)
                    logger.info(f"✓ {source}: {len(domains)} Domains")
                except Exception as e:
                    logger.error(f"✗ {source} fehlgeschlagen: {e}")
                    results[source] = 0
        
        logger.info("=" * 60)
        logger.info("Paralleles Scraping abgeschlossen!")
        for source, count in results.items():
            logger.info(f"  {source}: {count} Domains")
        logger.info(f"Gesamt: {total_domains} Domains verarbeitet")
        logger.info("=" * 60)
        
        return total_domains
    
    def run_all_scrapers(self, parallel: bool = True):
        """Alle Scraper ausführen"""
        if parallel:
            return self.run_all_scrapers_parallel()
        else:
            return self.run_all_scrapers_sequential()
    
    def run_all_scrapers_sequential(self):
        """Alle Scraper sequentiell ausführen (Legacy)"""
        logger.info("=" * 60)
        logger.info("Starte sequenzielles Domain-Scraping...")
        logger.info(f"Zeit: {datetime.now().isoformat()}")
        logger.info(f"Modus: {'TEST' if self.test_mode else 'PRODUCTION'}")
        logger.info("=" * 60)
        
        total_domains = 0
        
        try:
            domains = self.scrape_expired_domains_net(limit=200)
            total_domains += len(domains)
        except Exception as e:
            logger.error(f"ExpiredDomains.net scraper failed: {e}")
        
        try:
            domains = self.scrape_dynadot(limit=50)
            total_domains += len(domains)
        except Exception as e:
            logger.error(f"Dynadot scraper failed: {e}")
        
        try:
            domains = self.scrape_godaddy(limit=50)
            total_domains += len(domains)
        except Exception as e:
            logger.error(f"GoDaddy scraper failed: {e}")
        
        try:
            domains = self.scrape_namecheap(limit=50)
            total_domains += len(domains)
        except Exception as e:
            logger.error(f"Namecheap scraper failed: {e}")
        
        logger.info("=" * 60)
        logger.info(f"Scraping abgeschlossen!")
        logger.info(f"Gesamt: {total_domains} Domains verarbeitet")
        logger.info("=" * 60)
        
        return total_domains
    
    # ==================== UTILITY METHODS ====================
    
    def test_connection(self, url: str = "https://httpbin.org/get") -> bool:
        """Teste Verbindung und zeige Details"""
        try:
            logger.info(f"Teste Verbindung zu {url}...")
            response = self.retry_session.get(url)
            logger.info(f"Verbindung erfolgreich! Status: {response.status_code}")
            
            try:
                data = response.json()
                headers = data.get('headers', {})
                logger.info(f"User-Agent: {headers.get('User-Agent', 'N/A')}")
                logger.info(f"Origin IP: {data.get('origin', 'N/A')}")
            except:
                pass
            
            return True
        except Exception as e:
            logger.error(f"Verbindungstest fehlgeschlagen: {e}")
            return False
    
    def test_proxies(self) -> Dict[str, bool]:
        """Teste alle konfigurierten Proxies"""
        results = {}
        test_url = "https://httpbin.org/ip"
        
        if not self.retry_session.proxy_manager:
            logger.warning("Keine Proxies konfiguriert!")
            return results
        
        pm = self.retry_session.proxy_manager
        
        if hasattr(pm, 'working_proxies'):
            logger.info(f"Teste {len(pm.working_proxies)} Proxies...")
            
            for proxy_url in pm.working_proxies:
                try:
                    if hasattr(pm, 'test_proxy'):
                        success, ip = pm.test_proxy(proxy_url)
                    else:
                        proxies = {'http': proxy_url, 'https': proxy_url}
                        response = requests.get(test_url, proxies=proxies, timeout=10)
                        success = response.status_code == 200
                        ip = None
                    
                    results[proxy_url] = success
                    
                    if success:
                        logger.info(f"✓ Proxy funktioniert: {proxy_url} (IP: {ip})")
                    else:
                        logger.warning(f"✗ Proxy fehlgeschlagen: {proxy_url}")
                        
                except Exception as e:
                    logger.error(f"✗ Proxy Fehler {proxy_url}: {e}")
                    results[proxy_url] = False
        
        working = sum(1 for v in results.values() if v)
        logger.info(f"Proxy-Test abgeschlossen: {working}/{len(results)} Proxies funktionieren")
        
        return results
    
    def refresh_proxies(self) -> int:
        """Aktualisiere Proxies von Free Sources"""
        if not self.retry_session.proxy_manager:
            logger.warning("Kein ProxyManager konfiguriert!")
            return 0
        
        pm = self.retry_session.proxy_manager
        
        if hasattr(pm, 'fetch_and_test_proxies'):
            logger.info("Aktualisiere Proxies...")
            working = pm.fetch_and_test_proxies(force=True)
            logger.info(f"{len(working)} Proxies jetzt verfügbar")
            return len(working)
        else:
            logger.warning("ProxyManager unterstützt kein Auto-Fetch")
            return 0
    
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
    
    def close(self):
        """Ressourcen freigeben"""
        self.retry_session.close()


def main():
    """Hauptfunktion mit Argument-Parser"""
    parser = argparse.ArgumentParser(
        description='Domain Scraper - Sammelt expired Domains von verschiedenen Quellen',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python scraper.py                           # Normaler Scraping-Lauf (parallel)
  python scraper.py --sequential              # Sequentielles Scraping
  python scraper.py --test                    # Test-Modus
  python scraper.py --use-free-proxies        # Free Proxies verwenden
  python scraper.py --workers 5               # 5 parallele Worker
  python scraper.py --max-retries 5           # 5 Retry-Versuche
        """
    )
    
    parser.add_argument('--test', action='store_true',
                        help='Test-Modus: Nur wenige Domains scrapen')
    parser.add_argument('--sequential', action='store_true',
                        help='Sequentielles statt paralleles Scraping')
    parser.add_argument('--workers', type=int, default=3,
                        help='Anzahl paralleler Worker (default: 3)')
    parser.add_argument('--max-retries', type=int, default=3,
                        help='Maximale Retry-Versuche (default: 3)')
    parser.add_argument('--proxy-test', action='store_true',
                        help='Teste alle konfigurierten Proxies')
    parser.add_argument('--connection-test', action='store_true',
                        help='Teste Verbindung (zeigt User-Agent und IP)')
    parser.add_argument('--use-proxies', action='store_true',
                        help='Aktiviere Proxy-Support')
    parser.add_argument('--use-free-proxies', action='store_true',
                        help='Verwende kostenlose Free Proxies (empfohlen)')
    parser.add_argument('--refresh-proxies', action='store_true',
                        help='Aktualisiere Proxies von Free Sources')
    parser.add_argument('--proxy-list', type=str,
                        help='Komma-getrennte Liste von Proxies (format: host:port)')
    parser.add_argument('--timeout', type=int, default=10,
                        help='Request Timeout in Sekunden (default: 10)')
    parser.add_argument('--min-delay', type=float, default=1.0,
                        help='Minimale Pause zwischen Requests (default: 1.0)')
    parser.add_argument('--max-delay', type=float, default=3.0,
                        help='Maximale Pause zwischen Requests (default: 3.0)')
    
    args = parser.parse_args()
    
    # Proxy-Liste parsen
    proxy_list = None
    if args.proxy_list:
        proxy_list = [f"http://{p.strip()}" for p in args.proxy_list.split(',')]
    
    # Scraper initialisieren
    scraper = DomainScraper(
        use_proxies=args.use_proxies,
        proxy_list=proxy_list,
        use_free_proxies=args.use_free_proxies,
        test_mode=args.test,
        timeout=args.timeout,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        max_workers=args.workers
    )
    
    try:
        # Verbindungstest
        if args.connection_test:
            success = scraper.test_connection()
            sys.exit(0 if success else 1)
        
        # Proxies aktualisieren
        if args.refresh_proxies:
            count = scraper.refresh_proxies()
            sys.exit(0 if count > 0 else 1)
        
        # Proxy-Test
        if args.proxy_test:
            results = scraper.test_proxies()
            working = sum(1 for v in results.values() if v)
            sys.exit(0 if working > 0 else 1)
        
        # Normale Ausführung
        stats = scraper.get_stats()
        logger.info(f"Aktuelle Datenbank-Statistik: {stats['total_domains']} Domains gespeichert")
        
        total = scraper.run_all_scrapers(parallel=not args.sequential)
        
        stats = scraper.get_stats()
        logger.info(f"Neue Gesamtstatistik: {stats['total_domains']} Domains in Datenbank")
        
        return total
        
    finally:
        scraper.close()


def run(use_proxies=False, proxy_list=None, use_free_proxies=False, 
        test_mode=False, timeout=10, min_delay=1.0, max_delay=3.0,
        max_workers=3, parallel=True):
    """
    Hauptfunktion für main.py Integration
    
    Args:
        use_proxies: Aktiviere Proxy-Support
        proxy_list: Liste von Proxy-URLs
        use_free_proxies: Verwende kostenlose Proxies
        test_mode: Test-Modus mit weniger Domains
        timeout: Request Timeout
        min_delay: Minimale Pause
        max_delay: Maximale Pause
        max_workers: Anzahl paralleler Worker
        parallel: Paralleles Scraping aktivieren
    
    Returns:
        int: Anzahl der gefundenen Domains
    """
    logger.info("Starte Domain Scraper...")
    
    scraper = DomainScraper(
        use_proxies=use_proxies,
        proxy_list=proxy_list,
        use_free_proxies=use_free_proxies,
        test_mode=test_mode,
        timeout=timeout,
        min_delay=min_delay,
        max_delay=max_delay,
        max_workers=max_workers
    )
    
    try:
        count = scraper.run_all_scrapers(parallel=parallel)
        logger.info(f"Scraper fertig. {count} Domains gefunden.")
        return count
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
