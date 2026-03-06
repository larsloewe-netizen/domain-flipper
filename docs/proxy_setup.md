# Proxy Setup Dokumentation

## Übersicht

Das Domain-Flipping Projekt verwendet nun ein automatisches Proxy-Management-System mit Free Proxies von verschiedenen Quellen.

## Komponenten

### 1. Proxy Manager (`src/proxy_manager.py`)

Die zentrale Proxy-Verwaltungsklasse:

- **Free Proxy Sources**: Holt Proxies von `proxy-list.download` (HTTP, HTTPS, SOCKS4, SOCKS5)
- **Proxy-Validierung**: Testet jede Proxy gegen `httpbin.org/ip`
- **Auto-Rotation**: Rotiert Proxies alle X Requests (default: 10)
- **Persistenz**: Speichert funktionierende Proxies in `data/working_proxies.json`
- **Auto-Refresh**: Holt automatisch neue Proxies wenn < 3 verfügbar

**Verwendung:**
```python
from src.proxy_manager import ProxyManager, get_proxy_manager

# Neue Instanz
pm = ProxyManager(
    rotation_limit=10,      # Rotiere nach X Requests
    test_before_use=True,   # Teste vor Verwendung
    auto_fetch=True,        # Hole neue wenn zu wenige
    min_proxies=3          # Minimale Anzahl
)

# Singleton (empfohlen)
pm = get_proxy_manager()

# Hole Proxy
proxy = pm.get_proxy()  # {'http': 'http://ip:port', 'https': 'http://ip:port'}

# Stats
stats = pm.get_stats()
```

### 2. Erweiterter Scraper (`src/scraper.py`)

Neue Features:

```bash
# Free Proxies verwenden
python src/scraper.py --use-free-proxies

# Proxies aktualisieren
python src/scraper.py --refresh-proxies

# Alle Proxies testen
python src/scraper.py --proxy-test

# Proxy-Rotation konfigurieren
python src/scraper.py --use-free-proxies --proxy-rotation 5
```

**Programmatische Verwendung:**
```python
from src.scraper import DomainScraper

scraper = DomainScraper(
    use_free_proxies=True,
    proxy_rotation_limit=10
)

# Proxies aktualisieren
scraper.refresh_proxies()

# Scrape durchführen
scraper.run_all_scrapers()
```

### 3. Proxy Check Cron (`cron/check_proxys.py`)

Wird alle 2 Stunden ausgeführt.

**Funktionen:**
- Testet alle gespeicherten Proxies
- Entfernt tote Proxies
- Holt neue wenn < 3 verfügbar
- Loggt Ergebnis nach `logs/proxy_check.log`
- Speichert JSON-Resultat nach `data/proxy_check_result.json`

**Manuelle Ausführung:**
```bash
python cron/check_proxys.py
```

**Exit-Codes:**
- `0`: OK, genügend Proxies verfügbar
- `1`: Warnung, weniger als 3 Proxies
- `2`: Fehler bei Ausführung

### 4. Full Scrape Cron (`cron/full_scrape.py`)

Wird alle 6 Stunden ausgeführt.

**Funktionen:**
- Führt vollständigen Scrape mit allen Quellen durch
- Verwendet Free Proxies automatisch
- Häufigere Proxy-Rotation (alle 5 Requests)
- Längere Timeouts und Delays für Stabilität
- Loggt nach `logs/full_scrape.log`
- Speichert JSON-Resultat nach `data/full_scrape_result.json`

**Manuelle Ausführung:**
```bash
python cron/full_scrape.py
```

## Cron-Jobs einrichten

### Variante 1: crontab (empfohlen)

```bash
# Öffne crontab
sudo crontab -e

# Füge folgende Zeilen hinzu:
# Proxy-Check alle 2 Stunden
0 */2 * * * cd /root/.openclaw/workspace/projects/domain-flipper && /root/.openclaw/workspace/projects/domain-flipper/venv/bin/python /root/.openclaw/workspace/projects/domain-flipper/cron/check_proxys.py >> /root/.openclaw/workspace/projects/domain-flipper/logs/cron.log 2>&1

# Full Scrape alle 6 Stunden
0 */6 * * * cd /root/.openclaw/workspace/projects/domain-flipper && /root/.openclaw/workspace/projects/domain-flipper/venv/bin/python /root/.openclaw/workspace/projects/domain-flipper/cron/full_scrape.py >> /root/.openclaw/workspace/projects/domain-flipper/logs/cron.log 2>&1
```

### Variante 2: Systemd Timer (alternativ)

Erstelle `/etc/systemd/system/domainflipper-proxy-check.service`:
```ini
[Unit]
Description=Domain Flipper Proxy Check

[Service]
Type=oneshot
WorkingDirectory=/root/.openclaw/workspace/projects/domain-flipper
ExecStart=/root/.openclaw/workspace/projects/domain-flipper/venv/bin/python /root/.openclaw/workspace/projects/domain-flipper/cron/check_proxys.py
```

