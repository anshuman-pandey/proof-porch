"""Single-owner testimonial collection. Run behind HTTPS for public deployment."""
import csv
import json
import hashlib
import hmac
import io
import os
import secrets
import sqlite3
import time
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, abort, g, redirect, render_template, request, session, url_for, Response
from werkzeug.security import check_password_hash

CONSENT = 'I permit this site owner to publish my name, role and testimonial on their website. I can withdraw using my private removal link.'

CONSENT_TRANSLATIONS = json.loads((Path(__file__).parent / 'static' / 'consent.json').read_text())

def create_app(config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY'),
        ADMIN_PASSWORD_HASH=os.environ.get('ADMIN_PASSWORD_HASH'),
        DATABASE=os.environ.get('DATABASE', 'data/proof.sqlite'),
        PUBLIC_BASE_URL=os.environ.get('PUBLIC_BASE_URL', ''),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '1') == '1',
        MAX_CONTENT_LENGTH=32 * 1024)
    if config:
        app.config.update(config)
    if not app.config['SECRET_KEY'] or not app.config['ADMIN_PASSWORD_HASH']:
        raise RuntimeError('Set SECRET_KEY and ADMIN_PASSWORD_HASH; see README.')
    public_base = app.config['PUBLIC_BASE_URL']
    if public_base:
        try:
            parts = urlsplit(public_base)
            valid_port = parts.port  # Reject invalid ports before generating links.
            if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
                    or parts.password is not None or parts.path not in ('', '/')
                    or '?' in public_base or '#' in public_base or '\\' in public_base
                    or parts.netloc.endswith(':') or any(ord(c) <= 32 for c in public_base)):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('PUBLIC_BASE_URL must be an HTTPS origin, e.g. https://testimonials.example.com, without credentials, path, query or fragment.') from None
        app.config['PUBLIC_BASE_URL'] = public_base.rstrip('/')
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(app.config['DATABASE']) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS boards(id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS testimonials(
          id TEXT PRIMARY KEY, board TEXT NOT NULL REFERENCES boards(id),
          name TEXT NOT NULL, role TEXT NOT NULL, quote TEXT NOT NULL,
          consent TEXT NOT NULL, created INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', removal_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts(bucket TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS attempts_bucket ON attempts(bucket,created);
        ''')

    def db():
        if 'db' not in g:
            g.db = sqlite3.connect(app.config['DATABASE'])
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db

    @app.teardown_appcontext
    def close(error):
        connection = g.pop('db', None)
        if connection:
            connection.close()

    def csrf():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        return session['csrf']
    def public_url(endpoint, **values):
        if app.config['PUBLIC_BASE_URL']:
            return app.config['PUBLIC_BASE_URL'] + url_for(endpoint, **values)
        return url_for(endpoint, _external=True, **values)

    app.jinja_env.globals.update(csrf=csrf, consent_text=CONSENT, public_url=public_url)

    @app.before_request
    def verify_csrf():
        if request.method == 'POST':
            supplied = request.form.get('csrf', '')
            if not supplied or not hmac.compare_digest(supplied, session.get('csrf', '')):
                abort(400, 'This form expired. Reload the page and try again.')

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        ancestors = '*' if request.endpoint == 'wall' else "'none'"
        response.headers['Content-Security-Policy'] = f"default-src 'self'; style-src 'self'; script-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors {ancestors}"
        if request.endpoint != 'wall':
            response.headers['X-Frame-Options'] = 'DENY'
        return response

    def owner(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get('owner'):
                return redirect(url_for('login'))
            return fn(*args, **kwargs)
        return wrapped

    def limit(kind, maximum):
        # Do not trust forwarded IP headers; configure a trusted proxy separately.
        digest = hmac.new(app.secret_key.encode(), (request.remote_addr or 'unknown').encode(), hashlib.sha256).hexdigest()
        bucket = kind + ':' + digest
        conn = db()
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('DELETE FROM attempts WHERE created < ?', (int(time.time())-3600,))
        count = conn.execute('SELECT count(*) FROM attempts WHERE bucket=?', (bucket,)).fetchone()[0]
        if count >= maximum:
            conn.rollback()
            abort(429, 'Too many attempts. Please try again in an hour.')
        conn.execute('INSERT INTO attempts VALUES (?,?)', (bucket, int(time.time())))
        conn.commit()

    def field(name, maxlen, required=True):
        value = request.form.get(name, '').strip()
        if (required and not value) or len(value) > maxlen:
            abort(400, f'{name} is required and must be at most {maxlen} characters.' if required else f'{name} must be at most {maxlen} characters.')
        return value

    def board_or_404(board):
        result = db().execute('SELECT * FROM boards WHERE id=?', (board,)).fetchone()
        if not result:
            abort(404)
        return result

    @app.route('/')
    def home():
        return render_template('home.html')

    @app.route('/login', methods=['GET','POST'])
    def login():
        if request.method == 'POST':
            limit('login', 10)
            if not check_password_hash(app.config['ADMIN_PASSWORD_HASH'], request.form.get('password','')):
                return render_template('login.html', error='Incorrect password.'), 401
            session.clear()
            session['owner'] = True
            return redirect(url_for('admin'))
        return render_template('login.html')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('home'))

    @app.route('/admin', methods=['GET','POST'])
    @owner
    def admin():
        if request.method == 'POST':
            db().execute('INSERT INTO boards VALUES (?,?)', (secrets.token_urlsafe(12),field('name',80)))
            db().commit()
            return redirect(url_for('admin'))
        boards = db().execute('SELECT * FROM boards ORDER BY rowid DESC').fetchall()
        return render_template('admin.html', boards=boards)

    @app.route('/admin/<board>')
    @owner
    def moderate(board):
        b = board_or_404(board)
        rows = db().execute('SELECT * FROM testimonials WHERE board=? ORDER BY created DESC', (board,)).fetchall()
        return render_template('moderate.html', board=b, rows=rows)

    @app.post('/admin/<board>/<item>/<action>')
    @owner
    def action(board,item,action):
        board_or_404(board)
        if action not in ('approve','reject','delete'):
            abort(404)
        if action == 'delete' and request.form.get('confirm') != 'yes':
            return render_template('delete.html', board=board, item=item)
        if action == 'delete':
            cur = db().execute('DELETE FROM testimonials WHERE id=? AND board=?',(item,board))
        else:
            cur = db().execute('UPDATE testimonials SET status=? WHERE id=? AND board=?',('approved' if action=='approve' else 'rejected',item,board))
        if not cur.rowcount:
            abort(404)
        db().commit()
        return redirect(url_for('moderate',board=board))

    @app.route('/collect/<board>', methods=['GET','POST'])
    def collect(board):
        b = board_or_404(board)
        if request.method == 'POST':
            limit('submit', 10)
            if request.form.get('consent') != 'yes':
                abort(400,'Publication consent is required. Nothing was saved.')
            name, role, quote = field('name',80), field('role',120,False), field('quote',2000)
            token = secrets.token_urlsafe(32)
            db().execute('INSERT INTO testimonials(id,board,name,role,quote,consent,created,removal_hash) VALUES (?,?,?,?,?,?,?,?)',
                (secrets.token_urlsafe(12),board,name,role,quote,CONSENT_TRANSLATIONS.get(request.form.get('interface_locale'),CONSENT),int(time.time()),hashlib.sha256(token.encode()).hexdigest()))
            db().commit()
            return render_template('thanks.html', token=token), 201
        return render_template('collect.html', board=b)

    @app.route('/remove/<token>', methods=['GET','POST'])
    def remove(token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = db().execute('SELECT id FROM testimonials WHERE removal_hash=?',(digest,)).fetchone()
        if not row:
            abort(404,'This removal link is invalid or the testimonial has already been removed.')
        if request.method == 'POST':
            db().execute('DELETE FROM testimonials WHERE removal_hash=?',(digest,))
            db().commit()
            return render_template('message.html', title='Testimonial removed', message='Your testimonial is no longer stored or displayed by this installation.')
        return render_template('remove.html')

    @app.get('/wall/<board>')
    def wall(board):
        b = board_or_404(board)
        rows = db().execute("SELECT name,role,quote FROM testimonials WHERE board=? AND status='approved' ORDER BY created DESC",(board,)).fetchall()
        return render_template('wall.html',board=b,rows=rows)

    @app.get('/admin/<board>/export.csv')
    @owner
    def export(board):
        board_or_404(board)
        data = io.StringIO()
        writer = csv.writer(data)
        columns = ['name','role','quote','status','consent','created']
        writer.writerow(columns)
        for row in db().execute('SELECT * FROM testimonials WHERE board=?',(board,)):
            # Spreadsheet formula injection includes whitespace-prefixed formulas.
            values = [str(row[c]) for c in columns]
            writer.writerow(["'"+v if v.lstrip().startswith(('=','+','-','@','\t','\r')) else v for v in values])
        return Response(data.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename="testimonials.csv"'})

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(429)
    def error(exc):
        return render_template('message.html',title=f'Request could not be completed ({exc.code})',message=exc.description),exc.code
    return app
