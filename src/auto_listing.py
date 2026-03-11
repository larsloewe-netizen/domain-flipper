#!/usr/bin/env python3
"""
Auto-Listing & Verkaufs-Automatisierung für Domain Flipping
==============================================================

Features:
- Sedo API Integration (Sandbox-Modus)
- Afternic API Integration (Sandbox-Modus)
- Dan.com API Integration (Sandbox-Modus)
- Preis-Optimierung mit dynamischer Anpassung
- Outreach-Automatisierung an potenzielle Käufer

WICHTIG: Alle APIs laufen im Sandbox/Test-Modus bis explizit freigegeben!
"""

import sqlite3
import json
import re
import os
import time
import smtplib
import hashlib
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from abc import ABC, abstractmethod
import requests
from urllib.parse import urlparse

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Konstanten
DATA_DIR = Path(__file__).parent.parent / 'data'
DB_PATH = DATA_DIR / 'expired_domains.db'
TEMPLATES_DIR = Path(__file__).parent.parent / 'templates'

# E-Mail Konfiguration
GMAIL_USER = os.getenv('GMAIL_USER', 'hansdieterbot@gmail.com')
GMAIL_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
RECIPIENT_EMAIL = 'lars.loewe@gmail.com'

# ==================== DATACLASSES ====================

@dataclass
class ListingConfig:
    """Konfiguration für ein Domain-Listing"""
    domain: str
    platform: str  # 'sedo', 'afternic', 'dan'
    start_price: float
    min_price: float
    buy_now_price: Optional[float] = None
    currency: str = 'USD'
    category: Optional[str] = None
    description: Optional[str] = None
    keywords: List[str] = None
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []

@dataclass
class PriceHistory:
    """Preis-Historie für eine Domain"""
    domain: str
    platform: str
    price: float
    date: datetime
    reason: str

@dataclass
class OutreachCampaign:
    """Outreach-Kampagne für eine Domain"""
    domain: str
    template_id: str
    target_domains: List[str]
    emails_sent: int = 0
    emails_opened: int = 0
    replies: int = 0
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


# ==================== DATABASE MODELS ====================

def init_auto_listing_db():
    """Initialisiert die Datenbank-Tabellen für Auto-Listing"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Listings Tabelle
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_name TEXT NOT NULL,
            platform TEXT NOT NULL,
            listing_id TEXT,
            status TEXT DEFAULT 'pending',  -- pending, active, sold, expired, error
            start_price REAL,
            current_price REAL,
            min_price REAL,
            buy_now_price REAL,
            currency TEXT DEFAULT 'USD',
            listed_at TEXT,
            last_price_update TEXT,
            platform_listing_url TEXT,
            api_response TEXT,
            error_message TEXT,
            is_sandbox INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(domain_name, platform)
        )
    ''')
    
    # Preis-Historie
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_name TEXT NOT NULL,
            platform TEXT NOT NULL,
            old_price REAL,
            new_price REAL,
            change_reason TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    
    # Outreach-Kampagnen
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outreach_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_name TEXT NOT NULL,
            template_id TEXT NOT NULL,
            status TEXT DEFAULT 'active',  -- active, paused, completed
            emails_sent INTEGER DEFAULT 0,
            emails_opened INTEGER DEFAULT 0,
            replies_received INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            last_sent_at TEXT
        )
    ''')
    
    # Outreach-Empfänger
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outreach_recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            target_domain TEXT,
            recipient_email TEXT,
            email_sent INTEGER DEFAULT 0,
            email_opened INTEGER DEFAULT 0,
            replied INTEGER DEFAULT 0,
            sent_at TEXT,
            opened_at TEXT,
            replied_at TEXT,
            message_id TEXT,
            FOREIGN KEY (campaign_id) REFERENCES outreach_campaigns(id)
        )
    ''')
    
    # WHOIS-Cache für ähnliche Domains
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS whois_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_name TEXT NOT NULL UNIQUE,
            registrar TEXT,
            registrant_email TEXT,
            registrant_name TEXT,
            organization TEXT,
            country TEXT,
            created_date TEXT,
            expiry_date TEXT,
            cached_at TEXT NOT NULL,
            is_available INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Auto-Listing Datenbank initialisiert")


# ==================== ABSTRACT BASE CLASS ====================

class MarketplaceAPI(ABC):
    """Abstrakte Basisklasse für Marketplace APIs"""
    
    def __init__(self, sandbox: bool = True):
        self.sandbox = sandbox
        self.session = requests.Session()
        self.base_url = self._get_base_url()
        
    @abstractmethod
    def _get_base_url(self) -> str:
        """Gibt die Base-URL für die API zurück"""
        pass
    
    @abstractmethod
    def authenticate(self) -> bool:
        """Authentifiziert mit der API"""
        pass
    
    @abstractmethod
    def list_domain(self, config: ListingConfig) -> Dict[str, Any]:
        """Listet eine Domain auf dem Marketplace"""
        pass
    
    @abstractmethod
    def update_price(self, domain: str, new_price: float) -> bool:
        """Aktualisiert den Preis einer gelisteten Domain"""
        pass
    
    @abstractmethod
    def get_listing_status(self, domain: str) -> Dict[str, Any]:
        """Holt den Status eines Listings"""
        pass
    
    @abstractmethod
    def delete_listing(self, domain: str) -> bool:
        """Löscht ein Listing"""
        pass
    
    def _log_api_call(self, method: str, endpoint: str, data: dict = None, response: dict = None):
        """Loggt API-Aufrufe für Debugging"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'platform': self.__class__.__name__,
            'sandbox': self.sandbox,
            'method': method,
            'endpoint': endpoint,
            'request': data,
            'response': response
        }
        logger.info(f"API Call: {json.dumps(log_entry, default=str)}")


# ==================== SEDO API ====================

