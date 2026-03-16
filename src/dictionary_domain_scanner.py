#!/usr/bin/env python3
"""
Dictionary Domain Scanner
Durchforstet englische Wörterbücher und prüft Domain-Verfügbarkeit
"""

import subprocess
import json
import re
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import urllib.request
import urllib.error

# Konfiguration
MAX_PRICE_DE = 50  # EUR
MAX_PRICE_COM = 50  # EUR
MAX_PRICE_AI = 100  # EUR
BATCH_SIZE = 50    # Parallele Checks
DELAY_BETWEEN_CHECKS = 0.5  # Sekunden

def load_wordlist():
    """Lade englisches Wörterbuch"""
    print("📚 Lade englisches Wörterbuch...")
    
    # Versuche verschiedene Quellen
    wordlist = []
    
    # Quelle 1: SCOWL Wörterliste (häufigste englische Wörter)
    try:
        url = "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt"
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read().decode('utf-8')
            wordlist = [w.strip().lower() for w in content.split('\n') if w.strip()]
            print(f"✅ {len(wordlist)} Wörter geladen von {url}")
            return wordlist
    except Exception as e:
        print(f"⚠️ Konnte nicht von GitHub laden: {e}")
    
    # Fallback: Lokal generierte Liste
    print("⚠️ Verwende Fallback-Wortliste")
    return []

def filter_words(words):
    """Filtere starke/mittelstarke Wörter"""
    filtered = []
    
    for word in words:
        word = word.lower().strip()
        
        # Filterkriterien
        if len(word) < 4 or len(word) > 15:  # Zu kurz oder zu lang
            continue
        if not word.isalpha():  # Nur Buchstaben
            continue
        if word.endswith('ing') and len(word) > 7:  # Viele Gerundien sind schwach
            continue
        if word.endswith('ed') and len(word) > 8:  # Viele Partizipien sind schwach
            continue
        if re.match(r'^[bcdfghjklmnpqrstvwxz]+$', word):  # Keine Vokale
            continue
            
        filtered.append(word)
    
    return filtered

def check_domain_tld(domain, tld):
    """Prüfe Verfügbarkeit einer Domain mit spezifischer TLD"""
    full_domain = f"{domain}.{tld}"
    
    try:
        result = subprocess.run(
            ['whois', full_domain],
            capture_output=True,
            text=True,
            timeout=5
        )
        whois_text = result.stdout.lower()
        
        # .de Domains
        if tld == 'de':
            if 'status: free' in whois_text or 'not found' in whois_text:
                return {'available': True, 'price': 11.98}
            elif 'status: connect' in whois_text:
                return {'available': False, 'price': None}
        
        # .com und .ai Domains
        elif tld in ['com', 'ai']:
            if 'no match' in whois_text or 'not found' in whois_text:
                # Standard-Preise
                price = 12.0 if tld == 'com' else 100.0
                return {'available': True, 'price': price}
            elif any(x in whois_text for x in ['registrar:', 'name server:', 'status:']):
                return {'available': False, 'price': None}
        
        return {'available': False, 'price': None, 'unclear': True}
        
    except subprocess.TimeoutExpired:
        return {'available': False, 'price': None, 'error': 'timeout'}
    except Exception as e:
        return {'available': False, 'price': None, 'error': str(e)}

def score_word(word):
    """Bewerte die Qualität eines Wortes"""
    score = 0
    
    # Länge (4-8 ist ideal)
    if 4 <= len(word) <= 6:
        score += 30
    elif 7 <= len(word) <= 8:
        score += 20
    elif 9 <= len(word) <= 10:
        score += 10
    
    # Aussprache (Vokale sind gut)
    vowels = sum(1 for c in word if c in 'aeiou')
    vowel_ratio = vowels / len(word)
    if 0.3 <= vowel_ratio <= 0.6:
        score += 15
    
    # Häufige Anfangsbuchstaben (Kommerziell wertvoll)
    if word[0] in 'bcdfghjklmnpqrstvwxz':  # Konsonant am Anfang
        score += 10
    
    # Vermeide doppelte Buchstaben
    if not re.search(r'(.)\1', word):
        score += 10
    
    # Bonus für bestimmte Endungen
    if word.endswith(('er', 'ly', 'al', 'ic', 'on')):
        score += 5
    
    return score

