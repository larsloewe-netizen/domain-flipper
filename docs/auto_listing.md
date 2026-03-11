# Auto-Listing & Verkaufs-Automatisierung

Automatisches Listing auf Verkaufsplattformen mit Preis-Optimierung und Outreach-Automatisierung.

## ⚠️ WICHTIG: Sandbox-Modus

**Alle APIs laufen standardmäßig im Sandbox/Test-Modus!**

Für den Produktivbetrieb müssen echte API-Keys hinterlegt und explizit mit `--production` aktiviert werden.

## Features

### 1. Marketplace-Integrationen

| Plattform | Status | Sandbox | API-Doku |
|-----------|--------|---------|----------|
| **Sedo** | ✅ Implementiert | ✅ | https://sedo.com/us/sedo-api/ |
| **Afternic** | ✅ Implementiert | ✅ | https://developer.godaddy.com/ |
| **Dan.com** | ✅ Implementiert | ✅ | https://docs.dan.com/ |

### 2. Preis-Optimierung

- **Startpreis-Berechnung** basierend auf:
  - Bewertungspunktzahl (0-100)
  - TLD-Premium (.com, .ai, .io, etc.)
  - Domain-Länge (kürzer = wertvoller)
  - Keywords (AI, Crypto, Cloud, etc.)

- **Dynamische Preis-Anpassung**:
  - Automatische Reduktion alle 7 Tage um 5%
  - Mindestpreis-Schutz
  - Runden auf schöne Zahlen

### 3. Outreach-Automatisierung

- **WHOIS-Lookup** für ähnliche Domains
- **Template-basierte E-Mails**:
  - Initial Offer
  - Follow-up mit Preisreduktion
  - Final Call
- **Tracking**: Gesendet, Geöffnet, Antworten

## Installation

```bash
# Abhängigkeiten prüfen
pip install requests

# Datenbank initialisieren
python src/auto_listing.py
```

## Konfiguration

Erstelle `.env` Datei im Projekt-Root:

```bash
# Sedo API
SEDO_API_KEY=your_sedo_api_key
SEDO_USERNAME=your_sedo_username
SEDO_PASSWORD=your_sedo_password

# Afternic/GoDaddy API
AFTERNIC_API_KEY=your_afternic_key
AFTERNIC_API_SECRET=your_afternic_secret
# ODER
GODADDY_API_KEY=your_godaddy_key
GODADDY_API_SECRET=your_godaddy_secret

# Dan.com API
DAN_API_KEY=your_dan_api_key

# E-Mail (Gmail)
GMAIL_USER=hansdieterbot@gmail.com
GMAIL_APP_PASSWORD=your_app_password
```

## Verwendung

### Domain auf allen Plattformen listen

```bash
# Sandbox-Modus (Standard)
python src/auto_listing.py list exampledomain.com --score 75

# Mit Beschreibung
python src/auto_listing.py list cloudai.com --score 85 --description "Premium AI Domain"
```

### Preis-Optimierung durchführen

```bash
# Automatische Preisreduktion für alle Listings
python src/auto_listing.py optimize
```

### Outreach-Kampagne

```bash
# Neue Kampagne erstellen
python src/auto_listing.py outreach cloudai.com --create

# Kampagne ausführen (max 10 E-Mails)
python src/auto_listing.py outreach cloudai.com --campaign-id 1 --max-emails 10
```

### Status anzeigen

```bash
# Alle Listings
python src/auto_listing.py status

# Nur eine Domain
python src/auto_listing.py status --domain cloudai.com
```

### Listing entfernen

```bash
# Von allen Plattformen
python src/auto_listing.py remove exampledomain.com

# Nur eine Plattform
python src/auto_listing.py remove exampledomain.com --platform sedo
```

## Python API

```python
from src.auto_listing import AutoListingManager, ListingConfig

# Manager initialisieren (Sandbox)
manager = AutoListingManager(sandbox=True)

# Domain listen
results = manager.list_domain_on_all_platforms(
    domain='cloudai.com',
    valuation_score=85,
    description='Premium AI Domain'
)

# Ergebnisse auswerten
for platform, result in results.items():
    print(f"{platform}: {result['listing_id']}")

# Outreach starten
campaign_id = manager.create_outreach_campaign('cloudai.com')
manager.outreach.run_campaign(campaign_id, max_emails=10)

# Preis-Optimierung
manager.run_price_optimization()
```

## Preis-Berechnung

Der Startpreis wird berechnet mit:

```
Preis = $100 × Score-Multiplikator × TLD-Multiplikator × Längen-Faktor × Keyword-Multiplikator
```

### Multiplikatoren

**TLD-Premium:**
- .com: 2.0x
- .ai: 1.8x
- .io: 1.6x
- .co: 1.4x
- .de: 1.3x
- ...

**Längen-Faktor:**
- ≤4 Zeichen: 2.0x
- ≤6 Zeichen: 1.5x
- ≤10 Zeichen: 1.2x
- >15 Zeichen: 0.8x

**Keyword-Multiplikator:**
- AI: 2.0x
- Crypto: 1.8x
- Cloud: 1.6x
- Pay: 1.5x
- ...

## Datenbank-Schema

### listings
```sql
CREATE TABLE listings (
    id INTEGER PRIMARY KEY,
    domain_name TEXT NOT NULL,
    platform TEXT NOT NULL,
    listing_id TEXT,
    status TEXT DEFAULT 'pending',
    start_price REAL,
    current_price REAL,
    min_price REAL,
    buy_now_price REAL,
    currency TEXT DEFAULT 'USD',
    listed_at TEXT,
    last_price_update TEXT,
    platform_listing_url TEXT,
    is_sandbox INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### price_history
```sql
CREATE TABLE price_history (
    id INTEGER PRIMARY KEY,
    domain_name TEXT NOT NULL,
    platform TEXT NOT NULL,
    old_price REAL,
    new_price REAL,
    change_reason TEXT,
    created_at TEXT NOT NULL
);
```

### outreach_campaigns
```sql
CREATE TABLE outreach_campaigns (
    id INTEGER PRIMARY KEY,
    domain_name TEXT NOT NULL,
    template_id TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    emails_sent INTEGER DEFAULT 0,
    emails_opened INTEGER DEFAULT 0,
    replies_received INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_sent_at TEXT
);
```

## Cron-Jobs

Empfohlene Cron-Jobs für Automatisierung:

```bash
# Täglich: Preis-Optimierung durchführen
0 2 * * * cd /root/.openclaw/workspace/projects/domain-flipper && python3 src/auto_listing.py optimize

# Wöchentlich: Outreach-Kampagnen ausführen
0 9 * * 1 cd /root/.openclaw/workspace/projects/domain-flipper && python3 -c "
from src.auto_listing import OutreachAutomator, sqlite3, DB_PATH
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute('SELECT id FROM outreach_campaigns WHERE status = \"active\"')
for row in cursor.fetchall():
    outreach = OutreachAutomator()
    outreach.run_campaign(row[0], max_emails=5)
conn.close()
"
```

## Tests

```bash
# Modul importieren testen
python3 -c "from src.auto_listing import AutoListingManager; print('OK')"

# Sandbox-Listing testen
python3 src/auto_listing.py list testdomain.com --score 50

# Status anzeigen
python3 src/auto_listing.py status
```

## Roadmap

- [ ] Echte API-Integrationen (nach Approval)
- [ ] E-Mail Tracking mit Pixel
- [ ] Automatische Antwort-Analyse
- [ ] Verkaufs-Tracking
- [ ] Analytics Dashboard
- [ ] A/B Testing für Templates
