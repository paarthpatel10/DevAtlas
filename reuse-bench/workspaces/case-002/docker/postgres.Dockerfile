# ── PostgreSQL Service Dockerfile ──────────────────────────────────────────────
# Extends the official PostgreSQL 16 image with the sample analytics dataset.

FROM postgres:16-alpine

# Copy the initialization SQL script
# Scripts in /docker-entrypoint-initdb.d/ run automatically on first container start
COPY app/database/sample_data.sql /docker-entrypoint-initdb.d/01_sample_data.sql

# Set default environment variables (can be overridden in docker-compose)
ENV POSTGRES_DB=analytics_db \
    POSTGRES_USER=assistant \
    POSTGRES_PASSWORD=assistant_password

# Expose PostgreSQL port
EXPOSE 5432
