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
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.settings import DB_PATH, TOP_N_DOMAINS

app = Flask(__name__)
app.config['SECRET_KEY'] = 'domain-flipper-dashboard'

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
    
    cursor.execute('SELECT COUNT(*) FROM domains WHERE DATE(found_at) = DATE("now")')
    new_today = cursor.fetchone()[0]
    
    cursor.execute('SELECT AVG(valuation_score) FROM domains WHERE valuation_score IS NOT NULL')
    avg_score = cursor.fetchone()[0] or 0
    
    # Top 5 Domains
    cursor.execute('''
        SELECT domain_name, tld, valuation_score, estimated_sell_price, current_price
        FROM domains
        WHERE valuation_score >= 70
        ORDER BY valuation_score DESC
        LIMIT 5
    ''')
    top_domains = [dict(row) for row in cursor.fetchall()]
    
    # Letzte 5 Domains
    cursor.execute('''
        SELECT domain_name, tld, found_at, valuation_score
        FROM domains
        ORDER BY found_at DESC
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
    
    # Query-Parameter
    sort_by = request.args.get('sort', 'found_at')
    order = request.args.get('order', 'desc')
    filter_tld = request.args.get('tld', '')
    min_score = request.args.get('min_score', '')
    search = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    per_page = 50
    
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
    
    # Sortierung
    valid_columns = ['domain_name', 'tld', 'found_at', 'valuation_score', 
                     'estimated_sell_price', 'current_price', 'age_days']
    if sort_by in valid_columns:
        query += f' ORDER BY {sort_by}'
        if order.lower() == 'desc':
            query += ' DESC'
    else:
        query += ' ORDER BY found_at DESC'
    
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
    
    cursor.execute('SELECT COUNT(*) FROM domains WHERE DATE(found_at) = DATE("now")')
    new_today = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT DATE(found_at) as date, COUNT(*) as count
        FROM domains
        WHERE found_at >= DATE("now", "-7 days")
        GROUP BY DATE(found_at)
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
    
    query += ' ORDER BY found_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    domains = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify(domains)


if __name__ == '__main__':
    print("🚀 Domain Flipper Dashboard")
    print("📍 http://localhost:5000")
    print("⏹  Ctrl+C zum Beenden")
    app.run(host='0.0.0.0', port=5000, debug=True)