Erstelle `/etc/systemd/system/domainflipper-proxy-check.timer`:
```ini
[Unit]
Description=Run Proxy Check every 2 hours

[Timer]
OnCalendar=*:0/2
Persistent=true

[Install]
WantedBy=timers.target
```

Erstelle `/etc/systemd/system/domainflipper-full-scrape.service`:
```ini
[Unit]
Description=Domain Flipper Full Scrape

[Service]
Type=oneshot
WorkingDirectory=/root/.openclaw/workspace/projects/domain-flipper
ExecStart=/root/.openclaw/workspace/projects/domain-flipper/venv/bin/python /root/.openclaw/workspace/projects/domain-flipper/cron/full_scrape.py
```

Erstelle `/etc/systemd/system/domainflipper-full-scrape.timer`:
```ini
[Unit]
Description=Run Full Scrape every 6 hours

[Timer]
OnCalendar=*:0/6
Persistent=true

[Install]
WantedBy=timers.target
```

**Aktivieren:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable domainflipper-proxy-check.timer
sudo systemctl enable domainflipper-full-scrape.timer
sudo systemctl start domainflipper-proxy-check.timer
sudo systemctl start domainflipper-full-scrape.timer
```

## Dateistruktur

```
projects/domain-flipper/
├── src/
│   ├── scraper.py           # Erweiterter Scraper mit Proxy-Support
│   └── proxy_manager.py     # Neue Proxy Manager Klasse
├── cron/
│   ├── check_proxys.py      # Proxy-Check alle 2h
│   └── full_scrape.py       # Full Scrape alle 6h
├── data/
│   ├── working_proxies.json # Persistente Proxy-Liste
│   ├── proxy_check_result.json
│   └── full_scrape_result.json
├── logs/
│   ├── proxy_check.log      # Proxy-Check Logs
│   ├── full_scrape.log      # Full Scrape Logs
│   └── cron.log            # Cron Ausgaben
└── docs/
    └── proxy_setup.md       # Diese Dokumentation
```

## Monitoring

### Proxy Status prüfen

```bash
# Zeige gespeicherte Proxies
cat data/working_proxies.json | jq

# Zeige letztes Check-Resultat
cat data/proxy_check_result.json | jq

# Zeige Logs
tail -f logs/proxy_check.log
tail -f logs/full_scrape.log
```

### Manuelle Tests

```bash
# Proxies testen
python src/scraper.py --proxy-test

# Verbindung testen
python src/scraper.py --connection-test

# Test-Scrape mit Proxies
python src/scraper.py --use-free-proxies --test
```

## Troubleshooting

### Keine Proxies verfügbar

```bash
# Proxies manuell aktualisieren
python src/scraper.py --refresh-proxies

# Oder direkt im ProxyManager
python -c "from src.proxy_manager import ProxyManager; pm = ProxyManager(); pm.fetch_and_test_proxies()"
```

### Proxy-Check schlägt fehl

1. Prüfe Internet-Verbindung
2. Prüfe Logs: `tail logs/proxy_check.log`
3. Führe manuell aus: `python cron/check_proxys.py`

### Scraper zu langsam

- Erhöhe `max_delay` (weniger aggressives Rate-Limiting)
- Verringere `proxy_rotation_limit` (häufigere Rotation)
- Prüfe ob genügend Proxies verfügbar

### Zu viele Proxy-Fehler

- Free Proxies sind instabil, das ist normal
- Der ProxyManager versucht automatisch neue zu holen
- Erhöhe `min_proxies` für mehr Redundanz

## Konfiguration

### Umgebungsvariablen

```bash
# Proxy Test URL (default: https://httpbin.org/ip)
export PROXY_TEST_URL="https://ipinfo.io/ip"

# Minimale Proxy-Anzahl
export MIN_PROXIES=5

# Timeout für Proxy-Tests
export PROXY_TEST_TIMEOUT=15
```

### Code-Anpassungen

In `src/proxy_manager.py`:
```python
# Eigene Proxy Sources hinzufügen
FREE_PROXY_SOURCES = {
    'meine_quelle': 'https://example.com/proxy-list',
    # ...
}
```

## Wichtige Hinweise

1. **Free Proxies sind instabil**: Funktionieren oft nur kurz, deshalb der Auto-Refresh
2. **Rate Limiting**: Free Proxies brauchen längere Pausen zwischen Requests
3. **Privacy**: Free Proxies können Traffic loggen - keine sensiblen Daten senden
4. **Legal**: Nur für legale Zwecke verwenden

## Roadmap

- [ ] Private Proxy Provider Integration
- [ ] Proxy-Performance-Tracking
- [ ] Geolocation-basierte Proxy-Auswahl
- [ ] Proxy-Pool mit unterschiedlichen Ländern
