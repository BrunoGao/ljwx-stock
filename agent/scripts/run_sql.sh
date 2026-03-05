#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL 未设置" >&2
  exit 1
fi

if [[ $# -ne 1 ]]; then
  echo "用法: $0 <sql_file>" >&2
  exit 1
fi

SQL_FILE="$1"

if [[ ! -f "$SQL_FILE" ]]; then
  echo "SQL 文件不存在: $SQL_FILE" >&2
  exit 1
fi

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$SQL_FILE"
