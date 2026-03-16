#!/usr/bin/env python3
"""
Dictionary Domain Scanner - GRÜNDLICHE VERSION
Durchforstet englische Wörterbücher und prüft Domain-Verfügbarkeit
Langsamer, aber gründlicher mit besserem Scoring
"""

import subprocess
import json
import re
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import urllib.request
import socket

# Konfiguration - GRÜNDLICHER
MAX_PRICE_DE = 50   # EUR
MAX_PRICE_COM = 50  # EUR
MAX_PRICE_AI = 100  # EUR
BATCH_SIZE = 25     # Kleiner = stabiler
DELAY_BETWEEN_CHECKS = 0.8  # Höher = weniger Rate-Limiting-Probleme
MAX_WORDS = 2500   # Optimiert für 60-90 Minuten Laufzeit

def load_multiple_wordlists():
    """Lade mehrere englische Wörterbücher für bessere Abdeckung"""
    print("📚 Lade englische Wörterbücher...")
    
    all_words = set()  # Set für Eindeutigkeit
    
    # Quelle 1: DWYL English Words (370k Wörter)
    try:
        url = "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read().decode('utf-8')
            words = [w.strip().lower() for w in content.split('\n') if w.strip()]
            all_words.update(words)
            print(f"✅ Quelle 1: {len(words)} Wörter")
    except Exception as e:
        print(f"⚠️ Quelle 1 fehlgeschlagen: {e}")
    
    # Quelle 2: SCOWL Wörterliste (häufige Wörter)
    try:
        url = "https://raw.githubusercontent.com/jeremy-rifkin/Wordlist/master/common.txt"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read().decode('utf-8')
            words = [w.strip().lower() for w in content.split('\n') if w.strip()]
            all_words.update(words)
            print(f"✅ Quelle 2: {len(words)} Wörter")
    except Exception as e:
        print(f"⚠️ Quelle 2 fehlgeschlagen: {e}")
    
    # Quelle 3: Wordfreq (häufigste Wörter)
    try:
        url = "https://raw.githubusercontent.com/kilimchoi/wordlist/master/common-words.txt"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read().decode('utf-8')
            words = [w.strip().lower() for w in content.split('\n') if w.strip()]
            all_words.update(words)
            print(f"✅ Quelle 3: {len(words)} Wörter")
    except Exception as e:
        print(f"⚠️ Quelle 3 fehlgeschlagen: {e}")
    
    wordlist = sorted(list(all_words))
    print(f"📊 Insgesamt: {len(wordlist)} eindeutige Wörter geladen")
    return wordlist

def filter_quality_words(words):
    """Gründliche Filterung auf qualitativ hochwertige Wörter"""
    print("🔍 Filtere qualitativ hochwertige Wörter...")
    
    filtered = []
    
    # Schlechte Muster (Subjektive Liste von schwachen Wörtern)
    weak_suffixes = ('ingly', 'ingly', 'ationally', 'ization', 'fulness', 'lessness', 
                     'iveness', 'ability', 'ibility', 'ization', 'ational')
    weak_prefixes = ('un', 'non', 'anti', 'dis', 'mis', 'over', 'under', 'out', 'fore')
    
    for word in words:
        word = word.lower().strip()
        
        # Grundlegende Filter
        if len(word) < 4 or len(word) > 12:  # Ideal: 4-12 Buchstaben
            continue
        if not word.isalpha():
            continue
        if word.count('-') > 0 or word.count(' ') > 0:
            continue
        
        # Ausschluss schwacher Muster
        if word.endswith(weak_suffixes):
            continue
        if word.startswith(weak_prefixes) and len(word) > 8:
            continue
        
        # Keine Wörter mit 3+ gleichen Buchstaben hintereinander
        if re.search(r'(.)\1\1', word):
            continue
        
        # Mindestens eine Vokal
        if not any(c in 'aeiou' for c in word):
            continue
        
        # Keine extrem seltenen Konsonanten-Kombinationen
        rare_combos = ['xx', 'qq', 'zz', 'jj', 'kk']
        if any(combo in word for combo in rare_combos):
            continue
        
        # Ausschluss von Abkürzungen und Codes
        if word in ('info', 'admin', 'test', 'demo', 'www', 'api', 'app', 'dev'):
            continue
        
        filtered.append(word)
    
    print(f"✅ Nach Qualitätsfilterung: {len(filtered)} Wörter")
    return filtered

def check_dns_resolution(domain):
    """Zusätzlicher DNS-Check für Zuverlässigkeit"""
    try:
        socket.gethostbyname(domain)
        return True  # Domain hat DNS-Eintrag
    except socket.gaierror:
        return False  # Kein DNS-Eintrag
    except Exception:
        return None  # Unklar