class SedoAPI(MarketplaceAPI):
    """
    Sedo API Integration
    
    Dokumentation: https://sedo.com/us/sedo-api/
    Sandbox: https://api.sedo.com/sandbox/
    """
    
    def __init__(self, api_key: Optional[str] = None, username: Optional[str] = None, 
                 password: Optional[str] = None, sandbox: bool = True):
        super().__init__(sandbox)
        self.api_key = api_key or os.getenv('SEDO_API_KEY')
        self.username = username or os.getenv('SEDO_USERNAME')
        self.password = password or os.getenv('SEDO_PASSWORD')
        self.auth_token = None
        
    def _get_base_url(self) -> str:
        if self.sandbox:
            return "https://api.sedo.com/sandbox/v1"
        return "https://api.sedo.com/v1"
    
    def authenticate(self) -> bool:
        """Authentifiziert mit Sedo API"""
        if self.sandbox:
            logger.info("[SANDBOX] Sedo Authentifizierung simuliert")
            self.auth_token = "sandbox_token_12345"
            return True
            
        try:
            url = f"{self.base_url}/auth/login"
            headers = {'X-API-KEY': self.api_key}
            data = {
                'username': self.username,
                'password': self.password
            }
            
            response = self.session.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            self.auth_token = result.get('token')
            
            self._log_api_call('POST', '/auth/login', data, result)
            logger.info("Sedo Authentifizierung erfolgreich")
            return True
            
        except Exception as e:
            logger.error(f"Sedo Authentifizierung fehlgeschlagen: {e}")
            return False
    
    def list_domain(self, config: ListingConfig) -> Dict[str, Any]:
        """Listet eine Domain auf Sedo"""
        if not self.auth_token:
            if not self.authenticate():
                return {'success': False, 'error': 'Authentifizierung fehlgeschlagen'}
        
        if self.sandbox:
            logger.info(f"[SANDBOX] Domain {config.domain} würde auf Sedo gelistet")
            mock_response = {
                'success': True,
                'listing_id': f"SEDO_SB_{hashlib.md5(config.domain.encode()).hexdigest()[:10]}",
                'domain': config.domain,
                'price': config.start_price,
                'url': f"https://sedo.com/search/?keyword={config.domain}",
                'sandbox': True
            }
            self._save_listing_to_db(config, 'sedo', mock_response)
            return mock_response
        
        try:
            url = f"{self.base_url}/domains/list"
            headers = {
                'X-API-KEY': self.api_key,
                'Authorization': f'Bearer {self.auth_token}'
            }
            
            payload = {
                'domain': config.domain,
                'price': config.start_price,
                'min_price': config.min_price,
                'currency': config.currency,
                'buy_now': config.buy_now_price,
                'category': config.category or 'General',
                'description': config.description or f"Premium domain: {config.domain}"
            }
            
            response = self.session.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            self._log_api_call('POST', '/domains/list', payload, result)
            
            self._save_listing_to_db(config, 'sedo', result)
            logger.info(f"Domain {config.domain} erfolgreich auf Sedo gelistet")
            return result
            
        except Exception as e:
            logger.error(f"Fehler beim Sedo Listing: {e}")
            return {'success': False, 'error': str(e)}
    
    def update_price(self, domain: str, new_price: float) -> bool:
        """Aktualisiert den Preis auf Sedo"""
        if self.sandbox:
            logger.info(f"[SANDBOX] Preis für {domain} würde auf ${new_price} geändert")
            self._save_price_history(domain, 'sedo', new_price, "Manual update (sandbox)")
            return True
            
        try:
            url = f"{self.base_url}/domains/{domain}/price"
            headers = {
                'X-API-KEY': self.api_key,
                'Authorization': f'Bearer {self.auth_token}'
            }
            
            payload = {'price': new_price}
            response = self.session.put(url, headers=headers, json=payload)
            response.raise_for_status()
            
            self._save_price_history(domain, 'sedo', new_price, "API update")
            logger.info(f"Preis für {domain} auf Sedo aktualisiert: ${new_price}")
            return True
            
        except Exception as e:
            logger.error(f"Fehler bei Sedo Preis-Update: {e}")
            return False
    
    def get_listing_status(self, domain: str) -> Dict[str, Any]:
        """Holt Listing-Status von Sedo"""
        if self.sandbox:
            return {
                'domain': domain,
                'status': 'active',
                'price': 1000,
                'offers': 0,
                'views': 42,
                'sandbox': True
            }
            
        try:
            url = f"{self.base_url}/domains/{domain}"
            headers = {'Authorization': f'Bearer {self.auth_token}'}
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Sedo Status: {e}")
            return {'error': str(e)}
    
    def delete_listing(self, domain: str) -> bool:
        """Löscht ein Sedo Listing"""
        if self.sandbox:
            logger.info(f"[SANDBOX] Listing für {domain} würde gelöscht")
            return True
            
        try:
            url = f"{self.base_url}/domains/{domain}"
            headers = {'Authorization': f'Bearer {self.auth_token}'}
            response = self.session.delete(url, headers=headers)
            response.raise_for_status()
            logger.info(f"Listing für {domain} von Sedo entfernt")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Sedo Listings: {e}")
            return False
    
    def _save_listing_to_db(self, config: ListingConfig, platform: str, response: dict):
        """Speichert Listing in Datenbank"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO listings 
            (domain_name, platform, listing_id, status, start_price, current_price, 
             min_price, buy_now_price, currency, listed_at, platform_listing_url, 
             api_response, is_sandbox, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            config.domain, platform, response.get('listing_id'), 'active',
            config.start_price, config.start_price, config.min_price, config.buy_now_price,
            config.currency, now, response.get('url'), json.dumps(response),
            1 if self.sandbox else 0, now, now
        ))
        
        conn.commit()
        conn.close()
    
    def _save_price_history(self, domain: str, platform: str, new_price: float, reason: str):
        """Speichert Preis-Änderung in Historie"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Hole alten Preis
        cursor.execute('''
            SELECT current_price FROM listings 
            WHERE domain_name = ? AND platform = ?
        ''', (domain, platform))
        row = cursor.fetchone()
        old_price = row[0] if row else None
        
        cursor.execute('''
            INSERT INTO price_history 
            (domain_name, platform, old_price, new_price, change_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (domain, platform, old_price, new_price, reason, datetime.now().isoformat()))
        
        cursor.execute('''
            UPDATE listings SET current_price = ?, last_price_update = ?
            WHERE domain_name = ? AND platform = ?
        ''', (new_price, datetime.now().isoformat(), domain, platform))
        
        conn.commit()
        conn.close()


# ==================== AFTERNIC API ====================

class AfternicAPI(MarketplaceAPI):
    """
    Afternic API Integration (GoDaddy Tochter)
    
    Dokumentation: https://developer.godaddy.com/doc/endpoint/aftermarket
    Sandbox: https://api.ote-godaddy.com/
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None,
                 sandbox: bool = True):
        super().__init__(sandbox)
        self.api_key = api_key or os.getenv('AFTERNIC_API_KEY') or os.getenv('GODADDY_API_KEY')
        self.api_secret = api_secret or os.getenv('AFTERNIC_API_SECRET') or os.getenv('GODADDY_API_SECRET')
        
    def _get_base_url(self) -> str:
        if self.sandbox:
            return "https://api.ote-godaddy.com/v1/aftermarket"
        return "https://api.godaddy.com/v1/aftermarket"
    
    def authenticate(self) -> bool:
        """Authentifiziert mit Afternic/GoDaddy API"""
        if self.sandbox:
            logger.info("[SANDBOX] Afternic Authentifizierung simuliert")
            return True
            
        # GoDaddy nutzt API-Key/Secret als Basic Auth
        if self.api_key and self.api_secret:
            self.session.headers.update({
                'Authorization': f'sso-key {self.api_key}:{self.api_secret}'
            })
            return True
        return False
    
    def list_domain(self, config: ListingConfig) -> Dict[str, Any]:
        """Listet eine Domain auf Afternic"""
        if not self.authenticate():
            return {'success': False, 'error': 'Authentifizierung fehlgeschlagen'}
        
        if self.sandbox:
            logger.info(f"[SANDBOX] Domain {config.domain} würde auf Afternic gelistet")
            mock_response = {
                'success': True,
                'listing_id': f"AFTERNIC_SB_{hashlib.md5(config.domain.encode()).hexdigest()[:10]}",
                'domain': config.domain,
                'price': config.start_price,
                'url': f"https://afternic.com/domain/{config.domain}",
                'sandbox': True
            }
            self._save_listing_to_db(config, 'afternic', mock_response)
            return mock_response
        
        try:
            url = f"{self.base_url}/listings"
            
            payload = {
                'domain': config.domain,
                'price': config.start_price,
                'currency': config.currency,
                'category': config.category or 'Business'
            }
            
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            self._save_listing_to_db(config, 'afternic', result)
            logger.info(f"Domain {config.domain} erfolgreich auf Afternic gelistet")
            return result
            
        except Exception as e:
            logger.error(f"Fehler beim Afternic Listing: {e}")
            return {'success': False, 'error': str(e)}
    
    def update_price(self, domain: str, new_price: float) -> bool:
        """Aktualisiert den Preis auf Afternic"""
        if self.sandbox:
            logger.info(f"[SANDBOX] Preis für {domain} auf Afternic würde geändert zu ${new_price}")
            return True
            
        try:
            url = f"{self.base_url}/listings/{domain}"
            payload = {'price': new_price}
            response = self.session.put(url, json=payload)
            response.raise_for_status()
            logger.info(f"Preis für {domain} auf Afternic aktualisiert: ${new_price}")
            return True
        except Exception as e:
            logger.error(f"Fehler bei Afternic Preis-Update: {e}")
            return False
    
    def get_listing_status(self, domain: str) -> Dict[str, Any]:
        """Holt Listing-Status von Afternic"""
        if self.sandbox:
            return {
                'domain': domain,
                'status': 'active',
                'price': 1000,
                'offers': 0,
                'sandbox': True
            }
            
        try:
            url = f"{self.base_url}/listings/{domain}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Afternic Status: {e}")
            return {'error': str(e)}
    
    def delete_listing(self, domain: str) -> bool:
        """Löscht ein Afternic Listing"""
        if self.sandbox:
            logger.info(f"[SANDBOX] Afternic Listing für {domain} würde gelöscht")
            return True
            
        try:
            url = f"{self.base_url}/listings/{domain}"
            response = self.session.delete(url)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Afternic Listings: {e}")
            return False
    
    def _save_listing_to_db(self, config: ListingConfig, platform: str, response: dict):
        """Speichert Listing in Datenbank"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO listings 
            (domain_name, platform, listing_id, status, start_price, current_price, 
             min_price, buy_now_price, currency, listed_at, platform_listing_url, 
             api_response, is_sandbox, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            config.domain, platform, response.get('listing_id'), 'active',
            config.start_price, config.start_price, config.min_price, config.buy_now_price,
            config.currency, now, response.get('url'), json.dumps(response),
            1 if self.sandbox else 0, now, now
        ))
        
        conn.commit()
        conn.close()


# ==================== DAN.COM API ====================

class DanAPI(MarketplaceAPI):
    """
    Dan.com API Integration
    
    Dokumentation: https://docs.dan.com/
    Sandbox: Verfügbar über Test-Account
    """
    
    def __init__(self, api_key: Optional[str] = None, sandbox: bool = True):
        super().__init__(sandbox)
        self.api_key = api_key or os.getenv('DAN_API_KEY')
        
    def _get_base_url(self) -> str:
        if self.sandbox:
            return "https://api.dan.com/sandbox/v1"
        return "https://api.dan.com/v1"
    
    def authenticate(self) -> bool:
        """Authentifiziert mit Dan.com API"""
        if self.sandbox:
            logger.info("[SANDBOX] Dan.com Authentifizierung simuliert")
            return True
            
        if self.api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            })
            return True
        return False
    
    def list_domain(self, config: ListingConfig) -> Dict[str, Any]:
        """Listet eine Domain auf Dan.com"""
        if not self.authenticate():
            return {'success': False, 'error': 'Authentifizierung fehlgeschlagen'}
        
        if self.sandbox:
            logger.info(f"[SANDBOX] Domain {config.domain} würde auf Dan.com gelistet")
            mock_response = {
                'success': True,
                'listing_id': f"DAN_SB_{hashlib.md5(config.domain.encode()).hexdigest()[:10]}",
                'domain': config.domain,
                'price': config.start_price,
                'url': f"https://dan.com/buy-domain/{config.domain}",
                'sandbox': True
            }
            self._save_listing_to_db(config, 'dan', mock_response)
            return mock_response
        
        try:
            url = f"{self.base_url}/domains"
            
            payload = {
                'domain': config.domain,
                'buy_now_price': config.buy_now_price or config.start_price,
                'minimum_offer': config.min_price,
                'currency': config.currency,
                'description': config.description or ''
            }
            
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            self._save_listing_to_db(config, 'dan', result)
            logger.info(f"Domain {config.domain} erfolgreich auf Dan.com gelistet")
            return result
            
        except Exception as e:
            logger.error(f"Fehler beim Dan.com Listing: {e}")
            return {'success': False, 'error': str(e)}
    
    def update_price(self, domain: str, new_price: float) -> bool:
        """Aktualisiert den Preis auf Dan.com"""
        if self.sandbox:
            logger.info(f"[SANDBOX] Preis für {domain} auf Dan.com würde geändert zu ${new_price}")
            return True
            
        try:
            url = f"{self.base_url}/domains/{domain}"
            payload = {'buy_now_price': new_price}
            response = self.session.put(url, json=payload)
            response.raise_for_status()
            logger.info(f"Preis für {domain} auf Dan.com aktualisiert: ${new_price}")
            return True
        except Exception as e:
            logger.error(f"Fehler bei Dan.com Preis-Update: {e}")
            return False
    
    def get_listing_status(self, domain: str) -> Dict[str, Any]:
        """Holt Listing-Status von Dan.com"""
        if self.sandbox:
            return {
                'domain': domain,
                'status': 'active',
                'price': 1000,
                'offers': 0,
                'views': 25,
                'sandbox': True
            }
            
        try:
            url = f"{self.base_url}/domains/{domain}"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Dan.com Status: {e}")
            return {'error': str(e)}
    
    def delete_listing(self, domain: str) -> bool:
        """Löscht ein Dan.com Listing"""
        if self.sandbox:
            logger.info(f"[SANDBOX] Dan.com Listing für {domain} würde gelöscht")
            return True
            
        try:
            url = f"{self.base_url}/domains/{domain}"
            response = self.session.delete(url)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Dan.com Listings: {e}")
            return False
    
    def _save_listing_to_db(self, config: ListingConfig, platform: str, response: dict):
        """Speichert Listing in Datenbank"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO listings 
            (domain_name, platform, listing_id, status, start_price, current_price, 
             min_price, buy_now_price, currency, listed_at, platform_listing_url, 
             api_response, is_sandbox, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            config.domain, platform, response.get('listing_id'), 'active',
            config.start_price, config.start_price, config.min_price, config.buy_now_price,
            config.currency, now, response.get('url'), json.dumps(response),
            1 if self.sandbox else 0, now, now
        ))
        
        conn.commit()
        conn.close()


# ==================== PREIS-OPTIMIERUNG ====================

class PriceOptimizer:
    """
    Preis-Optimierungs-Engine
    
    Features:
    - Startpreis basierend auf Bewertung
    - Dynamische Preis-Anpassung (alle 7 Tage -5%)
    - Mindestpreis-Schutz
    """
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.price_reduction_percent = 5  # 5% alle 7 Tage
        self.reduction_interval_days = 7
        
    def calculate_start_price(self, domain: str, valuation_score: float, 
                             base_multiplier: float = 10.0) -> float:
        """
        Berechnet den optimalen Startpreis basierend auf der Bewertung
        
        Args:
            domain: Domain-Name
            valuation_score: Bewertungspunktzahl (0-100)
            base_multiplier: Basis-Multiplikator für den Preis
        
        Returns:
            Empfohlener Startpreis in USD
        """
        # Basis-Preis basierend auf Score
        # Score 0-100 -> Multiplikator 1x bis 50x
        score_multiplier = 1 + (valuation_score / 100) * 49
        
        # TLD-Premium
        tld_multiplier = self._get_tld_multiplier(domain)
        
        # Längen-Faktor (kürzer = teurer)
        length_factor = self._get_length_factor(domain)
        
        # Keyword-Premium
        keyword_multiplier = self._get_keyword_multiplier(domain)
        
        # Berechne finalen Preis
        base_price = 100  # Mindestpreis $100
        final_price = base_price * score_multiplier * tld_multiplier * length_factor * keyword_multiplier
        
        # Runde auf schöne Zahlen
        if final_price < 500:
            final_price = round(final_price / 50) * 50
        elif final_price < 2000:
            final_price = round(final_price / 100) * 100
        elif final_price < 10000:
            final_price = round(final_price / 500) * 500
        else:
            final_price = round(final_price / 1000) * 1000
        
        logger.info(f"Startpreis für {domain}: ${final_price:.0f} "
                   f"(Score: {valuation_score}, Multiplikatoren: "
                   f"TLD:{tld_multiplier:.1f}, Länge:{length_factor:.1f}, Keyword:{keyword_multiplier:.1f})")
        
        return final_price
    
    def _get_tld_multiplier(self, domain: str) -> float:
        """TLD-Premium-Multiplikator"""
        tld_premiums = {
            '.com': 2.0,
            '.ai': 1.8,
            '.io': 1.6,
            '.co': 1.4,
            '.de': 1.3,
            '.net': 1.2,
            '.org': 1.1,
            '.app': 1.3,
            '.dev': 1.2,
            '.cloud': 1.1,
        }
        
        for tld, multiplier in tld_premiums.items():
            if domain.endswith(tld):
                return multiplier
        return 1.0
    
    def _get_length_factor(self, domain: str) -> float:
        """Längen-Faktor (kürzer = wertvoller)"""
        name = domain.split('.')[0]
        length = len(name)
        
        if length <= 4:
            return 2.0
        elif length <= 6:
            return 1.5
        elif length <= 10:
            return 1.2
        elif length <= 15:
            return 1.0
        else:
            return 0.8
    
    def _get_keyword_multiplier(self, domain: str) -> float:
        """Keyword-Premium-Multiplikator"""
        name = domain.split('.')[0].lower()
        
        premium_keywords = {
            'ai': 2.0,
            'crypto': 1.8,
            'cloud': 1.6,
            'tech': 1.5,
            'app': 1.5,
            'data': 1.4,
            'smart': 1.3,
            'digital': 1.3,
            'bot': 1.3,
            'pay': 1.5,
            'shop': 1.4,
            'market': 1.3,
            'pro': 1.2,
            'go': 1.2,
            'get': 1.1,
        }
        
        multiplier = 1.0
        for keyword, factor in premium_keywords.items():
            if keyword in name:
                multiplier = max(multiplier, factor)
        
        return multiplier
    
    def calculate_min_price(self, start_price: float, min_percent: float = 40.0) -> float:
        """
        Berechnet den Mindestpreis
        
        Args:
            start_price: Startpreis
            min_percent: Prozentsatz des Startpreises als Minimum
        
        Returns:
            Mindestpreis
        """
        min_price = start_price * (min_percent / 100)
        return round(min_price / 10) * 10  # Runde auf $10
    
    def should_reduce_price(self, domain: str, platform: str) -> bool:
        """
        Prüft, ob der Preis reduziert werden sollte
        
        Returns:
            True wenn Preisreduktion fällig
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT last_price_update, listed_at, current_price, min_price
            FROM listings
            WHERE domain_name = ? AND platform = ? AND status = 'active'
        ''', (domain, platform))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return False
        
        last_update_str, listed_at_str, current_price, min_price = row
        
        # Parse Datum
        last_update = datetime.fromisoformat(last_update_str or listed_at_str)
        
        # Prüfe ob 7 Tage vergangen sind
        days_since_update = (datetime.now() - last_update).days
        
        if days_since_update < self.reduction_interval_days:
            return False
        
        # Prüfe ob Mindestpreis noch nicht erreicht
        new_price = current_price * (1 - self.price_reduction_percent / 100)
        
        if new_price < min_price:
            logger.info(f"Mindestpreis für {domain} auf {platform} erreicht, keine weitere Reduktion")
            return False
        
        return True
    
    def get_new_price(self, domain: str, platform: str) -> Optional[float]:
        """
        Berechnet den neuen Preis nach Reduktion
        
        Returns:
            Neuer Preis oder None wenn keine Reduktion möglich
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT current_price, min_price
            FROM listings
            WHERE domain_name = ? AND platform = ? AND status = 'active'
        ''', (domain, platform))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        current_price, min_price = row
        new_price = current_price * (1 - self.price_reduction_percent / 100)
        
        if new_price < min_price:
            return min_price
        
        # Runde auf schöne Zahl
        if new_price < 1000:
            new_price = round(new_price / 50) * 50
        else:
            new_price = round(new_price / 100) * 100
        
        return new_price
    
    def apply_price_reduction(self, domain: str, platform: str, 
                              api_client: MarketplaceAPI) -> bool:
        """
        Wendet eine Preisreduktion an
        
        Args:
            domain: Domain-Name
            platform: Plattform-Name
            api_client: API-Client für die Plattform
        
        Returns:
            True wenn erfolgreich
        """
        if not self.should_reduce_price(domain, platform):
            return False
        
        new_price = self.get_new_price(domain, platform)
        if not new_price:
            return False
        
        success = api_client.update_price(domain, new_price)
        
        if success:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Speichere in Historie
            cursor.execute('''
                SELECT current_price FROM listings
                WHERE domain_name = ? AND platform = ?
            ''', (domain, platform))
            row = cursor.fetchone()
            old_price = row[0] if row else None
            
            cursor.execute('''
                INSERT INTO price_history
                (domain_name, platform, old_price, new_price, change_reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (domain, platform, old_price, new_price, 
                  f"Automatische Reduktion nach {self.reduction_interval_days} Tagen",
                  datetime.now().isoformat()))
            
            cursor.execute('''
                UPDATE listings
                SET current_price = ?, last_price_update = ?
                WHERE domain_name = ? AND platform = ?
            ''', (new_price, datetime.now().isoformat(), domain, platform))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Preis für {domain} auf {platform} reduziert: ${old_price} -> ${new_price}")
            return True
        
        return False
    
    def run_price_optimization(self):
        """Führt Preis-Optimierung für alle aktiven Listings durch"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT domain_name, platform
            FROM listings
            WHERE status = 'active' AND is_sandbox = 1
        ''')
        
        listings = cursor.fetchall()
        conn.close()
        
        api_clients = {
            'sedo': SedoAPI(sandbox=True),
            'afternic': AfternicAPI(sandbox=True),
            'dan': DanAPI(sandbox=True)
        }
        
        reductions_applied = 0
        
        for domain, platform in listings:
            if platform in api_clients:
                if self.apply_price_reduction(domain, platform, api_clients[platform]):
                    reductions_applied += 1
        
        logger.info(f"Preis-Optimierung abgeschlossen: {reductions_applied} Reduktionen angewendet")
        return reductions_applied


# ==================== WHOIS LOOKUP ====================

class WhoisLookup:
    """WHOIS Lookup für ähnliche Domains"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.cache_duration_days = 30
    
    def lookup(self, domain: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Führt WHOIS-Lookup durch
        
        Args:
            domain: Zu prüfende Domain
            use_cache: Cache verwenden wenn verfügbar
        
        Returns:
            WHOIS-Daten als Dictionary
        """
        # Prüfe Cache
        if use_cache:
            cached = self._get_cached_whois(domain)
            if cached:
                return cached
        
        # In einer echten Implementierung würde hier ein WHOIS-Client aufgerufen
        # z.B. python-whois oder whoisxmlapi
        # Hier simulieren wir die Daten
        
        logger.info(f"[SIMULATION] WHOIS-Lookup für {domain}")
        
        # Simulierte WHOIS-Daten
        result = {
            'domain_name': domain,
            'registrar': 'Example Registrar, LLC',
            'registrant_email': f"admin@{domain}",
            'registrant_name': 'Domain Administrator',
            'organization': f'{domain.split(".")[0].upper()} Inc.',
            'country': 'US',
            'created_date': (datetime.now() - timedelta(days=365*2)).isoformat(),
            'expiry_date': (datetime.now() + timedelta(days=365)).isoformat(),
            'cached_at': datetime.now().isoformat(),
            'is_available': False
        }
        
        self._cache_whois(result)
        return result
    
    def _get_cached_whois(self, domain: str) -> Optional[Dict[str, Any]]:
        """Holt gecachte WHOIS-Daten"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT domain_name, registrar, registrant_email, registrant_name,
                   organization, country, created_date, expiry_date, cached_at
            FROM whois_cache
            WHERE domain_name = ?
            AND cached_at > datetime('now', '-{} days')
        '''.format(self.cache_duration_days), (domain,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'domain_name': row[0],
                'registrar': row[1],
                'registrant_email': row[2],
                'registrant_name': row[3],
                'organization': row[4],
                'country': row[5],
                'created_date': row[6],
                'expiry_date': row[7],
                'cached_at': row[8],
                'is_available': False
            }
        return None
    
    def _cache_whois(self, data: Dict[str, Any]):
        """Speichert WHOIS-Daten im Cache"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO whois_cache
            (domain_name, registrar, registrant_email, registrant_name,
             organization, country, created_date, expiry_date, cached_at, is_available)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['domain_name'],
            data.get('registrar'),
            data.get('registrant_email'),
            data.get('registrant_name'),
            data.get('organization'),
            data.get('country'),
            data.get('created_date'),
            data.get('expiry_date'),
            data.get('cached_at'),
            1 if data.get('is_available') else 0
        ))
        
        conn.commit()
        conn.close()
    
    def find_similar_domains(self, domain: str) -> List[str]:
        """
        Findet ähnliche Domains basierend auf Keywords
        
        Args:
            domain: Ausgangs-Domain
        
        Returns:
            Liste ähnlicher Domains
        """
        name = domain.split('.')[0].lower()
        
        # Generiere ähnliche Domain-Varianten
        similar = []
        tlds = ['.com', '.io', '.ai', '.co', '.net']
        
        # Plural/Singular-Varianten
        if name.endswith('s'):
            similar.append(name[:-1] + '.com')
        else:
            similar.append(name + 's.com')
        
        # Präfix/Suffix-Varianten
        prefixes = ['get', 'my', 'the', 'go', 'try']
        suffixes = ['app', 'hq', 'hub', 'lab', 'pro']
        
        for prefix in prefixes:
            similar.append(f"{prefix}{name}.com")
        
        for suffix in suffixes:
            similar.append(f"{name}{suffix}.com")
        
        # Andere TLDs
        for tld in tlds:
            if not domain.endswith(tld):
                similar.append(f"{name}{tld}")
        
        return list(set(similar))[:10]  # Max 10 Domains


# ==================== OUTREACH AUTOMATION ====================

class EmailTemplate:
    """E-Mail Templates für Outreach"""
    
    TEMPLATES = {
        'initial_offer': {
            'subject': 'Premium Domain Available: {domain}',
            'body': '''Dear {recipient_name},

I hope this email finds you well. My name is Lars, and I represent a portfolio of premium domain names.

I noticed that you own {similar_domain}, which is closely related to {domain} - a premium domain that is currently available for acquisition.

Given your interest in the {industry} space, I believe {domain} could be a valuable addition to your digital assets:

✓ Brand alignment with your existing portfolio
✓ Strong SEO potential and memorability
✓ Instant credibility and authority in the {industry} sector

The domain is currently listed at ${price}, but I'm open to discussing terms that work for both parties.

Would you be interested in a brief conversation about acquiring {domain}?

Best regards,
Lars
Domain Investment Specialist

---
This is a one-time outreach. If you're not interested, please disregard this message.'''
        },
        
        'follow_up': {
            'subject': 'Re: Premium Domain {domain} - Price Reduction',
            'body': '''Dear {recipient_name},

I hope you're doing well. I wanted to follow up on my previous email regarding {domain}.

To make this opportunity more accessible, I'm prepared to offer a special price of ${new_price} (reduced from ${original_price}) for a limited time.

{domain} would complement your existing domain {similar_domain} perfectly and strengthen your position in the {industry} market.

If you have any questions or would like to discuss further, I'm happy to schedule a brief call at your convenience.

Best regards,
Lars'''
        },
        
        'final_call': {
            'subject': 'Last Call: {domain} - Final Opportunity',
            'body': '''Dear {recipient_name},

This is my final outreach regarding {domain}.

The domain has attracted significant interest, and I wanted to give you one last opportunity before it's acquired by another party.

Final offer: ${new_price}

Given your ownership of {similar_domain}, this could be a strategic acquisition for your business.

If you're interested, please let me know by {deadline}.

Best regards,
Lars'''
        }
    }
    
    @classmethod
    def render(cls, template_id: str, **kwargs) -> Tuple[str, str]:
        """
        Rendert ein Template
        
        Args:
            template_id: Template-Name
            **kwargs: Template-Variablen
        
        Returns:
            Tuple (subject, body)
        """
        template = cls.TEMPLATES.get(template_id, cls.TEMPLATES['initial_offer'])
        
        subject = template['subject'].format(**kwargs)
        body = template['body'].format(**kwargs)
        
        return subject, body


class OutreachAutomator:
    """Automatisiert Outreach an potenzielle Käufer"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.whois = WhoisLookup(db_path)
        self.gmail_user = GMAIL_USER
        self.gmail_password = GMAIL_PASSWORD
        
    def create_campaign(self, domain: str, template_id: str = 'initial_offer') -> int:
        """
        Erstellt eine neue Outreach-Kampagne
        
        Args:
            domain: Zu verkaufende Domain
            template_id: Zu verwendendes Template
        
        Returns:
            Campaign-ID
        """
        # Finde ähnliche Domains
        similar_domains = self.whois.find_similar_domains(domain)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Erstelle Kampagne
        cursor.execute('''
            INSERT INTO outreach_campaigns
            (domain_name, template_id, status, created_at)
            VALUES (?, ?, 'active', ?)
        ''', (domain, template_id, datetime.now().isoformat()))
        
        campaign_id = cursor.lastrowid
        
        # Füge Empfänger hinzu
        for similar_domain in similar_domains:
            cursor.execute('''
                INSERT INTO outreach_recipients
                (campaign_id, target_domain, email_sent)
                VALUES (?, ?, 0)
            ''', (campaign_id, similar_domain))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Outreach-Kampagne erstellt für {domain}: {len(similar_domains)} potenzielle Empfänger")
        return campaign_id
    
    def find_recipient_email(self, domain: str) -> Optional[str]:
        """
        Findet die E-Mail-Adresse des Domain-Inhabers
        
        Args:
            domain: Zu prüfende Domain
        
        Returns:
            E-Mail-Adresse oder None
        """
        whois_data = self.whois.lookup(domain)
        
        # In einer echten Implementierung würden hier verschiedene
        # Methoden verwendet werden:
        # 1. WHOIS-Daten
        # 2. Website-Kontaktseite scrapen
        # 3. Hunter.io API
        # 4. LinkedIn-Suche
        
        email = whois_data.get('registrant_email')
        
        # Validiere E-Mail
        if email and '@' in email and '.' in email:
            return email
        
        return None
    
    def send_outreach_email(self, campaign_id: int, recipient_id: int,
                           domain: str, target_domain: str,
                           price: float, template_id: str = 'initial_offer') -> bool:
        """
        Sendet Outreach-E-Mail
        
        Args:
            campaign_id: Kampagne-ID
            recipient_id: Empfänger-ID
            domain: Zu verkaufende Domain
            target_domain: Ziel-Domain des Empfängers
            price: Preis
            template_id: Template-Name
        
        Returns:
            True wenn erfolgreich
        """
        if not self.gmail_password:
            logger.error("GMAIL_APP_PASSWORD nicht gesetzt")
            return False
        
        # Finde E-Mail-Adresse
        recipient_email = self.find_recipient_email(target_domain)
        if not recipient_email:
            logger.warning(f"Keine E-Mail für {target_domain} gefunden")
            return False
        
        # Bestimme Industrie basierend auf Domain
        industry = self._detect_industry(domain)
        
        # Rendere Template
        subject, body = EmailTemplate.render(
            template_id,
            domain=domain,
            similar_domain=target_domain,
            recipient_name='Domain Owner',
            price=f"{price:.0f}",
            industry=industry
        )
        
        # Erstelle E-Mail
        msg = MIMEMultipart('alternative')
        msg['From'] = self.gmail_user
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg['X-Campaign-ID'] = str(campaign_id)
        msg['X-Recipient-ID'] = str(recipient_id)
        
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            # In Sandbox-Modus nur simulieren
            if os.getenv('OUTREACH_SANDBOX', 'true').lower() == 'true':
                logger.info(f"[SANDBOX] E-Mail würde gesendet an {recipient_email}")
                logger.info(f"  Betreff: {subject}")
                self._mark_email_sent(campaign_id, recipient_id, recipient_email, f"sandbox_{recipient_id}")
                return True
            
            # Sende E-Mail
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.gmail_user, self.gmail_password)
            
            message_id = hashlib.md5(f"{campaign_id}_{recipient_id}_{time.time()}".encode()).hexdigest()
            msg['Message-ID'] = f"<{message_id}@domainflipper.local>"
            
            server.send_message(msg)
            server.quit()
            
            self._mark_email_sent(campaign_id, recipient_id, recipient_email, message_id)
            
            logger.info(f"Outreach-E-Mail gesendet an {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Fehler beim Senden der E-Mail: {e}")
            return False
    
    def _mark_email_sent(self, campaign_id: int, recipient_id: int, 
                         email: str, message_id: str):
        """Markiert E-Mail als gesendet"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE outreach_recipients
            SET recipient_email = ?, message_id = ?, email_sent = 1, sent_at = ?
            WHERE id = ?
        ''', (email, message_id, datetime.now().isoformat(), recipient_id))
        
        cursor.execute('''
            UPDATE outreach_campaigns
            SET emails_sent = emails_sent + 1, last_sent_at = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), campaign_id))
        
        conn.commit()
        conn.close()
    
    def _detect_industry(self, domain: str) -> str:
        """Erkennt die Industrie basierend auf der Domain"""
        name = domain.split('.')[0].lower()
        
        industries = {
            'ai': 'Artificial Intelligence',
            'crypto': 'Cryptocurrency',
            'cloud': 'Cloud Computing',
            'tech': 'Technology',
            'health': 'Healthcare',
            'finance': 'Financial Services',
            'shop': 'E-Commerce',
            'pay': 'Fintech',
            'data': 'Data Analytics',
            'app': 'Mobile Applications',
        }
        
        for keyword, industry in industries.items():
            if keyword in name:
                return industry
        
        return 'Technology'
    
    def run_campaign(self, campaign_id: int, max_emails: int = 10) -> int:
        """
        Führt eine Outreach-Kampagne aus
        
        Args:
            campaign_id: Kampagne-ID
            max_emails: Maximale Anzahl E-Mails
        
        Returns:
            Anzahl gesendeter E-Mails
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Hole Kampagnen-Details
        cursor.execute('''
            SELECT domain_name, template_id
            FROM outreach_campaigns
            WHERE id = ? AND status = 'active'
        ''', (campaign_id,))
        
        row = cursor.fetchone()
        if not row:
            logger.error(f"Kampagne {campaign_id} nicht gefunden oder nicht aktiv")
            conn.close()
            return 0
        
        domain, template_id = row
        
        # Hole aktuellen Preis
        cursor.execute('''
            SELECT current_price FROM listings
            WHERE domain_name = ? AND status = 'active'
            ORDER BY listed_at DESC
            LIMIT 1
        ''', (domain,))
        
        price_row = cursor.fetchone()
        price = price_row[0] if price_row else 1000
        
        # Hole unberührte Empfänger
        cursor.execute('''
            SELECT id, target_domain
            FROM outreach_recipients
            WHERE campaign_id = ? AND email_sent = 0
            LIMIT ?
        ''', (campaign_id, max_emails))
        
        recipients = cursor.fetchall()
        conn.close()
        
        sent_count = 0
        
        for recipient_id, target_domain in recipients:
            if self.send_outreach_email(campaign_id, recipient_id, domain, 
                                       target_domain, price, template_id):
                sent_count += 1
                time.sleep(2)  # Rate limiting
        
        logger.info(f"Kampagne {campaign_id}: {sent_count} E-Mails gesendet")
        return sent_count
    
    def track_reply(self, message_id: str, replied: bool = True):
        """Tracked eine Antwort auf eine Outreach-E-Mail"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE outreach_recipients
            SET replied = ?, replied_at = ?
            WHERE message_id = ?
        ''', (1 if replied else 0, datetime.now().isoformat() if replied else None, message_id))
        
        if replied and cursor.rowcount > 0:
            # Aktualisiere Kampagnen-Statistik
            cursor.execute('''
                UPDATE outreach_campaigns
                SET replies_received = replies_received + 1
                WHERE id = (SELECT campaign_id FROM outreach_recipients WHERE message_id = ?)
            ''', (message_id,))
        
        conn.commit()
        conn.close()
    
    def get_campaign_stats(self, campaign_id: int) -> Dict[str, Any]:
        """Holt Statistiken für eine Kampagne"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT domain_name, template_id, status, emails_sent, emails_opened, 
                   replies_received, created_at
            FROM outreach_campaigns
            WHERE id = ?
        ''', (campaign_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {}
        
        stats = {
            'domain': row[0],
            'template': row[1],
            'status': row[2],
            'emails_sent': row[3],
            'emails_opened': row[4],
            'replies': row[5],
            'created_at': row[6]
        }
        
        # Berechne Raten
        if stats['emails_sent'] > 0:
            stats['open_rate'] = (stats['emails_opened'] / stats['emails_sent']) * 100
            stats['reply_rate'] = (stats['replies'] / stats['emails_sent']) * 100
        else:
            stats['open_rate'] = 0
            stats['reply_rate'] = 0
        
        conn.close()
        return stats


# ==================== MAIN AUTO-LISTING MANAGER ====================

class AutoListingManager:
    """
    Haupt-Manager für automatisches Domain-Listing
    
    Koordiniert alle Komponenten:
    - API-Integrationen (Sedo, Afternic, Dan.com)
    - Preis-Optimierung
    - Outreach-Automatisierung
    """
    
    def __init__(self, sandbox: bool = True):
        self.sandbox = sandbox
        self.apis = {
            'sedo': SedoAPI(sandbox=sandbox),
            'afternic': AfternicAPI(sandbox=sandbox),
            'dan': DanAPI(sandbox=sandbox)
        }
        self.price_optimizer = PriceOptimizer()
        self.outreach = OutreachAutomator()
        
        # Initialisiere Datenbank
        init_auto_listing_db()
    
    def list_domain_on_all_platforms(self, domain: str, valuation_score: float,
                                     description: Optional[str] = None) -> Dict[str, Any]:
        """
        Listet eine Domain auf allen verfügbaren Plattformen
        
        Args:
            domain: Zu listende Domain
            valuation_score: Bewertungspunktzahl (0-100)
            description: Optionale Beschreibung
        
        Returns:
            Ergebnisse pro Plattform
        """
        # Berechne Preise
        start_price = self.price_optimizer.calculate_start_price(domain, valuation_score)
        min_price = self.price_optimizer.calculate_min_price(start_price)
        buy_now_price = start_price * 1.1  # 10% Premium für Buy-Now
        
        results = {}
        
        for platform_name, api in self.apis.items():
            config = ListingConfig(
                domain=domain,
                platform=platform_name,
                start_price=start_price,
                min_price=min_price,
                buy_now_price=buy_now_price,
                description=description or f"Premium domain: {domain}"
            )
            
            result = api.list_domain(config)
            results[platform_name] = result
            
            if result.get('success'):
                logger.info(f"✓ {domain} erfolgreich auf {platform_name} gelistet: ${start_price}")
            else:
                logger.error(f"✗ Fehler beim Listing auf {platform_name}: {result.get('error')}")
        
        return results
    
    def create_outreach_campaign(self, domain: str) -> int:
        """
        Erstellt eine Outreach-Kampagne für eine Domain
        
        Args:
            domain: Zu bewerbende Domain
        
        Returns:
            Campaign-ID
        """
        campaign_id = self.outreach.create_campaign(domain)
        return campaign_id
    
    def run_price_optimization(self) -> int:
        """Führt Preis-Optimierung für alle Listings durch"""
        return self.price_optimizer.run_price_optimization()
    
    def get_listing_summary(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Holt Zusammenfassung aller Listings
        
        Args:
            domain: Optional Filter nach Domain
        
        Returns:
            Liste aller Listings
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if domain:
            cursor.execute('''
                SELECT domain_name, platform, status, current_price, min_price,
                       listed_at, last_price_update, is_sandbox
                FROM listings
                WHERE domain_name = ?
                ORDER BY listed_at DESC
            ''', (domain,))
        else:
            cursor.execute('''
                SELECT domain_name, platform, status, current_price, min_price,
                       listed_at, last_price_update, is_sandbox
                FROM listings
                ORDER BY listed_at DESC
            ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        listings = []
        for row in rows:
            listings.append({
                'domain': row[0],
                'platform': row[1],
                'status': row[2],
                'current_price': row[3],
                'min_price': row[4],
                'listed_at': row[5],
                'last_price_update': row[6],
                'is_sandbox': bool(row[7])
            })
        
        return listings
    
    def remove_listing(self, domain: str, platform: Optional[str] = None) -> bool:
        """
        Entfernt ein oder alle Listings für eine Domain
        
        Args:
            domain: Zu entfernende Domain
            platform: Optional nur eine Plattform
        
        Returns:
            True wenn erfolgreich
        """
        if platform:
            if platform in self.apis:
                success = self.apis[platform].delete_listing(domain)
                if success:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE listings SET status = 'deleted', updated_at = ?
                        WHERE domain_name = ? AND platform = ?
                    ''', (datetime.now().isoformat(), domain, platform))
                    conn.commit()
                    conn.close()
                return success
            return False
        else:
            # Entferne von allen Plattformen
            all_success = True
            for platform_name, api in self.apis.items():
                if not api.delete_listing(domain):
                    all_success = False
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE listings SET status = 'deleted', updated_at = ?
                WHERE domain_name = ?
            ''', (datetime.now().isoformat(), domain))
            conn.commit()
            conn.close()
            
            return all_success


