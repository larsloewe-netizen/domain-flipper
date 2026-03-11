#!/usr/bin/env python3
"""
Demo-Skript für das Auto-Purchasing System
Zeigt alle Features ohne echte Käufe (Sandbox-Modus)
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from auto_purchaser import AutoPurchaser


def demo():
    print("=" * 70)
    print("🛒 AUTO-PURCHASER DEMO")
    print("=" * 70)
    print()
    
    base_dir = Path('/root/.openclaw/workspace/projects/domain-flipper')
    config_path = base_dir / 'config' / 'purchase_rules.yaml'
    db_path = base_dir / 'data' / 'purchases.db'
    
    # Stelle sicher, dass data-Verzeichnis existiert
    db_path.parent.mkdir(exist_ok=True)
    
    print(f"📁 Config: {config_path}")
    print(f"🗄️  Datenbank: {db_path}")
    print()
    
    # Initialisiere AutoPurchaser
    purchaser = AutoPurchaser(str(config_path), str(db_path))
    
    print("-" * 70)
    print("📊 AKTUELLE LIMITS")
    print("-" * 70)
    limits = purchaser.get_purchase_limits()
    print(f"  Heute gekauft: {limits.daily_domains} Domains (${limits.daily_amount:.2f})")
    print(f"  Verfügbar heute: {limits.remaining_daily_domains} Domains (${limits.remaining_daily_amount:.2f})")
    print()
    
    print("-" * 70)
    print("🧪 SANDBOX-TESTS")
    print("-" * 70)
    
    test_cases = [
        ("cloudai.com", 85, "High-Score Domain"),
        ("fintech.io", 78, "Guter Score"),
        ("lowscore.xyz", 40, "Zu niedriger Score"),
        ("bad-tld.tk", 80, "Blockierte TLD"),
        ("test.com", 90, "Erfolgreicher Kauf"),
    ]
    
    for domain, score, description in test_cases:
        print(f"\n  Test: {description}")
        print(f"  Domain: {domain} | Score: {score}")
        
        result = purchaser.attempt_purchase(domain, score)
        
        if result.success:
            print(f"  ✅ ERFOLG: ${result.price:.2f} via {result.provider}")
            print(f"     TX-ID: {result.transaction_id}")
        else:
            print(f"  ❌ FEHLGESCHLAGEN: {result.error_message}")
            if result.requires_manual_approval:
                print(f"     ⚠️  Manuelle Freigabe erforderlich!")
    
    print()
    print("-" * 70)
    print("📋 KAUF-HISTORIE")
    print("-" * 70)
    history = purchaser.get_purchase_history(days=1)
    successful = [h for h in history if h['success']]
    failed = [h for h in history if not h['success']]
    
    print(f"  Erfolgreich: {len(successful)}")
    print(f"  Fehlgeschlagen: {len(failed)}")
    
    if successful:
        print("\n  Letzte erfolgreiche Käufe:")
        for h in successful[-3:]:
            mode = "🧪" if h['sandbox_mode'] else "🔴"
            print(f"    {mode} {h['domain']} @ ${h['price']:.2f}")
    
    print()
    print("-" * 70)
    print("📝 BERICHT")
    print("-" * 70)
    print(purchaser.generate_report())
    
    print()
    print("=" * 70)
    print("✅ DEMO ABGESCHLOSSEN")
    print("=" * 70)
    print()
    print("Hinweise:")
    print("  • Alle Käufe liefen im SANDBOX-Modus (keine echten Käufe!)")
    print("  • Für echte Käufe: sandbox_mode in config/purchase_rules.yaml auf false setzen")
    print("  • API-Keys müssen in der Config hinterlegt werden")
    print()
    print("Verwendung:")
    print("  python3 src/auto_purchaser.py --domain 'example.com' --score 80")
    print("  python3 src/auto_purchaser.py --report")


if __name__ == "__main__":
    demo()