def check_domain_comprehensive(domain, tld):
    """Gründliche Domain-Prüfung mit whois + DNS"""
    full_domain = f"{domain}.{tld}"
    result = {
        'domain': full_domain,
        'word': domain,
        'tld': tld,
        'available': False,
        'price': None,
        'checks': {}
    }
    
    # Whois-Check
    try:
        whois_result = subprocess.run(
            ['whois', full_domain],
            capture_output=True,
            text=True,
            timeout=8
        )
        whois_text = whois_result.stdout.lower()
        stderr_text = whois_result.stderr.lower()
        
        # .de Domains (DENIC)
        if tld == 'de':
            if 'status: free' in whois_text or 'not found' in whois_text:
                result['available'] = True
                result['price'] = 11.98
                result['checks']['whois'] = 'free'
            elif 'status: connect' in whois_text:
                result['available'] = False
                result['checks']['whois'] = 'taken'
            elif 'pendingdelete' in whois_text:
                result['checks']['whois'] = 'expiring_soon'
                result['expiring'] = True
            else:
                result['checks']['whois'] = 'unclear'
        
        # .com Domains
        elif tld == 'com':
            if 'no match' in whois_text or 'not found' in whois_text:
                result['available'] = True
                result['price'] = 12.00
                result['checks']['whois'] = 'free'
            elif any(x in whois_text for x in ['registrar:', 'name server:', 'creation date:']):
                result['available'] = False
                result['checks']['whois'] = 'taken'
            else:
                result['checks']['whois'] = 'unclear'
        
        # .ai Domains
        elif tld == 'ai':
            if 'not registered' in whois_text or 'no match' in whois_text:
                result['available'] = True
                result['price'] = 100.00  # Standard .ai Preis
                result['checks']['whois'] = 'free'
            elif any(x in whois_text for x in ['registrar:', 'nameserver:']):
                result['available'] = False
                result['checks']['whois'] = 'taken'
            else:
                result['checks']['whois'] = 'unclear'
        
    except subprocess.TimeoutExpired:
        result['checks']['whois'] = 'timeout'
    except Exception as e:
        result['checks']['whois'] = f'error: {str(e)[:50]}'
    
    # Zusätzlicher DNS-Check für Verfügbarkeitsbestätigung
    if result.get('available'):
        has_dns = check_dns_resolution(full_domain)
        result['checks']['dns'] = 'active' if has_dns else 'no_dns'
        if has_dns:
            # Wenn DNS aktiv ist, aber whois "free" sagt -> widersprüchlich
            result['available'] = False
            result['checks']['conflict'] = 'dns_active_but_whois_free'
    
    return result

def score_word_advanced(word, tld):
    """Erweitertes Scoring-System"""
    score = 0
    
    # Längen-Bewertung
    length = len(word)
    if 5 <= length <= 7:
        score += 40  # Ideal
    elif 4 <= length <= 8:
        score += 30
    elif 9 <= length <= 10:
        score += 15
    
    # Vokal-Verhältnis (für Aussprache)
    vowels = sum(1 for c in word if c in 'aeiou')
    vowel_ratio = vowels / length
    if 0.35 <= vowel_ratio <= 0.55:
        score += 20  # Perfektes Verhältnis
    elif 0.3 <= vowel_ratio <= 0.6:
        score += 10
    
    # Konsonant-Cluster (Lesbarkeit)
    consonant_clusters = len(re.findall(r'[bcdfghjklmnpqrstvwxz]{3,}', word))
    if consonant_clusters == 0:
        score += 15
    elif consonant_clusters == 1:
        score += 5
    else:
        score -= 10  # Zu schwer auszusprechen
    
    # Häufige Anfangsbuchstaben (Markenwert)
    valuable_starts = 'bcdfghjklmnpqrstvwxz'
    if word[0] in valuable_starts:
        score += 10
    
    # Häufige Endungen (kommerzieller Wert)
    commercial_ends = ('er', 'ly', 'al', 'ic', 'on', 'it', 'ar', 'or', 'en')
    if word.endswith(commercial_ends):
        score += 8
    
    # Vermeide doppelte Buchstaben
    if not re.search(r'(.)\1', word):
        score += 10
    
    # TLD-Bonus
    if tld == 'com':
        score += 15  # .com ist meist wertvoller
    elif tld == 'de':
        score += 10
    elif tld == 'ai':
        score += 5   # .ai ist spezialisiert (KI)
    
    # Einzigartige Buchstaben (Memorabilität)
    unique_chars = len(set(word))
    if unique_chars >= length * 0.7:  # Gut gemischt
        score += 10
    
    return max(0, score)  # Keine negativen Scores

def check_batch_with_delay(batch):
    """Batch-Prüfung mit Verzögerung für Stabilität"""
    results = []
    for domain, tld in batch:
        result = check_domain_comprehensive(domain, tld)
        result['score'] = score_word_advanced(domain, tld)
        results.append(result)
        time.sleep(DELAY_BETWEEN_CHECKS)
    return results

