# Auto-Purchasing System Dokumentation

## Übersicht

Das Auto-Purchasing System ermöglicht automatisierte Domain-Käufe mit umfassenden Safety-Features.

**⚠️ WICHTIG: Immer zuerst im Sandbox-Modus testen!**

## Features

### 1. API-Integrationen

#### Namecheap API
- Sandbox-Unterstützung für Tests
- Domain-Verfügbarkeits-Check
- Automatischer Kauf
- Guthaben-Abfrage

#### Dynadot API
- Sandbox-Unterstützung für Tests
- Bestpreis-Suche über beide APIs
- Automatischer Kauf

### 2. Kauf-Logik

**Auto-Kauf Kriterien:**
- Score > 75 UND Preis < $20 → Automatischer Kauf
- Max 5 Domains/Tag
- Max $500/Tag
- TLD-Blacklist für problematische TLDs

### 3. Safety-Features

- **Sandbox-Modus**: Standardmäßig aktiviert - keine echten Käufe möglich
- **Manuelle Freigabe**: Für Domains >$50
- **E-Mail/Telegram Benachrichtigungen**: Für jeden Kauf
- **Daily/Weekly/Monthly Limits**: Strikte Budget-Kontrolle
- **TLD Blacklist**: Blockiert problematische TLDs (.tk, .ml, .xxx, etc.)
- **Retry-Logik**: Automatische Wiederholung bei Fehlern
- **Cooldown**: Zeit zwischen Käufen

### 4. Logging

- Alle Kaufversuche in SQLite-Datenbank
- Detaillierte Logs in `logs/purchases.log`
- Kaufhistorie und Statistiken

## Konfiguration

### Datei: `config/purchase_rules.yaml`

```yaml
# Sandbox-Modus (immer true für Tests!)
sandbox_mode: true

# Auto-Kauf Kriterien
auto_purchase:
  min_score: 75
  max_price: 20.00

# Limits
limits:
  daily:
    max_domains: 5
    max_amount_usd: 500
  weekly:
    max_domains: 20
    max_amount_usd: 2000

# Manuelle Freigabe
manual_approval:
  enabled: true
  price_threshold: 50.00

# TLD Blacklist
tld_blacklist:
  - tk
  - ml
  - xxx

# API Konfigurationen
apis:
  namecheap:
    enabled: true
    sandbox: true
    api_user: "YOUR_USERNAME"
    api_key: "YOUR_API_KEY"
    username: "YOUR_USERNAME"
    client_ip: "YOUR_IP"
    
  dynadot:
    enabled: true
    sandbox: true
    api_key: "YOUR_API_KEY"
```

## CLI Verwendung

### Einzelne Domain kaufen
```bash
python3 src/auto_purchaser.py --domain "cloudai.com" --score 85
```

### Kauf erzwingen (ignoriert Score)
```bash
python3 src/auto_purchaser.py --domain "example.com" --score 50 --force
```

### Maximalpreis setzen
```bash
python3 src/auto_purchaser.py --domain "example.com" --score 80 --max-price 15.00
```

### Bericht anzeigen
```bash
python3 src/auto_purchaser.py --report
```

### Ausstehende Freigaben anzeigen
```bash
python3 src/auto_purchaser.py --pending
```

### Domain freigeben
```bash
python3 src/auto_purchaser.py --approve "expensive.com" --approve-by "admin"
```

## Demo ausführen

```bash
python3 demo_auto_purchaser.py
```

## Tests ausführen

```bash
# Alle Tests
python3 -m pytest tests/test_auto_purchaser.py -v

# Mit Coverage
python3 -m pytest tests/test_auto_purchaser.py --cov=src
```

## Python API

```python
from src.auto_purchaser import AutoPurchaser

# Initialisieren
purchaser = AutoPurchaser(
    config_path='config/purchase_rules.yaml',
    db_path='data/purchases.db'
)

# Domain kaufen
result = purchaser.attempt_purchase('cloudai.com', score=85)

if result.success:
    print(f"Gekauft: {result.domain} für ${result.price}")
    print(f"Transaction ID: {result.transaction_id}")
else:
    print(f"Fehlgeschlagen: {result.error_message}")

# Limits prüfen
limits = purchaser.get_purchase_limits()
print(f"Verfügbar heute: {limits.remaining_daily_domains} Domains")

# Historie anzeigen
history = purchaser.get_purchase_history(days=7)
```

## Datenbank-Schema

### Tabelle: purchase_attempts
- `domain` - Domain-Name
- `price` - Kaufpreis
- `score` - Domain-Score
- `provider` - Registrar (namecheap/dynadot)
- `success` - Kauf erfolgreich?
- `timestamp` - Zeitpunkt
- `error_message` - Fehlermeldung (falls fehlgeschlagen)
- `transaction_id` - Transaktions-ID (falls erfolgreich)
- `requires_manual_approval` - Manuelle Freigabe nötig?
- `sandbox_mode` - Im Sandbox-Modus ausgeführt?

### Tabelle: purchase_stats
- `date` - Datum
- `domains_purchased` - Anzahl gekaufter Domains
- `total_amount` - Gesamtbetrag

## Wichtige Hinweise

1. **Immer Sandbox-Modus zuerst!**
   - `sandbox_mode: true` in der Config
   - Teste alle Funktionen
   - Erst dann auf `false` setzen

2. **API-Keys sicher aufbewahren**
   - Nie in Git committen
   - Umgebungsvariablen oder .env verwenden

3. **Limits konservativ wählen**
   - Starte mit niedrigen Limits
   - Steigere schrittweise

4. **Regelmäßige Überwachung**
   - Logs prüfen
   - Limits überwachen
   - Kaufhistorie analysieren

## Troubleshooting

### API-Fehler
- Prüfe API-Keys
- Prüfe IP-Whitelist bei Namecheap
- Sandbox vs. Production URLs

### Limits erreicht
- Tägliche Limits prüfen
- `purchase_stats` Tabelle prüfen
- Gegebenenfalls Limits erhöhen

### Keine E-Mails
- SMTP-Einstellungen prüfen
- Spam-Ordner checken
- Logging prüfen
