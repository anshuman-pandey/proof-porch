"""Disposable localhost-only browser acceptance fixture; never deploy this file."""
import secrets
import tempfile
from pathlib import Path
from app import create_app
from werkzeug.security import generate_password_hash

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='proof-preview-') as directory:
        create_app({'SECRET_KEY':secrets.token_hex(32),
            'ADMIN_PASSWORD_HASH':generate_password_hash('preview-only-password'),
            'DATABASE':str(Path(directory)/'preview.sqlite'),
            'SESSION_COOKIE_SECURE':False}).run(host='127.0.0.1',port=5087)
