# Domain Sources Documentation

Dokumentation aller im Domain-Flipper Scraper unterstützten Datenquellen.

## Übersicht

| Quelle | Typ | TLDs | Authentifizierung | Rate Limit |
|--------|-----|------|-------------------|------------|
| ExpiredDomains.net | Web Scraping | 500+ | Nein | 1s/Request |
| Dynadot.com | Web Scraping | 500+ | Optional | 1s/Request |
| GoDaddy Auctions | Web Scraping/API | Alle gTLDs | API-Key | 1s/Request |
| Namecheap | Web Scraping | Alle gTLDs | Nein | 1s/Request |
| **DropCatch.com** | API/Web | .com, .net, .org, .io | API-Key empfohlen | 1s/Request |
| **NameJet.com** | CSV/API | .com, .net, .org, .io | Nein | 1s/Request |
| **SnapNames.com** | CSV/API | Alle gTLDs | Nein | 1s/Request |
| **Park.io** | JSON API | .io, .ai, .ly, .to, .me | Nein | 1s/Request |
| **Pool.com** | Web Scraping | Alle gTLDs | Nein | 1s/Request |

*Neue Quellen in v2.1 sind fett markiert*

---

## Neue Quellen (v2.1)

### 1. DropCatch.com

**Beschreibung:**
DropCatch ist einer der führenden Drop-Catching Services. Sie besitzen den Registrar NameBright und haben direkten Zugang zu Registry-Systemen, um expiring Domains Millisekunden nach dem Löschen zu registrieren.

**Funktionsweise:**
- Domains durchlaufen den vollen Domain-Lifecycle (Grace Period → Redemption → Pending Delete)
- DropCatch fängt Domains direkt beim Löschen ab
- Bei mehreren Backorders wird eine öffentliche Auktion gestartet
- Verarbeitet 60.000-85.000 dropping Domains täglich

**API Endpunkte:**
```
API Base: https://www.dropcatch.com/api/v1/
Endpoints:
  - GET /auctions          - Aktive Auktionen
  - GET /expiring          - Bald expiring Domains
  - GET /domain/{domain}   - Details zu einer Domain
```

**Authentifizierung:**
- API-Key über Umgebungsvariable: `DROPCATCH_API_KEY`
- Ohne API-Key: HTML Scraping als Fallback

**Rate Limiting:**
- 1 Request pro Sekunde (empfohlen)
- Bei 429: Exponential Backoff mit Jitter

**Datenfelder:**
| Feld | Beschreibung |
|------|--------------|
| domain | Domain-Name |
| status | Auktionsstatus (auction, pending) |
| currentBid | Aktuelles Gebot |
| dropDate | Löschdatum |
| domainAuthority | DA-Wert (falls verfügbar) |
| backlinks | Anzahl Backlinks |

**Beispiel-Response:**
```json
{
  "auctions": [
    {
      "domain": "example.com",
      "status": "auction",
      "currentBid": 85,
      "dropDate": "2026-03-15T00:00:00Z",
      "backorders": 3
    }
  ]
}
```

**Links:**
- Website: https://www.dropcatch.com
- API-Doku: https://www.dropcatch.com/hiw/dropcatch-api
- Auktionen: https://www.dropcatch.com/auctions

---

### 2. NameJet.com

**Beschreibung:**
NameJet ist ein Premium Domain-Auktionshaus mit exklusiven Partnerschaften zu großen Registrarn (Network Solutions, Register.com, eNom). Sie bieten Pre-Release Auktionen an, bei denen Domains vor dem tatsächlichen Löschen versteigert werden.

**Funktionsweise:**
1. **Pre-Release Auktionen:** Domains werden vor dem Löschen angeboten
2. **Kostenlose Backorders:** Unbegrenzte Backorders möglich
3. **Private Auktionen:** 3-tägige Auktion nur für Backorder-Inhaber
4. **Drop-Catch Backup:** Falls keine Auktion stattfindet, wird versucht zu catchen

**CSV Download:**
```
URL: https://www.namejet.com/download.action?format=csv
Format: CSV mit Header
Update: Täglich
```

**CSV-Spalten:**
| Spalte | Beschreibung |
|--------|--------------|
| Domain | Domain-Name |
| Status | auction, pending_delete, available_soon |
| Minimum Bid | Mindestgebot |
| Drop Date | Geschätztes Löschdatum |
| Backlinks | Anzahl Backlinks |

**Rate Limiting:**
- CSV: 1x pro Stunde herunterladen
- Website: 1 Request pro Sekunde

