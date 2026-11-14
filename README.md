# Testimonial Cabinet

Open-source alternative to Senja and Feedspace for collecting and displaying customer testimonials. Self-hosted, with consent forms, testimonial approval, embeddable walls of love, and CSV export. MIT licensed.

A small, single-owner, self-hosted text testimonial tool. Collect permission, review submissions, publish an embeddable wall, and export your data. Built as the first OSS Everyday project targeting the text collection/publishing workflow in Senja and Feedspace.

Status: developer preview. Public source repository: https://github.com/anshuman-pandey/testimonial-cabinet . No hosted public demo or independent customer-use claims. Hosted HTTPS, cross-site iframe and persistent-volume deployment checks remain pending.

## Local start

Python 3.10+ is required (3.12 tested).

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export ADMIN_PASSWORD_HASH="$(python -c 'from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass("Choose owner password: ")))')"
export COOKIE_SECURE=0  # localhost HTTP only
flask --app 'app:create_app()' run
```

Open http://127.0.0.1:5000. Sign in, create a collection and share its request link. Submissions start private; Publish puts them on the wall. Keep private unpublishes them. Export CSV includes stored consent and Unix timestamps. Delete permanently removes the record. Contributors get a private withdrawal link; it is shown once and must be saved. The owner cannot retrieve that link because only its hash is stored.

## Public deployment

Use HTTPS, retain a stable SECRET_KEY and password hash in your hosting secret store, and leave COOKIE_SECURE at its default 1. Run `gunicorn --bind 127.0.0.1:8000 --workers 1 'app:create_app()'` behind an HTTPS reverse proxy. Set the proxy's canonical Host correctly. Do not enable untrusted forwarded headers. The rate limit uses the socket peer address; behind a proxy it conservatively shares a quota unless trusted proxy configuration is added. Evaluate this before opening a busy public collection.

The Docker image was built and the full browser acceptance flow passed against its non-root Gunicorn process. Mount persistent storage at `/app/data` writable by the image's app user. Never run production on Flask's development server. Access logs should omit withdrawal URL paths because these contain private deletion tokens; the Docker command disables Gunicorn access logs. Configure the proxy accordingly.

SQLite is deliberately single-installation storage. No team accounts, email delivery, video testimonials, automatic review imports, AI copy generation, domain management or high-volume abuse protection. Rate limiting is 10 login/submission attempts per peer per hour. Public collection URLs should be shared intentionally. An embed can be framed by any website; only approved text is served there.

## Backup / restore / upgrade

Stop writes and copy `data/proof.sqlite` plus keep your SECRET_KEY/password hash safely in your secret manager. For a consistent online backup use Python's sqlite3 `Connection.backup` rather than copying an actively written file. Restore to DATABASE (default `data/proof.sqlite`) with appropriate owner permissions and restart. Verify collection, approved wall and owner login after restoration. Future schema changes need reviewed migrations; this initial version only creates missing tables.

To upgrade: back up, stop the server, install the new pinned requirements, run tests, restart and verify. Roll back using both previous code and matching database backup. To uninstall, stop the service and remove the database and secrets; delete retained backups according to your policy. Revocation removes live records, but cannot erase already exported or cached copies.

## Validation

```sh
pip install pytest==9.2.0
python -m pytest -q
```

Integration coverage includes full collection/moderation/export/withdrawal, consent rejection, unauthorized access, CSRF, escaped script input, spreadsheet-formula escaping, rate limits and validation. Screenshots, when present, contain explicitly synthetic content. Backup/restore and dependency audit passed locally; hosted HTTPS, cross-site iframe acceptance and persistent-volume deployment still require validation before public launch.

## Distribution

First audience: small agencies and indie founders collecting written client feedback. Demonstrate create collection → guest permission → publish → embed → withdraw in one recording. Publish a factual workflow comparison and runnable package; no claims of complete Senja/Feedspace parity. Prepare eligible self-hosting listings only after public installation instructions and a stable downloadable release exist. No submissions or promotional posts have been made.

For the disposable browser fixture run `python preview.py` (localhost port 5087; test-only password `preview-only-password`). With Playwright installed, run `node artifacts/browser-acceptance.cjs`. The fixture uses a temporary database removed when it stops. Never deploy preview.py. The Dockerfile deliberately excludes it and the test artifacts.

When building behind a private TLS proxy, supply its trusted CA bundle as a BuildKit secret: `docker build --secret id=pip_ca,src=/path/to/ca-bundle.crt -t testimonial-cabinet .`. The optional certificate is used only during dependency installation and is not baked into the image. TLS verification stays enabled.
