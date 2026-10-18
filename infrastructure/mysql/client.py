"""MySQL Read-only Client.

- 세션을 `READ ONLY` 트랜잭션 모드로 엽니다.
- SELECT / SHOW / DESCRIBE / EXPLAIN 문만 실행합니다.
- 반드시 파라미터 바인딩(`%s`)을 사용합니다.
"""

import re
from collections.abc import Sequence
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from infrastructure.config import Settings, get_settings
from infrastructure.errors import ConfigError, DBConnectionError

_ALLOWED_STATEMENT = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b", re.I)


class ReadOnlyMySQL:
    """읽기 전용 MySQL 래퍼."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        if not (
            settings.mysql_host
            and settings.mysql_user
            and settings.mysql_password
            and settings.mysql_database
        ):
            raise ConfigError(
                ".env에 MYSQL_HOST / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE를 설정해주세요."
            )

        timeout_s = max(1, settings.db_query_timeout_ms // 1000)
        try:
            self._conn = pymysql.connect(
                host=settings.mysql_host,
                port=settings.mysql_port,
                user=settings.mysql_user,
                password=settings.mysql_password.get_secret_value(),
                database=settings.mysql_database,
                charset="utf8mb4",
                cursorclass=DictCursor,
                connect_timeout=timeout_s,
                read_timeout=timeout_s,
                autocommit=True,
            )
            with self._conn.cursor() as cur:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
        except pymysql.MySQLError as e:
            raise DBConnectionError(str(e)) from e

        self.database_name = settings.mysql_database

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ReadOnlyMySQL":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def query(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> list[dict[str, Any]]:
        """읽기 전용 쿼리를 실행하고 결과 row 목록을 반환합니다."""
        if ";" in sql.strip().rstrip(";") or not _ALLOWED_STATEMENT.match(sql):
            raise PermissionError("단일 SELECT/SHOW/DESCRIBE/EXPLAIN 문만 허용됩니다.")
        try:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
        except pymysql.OperationalError as e:
            raise DBConnectionError(str(e)) from e

    def ping(self) -> None:
        self.query("SELECT 1")
