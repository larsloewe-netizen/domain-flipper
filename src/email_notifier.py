#!/usr/bin/env python3
"""E-Mail Benachrichtigungen für Domain Flipper"""

import smtplib
import os
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Konfiguration
GMAIL_USER = os.getenv('GMAIL_USER', 'hansdieterbot@gmail.com')
GMAIL_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
RECIPIENT = 'lars.loewe@gmail.com'
DB_PATH = '/root/.openclaw/workspace/projects/domain-flipper/data/expired_domains.db'


def send_email(subject, body, html_body=None):
    """Sendet E-Mail über Gmail SMTP"""
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


def send_daily_report():
    """Sendet täglichen Domain-Report"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Prüfe welche Spalten existieren
    cursor.execute('PRAGMA table_info(domains)')
    columns = [col[1] for col in cursor.fetchall()]
    
    # Top 10 Domains der letzten 24h
    if 'valuation_score' in columns:
        cursor.execute('''
            SELECT domain_name, tld, valuation_score, estimated_sell_price, first_seen
            FROM domains
            WHERE DATE(first_seen) = DATE('now')
            ORDER BY valuation_score DESC
            LIMIT 10
        ''')
    else:
        cursor.execute('''
            SELECT domain_name, tld, 0, NULL, first_seen
            FROM domains
            WHERE DATE(first_seen) = DATE('now')
            ORDER BY domain_name
            LIMIT 10
        ''')
    
    domains = cursor.fetchall()
    
    # Statistiken
    cursor.execute("SELECT COUNT(*) FROM domains WHERE DATE(first_seen) = DATE('now')")
    total_today = cursor.fetchone()[0]
    
    if 'valuation_score' in columns:
        cursor.execute("SELECT COUNT(*) FROM domains WHERE valuation_score >= 70 AND DATE(first_seen) = DATE('now')")
        high_potential = cursor.fetchone()[0]
    else:
        high_potential = 0
    
    conn.close()
    
    # E-Mail erstellen
    subject = f"📊 Domain Flipper Report - {datetime.now().strftime('%d.%m.%Y')}"
    
    body = f"""Hallo Lars,

hier ist dein täglicher Domain Flipper Report.

📈 Statistiken (letzte 24h):
- Neue Domains: {total_today}
- High Potential (Score ≥70): {high_potential}

🏆 Top 10 Domains:
"""
    
    body += f"""
🏆 Top 10 Domains:
{'Rank':<6} {'Domain':<35} {'Kaufpreis':<12} {'Verkaufspreis':<15} {'Score':<8}
{'-'*75}
"""
    
    for i, (domain, tld, score, price, found) in enumerate(domains, 1):
        score_str = f"{score}/100" if score else "n/a"
        # Parse buy price
        buy_price_str = "N/A"
        if price:
            try:
                buy_val = float(str(price).replace('$', '').replace(',', ''))
                buy_price_str = f"${buy_val:.0f}"
            except:
                buy_price_str = str(price)
        
        # Calculate estimated sell price
        sell_price_str = "N/A"
        if score and price:
            try:
                buy_val = float(str(price).replace('$', '').replace(',', ''))
                multiplier = 3 + (score / 100) * 7  # 3-10x based on score
                sell_val = buy_val * multiplier
                sell_price_str = f"${sell_val:.0f}"
            except:
                pass
        
        body += f"{i:<6} {domain:<35} {buy_price_str:<12} {sell_price_str:<15} {score_str:<8}\n"
    
    if not domains:
        body += "\nKeine neuen Domains heute."
    
    body += """

---
Hans-Dieter (Domain Flipper Bot)
"""
    
    return send_email(subject, body)


def send_high_potential_alert(domain, score, sell_price, buy_price=None):
    """Sendet Alert bei High-Potential Domain"""
    subject = f"🌟 High Potential Domain gefunden: {domain}"
    
    buy_str = f"{buy_price:.2f} USD" if buy_price else "Nicht bekannt"
    
    body = f"""Hallo Lars,

eine neue Domain mit hohem Potential wurde gefunden!

🌟 Domain: {domain}
📊 Score: {score}/100
💰 Aktueller Kaufpreis: {buy_str}
💵 Geschätzter Verkaufspreis: ${sell_price:.0f}
📈 Marge: {(sell_price/buy_price - 1)*100:.0f}% (wenn Kauf erfolgreich)
⏰ Gefunden: {datetime.now().strftime('%d.%m.%Y %H:%M')}

Diese Domain könnte interessant sein für einen Kauf.
Prüfe auf: ExpiredDomains.net oder ähnlichen Plattformen.

