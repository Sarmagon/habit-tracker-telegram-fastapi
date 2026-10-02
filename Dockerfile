FROM python:3.12-slim AS dependencies
ENV POETRY_VERSION=2.5.1 POETRY_VIRTUALENVS_IN_PROJECT=true POETRY_NO_INTERACTION=1
WORKDIR /application
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/application/.venv/bin:$PATH"
WORKDIR /application
RUN groupadd --gid 10001 application && useradd --uid 10001 --gid 10001 application
COPY --from=dependencies /application/.venv /application/.venv
COPY --chown=10001:10001 backend backend
COPY --chown=10001:10001 bot bot
COPY --chown=10001:10001 common common
COPY --chown=10001:10001 scripts scripts
COPY --chown=10001:10001 migrations migrations
COPY --chown=10001:10001 alembic.ini ./
USER 10001:10001
CMD ["python", "scripts/start_backend.py"]
