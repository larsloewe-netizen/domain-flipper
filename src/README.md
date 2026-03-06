# Domain Valuation Engine

Bewertungs-Engine für das Domain-Flipping-Projekt. Bewertet Domains nach 5 Kriterien mit je max. 20 Punkten (Gesamt: 0-100).

## Bewertungskriterien

| Kriterium | Max Punkte | Beschreibung |
|-----------|------------|--------------|
| Länge | 20 | Kürzer = besser (4 Zeichen = 20 Punkte) |
| TLD | 20 | .com=20, .ai=18, .io=17, .de=15, ... |
| Keywords | 20 | Tech-/Geschäfts-Begriffe erkennen |
| Authority | 20 | Backlinks & Domain Authority |
| Brandability | 20 | Lesbarkeit, Aussprache, Memorabilität |

## High Potential Threshold

Domains mit Score >= 70 werden als "High Potential" markiert.

## Preisempfehlung

Multiplikator basierend auf Score:
- Score 90+: 10x Kaufpreis
- Score 80-89: 7x Kaufpreis
- Score 70-79: 5x Kaufpreis
- Score 60-69: 4x Kaufpreis
- Score 50-59: 3x Kaufpreis
- Score < 50: 2x Kaufpreis

## Verwendung

```bash
# Einzelne Domain bewerten
python3 valuator.py --domain 'example.com'

# Alle Domains in DB bewerten
python3 valuator.py --evaluate-all

# Bericht generieren
python3 valuator.py --report

# Bericht in Datei speichern
python3 valuator.py --report --output report.txt
```

## Als Modul nutzen

```python
from valuator import DomainValuator

valuator = DomainValuator('data/expired_domains.db')

# Einzelne Domain bewerten
result = valuator.evaluate_domain(
    domain='aipay.io',
    purchase_price=15.0,
    backlinks=1500,
    domain_authority=35
)

print(f"Score: {result.total_score}/100")
print(f"High Potential: {result.is_high_potential}")
print(f"Empfohlener Preis: ${result.recommended_sale_price}")

# Alle Domains bewerten
valuations = valuator.evaluate_all_domains()

# Top 10 anzeigen
top_domains = valuator.get_top_domains(limit=10)

# Bericht generieren
report = valuator.generate_report('report.txt')
```

## Datenbank-Schema

Die Engine arbeitet mit der `domains`-Tabelle:
- `domain_name`: Domain-Name
- `tld`: Top-Level-Domain
- `price`: Kaufpreis
- `backlinks`: Anzahl Backlinks
- `domain_authority`: Domain Authority Score

Bewertungen werden in `domain_valuations` gespeichert.

## Tech-Stack

- Python 3
- sqlite3
- regex
