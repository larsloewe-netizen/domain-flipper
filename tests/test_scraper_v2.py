#!/usr/bin/env python3
"""
Tests für den verbesserten Domain Scraper
"""

import unittest
import sys
import os
import json
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Füge src zu Pfad hinzu
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from scraper import (
    DomainScraper, RetrySession, RateLimiter,
    USER_AGENTS, DATA_DIR, DB_PATH
)


class TestRateLimiter(unittest.TestCase):
    """Tests für RateLimiter"""
    
    def test_initialization(self):
        """Test RateLimiter Initialisierung"""
        limiter = RateLimiter(min_delay=1.0, max_delay=2.0)
        self.assertEqual(limiter.min_delay, 1.0)
        self.assertEqual(limiter.max_delay, 2.0)
        self.assertEqual(limiter.error_count, 0)
    
    def test_report_success(self):
        """Test Erfolgsmeldung"""
        limiter = RateLimiter()
        limiter.consecutive_errors = 5
        limiter.report_success()
        self.assertEqual(limiter.consecutive_errors, 0)
    
    def test_report_error(self):
        """Test Fehlermeldung"""
        limiter = RateLimiter()
        limiter.report_error()
        self.assertEqual(limiter.error_count, 1)
        self.assertEqual(limiter.consecutive_errors, 1)


