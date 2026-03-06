# Domain Flipper - README

## Überblick
Domain Scraper für Domain-Flipping Projekte. Sammelt expired Domains von verschiedenen Quellen.

## Installation

```bash
# Abhängigkeiten installieren
pip3 install -r requirements.txt

# Oder im Projektverzeichnis:
cd /root/.openclaw/workspace/projects/domain-flipper
pip3 install -r requirements.txt
```

## Verwendung

### Einmaliges Scraping
```bash
python3 src/scraper.py
```

### Automatisches Scraping (alle 6 Stunden)

Cronjob einrichten:
```bash
crontab -e
```

Folgende Zeile hinzufügen:
```
0 */6 * * * /root/.openclaw/workspace/projects/domain-flipper/cron/run_scraper.sh >> /root/.openclaw/workspace/projects/domain-flipper/data/scraper.log 2>&1
```

Oder manuell ausführen:
```bash
./cron/run_scraper.sh
```

## Datenbank

SQLite Datenbank unter:
```
/root/.openclaw/workspace/projects/domain-flipper/data/expired_domains.db
```

Tabellen:
- `domains`: Gesammelte Domain-Daten
- `scrape_log`: Logging der Scraping-Vorgänge

## Datenfelder

Jede Domain enthält:
- `domain_name`: Domain-Name
- `tld`: Top-Level-Domain (.com, .io, etc.)
- `age_years`: Alter in Jahren
- `backlinks`: Anzahl Backlinks
- `estimated_traffic`: Geschätzter Traffic
- `price`: Aktueller Preis
- `auction_status`: Status (active, deleted, listed, auction)
- `domain_authority`: Domain Authority (wenn verfügbar)
- `page_authority`: Page Authority (wenn verfügbar)
- `source`: Datenquelle
- `auction_url`: Link zur Auktion

## Datenquellen

1. **ExpiredDomains.net** - Deleted & Expired Domains (kein API-Key nötig)
2. **Dynadot** - Expired Domain Auctions
3. **Namecheap** - Domain Marketplace
4. **GoDaddy** - Domain Auctions (optional, erfordert teilweise Login)

## Logs

Scraper-Log:
```
/root/.openclaw/workspace/projects/domain-flipper/data/scraper.log
```

## Anpassungen

### TLD-Filter
Bearbeite den Scraper um bestimmte TLDs zu priorisieren:
```python
PRIORITY_TLDS = ['.com', '.io', '.ai', '.co', '.app']
```

### Preis-Filter
Füge einen Preis-Filter hinzu um nur Domains unter einem bestimmten Preis zu sammeln.

## Fehlerbehebung

### ImportError
```bash
pip3 install --upgrade -r requirements.txt
```

### Rate Limiting
Der Scraper hat eingebautes Rate Limiting (2-5 Sekunden Pause zwischen Requests).
Bei Problemen erhöhe die Wartezeiten in `_get_headers()`.

### Datenbank-Lock
Wenn die Datenbank gesperrt ist, warte bis andere Prozesse fertig sind.

## Roadmap / TODO

- [ ] GoDaddy API-Integration (mit API-Key)
- [ ] Dynadot API-Integration
- [ ] Moz API für DA/PA Werte
- [ ] Ahrefs/SEMrush Integration für Backlinks
- [ ] Filter nach Domain-Alter
- [ ] Filter nach Preis-Bereich
- [ ] Email-Benachrichtigung bei interessanten Domains
