#!/usr/bin/env python3
"""
Domain Flipper Dashboard
Web-Interface für Domain-Management
"""

import os
import sys
import sqlite3
import json
import subprocess
import threading
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, send_from_directory, Response

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.settings import DB_PATH, TOP_N_DOMAINS

app = Flask(__name__)
# SECURITY FIX: SECRET_KEY aus Umgebungsvariable laden
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
if not app.config['SECRET_KEY']:
    import secrets
    app.config['SECRET_KEY'] = secrets.token_hex(32)
    app.logger.warning("FLASK_SECRET_KEY not set - using random key (sessions won't persist across restarts)")

# Job-Status-Tracking
job_status = {
    'scraper': {'running': False, 'last_run': None, 'result': None},
    'checker': {'running': False, 'last_run': None, 'result': None},
    'valuator': {'running': False, 'last_run': None, 'result': None}
}


def get_db_connection():
    """Erstellt eine Datenbankverbindung."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    """Dashboard-Startseite."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Statistiken
    cursor.execute('SELECT COUNT(*) FROM domains')
    total_domains = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM domains WHERE valuation_score >= 70')
    high_potential = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM domains WHERE DATE(first_seen) = DATE("now")')
    new_today = cursor.fetchone()[0]
    
    cursor.execute('SELECT AVG(valuation_score) FROM domains WHERE valuation_score IS NOT NULL')
    avg_score = cursor.fetchone()[0] or 0
    
    # Top 5 Domains
    cursor.execute('''
        SELECT domain_name, tld, valuation_score, estimated_sell_price, price
        FROM domains
        WHERE valuation_score >= 70
        ORDER BY valuation_score DESC
        LIMIT 5
    ''')
    top_domains = [dict(row) for row in cursor.fetchall()]
    
    # Letzte 5 Domains
    cursor.execute('''
        SELECT domain_name, tld, first_seen, valuation_score
        FROM domains
        ORDER BY first_seen DESC
        LIMIT 5
    ''')
    recent_domains = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('index.html',
                         stats={
                             'total': total_domains,
                             'high_potential': high_potential,
                             'new_today': new_today,
                             'avg_score': round(avg_score, 1)
                         },
                         top_domains=top_domains,
                         recent_domains=recent_domains,
                         job_status=job_status)


@app.route('/domains')
def domains():
    """Domain-Liste mit Filter und Sortierung."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query-Parameter mit Validierung
    valid_columns = {'domain_name', 'tld', 'first_seen', 'valuation_score', 
                     'estimated_sell_price', 'price', 'age_years'}
    sort_by = request.args.get('sort', 'first_seen')
    # SECURITY FIX: Nur erlaubte Spalten für Sortierung
    if sort_by not in valid_columns:
        sort_by = 'first_seen'
    
    order = request.args.get('order', 'desc')
    if order.lower() not in ('asc', 'desc'):
        order = 'desc'
    
    filter_tld = request.args.get('tld', '')
    
    # SECURITY FIX: Eingabevalidierung für min_score
    min_score = request.args.get('min_score', '')
    if min_score:
        try:
            min_score = int(min_score)
            if not 0 <= min_score <= 100:
                min_score = ''
        except ValueError:
            min_score = ''
    
    search = request.args.get('search', '')
    # SECURITY FIX: XSS-Schutz - entferne potenziell gefährliche Zeichen
    search = re.sub(r'[<>{}{}]', '', search)[:100]  # Max 100 Zeichen
    
    # PERFORMANCE FIX: Page-Limitierung
    try:
        page = int(request.args.get('page', 1))
        page = max(1, min(page, 1000))  # Max 1000 Seiten
    except ValueError:
        page = 1
    
    per_page = min(int(request.args.get('per_page', 50)), 100)  # Max 100 pro Seite
    
    # Basis-Query
    query = 'SELECT * FROM domains WHERE 1=1'
    params = []
    
    if filter_tld:
        query += ' AND tld = ?'
        params.append(filter_tld)
    
    if min_score:
        query += ' AND valuation_score >= ?'
        params.append(int(min_score))
    
    if search:
        query += ' AND domain_name LIKE ?'
        params.append(f'%{search}%')
    
    # Count für Pagination
    count_query = query.replace('SELECT *', 'SELECT COUNT(*)')
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()[0]
    
    # Sortierung - jetzt sicher durch Whitelist-Validierung oben
    query += f' ORDER BY {sort_by}'
    if order.lower() == 'desc':
        query += ' DESC'
    
    # Pagination
    query += ' LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])
    
    cursor.execute(query, params)
    domain_list = [dict(row) for row in cursor.fetchall()]
    
    # Verfügbare TLDs für Filter
    cursor.execute('SELECT DISTINCT tld FROM domains WHERE tld IS NOT NULL ORDER BY tld')
    available_tlds = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('domains.html',
                         domains=domain_list,
                         total_count=total_count,
                         page=page,
                         per_page=per_page,
                         total_pages=(total_count + per_page - 1) // per_page,
                         available_tlds=available_tlds,
                         current_filters={
                             'sort': sort_by,
                             'order': order,
                             'tld': filter_tld,
                             'min_score': min_score,
                             'search': search
                         })


@app.route('/domain/<domain_name>')
def domain_detail(domain_name):
    """Detail-Ansicht einer Domain."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM domains WHERE domain_name = ?', (domain_name,))
    row = cursor.fetchone()
    
    if not row:
        return "Domain nicht gefunden", 404
    
    domain = dict(row)
    conn.close()
    
    return render_template('domain_detail.html', domain=domain)


