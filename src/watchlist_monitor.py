#!/usr/bin/env python3
"""
EuroBikes Domain Status Monitor
Prüft ob eurobikes.de (oder andere Wunschdomains) verfügbar sind
"""

import whois
import smtplib
import os
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional

# Konfiguration
GMAIL_USER = os.getenv('GMAIL_USER', 'hansdieterbot@gmail.com')
GMAIL_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
RECIPIENT = 'lars.loewe@gmail.com'

# E-Mail deaktiviert - nur noch Telegram über Cron-Jobs
EMAIL_ENABLED = False

# Zu überwachende Domains
WATCHLIST = [
    {
        'domain': 'eurobikes.de',
        'status': 'reserved',  # aktueller Status
        'note': 'Wunschdomain für Fahrrad-Projekt'
    }
]

DB_PATH = '/root/.openclaw/workspace/projects/domain-flipper/data/expired_domains.db'


def send_email(subject: str, body: str, html_body: Optional[str] = None) -> bool:
    """Sendet E-Mail über Gmail SMTP - AKTUELL DEAKTIVIERT"""
    if not EMAIL_ENABLED:
        print(f"📧 E-Mail deaktiviert (nur Telegram): {subject}")
        return True
    
    if not GMAIL_PASSWORD:
        print("❌ GMAIL_APP_PASSWORD nicht gesetzt")
        return False
    
    msg = MIMEMultipart('alternative')
    msg['From'] = GMAIL_USER
    msg['To'] = RECIPIENT
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    if html_body:
        msg.attach(MIMEText(html_body, 'html'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ E-Mail gesendet: {subject}")
        return True
    except Exception as e:
        print(f"❌ Fehler beim Senden: {e}")
        return False


def check_domain_status(domain: str) -> dict:
    """
    Prüft den Status einer Domain via WHOIS
    Returns: dict mit status ('available', 'registered', 'reserved', 'unknown') und details
    """
    try:
        w = whois.whois(domain)
        
        # Wenn keine Registrar-Info vorhanden, ist sie möglicherweise verfügbar
        if not w.registrar:
            return {
                'status': 'available',
                'message': f'{domain} scheint verfügbar zu sein (kein Registrar gefunden)',
                'raw': str(w)
            }
        
        # Status prüfen
        domain_status = w.status
        if isinstance(domain_status, list):
            domain_status = domain_status[0] if domain_status else 'unknown'
        
        # Reservierte Domains erkennen
        if domain_status and ('reserved' in str(domain_status).lower() or 
                              'blocked' in str(domain_status).lower()):
            return {
                'status': 'reserved',
                'message': f'{domain} ist weiterhin reserviert/gesperrt',
                'registrar': w.registrar,
                'raw': str(w)
            }
        
        # Registriert
        return {
            'status': 'registered',
            'message': f'{domain} ist registriert bei {w.registrar}',
            'registrar': w.registrar,
            'expiration': w.expiration_date,
            'raw': str(w)
        }
        
    except whois.parser.PywhoisError as e:
        # Domain nicht gefunden = verfügbar
        if 'not found' in str(e).lower() or 'no match' in str(e).lower():
            return {
                'status': 'available',
                'message': f'{domain} ist VERFÜGBAR! 🎉',
                'raw': str(e)
            }
        return {
            'status': 'unknown',
            'message': f'Fehler bei WHOIS-Abfrage: {e}',
            'raw': str(e)
        }
    except Exception as e:
        return {
            'status': 'unknown',
            'message': f'Unerwarteter Fehler: {e}',
            'raw': str(e)
        }


def save_check_result(domain: str, result: dict):
    """Speichert das Prüfergebnis in die Datenbank"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabelle erstellen falls nicht existiert
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS domain_watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE,
            status TEXT,
            last_check TEXT,
            last_status_change TEXT,
            note TEXT,
            history TEXT
        )
    ''')
    
    now = datetime.now().isoformat()
    
    # Prüfe ob Eintrag existiert
    cursor.execute('SELECT status, history FROM domain_watchlist WHERE domain = ?', (domain,))
    row = cursor.fetchone()
    
    if row:
        old_status, history = row
        # Status-Change erkennen
        status_change = now if old_status != result['status'] else None
        
        # History aktualisieren
        history_entry = f"{now}: {result['status']}"
        new_history = f"{history}\n{history_entry}" if history else history_entry
        
        cursor.execute('''
            UPDATE domain_watchlist 
            SET status = ?, last_check = ?, history = ?,
                last_status_change = COALESCE(?, last_status_change)
            WHERE domain = ?
        ''', (result['status'], now, new_history, status_change, domain))
    else:
        cursor.execute('''
            INSERT INTO domain_watchlist (domain, status, last_check, last_status_change, note, history)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (domain, result['status'], now, now, 'Wunschdomain für Fahrrad-Projekt', 
              f"{now}: {result['status']}"))
    
    conn.commit()
    conn.close()


def was_alert_sent_recently(domain: str, minutes: int = 60) -> bool:
    """Prüft ob in den letzten X Minuten bereits ein Alert gesendet wurde"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS domain_alerts_sent (
            domain TEXT PRIMARY KEY,
            last_alert TEXT,
            alert_count INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('SELECT last_alert FROM domain_alerts_sent WHERE domain = ?', (domain,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return False
    
    last_alert = datetime.fromisoformat(row[0])
    minutes_since = (datetime.now() - last_alert).total_seconds() / 60
    
    return minutes_since < minutes


def mark_alert_sent(domain: str):
    """Markiert dass ein Alert gesendet wurde"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO domain_alerts_sent (domain, last_alert, alert_count)
        VALUES (?, ?, 1)
        ON CONFLICT(domain) DO UPDATE SET
            last_alert = excluded.last_alert,
            alert_count = domain_alerts_sent.alert_count + 1
    ''', (domain, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()


def send_status_change_alert(domain: str, old_status: str, new_status: str, details: dict):
    """Sendet Alert bei Status-Änderung"""
    
    # Keine Spam-Alerts - nur wenn sie tatsächlich verfügbar wird
    if new_status != 'available':
        print(f"ℹ️ {domain}: Status '{new_status}' - kein Alert nötig")
        return False
    
    # Prüfe ob schon vor Kurzem alerted
    if was_alert_sent_recently(domain, minutes=60):
        print(f"⏳ {domain}: Alert wurde bereits in der letzten Stunde gesendet")
        return False
    
    subject = f"🎉 {domain} ist jetzt VERFÜGBAR!"
    
    body = f"""Hallo Lars,

gute Nachrichten! Die Domain {domain} ist nicht mehr reserviert und kann jetzt registriert werden!

📊 Details:
• Domain: {domain}
• Vorheriger Status: {old_status}
• Neuer Status: {new_status}
• Geprüft am: {datetime.now().strftime('%d.%m.%Y %H:%M')}

🛒 Sofort kaufen:
• Denic: https://www.denic.de/service/whois/{domain}
• Checkdomain: https://www.checkdomain.de/domain-registrieren/?domain={domain}
• United-Domains: https://www.united-domains.de/domain-registrieren/{domain}

⚡ Aktion empfohlen – reservierte Domains sind oft schnell weg!

---
Hans-Dieter (Domain Watchdog)
"""
    
    if send_email(subject, body):
        mark_alert_sent(domain)
        return True
    return False


def check_all_watchlist():
    """Prüft alle Domains in der Watchlist"""
    print(f"🔍 Starte Watchlist-Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    alerts_sent = 0
    
    for item in WATCHLIST:
        domain = item['domain']
        print(f"\n📋 Prüfe: {domain}")
        
        # WHOIS-Check
        result = check_domain_status(domain)
        print(f"   Status: {result['status']}")
        print(f"   Info: {result['message']}")
        
        # In DB speichern
        old_status = get_last_known_status(domain)
        save_check_result(domain, result)
        
        # Bei Status-Änderung alerten
        if old_status and old_status != result['status']:
            print(f"   ⚠️ Status-Änderung erkannt: {old_status} → {result['status']}")
            if send_status_change_alert(domain, old_status, result['status'], result):
                alerts_sent += 1
                print(f"   ✅ Alert gesendet!")
        
        # Bei sofortiger Verfügbarkeit (auch ohne vorherigen Status)
        elif result['status'] == 'available' and not old_status:
            if send_status_change_alert(domain, 'unknown', result['status'], result):
                alerts_sent += 1
                print(f"   ✅ Alert gesendet!")
    
    print(f"\n{'-' * 60}")
    print(f"✅ Watchlist-Check abgeschlossen. {alerts_sent} Alert(s) gesendet.")
    return alerts_sent


def get_last_known_status(domain: str) -> Optional[str]:
    """Holt den letzten bekannten Status aus der DB"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT status FROM domain_watchlist WHERE domain = ?', (domain,))
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row else None


def show_watchlist_status():
    """Zeigt den aktuellen Status aller beobachteten Domains"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT domain, status, last_check, last_status_change, note 
        FROM domain_watchlist 
        ORDER BY last_check DESC
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("📭 Noch keine Domains in der Watchlist")
        return
    
    print("\n📋 Domain Watchlist Status:")
    print("-" * 80)
    print(f"{'Domain':<25} {'Status':<12} {'Letzte Prüfung':<20} {'Notiz':<30}")
    print("-" * 80)
    
    for row in rows:
        domain, status, last_check, last_change, note = row
        check_str = last_check[:16] if last_check else 'nie'
        print(f"{domain:<25} {status:<12} {check_str:<20} {note or '-':<30}")
    
    print("-" * 80)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'status':
        show_watchlist_status()
    else:
        check_all_watchlist()