**Auktions-Status:**
| Status | Bedeutung |
|--------|-----------|
| In Auction | Aktive Auktion |
| Available Soon | Bald verfügbar (Backorder möglich) |
| Pending Delete | Wird gelöscht |
| Buy It Now | Sofortkauf verfügbar |

**Links:**
- Website: https://www.namejet.com
- CSV Download: https://www.namejet.com/download.action?format=csv
- FAQ: https://www.namejet.com/faqs.action

---

### 3. SnapNames.com

**Beschreibung:**
SnapNames (jetzt Teil der NameJet/Web.com Familie) bietet Backorder-Services für Pending Delete und Expiring Domains. Seit der Fusion teilen SnapNames und NameJet die gleiche Domain-Inventar-Plattform.

**Funktionsweise:**
- Backorders für Pending Delete Domains
- Pre-Release Domains von Partner-Registrarn
- 3-tägige Auktionen bei mehreren Backorders
- Nur Bezahlung bei erfolgreicher Akquirierung

**CSV Download:**
```
URL: https://www.snapnames.com/download.action?format=csv
Format: CSV
Update: Täglich
```

**Backorder Cut-off Zeiten:**
| Domain-Typ | Cut-off Zeit |
|------------|--------------|
| Registry Release | 10:45 AM PST am Löschtag |
| Priority Partner | 21:00 PM PST am Vorabend |

**Rate Limiting:**
- CSV: 1x pro Stunde
- Website: 1 Request pro Sekunde

**Links:**
- Website: https://www.snapnames.com
- FAQ: https://www.snapnames.com/faqs.action
- About: https://www.snapnames.com/about.action

---

### 4. Park.io

**Beschreibung:**
Park.io ist spezialisiert auf kurze, wertvolle ccTLDs (Country Code Top-Level Domains). Besonders beliebt bei Tech-Startups und Domain-Hackern.

**Unterstützte TLDs:**
| TLD | Land | Besonderheit |
|-----|------|--------------|
| .io | British Indian Ocean Territory | Beliebt bei Tech-Startups (I/O) |
| .ai | Anguilla | Beliebt für AI-Startups |
| .ly | Libya | Beliebt für Domain-Hacks |
| .to | Tonga | Kurze, prägnante Domains |
| .me | Montenegro | Persönliche Domains |
| .sh | Saint Helena | Shell/Unix-Themen |
| .ac | Ascension Island | Akademische Themen |

**JSON API:**
```
Base URL: https://park.io

Endpoints:
  GET /domains.json              - Alle dropping Domains
  GET /domains/index/{tld}.json  - Spezifische TLD
  GET /domains/index/all.json    - Alle TLDs
  GET /auctions.json             - Aktive Auktionen
  
Parameter:
  ?limit=N  - Maximale Anzahl Ergebnisse (z.B. ?limit=1000)
  ?page=N   - Seitennummer für Pagination
```

**Beispiel-Request:**
```bash
curl "https://park.io/domains/index/io.json?limit=100"
```

**Beispiel-Response:**
```json
{
  "page": 1,
  "current": 15,
  "count": 15,
  "prevPage": false,
  "nextPage": true,
  "pageCount": 5,
  "limit": 20,
  "success": true,
  "domains": [
    {
      "id": "439097",
      "name": "example.io",
      "date_available": "2026-03-15",
      "tld": "io"
    }
  ]
}
```

**Auktions-Modell:**
- Backorder: $99 (wenn nur eine Person)
- Auktion: 10-tägige öffentliche Auktion bei mehreren Backorders

**Rate Limiting:**
- Keine strikten Limits dokumentiert
- Empfohlen: 1 Request pro Sekunde
- Bei 429: 30 Sekunden warten

**Links:**
- Website: https://park.io
- API Blog: http://blog.park.io/articles/park-io-api
- .io Domains: https://park.io/domains/index/io.json

---

### 5. Pool.com

**Beschreibung:**
Pool.com ist einer der ältesten Drop-Catching Services (seit 2001). Sie spezialisieren sich auf das Abfangen von Domains direkt beim Löschen aus dem Registry-System.

**Funktionsweise:**
- Backorder-Service für Pending Delete Domains
- Unterstützung für viele TLDs
- Nur Bezahlung bei erfolgreichem Catch
- Konkurrenz zu DropCatch, NameJet, SnapNames

**Web Scraping:**
Da Pool.com keine öffentliche API anbietet, wird HTML Scraping verwendet:

**Ziel-URLs:**
```
https://www.pool.com/domainlisting.aspx
https://www.pool.com/dropping.aspx
```

**HTML-Struktur:**
```html
<table class="domainTable">
  <tr>
    <td><a href="/details.aspx?item=example.com">example.com</a></td>
    <td>2026-03-15</td>
    <td>3 Backorders</td>
  </tr>
</table>
```

