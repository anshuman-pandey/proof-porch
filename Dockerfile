FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=pip_ca,target=/tmp/pip-ca.pem \
    if [ -f /tmp/pip-ca.pem ]; then export PIP_CERT=/tmp/pip-ca.pem; fi; \
    pip install --no-cache-dir -r requirements.txt && useradd --create-home app && mkdir /app/data && chown app:app /app/data
COPY --chown=app:app app.py .
COPY --chown=app:app templates templates
COPY --chown=app:app static static
USER app
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--access-logfile", "/dev/null", "app:create_app()"]
