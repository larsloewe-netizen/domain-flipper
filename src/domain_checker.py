#!/usr/bin/env python3
"""
Domain Checker für das Domain-Flipping-Projekt

Dieses Modul prüft Domains auf Verfügbarkeit, historische Daten und SEO-Metriken.

MVP-Funktionen:
- WHOIS-Lookup für Verfügbarkeit
- Archive.org-Integration für historische Nutzung

Premium-Erweiterungen (optional):
- Dynadot/Namecheap API für Auction-Status
- NameBio API für Verkaufsdaten
- Majestic/ahrefs für Backlinks
"""

import sqlite3
import whois
import requests
import json
import time
import re
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, asdict
from urllib.parse import quote
import logging
from pathlib import Path

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class DomainCheckResult:
    """Ergebnis einer Domain-Überprüfung"""
    id: Optional[int] = None  # Datenbank-ID
    domain: str = ""
    timestamp: str = ""
    
    # Verfügbarkeit
    is_available: Optional[bool] = None
    is_registered: Optional[bool] = None
    expiry_date: Optional[str] = None
    creation_date: Optional[str] = None
    registrar: Optional[str] = None
    
    # Historische Daten (Archive.org)
    archive_count: Optional[int] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    has_history: Optional[bool] = None
    
    # Auction-Status (Premium)
    auction_status: Optional[str] = None
    auction_price: Optional[float] = None
    auction_platform: Optional[str] = None
    
    # Verkaufsdaten (Premium)
    comparable_sales: Optional[List[Dict]] = None
    estimated_value: Optional[float] = None
    
    # SEO-Metriken (Premium)
    backlink_count: Optional[int] = None
    referring_domains: Optional[int] = None
    domain_authority: Optional[float] = None
    spam_score: Optional[int] = None
    
    # Zusätzliche Metadaten
    tld: Optional[str] = None
    category: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Konvertiere zu Dictionary für JSON/DB"""
        result = asdict(self)
        # Konvertiere Listen/Dicts zu JSON-Strings für SQLite
        if self.comparable_sales:
            result['comparable_sales'] = json.dumps(self.comparable_sales)
        return result


class DomainChecker:
    """Hauptklasse für Domain-Überprüfungen"""
    
    def __init__(self, db_path: str = None, config: Dict = None):
        """
        Initialisiert den DomainChecker
        
        Args:
            db_path: Pfad zur SQLite-Datenbank
            config: Optional - API-Keys und Konfiguration
        """
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "expired_domains.db")
        
        self.db_path = db_path
        self.config = config or {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'DomainFlipper/1.0 (Research Tool)'
        })
        
        # Rate Limiting
        self.last_whois_check = 0
        self.whois_delay = 1.0  # Sekunden zwischen WHOIS-Abfragen
        
        self._init_database()
    
    def _init_database(self):
        """Initialisiert die Datenbanktabellen"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabelle für Domain-Checks
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS domain_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                
                -- Verfügbarkeit
                is_available INTEGER,
                is_registered INTEGER,
                expiry_date TEXT,
                creation_date TEXT,
                registrar TEXT,
                
                -- Archive.org Daten
                archive_count INTEGER,
                first_seen TEXT,
                last_seen TEXT,
                has_history INTEGER,
                
                -- Auction Daten (Premium)
                auction_status TEXT,
                auction_price REAL,
                auction_platform TEXT,
                
                -- Verkaufsdaten (Premium)
                comparable_sales TEXT,  -- JSON
                estimated_value REAL,
                
                -- SEO-Metriken (Premium)
                backlink_count INTEGER,
                referring_domains INTEGER,
                domain_authority REAL,
                spam_score INTEGER,
                
                -- Metadaten
                tld TEXT,
                category TEXT,
                error_message TEXT,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Index für schnelle Abfragen
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_domain_checks_domain 
            ON domain_checks(domain)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_domain_checks_available 
            ON domain_checks(is_available)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_domain_checks_history 
            ON domain_checks(has_history)
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Datenbank initialisiert: %s", self.db_path)
    
    def _rate_limit_whois(self):
        """Rate Limiting für WHOIS-Anfragen"""
        elapsed = time.time() - self.last_whois_check
        if elapsed < self.whois_delay:
            time.sleep(self.whois_delay - elapsed)
        self.last_whois_check = time.time()
    
    def extract_tld(self, domain: str) -> str:
        """Extrahiert die TLD aus einer Domain"""
        parts = domain.lower().split('.')
        if len(parts) > 1:
            return parts[-1]
        return ''
    
    def check_whois(self, domain: str) -> Dict[str, Any]:
        """
        Prüft Domain-Verfügbarkeit via WHOIS
        
        Args:
            domain: Zu prüfende Domain
            
        Returns:
            Dictionary mit Verfügbarkeitsinformationen
        """
        self._rate_limit_whois()
        
        result = {
            'is_available': None,
            'is_registered': None,
            'expiry_date': None,
            'creation_date': None,
            'registrar': None,
            'error': None
        }
        
        try:
            w = whois.whois(domain)
            
            # Domain ist registriert wenn wir Daten bekommen
            result['is_registered'] = True
            result['is_available'] = False
            
            # Extrahiere Datumswerte
            if w.expiration_date:
                if isinstance(w.expiration_date, list):
                    expiry = w.expiration_date[0]
                else:
                    expiry = w.expiration_date
                if isinstance(expiry, datetime):
                    result['expiry_date'] = expiry.isoformat()
            
            if w.creation_date:
                if isinstance(w.creation_date, list):
                    creation = w.creation_date[0]
                else:
                    creation = w.creation_date
                if isinstance(creation, datetime):
                    result['creation_date'] = creation.isoformat()
            
            if w.registrar:
                result['registrar'] = str(w.registrar)
            
            logger.info("WHOIS: %s ist registriert (Registrar: %s)", 
                       domain, result['registrar'] or 'unbekannt')
            
        except whois.parser.PywhoisError as e:
            # Domain wahrscheinlich verfügbar
            error_str = str(e).lower()
            if 'not found' in error_str or 'no match' in error_str or 'available' in error_str:
                result['is_available'] = True
                result['is_registered'] = False
                logger.info("WHOIS: %s scheint verfügbar zu sein", domain)
            else:
                result['error'] = str(e)
                logger.warning("WHOIS-Fehler für %s: %s", domain, e)
                
        except Exception as e:
            result['error'] = str(e)
            logger.error("Unerwarteter WHOIS-Fehler für %s: %s", domain, e)
        
        return result
    
    def check_archive_org(self, domain: str) -> Dict[str, Any]:
        """
        Prüft Archive.org nach historischen Snapshots der Domain
        
        Args:
            domain: Zu prüfende Domain
            
        Returns:
            Dictionary mit Archiv-Daten
        """
        result = {
            'archive_count': 0,
            'first_seen': None,
            'last_seen': None,
            'has_history': False,
            'error': None
        }
        
        try:
            # CDX API für Snapshot-Liste
            url = f"https://web.archive.org/cdx/search/cdx"
            params = {
                'url': domain,
                'output': 'json',
                'fl': 'timestamp,original',
                'collapse': 'timestamp:6',  # Eintrag pro Monat
                'limit': 1000
            }
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Erste Zeile sind Header
            if len(data) > 1:
                snapshots = data[1:]  # Header überspringen
                result['archive_count'] = len(snapshots)
                result['has_history'] = True
                
                # Erster und letzter Snapshot
                if snapshots:
                    first_ts = snapshots[0][0]
                    last_ts = snapshots[-1][0]
                    
                    # Konvertiere Timestamp (YYYYMMDDHHMMSS)
                    result['first_seen'] = self._parse_wayback_timestamp(first_ts)
                    result['last_seen'] = self._parse_wayback_timestamp(last_ts)
                
                logger.info("Archive.org: %s hat %d Snapshots (%s bis %s)",
                           domain, result['archive_count'],
                           result['first_seen'] or 'unbekannt',
                           result['last_seen'] or 'unbekannt')
            else:
                logger.info("Archive.org: %s hat keine historischen Daten", domain)
                
        except requests.exceptions.RequestException as e:
            result['error'] = f"Netzwerkfehler: {str(e)}"
            logger.warning("Archive.org-Fehler für %s: %s", domain, e)
        except Exception as e:
            result['error'] = str(e)
            logger.error("Unerwarteter Archive.org-Fehler für %s: %s", domain, e)
        
        return result
    
    def _parse_wayback_timestamp(self, ts: str) -> str:
        """Konvertiert Wayback-Timestamp zu ISO-Format"""
        try:
            if len(ts) >= 14:
                dt = datetime.strptime(ts[:14], '%Y%m%d%H%M%S')
                return dt.isoformat()
        except:
            pass
        return ts
    
    def get_archive_snapshot_url(self, domain: str, timestamp: str = None) -> str:
        """
        Generiert URL für Archive.org-Snapshot
        
        Args:
            domain: Die Domain
            timestamp: Optional - spezifischer Zeitpunkt (YYYYMMDD)
            
        Returns:
            URL zum Snapshot
        """
        if timestamp:
            return f"https://web.archive.org/web/{timestamp}/{domain}"
        return f"https://web.archive.org/web/*/{domain}"
    
    # =========================================================================
    # PREMIUM-FUNKTIONEN (Erweiterungen - benötigen API-Keys)
    # =========================================================================
    
    def check_dynadot_auction(self, domain: str) -> Dict[str, Any]:
        """
        [PREMIUM] Prüft Dynadot Auction-Status
        
        Benötigt: Dynadot API-Key in config['dynadot_api_key']
        
        Args:
            domain: Zu prüfende Domain
            
        Returns:
            Dictionary mit Auction-Informationen
        """
        result = {
            'auction_status': None,
            'auction_price': None,
            'auction_platform': 'dynadot',
            'error': None
        }
        
        api_key = self.config.get('dynadot_api_key')
        if not api_key:
            result['error'] = 'Kein Dynadot API-Key konfiguriert'
            return result
        
        try:
            # Dynadot API-Call (Beispiel - API-Doku beachten)
            url = "https://api.dynadot.com/api3.json"
            params = {
                'key': api_key,
                'command': 'search',
                'domain0': domain
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # Hier müsste die tatsächliche Response-Verarbeitung implementiert werden
            # basierend auf der Dynadot API-Dokumentation
            
            logger.info("Dynadot-Check für %s abgeschlossen", domain)
            
        except Exception as e:
            result['error'] = str(e)
            logger.error("Dynadot-Fehler für %s: %s", domain, e)
        
        return result
    
    def check_namecheap_auction(self, domain: str) -> Dict[str, Any]:
        """
        [PREMIUM] Prüft Namecheap Auction-Status
        
        Benötigt: Namecheap API-Key in config['namecheap_api_key']
        
        Args:
            domain: Zu prüfende Domain
            
        Returns:
            Dictionary mit Auction-Informationen
        """
        result = {
            'auction_status': None,
            'auction_price': None,
            'auction_platform': 'namecheap',
            'error': None
        }
        
        api_key = self.config.get('namecheap_api_key')
        if not api_key:
            result['error'] = 'Kein Namecheap API-Key konfiguriert'
            return result
        
        # Namecheap API-Integration hier implementieren
        result['error'] = 'Namecheap API-Integration noch nicht implementiert'
        
        return result
    
    def check_namebio_sales(self, domain: str) -> Dict[str, Any]:
        """
        [PREMIUM] Prüft historische Verkaufsdaten bei NameBio
        
        Benötigt: NameBio API-Key in config['namebio_api_key']
        
        Args:
            domain: Zu prüfende Domain
            
        Returns:
            Dictionary mit Verkaufsdaten und vergleichbaren Domains
        """
        result = {
            'comparable_sales': [],
            'estimated_value': None,
            'error': None
        }
        
        api_key = self.config.get('namebio_api_key')
        if not api_key:
            result['error'] = 'Kein NameBio API-Key konfiguriert'
            return result
        
        try:
            # NameBio API-Call
            tld = self.extract_tld(domain)
            keyword = domain.replace(f'.{tld}', '')
            
            url = "https://api.namebio.com/v1/sales"
            headers = {'Authorization': f'Bearer {api_key}'}
            params = {
                'keyword': keyword,
                'tld': tld,
                'limit': 10
            }
            
            response = self.session.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Verarbeite vergleichbare Verkäufe
            if 'sales' in data:
                for sale in data['sales']:
                    result['comparable_sales'].append({
                        'domain': sale.get('domain'),
                        'price': sale.get('price'),
                        'date': sale.get('date'),
                        'platform': sale.get('platform')
                    })
                
                # Schätze Wert basierend auf vergleichbaren Verkäufen
                if result['comparable_sales']:
                    prices = [s['price'] for s in result['comparable_sales'] if s['price']]
                    if prices:
                        result['estimated_value'] = sum(prices) / len(prices)
            
            logger.info("NameBio: %d vergleichbare Verkäufe für %s gefunden",
                       len(result['comparable_sales']), domain)
            
        except Exception as e:
            result['error'] = str(e)
            logger.error("NameBio-Fehler für %s: %s", domain, e)
        
        return result
    
    def check_backlinks_free(self, domain: str) -> Dict[str, Any]:
        """
        [BASIC] Prüft Backlinks mit kostenlosen Methoden
        
        Hinweis: Kostenlose Backlink-Checker haben starke Limits.
        Für genaue Daten: Majestic/Ahrefs API erforderlich.
        
        Args:
            domain: Zu prüfende Domain
            
        Returns:
            Dictionary mit Backlink-Informationen
        """
        result = {
            'backlink_count': None,
            'referring_domains': None,
            'domain_authority': None,
            'error': None
        }
        
        # OpenLinkProfiler (kostenlos, limitiert)
        # Alternativ: Open SEO Stats oder ähnliche
        
        try:
            # Beispiel: Google-Suche nach Backlinks (nicht empfohlen für Produktion)
            # Bessere Alternative: OpenLinkProfiler API
            
            # Placeholder - hier würde die tatsächliche Implementierung stehen
            result['error'] = ('Kostenlose Backlink-Checks haben hohe Rate-Limits. '
                              'Für produktive Nutzung Majestic/Ahrefs empfohlen.')
            
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def check_spam_score(self, domain: str) -> Dict[str, Any]:
        """
        [BASIC] Prüft Domain auf Spam-Listen
        
        Args:
            domain: Zu prüfende Domain
            
        Returns:
            Dictionary mit Spam-Informationen
        """
        result = {
            'spam_score': None,
            'in_spam_lists': False,
            'spam_lists': [],
            'error': None
        }
        
        # DNSBL-Checks könnten hier implementiert werden
        # Achtung: Viele DNSBLs blockieren automatisierte Abfragen
        
        result['error'] = ('Spam-Score-Check erfordert spezialisierte APIs '
                          '(z.B. Moz API, Spamhaus)')
        
        return result
    
    # =========================================================================
    # HAUPTFUNKTIONEN
    # =========================================================================
    
    def check_domain(self, domain: str, use_premium: bool = False) -> DomainCheckResult:
        """
        Führt alle verfügbaren Checks für eine Domain durch
        
        Args:
            domain: Zu prüfende Domain
            use_premium: Ob Premium-APIs genutzt werden sollen
            
        Returns:
            DomainCheckResult mit allen Daten
        """
        domain = domain.lower().strip()
        timestamp = datetime.now().isoformat()
        
        logger.info("Starte Domain-Check für: %s", domain)
        
        result = DomainCheckResult(
            domain=domain,
            timestamp=timestamp,
            tld=self.extract_tld(domain)
        )
        
        # 1. WHOIS-Check (MVP)
        whois_data = self.check_whois(domain)
        result.is_available = whois_data.get('is_available')
        result.is_registered = whois_data.get('is_registered')
        result.expiry_date = whois_data.get('expiry_date')
        result.creation_date = whois_data.get('creation_date')
        result.registrar = whois_data.get('registrar')
        
        if whois_data.get('error'):
            result.error_message = whois_data['error']
        
        # 2. Archive.org-Check (MVP)
        archive_data = self.check_archive_org(domain)
        result.archive_count = archive_data.get('archive_count')
        result.first_seen = archive_data.get('first_seen')
        result.last_seen = archive_data.get('last_seen')
        result.has_history = archive_data.get('has_history')
        
        # 3. Premium-Checks (optional)
        if use_premium:
            # Auction-Checks
            dynadot_data = self.check_dynadot_auction(domain)
            if not dynadot_data.get('error'):
                result.auction_status = dynadot_data.get('auction_status')
                result.auction_price = dynadot_data.get('auction_price')
                result.auction_platform = dynadot_data.get('auction_platform')
            
            # Verkaufsdaten
            namebio_data = self.check_namebio_sales(domain)
            if not namebio_data.get('error'):
                result.comparable_sales = namebio_data.get('comparable_sales')
                result.estimated_value = namebio_data.get('estimated_value')
            
            # SEO-Metriken
            backlink_data = self.check_backlinks_free(domain)
            result.backlink_count = backlink_data.get('backlink_count')
            result.referring_domains = backlink_data.get('referring_domains')
            result.domain_authority = backlink_data.get('domain_authority')
            
            spam_data = self.check_spam_score(domain)
            result.spam_score = spam_data.get('spam_score')
        
        logger.info("Domain-Check für %s abgeschlossen", domain)
        return result
    
    def save_result(self, result: DomainCheckResult) -> bool:
        """
        Speichert ein Check-Ergebnis in der Datenbank
        
        Args:
            result: Das zu speichernde Ergebnis
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            data = result.to_dict()
            
            # Entferne 'id' für INSERT/UPDATE
            data.pop('id', None)
            
            # Prüfe ob Eintrag existiert
            cursor.execute(
                "SELECT id FROM domain_checks WHERE domain = ?",
                (result.domain,)
            )
            existing = cursor.fetchone()
            
            if existing:
                # UPDATE
                fields = [f"{k} = ?" for k in data.keys()]
                values = list(data.values()) + [result.domain]
                cursor.execute(
                    f"UPDATE domain_checks SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE domain = ?",
                    values
                )
            else:
                # INSERT
                fields = list(data.keys())
                placeholders = ', '.join(['?' for _ in fields])
                cursor.execute(
                    f"INSERT INTO domain_checks ({', '.join(fields)}) VALUES ({placeholders})",
                    list(data.values())
                )
            
            conn.commit()
            conn.close()
            
            logger.info("Ergebnis für %s gespeichert", result.domain)
            return True
            
        except Exception as e:
            logger.error("Fehler beim Speichern für %s: %s", result.domain, e)
            return False
    
    def get_result(self, domain: str) -> Optional[DomainCheckResult]:
        """
        Lädt ein gespeichertes Ergebnis aus der Datenbank
        
        Args:
            domain: Die Domain
            
        Returns:
            DomainCheckResult oder None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT * FROM domain_checks WHERE domain = ?",
                (domain.lower().strip(),)
            )
            row = cursor.fetchone()
            conn.close()
            
            if row:
                data = dict(row)
                
                # Filtere nur gültige Felder für DomainCheckResult
                valid_fields = {f.name for f in DomainCheckResult.__dataclass_fields__.values()}
                filtered_data = {k: v for k, v in data.items() if k in valid_fields}
                
                # Konvertiere JSON-Strings zurück
                if filtered_data.get('comparable_sales'):
                    try:
                        filtered_data['comparable_sales'] = json.loads(filtered_data['comparable_sales'])
                    except:
                        pass
                
                return DomainCheckResult(**filtered_data)
            
            return None
            
        except Exception as e:
            logger.error("Fehler beim Laden für %s: %s", domain, e)
            return None
    
    def check_domains_batch(self, domains: List[str], use_premium: bool = False, 
                           delay: float = 1.0, save: bool = True) -> List[DomainCheckResult]:
        """
        Prüft mehrere Domains mit Verzögerung zwischen den Checks
        
        Args:
            domains: Liste der zu prüfenden Domains
            use_premium: Ob Premium-APIs genutzt werden sollen
            delay: Verzögerung zwischen Checks in Sekunden
            save: Ob Ergebnisse automatisch gespeichert werden sollen
            
        Returns:
            Liste der DomainCheckResults
        """
        results = []
        
        for i, domain in enumerate(domains):
            logger.info("Batch-Check %d/%d: %s", i + 1, len(domains), domain)
            
            result = self.check_domain(domain, use_premium=use_premium)
            results.append(result)
            
            if save:
                self.save_result(result)
            
            # Rate Limiting zwischen Domains
            if i < len(domains) - 1 and delay > 0:
                time.sleep(delay)
        
        return results
    
    def find_expiring_soon(self, days: int = 30) -> List[Dict]:
        """
        Findet registrierte Domains, die bald auslaufen
        
        Args:
            days: Anzahl der Tage bis zum Ablauf
            
        Returns:
            Liste der ablaufenden Domains
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            future = (datetime.now() + timedelta(days=days)).isoformat()
            
            cursor.execute('''
                SELECT * FROM domain_checks 
                WHERE is_registered = 1 
                AND expiry_date IS NOT NULL
                AND expiry_date <= ?
                ORDER BY expiry_date ASC
            ''', (future,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error("Fehler beim Finden ablaufender Domains: %s", e)
            return []
    
    def find_available_with_history(self, min_snapshots: int = 5) -> List[Dict]:
        """
        Findet verfügbare Domains mit Archive.org-History
        
        Args:
            min_snapshots: Minimale Anzahl an Snapshots
            
        Returns:
            Liste der Domains
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM domain_checks 
                WHERE is_available = 1 
                AND has_history = 1
                AND archive_count >= ?
                ORDER BY archive_count DESC
            ''', (min_snapshots,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error("Fehler beim Finden von Domains mit History: %s", e)
            return []


# ============================================================================
# KONVENIENZFUNKTIONEN FÜR EXTERNE NUTZUNG
# ============================================================================

def check_domain(domain: str, db_path: str = None, use_premium: bool = False) -> DomainCheckResult:
    """
    Einfache Funktion zum Prüfen einer Domain
    
    Usage:
        result = check_domain("example.com")
        print(f"Verfügbar: {result.is_available}")
        print(f"History: {result.archive_count} Snapshots")
    """
    checker = DomainChecker(db_path=db_path)
    return checker.check_domain(domain, use_premium=use_premium)


def check_and_save(domain: str, db_path: str = None, use_premium: bool = False) -> DomainCheckResult:
    """
    Prüft eine Domain und speichert das Ergebnis
    
    Usage:
        result = check_and_save("example.com")
    """
    checker = DomainChecker(db_path=db_path)
    result = checker.check_domain(domain, use_premium=use_premium)
    checker.save_result(result)
    return result


def quick_check(domain: str) -> Dict[str, Any]:
    """
    Schneller Check ohne Datenbank - nur WHOIS + Archive.org
    
    Usage:
        info = quick_check("example.com")
    """
    checker = DomainChecker(db_path=":memory:")  # Temporäre DB
    result = checker.check_domain(domain, use_premium=False)
    return {
        'domain': result.domain,
        'is_available': result.is_available,
        'is_registered': result.is_registered,
        'has_history': result.has_history,
        'archive_count': result.archive_count,
        'first_seen': result.first_seen,
        'last_seen': result.last_seen,
        'expiry_date': result.expiry_date,
        'registrar': result.registrar
    }


# ============================================================================
# MAIN - Für direkte Ausführung
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python domain_checker.py <domain> [domain2] ...")
        print("\nBeispiele:")
        print("  python domain_checker.py example.com")
        print("  python domain_checker.py domain1.com domain2.org domain3.net")
        sys.exit(1)
    
    domains = sys.argv[1:]
    checker = DomainChecker()
    
    print(f"\n{'='*60}")
    print(f"Domain-Checker für {len(domains)} Domain(s)")
    print(f"{'='*60}\n")
    
    for domain in domains:
        result = checker.check_domain(domain)
        checker.save_result(result)
        
        print(f"\n🌐 {result.domain}")
        print(f"   {'─'*50}")
        print(f"   Verfügbar:      {'✅ Ja' if result.is_available else '❌ Nein' if result.is_available == False else '❓ Unbekannt'}")
        print(f"   Registriert:    {'✅ Ja' if result.is_registered else '❌ Nein' if result.is_registered == False else '❓ Unbekannt'}")
        print(f"   Registrar:      {result.registrar or 'N/A'}")
        print(f"   Ablaufdatum:    {result.expiry_date or 'N/A'}")
        print(f"   History:        {'✅ Ja' if result.has_history else '❌ Nein'} ({result.archive_count or 0} Snapshots)")
        
        if result.first_seen:
            print(f"   Erstmals gesehen: {result.first_seen[:10]}")
        if result.last_seen:
            print(f"   Zuletzt gesehen:  {result.last_seen[:10]}")
        
        if result.error_message:
            print(f"   ⚠️  Fehler: {result.error_message}")
        
        if domain != domains[-1]:
            time.sleep(1)  # Rate limiting
    
    print(f"\n{'='*60}")
    print("Checks abgeschlossen!")
    print(f"{'='*60}")


def run():
    """Hauptfunktion für main.py Integration"""
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Starte Domain Checker...")
    
    db_path = "/root/.openclaw/workspace/projects/domain-flipper/data/expired_domains.db"
    checker = DomainChecker(db_path)
    
    # Neue Domains aus DB laden und prüfen
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT domain_name FROM domains WHERE age_days IS NULL LIMIT 50")
    domains = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    checked = 0
    for domain in domains:
        try:
            result = checker.check_domain(domain, use_premium=False)
            checker.save_result(result)
            checked += 1
        except Exception as e:
            logger.error(f"Fehler bei {domain}: {e}")
    
    logger.info(f"Checker fertig. {checked} Domains geprüft.")
    return checked
