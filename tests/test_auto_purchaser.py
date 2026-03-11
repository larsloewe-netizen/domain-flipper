#!/usr/bin/env python3
"""
Tests für das Auto-Purchasing System
WICHTIG: Alle Tests laufen im Sandbox-Modus!
"""

import os
import sys
import json
import sqlite3
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Füge src zum Pfad hinzu
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from auto_purchaser import (
    AutoPurchaser, NamecheapAPI, DynadotAPI,
    PurchaseAttempt, PurchaseLimits
)


class TestNamecheapAPI:
    """Tests für Namecheap API Integration"""
    
    @pytest.fixture
    def sandbox_config(self):
        return {
            'enabled': True,
            'sandbox': True,
            'api_user': 'test_user',
            'api_key': 'test_key',
            'username': 'test_user',
            'client_ip': '127.0.0.1'
        }
    
    @pytest.fixture
    def disabled_config(self):
        return {
            'enabled': False,
            'sandbox': True,
            'api_user': '',
            'api_key': '',
            'username': '',
            'client_ip': ''
        }
    
    def test_initialization_sandbox(self, sandbox_config):
        """Test: API initialisiert korrekt im Sandbox-Modus"""
        api = NamecheapAPI(sandbox_config)
        assert api.sandbox is True
        assert api.enabled is True
        assert api.base_url == api.SANDBOX_URL
    
    def test_initialization_disabled(self, disabled_config):
        """Test: API funktioniert auch wenn deaktiviert"""
        api = NamecheapAPI(disabled_config)
        assert api.enabled is False
    
    def test_check_availability_sandbox(self, sandbox_config):
        """Test: Sandbox gibt simulierte Verfügbarkeit zurück"""
        api = NamecheapAPI(sandbox_config)
        available, price = api.check_availability('test.com')
        
        # Sandbox gibt zufällige aber valide Ergebnisse
        assert isinstance(available, bool)
        if available:
            assert price is not None
            assert 8.0 <= price <= 15.0
    
    def test_purchase_domain_sandbox(self, sandbox_config):
        """Test: Sandbox-Kauf simuliert erfolgreichen Kauf"""
        api = NamecheapAPI(sandbox_config)
        success, tx_id, error = api.purchase_domain('test.com')
        
        assert success is True
        assert tx_id is not None
        assert tx_id.startswith('SANDBOX_')
        assert error is None
    
    def test_get_balance_sandbox(self, sandbox_config):
        """Test: Sandbox gibt Dummy-Balance zurück"""
        api = NamecheapAPI(sandbox_config)
        balance = api.get_balance()
        
        assert balance == 1000.0


class TestDynadotAPI:
    """Tests für Dynadot API Integration"""
    
    @pytest.fixture
    def sandbox_config(self):
        return {
            'enabled': True,
            'sandbox': True,
            'api_key': 'test_key'
        }
    
    def test_initialization(self, sandbox_config):
        """Test: API initialisiert korrekt"""
        api = DynadotAPI(sandbox_config)
        assert api.sandbox is True
        assert api.enabled is True
    
    def test_check_availability_sandbox(self, sandbox_config):
        """Test: Sandbox gibt simulierte Verfügbarkeit zurück"""
        api = DynadotAPI(sandbox_config)
        available, price = api.check_availability('test.io')
        
        assert isinstance(available, bool)
        if available:
            assert price is not None
    
    def test_purchase_domain_sandbox(self, sandbox_config):
        """Test: Sandbox-Kauf simuliert erfolgreichen Kauf"""
        api = DynadotAPI(sandbox_config)
        success, tx_id, error = api.purchase_domain('test.io')
        
        assert success is True
        assert tx_id is not None
        assert error is None


