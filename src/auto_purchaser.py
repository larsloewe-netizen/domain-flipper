#!/usr/bin/env python3
"""
Auto-Purchasing System für Domain Flipping
Integriert Namecheap und Dynadot APIs mit Safety-Features
"""

import os
import re
import json
import yaml
import time
import sqlite3
import logging
import smtplib
import requests
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from abc import ABC, abstractmethod

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/root/.openclaw/workspace/projects/domain-flipper/logs/purchases.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('AutoPurchaser')


@dataclass
class PurchaseAttempt:
    """Protokolliert einen Kaufversuch"""
    domain: str
    price: float
    score: int
    provider: str
    success: bool
    timestamp: str
    error_message: Optional[str] = None
    transaction_id: Optional[str] = None
    requires_manual_approval: bool = False
    sandbox_mode: bool = True
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PurchaseLimits:
    """Aktuelle Limit-Status"""
    daily_domains: int
    daily_amount: float
    weekly_domains: int
    weekly_amount: float
    monthly_domains: int
    monthly_amount: float
    remaining_daily_domains: int
    remaining_daily_amount: float
    

class RegistrarAPI(ABC):
    """Abstrakte Basisklasse für Registrar APIs"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sandbox = config.get('sandbox', True)
        self.enabled = config.get('enabled', False)
    
    @abstractmethod
    def check_availability(self, domain: str) -> Tuple[bool, Optional[float]]:
        """Prüft ob Domain verfügbar ist, gibt (verfügbar, preis) zurück"""
        pass
    
    @abstractmethod
    def purchase_domain(self, domain: str, years: int = 1) -> Tuple[bool, Optional[str], Optional[str]]:
        """Kauft Domain, gibt (success, transaction_id, error) zurück"""
        pass
    
    @abstractmethod
    def get_balance(self) -> Optional[float]:
        """Gibt aktuelles Guthaben zurück"""
        pass


class NamecheapAPI(RegistrarAPI):
    """Namecheap API Integration mit Sandbox-Support"""
    
    SANDBOX_URL = "https://api.sandbox.namecheap.com/xml.response"
    PRODUCTION_URL = "https://api.namecheap.com/xml.response"
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_user = config.get('api_user', '')
        self.api_key = config.get('api_key', '')
        self.username = config.get('username', '')
        self.client_ip = config.get('client_ip', '')
        self.base_url = self.SANDBOX_URL if self.sandbox else self.PRODUCTION_URL
        
        if not all([self.api_user, self.api_key, self.username]):
            logger.warning("Namecheap API nicht vollständig konfiguriert")
    
    def _make_request(self, command: str, params: Dict[str, str]) -> Optional[requests.Response]:
        """Führt API-Request aus"""
        if not self.enabled:
            logger.debug(f"Namecheap API deaktiviert - Mock-Response für {command}")
            return None
            
        request_params = {
            'ApiUser': self.api_user,
            'ApiKey': self.api_key,
            'UserName': self.username,
            'ClientIp': self.client_ip,
            'Command': command,
            **params
        }
        
        try:
            response = requests.get(self.base_url, params=request_params, timeout=30)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Namecheap API Fehler: {e}")
            return None
    
    def check_availability(self, domain: str) -> Tuple[bool, Optional[float]]:
        """Prüft Domain-Verfügbarkeit"""
        if self.sandbox or not self.enabled:
            # Sandbox: Simuliere Verfügbarkeit
            logger.info(f"[SANDBOX] Prüfe Verfügbarkeit für {domain}")
            # Simuliere: 70% verfügbar, zufälliger Preis $8-15
            import random
            available = random.random() > 0.3
            price = round(random.uniform(8.0, 15.0), 2) if available else None
            return available, price
        
        response = self._make_request('namecheap.domains.check', {
            'DomainList': domain
        })
        
        if not response:
            return False, None
        
        # XML Parsing (vereinfacht)
        content = response.text
        available = 'Available="true"' in content
        
        # Preis extrahieren (vereinfacht)
        price = None
        if available:
            price_match = re.search(r'Price="([\d.]+)"', content)
            if price_match:
                price = float(price_match.group(1))
        
        return available, price
    
    def purchase_domain(self, domain: str, years: int = 1) -> Tuple[bool, Optional[str], Optional[str]]:
        """Kauft Domain"""
        if self.sandbox or not self.enabled:
            logger.info(f"[SANDBOX] Kauf simuliert für {domain}")
            # Simuliere erfolgreichen Kauf
            transaction_id = f"SANDBOX_{int(time.time())}_{domain.replace('.', '_')}"
            return True, transaction_id, None
        
        # Erst WhoisGuard/Contact Info hinzufügen (erforderlich für Namecheap)
        # Dies ist vereinfacht - in Produktion müssen Contact Details gesetzt werden
        
        response = self._make_request('namecheap.domains.create', {
            'DomainName': domain,
            'Years': str(years),
            # Weitere Parameter wie Registrant/Admin/Tech/Billing Contact nötig
        })
        
        if not response:
            return False, None, "API Request fehlgeschlagen"
        
        content = response.text
        
        if 'Status="OK"' in content:
            # Transaction ID extrahieren
            tx_match = re.search(r'TransactionID="(\d+)"', content)
            transaction_id = tx_match.group(1) if tx_match else None
            return True, transaction_id, None
        else:
            error_match = re.search(r'Error[^>]*>([^<]+)</Error', content)
            error_msg = error_match.group(1) if error_match else "Unbekannter Fehler"
            return False, None, error_msg
    
    def get_balance(self) -> Optional[float]:
        """Holt aktuelles Guthaben"""
        if self.sandbox or not self.enabled:
            return 1000.0  # Sandbox-Balance
        
        response = self._make_request('namecheap.users.getBalances', {})
        if not response:
            return None
        
        content = response.text
        balance_match = re.search(r'Currency="USD"[^>]*>([\d.]+)</', content)
        if balance_match:
            return float(balance_match.group(1))
        return None


class DynadotAPI(RegistrarAPI):
    """Dynadot API Integration"""
    
    API_URL = "https://api.dynadot.com/api3.json"
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key', '')
        
        if not self.api_key:
            logger.warning("Dynadot API Key nicht konfiguriert")
    
    def _make_request(self, command: str, params: Dict[str, str]) -> Optional[Dict]:
        """Führt API-Request aus"""
        if not self.enabled:
            logger.debug(f"Dynadot API deaktiviert - Mock-Response für {command}")
            return None
        
        request_params = {
            'key': self.api_key,
            'command': command,
            **params
        }
        
        try:
            response = requests.get(self.API_URL, params=request_params, timeout=30)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Dynadot API Fehler: {e}")
            return None
    
    def check_availability(self, domain: str) -> Tuple[bool, Optional[float]]:
        """Prüft Domain-Verfügbarkeit"""
        if self.sandbox or not self.enabled:
            logger.info(f"[SANDBOX] Prüfe Verfügbarkeit für {domain}")
            import random
            available = random.random() > 0.3
            price = round(random.uniform(8.0, 15.0), 2) if available else None
            return available, price
        
        result = self._make_request('search', {'domain0': domain})
        
        if not result or 'SearchResponse' not in result:
            return False, None
        
        try:
            status = result['SearchResponse']['SearchResults'][0]['Status']
            available = status == 'available'
            
            price = None
            if available:
                price_str = result['SearchResponse']['SearchResults'][0].get('Price', '0')
                price = float(price_str)
            
            return available, price
        except (KeyError, IndexError, ValueError) as e:
            logger.error(f"Fehler beim Parsen der Dynadot-Antwort: {e}")
            return False, None
    
    def purchase_domain(self, domain: str, years: int = 1) -> Tuple[bool, Optional[str], Optional[str]]:
        """Kauft Domain"""
        if self.sandbox or not self.enabled:
            logger.info(f"[SANDBOX] Kauf simuliert für {domain}")
            transaction_id = f"SANDBOX_{int(time.time())}_{domain.replace('.', '_')}"
            return True, transaction_id, None
        
        result = self._make_request('register', {
            'domain': domain,
            'duration': str(years)
            # Weitere Parameter wie Kontakt-ID nötig
        })
        
        if not result:
            return False, None, "API Request fehlgeschlagen"
        
        try:
            status = result.get('RegisterResponse', {}).get('Status')
            if status == 'success':
                transaction_id = result['RegisterResponse'].get('OrderId')
                return True, transaction_id, None
            else:
                error = result.get('RegisterResponse', {}).get('Error', 'Unbekannter Fehler')
                return False, None, error
        except KeyError as e:
            return False, None, f"Ungültige API-Antwort: {e}"
    
    def get_balance(self) -> Optional[float]:
        """Holt aktuelles Guthaben"""
        if self.sandbox or not self.enabled:
            return 1000.0
        
        result = self._make_request('get_balance', {})
        
        if not result:
            return None
        
        try:
            balance = result['GetBalanceResponse']['Balance']['BalanceAmount']
            return float(balance)
        except (KeyError, ValueError):
            return None


class AutoPurchaser:
    """
    Automatisches Kauf-System für Domains
    Mit Safety-Features und Limits
    """
    
    def __init__(self, config_path: str, db_path: str):
        self.config_path = config_path
        self.db_path = db_path
        self.config = self._load_config()
        self._init_db()
        
        # APIs initialisieren
        self.apis = {}
        self._init_apis()
        
        # Tracking
        self.last_purchase_time = None
        
        logger.info("AutoPurchaser initialisiert")
        logger.info(f"Sandbox-Modus: {self.config.get('sandbox_mode', True)}")
    
    def _load_config(self) -> Dict:
        """Lädt Konfiguration aus YAML"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Fehler beim Laden der Konfiguration: {e}")
            return {}
    
    def _init_db(self):
        """Initialisiert SQLite-Datenbank für Käufe"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabelle für Kaufversuche
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchase_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                price REAL NOT NULL,
                score INTEGER NOT NULL,
                provider TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT,
                transaction_id TEXT,
                requires_manual_approval BOOLEAN DEFAULT 0,
                sandbox_mode BOOLEAN DEFAULT 1,
                user_approved BOOLEAN DEFAULT NULL,
                approved_by TEXT,
                approved_at TIMESTAMP
            )
        ''')
        
        # Tabelle für Limits/Statistiken
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchase_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL UNIQUE,
                domains_purchased INTEGER DEFAULT 0,
                total_amount REAL DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _init_apis(self):
        """Initialisiert Registrar APIs"""
        apis_config = self.config.get('apis', {})
        
        # Namecheap
        if apis_config.get('namecheap', {}).get('enabled', False):
            self.apis['namecheap'] = NamecheapAPI(apis_config['namecheap'])
            logger.info("Namecheap API initialisiert")
        
        # Dynadot
        if apis_config.get('dynadot', {}).get('enabled', False):
            self.apis['dynadot'] = DynadotAPI(apis_config['dynadot'])
            logger.info("Dynadot API initialisiert")
        
        if not self.apis:
            logger.warning("Keine APIs aktiviert - System läuft im Demo-Modus")
    
    def _is_tld_blocked(self, domain: str) -> bool:
        """Prüft ob TLD auf Blacklist ist"""
        tld = domain.split('.')[-1].lower()
        blacklist = self.config.get('tld_blacklist', [])
        whitelist = self.config.get('tld_whitelist', [])
        
        # Whitelist hat Priorität
        if whitelist and tld not in whitelist:
            logger.info(f"TLD {tld} nicht in Whitelist")
            return True
        
        if tld in blacklist:
            logger.info(f"TLD {tld} auf Blacklist")
            return True
        
        return False
    
    def get_purchase_limits(self) -> PurchaseLimits:
        """Holt aktuelle Kauf-Limits"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        
        # Daily stats
        cursor.execute('''
            SELECT COALESCE(SUM(domains_purchased), 0), COALESCE(SUM(total_amount), 0)
            FROM purchase_stats WHERE date = ?
        ''', (today.isoformat(),))
        daily_domains, daily_amount = cursor.fetchone()
        
        # Weekly stats
        cursor.execute('''
            SELECT COALESCE(SUM(domains_purchased), 0), COALESCE(SUM(total_amount), 0)
            FROM purchase_stats WHERE date >= ?
        ''', (week_start.isoformat(),))
        weekly_domains, weekly_amount = cursor.fetchone()
        
        # Monthly stats
        cursor.execute('''
            SELECT COALESCE(SUM(domains_purchased), 0), COALESCE(SUM(total_amount), 0)
            FROM purchase_stats WHERE date >= ?
        ''', (month_start.isoformat(),))
        monthly_domains, monthly_amount = cursor.fetchone()
        
        conn.close()
        
        limits_config = self.config.get('limits', {})
        daily_limit = limits_config.get('daily', {})
        
        return PurchaseLimits(
            daily_domains=daily_domains,
            daily_amount=daily_amount,
            weekly_domains=weekly_domains,
            weekly_amount=weekly_amount,
            monthly_domains=monthly_domains,
            monthly_amount=monthly_amount,
            remaining_daily_domains=daily_limit.get('max_domains', 5) - daily_domains,
            remaining_daily_amount=daily_limit.get('max_amount_usd', 500) - daily_amount
        )
    
    def check_limits(self, price: float) -> Tuple[bool, Optional[str]]:
        """Prüft ob Limits eingehalten werden"""
        limits = self.get_purchase_limits()
        limits_config = self.config.get('limits', {})
        
        # Daily checks
        daily = limits_config.get('daily', {})
        if limits.daily_domains >= daily.get('max_domains', 5):
            return False, "Tägliches Domain-Limit erreicht"
        if limits.daily_amount + price > daily.get('max_amount_usd', 500):
            return False, "Tägliches Budget-Limit würde überschritten"
        
        # Weekly checks
        weekly = limits_config.get('weekly', {})
        if limits.weekly_domains >= weekly.get('max_domains', 20):
            return False, "Wöchentliches Domain-Limit erreicht"
        if limits.weekly_amount + price > weekly.get('max_amount_usd', 2000):
            return False, "Wöchentliches Budget-Limit würde überschritten"
        
        # Monthly checks
        monthly = limits_config.get('monthly', {})
        if limits.monthly_domains >= monthly.get('max_domains', 50):
            return False, "Monatliches Domain-Limit erreicht"
        if limits.monthly_amount + price > monthly.get('max_amount_usd', 5000):
            return False, "Monatliches Budget-Limit würde überschritten"
        
        return True, None
    
    def requires_manual_approval(self, price: float) -> bool:
        """Prüft ob manuelle Freigabe nötig ist"""
        approval_config = self.config.get('manual_approval', {})
        if not approval_config.get('enabled', True):
            return False
        
        threshold = approval_config.get('price_threshold', 50.0)
        return price > threshold
    
    def log_attempt(self, attempt: PurchaseAttempt):
        """Protokolliert Kaufversuch in Datenbank"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO purchase_attempts 
            (domain, price, score, provider, success, error_message, transaction_id, 
             requires_manual_approval, sandbox_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            attempt.domain, attempt.price, attempt.score, attempt.provider,
            attempt.success, attempt.error_message, attempt.transaction_id,
            attempt.requires_manual_approval, attempt.sandbox_mode
        ))
        
        conn.commit()
        conn.close()
        
        # Auch in Log-Datei
        status = "ERFOLG" if attempt.success else "FEHLGESCHLAGEN"
        mode = "[SANDBOX] " if attempt.sandbox_mode else ""
        logger.info(f"{mode}Kaufversuch {status}: {attempt.domain} @ ${attempt.price} (Score: {attempt.score})")
    
    def update_stats(self, price: float, success: bool):
        """Aktualisiert Kauf-Statistiken"""
        if not success:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().date().isoformat()
        
        cursor.execute('''
            INSERT INTO purchase_stats (date, domains_purchased, total_amount)
            VALUES (?, 1, ?)
            ON CONFLICT(date) DO UPDATE SET
                domains_purchased = domains_purchased + 1,
                total_amount = total_amount + ?,
                updated_at = CURRENT_TIMESTAMP
        ''', (today, price, price))
        
        conn.commit()
        conn.close()
    
    def send_notification(self, attempt: PurchaseAttempt):
        """Sendet E-Mail/Telegram Benachrichtigung"""
        notifications = self.config.get('notifications', {})
        
        # E-Mail
        email_config = notifications.get('email', {})
        if email_config.get('enabled', False) and attempt.success:
            self._send_email_notification(attempt, email_config)
        
        # Telegram
        telegram_config = notifications.get('telegram', {})
        if telegram_config.get('enabled', False):
            self._send_telegram_notification(attempt, telegram_config)
    
    def _send_email_notification(self, attempt: PurchaseAttempt, config: Dict):
        """Sendet E-Mail Benachrichtigung"""
        try:
            msg = MIMEMultipart()
            msg['From'] = config.get('from_address', 'domain-flipper@example.com')
            msg['To'] = config.get('to_address', '')
            
            if attempt.success:
                msg['Subject'] = f"✅ Domain gekauft: {attempt.domain}"
                body = f"""
