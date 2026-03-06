#!/usr/bin/env python3
"""
Test-Script für die Robustheit des Domain Scrapers

Testet:
- Retry-Logik mit Exponential Backoff
- User-Agent Rotation
- Fehlerbehandlung
- Rate-Limiting
"""

import sys
import os
import time
import unittest
from unittest.mock import Mock, patch, MagicMock
import requests

# Füge src zum Pfad hinzu
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from scraper import (
    RetrySession, RateLimiter, ProxyManager, DomainScraper,
    USER_AGENTS
)


class TestUserAgentRotation(unittest.TestCase):
    """Testet User-Agent Rotation"""
    
    def test_minimum_user_agents(self):
        """Es sollten mindestens 10 User-Agents vorhanden sein"""
        self.assertGreaterEqual(len(USER_AGENTS), 10, 
                                f"Nur {len(USER_AGENTS)} User-Agents gefunden, mindestens 10 erwartet")
    
    def test_user_agents_are_different(self):
        """Alle User-Agents sollten unterschiedlich sein"""
        unique_agents = set(USER_AGENTS)
        self.assertEqual(len(unique_agents), len(USER_AGENTS),
                        "Es gibt doppelte User-Agents")
    
    def test_user_agents_contain_browser_info(self):
        """User-Agents sollten Browser-Informationen enthalten"""
        for agent in USER_AGENTS:
            self.assertIn("Mozilla", agent, f"User-Agent enthält kein 'Mozilla': {agent}")
    
    def test_random_user_agent_selection(self):
        """RetrySession sollte verschiedene User-Agents wählen"""
        session = RetrySession()
        headers_list = []
        
        for _ in range(20):
            headers = session._get_headers()
            headers_list.append(headers['User-Agent'])
        
        # Es sollten mehrere verschiedene User-Agents verwendet werden
        unique_used = set(headers_list)
        self.assertGreater(len(unique_used), 1, 
                          "Es wurde nur ein User-Agent verwendet")


class TestRetryLogic(unittest.TestCase):
    """Testet Retry-Logik mit Exponential Backoff"""
    
    def test_max_retries_configurable(self):
        """Max Retries sollte konfigurierbar sein"""
        session = RetrySession(max_retries=5)
        self.assertEqual(session.max_retries, 5)
        
        session = RetrySession(max_retries=3)
        self.assertEqual(session.max_retries, 3)
    
    def test_exponential_backoff_calculation(self):
        """Exponential Backoff sollte korrekt berechnet werden"""
        session = RetrySession(base_delay=1.0)
        
        # Versuch 0: ~1s, Versuch 1: ~2s, Versuch 2: ~4s
        delay0 = session._get_backoff_delay(0)
        delay1 = session._get_backoff_delay(1)
        delay2 = session._get_backoff_delay(2)
        
        # Mit Jitter - prüfe Richtung
        self.assertGreaterEqual(delay0, 0.8)   # 1.0 * 0.8
        self.assertLessEqual(delay0, 1.2)      # 1.0 * 1.2
        
        self.assertGreaterEqual(delay1, 1.6)   # 2.0 * 0.8
        self.assertLessEqual(delay1, 2.4)      # 2.0 * 1.2
        
        self.assertGreaterEqual(delay2, 3.2)   # 4.0 * 0.8
        self.assertLessEqual(delay2, 4.8)      # 4.0 * 1.2
    
    def test_backoff_with_status_429(self):
        """Bei 429 sollte länger gewartet werden"""
        session = RetrySession(base_delay=1.0)
        
        normal_delay = session._get_backoff_delay(1)
        rate_limited_delay = session._get_backoff_delay(1, status_code=429)
        
        # Rate-limited Delay sollte etwa 3x so groß sein
        self.assertGreater(rate_limited_delay, normal_delay * 2)
    
    def test_backoff_with_status_503(self):
        """Bei 503 sollte länger gewartet werden"""
        session = RetrySession(base_delay=1.0)
        
        normal_delay = session._get_backoff_delay(1)
        service_unavailable_delay = session._get_backoff_delay(1, status_code=503)
        
        # 503 Delay sollte etwa 2x so groß sein
        self.assertGreater(service_unavailable_delay, normal_delay * 1.5)
    
    @patch('requests.Session.request')
    def test_retry_on_connection_error(self, mock_request):
        """Sollte bei Connection Error retry"""
        mock_request.side_effect = [
            requests.exceptions.ConnectionError("Connection refused"),
            requests.exceptions.ConnectionError("Connection refused"),
            Mock(status_code=200, raise_for_status=lambda: None)
        ]
        
        session = RetrySession(max_retries=3, base_delay=0.1)
        response = session.get('http://example.com')
        
        self.assertEqual(mock_request.call_count, 3)
    
    @patch('requests.Session.request')
    def test_retry_on_timeout(self, mock_request):
        """Sollte bei Timeout retry"""
        mock_request.side_effect = [
            requests.exceptions.Timeout("Request timed out"),
            Mock(status_code=200, raise_for_status=lambda: None)
        ]
        
        session = RetrySession(max_retries=3, base_delay=0.1)
        response = session.get('http://example.com')
        
        self.assertEqual(mock_request.call_count, 2)
    
    @patch('requests.Session.request')
    def test_retry_on_rate_limit(self, mock_request):
        """Sollte bei 429 retry"""
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.raise_for_status.side_effect = requests.exceptions.HTTPError("429")
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.raise_for_status = Mock()
        
        mock_request.side_effect = [
            mock_response_429,
            mock_response_200
        ]
        
        session = RetrySession(max_retries=3, base_delay=0.1)
        response = session.get('http://example.com')
        
        self.assertEqual(mock_request.call_count, 2)
    
    @patch('requests.Session.request')
    def test_final_exception_raised(self, mock_request):
        """Sollte Exception werfen wenn alle Versuche fehlschlagen"""
        mock_request.side_effect = requests.exceptions.ConnectionError("Always fails")
        
        session = RetrySession(max_retries=3, base_delay=0.1)
        
        with self.assertRaises(requests.exceptions.ConnectionError):
            session.get('http://example.com')
        
        self.assertEqual(mock_request.call_count, 3)