class TestAutoPurchaser:
    """Tests für AutoPurchaser Hauptklasse"""
    
    @pytest.fixture
    def temp_db(self):
        """Erstellt temporäre Datenbank"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)
    
    @pytest.fixture
    def test_config(self):
        """Test-Konfiguration"""
        return {
            'sandbox_mode': True,
            'enabled': True,
            'auto_purchase': {
                'min_score': 75,
                'max_price': 20.0,
                'require_manual_approval': False
            },
            'limits': {
                'daily': {'max_domains': 5, 'max_amount_usd': 500},
                'weekly': {'max_domains': 20, 'max_amount_usd': 2000},
                'monthly': {'max_domains': 50, 'max_amount_usd': 5000}
            },
            'manual_approval': {
                'enabled': True,
                'price_threshold': 50.0
            },
            'tld_blacklist': ['tk', 'ml', 'ga'],
            'tld_whitelist': [],
            'notifications': {
                'email': {'enabled': False},
                'telegram': {'enabled': False}
            },
            'apis': {
                'namecheap': {
                    'enabled': True,
                    'sandbox': True,
                    'api_user': 'test',
                    'api_key': 'test',
                    'username': 'test',
                    'client_ip': '127.0.0.1'
                },
                'dynadot': {
                    'enabled': True,
                    'sandbox': True,
                    'api_key': 'test'
                }
            },
            'cooldown': {'seconds_between_purchases': 0}
        }
    
    @pytest.fixture
    def purchaser(self, temp_db, test_config):
        """Erstellt AutoPurchaser mit Test-Konfiguration"""
        # Schreibe Config in temporäre Datei
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(test_config, f)
            config_path = f.name
        
        purchaser = AutoPurchaser(config_path, temp_db)
        
        yield purchaser
        
        os.unlink(config_path)
    
    def test_initialization(self, purchaser):
        """Test: AutoPurchaser initialisiert korrekt"""
        assert purchaser.config is not None
        assert purchaser.db_path is not None
        assert len(purchaser.apis) == 2  # Namecheap + Dynadot
    
    def test_tld_blacklist(self, purchaser):
        """Test: Blockierte TLDs werden erkannt"""
        assert purchaser._is_tld_blocked('test.tk') is True
        assert purchaser._is_tld_blocked('test.ml') is True
        assert purchaser._is_tld_blocked('test.com') is False
        assert purchaser._is_tld_blocked('test.io') is False
    
    def test_tld_whitelist(self, temp_db):
        """Test: Whitelist funktioniert korrekt"""
        config = {
            'sandbox_mode': True,
            'tld_blacklist': [],
            'tld_whitelist': ['com', 'io'],
            'apis': {},
            'limits': {},
            'manual_approval': {},
            'notifications': {},
            'auto_purchase': {}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(config, f)
            config_path = f.name
        
        purchaser = AutoPurchaser(config_path, temp_db)
        
        assert purchaser._is_tld_blocked('test.com') is False
        assert purchaser._is_tld_blocked('test.io') is False
        assert purchaser._is_tld_blocked('test.net') is True
        
        os.unlink(config_path)
    
    def test_limits_initial(self, purchaser):
        """Test: Limits sind initial 0"""
        limits = purchaser.get_purchase_limits()
        assert limits.daily_domains == 0
        assert limits.daily_amount == 0.0
        assert limits.remaining_daily_domains == 5
        assert limits.remaining_daily_amount == 500.0
    
    def test_check_limits_allowed(self, purchaser):
        """Test: Kauf innerhalb der Limits erlaubt"""
        allowed, error = purchaser.check_limits(10.0)
        assert allowed is True
        assert error is None
    
    def test_check_limits_exceed_daily_domains(self, purchaser, temp_db):
        """Test: Tägliches Domain-Limit wird enforced"""
        # Simuliere 5 Käufe heute
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        today = datetime.now().date().isoformat()
        cursor.execute('''
            INSERT INTO purchase_stats (date, domains_purchased, total_amount)
            VALUES (?, 5, 100.0)
        ''', (today,))
        conn.commit()
        conn.close()
        
        allowed, error = purchaser.check_limits(10.0)
        assert allowed is False
        assert 'tägliches' in error.lower() or 'daily' in error.lower()
    
    def test_check_limits_exceed_daily_amount(self, purchaser, temp_db):
        """Test: Tägliches Budget-Limit wird enforced"""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        today = datetime.now().date().isoformat()
        cursor.execute('''
            INSERT INTO purchase_stats (date, domains_purchased, total_amount)
            VALUES (?, 1, 490.0)
        ''', (today,))
        conn.commit()
        conn.close()
        
        allowed, error = purchaser.check_limits(20.0)
        assert allowed is False
        assert 'budget' in error.lower() or 'amount' in error.lower()
    
    def test_manual_approval_required(self, purchaser):
        """Test: Manuelle Freigabe bei hohen Preisen"""
        assert purchaser.requires_manual_approval(60.0) is True
        assert purchaser.requires_manual_approval(50.0) is False
        assert purchaser.requires_manual_approval(30.0) is False
    
    def test_attempt_purchase_blocked_tld(self, purchaser):
        """Test: Kauf blockierter TLD schlägt fehl"""
        result = purchaser.attempt_purchase('test.tk', score=80)
        
        assert result.success is False
        assert 'blacklist' in result.error_message.lower()
        assert result.sandbox_mode is True
    
    def test_attempt_purchase_low_score(self, purchaser):
        """Test: Kauf mit zu niedrigem Score schlägt fehl"""
        result = purchaser.attempt_purchase('test.com', score=50)
        
        assert result.success is False
        assert 'score' in result.error_message.lower()
    
    def test_attempt_purchase_high_price(self, purchaser):
        """Test: Kauf mit zu hohem Preis schlägt fehl"""
        # Mit force=True um Score-Check zu umgehen, aber Preis-Limit soll greifen
        result = purchaser.attempt_purchase('test.com', score=80, max_price=5.0)
        
        assert result.success is False
    
    def test_attempt_purchase_force(self, purchaser):
        """Test: Force-Kauf ignoriert Score-Kriterien"""
        result = purchaser.attempt_purchase('test.com', score=50, force=True)
        
        # Sollte nicht wegen Score fehlschlagen
        # Kann aber aus anderen Gründen fehlschlagen (nicht verfügbar, etc.)
        if not result.success:
            assert 'score' not in result.error_message.lower()
    
    def test_log_attempt(self, purchaser, temp_db):
        """Test: Kaufversuch wird in Datenbank geloggt"""
        attempt = PurchaseAttempt(
            domain='test.com',
            price=10.0,
            score=80,
            provider='namecheap',
            success=True,
            timestamp=datetime.now().isoformat(),
            transaction_id='TX123',
            sandbox_mode=True
        )
        
        purchaser.log_attempt(attempt)
        
        # Prüfe Datenbank
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM purchase_attempts WHERE domain = ?', ('test.com',))
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[1] == 'test.com'  # domain column
        assert row[4] == 'namecheap'  # provider column
    
    def test_update_stats(self, purchaser, temp_db):
        """Test: Statistiken werden korrekt aktualisiert"""
        purchaser.update_stats(15.0, success=True)
        purchaser.update_stats(20.0, success=True)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        today = datetime.now().date().isoformat()
        cursor.execute('SELECT domains_purchased, total_amount FROM purchase_stats WHERE date = ?', (today,))
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == 2  # 2 Domains
        assert row[1] == 35.0  # $35 total
    
    def test_get_pending_approvals(self, purchaser, temp_db):
        """Test: Ausstehende Freigaben werden korrekt geholt"""
        # Füge Test-Daten ein
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO purchase_attempts 
            (domain, price, score, provider, success, requires_manual_approval, sandbox_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('expensive.com', 75.0, 85, 'namecheap', False, True, True))
        conn.commit()
        conn.close()
        
        pending = purchaser.get_pending_approvals()
        
        assert len(pending) == 1
        assert pending[0]['domain'] == 'expensive.com'
        assert pending[0]['price'] == 75.0
    
    def test_approve_purchase(self, purchaser, temp_db):
        """Test: Kauf wird korrekt freigegeben"""
        # Füge Test-Daten ein
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO purchase_attempts 
            (domain, price, score, provider, success, requires_manual_approval, sandbox_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('approval-test.com', 75.0, 85, 'namecheap', False, True, True))
        conn.commit()
        conn.close()
        
        result = purchaser.approve_purchase('approval-test.com', 'admin_user')
        
        assert result is True
        
        # Prüfe Datenbank
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute('SELECT user_approved, approved_by FROM purchase_attempts WHERE domain = ?', 
                      ('approval-test.com',))
        row = cursor.fetchone()
        conn.close()
        
        assert row[0] == 1  # user_approved
        assert row[1] == 'admin_user'  # approved_by
    
    def test_get_purchase_history(self, purchaser, temp_db):
        """Test: Kaufhistorie wird korrekt geholt"""
        # Füge Test-Daten ein
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO purchase_attempts 
            (domain, price, score, provider, success, timestamp, sandbox_mode)
            VALUES 
                (?, ?, ?, ?, ?, ?, ?),
                (?, ?, ?, ?, ?, ?, ?)
        ''', ('hist1.com', 10.0, 80, 'namecheap', True, now, True,
              'hist2.com', 15.0, 75, 'dynadot', False, now, True))
        conn.commit()
        conn.close()
        
        history = purchaser.get_purchase_history(days=30)
        
        assert len(history) == 2
    
    def test_generate_report(self, purchaser):
        """Test: Bericht wird generiert"""
        report = purchaser.generate_report()
        
        assert 'AUTO-PURCHASER BERICHT' in report
        assert 'LIMITS' in report
        assert 'Sandbox-Modus' in report


class TestIntegration:
    """Integrationstests mit verschiedenen Szenarien"""
    
    @pytest.fixture
    def integration_setup(self):
        """Erstellt vollständiges Test-Setup"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        config = {
            'sandbox_mode': True,
            'enabled': True,
            'auto_purchase': {
                'min_score': 75,
                'max_price': 20.0
            },
            'limits': {
                'daily': {'max_domains': 5, 'max_amount_usd': 500},
                'weekly': {'max_domains': 20, 'max_amount_usd': 2000},
                'monthly': {'max_domains': 50, 'max_amount_usd': 5000}
            },
            'manual_approval': {
                'enabled': True,
                'price_threshold': 50.0
            },
            'tld_blacklist': ['tk', 'ml', 'ga', 'cf', 'gq'],
            'notifications': {
                'email': {'enabled': False},
                'telegram': {'enabled': False}
            },
            'apis': {
                'namecheap': {
                    'enabled': True,
                    'sandbox': True,
                    'api_user': 'test',
                    'api_key': 'test',
                    'username': 'test',
                    'client_ip': '127.0.0.1'
                },
                'dynadot': {
                    'enabled': True,
                    'sandbox': True,
                    'api_key': 'test'
                }
            },
            'cooldown': {'seconds_between_purchases': 0},
            'retry': {'max_attempts': 1, 'delay_seconds': 0}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(config, f)
            config_path = f.name
        
        purchaser = AutoPurchaser(config_path, db_path)
        
        yield purchaser, db_path, config_path
        
        os.unlink(db_path)
        os.unlink(config_path)
    
    def test_full_purchase_flow_success(self, integration_setup):
        """Test: Kompletter erfolgreicher Kauf-Flow"""
        purchaser, db_path, _ = integration_setup
        
        # Simuliere verfügbare Domain
        with patch.object(purchaser.apis['namecheap'], 'check_availability', return_value=(True, 12.50)):
            with patch.object(purchaser.apis['namecheap'], 'purchase_domain', return_value=(True, 'TX123', None)):
                result = purchaser.attempt_purchase('cloudai.com', score=85)
        
        assert result.success is True
        assert result.price == 12.50
        assert result.transaction_id == 'TX123'
        
        # Prüfe Datenbank
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT success FROM purchase_attempts WHERE domain = ?', ('cloudai.com',))
        row = cursor.fetchone()
        conn.close()
        
        assert row[0] == 1
    
    def test_full_purchase_flow_domain_unavailable(self, integration_setup):
        """Test: Kauf nicht verfügbarer Domain"""
        purchaser, db_path, _ = integration_setup
        
        # Simuliere nicht verfügbare Domain
        with patch.object(purchaser.apis['namecheap'], 'check_availability', return_value=(False, None)):
            with patch.object(purchaser.apis['dynadot'], 'check_availability', return_value=(False, None)):
                result = purchaser.attempt_purchase('taken.com', score=85)
        
        assert result.success is False
        assert 'nicht verfügbar' in result.error_message.lower() or 'not available' in result.error_message.lower()
    
    def test_full_purchase_flow_limits_reached(self, integration_setup):
        """Test: Kauf bei erreichten Limits"""
        purchaser, db_path, _ = integration_setup
        
        # Setze tägliches Limit auf Maximum
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today = datetime.now().date().isoformat()
        cursor.execute('''
            INSERT INTO purchase_stats (date, domains_purchased, total_amount)
            VALUES (?, 5, 500.0)
        ''', (today,))
        conn.commit()
        conn.close()
        
        result = purchaser.attempt_purchase('limited.com', score=90)
        
        assert result.success is False
        assert 'limit' in result.error_message.lower()
    
    def test_price_comparison_across_apis(self, integration_setup):
        """Test: Bestpreis über APIs wird gefunden"""
        purchaser, _, _ = integration_setup
        
        # Simuliere verschiedene Preise
        with patch.object(purchaser.apis['namecheap'], 'check_availability', return_value=(True, 15.00)):
            with patch.object(purchaser.apis['dynadot'], 'check_availability', return_value=(True, 12.00)):
                provider, price = purchaser.find_best_price('test.com')
        
        assert provider == 'dynadot'
        assert price == 12.00
    
    def test_high_price_requires_approval(self, integration_setup):
        """Test: Hoher Preis erfordert manuelle Freigabe"""
        purchaser, db_path, _ = integration_setup
        
        # Konfiguriere höheres max_price für diesen Test, damit der Preis-Check nicht greift
        purchaser.config['auto_purchase']['max_price'] = 100.0
        
        # Simuliere teure Domain über $50 Threshold - bei beiden APIs mocken
        with patch.object(purchaser.apis['namecheap'], 'check_availability', return_value=(True, 75.00)):
            with patch.object(purchaser.apis['namecheap'], 'purchase_domain', return_value=(True, 'TX_APPROVAL', None)):
                # Dynadot auf nicht verfügbar setzen, damit Namecheap genommen wird
                with patch.object(purchaser.apis['dynadot'], 'check_availability', return_value=(False, None)):
                    result = purchaser.attempt_purchase('expensive.com', score=85)
        
        assert result.success is False
        assert result.requires_manual_approval is True
        assert 'manuelle' in result.error_message.lower() or 'manual' in result.error_message.lower() or 'approval' in result.error_message.lower() or 'Freigabe' in result.error_message


