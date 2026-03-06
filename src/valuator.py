#!/usr/bin/env python3
"""
Domain Valuation Engine for Domain Flipping
Bewertet Domains nach verschiedenen Kriterien (0-100 Punkte)
"""

import sqlite3
import re
import json
import math
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from pathlib import Path

# Konstanten für Bewertung
MAX_LENGTH_SCORE = 20
MAX_TLD_SCORE = 20
MAX_KEYWORD_SCORE = 20
MAX_AUTHORITY_SCORE = 20
MAX_BRANDABILITY_SCORE = 20
MAX_TOTAL_SCORE = 100

HIGH_POTENTIAL_THRESHOLD = 70

# TLD-Ranking (je höher, desto wertvoller)
TLD_RANKING = {
    'com': 20,
    'ai': 18,
    'io': 17,
    'co': 16,
    'de': 15,
    'net': 14,
    'org': 13,
    'app': 13,
    'dev': 12,
    'cloud': 11,
    'tech': 11,
    'shop': 10,
    'store': 10,
    'online': 9,
    'site': 9,
    'xyz': 7,
    'info': 6,
    'biz': 6,
    'us': 5,
    'eu': 5,
    'uk': 5,
    'fr': 5,
    'es': 5,
    'it': 5,
    'nl': 5,
    'pl': 4,
    'ru': 4,
    'cn': 4,
    'jp': 4,
    'in': 4,
    'br': 4,
    'au': 4,
    'ca': 4,
}

# Populäre/Geschäftliche Keywords (mit Gewichtung)
KEYWORD_PATTERNS = {
    # Tech-Begriffe
    r'cloud': 15,
    r'ai|artificial|intelligence|machine|learning': 18,
    r'crypto|bitcoin|blockchain|nft|web3': 16,
    r'tech|technology|digital|smart': 14,
    r'data|analytics|bigdata': 14,
    r'saas|software|app|api': 15,
    r'bot|automation|robot': 12,
    r'vr|ar|metaverse|virtual|augmented': 13,
    r'cyber|security|privacy|secure': 14,
    
    # Geschäftliche Begriffe
    r'business|company|corp|enterprise': 12,
    r'market|marketing|seo|growth': 13,
    r'shop|store|ecommerce|retail|buy|sell': 14,
    r'pay|payment|finance|fintech|bank|money': 15,
    r'invest|trading|stock|forex': 13,
    r'health|med|medical|care|wellness|fitness': 13,
    r'edu|education|learn|course|academy': 12,
    r'job|career|work|hire|talent|hr': 11,
    r'home|house|realty|estate|property': 12,
    r'auto|car|vehicle|mobility': 11,
    r'food|eat|restaurant|delivery|recipe': 10,
    r'travel|trip|hotel|vacation|booking': 11,
    r'game|gaming|play|esports': 12,
    r'sport|sports|fitness|gym': 10,
    r'news|media|press|blog': 9,
    r'social|community|network': 11,
    r'green|eco|sustainable|energy|solar': 12,
    
    # Premium-Begriffe
    r'pro|premium|elite|vip|plus|max': 10,
    r'now|today|instant|fast|quick': 9,
    r'go|get|start|launch|boost': 9,
    r'lab|hub|space|zone|spot': 9,
    r'ify|able|ly|io$': 8,  # Typische Startup-Endungen
}

# Unwünschte Muster (penalty)
NEGATIVE_PATTERNS = [
    r'[0-9]{4,}',  # Viele Zahlen (außer Jahreszahlen)
    r'-{2,}',      # Mehrfache Bindestriche
    r'[^a-z0-9\-]', # Sonderzeichen (außer Bindestrich)
    r'(.)\1{3,}',  # Vierfache Buchstaben (zzz, ooo)
]

# Vokale für Brandability-Check
VOWELS = set('aeiouAEIOU')