def check_domain_batch(domain_tld_pairs):
    """Prüfe Batch von Domains"""
    results = []
    for domain, tld in domain_tld_pairs:
        result = check_domain_tld(domain, tld)
        result['domain'] = f"{domain}.{tld}"
        result['word'] = domain
        result['tld'] = tld
        result['score'] = score_word(domain)
        results.append(result)
        time.sleep(0.2)  # Rate limiting
    return results

def main():
    print("🚀 Dictionary Domain Scanner gestartet")
    print("=" * 50)
    
    # Wörterbuch laden
    words = load_wordlist()
    if not words:
        print("❌ Kein Wörterbuch geladen")
        return
    
    print(f"📊 {len(words)} Wörter geladen")
    
    # Wörter filtern
    filtered_words = filter_words(words)
    print(f"🔍 {len(filtered_words)} Wörter nach Filterung")
    
    # Begrenze auf erst 5000 Wörter (Performance)
    check_words = filtered_words[:5000]
    print(f"⏱️  Prüfe top {len(check_words)} Wörter")
    
    # Erstelle Domain-Liste zu prüfen
    domain_checks = []
    for word in check_words:
        domain_checks.append((word, 'de'))
        domain_checks.append((word, 'com'))
        domain_checks.append((word, 'ai'))
    
    print(f"🌐 {len(domain_checks)} Domain-Checks geplant")
    print("⏳ Starte parallele Prüfung... (das kann einige Minuten dauern)")
    
    # Parallele Prüfung
    available_domains = []
    checked = 0
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        # Teile in Batches auf
        batches = [domain_checks[i:i+BATCH_SIZE] for i in range(0, len(domain_checks), BATCH_SIZE)]
        futures = [executor.submit(check_domain_batch, batch) for batch in batches]
        
        for future in as_completed(futures):
            try:
                results = future.result()
                for r in results:
                    checked += 1
                    if r.get('available'):
                        # Preis-Check
                        tld = r['tld']
                        price = r.get('price', 0)
                        
                        max_price = MAX_PRICE_DE if tld == 'de' else (MAX_PRICE_COM if tld == 'com' else MAX_PRICE_AI)
                        
                        if price <= max_price:
                            available_domains.append(r)
                            print(f"✅ {r['domain']} (Score: {r['score']}, Preis: {price}€)")
                
                if checked % 100 == 0:
                    print(f"⏳ Fortschritt: {checked}/{len(domain_checks)} geprüft, {len(available_domains)} gefunden")
                    
            except Exception as e:
                print(f"⚠️ Batch-Fehler: {e}")
    
    # Sortiere nach Score
    available_domains.sort(key=lambda x: x['score'], reverse=True)
    
    print("\n" + "=" * 50)
    print(f"🎉 FERTIG! {len(available_domains)} verfügbare Domains gefunden")
    
    # Speichere Ergebnisse
    output_dir = Path('/root/.openclaw/workspace/projects/domain-flipper/data')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    result_file = output_dir / f'dictionary_scan_{timestamp}.json'
    
    with open(result_file, 'w') as f:
        json.dump(available_domains, f, indent=2)
    
    print(f"💾 Ergebnisse gespeichert in: {result_file}")
    
    # Zeige Top 30
    print("\n🏆 TOP 30 VERFÜGBARE DOMAINS:")
    print("-" * 50)
    for i, d in enumerate(available_domains[:30], 1):
        print(f"{i:2}. {d['domain']:20} | Score: {d['score']:3} | Preis: {d.get('price', 'N/A')}€")
    
    # Erstelle CSV für PDF-Generierung
    csv_file = output_dir / f'dictionary_scan_{timestamp}.csv'
    with open(csv_file, 'w') as f:
        f.write("Rank,Domain,Word,TLD,Score,Price\n")
        for i, d in enumerate(available_domains[:1000], 1):
            f.write(f"{i},{d['domain']},{d['word']},{d['tld']},{d['score']},{d.get('price', 'N/A')}\n")
    
    print(f"\n📄 CSV für PDF erstellt: {csv_file}")
    print(f"📊 Top 1000 Domains bereit für PDF-Generierung")
    
    return available_domains

if __name__ == '__main__':
    main()
