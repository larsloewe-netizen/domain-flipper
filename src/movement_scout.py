#!/usr/bin/env python3
"""
Movement Scout - Automatische Erkennung viralier Bewegungen & Domain-Monitoring
Überwacht News, Social Media und Trends nach neuen Abkürzungen und Bewegungen
"""

import sqlite3
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import os
import time
import json

DB_PATH = '/root/.openclaw/workspace/projects/domain-flipper/data/expired_domains.db'

# Zu überwachende Quellen
SOURCES = {
    'reddit': [
        'de', 'politics', 'worldnews', 'news', 'europe', 'australia', 'canada',
        'trending', 'outoftheloop', 'explainlikeimfive', 'changemyview'
    ],
    'news_keywords': [
        'movement', 'protest', 'activism', 'organization', 'coalition',
        'initiative', 'campaign', 'manifesto', 'demonstration'
    ]
}

# TLDs für verschiedene Regionen
TLDS_BY_REGION = {
    'global': ['.com', '.org', '.io', '.net'],
    'europe': ['.de', '.eu', '.fr', '.uk', '.nl', '.es', '.it', '.pl'],
    'australia': ['.au', '.com.au', '.net.au'],
    'north_america': ['.us', '.ca']
}

# Muster für Abkürzungen (3-5 Buchstaben)
ACRONYM_PATTERN = re.compile(r'\b[A-Z]{2,5}\b')
# Muster für Hashtags
HASHTAG_PATTERN = re.compile(r'#(\w+)')