Domain erfolgreich gekauft!

Domain: {attempt.domain}
Preis: ${attempt.price:.2f}
Score: {attempt.score}
Provider: {attempt.provider}
Transaction ID: {attempt.transaction_id}
Modus: {'SANDBOX' if attempt.sandbox_mode else 'PRODUKTION'}

Zeit: {attempt.timestamp}
                """
            else:
                msg['Subject'] = f"❌ Kauf fehlgeschlagen: {attempt.domain}"
                body = f"""
Domain-Kauf fehlgeschlagen!

Domain: {attempt.domain}
Preis: ${attempt.price:.2f}
Score: {attempt.score}
Provider: {attempt.provider}
Fehler: {attempt.error_message}
Modus: {'SANDBOX' if attempt.sandbox_mode else 'PRODUKTION'}

Zeit: {attempt.timestamp}
                """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # SMTP Verbindung
            server = smtplib.SMTP(config.get('smtp_host', 'smtp.gmail.com'), 
                                  config.get('smtp_port', 587))
            server.starttls()
            server.login(config.get('smtp_user', ''), config.get('smtp_password', ''))
            server.send_message(msg)
            server.quit()
            
            logger.info(f"E-Mail Benachrichtigung gesendet für {attempt.domain}")
        except Exception as e:
            logger.error(f"Fehler beim Senden der E-Mail: {e}")
    
    def _send_telegram_notification(self, attempt: PurchaseAttempt, config: Dict):
        """Sendet Telegram Benachrichtigung"""
        try:
            bot_token = config.get('bot_token', '')
            chat_id = config.get('chat_id', '')
            
            if not bot_token or not chat_id:
                return
            
            if attempt.success:
                emoji = "🟢" if not attempt.sandbox_mode else "🧪"
                text = f"""{emoji} <b>Domain gekauft!</b>

