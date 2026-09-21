"""Convert raw Spider data into backend-neutral canonical JSONL records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Deferred import: config.schema imports SYSTEM_PROMPT from this module,
    # so importing its types at module load time would create a cycle.
    from fine_tuning_experimentations.config.schema import (
        PrepareSpiderConfig,
        SplitConfig,
    )

SYSTEM_PROMPT = (
    "You are a text-to-SQL assistant. Given a database schema and a question, "
    "generate only the SQLite SQL query needed to answer the question. "
    "Do not include explanations, comments, or markdown formatting."
)

_SQL_TYPE_MAP: dict[str, str] = {
    "text": "TEXT",
    "number": "NUMERIC",
    "time": "TEXT",
    "boolean": "BOOLEAN",
    "others": "TEXT",
}


@dataclass(frozen=True)
class CanonicalRecord:
    """One backend-neutral Spider training example.

    Attributes:
        id: Stable identifier, formatted as "<source-file>:<index>".
        db_id: Spider database identifier.
        schema: Serialized `CREATE TABLE` statements for db_id.
        question: Natural-language question.
        sql: Target SQL string, taken from Spider's `query` field.
        messages: Chat-formatted system/user/assistant turns.
        format_version: Canonical record schema version.
    """

    id: str
    db_id: str
    schema: str
    question: str
    sql: str
    messages: list[dict[str, str]]
    format_version: str

    def to_dict(self) -> dict[str, Any]:
        """Convert the record to a plain dict for JSONL serialization.

        Returns:
            Field values as a dict, in declaration order.
        """
        as_dict = {
            "id": self.id,
            "db_id": self.db_id,
            "schema": self.schema,
            "question": self.question,
            "sql": self.sql,
            "messages": self.messages,
            "format_version": self.format_version,
        }
        return as_dict


def serialize_schema(table_meta: dict[str, Any]) -> str:
    """Serialize one Spider `tables.json` entry into `CREATE TABLE` statements.

    Preserves original table and column identifiers because generated SQL
    must match the underlying SQLite database, not the humanized names in
    `column_names`/`table_names`.

    Args:
        table_meta: One entry from tables.json, keyed by table_names_original,
            column_names_original, column_types, primary_keys, and
            foreign_keys.

    Returns:
        Newline-joined `CREATE TABLE` statements, one per table.
    """
    table_names = table_meta["table_names_original"]
    columns = table_meta["column_names_original"]
    column_types = table_meta["column_types"]
    primary_keys = set(table_meta["primary_keys"])
    foreign_keys = dict(table_meta["foreign_keys"])

    columns_by_table: dict[int, list[int]] = {}
    for col_idx, (table_idx, _name) in enumerate(columns):
        if table_idx >= 0:
            columns_by_table.setdefault(table_idx, []).append(col_idx)

    statements = []
    for table_idx, table_name in enumerate(table_names):
        column_lines = []
        for col_idx in columns_by_table.get(table_idx, []):
            _, col_name = columns[col_idx]
            sql_type = _SQL_TYPE_MAP.get(column_types[col_idx], "TEXT")
            line = f'  "{col_name}" {sql_type}'
            if col_idx in primary_keys:
                line += " PRIMARY KEY"
            if col_idx in foreign_keys:
                ref_table_idx, ref_col_name = columns[foreign_keys[col_idx]]
                ref_table_name = table_names[ref_table_idx]
                line += f' REFERENCES "{ref_table_name}"("{ref_col_name}")'
            column_lines.append(line)
        statement = (
            f'CREATE TABLE "{table_name}" (\n' + ",\n".join(column_lines) + "\n);"
        )
        statements.append(statement)

    schema_text = "\n".join(statements)
    return schema_text


def load_tables(tables_path: Path) -> dict[str, str]:
    """Load and serialize schema text for every db_id in `tables.json`.

    Args:
        tables_path: Path to Spider's tables.json.

    Returns:
        Mapping of db_id to serialized `CREATE TABLE` schema text.
    """
    raw_tables = json.loads(tables_path.read_text())
    schema_by_db = {entry["db_id"]: serialize_schema(entry) for entry in raw_tables}
    return schema_by_db


def load_raw_examples(
    raw_dir: Path, source_files: Sequence[str]
) -> Iterator[tuple[str, int, dict[str, Any]]]:
    """Yield raw Spider examples from one or more source JSON files.

    Args:
        raw_dir: Directory containing raw Spider JSON files.
        source_files: File names, relative to raw_dir, read in order.

    Yields:
        Tuples of (source file name, index within that file, raw example).
    """
    for source_name in source_files:
        examples = json.loads((raw_dir / source_name).read_text())
        for index, example in enumerate(examples):
            yield source_name, index, example


def build_messages(
    system_prompt: str, schema_text: str, question: str, sql: str
) -> list[dict[str, str]]:
    """Build a chat-formatted message list for one canonical record.

    Args:
        system_prompt: Shared system instruction for SQL generation.
        schema_text: Serialized `CREATE TABLE` statements for the target db.
        question: Natural-language question.
        sql: Target SQL, used as the assistant turn.

    Returns:
        Role/content message dicts in order: system, user, assistant.
    """
    user_content = f"Database schema:\n{schema_text}\n\nQuestion:\n{question}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": sql},
    ]
    return messages


def build_record(
    source_name: str,
    index: int,
    example: dict[str, Any],
    schema_by_db: dict[str, str],
    system_prompt: str,
    format_version: str,
) -> CanonicalRecord:
    """Build one canonical record from a raw Spider example.

    Args:
        source_name: Raw source file name, used for the record id prefix.
        index: Index of the example within source_name.
        example: Raw Spider example with db_id, question, and query.
        schema_by_db: Serialized schema text keyed by db_id.
        system_prompt: Shared system instruction for SQL generation.
        format_version: Canonical record schema version stamped on the record.

    Returns:
        The corresponding CanonicalRecord.

    Raises:
        KeyError: If the example's db_id is missing from schema_by_db.
    """
    db_id = example["db_id"]
    if db_id not in schema_by_db:
        raise KeyError(f"Unknown db_id {db_id!r} in {source_name}[{index}]")

    schema_text = schema_by_db[db_id]
    question = example["question"]
    sql = example["query"]
    record = CanonicalRecord(
        id=f"{source_name}:{index}",
        db_id=db_id,
        schema=schema_text,
        question=question,
        sql=sql,
        messages=build_messages(system_prompt, schema_text, question, sql),
        format_version=format_version,
    )
    return record


def build_split(
    split: "SplitConfig",
    raw_dir: Path,
    schema_by_db: dict[str, str],
    system_prompt: str,
    format_version: str,
) -> list[CanonicalRecord]:
    """Build all canonical records for one configured split.

    Args:
        split: Split configuration naming its raw source files.
        raw_dir: Directory containing raw Spider JSON files.
        schema_by_db: Serialized schema text keyed by db_id.
        system_prompt: Shared system instruction for SQL generation.
        format_version: Canonical record schema version stamped on records.

    Returns:
        Canonical records for the split, in source-file then in-file order.
    """
    records = [
        build_record(
            source_name, index, example, schema_by_db, system_prompt, format_version
        )
        for source_name, index, example in load_raw_examples(raw_dir, split.sources)
    ]
    return records


def compute_dataset_hash(records: Sequence[CanonicalRecord]) -> str:
    """Compute a deterministic content hash over canonical records.

    Args:
        records: Canonical records to hash, in a stable order.

    Returns:
        Hex-encoded SHA-256 digest of the records' serialized content.
    """
    digest = hashlib.sha256()
    for record in records:
        digest.update(json.dumps(record.to_dict(), sort_keys=True).encode("utf-8"))
    dataset_hash = digest.hexdigest()
    return dataset_hash


def write_jsonl(records: Sequence[CanonicalRecord], output_path: Path) -> None:
    """Write canonical records as newline-delimited JSON.

    Args:
        records: Canonical records to serialize, one per line.
        output_path: Destination file; parent directories are created.

    Returns:
        None.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = (json.dumps(record.to_dict(), ensure_ascii=False) for record in records)
    output_path.write_text("\n".join(lines) + "\n")
    return None