---
Hans-Dieter (Domain Flipper Bot)
"""
    
    return send_email(subject, body)


def check_and_alert_high_potential():
    """Prüft auf neue High-Potential Domains (Score >= 70) und sendet Alerts"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Prüfe welche Spalten existieren
    cursor.execute('PRAGMA table_info(domains)')
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'alert_sent' not in columns or 'valuation_score' not in columns:
        return 0
    
    # Domains mit Score >=70, noch nicht alerted
    cursor.execute('''
        SELECT domain_name, valuation_score, estimated_sell_price, price
        FROM domains
        WHERE valuation_score >= 70
        AND (alert_sent IS NULL OR alert_sent = 0)
    ''')
    
    domains = cursor.fetchall()
    alerted = 0
    
    for domain_data in domains:
        domain = domain_data[0]
        score = domain_data[1]
        sell_price = domain_data[2] or 0
        buy_price_str = domain_data[3]
        
        buy_price = parse_price(buy_price_str)
        if not buy_price and sell_price:
            buy_price = sell_price / 5
        
        if send_high_potential_alert(domain, score, sell_price, buy_price):
            cursor.execute('UPDATE domains SET alert_sent = 1 WHERE domain_name = ?', (domain,))
            alerted += 1
    
    conn.commit()
    conn.close()
    
    return alerted


def parse_price(price_str):
    """Hilfsfunktion zum Parsen des Preises"""
    if not price_str:
        return None
    try:
        return float(str(price_str).replace('$', '').replace(',', '').replace(' USD', ''))
    except:
        return None


def send_interesting_domains_report():
    """Sendet Report über interessante Domains (Score 60-69) im Daily Report"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Prüfe Spalten
    cursor.execute('PRAGMA table_info(domains)')
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'valuation_score' not in columns:
        return 0
    
    # Domains mit Score 60-69, noch nicht im Report erwähnt
    if 'reported' in columns:
        cursor.execute('''
            SELECT domain_name, tld, valuation_score, estimated_sell_price, price, first_seen
            FROM domains
            WHERE valuation_score >= 60 AND valuation_score < 70
            AND (reported IS NULL OR reported = 0)
            ORDER BY valuation_score DESC
        ''')
    else:
        cursor.execute('''
            SELECT domain_name, tld, valuation_score, estimated_sell_price, price, first_seen
            FROM domains
            WHERE valuation_score >= 60 AND valuation_score < 70
            ORDER BY valuation_score DESC
        ''')
    
    domains = cursor.fetchall()
    
    if not domains:
        conn.close()
        return 0
    
    # E-Mail erstellen
    subject = f"📋 Interessante Domains gefunden (Score 60-69) - {datetime.now().strftime('%d.%m.%Y')}"
    
    body = f"""Hallo Lars,

hier sind interessante Domains mit Score 60-69 (unterhalb der High-Potential-Schwelle, aber dennoch beachtenswert):

{'Domain':<35} {'Kaufpreis':<12} {'Verkaufspreis':<15} {'Score':<8}
{'-'*75}
"""
    
    for domain_data in domains:
        domain = domain_data[0]
        tld = domain_data[1] or ''
        score = domain_data[2] or 0
        sell_price = domain_data[3] or 0
        buy_price_str = domain_data[4]
        
        buy_price = parse_price(buy_price_str)
        buy_str = f"${buy_price:.0f}" if buy_price else "N/A"
        sell_str = f"${sell_price:.0f}" if sell_price else "N/A"
        
        body += f"{domain:<35} {buy_str:<12} {sell_str:<15} {score}/100\n"
    
    body += """
Diese Domains sind im Daily Report enthalten, aber erreichen nicht die Schwelle für einen Sofort-Alert (Score >= 70).

---
Hans-Dieter (Domain Flipper Bot)
"""
    
    success = send_email(subject, body)
    
    if success and 'reported' in columns:
        # Markiere als reported
        for domain_data in domains:
            domain = domain_data[0]
            cursor.execute('UPDATE domains SET reported = 1 WHERE domain_name = ?', (domain,))
        conn.commit()
    
    conn.close()
    return len(domains) if success else 0


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python email_notifier.py [daily|alert|interesting|test]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "daily":
        send_daily_report()
    elif command == "alert":
        count = check_and_alert_high_potential()
        print(f"{count} High-Potential Alerts gesendet")
    elif command == "interesting":
        count = send_interesting_domains_report()
        print(f"{count} interessante Domains (Score 60-69) gemeldet")
    elif command == "test":
        send_email(
            "Test: Domain Flipper E-Mail",
            "Dies ist eine Test-E-Mail vom Domain Flipper Bot.\n\nHans-Dieter"
        )
    else:
        print(f"Unbekannter Befehl: {command}")
