# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.13.14-slim-bookworm@sha256:67a1e1f215ccda113cfc024e8639049257e88f273898f595b61476d128d387e8

FROM ${PYTHON_IMAGE} AS dependency-base

ARG UV_VERSION=0.11.29
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
RUN python -m pip install --no-cache-dir "uv==${UV_VERSION}"
COPY pyproject.toml uv.lock ./

FROM dependency-base AS production-dependencies
RUN uv sync --frozen --no-dev --no-install-project

FROM dependency-base AS quality-dependencies
RUN uv sync --frozen --all-groups --no-install-project

FROM ${PYTHON_IMAGE} AS application-base

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --home-dir /home/app app \
    && mkdir -p /app/media /app/staticfiles /tmp/ftl \
    && chown -R app:app /app /tmp/ftl
COPY --chown=app:app . /app

FROM application-base AS runtime
COPY --from=production-dependencies --chown=app:app /opt/venv /opt/venv
RUN DJANGO_SETTINGS_MODULE=config.settings.collectstatic python manage.py collectstatic --noinput \
    && chown -R app:app /app/staticfiles
USER 10001:10001
EXPOSE 8000

FROM application-base AS quality
COPY --from=quality-dependencies --chown=app:app /opt/venv /opt/venv
USER 10001:10001
