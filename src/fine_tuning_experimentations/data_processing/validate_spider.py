"""Validate canonical Spider splits: schema resolution, leakage, SQL correctness."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationReport:
    """Aggregated validation results for one or more canonical splits.

    Attributes:
        errors: Human-readable validation failures found.
        record_count: Total records checked across all splits.
    """

    errors: list[str] = field(default_factory=list)
    record_count: int = 0

    @property
    def ok(self) -> bool:
        """Whether validation found zero errors.

        Returns:
            True if no errors were recorded, else False.
        """
        is_ok = len(self.errors) == 0
        return is_ok


def load_canonical_jsonl(path: Path) -> list[dict]:
    """Load a canonical JSONL split into memory.

    Args:
        path: Path to a canonical train/valid JSONL file.

    Returns:
        Parsed records as plain dicts, in file order.
    """
    lines = path.read_text().splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    return records


def check_db_ids_resolve(records: Iterable[dict], known_db_ids: set[str]) -> list[str]:
    """Check that every record's db_id has schema metadata.

    Args:
        records: Canonical records to check.
        known_db_ids: db_ids present in tables.json.

    Returns:
        One error message per record with an unresolved db_id.
    """
    errors = [
        f"{record.get('id')}: unknown db_id {record.get('db_id')!r}"
        for record in records
        if record.get("db_id") not in known_db_ids
    ]
    return errors


def check_split_leakage(
    train_records: Iterable[dict], valid_records: Iterable[dict]
) -> list[str]:
    """Check that no db_id is shared between train and validation splits.

    Spider is cross-domain; a db_id present in both splits invalidates the
    generalization evaluation.

    Args:
        train_records: Canonical training records.
        valid_records: Canonical validation records.

    Returns:
        One error message per db_id found in both splits.
    """
    train_db_ids = {record["db_id"] for record in train_records}
    valid_db_ids = {record["db_id"] for record in valid_records}
    overlap = train_db_ids & valid_db_ids
    errors = [
        f"db_id {db_id!r} present in both train and validation"
        for db_id in sorted(overlap)
    ]
    return errors


def validate_sql(sql: str, db_path: Path) -> str | None:
    """Check that SQL parses and plans against its SQLite database.

    Uses `EXPLAIN QUERY PLAN` so the statement is validated without
    executing or mutating the database.

    Args:
        sql: Target SQL string to validate.
        db_path: Path to the db_id's SQLite database file.

    Returns:
        None if the SQL is valid, else an error message.
    """
    error: str | None = None
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        connection.execute(f"EXPLAIN QUERY PLAN {sql}")
    except sqlite3.Error as exc:
        error = str(exc)
    finally:
        connection.close()
    return error


def validate_split(
    records: Sequence[dict],
    known_db_ids: set[str],
    database_root: Path | None = None,
) -> list[str]:
    """Validate one split's db_id resolution and, optionally, SQL correctness.

    Args:
        records: Canonical records for one split.
        known_db_ids: db_ids present in tables.json.
        database_root: Root directory of per-db_id SQLite databases. SQL
            validation is skipped if this is None.

    Returns:
        Combined list of validation error messages.
    """
    errors = check_db_ids_resolve(records, known_db_ids)
    if database_root is not None:
        for record in records:
            db_path = database_root / record["db_id"] / f"{record['db_id']}.sqlite"
            if db_path.exists():
                sql_error = validate_sql(record["sql"], db_path)
                if sql_error is not None:
                    errors.append(f"{record['id']}: {sql_error}")
    return errors


def validate_canonical_dataset(
    train_path: Path,
    valid_path: Path,
    tables_path: Path,
    database_root: Path | None = None,
) -> ValidationReport:
    """Run full validation across train and validation canonical splits.

    Args:
        train_path: Path to canonical train.jsonl.
        valid_path: Path to canonical valid.jsonl.
        tables_path: Path to raw Spider tables.json.
        database_root: Root directory of per-db_id SQLite databases, used for
            SQL execution-plan validation. Skipped if None.

    Returns:
        A ValidationReport aggregating all findings.
    """
    train_records = load_canonical_jsonl(train_path)
    valid_records = load_canonical_jsonl(valid_path)
    known_db_ids = {entry["db_id"] for entry in json.loads(tables_path.read_text())}

    errors: list[str] = []
    errors.extend(validate_split(train_records, known_db_ids, database_root))
    errors.extend(validate_split(valid_records, known_db_ids, database_root))
    errors.extend(check_split_leakage(train_records, valid_records))

    report = ValidationReport(
        errors=errors, record_count=len(train_records) + len(valid_records)
    )
    return report
