#!/usr/bin/env python3
"""
Auto-Listing Tests
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.auto_listing import (
    AutoListingManager, SedoAPI, AfternicAPI, DanAPI,
    PriceOptimizer, OutreachAutomator, EmailTemplate, ListingConfig,
    init_auto_listing_db
)

def test_imports():
    """Testet ob alle Klassen importierbar sind"""
    print("✅ Alle Importe erfolgreich")
    return True

def test_database_init():
    """Testet Datenbank-Initialisierung"""
    init_auto_listing_db()
    print("✅ Datenbank initialisiert")
    return True

def test_price_optimizer():
    """Testet Preis-Optimierung"""
    optimizer = PriceOptimizer()
    
    test_cases = [
        ('cloudai.com', 85),
        ('myshop.io', 65),
        ('test.com', 50),
    ]
    
    for domain, score in test_cases:
        price = optimizer.calculate_start_price(domain, score)
        assert price > 0, f"Preis für {domain} sollte > 0 sein"
        print(f"✅ {domain} (Score {score}): ${price:.0f}")
    
    return True

def test_email_templates():
    """Testet E-Mail Templates"""
    templates = ['initial_offer', 'follow_up', 'final_call']
    
    for template_id in templates:
        subject, body = EmailTemplate.render(
            template_id,
            domain='test.com',
            similar_domain='test.io',
            recipient_name='Test',
            price='1000',
            new_price='900',
            original_price='1000',
            industry='Technology',
            deadline='2024-12-31'
        )
        assert subject, f"Subject für {template_id} sollte existieren"
        assert body, f"Body für {template_id} sollte existieren"
        print(f"✅ Template '{template_id}' gerendert")
    
    return True

def test_sandbox_listing():
    """Testet Sandbox-Listing"""
    manager = AutoListingManager(sandbox=True)
    
    results = manager.list_domain_on_all_platforms('test-example-domain.com', 60)
    
    for platform, result in results.items():
        assert result.get('success'), f"{platform} Listing sollte erfolgreich sein"
        assert result.get('sandbox'), f"{platform} sollte Sandbox-Flag haben"
        print(f"✅ {platform}: {result.get('listing_id')}")
    
    return True

def test_whois_lookup():
    """Testet WHOIS-Lookup"""
    whois = OutreachAutomator().whois
    
    # Teste ähnliche Domains
    similar = whois.find_similar_domains('cloudai.com')
    assert len(similar) > 0, "Sollte ähnliche Domains finden"
    print(f"✅ {len(similar)} ähnliche Domains gefunden")
    
    # Teste WHOIS-Lookup (simuliert)
    result = whois.lookup('example.com')
    assert result.get('domain_name') == 'example.com'
    print("✅ WHOIS-Lookup funktioniert")
    
    return True

def run_all_tests():
    """Führt alle Tests aus"""
    tests = [
        ('Imports', test_imports),
        ('Datenbank', test_database_init),
        ('Preis-Optimierung', test_price_optimizer),
        ('E-Mail Templates', test_email_templates),
        ('Sandbox Listing', test_sandbox_listing),
        ('WHOIS Lookup', test_whois_lookup),
    ]
    
    print("=" * 50)
    print("Auto-Listing Tests")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            print(f"\n🧪 Test: {name}")
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ Fehler in {name}: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Ergebnis: {passed} bestanden, {failed} fehlgeschlagen")
    print("=" * 50)
    
    return failed == 0

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