class TestSafetyFeatures:
    """Tests für Safety-Features"""
    
    @pytest.fixture
    def safety_setup(self):
        """Setup mit Safety-Fokus"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        config = {
            'sandbox_mode': True,  # Immer True für Tests!
            'enabled': True,
            'auto_purchase': {
                'min_score': 75,
                'max_price': 20.0
            },
            'limits': {
                'daily': {'max_domains': 2, 'max_amount_usd': 100},  # Niedrige Limits für Tests
                'weekly': {'max_domains': 5, 'max_amount_usd': 300},
                'monthly': {'max_domains': 10, 'max_amount_usd': 500}
            },
            'manual_approval': {
                'enabled': True,
                'price_threshold': 30.0  # Niedrig für Tests
            },
            'tld_blacklist': ['tk', 'ml', 'ga', 'cf', 'gq', 'xxx'],
            'notifications': {
                'email': {'enabled': False},
                'telegram': {'enabled': False}
            },
            'backup_wallet': {
                'enabled': True,
                'max_amount_per_purchase': 50,
                'daily_limit': 100
            },
            'apis': {
                'namecheap': {'enabled': True, 'sandbox': True, 'api_user': 't', 'api_key': 't', 'username': 't', 'client_ip': '1.1.1.1'},
                'dynadot': {'enabled': True, 'sandbox': True, 'api_key': 't'}
            },
            'cooldown': {'seconds_between_purchases': 0}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(config, f)
            config_path = f.name
        
        purchaser = AutoPurchaser(config_path, db_path)
        
        yield purchaser, db_path, config_path
        
        os.unlink(db_path)
        os.unlink(config_path)
    
    def test_sandbox_mode_prevents_real_purchases(self, safety_setup):
        """Test: Sandbox-Modus verhindert echte Käufe"""
        purchaser, _, _ = safety_setup
        
        assert purchaser.config['sandbox_mode'] is True
        
        with patch.object(purchaser.apis['namecheap'], 'check_availability', return_value=(True, 10.0)):
            result = purchaser.attempt_purchase('test.com', score=80)
        
        assert result.sandbox_mode is True
        assert 'SANDBOX' in result.transaction_id or result.success is True
    
    def test_adult_tld_blocked(self, safety_setup):
        """Test: Adult-TLDs werden blockiert"""
        purchaser, _, _ = safety_setup
        
        result = purchaser.attempt_purchase('test.xxx', score=80)
        
        assert result.success is False
        assert 'blacklist' in result.error_message.lower()
    
    def test_low_daily_limit_enforced(self, safety_setup):
        """Test: Niedriges tägliches Limit wird enforced"""
        purchaser, db_path, _ = safety_setup
        
        # Setze tägliches Limit auf Maximum (2)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today = datetime.now().date().isoformat()
        cursor.execute('''
            INSERT INTO purchase_stats (date, domains_purchased, total_amount)
            VALUES (?, 2, 50.0)
        ''', (today,))
        conn.commit()
        conn.close()
        
        result = purchaser.attempt_purchase('limit-test.com', score=85)
        
        assert result.success is False
    
    def test_manual_approval_threshold(self, safety_setup):
        """Test: Manuelle Freigabe-Schwelle wird korrekt angewendet"""
        purchaser, _, _ = safety_setup
        
        assert purchaser.requires_manual_approval(35.0) is True
        assert purchaser.requires_manual_approval(30.0) is False
        assert purchaser.requires_manual_approval(25.0) is False


def run_tests():
    """Führt alle Tests aus"""
    import subprocess
    result = subprocess.run(
        ['python', '-m', 'pytest', __file__, '-v', '--tb=short'],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    return result.returncode


if __name__ == '__main__':
    sys.exit(run_tests())
