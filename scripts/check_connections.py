"""Pritunl VPN 환경에서 MongoDB / MySQL 접속과 Read-only 권한을 확인합니다.

쓰기 시도로 검증하지 않고, 계정 권한 조회로만 확인합니다.

Usage:
    uv run python -m scripts.check_connections
"""

import re
import sys

from infrastructure.config import get_settings
from infrastructure.errors import ConfigError, DBConnectionError
from infrastructure.mongodb.client import ReadOnlyMongo
from infrastructure.mysql.client import ReadOnlyMySQL

MONGO_READ_ROLES = {"read", "readAnyDatabase"}

# 쓰기 없이 읽기/진단만 가능한 MySQL 권한
MYSQL_READ_PRIVILEGES = {
    "SELECT",
    "USAGE",
    "SHOW VIEW",
    "SHOW DATABASES",
    "PROCESS",
    "REPLICATION CLIENT",
}

_GRANT_PRIVS = re.compile(r"^GRANT\s+(.+?)\s+ON\s+", re.I)


def check_mongo() -> bool:
    print("[MongoDB]")
    try:
        with ReadOnlyMongo() as mongo:
            mongo.ping()
            print(f"  접속 OK  (database: {mongo.database_name})")

            collections = mongo.list_collection_names()
            print(f"  Collection {len(collections)}개: {', '.join(collections)}")

            status = mongo.command("connectionStatus")
            roles = status.get("authInfo", {}).get("authenticatedUserRoles", [])
            role_names = {r["role"] for r in roles}
            print(
                "  Roles: "
                + (", ".join(f"{r['role']}@{r['db']}" for r in roles) or "(없음)")
            )
            extra = role_names - MONGO_READ_ROLES
            if extra:
                print(f"  ⚠ Read 외 role 존재: {sorted(extra)} — 계정 권한 확인 필요")
            else:
                print("  Read-only 확인 OK")
            return True
    except ConfigError as e:
        print(f"  ✗ 설정 오류: {e}")
    except DBConnectionError as e:
        print(f"  ✗ 접속 실패: {e}\n  {DBConnectionError.USER_MESSAGE}")
    return False


def check_mysql() -> bool:
    print("[MySQL]")
    try:
        with ReadOnlyMySQL() as mysql:
            mysql.ping()
            print(f"  접속 OK  (database: {mysql.database_name})")

            tables = [next(iter(row.values())) for row in mysql.query("SHOW TABLES")]
            print(f"  Table {len(tables)}개: {', '.join(tables)}")

            grants = [
                next(iter(row.values()))
                for row in mysql.query("SHOW GRANTS FOR CURRENT_USER()")
            ]
            extra: set[str] = set()
            for grant in grants:
                print(f"  {grant}")
                m = _GRANT_PRIVS.match(grant)
                if m:
                    privs = {p.strip().upper() for p in m.group(1).split(",")}
                    extra |= privs - MYSQL_READ_PRIVILEGES
            if extra:
                print(f"  ⚠ Read 외 권한 존재: {sorted(extra)} — 계정 권한 확인 필요")
            else:
                print("  Read-only 확인 OK (Role 부여분은 위 GRANT 목록에서 별도 확인)")
            return True
    except ConfigError as e:
        print(f"  ✗ 설정 오류: {e}")
    except DBConnectionError as e:
        print(f"  ✗ 접속 실패: {e}\n  {DBConnectionError.USER_MESSAGE}")
    return False


def main() -> int:
    settings = get_settings()
    print(f"timeout: {settings.db_query_timeout_ms}ms\n")
    mongo_ok = check_mongo()
    print()
    mysql_ok = check_mysql()
    return 0 if (mongo_ok and mysql_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