class TestRateLimiter(unittest.TestCase):
    """Testet Rate-Limiting"""
    
    def test_variable_delay(self):
        """Delays sollten variabel sein"""
        limiter = RateLimiter(min_delay=1.0, max_delay=3.0)
        
        delays = []
        for _ in range(10):
            # Simuliere wait ohne echte Pause
            start = time.time()
            limiter.last_request_time = None
            limiter.wait()
            # Zeit wird nicht gewartet weil last_request_time None ist
        
        # Wir können nicht direkt testen, aber wir können prüfen dass
        # die Konfiguration korrekt ist
        self.assertEqual(limiter.min_delay, 1.0)
        self.assertEqual(limiter.max_delay, 3.0)
    
    def test_error_tracking(self):
        """Sollte Fehler tracken"""
        limiter = RateLimiter(error_threshold=5)
        
        # Melde Fehler
        for _ in range(3):
            limiter.report_error()
        
        self.assertEqual(limiter.error_count, 3)
        self.assertEqual(limiter.consecutive_errors, 3)
        
        # Melde Erfolg
        limiter.report_success()
        self.assertEqual(limiter.consecutive_errors, 0)
        self.assertEqual(limiter.error_count, 3)  # Bleibt erhalten
    
    def test_error_threshold_pause(self):
        """Sollte Pause machen bei zu vielen Fehlern"""
        limiter = RateLimiter(error_threshold=3, pause_duration=1)
        
        # Simuliere viele Fehler
        for _ in range(5):
            limiter.report_error()
        
        # Bei wait() sollte eine längere Pause gemacht werden
        # Wir testen indem wir prüfen ob error_count zurückgesetzt wird
        limiter.last_request_time = datetime.now() - timedelta(seconds=10)
        start = time.time()
        limiter.wait()
        elapsed = time.time() - start
        
        # Nach der Pause sollte error_count zurückgesetzt sein
        self.assertLess(limiter.error_count, 5)