@dataclass
class DomainValuation:
    """Ergebnis einer Domain-Bewertung"""
    domain: str
    tld: str
    length_score: int
    tld_score: int
    keyword_score: int
    authority_score: int
    brandability_score: int
    total_score: int
    is_high_potential: bool
    recommended_sale_price: Optional[float]
    purchase_price: Optional[float]
    backlinks: Optional[int]
    domain_authority: Optional[float]
    matched_keywords: List[str]
    valuation_date: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


class DomainValuator:
    """
    Domain-Bewertungs-Engine
    Bewertet Domains nach 5 Kriterien mit je max. 20 Punkten
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialisiert die Datenbank mit Bewertungstabelle"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Domains-Tabelle (falls nicht existiert)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT UNIQUE NOT NULL,
                tld TEXT,
                purchase_price REAL,
                backlinks INTEGER,
                domain_authority REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Bewertungen-Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS domain_valuations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain_id INTEGER,
                domain TEXT NOT NULL,
                length_score INTEGER DEFAULT 0,
                tld_score INTEGER DEFAULT 0,
                keyword_score INTEGER DEFAULT 0,
                authority_score INTEGER DEFAULT 0,
                brandability_score INTEGER DEFAULT 0,
                total_score INTEGER DEFAULT 0,
                is_high_potential BOOLEAN DEFAULT 0,
                recommended_sale_price REAL,
                purchase_price REAL,
                matched_keywords TEXT,
                backlinks INTEGER,
                domain_authority REAL,
                valuation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (domain_id) REFERENCES domains(id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _extract_tld(self, domain: str) -> str:
        """Extrahiert die TLD aus einer Domain"""
        parts = domain.lower().split('.')
        if len(parts) >= 2:
            return parts[-1]
        return ''
    
    def _extract_name(self, domain: str) -> str:
        """Extrahiert den Domain-Namen ohne TLD"""
        parts = domain.lower().split('.')
        if len(parts) >= 2:
            return '.'.join(parts[:-1])
        return domain.lower()
    
    def calculate_length_score(self, domain: str) -> int:
        """
        Bewertet die Länge der Domain (kürzer = besser)
        Max: 20 Punkte
        """
        name = self._extract_name(domain)
        length = len(name)
        
        # Punkteschema für Länge
        if length <= 4:
            return 20
        elif length <= 6:
            return 18
        elif length <= 8:
            return 16
        elif length <= 10:
            return 14
        elif length <= 12:
            return 12
        elif length <= 15:
            return 9
        elif length <= 20:
            return 6
        elif length <= 25:
            return 3
        else:
            return 0
    
    def calculate_tld_score(self, domain: str) -> int:
        """
        Bewertet die TLD nach Wertigkeit
        Max: 20 Punkte
        """
        tld = self._extract_tld(domain)
        return TLD_RANKING.get(tld, 3)  # Standard: 3 Punkte für unbekannte TLDs
    
    def calculate_keyword_score(self, domain: str) -> Tuple[int, List[str]]:
        """
        Bewertet Keywords in der Domain
        Max: 20 Punkte
        """
        name = self._extract_name(domain)
        name_clean = re.sub(r'[^a-z]', '', name.lower())
        
        matched = []
        total_weight = 0
        
        for pattern, weight in KEYWORD_PATTERNS.items():
            if re.search(pattern, name, re.IGNORECASE):
                matched.append(pattern.replace('\\\\', '').replace('|', '/'))
                total_weight += weight
        
        # Normalisieren auf 0-20 Punkte
        # Maximalgewicht ca. 100, skalieren auf 20
        score = min(20, int((total_weight / 100) * 20))
        
        return score, matched[:5]  # Max 5 Keywords zurückgeben
    
    def calculate_authority_score(self, backlinks: Optional[int], 
                                   domain_authority: Optional[float]) -> int:
        """
        Bewertet Backlinks und Domain Authority
        Max: 20 Punkte
        """
        score = 0
        
        if backlinks:
            if backlinks >= 10000:
                score += 10
            elif backlinks >= 1000:
                score += 8
            elif backlinks >= 500:
                score += 6
            elif backlinks >= 100:
                score += 4
            elif backlinks >= 10:
                score += 2
        
        if domain_authority:
            if domain_authority >= 50:
                score += 10
            elif domain_authority >= 40:
                score += 8
            elif domain_authority >= 30:
                score += 6
            elif domain_authority >= 20:
                score += 4
            elif domain_authority >= 10:
                score += 2
        
        return min(20, score)
    
    def calculate_brandability_score(self, domain: str) -> int:
        """
        Bewertet die Brandability (Lesbarkeit, Aussprache, Memorabilität)
        Max: 20 Punkte
        """
        name = self._extract_name(domain)
        name_clean = re.sub(r'[^a-zA-Z]', '', name)
        
        score = 10  # Basispunktzahl
        
        # Kurze Domains sind brandbarer
        if len(name_clean) <= 6:
            score += 3
        elif len(name_clean) <= 10:
            score += 1
        
        # Keine Bindestriche = besser
        if '-' not in name:
            score += 2
        
        # Balance aus Konsonanten und Vokalen (gute Aussprache)
        vowels_count = sum(1 for c in name_clean if c.lower() in VOWELS)
        consonants_count = len(name_clean) - vowels_count
        
        if len(name_clean) > 0:
            vowel_ratio = vowels_count / len(name_clean)
            # Ideales Verhältnis ca. 30-50% Vokale
            if 0.3 <= vowel_ratio <= 0.5:
                score += 3
            elif 0.2 <= vowel_ratio <= 0.6:
                score += 1
        
        # Keine negativen Muster
        has_negative = any(re.search(pattern, name) for pattern in NEGATIVE_PATTERNS)
        if not has_negative:
            score += 2
        
        # Einfache Wiederholungsmuster (memorabel)
        if re.search(r'(.)(.)\1\2', name_clean):  # ABAB Pattern
            score += 1
        
        # Alliteration (gleicher Anfangsbuchstabe)
        words = name.replace('-', ' ').split()
        if len(words) >= 2:
            first_letters = [w[0].lower() for w in words if w]
            if len(set(first_letters)) < len(first_letters):
                score += 1
        
        return min(20, max(0, score))
    
    def calculate_recommended_price(self, purchase_price: Optional[float], 
                                     total_score: int) -> Optional[float]:
        """
        Berechnet den empfohlenen Verkaufspreis basierend auf Score und Kaufpreis
        Multiplikator: 3-10x je nach Score
        """
        if purchase_price is None or purchase_price <= 0:
            # Geschätzter Basiswert wenn kein Kaufpreis bekannt
            base_value = 10 if total_score >= 50 else 5
        else:
            base_value = purchase_price
        
        # Multiplikator basierend auf Score
        if total_score >= 90:
            multiplier = 10
        elif total_score >= 80:
            multiplier = 7
        elif total_score >= 70:
            multiplier = 5
        elif total_score >= 60:
            multiplier = 4
        elif total_score >= 50:
            multiplier = 3
        else:
            multiplier = 2
        
        recommended = base_value * multiplier
        
        # Auf schöne Zahlen runden
        if recommended >= 100:
            return round(recommended / 10) * 10
        elif recommended >= 10:
            return round(recommended / 5) * 5
        else:
            return round(recommended, 2)
    
    def evaluate_domain(self, domain: str, 
                        purchase_price: Optional[float] = None,
                        backlinks: Optional[int] = None,
                        domain_authority: Optional[float] = None) -> DomainValuation:
        """
        Bewertet eine einzelne Domain nach allen Kriterien
        """
        domain = domain.lower().strip()
        tld = self._extract_tld(domain)
        
        # Einzelbewertungen
        length_score = self.calculate_length_score(domain)
        tld_score = self.calculate_tld_score(domain)
        keyword_score, matched_keywords = self.calculate_keyword_score(domain)
        authority_score = self.calculate_authority_score(backlinks, domain_authority)
        brandability_score = self.calculate_brandability_score(domain)
        
        # Gesamtpunktzahl
        total_score = (length_score + tld_score + keyword_score + 
                       authority_score + brandability_score)
        
        # High Potential?
        is_high_potential = total_score >= HIGH_POTENTIAL_THRESHOLD
        
        # Empfohlener Verkaufspreis
        recommended_price = self.calculate_recommended_price(purchase_price, total_score)
        
        return DomainValuation(
            domain=domain,
            tld=tld,
            length_score=length_score,
            tld_score=tld_score,
            keyword_score=keyword_score,
            authority_score=authority_score,
            brandability_score=brandability_score,
            total_score=total_score,
            is_high_potential=is_high_potential,
            recommended_sale_price=recommended_price,
            purchase_price=purchase_price,
            backlinks=backlinks,
            domain_authority=domain_authority,
            matched_keywords=matched_keywords,
            valuation_date=datetime.now().isoformat()
        )
    
    def save_valuation(self, valuation: DomainValuation) -> int:
        """Speichert eine Bewertung in der Datenbank"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO domain_valuations 
            (domain, length_score, tld_score, keyword_score, authority_score,
             brandability_score, total_score, is_high_potential, recommended_sale_price,
             purchase_price, matched_keywords, backlinks, domain_authority, valuation_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            valuation.domain,
            valuation.length_score,
            valuation.tld_score,
            valuation.keyword_score,
            valuation.authority_score,
            valuation.brandability_score,
            valuation.total_score,
            1 if valuation.is_high_potential else 0,
            valuation.recommended_sale_price,
            valuation.purchase_price,
            json.dumps(valuation.matched_keywords),
            valuation.backlinks,
            valuation.domain_authority,
            valuation.valuation_date
        ))
        
        valuation_id = cursor.lastrowid
        
        # 2. Aktualisiere auch die domains Tabelle (für schnelle Abfragen)
        cursor.execute('''
            UPDATE domains 
            SET valuation_score = ?,
                estimated_sell_price = ?
            WHERE domain_name = ?
        ''', (
            valuation.total_score,
            valuation.recommended_sale_price,
            valuation.domain
        ))
        
        conn.commit()
        conn.close()
        
        return valuation_id
    
    def evaluate_all_domains(self) -> List[DomainValuation]:
        """Bewertet alle Domains aus der Datenbank"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Versuche zuerst das Original-Schema
            cursor.execute('''
                SELECT domain_name, price, backlinks, domain_authority 
                FROM domains
            ''')
            domains = cursor.fetchall()
        except sqlite3.OperationalError:
            try:
                # Fallback auf alternatives Schema
                cursor.execute('''
                    SELECT domain, purchase_price, backlinks, domain_authority 
                    FROM domains
                ''')
                domains = cursor.fetchall()
            except sqlite3.OperationalError:
                # Tabelle existiert nicht oder hat falsches Schema
                domains = []
        
        conn.close()
        
        valuations = []
        for row in domains:
            domain_name, price, backlinks, da = row
            # Preis aus Text extrahieren (falls als String gespeichert)
            if isinstance(price, str):
                try:
                    price = float(price.replace('$', '').replace(',', ''))
                except (ValueError, AttributeError):
                    price = None
            
            valuation = self.evaluate_domain(
                domain_name, 
                purchase_price=price,
                backlinks=backlinks,
                domain_authority=da
            )
            self.save_valuation(valuation)
            valuations.append(valuation)
        
        return valuations
    
    def get_top_domains(self, limit: int = 10, 
                        min_score: int = 0) -> List[DomainValuation]:
        """Holt die Top-Domains aus der Datenbank"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT domain, length_score, tld_score, keyword_score, 
                   authority_score, brandability_score, total_score,
                   is_high_potential, recommended_sale_price, purchase_price,
                   matched_keywords, backlinks, domain_authority, valuation_date
            FROM domain_valuations
            WHERE total_score >= ?
            ORDER BY total_score DESC, recommended_sale_price DESC
            LIMIT ?
        ''', (min_score, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        valuations = []
        for row in rows:
            valuations.append(DomainValuation(
                domain=row[0],
                tld='',
                length_score=row[1],
                tld_score=row[2],
                keyword_score=row[3],
                authority_score=row[4],
                brandability_score=row[5],
                total_score=row[6],
                is_high_potential=bool(row[7]),
                recommended_sale_price=row[8],
                purchase_price=row[9],
                matched_keywords=json.loads(row[10]) if row[10] else [],
                backlinks=row[11],
                domain_authority=row[12],
                valuation_date=row[13]
            ))
        
        return valuations
    
    def get_high_potential_domains(self) -> List[DomainValuation]:
        """Holt alle High-Potential-Domains (Score > 70)"""
        return self.get_top_domains(limit=1000, min_score=HIGH_POTENTIAL_THRESHOLD)
    
    def generate_report(self, output_path: Optional[str] = None) -> str:
        """Generiert einen Bewertungsbericht"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Top 10 Domains holen
        top_domains = self.get_top_domains(limit=10)
        high_potential = self.get_high_potential_domains()
        
        if not top_domains:
            return "Keine Domains in der Datenbank vorhanden."
        
        report_lines = [
            "=" * 70,
            f"DOMAIN BEWERTUNGSBERICHT - {today}",
            "=" * 70,
            "",
            f"High Potential Domains (Score >= {HIGH_POTENTIAL_THRESHOLD}): {len(high_potential)}",
            f"Bewertete Domains gesamt: {len(self.get_top_domains(limit=10000))}",
            "",
            "-" * 70,
            "TOP 10 DOMAIN BEWERTUNGEN",
            "-" * 70,
            "",
        ]
        
        for i, v in enumerate(top_domains, 1):
            status = "🌟 HIGH POTENTIAL" if v.is_high_potential else ""
            report_lines.extend([
                f"{i}. {v.domain.upper()} {status}",
                f"   Gesamtscore: {v.total_score}/100",
                f"   ├── Länge:        {v.length_score}/20",
                f"   ├── TLD:          {v.tld_score}/20",
                f"   ├── Keywords:     {v.keyword_score}/20  ({', '.join(v.matched_keywords[:3]) or 'keine'})",
                f"   ├── Authority:    {v.authority_score}/20",
                f"   └── Brandability: {v.brandability_score}/20",
            ])
            
            if v.purchase_price:
                profit = (v.recommended_sale_price or 0) - v.purchase_price
                report_lines.append(f"   Kaufpreis: ${v.purchase_price:.2f} → Verkauf: ${v.recommended_sale_price:.2f} (Gewinn: ${profit:.2f})")
            else:
                report_lines.append(f"   Empfohlener Verkaufspreis: ${v.recommended_sale_price:.2f}")
            
            if v.backlinks or v.domain_authority:
                report_lines.append(f"   Backlinks: {v.backlinks or 'N/A'} | DA: {v.domain_authority or 'N/A'}")
            
            report_lines.append("")
        
        report_lines.extend([
            "-" * 70,
            "BEWERTUNGSKRITERIEN",
            "-" * 70,
            "",
            "Länge (max 20):        Kürzer = besser (4 Zeichen = 20 Punkte)",
            "TLD (max 20):          .com=20, .ai=18, .io=17, .de=15, ...",
            "Keywords (max 20):     Tech/Geschäfts-Begriffe erkennen",
            "Authority (max 20):    Backlinks & Domain Authority",
            "Brandability (max 20): Lesbarkeit, Aussprache, Memorabilität",
            "",
            "High Potential: Score >= 70",
            "Preisempfehlung: Kaufpreis * Multiplikator (3-10x)",
            "",
            "=" * 70,
        ])
        
        report = "\n".join(report_lines)
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
        
        return report


def main():
    """Hauptfunktion für CLI-Nutzung"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Domain Bewertungs-Engine')
    parser.add_argument('--db', default='data/expired_domains.db', 
                        help='Pfad zur SQLite-Datenbank')
    parser.add_argument('--domain', help='Einzelne Domain bewerten')
    parser.add_argument('--report', action='store_true', help='Bericht generieren')
    parser.add_argument('--output', help='Ausgabedatei für Bericht')
    parser.add_argument('--evaluate-all', action='store_true', 
                        help='Alle Domains in DB bewerten')
    
    args = parser.parse_args()
    
    # Default-Pfad korrigieren falls relativ
    db_path = args.db
    if not db_path.startswith('/'):
        db_path = f"/root/.openclaw/workspace/projects/domain-flipper/{db_path}"
    
    valuator = DomainValuator(db_path)
    
    if args.domain:
        # Einzelne Domain bewerten
        valuation = valuator.evaluate_domain(args.domain)
        print(f"\nBewertung für: {valuation.domain}")
        print(f"Gesamtscore: {valuation.total_score}/100")
        print(f"  Länge:        {valuation.length_score}/20")
        print(f"  TLD:          {valuation.tld_score}/20")
        print(f"  Keywords:     {valuation.keyword_score}/20")
        print(f"  Authority:    {valuation.authority_score}/20")
        print(f"  Brandability: {valuation.brandability_score}/20")
        print(f"\nHigh Potential: {'Ja' if valuation.is_high_potential else 'Nein'}")
        print(f"Empfohlener Preis: ${valuation.recommended_sale_price}")
        if valuation.matched_keywords:
            print(f"Gefundene Keywords: {', '.join(valuation.matched_keywords)}")
    
    elif args.evaluate_all:
        # Alle Domains bewerten
        valuations = valuator.evaluate_all_domains()
        print(f"{len(valuations)} Domains bewertet.")
        high_potential = sum(1 for v in valuations if v.is_high_potential)
        print(f"High Potential Domains: {high_potential}")
    
    elif args.report:
        # Bericht generieren
        report = valuator.generate_report(args.output)
        print(report)
    
    else:
        # Demo: Ein paar Beispiel-Domains bewerten
        demo_domains = [
            "cloudai.com",
            "smartpay.io",
            "fintech.de",
            "super-long-domain-name.xyz",
            "crypto-bot.net",
            "healthylife.co",
            "xr",
        ]
        
        print("=" * 60)
        print("DOMAIN BEWERTUNGS-ENGINE - DEMO")
        print("=" * 60)
        print()
        
        for domain in demo_domains:
            v = valuator.evaluate_domain(domain, purchase_price=10.0)
            status = "🌟 HIGH POTENTIAL" if v.is_high_potential else ""
            print(f"{domain:30} Score: {v.total_score:3d}/100  Preis: ${v.recommended_sale_price}  {status}")
        
        print()
        print("Nutzung:")
        print("  python3 valuator.py --domain 'example.com'")
        print("  python3 valuator.py --evaluate-all")
        print("  python3 valuator.py --report")


if __name__ == "__main__":
    main()


def run():
    """Hauptfunktion für main.py Integration"""
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Starte Domain Valuator...")
    
    db_path = "/root/.openclaw/workspace/projects/domain-flipper/data/expired_domains.db"
    valuator = DomainValuator(db_path)
    
    # Alle Domains bewerten
    valuations = valuator.evaluate_all_domains()
    
    # High Potential zählen
    high_potential = sum(1 for v in valuations if v.is_high_potential)
    
    logger.info(f"Valuator fertig. {len(valuations)} Domains bewertet, {high_potential} High Potential.")
    return len(valuations), high_potential