@app.route('/api/jobs/<job_name>/start', methods=['POST'])
def start_job(job_name):
    """Startet einen Job im Hintergrund."""
    if job_name not in job_status:
        return jsonify({'error': 'Unbekannter Job'}), 400
    
    if job_status[job_name]['running']:
        return jsonify({'error': 'Job läuft bereits'}), 409
    
    def run_job():
        job_status[job_name]['running'] = True
        job_status[job_name]['last_run'] = datetime.now().isoformat()
        
        try:
            if job_name == 'scraper':
                result = subprocess.run(
                    ['python3', 'src/scraper.py'],
                    cwd='/root/.openclaw/workspace/projects/domain-flipper',
                    capture_output=True,
                    text=True,
                    timeout=300
                )
            elif job_name == 'checker':
                result = subprocess.run(
                    ['python3', 'src/domain_checker.py'],
                    cwd='/root/.openclaw/workspace/projects/domain-flipper',
                    capture_output=True,
                    text=True,
                    timeout=600
                )
            elif job_name == 'valuator':
                result = subprocess.run(
                    ['python3', 'src/valuator.py'],
                    cwd='/root/.openclaw/workspace/projects/domain-flipper',
                    capture_output=True,
                    text=True,
                    timeout=300
                )
            
            job_status[job_name]['result'] = {
                'success': result.returncode == 0,
                'stdout': result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout,
                'stderr': result.stderr[-500:] if len(result.stderr) > 500 else result.stderr
            }
        except Exception as e:
            job_status[job_name]['result'] = {
                'success': False,
                'error': str(e)
            }
        finally:
            job_status[job_name]['running'] = False
    
    thread = threading.Thread(target=run_job)
    thread.start()
    
    return jsonify({'status': 'started', 'job': job_name})


@app.route('/api/jobs/<job_name>/status')
def get_job_status(job_name):
    """Gibt den Status eines Jobs zurück."""
    if job_name not in job_status:
        return jsonify({'error': 'Unbekannter Job'}), 400
    
    return jsonify(job_status[job_name])


@app.route('/api/stats')
def get_stats():
    """API-Endpoint für Statistiken."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM domains')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM domains WHERE valuation_score >= 70')
    high_potential = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM domains WHERE DATE(first_seen) = DATE("now")')
    new_today = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT DATE(first_seen) as date, COUNT(*) as count
        FROM domains
        WHERE first_seen >= DATE("now", "-7 days")
        GROUP BY DATE(first_seen)
        ORDER BY date
    ''')
    daily_counts = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'total': total,
        'high_potential': high_potential,
        'new_today': new_today,
        'daily_counts': daily_counts
    })


@app.route('/api/domains')
def api_domains():
    """API-Endpoint für Domain-Liste."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    limit = min(int(request.args.get('limit', 100)), 1000)
    offset = int(request.args.get('offset', 0))
    min_score = request.args.get('min_score')
    
    query = 'SELECT * FROM domains'
    params = []
    
    if min_score:
        query += ' WHERE valuation_score >= ?'
        params.append(int(min_score))
    
    query += ' ORDER BY first_seen DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    domains = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify(domains)