**Rate Limiting:**
- 1 Request pro Sekunde
- Respektiere robots.txt

**Links:**
- Website: https://www.pool.com

---

## Bestehende Quellen (v2.0)

### ExpiredDomains.net
- **Typ:** Web Scraping
- **URL:** https://www.expireddomains.net
- **TLDs:** 500+
- **Features:** Umfangreiche Metriken (Backlinks, Domain Authority, etc.)

### Dynadot.com
- **Typ:** Web Scraping
- **URL:** https://www.dynadot.com/market/expired-domains
- **TLDs:** 500+
- **Features:** Expired Domain Marketplace

### GoDaddy Auctions
- **Typ:** Web Scraping/API
- **URL:** https://auctions.godaddy.com
- **TLDs:** Alle gTLDs
- **Features:** Größter Domain-Auktionsmarktplatz

### Namecheap Marketplace
- **Typ:** Web Scraping
- **URL:** https://www.namecheap.com/market/
- **TLDs:** Alle gTLDs
- **Features:** Marketplace für Premium-Domains

---

## Technische Implementierung

### Retry-Logik mit Exponential Backoff

Alle Scraper verwenden die `RetrySession` Klasse:

```python
retry_session = RetrySession(
    max_retries=3,
    base_delay=1.0,
    timeout=10,
    proxy_manager=proxy_manager,
    rate_limiter=rate_limiter
)
```

**Backoff-Formel:**
```
delay = base_delay * (2 ^ attempt) + jitter

jitter = delay * 0.2 * (random * 2 - 1)
```

**Status-Code-Behandlung:**
| Code | Aktion |
|------|--------|
| 429 | delay *= 3, Retry |
| 503 | delay *= 2, Retry |
| 401/403 | Log Fehler, abbrechen |
| 500 | Retry mit Backoff |

### Rate Limiting

```python
rate_limiter = RateLimiter(
    min_delay=1.0,      # Minimum 1 Sekunde zwischen Requests
    max_delay=3.0,      # Maximum 3 Sekunden
    error_threshold=5,  # Pause nach 5 Fehlern
    pause_duration=60   # 60 Sekunden Pause
)
```

### Datenbank-Schema

```sql
CREATE TABLE domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_name TEXT NOT NULL,
    tld TEXT NOT NULL,
    age_years INTEGER,
    backlinks INTEGER,
    estimated_traffic INTEGER,
    price TEXT,
    auction_status TEXT,
    domain_authority INTEGER,
    page_authority INTEGER,
    source TEXT NOT NULL,
    auction_url TEXT,
    expiry_date TEXT,
    first_seen TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    UNIQUE(domain_name, source)
);
```

---

## Fehlerbehandlung

### Logging-Level

| Level | Verwendung |
|-------|------------|
| DEBUG | Detaillierte Parse-Informationen |
| INFO | Allgemeine Scraper-Status |
| WARNING | Retry-Versuche, Rate Limits |
| ERROR | Kritische Fehler |

### Fehler-Typen

| Fehler | Behandlung |
|--------|------------|
| Timeout | Retry mit erhöhtem Delay |
| Connection Error | Proxy wechseln, Retry |
| HTTP 429 | Exponential Backoff |
| Parse Error | Überspringen, nächste Domain |
| JSON Decode Error | Fallback zu HTML Scraping |

---

## Umgebungsvariablen

| Variable | Beschreibung | Quelle |
|----------|--------------|--------|
| `DROPCATCH_API_KEY` | API-Key für DropCatch | DropCatch.com |
| `GODADDY_API_KEY` | API-Key für GoDaddy | GoDaddy |
| `GODADDY_API_SECRET` | API-Secret für GoDaddy | GoDaddy |

---

## Changelog

### v2.1 (März 2026)
- **Neu:** DropCatch.com Scraper
- **Neu:** NameJet.com Scraper
- **Neu:** SnapNames.com Scraper
- **Neu:** Park.io Scraper
- **Neu:** Pool.com Scraper
- **Update:** Verbesserte Fehlerbehandlung
- **Update:** Erweiterte Dokumentation

### v2.0 (Februar 2026)
- **Neu:** Paralleles Scraping
- **Neu:** Proxy-Rotation
- **Neu:** Retry-Logik mit Exponential Backoff
- **Neu:** Rate Limiting
- **Neu:** Thread-Safe Datenbank-Zugriff

---

## Support & Ressourcen

- **Issues:** GitHub Issues
- **Dokumentation:** Diese Datei
- **API-Keys:** Bei den jeweiligen Anbietern beantragen
