"""Authenticated dataset and analysis API, served by the existing server entry point."""
import csv
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import signal
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, request, send_file
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException, NotFound, TooManyRequests, UnsupportedMediaType

import database
from statistics_engine import MAX_ROWS, METRICS, calculate, number, parse_text, validate_dataset

ROOT = Path(__file__).resolve().parent
ITERATIONS = 600_000


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def text_field(data, key, maximum, required=False):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f'{key.replace("_", " ").capitalize()} must contain {"1" if required else "0"}–{maximum} characters.')
    return value.strip()


def password_field(data, key, minimum=1):
    value = data.get(key)
    if not isinstance(value, str) or not minimum <= len(value) <= 128:
        raise ValueError(f'{key.replace("_", " ").capitalize()} must contain {minimum}–128 characters.')
    return value


def create_app(config=None):
    serve_frontend = (config or {}).get('SERVE_FRONTEND', os.environ.get('SERVE_FRONTEND', 'true').lower() == 'true')
    app = Flask(__name__, static_folder='static' if serve_frontend else None)
    app.json.sort_keys = False
    app.config.update(
        DATABASE=os.environ.get('DATABASE_PATH', str(ROOT / 'accounts.sqlite3')),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'false').lower() == 'true',
        ALLOWED_HOSTS=os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(','),
        SECRET_KEY=os.environ.get('APP_SECRET'),
    )
    app.config.update(config or {})
    database.initialize(app.config['DATABASE'])
    if not app.config['SECRET_KEY']:
        key_path = Path(app.config['DATABASE']).with_suffix('.secret')
        try:
            with key_path.open('x', encoding='utf-8') as key_file:
                key_file.write(secrets.token_hex(32))
            key_path.chmod(0o600)
        except FileExistsError:
            pass
        app.config['SECRET_KEY'] = key_path.read_text(encoding='utf-8').strip()
    signer = URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='workspace-csrf-v1')

    def db():
        if 'db' not in g:
            g.db = database.connect(app.config['DATABASE'])
        return g.db

    @app.teardown_appcontext
    def close_db(error=None):
        connection = g.pop('db', None)
        if connection:
            connection.close()

    def error(message, status=400):
        return jsonify(error=message), status

    def token_hash():
        return hashlib.sha256(request.cookies.get('session', '').encode()).hexdigest()

    def set_cookie(response, name, value, max_age=None):
        response.set_cookie(name, value, max_age=max_age, httponly=True,
                            secure=app.config['COOKIE_SECURE'], samesite='Strict', path='/')

    @app.before_request
    def protect_request():
        host = urlsplit('//' + request.host).hostname
        if host not in app.config['ALLOWED_HOSTS']:
            return error('Invalid host. Configure ALLOWED_HOSTS for your server address.', 403)
        g.csrf = request.cookies.get('csrf', '')
        try:
            signer.loads(g.csrf, max_age=7200)
        except (BadSignature, SignatureExpired):
            g.csrf = signer.dumps(secrets.token_urlsafe(24))
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                return error('Request origin is not allowed.', 403)
            supplied = request.headers.get('X-CSRF-Token', '')
            if not supplied or not hmac.compare_digest(supplied, g.csrf):
                return error('CSRF token missing or expired. Refresh the page and try again.', 403)
        g.user = db().execute('''SELECT users.id, username, email FROM users JOIN sessions
            ON users.id=sessions.user_id WHERE token_hash=? AND expires>?''', (token_hash(), time.time())).fetchone()
        if request.path.startswith('/api/') and request.path not in ('/api/me', '/api/login', '/api/signup', '/api/health') and not g.user:
            return error('Please sign in to continue.', 401)

    @app.after_request
    def security_headers(response):
        response.headers['Cache-Control'] = 'no-store' if not request.path.startswith('/static/') else 'public, max-age=3600'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; worker-src blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if app.config['COOKIE_SECURE']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if hasattr(g, 'csrf') and g.csrf != request.cookies.get('csrf'):
            set_cookie(response, 'csrf', g.csrf)
        if request.path.startswith('/api/'):
            app.logger.info('%s %s %s', request.method, request.path, response.status_code)
        return response

    @app.errorhandler(ValueError)
    def invalid_value(exc):
        return error(str(exc))

    @app.errorhandler(HTTPException)
    def http_error(exc):
        response, status = error('Upload or request exceeds the 2 MB limit.' if exc.code == 413 else exc.description, exc.code)
        if status == 429:
            response.headers['Retry-After'] = '900'
        return response, status

    @app.errorhandler(sqlite3.Error)
    def database_error(exc):
        app.logger.exception('Database operation failed')
        return error('The database is busy or unavailable. Please try again.', 503)

    @app.errorhandler(Exception)
    def unexpected_error(exc):
        app.logger.exception('Request failed')
        return error('An unexpected server error occurred.', 500)

    def body():
        if not request.is_json:
            raise UnsupportedMediaType('JSON is required.')
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError('A JSON object is required.')
        return data

    def user_json():
        return {'username': g.user['username'], 'email': g.user['email']} if g.user else None

    def owned_dataset(identifier):
        if type(identifier) is not int:
            raise ValueError('Provide a valid dataset identifier.')
        row = db().execute('SELECT * FROM datasets WHERE id=? AND user_id=?', (identifier, g.user['id'])).fetchone()
        if not row:
            raise NotFound('Dataset not found.')
        return row

    def owned_analysis(identifier):
        if type(identifier) is not int:
            raise ValueError('Provide a valid analysis identifier.')
        row = db().execute('''SELECT analyses.*, datasets.name AS dataset_name, datasets.revision AS current_revision
            FROM analyses JOIN datasets ON datasets.id=dataset_id WHERE analyses.id=? AND analyses.user_id=?''',
                           (identifier, g.user['id'])).fetchone()
        if not row:
            raise NotFound('Analysis not found.')
        return row

    def parameters(dataset_id, analysis_id=None):
        owned_dataset(dataset_id)
        sql, args = 'SELECT * FROM custom_parameters WHERE dataset_id=?', [dataset_id]
        if analysis_id is not None:
            sql += ' AND (analysis_id IS NULL OR analysis_id=?)'
            args.append(analysis_id)
        output = []
        for row in db().execute(sql + ' ORDER BY created_at', args):
            entry = dict(row)
            entry['value'] = json.loads(entry.pop('value_json'))
            output.append(entry)
        return output

    def dataset_json(row, full=True):
        output = dict(row)
        data = json.loads(output.pop('data_json'))
        output['observation_count'] = len(data['rows']) if data['kind'] == 'raw' else sum(int(number(r[-1])) for r in data['rows'])
        output['kind'], output['columns'] = data['kind'], data['columns']
        output['analysis_count'] = db().execute('SELECT COUNT(*) FROM analyses WHERE dataset_id=?', (row['id'],)).fetchone()[0]
        if full:
            output['data'], output['parameters'] = data, parameters(row['id'])
        return output

    def analysis_json(row, full=True):
        output = dict(row)
        result = json.loads(output.pop('result_json'))
        snapshot = json.loads(output.pop('dataset_snapshot'))
        output['historical'] = output['dataset_revision'] != output['current_revision']
        output['summary'] = result['summary']
        if full:
            output['calculation'], output['snapshot'] = result, snapshot
            output['parameters'] = parameters(row['dataset_id'], row['id'])
        return output

    def rate_limit(identifier=''):
        connection, timestamp = db(), time.time()
        ip = hashlib.sha256(('ip:' + (request.remote_addr or '')).encode()).hexdigest()
        account = hashlib.sha256(('account:' + identifier.casefold()).encode()).hexdigest()
        with connection:
            connection.execute('DELETE FROM login_attempts WHERE attempted_at<?', (timestamp-900,))
            for key, limit in [(ip, 30)] + ([(account, 10)] if identifier else []):
                count = connection.execute('SELECT COUNT(*) FROM login_attempts WHERE key=? AND attempted_at>?', (key, timestamp-900)).fetchone()[0]
                if count >= limit:
                    raise TooManyRequests('Too many account attempts. Try again in 15 minutes.')
            for key in [ip] + ([account] if identifier else []):
                connection.execute('INSERT INTO login_attempts VALUES (?, ?)', (key, timestamp))

    @app.get('/')
    @app.get('/hrml')
    def index():
        if not serve_frontend:
            raise NotFound()
        return send_file(ROOT / 'hrml', mimetype='text/html')

    @app.get('/api/health')
    def health():
        db().execute('SELECT 1')
        return jsonify(status='ok')

    @app.get('/api/me')
    def me():
        return jsonify(user=user_json(), csrf_token=g.csrf)

    @app.post('/api/signup')
    def signup():
        data = body()
        username = text_field(data, 'username', 32, True)
        email = text_field(data, 'email', 254, True).lower()
        password = password_field(data, 'password', 8)
        if not re.fullmatch(r'[A-Za-z0-9_]{3,32}', username):
            raise ValueError('Username must contain 3–32 letters, numbers, or underscores.')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise ValueError('Please enter a valid email address.')
        if not 8 <= len(password) <= 128:
            raise ValueError('Password must contain 8–128 characters.')
        rate_limit()
        salt = secrets.token_bytes(16)
        try:
            with db():
                db().execute('INSERT INTO users(username,email,salt,password_hash) VALUES (?,?,?,?)',
                             (username, email, salt, password_hash(password, salt)))
        except sqlite3.IntegrityError:
            return error('That username or email is already registered.', 409)
        return jsonify(ok=True), 201

    @app.post('/api/login')
    def login():
        data = body()
        identifier = text_field(data, 'identifier', 254, True)
        password = password_field(data, 'password')
        rate_limit(identifier)
        user = db().execute('SELECT * FROM users WHERE username=? OR email=?', (identifier, identifier)).fetchone()
        digest = password_hash(password, user['salt'] if user else bytes(16))
        if not user or not hmac.compare_digest(digest, user['password_hash']):
            return error('Incorrect username, email, or password.', 401)
        token = secrets.token_urlsafe(32)
        remember = data.get('remember') is True
        lifetime = 30*86400 if remember else 12*3600
        with db():
            db().execute('DELETE FROM sessions WHERE expires<=? OR token_hash=?', (time.time(), token_hash()))
            db().execute('INSERT INTO sessions VALUES (?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user['id'], time.time()+lifetime))
        response = jsonify(user={'username': user['username'], 'email': user['email']}, csrf_token=g.csrf)
        set_cookie(response, 'session', token, lifetime if remember else None)
        return response

    @app.post('/api/logout')
    def logout():
        with db():
            db().execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(),))
        response = jsonify(ok=True)
        set_cookie(response, 'session', '', 0)
        return response

    @app.post('/api/profile/password')
    def change_password():
        data = body()
        password_field(data, 'current_password')
        password_field(data, 'new_password', 8)
        if len(data['new_password']) < 8:
            raise ValueError('New password must contain 8–128 characters.')
        rate_limit(g.user['username'])
        user = db().execute('SELECT * FROM users WHERE id=?', (g.user['id'],)).fetchone()
        if not hmac.compare_digest(password_hash(data['current_password'], user['salt']), user['password_hash']):
            return error('Current password is incorrect.', 401)
        salt = secrets.token_bytes(16)
        with db():
            db().execute('UPDATE users SET salt=?, password_hash=? WHERE id=?', (salt, password_hash(data['new_password'], salt), user['id']))
            db().execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
        response = jsonify(ok=True)
        set_cookie(response, 'session', '', 0)
        return response

    @app.get('/api/datasets')
    def list_datasets():
        search = request.args.get('search', '').strip()[:120]
        sort = {'updated': 'updated_at DESC', 'created': 'created_at DESC', 'name': 'name COLLATE NOCASE'}.get(request.args.get('sort'), 'updated_at DESC')
        rows = db().execute(f'SELECT * FROM datasets WHERE user_id=? AND (instr(lower(name),lower(?))>0 OR instr(lower(description),lower(?))>0) ORDER BY {sort}', (g.user['id'], search, search)).fetchall()
        return jsonify(datasets=[dataset_json(row, False) for row in rows])

    def input_dataset(data):
        name = text_field(data, 'name', 120, True)
        description = text_field(data, 'description', 2000)
        source = data.get('data')
        if 'text' in data:
            source = {'kind': 'raw', 'columns': ['Value'], 'rows': [[v] for v in parse_text(data['text'])]}
        return name, description, validate_dataset(source)

    @app.post('/api/datasets')
    def create_dataset():
        name, description, data = input_dataset(body())
        timestamp = now()
        with db():
            cursor = db().execute('INSERT INTO datasets(user_id,name,description,data_json,created_at,updated_at) VALUES (?,?,?,?,?,?)', (g.user['id'], name, description, encode(data), timestamp, timestamp))
        return jsonify(dataset=dataset_json(owned_dataset(cursor.lastrowid))), 201

    @app.get('/api/datasets/<int:identifier>')
    def get_dataset(identifier):
        return jsonify(dataset=dataset_json(owned_dataset(identifier)))

    @app.put('/api/datasets/<int:identifier>')
    def edit_dataset(identifier):
        original = owned_dataset(identifier)
        payload = body()
        name, description, data = input_dataset(payload)
        if type(payload.get('revision')) is not int or payload['revision'] != original['revision']:
            return error('This dataset changed in another window. Reopen it before saving.', 409)
        changed = encode(data) != original['data_json']
        with db():
            cursor = db().execute('UPDATE datasets SET name=?,description=?,data_json=?,revision=revision+?,updated_at=? WHERE id=? AND user_id=? AND revision=?', (name, description, encode(data), int(changed), now(), identifier, g.user['id'], payload['revision']))
        if cursor.rowcount != 1:
            return error('This dataset changed in another window. Reopen it before saving.', 409)
        return jsonify(dataset=dataset_json(owned_dataset(identifier)))

    @app.delete('/api/datasets/<int:identifier>')
    def delete_dataset(identifier):
        owned_dataset(identifier)
        with db():
            db().execute('DELETE FROM datasets WHERE id=? AND user_id=?', (identifier, g.user['id']))
        return jsonify(ok=True)

    @app.post('/api/datasets/<int:identifier>/duplicate')
    def duplicate_dataset(identifier):
        row = owned_dataset(identifier)
        timestamp = now()
        with db():
            cursor = db().execute('INSERT INTO datasets(user_id,name,description,data_json,created_at,updated_at) VALUES (?,?,?,?,?,?)', (g.user['id'], row['name'][:110]+' (copy)', row['description'], row['data_json'], timestamp, timestamp))
            db().execute('''INSERT INTO custom_parameters(dataset_id,name,value_json,unit,formula,description,created_at,updated_at)
                SELECT ?,name,value_json,unit,formula,description,?,? FROM custom_parameters WHERE dataset_id=? AND analysis_id IS NULL''', (cursor.lastrowid, timestamp, timestamp, identifier))
        return jsonify(dataset=dataset_json(owned_dataset(cursor.lastrowid))), 201

    @app.post('/api/import/csv')
    def import_csv():
        file = request.files.get('file')
        if not file or not file.filename.lower().endswith('.csv'):
            raise ValueError('Choose a .csv file, at most 2 MB.')
        try:
            content = file.read().decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('CSV files must use UTF-8 encoding.') from exc
        if '\x00' in content:
            raise ValueError('Binary data is not a valid CSV file.')
        delimiter = request.form.get('delimiter', ',')
        if delimiter not in (',', ';', '\t'):
            raise ValueError('Choose comma, semicolon, or tab as the delimiter.')
        reader = csv.reader(io.StringIO(content), delimiter=delimiter, strict=True)
        try:
            rows = []
            for row in reader:
                rows.append(row)
                if len(rows) > MAX_ROWS+1:
                    raise ValueError('CSV files may contain at most 10,000 data rows.')
        except csv.Error as exc:
            raise ValueError('CSV format is invalid.') from exc
        if not rows:
            raise ValueError('The CSV file is empty.')
        has_header = request.form.get('header', 'true') == 'true'
        columns = rows.pop(0) if has_header else [f'Column {i+1}' for i in range(len(rows[0]))]
        data = validate_dataset({'kind': 'raw', 'columns': columns, 'rows': rows})
        return jsonify(data=data, preview_rows=data['rows'][:20], row_count=len(data['rows']))

    def dataset_calculation(payload):
        row = owned_dataset(payload.get('dataset_id'))
        result = calculate(json.loads(row['data_json']), payload.get('settings', {}))
        return row, result

    @app.post('/api/statistics/calculate')
    def calculate_statistics():
        row, result = dataset_calculation(body())
        return jsonify(calculation=result, dataset_revision=row['revision'])

    @app.get('/api/statistics/catalog')
    def metric_catalog():
        return jsonify(metrics={k: dict(zip(('name', 'section', 'formula', 'description'), v)) for k, v in METRICS.items()})

    @app.post('/api/statistics/preview')
    def preview_statistics():
        payload = body()
        source = payload.get('data')
        if 'text' in payload:
            source = {'kind': 'raw', 'columns': ['Value'], 'rows': [[v] for v in parse_text(payload['text'])]}
        return jsonify(calculation=calculate(source, payload.get('settings', {})))

    @app.post('/api/datasets/compare')
    def compare_datasets():
        selections = body().get('selections')
        if not isinstance(selections, list) or not 2 <= len(selections) <= 6 or any(not isinstance(s, dict) for s in selections):
            raise ValueError('Choose two to six datasets and their numerical columns.')
        output = []
        for selection in selections:
            row, result = dataset_calculation(selection)
            output.append({'dataset_id': row['id'], 'name': row['name'], 'revision': row['revision'], 'calculation': result})
        return jsonify(comparisons=output)

    @app.get('/api/analyses')
    def list_analyses():
        rows = db().execute('''SELECT analyses.*,datasets.name AS dataset_name,datasets.revision AS current_revision FROM analyses
            JOIN datasets ON datasets.id=dataset_id WHERE analyses.user_id=? ORDER BY analyses.created_at DESC''', (g.user['id'],)).fetchall()
        return jsonify(analyses=[analysis_json(row, False) for row in rows])

    @app.post('/api/analyses')
    def save_analysis():
        payload = body()
        name = text_field(payload, 'name', 120, True)
        row, result = dataset_calculation(payload)
        if payload.get('dataset_revision') != row['revision']:
            return error('The dataset changed. Recalculate before saving this analysis.', 409)
        snapshot = {'name': row['name'], 'description': row['description'], 'data': json.loads(row['data_json'])}
        with db():
            cursor = db().execute('INSERT INTO analyses(user_id,dataset_id,name,dataset_revision,dataset_snapshot,result_json,created_at) VALUES (?,?,?,?,?,?,?)', (g.user['id'], row['id'], name, row['revision'], encode(snapshot), encode(result), now()))
        return jsonify(analysis=analysis_json(owned_analysis(cursor.lastrowid))), 201

    @app.get('/api/analyses/<int:identifier>')
    def get_analysis(identifier):
        return jsonify(analysis=analysis_json(owned_analysis(identifier)))

    @app.delete('/api/analyses/<int:identifier>')
    def delete_analysis(identifier):
        owned_analysis(identifier)
        with db():
            db().execute('DELETE FROM analyses WHERE id=? AND user_id=?', (identifier, g.user['id']))
        return jsonify(ok=True)

    @app.post('/api/analyses/<int:identifier>/duplicate')
    def duplicate_analysis(identifier):
        row = owned_analysis(identifier)
        timestamp = now()
        with db():
            cursor = db().execute('INSERT INTO analyses(user_id,dataset_id,name,dataset_revision,dataset_snapshot,result_json,created_at) VALUES (?,?,?,?,?,?,?)', (g.user['id'], row['dataset_id'], row['name'][:110]+' (copy)', row['dataset_revision'], row['dataset_snapshot'], row['result_json'], timestamp))
            db().execute('''INSERT INTO custom_parameters(dataset_id,analysis_id,name,value_json,unit,formula,description,created_at,updated_at)
                SELECT dataset_id,?,name,value_json,unit,formula,description,?,? FROM custom_parameters WHERE analysis_id=?''', (cursor.lastrowid, timestamp, timestamp, identifier))
        return jsonify(analysis=analysis_json(owned_analysis(cursor.lastrowid))), 201

    def parameter_values(payload, dataset_id):
        name = text_field(payload, 'name', 120, True)
        value = payload.get('value')
        if isinstance(value, str):
            if not value.strip() or len(value) > 1000:
                raise ValueError('Parameter value must contain 1–1000 characters.')
        else:
            value = number(value)
        analysis_id = payload.get('analysis_id')
        if analysis_id is not None and owned_analysis(analysis_id)['dataset_id'] != dataset_id:
            raise ValueError('The analysis must belong to this dataset.')
        return (analysis_id, name, encode(value), text_field(payload, 'unit', 40), text_field(payload, 'formula', 500), text_field(payload, 'description', 2000))

    @app.get('/api/datasets/<int:identifier>/parameters')
    def get_parameters(identifier):
        return jsonify(parameters=parameters(identifier))

    @app.post('/api/datasets/<int:identifier>/parameters')
    def add_parameter(identifier):
        owned_dataset(identifier)
        values = parameter_values(body(), identifier)
        timestamp = now()
        with db():
            cursor = db().execute('INSERT INTO custom_parameters(dataset_id,analysis_id,name,value_json,unit,formula,description,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)', (identifier, *values, timestamp, timestamp))
            db().execute('UPDATE datasets SET updated_at=? WHERE id=?', (timestamp, identifier))
        return jsonify(parameter=next(p for p in parameters(identifier) if p['id'] == cursor.lastrowid)), 201

    def owned_parameter(identifier):
        row = db().execute('''SELECT custom_parameters.* FROM custom_parameters JOIN datasets ON datasets.id=dataset_id
            WHERE custom_parameters.id=? AND datasets.user_id=?''', (identifier, g.user['id'])).fetchone()
        if not row:
            raise NotFound('Parameter not found.')
        return row

    @app.put('/api/parameters/<int:identifier>')
    def edit_parameter(identifier):
        row = owned_parameter(identifier)
        values = parameter_values(body(), row['dataset_id'])
        with db():
            db().execute('UPDATE custom_parameters SET analysis_id=?,name=?,value_json=?,unit=?,formula=?,description=?,updated_at=? WHERE id=?', (*values, now(), identifier))
        return jsonify(parameter=next(p for p in parameters(row['dataset_id']) if p['id'] == identifier))

    @app.delete('/api/parameters/<int:identifier>')
    def delete_parameter(identifier):
        owned_parameter(identifier)
        with db():
            db().execute('DELETE FROM custom_parameters WHERE id=?', (identifier,))
        return jsonify(ok=True)

    def csv_download(rows, filename):
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        def safe(value):
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                try:
                    number(value)
                    return value  # Numeric signs are safe and must round-trip as numbers.
                except ValueError:
                    pass
                return "'" + value
            return value
        writer.writerows([[safe(v) for v in row] for row in rows])
        return send_file(io.BytesIO(stream.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name=filename)

    @app.get('/api/datasets/<int:identifier>/export')
    def export_dataset(identifier):
        row = owned_dataset(identifier)
        data = json.loads(row['data_json'])
        return csv_download([data['columns'], *data['rows']], f'dataset-{identifier}.csv')

    @app.get('/api/analyses/<int:identifier>/export')
    def export_analysis(identifier):
        analysis = analysis_json(owned_analysis(identifier))
        if request.args.get('format', 'csv') == 'pdf':
            from reports import analysis_pdf
            return send_file(analysis_pdf(analysis, g.user['username']), mimetype='application/pdf', as_attachment=True, download_name=f'analysis-{identifier}.pdf')
        if request.args.get('format', 'csv') != 'csv':
            raise ValueError('Export format must be csv or pdf.')
        calculation = analysis['calculation']
        rows = [['Parameter', 'Value', 'Unit', 'Source', 'Formula', 'Explanation', 'Dataset revision', 'Analysis date']]
        for key, value in calculation['results'].items():
            metric = calculation['catalog'][key]
            rows.append([metric['name'], encode(value), '', 'Calculated', metric['formula'], calculation['issues'].get(key, metric['description']), analysis['dataset_revision'], analysis['created_at']])
        for p in analysis['parameters']:
            rows.append([p['name'], p['value'], p['unit'], 'Manual', p['formula'], p['description'], analysis['dataset_revision'], analysis['created_at']])
        return csv_download(rows, f'analysis-{identifier}.csv')

    return app


def main():
    from waitress import create_server
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    host, port = os.environ.get('HOST', '127.0.0.1'), int(os.environ.get('PORT', '8000'))
    print(f'Statistical workspace running at http://{host}:{port}', flush=True)
    proxy = os.environ.get('TRUSTED_PROXY')
    proxy_options = {'trusted_proxy':proxy, 'trusted_proxy_headers':{'x-forwarded-for','x-forwarded-proto'}} if proxy else {}
    http = create_server(create_app(), host=host, port=port, threads=8, channel_timeout=60,
                         max_request_body_size=2*1024*1024, **proxy_options)
    def stop(signum, frame):
        logging.info('Shutdown requested; waiting for active requests.')
        http.task_dispatcher.shutdown(timeout=25)
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        http.run()
    finally:
        http.task_dispatcher.shutdown(timeout=25)
        http.close()
