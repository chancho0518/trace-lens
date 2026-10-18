"""TraceLens 설정 로더.

`.env`(또는 환경 변수)에서 DB 접속 정보와 Query Guardrail 값을 읽습니다.
Secret 값은 `SecretStr`로 감싸서 로그/repr에 노출되지 않도록 합니다.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """TraceLens 실행 설정.

    Attributes:
        mongo_uri: MongoDB 접속 URI (Read-only 계정).
        mongo_database: API Transaction Log가 저장된 Database.
        mysql_host: MySQL Host.
        mysql_port: MySQL Port.
        mysql_user: MySQL 계정 (Read-only).
        mysql_password: MySQL 비밀번호.
        mysql_database: eKYC SaaS Transaction Log가 저장된 Database.
        db_query_timeout_ms: DB 접속/쿼리 timeout (ms).
        default_result_limit: 기본 조회 건수.
        max_result_limit: 최대 조회 건수.
        max_query_period_days: 최대 조회 기간 (일).
        app_timezone: 날짜 해석 기준 타임존.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    mongo_uri: SecretStr | None = None
    mongo_database: str | None = None

    mysql_host: str | None = None
    mysql_port: int = 3306
    mysql_user: str | None = None
    mysql_password: SecretStr | None = None
    mysql_database: str | None = None

    db_query_timeout_ms: int = 10_000
    default_result_limit: int = 50
    max_result_limit: int = 500
    max_query_period_days: int = 31
    app_timezone: str = "Asia/Seoul"


@lru_cache
def get_settings() -> Settings:
    """프로세스 단위로 캐시된 Settings를 반환합니다."""
    return Settings()