@app.route('/api/charts')
def get_charts_data():
    """API-Endpoint für Chart-Daten."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # TLD-Verteilung
    cursor.execute('''
        SELECT tld, COUNT(*) as count
        FROM domains
        WHERE tld IS NOT NULL
        GROUP BY tld
        ORDER BY count DESC
        LIMIT 10
    ''')
    tld_distribution = [{'tld': row[0], 'count': row[1]} for row in cursor.fetchall()]
    
    # Score-Verteilung
    cursor.execute('''
        SELECT 
            CASE 
                WHEN valuation_score >= 80 THEN '80-100'
                WHEN valuation_score >= 60 THEN '60-79'
                WHEN valuation_score >= 40 THEN '40-59'
                WHEN valuation_score >= 20 THEN '20-39'
                ELSE '0-19'
            END as score_range,
            COUNT(*) as count
        FROM domains
        WHERE valuation_score IS NOT NULL
        GROUP BY score_range
        ORDER BY score_range DESC
    ''')
    score_distribution = [{'range': row[0], 'count': row[1]} for row in cursor.fetchall()]
    
    # Tägliche Entwicklung (letzte 14 Tage)
    cursor.execute('''
        SELECT DATE(first_seen) as date, COUNT(*) as count
        FROM domains
        WHERE first_seen >= DATE("now", "-14 days")
        GROUP BY DATE(first_seen)
        ORDER BY date
    ''')
    daily_growth = [{'date': row[0], 'count': row[1]} for row in cursor.fetchall()]
    
    # High-Potential über Zeit
    cursor.execute('''
        SELECT DATE(first_seen) as date, COUNT(*) as count
        FROM domains
        WHERE valuation_score >= 70 AND first_seen >= DATE("now", "-14 days")
        GROUP BY DATE(first_seen)
        ORDER BY date
    ''')
    high_potential_over_time = [{'date': row[0], 'count': row[1]} for row in cursor.fetchall()]
    
    # Preisverteilung
    cursor.execute('''
        SELECT 
            CASE 
                WHEN price < 10 THEN '< $10'
                WHEN price < 50 THEN '$10-49'
                WHEN price < 100 THEN '$50-99'
                WHEN price < 500 THEN '$100-499'
                ELSE '$500+'
            END as price_range,
            COUNT(*) as count
        FROM domains
        WHERE price IS NOT NULL
        GROUP BY price_range
        ORDER BY price
    ''')
    price_distribution = [{'range': row[0], 'count': row[1]} for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'tld_distribution': tld_distribution,
        'score_distribution': score_distribution,
        'daily_growth': daily_growth,
        'high_potential_over_time': high_potential_over_time,
        'price_distribution': price_distribution
    })


@app.route('/api/export/csv')
def export_csv():
    """Exportiert Domains als CSV."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Filter-Parameter
    min_score = request.args.get('min_score')
    filter_tld = request.args.get('tld', '')
    
    query = 'SELECT * FROM domains WHERE 1=1'
    params = []
    
    if min_score:
        query += ' AND valuation_score >= ?'
        params.append(int(min_score))
    
    if filter_tld:
        query += ' AND tld = ?'
        params.append(filter_tld)
    
    query += ' ORDER BY first_seen DESC'
    
    cursor.execute(query, params)
    domains = cursor.fetchall()
    conn.close()
    
    # CSV erstellen
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    headers = ['domain_name', 'tld', 'age_years', 'backlinks', 'domain_authority', 
               'price', 'auction_status', 'valuation_score', 
               'estimated_sell_price', 'status', 'first_seen']
    writer.writerow(headers)
    
    # Daten
    for domain in domains:
        writer.writerow([
            domain['domain_name'],
            domain['tld'],
            domain['age_years'],
            domain['backlinks'],
            domain['domain_authority'],
            domain['price'],
            domain['auction_status'],
            domain['valuation_score'],
            domain['estimated_sell_price'],
            domain['status'],
            domain['first_seen']
        ])
    
    output.seek(0)
    
    return Response(
        output,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=domains_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        }
    )