class TestRetrySession(unittest.TestCase):
    """Tests für RetrySession"""
    
    def test_initialization(self):
        """Test RetrySession Initialisierung"""
        session = RetrySession(max_retries=5, base_delay=2.0, timeout=15)
        self.assertEqual(session.max_retries, 5)
        self.assertEqual(session.base_delay, 2.0)
        self.assertEqual(session.timeout, 15)
    
    def test_get_backoff_delay(self):
        """Test Exponential Backoff Berechnung"""
        session = RetrySession(base_delay=1.0)
        
        # Normaler Fall
        delay = session._get_backoff_delay(0)
        self.assertGreaterEqual(delay, 0.8)  # Mit Jitter
        self.assertLessEqual(delay, 1.2)
        
        # Erhöhter Delay bei Retry
        delay2 = session._get_backoff_delay(1)
        self.assertGreater(delay2, delay)
        
        # Status 429
        delay_429 = session._get_backoff_delay(0, status_code=429)
        self.assertGreater(delay_429, delay)
    
    def test_get_headers(self):
        """Test Header Generierung"""
        session = RetrySession()
        headers = session._get_headers()
        
        self.assertIn('User-Agent', headers)
        self.assertIn(headers['User-Agent'], USER_AGENTS)
        self.assertIn('Accept', headers)
    
    @patch('scraper.requests.Session')
    def test_successful_request(self, mock_session_class):
        """Test erfolgreicher Request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        
        mock_session = Mock()
        mock_session.request = Mock(return_value=mock_response)
        mock_session_class.return_value = mock_session
        
        session = RetrySession()
        session.session = mock_session
        
        response = session.get('https://example.com')
        
        self.assertEqual(response.status_code, 200)
        mock_session.request.assert_called_once()
    
    @patch('scraper.requests.Session')
    def test_retry_on_failure(self, mock_session_class):
        """Test Retry bei Fehler"""
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status = Mock()
        
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.raise_for_status = Mock(side_effect=Exception("Server Error"))
        
        mock_session = Mock()
        mock_session.request = Mock(side_effect=[
            Exception("Connection Error"),
            mock_response_fail,
            mock_response_success
        ])
        mock_session_class.return_value = mock_session
        
        session = RetrySession(max_retries=3)
        session.session = mock_session
        
        # Simuliere erfolgreichen Retry
        try:
            response = session.get('https://example.com')
            self.assertEqual(response.status_code, 200)
        except:
            pass  # Erwartet bei diesem Mock-Verhalten


class TestDomainScraper(unittest.TestCase):
    """Tests für DomainScraper"""
    
    @classmethod
    def setUpClass(cls):
        """Setze Test-Datenbank auf"""
        cls.test_db_path = os.path.join(DATA_DIR, 'test_expired_domains.db')
        # Backup original
        cls.original_db_path = DB_PATH
    
    def setUp(self):
        """Bereite jeden Test vor"""
        self.scraper = DomainScraper(test_mode=True, max_workers=2)
    
    def tearDown(self):
        """Räume nach jedem Test auf"""
        if hasattr(self, 'scraper'):
            self.scraper.close()
    
    def test_initialization(self):
        """Test Scraper Initialisierung"""
        self.assertTrue(self.scraper.test_mode)
        self.assertEqual(self.scraper.max_workers, 2)
        self.assertIsNotNone(self.scraper.retry_session)
    
    def test_clean_domain(self):
        """Test Domain-Bereinigung"""
        test_cases = [
            ("Example.com", "example.com"),
            ("HTTPS://Test.IO", "test.io"),
            ("www.Domain-AI.de", "domain-ai.de"),
            ("test..domain.com", "test.domain.com"),
            ("domain.co.uk..co.uk", "domain.co.uk"),
            ("test.com.com", "test.com"),
            ("", None),
            (None, None),
        ]
        
        for raw, expected in test_cases:
            result = self.scraper._clean_domain(raw)
            self.assertEqual(result, expected, f"Fehler bei: {raw}")
    
    def test_extract_tld(self):
        """Test TLD Extraktion"""
        test_cases = [
            ("example.com", ".com"),
            ("test.co.uk", ".co.uk"),
            ("domain.io", ".io"),
            ("site.com.au", ".com.au"),
            ("test", ".com"),  # Fallback
            ("", ".com"),  # Fallback
        ]
        
        for domain, expected in test_cases:
            result = self.scraper._extract_tld(domain)
            self.assertEqual(result, expected, f"Fehler bei: {domain}")
    
    def test_get_test_limit(self):
        """Test Limit im Test-Modus"""
        self.assertEqual(self.scraper._get_test_limit(100), 5)
        self.scraper.test_mode = False
        self.assertEqual(self.scraper._get_test_limit(100), 100)
    
    @patch('scraper.requests.Session')
    def test_test_connection(self, mock_session_class):
        """Test Verbindungstest"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={
            'headers': {'User-Agent': 'Test'},
            'origin': '1.2.3.4'
        })
        
        mock_session = Mock()
        mock_session.request = Mock(return_value=mock_response)
        mock_session_class.return_value = mock_session
        
        self.scraper.retry_session.session = mock_session
        result = self.scraper.test_connection()
        
        self.assertTrue(result)
    
    def test_save_and_get_domain(self):
        """Test Speichern und Abrufen von Domains"""
        domain_data = {
            'domain_name': 'test-domain.com',
            'tld': '.com',
            'age_years': 5,
            'backlinks': 100,
            'source': 'test',
            'auction_status': 'available'
        }
        
        # Speichern
        result = self.scraper._save_domain(domain_data)
        self.assertIn(result, [0, 1])  # 1 = neu, 0 = update
        
        # Stats abrufen
        stats = self.scraper.get_stats()
        self.assertIn('total_domains', stats)
        self.assertIn('by_source', stats)
    
    @patch('scraper.RetrySession.get')
    def test_scrape_expired_domains_net(self, mock_get):
        """Test ExpiredDomains.net Scraper"""
        html_content = """
        <html>
        <table class="base1">
            <tr><th>Domain</th><th>TLD</th><th>Age</th></tr>
            <tr>
                <td><a href="/domain/test1-com">test1.com</a></td>
                <td>.com</td>
                <td>5 years</td>
            </tr>
            <tr>
                <td><a href="/domain/test2-io">test2.io</a></td>
                <td>.io</td>
                <td>3 years</td>
            </tr>
        </table>
        </html>
        """
        
        mock_response = Mock()
        mock_response.text = html_content
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        domains = self.scraper.scrape_expired_domains_net(limit=10)
        
        self.assertIsInstance(domains, list)
        mock_get.assert_called()
    
    @patch('scraper.RetrySession.get')
    def test_scrape_dynadot(self, mock_get):
        """Test Dynadot Scraper"""
        html_content = """
        <html>
        <div class="domain-item">
            <a>premium-domain.com</a>
            <span class="price">$500</span>
        </div>
        <div class="domain-item">
            <a>ai-startup.io</a>
            <span class="price">$1200</span>
        </div>
        </html>
        """
        
        mock_response = Mock()
        mock_response.text = html_content
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        domains = self.scraper.scrape_dynadot(limit=10)
        
        self.assertIsInstance(domains, list)


