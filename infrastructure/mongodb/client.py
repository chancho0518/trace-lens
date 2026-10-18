"""MongoDB Read-only Client.

DB 계정이 Read-only이더라도, TraceLens 코드 레벨에서도 읽기 연산만 노출합니다.
(find / find_one / aggregate / count_documents / list_collection_names)
"""

from collections.abc import Mapping, Sequence
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from infrastructure.config import Settings, get_settings
from infrastructure.errors import ConfigError, DBConnectionError

# 결과를 Collection에 쓰는 aggregate stage는 금지
_FORBIDDEN_STAGES = {"$out", "$merge"}

# command()로 허용하는 진단용 명령
_ALLOWED_COMMANDS = {"ping", "connectionStatus", "buildInfo", "collStats", "dbStats"}


class ReadOnlyMongo:
    """읽기 전용 MongoDB 래퍼."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        if settings.mongo_uri is None or not settings.mongo_database:
            raise ConfigError(".env에 MONGO_URI / MONGO_DATABASE를 설정해주세요.")

        timeout = settings.db_query_timeout_ms
        self._client: MongoClient = MongoClient(
            settings.mongo_uri.get_secret_value(),
            serverSelectionTimeoutMS=timeout,
            connectTimeoutMS=timeout,
            socketTimeoutMS=timeout,
            tz_aware=True,
        )
        self._db = self._client[settings.mongo_database]
        self._max_time_ms = timeout

    @property
    def database_name(self) -> str:
        return self._db.name

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ReadOnlyMongo":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ----- 진단 -----

    def command(self, name: str, **kwargs: Any) -> dict[str, Any]:
        """허용된 진단 명령만 실행합니다."""
        if name not in _ALLOWED_COMMANDS:
            raise PermissionError(f"허용되지 않은 MongoDB 명령입니다: {name}")
        try:
            return self._db.command(name, **kwargs)
        except PyMongoError as e:
            raise DBConnectionError(str(e)) from e

    def ping(self) -> None:
        self.command("ping")

    def list_collection_names(self) -> list[str]:
        try:
            return sorted(self._db.list_collection_names())
        except PyMongoError as e:
            raise DBConnectionError(str(e)) from e

    def index_information(self, collection: str) -> dict[str, Any]:
        try:
            return self._db[collection].index_information()
        except PyMongoError as e:
            raise DBConnectionError(str(e)) from e

    # ----- 조회 -----

    def find_one(
        self, collection: str, filter: Mapping[str, Any], **kwargs: Any
    ) -> dict[str, Any] | None:
        try:
            return self._db[collection].find_one(
                filter, max_time_ms=self._max_time_ms, **kwargs
            )
        except PyMongoError as e:
            raise DBConnectionError(str(e)) from e

    def find(
        self,
        collection: str,
        filter: Mapping[str, Any],
        *,
        limit: int,
        sort: Sequence[tuple[str, int]] | None = None,
        projection: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """limit 필수 — 무제한 조회를 막습니다."""
        if limit <= 0:
            raise ValueError("limit은 1 이상이어야 합니다.")
        try:
            cursor = self._db[collection].find(
                filter, projection, max_time_ms=self._max_time_ms
            )
            if sort:
                cursor = cursor.sort(list(sort))
            return list(cursor.limit(limit))
        except PyMongoError as e:
            raise DBConnectionError(str(e)) from e

    def count_documents(self, collection: str, filter: Mapping[str, Any]) -> int:
        try:
            return self._db[collection].count_documents(
                filter, maxTimeMS=self._max_time_ms
            )
        except PyMongoError as e:
            raise DBConnectionError(str(e)) from e

    def aggregate(
        self, collection: str, pipeline: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        for stage in pipeline:
            forbidden = _FORBIDDEN_STAGES & set(stage)
            if forbidden:
                raise PermissionError(f"쓰기 stage는 허용되지 않습니다: {forbidden}")
        try:
            return list(
                self._db[collection].aggregate(
                    list(pipeline), maxTimeMS=self._max_time_ms
                )
            )
        except PyMongoError as e:
            raise DBConnectionError(str(e)) from e
