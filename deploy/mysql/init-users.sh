#!/bin/bash
(
set -euo pipefail
# Sourced by the MySQL image on first initialization; passwords are deliberately
# URL-safe and SQL-safe, so neither shell nor SQL interpretation is possible.
for name in MYSQL_APP_PASSWORD MYSQL_PROJECTION_PASSWORD MYSQL_READONLY_PASSWORD MYSQL_MIGRATION_PASSWORD; do
    value="${!name:-}"
    if [[ ! "$value" =~ ^[a-zA-Z0-9_-]{16,128}$ ]] || [[ "$value" == replace_* ]]; then
        echo "Configure $name with a new 16-128 character URL-safe password" >&2
        exit 1
    fi
done
if [[ "${MYSQL_ROOT_PASSWORD:-}" == replace_* ]]; then
    echo "Replace MYSQL_ROOT_PASSWORD before initialization" >&2
    exit 1
fi
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=socket --host=localhost --user=root <<EOSQL
CREATE DATABASE IF NOT EXISTS datalens_data CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'datalens_app'@'%' IDENTIFIED WITH mysql_native_password BY '${MYSQL_APP_PASSWORD}';
CREATE USER 'datalens_projection'@'%' IDENTIFIED WITH mysql_native_password BY '${MYSQL_PROJECTION_PASSWORD}';
CREATE USER 'datalens_readonly'@'%' IDENTIFIED WITH mysql_native_password BY '${MYSQL_READONLY_PASSWORD}';
CREATE USER 'datalens_migrate'@'%' IDENTIFIED WITH mysql_native_password BY '${MYSQL_MIGRATION_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE ON datalens_agent.* TO 'datalens_app'@'%';
GRANT CREATE, DROP, INSERT, SELECT ON datalens_data.* TO 'datalens_projection'@'%';
GRANT SELECT ON datalens_data.* TO 'datalens_readonly'@'%';
GRANT ALL PRIVILEGES ON datalens_agent.* TO 'datalens_migrate'@'%';
EOSQL
)