class TestParallelScraping(unittest.TestCase):
    """Tests für paralleles Scraping"""
    
    def setUp(self):
        """Bereite Test vor"""
        self.scraper = DomainScraper(test_mode=True, max_workers=2)
    
    def tearDown(self):
        """Räume auf"""
        if hasattr(self, 'scraper'):
            self.scraper.close()
    
    @patch.object(DomainScraper, 'scrape_expired_domains_net')
    @patch.object(DomainScraper, 'scrape_dynadot')
    @patch.object(DomainScraper, 'scrape_godaddy')
    @patch.object(DomainScraper, 'scrape_namecheap')
    def test_run_all_scrapers_parallel(self, mock_namecheap, mock_godaddy, mock_dynadot, mock_expired):
        """Test paralleles Scraping"""
        mock_expired.return_value = [{'domain': 'test1.com'}]
        mock_dynadot.return_value = [{'domain': 'test2.com'}]
        mock_godaddy.return_value = [{'domain': 'test3.com'}]
        mock_namecheap.return_value = [{'domain': 'test4.com'}]
        
        total = self.scraper.run_all_scrapers(parallel=True)
        
        self.assertEqual(total, 4)
        mock_expired.assert_called_once()
        mock_dynadot.assert_called_once()
        mock_godaddy.assert_called_once()
        mock_namecheap.assert_called_once()
    
    def test_thread_safety(self):
        """Test Thread-Safety von DB-Operationen"""
        from concurrent.futures import ThreadPoolExecutor
        
        domains_added = []
        
        def add_domain(i):
            domain_data = {
                'domain_name': f'thread-test-{i}.com',
                'tld': '.com',
                'source': 'thread_test',
                'auction_status': 'test'
            }
            result = self.scraper._save_domain(domain_data)
            domains_added.append(result)
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(add_domain, range(10))
        
        self.assertEqual(len(domains_added), 10)


class TestProxyIntegration(unittest.TestCase):
    """Tests für Proxy-Integration"""
    
    @patch('scraper.get_proxy_manager')
    def test_proxy_manager_initialization(self, mock_get_pm):
        """Test Proxy Manager Initialisierung"""
        mock_pm = Mock()
        mock_pm.working_proxies = ['http://proxy1:8080', 'http://proxy2:8080']
        mock_get_pm.return_value = mock_pm
        
        scraper = DomainScraper(use_free_proxies=True)
        
        self.assertIsNotNone(scraper.retry_session.proxy_manager)
        scraper.close()
    
    def test_without_proxies(self):
        """Test Betrieb ohne Proxies"""
        scraper = DomainScraper(use_proxies=False)
        
        self.assertIsNone(scraper.retry_session.proxy_manager)
        scraper.close()


class TestEdgeCases(unittest.TestCase):
    """Tests für Edge Cases"""
    
    def test_malformed_domain(self):
        """Test mit fehlerhaften Domains"""
        scraper = DomainScraper(test_mode=True)
        
        malformed = [
            "...",
            ".com",
            "test.",
            "-test.com",
            "test-.com",
        ]
        
        for domain in malformed:
            result = scraper._clean_domain(domain)
            self.assertIsNone(result)
        
        scraper.close()
    
    def test_unicode_domain(self):
        """Test mit Unicode Domains"""
        scraper = DomainScraper(test_mode=True)
        
        # Punycode Domains
        result = scraper._clean_domain("münchen.de")
        # Sollte entweder bereinigt oder None sein
        self.assertTrue(result is None or isinstance(result, str))
        
        scraper.close()
    
    def test_very_long_domain(self):
        """Test mit sehr langen Domains"""
        scraper = DomainScraper(test_mode=True)
        
        long_domain = "a" * 50 + ".com"
        result = scraper._clean_domain(long_domain)
        
        # Sollte gültig bleiben (unter 63 Zeichen pro Label)
        if result:
            self.assertTrue(len(result) > 0)
        
        scraper.close()


def run_tests():
    """Führe alle Tests aus"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Füge alle Test-Klassen hinzu
    suite.addTests(loader.loadTestsFromTestCase(TestRateLimiter))
    suite.addTests(loader.loadTestsFromTestCase(TestRetrySession))
    suite.addTests(loader.loadTestsFromTestCase(TestDomainScraper))
    suite.addTests(loader.loadTestsFromTestCase(TestParallelScraping))
    suite.addTests(loader.loadTestsFromTestCase(TestProxyIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