def write_manifest(
    manifest_path: Path,
    split_records: dict[str, Sequence[CanonicalRecord]],
    template_version: str,
) -> None:
    """Write a manifest describing generated canonical splits.

    Args:
        manifest_path: Destination path for manifest.json.
        split_records: Canonical records keyed by split name.
        template_version: Prompt/format version stamped on the manifest.

    Returns:
        None.
    """
    manifest = {
        "format_version": template_version,
        "template_version": template_version,
        "splits": {
            name: {
                "count": len(records),
                "dataset_hash": compute_dataset_hash(records),
            }
            for name, records in split_records.items()
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return None


def prepare_spider(cfg: "PrepareSpiderConfig") -> dict[str, list[CanonicalRecord]]:
    """Build and write canonical Spider JSONL splits from raw data.

    Args:
        cfg: Prepare-Spider configuration naming paths, prompt, and splits.

    Returns:
        Canonical records actually written, keyed by split name.
    """
    raw_dir = Path(cfg.paths.raw_dir)
    canonical_dir = Path(cfg.paths.canonical_dir)
    schema_by_db = load_tables(raw_dir / cfg.tables_file)

    split_records = {
        split.name: build_split(
            split,
            raw_dir,
            schema_by_db,
            cfg.prompt.system_prompt,
            cfg.prompt.template_version,
        )
        for split in cfg.splits
    }
    for name, records in split_records.items():
        write_jsonl(records, canonical_dir / f"{name}.jsonl")
    if cfg.write_manifest:
        write_manifest(
            canonical_dir / "manifest.json",
            split_records,
            cfg.prompt.template_version,
        )
    return split_records