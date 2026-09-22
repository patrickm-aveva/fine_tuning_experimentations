"""Framework-agnostic scoring and example-selection for base-vs-fine-tuned comparison."""

from __future__ import annotations

import random
import re
import sqlite3
from pathlib import Path

from fine_tuning_experimentations.data_processing.validate_spider import validate_sql
from fine_tuning_experimentations.evaluation.predictor import Predictor


def select_examples(records: list[dict], mode: str, size: int, seed: int) -> list[dict]:
    """Choose canonical records to run through the comparison.

    Args:
        records: All canonical validation records.
        mode: "random" for a seeded sample, or "all" for every record.
        size: Number of examples to sample when mode is "random".
        seed: Random seed for reproducible sampling.

    Returns:
        The selected subset of records, in a stable order.
    """
    if mode == "all":
        selected = list(records)
    else:
        rng = random.Random(seed)
        selected = rng.sample(records, min(size, len(records)))
    return selected


def normalize_sql(sql: str) -> str:
    """Normalize SQL text for a lenient string-match comparison.

    Args:
        sql: Raw SQL text.

    Returns:
        Lowercased SQL with collapsed whitespace and no trailing semicolon.
    """
    collapsed = re.sub(r"\s+", " ", sql.strip().lower()).rstrip(";").strip()
    return collapsed


def execution_match(predicted_sql: str, gold_sql: str, db_path: Path) -> bool | None:
    """Check whether predicted and gold SQL return the same result set.

    Args:
        predicted_sql: Model-generated SQL.
        gold_sql: Spider's gold SQL for the same question.
        db_path: Path to the db_id's SQLite database file.

    Returns:
        True/False if both queries executed, None if either raised an error
        or the database file does not exist.
    """
    result: bool | None
    if not db_path.exists():
        result = None
    else:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA busy_timeout = 2000")
            predicted_rows = set(connection.execute(predicted_sql).fetchall())
            gold_rows = set(connection.execute(gold_sql).fetchall())
            result = predicted_rows == gold_rows
        except sqlite3.Error:
            result = None
        finally:
            connection.close()
    return result


def build_comparison_row(record: dict, predictor: Predictor, database_root: Path) -> dict:
    """Generate and score base and fine-tuned predictions for one record.

    Args:
        record: One canonical validation record.
        predictor: Backend-specific Predictor supplying both model outputs.
        database_root: Root directory of per-db_id SQLite databases.

    Returns:
        A row dict with predictions and correctness signals for both models.
    """
    gold_sql = record["sql"]
    db_path = database_root / record["db_id"] / f"{record['db_id']}.sqlite"

    base_sql = predictor.generate_base(record["messages"])
    finetuned_sql = predictor.generate_finetuned(record["messages"])

    row = {
        "id": record["id"],
        "db_id": record["db_id"],
        "question": record["question"],
        "gold_sql": gold_sql,
        "base_sql": base_sql,
        "base_parses": validate_sql(base_sql, db_path) is None,
        "base_string_match": normalize_sql(base_sql) == normalize_sql(gold_sql),
        "base_exec_match": execution_match(base_sql, gold_sql, db_path),
        "finetuned_sql": finetuned_sql,
        "finetuned_parses": validate_sql(finetuned_sql, db_path) is None,
        "finetuned_string_match": normalize_sql(finetuned_sql) == normalize_sql(gold_sql),
        "finetuned_exec_match": execution_match(finetuned_sql, gold_sql, db_path),
    }
    return row


def build_comparison_table(
    records: list[dict], predictor: Predictor, database_root: Path
) -> list[dict]:
    """Build comparison rows for a set of already-selected records.

    Args:
        records: Canonical records selected for this comparison run.
        predictor: Backend-specific Predictor supplying both model outputs.
        database_root: Root directory of per-db_id SQLite databases.

    Returns:
        One row dict per record, in the same order.
    """
    rows = [build_comparison_row(record, predictor, database_root) for record in records]
    return rows