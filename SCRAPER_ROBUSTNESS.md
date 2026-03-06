# Domain Scraper - Robustheit-Update

## Neue Features

### 1. Retry-Logik mit Exponential Backoff
- **3 Versuche** pro Request (konfigurierbar)
- **Delays**: 1s, 2s, 4s zwischen Versuchen
- **Bei 429/503**: 3x bzw. 2x längere Wartezeiten
- **Jitter**: ±20% zufällige Variation

### 2. User-Agent Rotation
- **15 verschiedene** realistische User-Agents
- Zufällige Auswahl pro Request
- Chrome, Firefox, Safari, Edge auf Windows/Mac/Linux

### 3. Proxy-Support
```bash
# Mit eigenen Proxies
python src/scraper.py --use-proxies --proxy-list "proxy1:8080,proxy2:8080"

# Mit kostenlosen Proxies (nicht empfohlen)
python src/scraper.py --use-free-proxies

# Proxies testen
python src/scraper.py --proxy-test
```

### 4. Smartes Rate-Limiting
- **Variabler Delay**: 1-3 Sekunden (konfigurierbar)
- **Pause bei Fehlern**: Erhöhte Pause nach 3+ Fehlern
- **Error-Threshold**: 60s Pause bei >5 Fehlern

### 5. Fehlerbehandlung
- **Timeout**: 10s default (konfigurierbar)
- **Connection Error Handling**: Mit Retry
- **Logging**: Alle Fehler werden geloggt

### 6. Test-Modus
```bash
# Schneller Test mit wenigen Domains
python src/scraper.py --test

# Verbindung testen
python src/scraper.py --connection-test

# Proxy-Test
python src/scraper.py --proxy-test
```

## CLI-Optionen

```
--test                    Test-Modus (nur 5 Domains pro Quelle)
--proxy-test              Proxies testen
--connection-test         Verbindung testen
--use-proxies             Proxy-Support aktivieren
--use-free-proxies        Kostenlose Proxies verwenden (nicht empfohlen)
--proxy-list PROXY_LIST   Komma-getrennte Proxy-Liste
--timeout TIMEOUT         Request Timeout (default: 10)
--min-delay MIN_DELAY     Minimale Pause (default: 1.0)
--max-delay MAX_DELAY     Maximale Pause (default: 3.0)
```

## Python API

```python
from src.scraper import DomainScraper

# Normaler Modus
scraper = DomainScraper()
scraper.run_all_scrapers()

# Mit Proxies
scraper = DomainScraper(
    use_proxies=True,
    proxy_list=["http://proxy1:8080", "http://proxy2:8080"]
)

# Test-Modus
scraper = DomainScraper(test_mode=True)
scraper.run_all_scrapers()

# Timeout und Delays anpassen
scraper = DomainScraper(
    timeout=20,
    min_delay=2.0,
    max_delay=5.0
)
```

## Tests ausführen

```bash
python tests/test_scraper_robustness.py
```

Testet:
- User-Agent Rotation
- Retry-Logik mit Exponential Backoff
- Rate-Limiting
- Proxy-Verwaltung
- Fehlerbehandlung