@app.route('/api/export/json')
def export_json():
    """Exportiert Domains als JSON."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Filter-Parameter
    min_score = request.args.get('min_score')
    filter_tld = request.args.get('tld', '')
    
    query = 'SELECT * FROM domains WHERE 1=1'
    params = []
    
    if min_score:
        query += ' AND valuation_score >= ?'
        params.append(int(min_score))
    
    if filter_tld:
        query += ' AND tld = ?'
        params.append(filter_tld)
    
    query += ' ORDER BY first_seen DESC'
    
    cursor.execute(query, params)
    domains = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return Response(
        json.dumps(domains, indent=2, default=str),
        mimetype='application/json',
        headers={
            'Content-Disposition': f'attachment; filename=domains_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        }
    )


# ============================================
# KAUF-INTEGRATION ÜBER REGISTRAR APIs
# ============================================

@app.route('/api/purchase/check/<domain_name>')
def check_domain_availability(domain_name):
    """Prüft Verfügbarkeit einer Domain bei verschiedenen Registraren."""
    import requests
    
    tld = request.args.get('tld', 'com')
    results = {}
    
    # Namecheap API Check (simuliert - erfordert API-Key)
    try:
        # Hier würde der echte Namecheap API-Call kommen
        # https://api.namecheap.com/xml.response?ApiUser=...&ApiKey=...&Command=namecheap.domains.check&DomainList=...
        results['namecheap'] = {
            'available': None,  # Würde von API kommen
            'price': None,
            'currency': 'USD',
            'api_required': True,
            'docs': 'https://www.namecheap.com/support/api/intro/'
        }
    except Exception as e:
        results['namecheap'] = {'error': str(e)}
    
    # GoDaddy API Check (simuliert - erfordert API-Key)
    try:
        # Hier würde der echte GoDaddy API-Call kommen
        # https://api.godaddy.com/v1/domains/available?domain=...
        results['godaddy'] = {
            'available': None,
            'price': None,
            'currency': 'USD',
            'api_required': True,
            'docs': 'https://developer.godaddy.com/'
        }
    except Exception as e:
        results['godaddy'] = {'error': str(e)}
    
    # Dynadot API Check (simuliert - erfordert API-Key)
    try:
        results['dynadot'] = {
            'available': None,
            'price': None,
            'currency': 'USD',
            'api_required': True,
            'docs': 'https://www.dynadot.com/domain/api.html'
        }
    except Exception as e:
        results['dynadot'] = {'error': str(e)}
    
    return jsonify({
        'domain': f"{domain_name}.{tld}",
        'check_time': datetime.now().isoformat(),
        'results': results,
        'note': 'Für echte Verfügbarkeitsprüfungen müssen API-Keys konfiguriert werden'
    })


@app.route('/api/purchase/cart/<registrar>', methods=['POST'])
def add_to_cart(registrar):
    """Fügt eine Domain zum Warenkorb eines Registrars hinzu (API-Integration)."""
    data = request.get_json() or {}
    domain_name = data.get('domain_name')
    tld = data.get('tld', 'com')
    
    if not domain_name:
        return jsonify({'error': 'Domain-Name erforderlich'}), 400
    
    if registrar not in ['namecheap', 'godaddy', 'dynadot']:
        return jsonify({'error': 'Unbekannter Registrar'}), 400
    
    # Konfiguration für APIs (muss mit echten Keys gefüllt werden)
    api_config = {
        'namecheap': {
            'api_url': 'https://api.namecheap.com/xml.response',
            'docs': 'https://www.namecheap.com/support/api/intro/',
            'required_keys': ['api_user', 'api_key', 'username', 'client_ip']
        },
        'godaddy': {
            'api_url': 'https://api.godaddy.com/v1/domains/purchase',
            'docs': 'https://developer.godaddy.com/',
            'required_keys': ['api_key', 'api_secret']
        },
        'dynadot': {
            'api_url': 'https://api.dynadot.com/api3.json',
            'docs': 'https://www.dynadot.com/domain/api.html',
            'required_keys': ['api_key']
        }
    }
    
    config = api_config.get(registrar)
    
    # Prüfe ob API-Keys konfiguriert sind
    env_prefix = f"{registrar.upper()}_API"
    missing_keys = []
    for key in config['required_keys']:
        env_key = f"{env_prefix}_{key.upper()}"
        if not os.getenv(env_key):
            missing_keys.append(env_key)
    
    if missing_keys:
        return jsonify({
            'status': 'config_required',
            'message': f'API-Keys für {registrar} nicht konfiguriert',
            'missing_env_vars': missing_keys,
            'setup_instructions': f"""
Um den automatischen Kauf über {registrar} zu aktivieren:

1. Erstelle ein API-Konto bei {registrar}
2. Füge folgende Umgebungsvariablen hinzu:
{chr(10).join([f'   export {k}=dein_key_hier' for k in missing_keys])}

3. Oder erstelle eine .env Datei im Projekt-Root

