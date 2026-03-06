# Domain Checker

Domain-Überprüfungstool für das Domain-Flipping-Projekt.

## Funktionen

### MVP (Implementiert)
- ✅ **WHOIS-Lookup** - Prüft Domain-Verfügbarkeit und Registrierungsdetails
- ✅ **Archive.org-Integration** - Ermittelt historische Nutzung der Domain
- ✅ **SQLite-Datenbank** - Speichert alle Ergebnisse persistent
- ✅ **Batch-Verarbeitung** - Prüft mehrere Domains mit Rate-Limiting

### Premium-Erweiterungen (Optional)
- 🔲 **Dynadot API** - Auction-Status
- 🔲 **Namecheap API** - Auction-Status
- 🔲 **NameBio API** - Historische Verkaufsdaten
- 🔲 **Majestic/Ahrefs** - Backlink-Daten
- 🔲 **Spam-Score** - Überprüfung auf Spam-Listen

## Installation

```bash
pip install python-whois requests
```

## Nutzung

### Kommandozeile

```bash
# Einzelne Domain prüfen
python src/domain_checker.py example.com

# Mehrere Domains prüfen
python src/domain_checker.py domain1.com domain2.org domain3.net
```

### Als Modul

```python
from src.domain_checker import DomainChecker, quick_check, check_and_save

# Schneller Check (nur WHOIS + Archive.org)
result = quick_check('example.com')
print(f"Verfügbar: {result['is_available']}")
print(f"History: {result['archive_count']} Snapshots")

# Mit Datenbank-Speicherung
result = check_and_save('example.com')

# Mit voller Kontrolle
checker = DomainChecker()
result = checker.check_domain('example.com', use_premium=False)
checker.save_result(result)

# Mehrere Domains
results = checker.check_domains_batch(
    ['domain1.com', 'domain2.org', 'domain3.net'],
    delay=1.0  # Sekunden zwischen Checks
)
```

### Premium-APIs aktivieren

```python
config = {
    'dynadot_api_key': 'your_key_here',
    'namebio_api_key': 'your_key_here'
}

checker = DomainChecker(config=config)
result = checker.check_domain('example.com', use_premium=True)
```

## Datenbank-Schema

Die SQLite-Datenbank enthält folgende Tabellen:

### domain_checks
| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primärschlüssel |
| domain | TEXT | Domain-Name |
| timestamp | TEXT | Check-Zeitpunkt |
| is_available | INTEGER | Verfügbar (1/0) |
| is_registered | INTEGER | Registriert (1/0) |
| expiry_date | TEXT | Ablaufdatum |
| creation_date | TEXT | Erstellungsdatum |
| registrar | TEXT | Registrar-Name |
| archive_count | INTEGER | Anzahl Archive.org-Snapshots |
| has_history | INTEGER | Hat History (1/0) |
| auction_status | TEXT | Auction-Status (Premium) |
| comparable_sales | TEXT | JSON mit Verkäufen (Premium) |
| backlink_count | INTEGER | Backlinks (Premium) |

## API-Konfiguration

API-Keys in `config/domain_checker.json` eintragen:

```json
{
  "apis": {
    "dynadot": {
      "enabled": true,
      "api_key": "YOUR_API_KEY"
    }
  }
}
```

## Hinweise

- **Rate Limiting**: WHOIS-Checks haben automatisches Rate-Limiting (1s Verzögerung)
- **Archive.org**: Kann bei sehr beliebten Domains langsam sein
- **Premium-APIs**: Erfordern gültige API-Keys und ggf. Bezahlung
