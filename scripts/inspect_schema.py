"""Transaction Collection / Table의 Schema를 샘플링해서 조사합니다.

최신 N건만 조회하고, 결과는 마스킹하여 docs/schema/ (gitignore 대상)에 저장합니다.
코드처럼 보이는 짧은 문자열(상태값, Error Code 등)만 원문을 남기고
그 외 문자열은 길이만 기록합니다.

Usage:
    uv run python -m scripts.inspect_schema --mongo-collection <name>
    uv run python -m scripts.inspect_schema --mysql-table <name> --mysql-order-by <col>
    uv run python -m scripts.inspect_schema --list
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from infrastructure.errors import ConfigError, DBConnectionError
from infrastructure.mongodb.client import ReadOnlyMongo
from infrastructure.mysql.client import ReadOnlyMySQL

OUTPUT_DIR = Path("docs/schema")
MAX_SAMPLE = 20
MAX_EXAMPLES = 3

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
_CODE_LIKE = re.compile(r"^[A-Za-z0-9_\-.:/]{1,24}$")


def mask(value: Any) -> str:
    """분석에 필요한 최소 정보만 남기고 값을 마스킹합니다."""
    if value is None:
        return "null"
    if isinstance(value, bool | int | float | Decimal):
        return repr(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, str):
        if _CODE_LIKE.match(value) and not value.isdigit():
            return repr(value)
        return f"<str len={len(value)}>"
    if isinstance(value, bytes):
        return f"<bytes len={len(value)}>"
    return f"<{type(value).__name__}>"


class FieldStats:
    def __init__(self) -> None:
        self.types: set[str] = set()
        self.count = 0
        self.examples: list[str] = []

    def add(self, value: Any) -> None:
        self.count += 1
        self.types.add(type(value).__name__)
        masked = mask(value)
        if masked not in self.examples and len(self.examples) < MAX_EXAMPLES:
            self.examples.append(masked)


def flatten(doc: Any, prefix: str, stats: dict[str, FieldStats]) -> None:
    """중첩 문서를 `a.b.c` / `a[]` 경로로 펼쳐 통계를 쌓습니다."""
    if isinstance(doc, dict):
        if prefix:
            stats[prefix].add(doc)
        for key, value in doc.items():
            flatten(value, f"{prefix}.{key}" if prefix else str(key), stats)
    elif isinstance(doc, list):
        stats[prefix].add(doc)
        for item in doc[:MAX_EXAMPLES]:
            flatten(item, f"{prefix}[]", stats)
    else:
        stats[prefix].add(doc)


def render_stats(stats: dict[str, FieldStats], total: int) -> list[str]:
    lines = ["| Field | Type | 출현 | 예시 (마스킹) |", "|---|---|---|---|"]
    for path in sorted(stats):
        s = stats[path]
        lines.append(
            f"| `{path}` | {', '.join(sorted(s.types))} | {s.count}/{total} "
            f"| {' / '.join(s.examples)} |"
        )
    return lines


def inspect_mongo(collection: str, n: int) -> str:
    with ReadOnlyMongo() as mongo:
        docs = mongo.find(collection, {}, limit=n, sort=[("_id", -1)])
        indexes = mongo.index_information(collection)
        db_name = mongo.database_name

    stats: dict[str, FieldStats] = defaultdict(FieldStats)
    for doc in docs:
        flatten(doc, "", stats)

    lines = [
        f"# MongoDB `{db_name}.{collection}`",
        "",
        f"최신 {len(docs)}건 샘플 기준 (`_id` 내림차순).",
        "",
        "## Indexes",
        "",
    ]
    lines += [f"- `{name}`: {info.get('key')}" for name, info in indexes.items()]
    lines += ["", "## Fields", ""] + render_stats(stats, len(docs))
    return "\n".join(lines) + "\n"


def inspect_mysql(table: str, order_by: str | None, n: int) -> str:
    for ident in (table, order_by):
        if ident is not None and not _IDENTIFIER.match(ident):
            raise ValueError(f"허용되지 않은 식별자입니다: {ident}")

    with ReadOnlyMySQL() as mysql:
        columns = mysql.query(f"DESCRIBE `{table}`")
        indexes = mysql.query(f"SHOW INDEX FROM `{table}`")
        order = f" ORDER BY `{order_by}` DESC" if order_by else ""
        rows = mysql.query(f"SELECT * FROM `{table}`{order} LIMIT %s", [n])
        db_name = mysql.database_name

    stats: dict[str, FieldStats] = defaultdict(FieldStats)
    for row in rows:
        for key, value in row.items():
            stats[key].add(value)

    lines = [
        f"# MySQL `{db_name}.{table}`",
        "",
        f"{len(rows)}건 샘플 기준"
        + (f" (`{order_by}` 내림차순)." if order_by else "."),
        "",
        "## Columns",
        "",
        "| Field | Type | Null | Key | Default | Extra |",
        "|---|---|---|---|---|---|",
    ]
    for c in columns:
        lines.append(
            f"| `{c['Field']}` | {c['Type']} | {c['Null']} | {c['Key']} "
            f"| {c['Default']} | {c['Extra']} |"
        )
    lines += ["", "## Indexes", ""]
    lines += [
        f"- `{i['Key_name']}` seq={i['Seq_in_index']} col=`{i['Column_name']}`"
        for i in indexes
    ]
    lines += ["", "## Sample Values", ""] + render_stats(stats, len(rows))
    return "\n".join(lines) + "\n"


def list_targets() -> None:
    try:
        with ReadOnlyMongo() as mongo:
            print(f"[MongoDB {mongo.database_name}]")
            for name in mongo.list_collection_names():
                print(f"  {name}")
    except (ConfigError, DBConnectionError) as e:
        print(f"[MongoDB] ✗ {e}")
    try:
        with ReadOnlyMySQL() as mysql:
            print(f"[MySQL {mysql.database_name}]")
            for row in mysql.query("SHOW TABLES"):
                print(f"  {next(iter(row.values()))}")
    except (ConfigError, DBConnectionError) as e:
        print(f"[MySQL] ✗ {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="Collection / Table 목록")
    parser.add_argument("--mongo-collection")
    parser.add_argument("--mysql-table")
    parser.add_argument(
        "--mysql-order-by", help="최신순 정렬 기준 컬럼 (예: created_at)"
    )
    parser.add_argument(
        "-n", type=int, default=10, help=f"샘플 건수 (최대 {MAX_SAMPLE})"
    )
    args = parser.parse_args()

    if args.list:
        list_targets()
        return 0
    if not (args.mongo_collection or args.mysql_table):
        parser.error("--list, --mongo-collection, --mysql-table 중 하나가 필요합니다.")

    n = max(1, min(args.n, MAX_SAMPLE))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if args.mongo_collection:
            out = OUTPUT_DIR / f"mongo_{args.mongo_collection}.md"
            out.write_text(inspect_mongo(args.mongo_collection, n), encoding="utf-8")
            print(f"저장: {out}")
        if args.mysql_table:
            out = OUTPUT_DIR / f"mysql_{args.mysql_table}.md"
            out.write_text(
                inspect_mysql(args.mysql_table, args.mysql_order_by, n),
                encoding="utf-8",
            )
            print(f"저장: {out}")
    except ConfigError as e:
        print(f"✗ 설정 오류: {e}")
        return 1
    except DBConnectionError as e:
        print(f"✗ 접속 실패: {e}\n{DBConnectionError.USER_MESSAGE}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
