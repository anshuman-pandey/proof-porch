"""Create a private Compose configuration without requiring third-party Python packages."""
import argparse
import getpass
import hashlib
import os
import secrets
from pathlib import Path


def config_text(password, local_http=False):
    if len(password) < 12:
        raise ValueError('Use an owner password of at least 12 characters.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 1_000_000).hex()
    password_hash = f'pbkdf2:sha256:1000000${salt}${digest}'
    return (f"SECRET_KEY='{secrets.token_hex(32)}'\n"
            f"ADMIN_PASSWORD_HASH='{password_hash}'\n"
            f"COOKIE_SECURE={'0' if local_http else '1'}\nHOST_PORT=8000\n")


def write_config(path, contents):
    # Refuse to replace stable secrets; replacing them invalidates existing sessions.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(contents)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-http', action='store_true', help='Allow HTTP cookies for loopback testing only')
    args = parser.parse_args()
    if Path('.env').exists():
        parser.exit(1, '.env already exists; preserving its secrets. Edit it explicitly if needed.\n')
    password = getpass.getpass('Choose owner password (12+ characters): ')
    if password != getpass.getpass('Confirm owner password: '):
        parser.exit(1, 'Passwords did not match. Nothing was written.\n')
    try:
        write_config('.env', config_text(password, args.local_http))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error)+'\n')
    print('Created private .env. Keep it out of Git and preserve it with your backups.')
