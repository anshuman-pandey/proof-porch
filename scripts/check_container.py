"""Disposable Compose acceptance. Requires the locally built image and requirements."""
import http.cookiejar
import os
import re
import secrets
import subprocess
import urllib.parse
import urllib.request
from werkzeug.security import generate_password_hash

project = 'testimonial-test-' + secrets.token_hex(5)
password = secrets.token_urlsafe(24)
env = dict(os.environ, SECRET_KEY=secrets.token_hex(32),
           ADMIN_PASSWORD_HASH=generate_password_hash(password), COOKIE_SECURE='0', HOST_PORT='0')
base = ''


def compose(*args):
    return subprocess.check_output(['docker', 'compose', '-p', project, *args], env=env, text=True)


def start(*args):
    global base
    compose('up', '-d', '--no-build', '--wait', *args)
    base = 'http://' + compose('port', 'app', '8000').strip()


def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(opener, route, fields=None):
    body = urllib.parse.urlencode(fields).encode() if fields is not None else None
    with opener.open(base+route, data=body, timeout=10) as response:
        return response.read().decode()


def csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def login(owner):
    page = request(owner, '/login')
    return request(owner, '/login', {'csrf': csrf(page), 'password': password})


try:
    start()
    assert compose('exec', '-T', 'app', 'id', '-u').strip() != '0'
    owner, guest = client(), client()
    page = login(owner)
    page = request(owner, '/admin', {'csrf': csrf(page), 'name': 'Persistent synthetic collection'})
    board = re.search(r'href="(/admin/[^"/]+)"', page).group(1)
    collect = board.replace('/admin/', '/collect/')
    wall = board.replace('/admin/', '/wall/')
    page = request(guest, collect)
    page = request(guest, collect, {'csrf': csrf(page), 'name': 'Persistence fixture',
                                  'role': 'Synthetic', 'quote': 'A synthetic storage acceptance record.', 'consent': 'yes'})
    removal = re.search(r'href="(/remove/[^"/]+)"', page).group(1)
    page = request(owner, board)
    approve = re.search(r'action="([^"]+/approve)"', page).group(1)
    request(owner, approve, {'csrf': csrf(page)})
    assert 'Persistence fixture' in request(guest, wall)
    start('--force-recreate')
    login(owner)
    assert 'Persistence fixture' in request(guest, wall), 'Approved record lost on recreate'
    assert 'Persistence fixture' in request(owner, board+'/export.csv')
    page = request(guest, removal)
    request(guest, removal, {'csrf': csrf(page)})
    start('--force-recreate')
    assert 'Persistence fixture' not in request(guest, wall), 'Withdrawal did not persist'
    login(owner)
    assert 'Persistence fixture' not in request(owner, board+'/export.csv')
    print('PASS: non-root Compose, named-volume persistence across two recreations, owner login, CSV and preserved withdrawal link.')
finally:
    # Only this randomly named test project and its disposable volume are removed.
    subprocess.run(['docker', 'compose', '-p', project, 'down', '-v'], env=env, check=False)