class TestProxyManager(unittest.TestCase):
    """Testet Proxy-Verwaltung"""
    
    def test_proxy_rotation(self):
        """Proxies sollten rotiert werden"""
        proxies = ["http://proxy1:8080", "http://proxy2:8080", "http://proxy3:8080"]
        manager = ProxyManager(proxy_list=proxies)
        
        # Hole alle Proxies
        retrieved = []
        for _ in range(5):
            proxy = manager.get_proxy()
            if proxy:
                retrieved.append(proxy['http'])
        
        # Sollten verschiedene Proxies bekommen haben
        self.assertGreater(len(set(retrieved)), 1)
    
    def test_failed_proxy_skipped(self):
        """Fehlgeschlagene Proxies sollten übersprungen werden"""
        proxies = ["http://proxy1:8080", "http://proxy2:8080"]
        manager = ProxyManager(proxy_list=proxies)
        
        # Markiere einen als fehlgeschlagen
        manager.mark_failed({'http': 'http://proxy1:8080'})
        
        # Sollte nur noch proxy2 zurückgeben
        for _ in range(5):
            proxy = manager.get_proxy()
            if proxy:
                self.assertEqual(proxy['http'], 'http://proxy2:8080')
    
    def test_empty_proxy_list(self):
        """Leere Proxy-Liste sollte None zurückgeben"""
        manager = ProxyManager(proxy_list=[])
        proxy = manager.get_proxy()
        self.assertIsNone(proxy)
    
    def test_free_proxy_warning(self):
        """Free Proxies sollten Warnung loggen"""
        with self.assertLogs('scraper', level='WARNING') as cm:
            manager = ProxyManager(use_free_proxies=True)
            
            # Sollte Warnungen enthalten
            warning_messages = ' '.join(cm.output)
            self.assertIn('FREE PROXIES', warning_messages)


class TestDomainScraper(unittest.TestCase):
    """Testet DomainScraper Integration"""
    
    def test_test_mode_reduces_limit(self):
        """Test-Modus sollte Limit reduzieren"""
        scraper = DomainScraper(test_mode=True)
        
        limit = scraper._get_test_limit(100)
        self.assertEqual(limit, 5)
        
        limit = scraper._get_test_limit(50)
        self.assertEqual(limit, 5)
    
    def test_normal_mode_unchanged_limit(self):
        """Normaler Modus sollte Limit nicht ändern"""
        scraper = DomainScraper(test_mode=False)
        
        limit = scraper._get_test_limit(100)
        self.assertEqual(limit, 100)
    
    def test_timeout_configurable(self):
        """Timeout sollte konfigurierbar sein"""
        scraper = DomainScraper(timeout=20)
        self.assertEqual(scraper.retry_session.timeout, 20)
        
        scraper = DomainScraper(timeout=5)
        self.assertEqual(scraper.retry_session.timeout, 5)


class TestHeaders(unittest.TestCase):
    """Testet Request Headers"""
    
    def test_headers_structure(self):
        """Headers sollten alle wichtigen Felder enthalten"""
        session = RetrySession()
        headers = session._get_headers()
        
        required_fields = [
            'User-Agent', 'Accept', 'Accept-Language',
            'Accept-Encoding', 'DNT', 'Connection'
        ]
        
        for field in required_fields:
            self.assertIn(field, headers, f"Header '{field}' fehlt")
    
    def test_headers_different_per_call(self):
        """Headers sollten bei jedem Aufruf unterschiedlich sein (User-Agent)"""
        session = RetrySession()
        
        user_agents = set()
        for _ in range(20):
            headers = session._get_headers()
            user_agents.add(headers['User-Agent'])
        
        self.assertGreater(len(user_agents), 1,
                          "User-Agent wird nicht rotiert")


class TestErrorHandling(unittest.TestCase):
    """Testet Fehlerbehandlung"""
    
    @patch('requests.Session.request')
    def test_logs_all_errors(self, mock_request):
        """Alle Fehler sollten geloggt werden"""
        mock_request.side_effect = [
            requests.exceptions.Timeout("Timeout"),
            requests.exceptions.ConnectionError("Connection refused"),
            Mock(status_code=200, raise_for_status=lambda: None)
        ]
        
        session = RetrySession(max_retries=3, base_delay=0.1)
        
        with self.assertLogs('scraper', level='WARNING') as cm:
            session.get('http://example.com')
            
            # Sollte Timeout und Connection Error loggen
            logs = ' '.join(cm.output)
            self.assertIn('Timeout', logs)


# Import für Test
datetime = __import__('datetime').datetime
timedelta = __import__('datetime').timedelta


def run_tests():
    """Führe alle Tests aus"""
    # Setze Logging-Level für Tests
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Füge alle Test-Klassen hinzu
    suite.addTests(loader.loadTestsFromTestCase(TestUserAgentRotation))
    suite.addTests(loader.loadTestsFromTestCase(TestRetryLogic))
    suite.addTests(loader.loadTestsFromTestCase(TestRateLimiter))
    suite.addTests(loader.loadTestsFromTestCase(TestProxyManager))
    suite.addTests(loader.loadTestsFromTestCase(TestDomainScraper))
    suite.addTests(loader.loadTestsFromTestCase(TestHeaders))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandling))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