# ==================== CLI / MAIN ====================

def main():
    """Hauptfunktion für CLI-Usage"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Auto-Listing & Verkaufs-Automatisierung für Domain Flipping'
    )
    parser.add_argument('--sandbox', action='store_true', default=True,
                       help='Sandbox-Modus verwenden (Standard: True)')
    parser.add_argument('--production', action='store_true',
                       help='Produktions-Modus (NICHT verwenden ohne Approval!)')
    
    subparsers = parser.add_subparsers(dest='command', help='Verfügbare Befehle')
    
    # List-Befehl
    list_parser = subparsers.add_parser('list', help='Domain auf Marktplätzen listen')
    list_parser.add_argument('domain', help='Zu listende Domain')
    list_parser.add_argument('--score', type=float, default=50,
                            help='Bewertungspunktzahl (0-100)')
    list_parser.add_argument('--description', help='Beschreibung der Domain')
    
    # Optimize-Befehl
    optimize_parser = subparsers.add_parser('optimize', 
                                            help='Preis-Optimierung durchführen')
    
    # Outreach-Befehl
    outreach_parser = subparsers.add_parser('outreach', 
                                             help='Outreach-Kampagne erstellen/ausführen')
    outreach_parser.add_argument('domain', help='Domain für Outreach')
    outreach_parser.add_argument('--create', action='store_true',
                                help='Neue Kampagne erstellen')
    outreach_parser.add_argument('--campaign-id', type=int,
                                help='Bestehende Kampagne ausführen')
    outreach_parser.add_argument('--max-emails', type=int, default=10,
                                help='Maximale Anzahl E-Mails')
    
    # Status-Befehl
    status_parser = subparsers.add_parser('status', help='Listing-Status anzeigen')
    status_parser.add_argument('--domain', help='Filter nach Domain')
    
    # Remove-Befehl
    remove_parser = subparsers.add_parser('remove', help='Listing entfernen')
    remove_parser.add_argument('domain', help='Zu entfernende Domain')
    remove_parser.add_argument('--platform', choices=['sedo', 'afternic', 'dan'],
                              help='Nur eine Plattform')
    
    args = parser.parse_args()
    
    # Sandbox-Modus bestimmen
    sandbox = not args.production
    if not sandbox:
        print("⚠️  WARNUNG: Produktions-Modus aktiviert!")
        confirm = input("Bist du sicher? (ja/nein): ")
        if confirm.lower() != 'ja':
            print("Abgebrochen.")
            return
    
    # Manager initialisieren
    manager = AutoListingManager(sandbox=sandbox)
    
    if args.command == 'list':
        results = manager.list_domain_on_all_platforms(
            args.domain, args.score, args.description
        )
        
        print(f"\n📋 Listing-Ergebnisse für {args.domain}:")
        print("-" * 50)
        for platform, result in results.items():
            status = "✅" if result.get('success') else "❌"
            print(f"{status} {platform}: {result.get('listing_id', 'Fehler')}")
            if result.get('error'):
                print(f"   Fehler: {result['error']}")
    
    elif args.command == 'optimize':
        count = manager.run_price_optimization()
        print(f"\n💰 Preis-Optimierung abgeschlossen: {count} Reduktionen angewendet")
    
    elif args.command == 'outreach':
        if args.create:
            campaign_id = manager.create_outreach_campaign(args.domain)
            print(f"\n📧 Outreach-Kampagne erstellt: ID {campaign_id}")
            print(f"   Führe aus mit: python auto_listing.py outreach {args.domain} --campaign-id {campaign_id}")
        elif args.campaign_id:
            sent = manager.outreach.run_campaign(args.campaign_id, args.max_emails)
            print(f"\n📧 {sent} Outreach-E-Mails gesendet")
        else:
            print("Bitte --create oder --campaign-id angeben")
    
    elif args.command == 'status':
        listings = manager.get_listing_summary(args.domain)
        
        print(f"\n📊 Listing-Status:")
        print("-" * 80)
        print(f"{'Domain':<30} {'Plattform':<12} {'Status':<10} {'Preis':<12} {'Modus'}")
        print("-" * 80)
        
        for listing in listings:
            mode = "🧪 Sandbox" if listing['is_sandbox'] else "🚀 Live"
            print(f"{listing['domain']:<30} {listing['platform']:<12} "
                  f"{listing['status']:<10} ${listing['current_price']:<11.0f} {mode}")
    
    elif args.command == 'remove':
        success = manager.remove_listing(args.domain, args.platform)
        if success:
            print(f"\n✅ Listing für {args.domain} entfernt")
        else:
            print(f"\n❌ Fehler beim Entfernen")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