def main():
    print("=" * 60)
    print("🚀 GRÜNDLICHER Dictionary Domain Scanner")
    print("=" * 60)
    print(f"⏱️  Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Preislimits: .de/.com ≤ {MAX_PRICE_DE}€, .ai ≤ {MAX_PRICE_AI}€")
    print(f"📊 Max Wörter: {MAX_WORDS}")
    print("=" * 60)
    
    # Wörterbücher laden
    words = load_multiple_wordlists()
    if not words:
        print("❌ Kein Wörterbuch geladen - Abbruch")
        return
    
    # Qualitätsfilterung
    filtered_words = filter_quality_words(words)
    
    # Begrenze auf MAX_WORDS, aber sortiere nach Länge (kürzere zuerst = besser)
    filtered_words.sort(key=lambda w: (len(w), w))
    check_words = filtered_words[:MAX_WORDS]
    
    print(f"🔍 Werde {len(check_words)} Wörter prüfen")
    print("-" * 60)
    
    # Erstelle Domain-Liste
    domain_checks = []
    for word in check_words:
        domain_checks.append((word, 'de'))
        domain_checks.append((word, 'com'))
        domain_checks.append((word, 'ai'))
    
    total_checks = len(domain_checks)
    print(f"🌐 {total_checks} Domain-Checks geplant")
    print(f"⏳ Geschätzte Dauer: {(total_checks * DELAY_BETWEEN_CHECKS) / 60:.0f} Minuten")
    print("=" * 60)
    
    # Parallele Prüfung mit kleineren Batches
    available_domains = []
    checked = 0
    errors = 0
    
    batches = [domain_checks[i:i+BATCH_SIZE] for i in range(0, len(domain_checks), BATCH_SIZE)]
    total_batches = len(batches)
    
    print(f"📦 {total_batches} Batches zu verarbeiten\n")
    
    with ThreadPoolExecutor(max_workers=10) as executor:  # Weniger Worker = stabiler
        futures = {executor.submit(check_batch_with_delay, batch): i for i, batch in enumerate(batches)}
        
        for future in as_completed(futures):
            batch_num = futures[future]
            try:
                results = future.result()
                for r in results:
                    checked += 1
                    
                    # Preis-Filter
                    if r.get('available') and r.get('price'):
                        tld = r['tld']
                        price = r['price']
                        max_price = MAX_PRICE_DE if tld == 'de' else (MAX_PRICE_COM if tld == 'com' else MAX_PRICE_AI)
                        
                        if price <= max_price:
                            available_domains.append(r)
                            print(f"✅ {r['domain']:25} | Score: {r['score']:3} | {price:.2f}€")
                
                # Fortschritt alle 10 Batches
                if (batch_num + 1) % 10 == 0 or batch_num == total_batches - 1:
                    progress = (batch_num + 1) / total_batches * 100
                    print(f"\n⏳ Fortschritt: {progress:.1f}% | {checked}/{total_checks} geprüft | {len(available_domains)} gefunden\n")
                    
            except Exception as e:
                errors += 1
                if errors % 10 == 0:
                    print(f"⚠️ Fehler in Batch {batch_num}: {str(e)[:50]}")
    
    # Sortiere nach Score
    available_domains.sort(key=lambda x: x['score'], reverse=True)
    
    print("\n" + "=" * 60)
    print(f"🎉 FERTIG! {len(available_domains)} verfügbare Domains gefunden")
    print(f"⏱️  Ende: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Speichere Ergebnisse
    output_dir = Path('/root/.openclaw/workspace/projects/domain-flipper/data')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # JSON mit allen Details
    json_file = output_dir / f'dictionary_scan_thorough_{timestamp}.json'
    with open(json_file, 'w') as f:
        json.dump(available_domains, f, indent=2, default=str)
    print(f"💾 JSON gespeichert: {json_file}")
    
    # Top 30 für Bildschirmausgabe
    print("\n" + "🏆" * 30)
    print("TOP 30 VERFÜGBARE DOMAINS:")
    print("🏆" * 30)
    print(f"{'Rank':<5} {'Domain':<25} {'Score':<6} {'Preis':<8}")
    print("-" * 60)
    for i, d in enumerate(available_domains[:30], 1):
        print(f"{i:<5} {d['domain']:<25} {d['score']:<6} {d.get('price', 'N/A'):<8}€")
    
    # CSV für PDF-Generierung (Top 1000)
    csv_file = output_dir / f'dictionary_scan_thorough_{timestamp}.csv'
    with open(csv_file, 'w') as f:
        f.write("Rank,Domain,Word,TLD,Score,Price,EUR\n")
        for i, d in enumerate(available_domains[:1000], 1):
            f.write(f"{i},{d['domain']},{d['word']},{d['tld']},{d['score']},{d.get('price', 'N/A')},EUR\n")
    
    print(f"\n📄 CSV für PDF (Top 1000): {csv_file}")
    
    # Zusammenfassung nach TLD
    print("\n📊 Zusammenfassung nach TLD:")
    for tld in ['com', 'de', 'ai']:
        count = len([d for d in available_domains if d['tld'] == tld])
        print(f"   .{tld}: {count} Domains")
    
    return available_domains

if __name__ == '__main__':
    main()