<b>Domain:</b> <code>{attempt.domain}</code>
<b>Preis:</b> ${attempt.price:.2f}
<b>Score:</b> {attempt.score}
<b>Provider:</b> {attempt.provider}
<b>TX:</b> <code>{attempt.transaction_id}</code>
<b>Modus:</b> {'🧪 SANDBOX' if attempt.sandbox_mode else '🔴 PRODUKTION'}
"""
            else:
                text = f"""🔴 <b>Kauf fehlgeschlagen</b>

<b>Domain:</b> <code>{attempt.domain}</code>
<b>Preis:</b> ${attempt.price:.2f}
<b>Fehler:</b> {attempt.error_message}
<b>Modus:</b> {'🧪 SANDBOX' if attempt.sandbox_mode else '🔴 PRODUKTION'}
"""
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML'
            }, timeout=10)
            
            logger.info(f"Telegram Benachrichtigung gesendet für {attempt.domain}")
        except Exception as e:
            logger.error(f"Fehler beim Senden der Telegram-Nachricht: {e}")
    
    def find_best_price(self, domain: str) -> Tuple[Optional[str], Optional[float]]:
        """Findet den besten Preis über alle APIs"""
        best_provider = None
        best_price = None
        
        for provider_name, api in self.apis.items():
            available, price = api.check_availability(domain)
            
            if available and price is not None:
                if best_price is None or price < best_price:
                    best_price = price
                    best_provider = provider_name
        
        return best_provider, best_price
    
    def attempt_purchase(self, domain: str, score: int, 
                         max_price: Optional[float] = None,
                         force: bool = False) -> PurchaseAttempt:
        """
        Versucht eine Domain zu kaufen
        
        Args:
            domain: Die zu kaufende Domain
            score: Der Domain-Score
            max_price: Optionaler Maximalpreis (überschreibt Config)
            force: Wenn True, ignoriert Auto-Kauf-Kriterien (für manuelle Käufe)
        
        Returns:
            PurchaseAttempt mit Ergebnis
        """
        now = datetime.now().isoformat()
        sandbox = self.config.get('sandbox_mode', True)
        
        # 1. TLD Prüfung
        if self._is_tld_blocked(domain):
            attempt = PurchaseAttempt(
                domain=domain,
                price=0,
                score=score,
                provider="none",
                success=False,
                timestamp=now,
                error_message="TLD auf Blacklist",
                sandbox_mode=sandbox
            )
            self.log_attempt(attempt)
            return attempt
        
        # 2. Besten Preis finden
        provider, price = self.find_best_price(domain)
        
        if provider is None:
            attempt = PurchaseAttempt(
                domain=domain,
                price=0,
                score=score,
                provider="none",
                success=False,
                timestamp=now,
                error_message="Domain nicht verfügbar",
                sandbox_mode=sandbox
            )
            self.log_attempt(attempt)
            return attempt
        
        # 3. Auto-Kauf Kriterien prüfen (falls nicht forced)
        if not force:
            auto_config = self.config.get('auto_purchase', {})
            min_score = auto_config.get('min_score', 75)
            auto_max_price = auto_config.get('max_price', 20.0)
            
            if score < min_score:
                attempt = PurchaseAttempt(
                    domain=domain,
                    price=price,
                    score=score,
                    provider=provider,
                    success=False,
                    timestamp=now,
                    error_message=f"Score {score} unter Minimum {min_score}",
                    sandbox_mode=sandbox
                )
                self.log_attempt(attempt)
                return attempt
            
            if price > auto_max_price:
                attempt = PurchaseAttempt(
                    domain=domain,
                    price=price,
                    score=score,
                    provider=provider,
                    success=False,
                    timestamp=now,
                    error_message=f"Preis ${price} über Maximum ${auto_max_price}",
                    sandbox_mode=sandbox
                )
                self.log_attempt(attempt)
                return attempt
        
        # 4. Max-Price Check (überschreibt Config wenn gesetzt)
        effective_max = max_price or self.config.get('auto_purchase', {}).get('max_price', 20.0)
        if price > effective_max:
            attempt = PurchaseAttempt(
                domain=domain,
                price=price,
                score=score,
                provider=provider,
                success=False,
                timestamp=now,
                error_message=f"Preis ${price} über angegebenem Maximum ${effective_max}",
                sandbox_mode=sandbox
            )
            self.log_attempt(attempt)
            return attempt
        
        # 5. Limits prüfen
        limits_ok, limits_error = self.check_limits(price)
        if not limits_ok:
            attempt = PurchaseAttempt(
                domain=domain,
                price=price,
                score=score,
                provider=provider,
                success=False,
                timestamp=now,
                error_message=limits_error,
                sandbox_mode=sandbox
            )
            self.log_attempt(attempt)
            return attempt
        
        # 6. Manuelle Freigabe prüfen
        needs_approval = self.requires_manual_approval(price)
        if needs_approval and not force:
            attempt = PurchaseAttempt(
                domain=domain,
                price=price,
                score=score,
                provider=provider,
                success=False,
                timestamp=now,
                error_message="Manuelle Freigabe erforderlich (Preis > $50)",
                requires_manual_approval=True,
                sandbox_mode=sandbox
            )
            self.log_attempt(attempt)
            # Benachrichtigung senden für manuelle Freigabe
            self.send_notification(attempt)
            return attempt
        
        # 7. Cooldown einhalten
        cooldown = self.config.get('cooldown', {})
        if self.last_purchase_time:
            elapsed = (datetime.now() - self.last_purchase_time).total_seconds()
            min_wait = cooldown.get('seconds_between_purchases', 10)
            if elapsed < min_wait:
                wait_time = min_wait - elapsed
                logger.info(f"Warte {wait_time:.1f}s (Cooldown)...")
                time.sleep(wait_time)
        
        # 8. Kauf durchführen
        api = self.apis.get(provider)
        if not api:
            attempt = PurchaseAttempt(
                domain=domain,
                price=price,
                score=score,
                provider=provider,
                success=False,
                timestamp=now,
                error_message="API nicht verfügbar",
                sandbox_mode=sandbox
            )
            self.log_attempt(attempt)
            return attempt
        
        # Retry-Logik
        retry_config = self.config.get('retry', {})
        max_retries = retry_config.get('max_attempts', 3)
        base_delay = retry_config.get('delay_seconds', 5)
        backoff = retry_config.get('backoff_multiplier', 2)
        
        success = False
        transaction_id = None
        error_msg = None
        
        for attempt_num in range(max_retries):
            success, transaction_id, error_msg = api.purchase_domain(domain)
            
            if success:
                break
            
            logger.warning(f"Kaufversuch {attempt_num + 1}/{max_retries} fehlgeschlagen: {error_msg}")
            
            if attempt_num < max_retries - 1:
                delay = base_delay * (backoff ** attempt_num)
                logger.info(f"Warte {delay}s vor Retry...")
                time.sleep(delay)
        
        # Ergebnis erstellen
        attempt = PurchaseAttempt(
            domain=domain,
            price=price,
            score=score,
            provider=provider,
            success=success,
            timestamp=now,
            error_message=error_msg if not success else None,
            transaction_id=transaction_id if success else None,
            sandbox_mode=sandbox
        )
        
        # Loggen und Benachrichtigen
        self.log_attempt(attempt)
        
        if success:
            self.last_purchase_time = datetime.now()
            self.update_stats(price, True)
            self.send_notification(attempt)
        
        return attempt
    
    def get_pending_approvals(self) -> List[Dict]:
        """Holt alle ausstehenden manuellen Freigaben"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT domain, price, score, provider, timestamp
            FROM purchase_attempts
            WHERE requires_manual_approval = 1 AND user_approved IS NULL
            ORDER BY timestamp DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'domain': row[0],
                'price': row[1],
                'score': row[2],
                'provider': row[3],
                'timestamp': row[4]
            }
            for row in rows
        ]
    
    def approve_purchase(self, domain: str, approved_by: str) -> bool:
        """Genehmigt einen ausstehenden Kauf"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE purchase_attempts
            SET user_approved = 1, approved_by = ?, approved_at = CURRENT_TIMESTAMP
            WHERE domain = ? AND requires_manual_approval = 1 AND user_approved IS NULL
        ''', (approved_by, domain))
        
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        
        if updated:
            logger.info(f"Kauf für {domain} genehmigt von {approved_by}")
            # Kauf erneut versuchen mit force=True
            # Hier würde man den ursprünglichen Score laden und erneut versuchen
        
        return updated
    
    def get_purchase_history(self, days: int = 30) -> List[Dict]:
        """Holt Kaufhistorie"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute('''
            SELECT domain, price, score, provider, success, timestamp, 
                   error_message, transaction_id, sandbox_mode
            FROM purchase_attempts
            WHERE timestamp > ?
            ORDER BY timestamp DESC
        ''', (since,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'domain': row[0],
                'price': row[1],
                'score': row[2],
                'provider': row[3],
                'success': bool(row[4]),
                'timestamp': row[5],
                'error_message': row[6],
                'transaction_id': row[7],
                'sandbox_mode': bool(row[8])
            }
            for row in rows
        ]
    
    def generate_report(self) -> str:
        """Generiert einen Kauf-Bericht"""
        limits = self.get_purchase_limits()
        history = self.get_purchase_history(days=7)
        pending = self.get_pending_approvals()
        
        lines = [
            "=" * 70,
            "AUTO-PURCHASER BERICHT",
            f"Zeit: {datetime.now().isoformat()}",
            f"Sandbox-Modus: {self.config.get('sandbox_mode', True)}",
            "=" * 70,
            "",
            "--- LIMITS ---",
            f"Heute: {limits.daily_domains} Domains, ${limits.daily_amount:.2f}",
            f"Diese Woche: {limits.weekly_domains} Domains, ${limits.weekly_amount:.2f}",
            f"Dieser Monat: {limits.monthly_domains} Domains, ${limits.monthly_amount:.2f}",
            f"",
            f"Verfügbar heute: {limits.remaining_daily_domains} Domains, ${limits.remaining_daily_amount:.2f}",
            "",
            "--- AUSSTEHENDE FREIGABEN ---",
            f"Anzahl: {len(pending)}",
        ]
        
        for p in pending[:5]:
            lines.append(f"  - {p['domain']} @ ${p['price']:.2f} (Score: {p['score']})")
        
        lines.extend([
            "",
            "--- LETZTE KÄUFE (7 Tage) ---",
        ])
        
        successful = [h for h in history if h['success']]
        failed = [h for h in history if not h['success']]
        
        lines.append(f"Erfolgreich: {len(successful)}")
        for h in successful[:10]:
            mode = "[S] " if h['sandbox_mode'] else ""
            lines.append(f"  {mode}{h['domain']} @ ${h['price']:.2f} via {h['provider']}")
        
        lines.append(f"\nFehlgeschlagen: {len(failed)}")
        for h in failed[:5]:
            lines.append(f"  {h['domain']}: {h['error_message']}")
        
        lines.extend([
            "",
            "=" * 70,
        ])
        
        return "\n".join(lines)


def main():
    """CLI Interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Auto-Purchasing System für Domains')
    parser.add_argument('--config', default='config/purchase_rules.yaml',
                        help='Pfad zur Konfigurationsdatei')
    parser.add_argument('--db', default='data/purchases.db',
                        help='Pfad zur Datenbank')
    parser.add_argument('--domain', help='Einzelne Domain kaufen')
    parser.add_argument('--score', type=int, help='Domain-Score')
    parser.add_argument('--force', action='store_true', 
                        help='Kauf erzwingen (ignoriert Auto-Kriterien)')
    parser.add_argument('--max-price', type=float, help='Maximaler Preis')
    parser.add_argument('--report', action='store_true', help='Bericht anzeigen')
    parser.add_argument('--pending', action='store_true', 
                        help='Ausstehende Freigaben anzeigen')
    parser.add_argument('--approve', help='Domain freigeben')
    parser.add_argument('--approve-by', default='admin', help='Freigebende Person')
    
    args = parser.parse_args()
    
    # Pfade anpassen falls relativ
    base_dir = Path('/root/.openclaw/workspace/projects/domain-flipper')
    config_path = args.config if args.config.startswith('/') else base_dir / args.config
    db_path = args.db if args.db.startswith('/') else base_dir / args.db
    
    purchaser = AutoPurchaser(str(config_path), str(db_path))
    
    if args.domain:
        if args.score is None:
            print("Fehler: --score erforderlich für Domain-Kauf")
            return
        
        print(f"Versuche Kauf von {args.domain} (Score: {args.score})...")
        result = purchaser.attempt_purchase(
            args.domain, 
            args.score,
            max_price=args.max_price,
            force=args.force
        )
        
        print(f"\nErgebnis:")
        print(f"  Erfolg: {result.success}")
        print(f"  Preis: ${result.price:.2f}")
        print(f"  Provider: {result.provider}")
        if result.transaction_id:
            print(f"  Transaction ID: {result.transaction_id}")
        if result.error_message:
            print(f"  Fehler: {result.error_message}")
        print(f"  Sandbox: {result.sandbox_mode}")
    
    elif args.report:
        print(purchaser.generate_report())
    
    elif args.pending:
        pending = purchaser.get_pending_approvals()
        print(f"Ausstehende Freigaben: {len(pending)}")
        for p in pending:
            print(f"  - {p['domain']} @ ${p['price']:.2f} (Score: {p['score']})")
    
    elif args.approve:
        if purchaser.approve_purchase(args.approve, args.approve_by):
            print(f"{args.approve} freigegeben")
        else:
            print(f"Keine ausstehende Freigabe für {args.approve} gefunden")
    
    else:
        print(purchaser.generate_report())


if __name__ == "__main__":
    main()
