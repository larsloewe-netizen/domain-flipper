#!/usr/bin/env python3
"""
Proxy Manager für Domain-Scraper
Verwaltet Free Proxies von verschiedenen Quellen
"""

import requests
import json
import time
import random
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import os
import threading

logger = logging.getLogger(__name__)

# Konstanten
WORKING_PROXIES_FILE = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'working_proxies.json'
)
PROXY_TEST_URL = "https://httpbin.org/ip"
PROXY_TEST_TIMEOUT = 10
DEFAULT_ROTATION_LIMIT = 10  # Rotiere nach X Requests


class ProxyManager:
    """
    Verwaltet Proxies von Free Sources
    - Holt Proxys von free-proxy-list.download
    - Testet sie gegen httpbin.org/ip
    - Rotiert alle X Requests
    - Speichert funktionierende Proxies
    """
    
    # Free Proxy Sources
    FREE_PROXY_SOURCES = {
        'proxy_list_download': 'https://www.proxy-list.download/api/v1/get?type=https',
        'proxy_list_download_http': 'https://www.proxy-list.download/api/v1/get?type=http',
        'proxy_list_download_socks4': 'https://www.proxy-list.download/api/v1/get?type=socks4',
        'proxy_list_download_socks5': 'https://www.proxy-list.download/api/v1/get?type=socks5',
    }
    
    def __init__(self, 
                 rotation_limit: int = DEFAULT_ROTATION_LIMIT,
                 test_before_use: bool = True,
                 auto_fetch: bool = True,
                 min_proxies: int = 3):
        """
        Initialisiere ProxyManager
        
        Args:
            rotation_limit: Rotiere Proxy nach X Requests
            test_before_use: Teste Proxy vor Verwendung
            auto_fetch: Hole automatisch neue Proxies wenn zu wenige
            min_proxies: Minimale Anzahl an funktionierenden Proxies
        """
        self.rotation_limit = rotation_limit
        self.test_before_use = test_before_use
        self.auto_fetch = auto_fetch
        self.min_proxies = min_proxies
        
        self.proxies: List[str] = []
        self.working_proxies: List[str] = []
        self.failed_proxies: Dict[str, int] = {}  # proxy -> fail_count
        self.current_index = 0
        self.request_count = 0
        self.lock = threading.Lock()
        
        # Lade bestehende Proxies
        self._load_working_proxies()
        
        # Wenn zu wenige Proxies, hole neue
        if len(self.working_proxies) < min_proxies and auto_fetch:
            logger.info(f"Nur {len(self.working_proxies)} Proxies verfügbar, hole neue...")
            self.fetch_and_test_proxies()
    
    def _load_working_proxies(self) -> List[str]:
        """Lade funktionierende Proxies aus Datei"""
        if os.path.exists(WORKING_PROXIES_FILE):
            try:
                with open(WORKING_PROXIES_FILE, 'r') as f:
                    data = json.load(f)
                    self.working_proxies = data.get('proxies', [])
                    logger.info(f"{len(self.working_proxies)} Proxies aus Datei geladen")
                    return self.working_proxies
            except Exception as e:
                logger.error(f"Fehler beim Laden der Proxies: {e}")
        return []
    
    def _save_working_proxies(self):
        """Speichere funktionierende Proxies in Datei"""
        try:
            os.makedirs(os.path.dirname(WORKING_PROXIES_FILE), exist_ok=True)
            data = {
                'proxies': self.working_proxies,
                'last_updated': datetime.now().isoformat(),
                'count': len(self.working_proxies)
            }
            with open(WORKING_PROXIES_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"{len(self.working_proxies)} Proxies gespeichert")
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Proxies: {e}")
    
    def fetch_proxies_from_sources(self) -> List[str]:
        """Hole Proxies von allen Free Sources"""
        all_proxies = []
        
        for source_name, source_url in self.FREE_PROXY_SOURCES.items():
            try:
                logger.info(f"Hole Proxies von {source_name}...")
                response = requests.get(
                    source_url, 
                    timeout=30,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                
                if response.status_code == 200:
                    # Proxy-Liste parsen (Format: ip:port pro Zeile)
                    proxies = response.text.strip().split('\r\n')
                    proxies = [p.strip() for p in proxies if p.strip() and ':' in p]
                    
                    # Füge http:// Präfix hinzu wenn nicht vorhanden
                    formatted_proxies = []
                    for proxy in proxies:
                        if not proxy.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                            if 'socks4' in source_name:
                                proxy = f"socks4://{proxy}"
                            elif 'socks5' in source_name:
                                proxy = f"socks5://{proxy}"
                            else:
                                proxy = f"http://{proxy}"
                        formatted_proxies.append(proxy)
                    
                    all_proxies.extend(formatted_proxies)
                    logger.info(f"  {len(formatted_proxies)} Proxies von {source_name} geholt")
                else:
                    logger.warning(f"  {source_name} antwortete mit Status {response.status_code}")
                    
            except Exception as e:
                logger.error(f"  Fehler beim Holen von {source_name}: {e}")
        
        # Entferne Duplikate
        unique_proxies = list(set(all_proxies))
        logger.info(f"Insgesamt {len(unique_proxies)} einzigartige Proxies gefunden")
        
        self.proxies = unique_proxies
        return unique_proxies
    
    def test_proxy(self, proxy: str) -> Tuple[bool, Optional[str]]:
        """
        Teste einen einzelnen Proxy
        
        Returns:
            Tuple[bool, Optional[str]]: (funktioniert, ip_address)
        """
        proxies = {
            'http': proxy,
            'https': proxy
        }
        
        try:
            response = requests.get(
                PROXY_TEST_URL,
                proxies=proxies,
                timeout=PROXY_TEST_TIMEOUT,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    origin_ip = data.get('origin', 'unknown')
                    return True, origin_ip
                except:
                    return True, None
            else:
                return False, None
                
        except requests.exceptions.Timeout:
            return False, None
        except requests.exceptions.ConnectionError:
            return False, None
        except Exception as e:
            return False, None
    
    def test_proxies(self, proxies: List[str], max_workers: int = 10) -> List[str]:
        """
        Teste mehrere Proxies und gib funktionierende zurück
        
        Args:
            proxies: Liste der zu testenden Proxies
            max_workers: Maximale parallele Tests
            
        Returns:
            Liste funktionierender Proxies
        """
        working = []
        tested = 0
        
        logger.info(f"Teste {len(proxies)} Proxies...")
        
        for proxy in proxies:
            tested += 1
            if tested % 10 == 0:
                logger.info(f"  {tested}/{len(proxies)} getestet, {len(working)} funktionieren")
            
            success, ip = self.test_proxy(proxy)
            if success:
                working.append(proxy)
                logger.debug(f"  ✓ Proxy funktioniert: {proxy} (IP: {ip})")
                
                # Früherer Abbruch wenn wir genug haben
                if len(working) >= 20:
                    logger.info(f"  Genug funktionierende Proxies gefunden ({len(working)})")
                    break
            else:
                logger.debug(f"  ✗ Proxy fehlgeschlagen: {proxy}")
            
            # Kurze Pause zwischen Tests
            time.sleep(0.1)
        
        logger.info(f"Test abgeschlossen: {len(working)}/{tested} Proxies funktionieren")
        return working
    
    def fetch_and_test_proxies(self, force: bool = False) -> List[str]:
        """
        Hole neue Proxies und teste sie
        
        Args:
            force: Auch testen wenn genug Proxies vorhanden
            
        Returns:
            Liste funktionierender Proxies
        """
        if not force and len(self.working_proxies) >= self.min_proxies:
            logger.info(f"Bereits {len(self.working_proxies)} Proxies verfügbar")
            return self.working_proxies
        
        # Hole neue Proxies
        new_proxies = self.fetch_proxies_from_sources()
        
        # Teste sie
        working = self.test_proxies(new_proxies)
        
        # Aktualisiere Liste
        with self.lock:
            # Merge mit bestehenden Proxies
            existing_set = set(self.working_proxies)
            for proxy in working:
                if proxy not in existing_set:
                    self.working_proxies.append(proxy)
            
            # Speichere
            self._save_working_proxies()
        
        return self.working_proxies
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """
        Hole den nächsten Proxy in der Rotation
        
        Returns:
            Proxy Dict oder None
        """
        with self.lock:
            if not self.working_proxies:
                if self.auto_fetch:
                    logger.warning("Keine Proxies verfügbar, versuche neue zu holen...")
                    self.fetch_and_test_proxies(force=True)
                
                if not self.working_proxies:
                    logger.error("Keine funktionierenden Proxies verfügbar!")
                    return None
            
            # Rotiere nach X Requests
            if self.request_count >= self.rotation_limit:
                self.current_index = (self.current_index + 1) % len(self.working_proxies)
                self.request_count = 0
                logger.debug(f"Proxy rotiert zu Index {self.current_index}")
            
            proxy_url = self.working_proxies[self.current_index]
            self.request_count += 1
            
            # Teste Proxy vor Verwendung wenn aktiviert
            if self.test_before_use:
                success, _ = self.test_proxy(proxy_url)
                if not success:
                    logger.warning(f"Proxy {proxy_url} ist tot, entferne...")
                    self.mark_failed(proxy_url)
                    # Rekursiver Aufruf für nächsten Proxy
                    return self.get_proxy()
            
            return {
                'http': proxy_url,
                'https': proxy_url
            }
    
    def mark_failed(self, proxy: Dict[str, str]):
        """Markiere einen Proxy als fehlgeschlagen"""
        proxy_url = proxy.get('http') or proxy.get('https')
        if not proxy_url:
            return
        
        with self.lock:
            # Zähle Fehler
            self.failed_proxies[proxy_url] = self.failed_proxies.get(proxy_url, 0) + 1
            
            # Entferne nach 3 Fehlern
            if self.failed_proxies[proxy_url] >= 3:
                logger.warning(f"Proxy nach 3 Fehlern entfernt: {proxy_url}")
                if proxy_url in self.working_proxies:
                    self.working_proxies.remove(proxy_url)
                self._save_working_proxies()
                
                # Hole neue wenn zu wenige
                if len(self.working_proxies) < self.min_proxies and self.auto_fetch:
                    logger.info("Zu wenige Proxies, hole neue...")
                    self.fetch_and_test_proxies()
    
    def get_stats(self) -> Dict[str, Any]:
        """Gib Statistiken zurück"""
        return {
            'total_working': len(self.working_proxies),
            'total_failed': len(self.failed_proxies),
            'current_index': self.current_index,
            'request_count': self.request_count,
            'working_proxies': self.working_proxies,
            'failed_proxies': self.failed_proxies
        }
    
    def validate_all_proxies(self) -> Tuple[int, int]:
        """
        Validiere alle gespeicherten Proxies
        
        Returns:
            Tuple[int, int]: (funktionierend, gestorben)
        """
        logger.info(f"Validiere {len(self.working_proxies)} gespeicherte Proxies...")
        
        still_working = []
        dead_count = 0
        
        for proxy in self.working_proxies:
            success, ip = self.test_proxy(proxy)
            if success:
                still_working.append(proxy)
                logger.debug(f"  ✓ {proxy} (IP: {ip})")
            else:
                dead_count += 1
                logger.debug(f"  ✗ {proxy}")
        
        with self.lock:
            self.working_proxies = still_working
            self._save_working_proxies()
        
        logger.info(f"Validierung abgeschlossen: {len(still_working)} funktionieren, {dead_count} entfernt")
        return len(still_working), dead_count


# Singleton-Instanz für einfachen Zugriff
_proxy_manager_instance: Optional[ProxyManager] = None


def get_proxy_manager(**kwargs) -> ProxyManager:
    """Hole oder erstelle ProxyManager Singleton"""
    global _proxy_manager_instance
    if _proxy_manager_instance is None:
        _proxy_manager_instance = ProxyManager(**kwargs)
    return _proxy_manager_instance


def reset_proxy_manager():
    """Reset Singleton (für Tests)"""
    global _proxy_manager_instance
    _proxy_manager_instance = None


if __name__ == "__main__":
    # Logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Test
    pm = ProxyManager()
    
    print("\n=== Proxy Manager Test ===\n")
    
    # Hole und teste Proxies
    pm.fetch_and_test_proxies()
    
    # Zeige Stats
    stats = pm.get_stats()
    print(f"\nFunktionierende Proxies: {stats['total_working']}")
    print(f"Fehlgeschlagene Proxies: {stats['total_failed']}")
    
    # Teste einzelnen Proxy
    if stats['total_working'] > 0:
        proxy = pm.get_proxy()
        print(f"\nNächster Proxy: {proxy}")