Dokumentation: {config['docs']}
            """.strip(),
            'manual_link': f"https://www.{registrar}.com/domains/registration/results/?domain={domain_name}.{tld}"
        }), 200
    
    # Hier würde der echte API-Call zum Hinzufügen zum Warenkorb kommen
    # Zum jetzigen Zeitpunkt nur simuliert
    
    return jsonify({
        'status': 'simulated',
        'message': f'{domain_name}.{tld} würde zu {registrar} Warenkorb hinzugefügt',
        'registrar': registrar,
        'domain': f'{domain_name}.{tld}',
        'note': 'Echte API-Integration erfordert gültige API-Keys und Kontostand'
    })


@app.route('/api/config/registrars')
def get_registrar_config():
    """Zeigt den aktuellen Status der Registrar-API-Konfiguration."""
    registrars = ['NAMECHEAP', 'GODADDY', 'DYNADOT']
    status = {}
    
    for reg in registrars:
        has_key = bool(os.getenv(f'{reg}_API_KEY'))
        status[reg.lower()] = {
            'configured': has_key,
            'env_var': f'{reg}_API_KEY',
            'masked_key': os.getenv(f'{reg}_API_KEY', '')[:4] + '****' if has_key else None
        }
    
    return jsonify({
        'registrars': status,
        'note': 'API-Keys werden aus Umgebungsvariablen gelesen'
    })


@app.route('/health')
def health_check():
    """Health-Check Endpoint für Monitoring (Docker/Kubernetes)."""
    import shutil
    
    health = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '2.1.0',
        'checks': {}
    }
    
    # Database check
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM domains')
        count = cursor.fetchone()[0]
        conn.close()
        health['checks']['database'] = {
            'status': 'ok',
            'domains_count': count
        }
    except Exception as e:
        health['checks']['database'] = {
            'status': 'error',
            'message': str(e)
        }
        health['status'] = 'unhealthy'
    
    # Disk space check
    try:
        disk = shutil.disk_usage('/')
        free_gb = disk.free / (1024**3)
        free_percent = (disk.free / disk.total) * 100
        health['checks']['disk'] = {
            'status': 'ok' if free_percent > 10 else 'warning',
            'free_gb': round(free_gb, 2),
            'free_percent': round(free_percent, 2)
        }
        if free_percent < 5:
            health['status'] = 'unhealthy'
    except Exception as e:
        health['checks']['disk'] = {
            'status': 'error',
            'message': str(e)
        }
    
    status_code = 200 if health['status'] == 'healthy' else 503
    return jsonify(health), status_code


@app.route('/api/compare')
def compare_domains():
    """Vergleicht mehrere Domains miteinander."""
    domains = request.args.getlist('domain')
    if len(domains) < 2:
        return jsonify({'error': 'Mindestens 2 Domains erforderlich'}), 400
    
    if len(domains) > 10:
        return jsonify({'error': 'Maximum 10 Domains erlaubt'}), 400
    
    # Sanitize domain names
    domains = [re.sub(r'[^a-zA-Z0-9.-]', '', d) for d in domains]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    placeholders = ','.join(['?' for _ in domains])
    cursor.execute(f'''
        SELECT * FROM domains 
        WHERE domain_name IN ({placeholders})
        ORDER BY valuation_score DESC
    ''', domains)
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Berechne Vergleichs-Metriken
    comparison = {
        'domains': results,
        'count': len(results),
        'requested': len(domains)
    }
    
    if len(results) >= 2:
        scores = [r.get('valuation_score') or 0 for r in results]
        prices = [r.get('estimated_sell_price') or 0 for r in results]
        comparison['analysis'] = {
            'best_score': max(scores),
            'score_difference': max(scores) - min(scores),
            'avg_score': round(sum(scores) / len(scores), 2),
            'best_price': max(prices) if prices else 0,
        }
        comparison['winner'] = results[0]
    
    return jsonify(comparison)


if __name__ == '__main__':
    # SECURITY FIX: Debug-Modus nur via Umgebungsvariable aktivieren
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.getenv('FLASK_PORT', 5000))
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    
    print("🚀 Domain Flipper Dashboard")
    print(f"📍 http://{host}:{port}")
    print(f"🔧 Debug-Modus: {'AN' if debug_mode else 'AUS'}")
    print(f"📝 Health-Check: http://{host}:{port}/health")
    print("⏹  Ctrl+C zum Beenden")
    
    app.run(host=host, port=port, debug=debug_mode)
