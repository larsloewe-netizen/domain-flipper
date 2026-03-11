#!/usr/bin/env python3
"""
Domain Portfolio Dashboard
Web-Interface zur Verwaltung aller Domains
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json

app = Flask(__name__)

DB_PATH = '/root/.openclaw/workspace/projects/domain-flipper/data/expired_domains.db'
DASHBOARD_PORT = 5050


def get_db_connection():
    """Erstellt Datenbankverbindung"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_portfolio_db():
    """Initialisiert die Portfolio-Datenbanktabellen"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Portfolio-Tabelle: Deine eigenen Domains
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE NOT NULL,
            tld TEXT,
            status TEXT DEFAULT 'active',  -- active, sold, pending, expired
            registrar TEXT,
            
            -- Kauf-Informationen
            purchase_date TEXT,
            purchase_price REAL,
            purchase_currency TEXT DEFAULT 'EUR',
            
            -- Verkaufs-Informationen
            sale_date TEXT,
            sale_price REAL,
            sale_currency TEXT DEFAULT 'EUR',
            sale_platform TEXT,  -- sedo, dan, afternic, direct, etc.
            buyer TEXT,
            
            -- Bewertung & Metadaten
            estimated_value REAL,
            category TEXT,
            description TEXT,
            tags TEXT,  -- JSON-Array
            
            -- Technische Daten
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            
            -- WHOIS-Daten
            expiration_date TEXT,
            auto_renew BOOLEAN DEFAULT 0
        )
    ''')
    
    # Transaktionen-Tabelle (Kauf/Verkauf Historie)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id INTEGER,
            type TEXT,  -- purchase, sale, renewal, transfer
            date TEXT,
            amount REAL,
            currency TEXT DEFAULT 'EUR',
            platform TEXT,
            counterparty TEXT,
            notes TEXT,
            FOREIGN KEY (domain_id) REFERENCES portfolio(id)
        )
    ''')
    
    # Listings-Tabelle (aktive Verkaufsangebote)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id INTEGER,
            platform TEXT,  -- sedo, dan, afternic, ebay, etc.
            listing_url TEXT,
            listed_price REAL,
            currency TEXT DEFAULT 'EUR',
            listed_date TEXT,
            status TEXT DEFAULT 'active',  -- active, sold, expired, withdrawn
            views INTEGER DEFAULT 0,
            inquiries INTEGER DEFAULT 0,
            FOREIGN KEY (domain_id) REFERENCES portfolio(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Portfolio-Datenbank initialisiert")


# ==================== API ENDPOINTS ====================

@app.route('/')
def dashboard():
    """Haupt-Dashboard-Seite"""
    stats = get_portfolio_stats()
    recent_domains = get_recent_domains(10)
    return render_template('dashboard.html', stats=stats, recent=recent_domains)


@app.route('/api/stats')
def api_stats():
    """Portfolio-Statistiken als JSON"""
    return jsonify(get_portfolio_stats())


@app.route('/api/domains')
def api_domains():
    """Alle Domains als JSON"""
    status_filter = request.args.get('status')
    return jsonify(get_all_domains(status_filter))


@app.route('/api/domain/<domain_name>')
def api_domain_detail(domain_name):
    """Details zu einer Domain"""
    domain = get_domain_details(domain_name)
    if domain:
        return jsonify(domain)
    return jsonify({'error': 'Domain not found'}), 404


@app.route('/api/add_domain', methods=['POST'])
def api_add_domain():
    """Neue Domain zum Portfolio hinzufügen"""
    data = request.json
    success = add_domain(data)
    return jsonify({'success': success})


@app.route('/api/update_domain/<domain_name>', methods=['POST'])
def api_update_domain(domain_name):
    """Domain aktualisieren"""
    data = request.json
    success = update_domain(domain_name, data)
    return jsonify({'success': success})


@app.route('/api/sell_domain', methods=['POST'])
def api_sell_domain():
    """Domain als verkauft markieren"""
    data = request.json
    success = mark_domain_sold(data['domain'], data['sale_price'], 
                                data.get('sale_date'), data.get('platform'))
    return jsonify({'success': success})


@app.route('/portfolio')
def portfolio_view():
    """Portfolio-Übersichtsseite"""
    domains = get_all_domains()
    return render_template('portfolio.html', domains=domains)


@app.route('/transactions')
def transactions_view():
    """Transaktionshistorie"""
    transactions = get_all_transactions()
    return render_template('transactions.html', transactions=transactions)


# ==================== HELPER FUNCTIONS ====================

def get_portfolio_stats() -> Dict:
    """Berechnet Portfolio-Statistiken"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    stats = {
        'total_domains': 0,
        'active_domains': 0,
        'sold_domains': 0,
        'pending_domains': 0,
        'total_invested': 0,
        'total_revenue': 0,
        'total_profit': 0,
        'roi_percent': 0,
        'avg_purchase_price': 0,
        'avg_sale_price': 0
    }
    
    cursor.execute('SELECT COUNT(*) FROM portfolio')
    stats['total_domains'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM portfolio WHERE status = 'active'")
    stats['active_domains'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM portfolio WHERE status = 'sold'")
    stats['sold_domains'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM portfolio WHERE status = 'pending'")
    stats['pending_domains'] = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(purchase_price) FROM portfolio WHERE purchase_price IS NOT NULL')
    result = cursor.fetchone()[0]
    stats['total_invested'] = result or 0
    
    cursor.execute('SELECT SUM(sale_price) FROM portfolio WHERE sale_price IS NOT NULL')
    result = cursor.fetchone()[0]
    stats['total_revenue'] = result or 0
    
    stats['total_profit'] = stats['total_revenue'] - stats['total_invested']
    
    if stats['total_invested'] > 0:
        stats['roi_percent'] = round((stats['total_profit'] / stats['total_invested']) * 100, 2)
    
    cursor.execute('SELECT AVG(purchase_price) FROM portfolio WHERE purchase_price IS NOT NULL')
    result = cursor.fetchone()[0]
    stats['avg_purchase_price'] = round(result, 2) if result else 0
    
    cursor.execute('SELECT AVG(sale_price) FROM portfolio WHERE sale_price IS NOT NULL')
    result = cursor.fetchone()[0]
    stats['avg_sale_price'] = round(result, 2) if result else 0
    
    conn.close()
    return stats


def get_all_domains(status_filter: Optional[str] = None) -> List[Dict]:
    """Holt alle Domains aus dem Portfolio"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT p.*, 
               GROUP_CONCAT(DISTINCT l.platform) as listing_platforms,
               GROUP_CONCAT(DISTINCT l.listed_price) as listing_prices
        FROM portfolio p
        LEFT JOIN listings l ON p.id = l.domain_id AND l.status = 'active'
    '''
    
    if status_filter:
        query += f" WHERE p.status = '{status_filter}'"
    
    query += ' GROUP BY p.id ORDER BY p.created_at DESC'
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    domains = []
    for row in rows:
        domain = dict(row)
        
        # Berechne ROI für verkaufte Domains
        if domain['purchase_price'] and domain['sale_price']:
            profit = domain['sale_price'] - domain['purchase_price']
            domain['profit'] = round(profit, 2)
            domain['roi_percent'] = round((profit / domain['purchase_price']) * 100, 2)
        else:
            domain['profit'] = None
            domain['roi_percent'] = None
        
        # Parse Tags
        if domain['tags']:
            try:
                domain['tags'] = json.loads(domain['tags'])
            except:
                domain['tags'] = domain['tags'].split(',')
        else:
            domain['tags'] = []
        
        domains.append(domain)
    
    conn.close()
    return domains


def get_recent_domains(limit: int = 10) -> List[Dict]:
    """Holt die neuesten Domains"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM portfolio 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_domain_details(domain_name: str) -> Optional[Dict]:
    """Holt Details zu einer Domain"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM portfolio WHERE domain = ?', (domain_name,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None
    
    domain = dict(row)
    
    # Transaktionen holen
    cursor.execute('''
        SELECT * FROM transactions 
        WHERE domain_id = ? 
        ORDER BY date DESC
    ''', (domain['id'],))
    domain['transactions'] = [dict(r) for r in cursor.fetchall()]
    
    # Listings holen
    cursor.execute('''
        SELECT * FROM listings 
        WHERE domain_id = ? 
        ORDER BY listed_date DESC
    ''', (domain['id'],))
    domain['listings'] = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    return domain


def add_domain(data: Dict) -> bool:
    """Fügt neue Domain zum Portfolio hinzu"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO portfolio (
                domain, tld, status, registrar, purchase_date, purchase_price,
                purchase_currency, category, description, tags, notes, expiration_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('domain'),
            data.get('tld'),
            data.get('status', 'active'),
            data.get('registrar'),
            data.get('purchase_date'),
            data.get('purchase_price'),
            data.get('purchase_currency', 'EUR'),
            data.get('category'),
            data.get('description'),
            json.dumps(data.get('tags', [])),
            data.get('notes'),
            data.get('expiration_date')
        ))
        
        domain_id = cursor.lastrowid
        
        # Kauf-Transaktion erstellen
        if data.get('purchase_price'):
            cursor.execute('''
                INSERT INTO transactions (domain_id, type, date, amount, currency, platform, notes)
                VALUES (?, 'purchase', ?, ?, ?, ?, ?)
            ''', (
                domain_id,
                data.get('purchase_date', datetime.now().isoformat()),
                data.get('purchase_price'),
                data.get('purchase_currency', 'EUR'),
                data.get('registrar'),
                f"Kauf von {data.get('domain')}"
            ))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Fehler beim Hinzufügen: {e}")
        return False
    finally:
        conn.close()


def update_domain(domain_name: str, data: Dict) -> bool:
    """Aktualisiert eine Domain"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    allowed_fields = ['status', 'registrar', 'estimated_value', 'category', 
                      'description', 'notes', 'auto_renew', 'expiration_date']
    
    updates = []
    values = []
    
    for field in allowed_fields:
        if field in data:
            updates.append(f"{field} = ?")
            values.append(data[field])
    
    if not updates:
        return False
    
    values.append(domain_name)
    
    try:
        cursor.execute(f'''
            UPDATE portfolio 
            SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
            WHERE domain = ?
        ''', values)
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Fehler beim Aktualisieren: {e}")
        return False
    finally:
        conn.close()


def mark_domain_sold(domain_name: str, sale_price: float, 
                     sale_date: Optional[str] = None,
                     platform: Optional[str] = None) -> bool:
    """Markiert Domain als verkauft"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sale_date = sale_date or datetime.now().isoformat()
    
    try:
        cursor.execute('''
            UPDATE portfolio 
            SET status = 'sold', sale_price = ?, sale_date = ?, sale_platform = ?
            WHERE domain = ?
        ''', (sale_price, sale_date, platform, domain_name))
        
        if cursor.rowcount == 0:
            return False
        
        # Domain-ID holen
        cursor.execute('SELECT id FROM portfolio WHERE domain = ?', (domain_name,))
        row = cursor.fetchone()
        if row:
            # Verkaufs-Transaktion erstellen
            cursor.execute('''
                INSERT INTO transactions (domain_id, type, date, amount, currency, platform, notes)
                VALUES (?, 'sale', ?, ?, 'EUR', ?, ?)
            ''', (row[0], sale_date, sale_price, platform, f"Verkauf von {domain_name}"))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Fehler beim Markieren als verkauft: {e}")
        return False
    finally:
        conn.close()


def get_all_transactions() -> List[Dict]:
    """Holt alle Transaktionen"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT t.*, p.domain 
        FROM transactions t
        JOIN portfolio p ON t.domain_id = p.id
        ORDER BY t.date DESC
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ==================== INITIALISIERUNG ====================

if __name__ == '__main__':
    init_portfolio_db()
    print(f"🚀 Dashboard startet auf http://localhost:{DASHBOARD_PORT}")
    app.run(host='0.0.0.0', port=DASHBOARD_PORT, debug=True)