class MovementScout:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()
        self.init_db()
    
    def init_db(self):
        """Initialisiert die Datenbanktabellen"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                acronym TEXT,
                full_name TEXT,
                source TEXT,
                first_seen TEXT,
                last_mentioned TEXT,
                mention_count INTEGER DEFAULT 1,
                description TEXT,
                region TEXT,
                category TEXT,
                viral_score REAL DEFAULT 0.0,
                status TEXT DEFAULT 'watching'  -- watching, hot, peaked, dead
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS movement_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movement_id INTEGER,
                domain TEXT,
                tld TEXT,
                available BOOLEAN,
                checked_at TEXT,
                register_price REAL,
                estimated_value REAL,
                FOREIGN KEY (movement_id) REFERENCES movements(id)
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS scout_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checked_at TEXT,
                source TEXT,
                items_found INTEGER,
                new_movements INTEGER,
                domains_checked INTEGER,
                available_domains INTEGER
            )
        ''')
        
        self.conn.commit()
    
    def fetch_reddit_trends(self, subreddit: str) -> List[Dict]:
        """Holt Trending-Themen von Reddit"""
        try:
            # Reddit JSON API (ohne Authentifizierung, limitiert)
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=10"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            posts = []
            
            for post in data.get('data', {}).get('children', []):
                p = post['data']
                posts.append({
                    'title': p.get('title', ''),
                    'text': p.get('selftext', ''),
                    'subreddit': subreddit,
                    'upvotes': p.get('ups', 0),
                    'comments': p.get('num_comments', 0),
                    'url': p.get('url', '')
                })
            
            return posts
        except Exception as e:
            print(f"❌ Reddit Fehler ({subreddit}): {e}")
            return []
    
    def extract_acronyms(self, text: str) -> List[str]:
        """Extrahiert potenzielle Abkürzungen aus Text"""
        if not text:
            return []
        
        # Großbuchstaben-Abkürzungen finden
        acronyms = ACRONYM_PATTERN.findall(text)
        
        # Gängige Wörter ausschließen
        common_words = {'I', 'A', 'AN', 'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 
                        'YOU', 'ALL', 'CAN', 'HAD', 'HER', 'WAS', 'ONE', 'OUR', 'OUT',
                        'DAY', 'GET', 'HAS', 'HIM', 'HIS', 'HOW', 'ITS', 'MAY', 'NEW',
                        'NOW', 'OLD', 'SEE', 'TWO', 'WAY', 'WHO', 'BOY', 'DID', 'EAS',
                        'OIL', 'SIT', 'USE', 'ANT', 'ANY', 'BAD', 'BET', 'BIG', 'BUS',
                        'BUY', 'CAR', 'CAT', 'COP', 'COW', 'CRY', 'CUP', 'CUT', 'DOG',
                        'DRY', 'DUE', 'EAT', 'EGG', 'END', 'EYE', 'FAN', 'FAR', 'FAT',
                        'FEE', 'FEW', 'FIT', 'FIX', 'FUN', 'GAS', 'GAY', 'GEM', 'GET',
                        'GOD', 'GOT', 'GUM', 'GUN', 'GUY', 'GYM', 'HAT', 'HEN', 'HEY',
                        'HID', 'HIT', 'HOT', 'HUG', 'HUT', 'ICE', 'ILL', 'INK', 'INN',
                        'JAM', 'JAR', 'JAW', 'JET', 'JEW', 'JOB', 'JOY', 'KEY', 'KID',
                        'KIT', 'LAB', 'LAP', 'LAW', 'LAY', 'LEG', 'LID', 'LIE', 'LIP',
                        'LOG', 'LOT', 'LOW', 'MAD', 'MAN', 'MAP', 'MAT', 'MEN', 'MIX',
                        'MUD', 'MUG', 'NAP', 'NET', 'NOD', 'NUT', 'OAK', 'ODD', 'OFF',
                        'OFT', 'OWL', 'OWN', 'PAD', 'PAN', 'PAY', 'PEA', 'PEN', 'PET',
                        'PIE', 'PIN', 'PIT', 'POT', 'PRO', 'PUB', 'PUT', 'RAG', 'RAM',
                        'RAN', 'RAP', 'RAT', 'RAW', 'RAY', 'RED', 'RIB', 'RID', 'RIG',
                        'RIM', 'RIP', 'ROB', 'ROD', 'ROW', 'RUB', 'RUG', 'RUN', 'SAD',
                        'SAT', 'SAW', 'SEA', 'SET', 'SEW', 'SHY', 'SIN', 'SIT', 'SKI',
                        'SKY', 'SLY', 'SON', 'SPY', 'SUM', 'SUN', 'TAB', 'TAN', 'TAP',
                        'TAX', 'TEA', 'TEN', 'THE', 'TIE', 'TIP', 'TOE', 'TON', 'TOP',
                        'TOY', 'TRY', 'TUB', 'TUG', 'VAN', 'VET', 'VIA', 'WAR', 'WAX',
                        'WEB', 'WED', 'WET', 'WHY', 'WIG', 'WIN', 'WIT', 'WOW', 'YES',
                        'YET', 'ZIP', 'ZOO', 'WTF', 'LOL', 'OMG', 'TLDR', 'EDIT', 'IMO',
                        'IMHO', 'FYI', 'BTW', 'AKA', 'USA', 'UK', 'EU', 'UN', 'CEO',
                        'CFO', 'CTO', 'COO', 'CMO', 'VP', 'HR', 'IT', 'PR', 'R&D',
                        'GDP', 'GNP', 'CPI', 'FED', 'ECB', 'IMF', 'WTO', 'NATO', 'NASA',
                        'FBI', 'CIA', 'NSA', 'IRS', 'EPA', 'FDA', 'CDC', 'NIH', 'BBC',
                        'CNN', 'ABC', 'NBC', 'CBS', 'Fox', 'HBO', 'MTV', 'UFC', 'NFL',
                        'NBA', 'NHL', 'MLB', 'FIFA', 'UEFA', 'IOC', 'PGA', 'ATP', 'WTA'}
        
        # Filtere: Mindestens 2 Buchstaben, nicht in common_words, max 5 Buchstaben
        filtered = [a for a in acronyms if len(a) >= 2 and a not in common_words and len(a) <= 5]
        
        return list(set(filtered))  # Eindeutig machen
    
    def extract_hashtags(self, text: str) -> List[str]:
        """Extrahiert Hashtags aus Text"""
        if not text:
            return []
        hashtags = HASHTAG_PATTERN.findall(text)
        # Filtere zu kurze oder zu lange
        return [h for h in hashtags if 3 <= len(h) <= 20]
    
    def check_domain_availability_simple(self, domain: str) -> Tuple[bool, Optional[float]]:
        """Einfacher Domain-Check (simuliert für schnelle Prüfung)"""
        # In der Realität würde hier WHOIS geprüft werden
        # Für jetzt: Dummy-Implementierung
        try:
            import socket
            socket.gethostbyname(domain)
            return False, None  # Domain hat DNS-Eintrag = wahrscheinlich belegt
        except socket.gaierror:
            return True, None  # Kein DNS-Eintrag = möglicherweise verfügbar
    
    def generate_domain_variants(self, term: str) -> List[Tuple[str, str]]:
        """Generiert Domain-Varianten für einen Begriff"""
        term_clean = term.lower().replace(' ', '').replace('-', '').replace('_', '')
        
        variants = []
        all_tlds = []
        for region_tlds in TLDS_BY_REGION.values():
            all_tlds.extend(region_tlds)
        
        for tld in all_tlds:
            variants.append((f"{term_clean}{tld}", tld))
            # Auch kurze Form mit nur Akronym
            if len(term_clean) <= 5:
                variants.append((f"{term_clean}{tld}", tld))
        
        return variants
    
    def calculate_viral_score(self, mentions: int, upvotes: int, comments: int) -> float:
        """Berechnet einen Viralitätsscore"""
        score = 0.0
        score += min(mentions * 2, 20)  # Max 20 Punkte für Erwähnungen
        score += min(upvotes / 100, 30)  # Max 30 Punkte für Upvotes
        score += min(comments * 0.5, 20)  # Max 20 Punkte für Kommentare
        
        # Bonus für hohe Engagement-Rate
        if upvotes > 0 and comments > 0:
            engagement_rate = comments / upvotes
            if engagement_rate > 0.1:  # Kontrovers = viral
                score += 15
        
        return min(score, 100)  # Max 100
    
    def save_movement(self, name: str, acronym: str, source: str, 
                     description: str = '', region: str = 'global') -> int:
        """Speichert eine neue Bewegung oder aktualisiert bestehende"""
        now = datetime.now().isoformat()
        
        # Prüfe ob bereits existiert
        self.cursor.execute(
            'SELECT id, mention_count FROM movements WHERE acronym = ? OR name = ?',
            (acronym, name)
        )
        existing = self.cursor.fetchone()
        
        if existing:
            # Aktualisiere
            movement_id, current_count = existing
            self.cursor.execute('''
                UPDATE movements 
                SET mention_count = ?, last_mentioned = ?, viral_score = viral_score + 5
                WHERE id = ?
            ''', (current_count + 1, now, movement_id))
            self.conn.commit()
            return movement_id
        else:
            # Neue Bewegung
            self.cursor.execute('''
                INSERT INTO movements (name, acronym, source, first_seen, last_mentioned, 
                                      description, region)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, acronym, source, now, now, description, region))
            self.conn.commit()
            return self.cursor.lastrowid
    
    def check_domains_for_movement(self, movement_id: int, term: str):
        """Prüft Domains für eine Bewegung"""
        variants = self.generate_domain_variants(term)
        
        checked = 0
        available = 0
        
        for domain, tld in variants[:10]:  # Max 10 pro Bewegung (Rate-Limit)
            is_avail, price = self.check_domain_availability_simple(domain)
            checked += 1
            
            if is_avail:
                available += 1
                self.cursor.execute('''
                    INSERT INTO movement_domains (movement_id, domain, tld, available, checked_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (movement_id, domain, tld, True, datetime.now().isoformat()))
        
        self.conn.commit()
        return checked, available
    
    def run_scout(self, max_reddits: int = 5) -> Dict:
        """Führt einen kompletten Scout-Durchlauf durch"""
        print(f"\n🔍 Movement Scout gestartet: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)
        
        total_movements = 0
        new_movements = 0
        total_domains_checked = 0
        total_available = 0
        
        # 1. Reddit durchsuchen
        reddits_to_check = SOURCES['reddit'][:max_reddits]
        
        for subreddit in reddits_to_check:
            print(f"\n📱 Scanne r/{subreddit}...")
            posts = self.fetch_reddit_trends(subreddit)
            
            for post in posts:
                text = f"{post['title']} {post['text']}"
                
                # Extrahiere Abkürzungen
                acronyms = self.extract_acronyms(text)
                hashtags = self.extract_hashtags(text)
                
                for acronym in acronyms:
                    # Ignoriere zu kurze oder offensichtliche Abkürzungen
                    if len(acronym) < 2 or acronym in {'I', 'A', 'IT', 'TV', 'UK', 'US', 'EU', 'UN'}:
                        continue
                    
                    # Berechne Viral-Score
                    viral_score = self.calculate_viral_score(
                        1, post['upvotes'], post['comments']
                    )
                    
                    if viral_score > 5:  # Threshold (niedriger für mehr Funde)
                        movement_id = self.save_movement(
                            name=post['title'][:100],
                            acronym=acronym,
                            source=f"reddit/{subreddit}",
                            description=text[:200],
                            region='europe' if subreddit in ['de', 'europe'] else 'north_america'
                        )
                        
                        total_movements += 1
                        
                        # Prüfe ob neu (first_seen == last_mentioned)
                        self.cursor.execute(
                            'SELECT first_seen, last_mentioned FROM movements WHERE id = ?',
                            (movement_id,)
                        )
                        row = self.cursor.fetchone()
                        if row and row[0] == row[1]:
                            new_movements += 1
                            print(f"   🆕 Neue Bewegung: {acronym} (Score: {viral_score:.1f})")
                            
                            # Domain-Check
                            checked, avail = self.check_domains_for_movement(movement_id, acronym)
                            total_domains_checked += checked
                            total_available += avail
                            
                            if avail > 0:
                                print(f"      ✅ {avail} Domains verfügbar!")
            
            time.sleep(1)  # Rate-Limit beachten
        
        # Log speichern
        self.cursor.execute('''
            INSERT INTO scout_log (checked_at, source, items_found, new_movements, 
                                  domains_checked, available_domains)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), 'reddit', total_movements, new_movements,
              total_domains_checked, total_available))
        
        self.conn.commit()
        
        print(f"\n{'=' * 60}")
        print(f"✅ Scout abgeschlossen:")
        print(f"   Bewegungen gefunden: {total_movements}")
        print(f"   Neue Bewegungen: {new_movements}")
        print(f"   Domains geprüft: {total_domains_checked}")
        print(f"   Verfügbare Domains: {total_available}")
        
        return {
            'total_movements': total_movements,
            'new_movements': new_movements,
            'domains_checked': total_domains_checked,
            'available_domains': total_available
        }
    
    def get_hot_movements(self, min_score: float = 20.0) -> List[Dict]:
        """Holt die aktuell heißesten Bewegungen"""
        self.cursor.execute('''
            SELECT m.*, COUNT(md.id) as available_domains
            FROM movements m
            LEFT JOIN movement_domains md ON m.id = md.movement_id AND md.available = 1
            WHERE m.viral_score >= ?
            GROUP BY m.id
            ORDER BY m.viral_score DESC, m.last_mentioned DESC
            LIMIT 10
        ''', (min_score,))
        
        columns = [description[0] for description in self.cursor.description]
        rows = self.cursor.fetchall()
        
        return [dict(zip(columns, row)) for row in rows]
    
    def generate_report(self) -> str:
        """Generiert einen Report der aktuellen Funde"""
        hot = self.get_hot_movements(min_score=10.0)
        
        if not hot:
            return "📭 Keine neuen Bewegungen mit ausreichendem Score gefunden."
        
        report = "🔥 MOVEMENT SCOUT REPORT\n"
        report += "=" * 50 + "\n\n"
        
        for movement in hot:
            report += f"📢 {movement['acronym']}\n"
            report += f"   Name: {movement['name'][:50]}\n"
            report += f"   Score: {movement['viral_score']:.1f}/100\n"
            report += f"   Quelle: {movement['source']}\n"
            report += f"   Verfügbare Domains: {movement['available_domains']}\n"
            report += f"   Erstmals gesehen: {movement['first_seen'][:10]}\n\n"
        
        return report
    
    def close(self):
        """Schließt die Datenbankverbindung"""
        self.conn.close()


def main():
    """Hauptfunktion"""
    scout = MovementScout()
    
    try:
        # Führe Scout durch
        results = scout.run_scout(max_reddits=3)
        
        # Generiere Report
        report = scout.generate_report()
        print("\n" + report)
        
        # Speichere Report
        report_file = f"/root/.openclaw/workspace/projects/domain-flipper/logs/movement_scout_{datetime.now().strftime('%Y%m%d')}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(f"\n📝 Report gespeichert: {report_file}")
        
    finally:
        scout.close()


if __name__ == "__main__":
    main()
