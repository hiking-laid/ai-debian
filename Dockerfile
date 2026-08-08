# Plain Python base — no browser needed in v1 (supermarket scraping is a future version).
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md alembic.ini docker-entrypoint.sh ./
COPY src ./src
COPY migrations ./migrations
COPY db ./db

RUN pip install --no-cache-dir . && chmod +x docker-entrypoint.sh

# Config + inventory files are mounted as a volume (edit without rebuild).
EXPOSE 8080

# Entrypoint applies DB migrations (idempotent) then runs the CMD.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["toddler-dinner", "serve", "--port", "8080"]
