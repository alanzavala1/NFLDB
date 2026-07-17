"""Isolated text-to-SQL comparison arm for the /ask gold-set experiment.

This module lives under tests by design: product code must never import or wire
it into an API route. The agent gets the real DuckDB schema, emits one guarded
read-only query, receives one repair chance, and turns the bounded rows into an
answer that the typed-tool gold graders can judge unchanged.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import anthropic
import duckdb
from dotenv import load_dotenv


_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(_API_DIR, ".env"))

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
NOT_ANSWERABLE = "NOT_ANSWERABLE"
# Historical JSONL rows without a harness_version field are v1.
HARNESS_VERSION = 2
_MAX_ROWS = 50
_INTERNAL_TABLE_PREFIXES = ("duckdb_", "sqlite_", "_")
_FORBIDDEN_SQL = re.compile(
    r"\b(?:ALTER|ATTACH|CALL|COPY|CREATE|DELETE|DETACH|DROP|EXPORT|IMPORT|"
    r"INSERT|INSTALL|LOAD|MERGE|PRAGMA|SET|TRUNCATE|UPDATE|VACUUM)\b",
    re.IGNORECASE,
)


class SQLGuardError(ValueError):
    """The generated statement is outside the read-only SELECT contract."""


def _extract_sql(text: str) -> str:
    """Return the first fenced block's contents, or stripped unfenced text."""
    stripped = text.strip()
    fence_start = stripped.find("```")
    if fence_start < 0:
        return stripped
    content_start = fence_start + 3
    fence_end = stripped.find("```", content_start)
    if fence_end < 0:
        return stripped

    content = stripped[content_start:fence_end]
    first_line, newline, remainder = content.partition("\n")
    if newline and (
        not first_line.strip()
        or re.fullmatch(r"[A-Za-z0-9_.+-]+", first_line.strip())
    ):
        content = remainder
    return content.strip()


def _strip_sql_comments(sql: str) -> str:
    """Remove line/block comments while preserving quoted string contents."""
    out: list[str] = []
    i = 0
    quote = ""
    while i < len(sql):
        char = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if quote:
            out.append(char)
            if char == quote:
                if nxt == quote:
                    out.append(nxt)
                    i += 2
                    continue
                quote = ""
            i += 1
            continue
        if char in ("'", '"'):
            quote = char
            out.append(char)
            i += 1
            continue
        if char == "-" and nxt == "-":
            i += 2
            while i < len(sql) and sql[i] not in "\r\n":
                i += 1
            out.append("\n")
            continue
        if char == "/" and nxt == "*":
            end = sql.find("*/", i + 2)
            if end < 0:
                raise SQLGuardError("unterminated SQL block comment")
            out.append(" ")
            i = end + 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


def guard_select(sql: str) -> str:
    """Return one normalized SELECT/WITH statement or reject it before DuckDB."""
    if not isinstance(sql, str):
        raise SQLGuardError("model output was not text")
    statement = _strip_sql_comments(sql).strip()
    if not statement:
        raise SQLGuardError("model returned an empty statement")
    if ";" in statement:
        if not statement.endswith(";") or ";" in statement[:-1]:
            raise SQLGuardError("multiple statements are not allowed")
        statement = statement[:-1].rstrip()
    if not re.match(r"^(?:SELECT|WITH)\b", statement, re.IGNORECASE):
        raise SQLGuardError("statement must start with SELECT or WITH")
    forbidden = _FORBIDDEN_SQL.search(statement)
    if forbidden:
        raise SQLGuardError(f"forbidden SQL keyword: {forbidden.group(0).upper()}")
    if statement[:4].upper() == "WITH" and not re.search(
        r"\bSELECT\b", statement, re.IGNORECASE
    ):
        raise SQLGuardError("WITH statement must contain SELECT")
    return statement


def connect_read_only(
    db_path: str,
    connect: Callable[..., Any] = duckdb.connect,
) -> Any:
    """Open the comparison database with DuckDB's enforced read-only mode."""
    return connect(db_path, read_only=True)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _split_vocabulary_notes(conn: Any) -> list[str]:
    """Compact split contracts derived from the three materialized tables."""
    player_dims: dict[str, set[str]] = {}
    team_dims: dict[str, set[str]] = {}
    defense_dims: set[str] = set()
    values: dict[str, set[str]] = {}

    player_rows = conn.execute(
        "SELECT DISTINCT category, split_dim, split_value FROM player_splits"
    ).fetchall()
    for category, dimension, value in player_rows:
        player_dims.setdefault(category, set()).add(dimension)
        values.setdefault(dimension, set()).add(value)

    defense_rows = conn.execute(
        "SELECT DISTINCT split_dim, split_value FROM defense_splits"
    ).fetchall()
    for dimension, value in defense_rows:
        defense_dims.add(dimension)
        values.setdefault(dimension, set()).add(value)

    team_rows = conn.execute(
        "SELECT DISTINCT side, split_dim, split_value FROM team_splits"
    ).fetchall()
    for side, dimension, value in team_rows:
        team_dims.setdefault(side, set()).add(dimension)
        values.setdefault(dimension, set()).add(value)

    def grouped(mapping: dict[str, set[str]]) -> str:
        return "; ".join(
            f"{key}=[{','.join(sorted(items))}]"
            for key, items in sorted(mapping.items())
        )

    value_text = "; ".join(
        f"{dimension}=[{','.join(sorted(dimension_values))}]"
        for dimension, dimension_values in sorted(values.items())
    )
    return [
        f"player_splits category values=[{','.join(sorted(player_dims))}]; "
        f"split_dim by category: {grouped(player_dims)}.",
        f"defense_splits split_dim values=[{','.join(sorted(defense_dims))}].",
        f"team_splits side values=[{','.join(sorted(team_dims))}]; "
        f"split_dim by side: {grouped(team_dims)}.",
        f"Split split_value vocabulary by split_dim: {value_text}.",
    ]


def build_schema_prompt(conn: Any) -> str:
    """Describe every user table once for the run's cacheable system prompt."""
    table_rows = conn.execute("SHOW TABLES").fetchall()
    tables = sorted(
        row[0] for row in table_rows
        if row and not str(row[0]).lower().startswith(_INTERNAL_TABLE_PREFIXES)
    )
    schema_lines: list[str] = []
    for table in tables:
        columns = conn.execute(f"DESCRIBE {_quote_identifier(table)}").fetchall()
        rendered = ", ".join(f"{row[0]} {row[1]}" for row in columns)
        schema_lines.append(f"- {table}({rendered})")

    season_ranges = conn.execute(
        """
        SELECT 'plays', MIN(season), MAX(season) FROM plays
        UNION ALL SELECT 'schedules', MIN(season), MAX(season) FROM schedules
        UNION ALL SELECT 'player_game_stats', MIN(season), MAX(season)
          FROM player_game_stats
        """
    ).fetchall()
    coverage = "; ".join(
        f"{table}={int(first)}-{int(last)}" for table, first, last in season_ranges
    )
    play_types = ",".join(
        row[0] for row in conn.execute(
            "SELECT DISTINCT season_type FROM plays ORDER BY season_type"
        ).fetchall()
    )
    schedule_types = ",".join(
        row[0] for row in conn.execute(
            "SELECT DISTINCT game_type FROM schedules ORDER BY game_type"
        ).fetchall()
    )
    pgs_types = ",".join(
        row[0] for row in conn.execute(
            """
            SELECT DISTINCT schedules.game_type
            FROM player_game_stats JOIN schedules USING (game_id)
            ORDER BY schedules.game_type
            """
        ).fetchall()
    )

    ngs_ranges = []
    for table in ("ngs_passing", "ngs_receiving", "ngs_rushing"):
        first, last = conn.execute(
            f"SELECT MIN(season), MAX(season) FROM {_quote_identifier(table)}"
        ).fetchone()
        ngs_ranges.append(f"{table}={int(first)}-{int(last)}")
    ftn_first, ftn_last = conn.execute(
        "SELECT MIN(season), MAX(season) FROM ftn_charting"
    ).fetchone()

    from config import TEAM_NAMES

    team_codes = [
        row[0] for row in conn.execute(
            """
            SELECT home_team AS team FROM schedules
            UNION SELECT away_team FROM schedules
            ORDER BY team
            """
        ).fetchall()
    ]
    team_names = dict(TEAM_NAMES)
    team_names["JAX"] = team_names["JAC"]
    teams = ", ".join(f"{abbr}={team_names[abbr]}" for abbr in team_codes)
    split_notes = "\n".join(f"- {note}" for note in _split_vocabulary_notes(conn))
    schema = "\n".join(schema_lines)
    return f"""You are the SQL generation stage of an NFL statistics baseline.
Return exactly one read-only DuckDB SELECT statement (a WITH...SELECT is also
allowed), with no Markdown or explanation. Return exactly {NOT_ANSWERABLE} only
when the request is off-topic or the schema/coverage cannot answer it. Use only
the schema below; never guess a table or column. Prefer reconciled aggregate
tables over re-deriving official totals from plays when one exists.

SCHEMA:
{schema}

DATA NOTES:
- Season coverage: {coverage}.
- plays.season_type values=[{play_types}]; schedules.game_type values=[{schedule_types}].
- player_game_stats contains both regular-season and playoff rows (schedule
  game types=[{pgs_types}]) but has no season-type or game-type column. For
  official regular-season totals, JOIN schedules USING (game_id) and filter
  schedules.game_type='REG'.
- Resolve player names to ids with rosters(player_name,player_id), with
  id_map(name,gsis_id) as a fallback. Filter player_game_stats.player_id and
  plays role id columns (passer_player_id,receiver_player_id,rusher_player_id,
  etc.); plays.*_player_name labels can be abbreviated and non-unique.
- NGS coverage: {'; '.join(ngs_ranges)}. ngs_* rows are player/season_type/week
  AGGREGATES, not plays; week=0 is a REG season aggregate. Do not sum them as
  plays or combine week=0 with weekly rows.
- ftn_charting covers {int(ftn_first)}-{int(ftn_last)} and has one row per charted
  play; join plays USING (game_id,play_id).
{split_notes}
- Team abbreviations: {teams}
"""


def _conversation_messages(question: str, history: list[dict] | None) -> list[dict]:
    """Match /ask's bounded text-only user/assistant transcript shape."""
    raw = [*(history or []), {"role": "user", "content": question}]
    messages: list[dict] = []
    for message in raw:
        if isinstance(message, dict):
            role, content = message.get("role"), message.get("content")
        else:
            role = getattr(message, "role", None)
            content = getattr(message, "content", None)
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content or (not messages and role == "assistant"):
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n\n" + content
        else:
            messages.append({"role": role, "content": content})
    return messages


def _response_text(response: Any) -> str:
    parts = []
    for block in getattr(response, "content", []) or []:
        block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if block_type == "text":
            text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
            parts.append(text)
    return "".join(parts).strip()


def _usage_value(usage: Any, name: str) -> int:
    if usage is None:
        return 0
    value = usage.get(name, 0) if isinstance(usage, dict) else getattr(usage, name, 0)
    return int(value or 0)


@dataclass
class TokenUsage:
    uncached_input: int = 0
    cache_creation_input: int = 0
    cache_read_input: int = 0
    output: int = 0

    def add_response(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        self.uncached_input += _usage_value(usage, "input_tokens")
        self.cache_creation_input += _usage_value(usage, "cache_creation_input_tokens")
        self.cache_read_input += _usage_value(usage, "cache_read_input_tokens")
        self.output += _usage_value(usage, "output_tokens")

    @property
    def input(self) -> int:
        return self.uncached_input + self.cache_creation_input + self.cache_read_input

    @property
    def total(self) -> int:
        return self.input + self.output


@dataclass
class BaselineResult:
    answer: str
    sql: str | None
    rows: list[dict]
    latency_seconds: float
    usage: TokenUsage
    sql_error_count: int
    repair_used: bool
    not_answerable: bool
    error: str | None


class SQLBaseline:
    """One cached-schema text-to-SQL runner with a single bounded repair."""

    def __init__(self, client: Any, conn: Any, schema_prompt: str, model: str = MODEL):
        self.client = client
        self.conn = conn
        self.schema_prompt = schema_prompt
        self.model = model

    @classmethod
    def from_database(
        cls,
        db_path: str,
        client: Any | None = None,
        model: str = MODEL,
        connect: Callable[..., Any] = duckdb.connect,
    ) -> "SQLBaseline":
        conn = connect_read_only(db_path, connect=connect)
        return cls(client or anthropic.Anthropic(), conn, build_schema_prompt(conn), model)

    def close(self) -> None:
        self.conn.close()

    def _model_call(
        self,
        *,
        system: str | list[dict],
        messages: list[dict],
        max_tokens: int,
        usage: TokenUsage,
    ) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=messages,
        )
        usage.add_response(response)
        return _response_text(response)

    def _generate_sql(self, messages: list[dict], usage: TokenUsage) -> str:
        system = [{
            "type": "text",
            "text": self.schema_prompt,
            "cache_control": {"type": "ephemeral"},
        }]
        return _extract_sql(self._model_call(
            system=system, messages=messages, max_tokens=1200, usage=usage
        ))

    def _execute(self, sql: str) -> tuple[str, list[dict]]:
        statement = guard_select(sql)
        result = self.conn.execute(statement)
        columns = [description[0] for description in result.description]
        rows = [dict(zip(columns, row)) for row in result.fetchmany(_MAX_ROWS)]
        return statement, rows

    def _answer(
        self,
        question: str,
        history: list[dict] | None,
        sql: str | None,
        rows: list[dict],
        not_answerable: bool,
        error: str | None,
        usage: TokenUsage,
    ) -> str:
        transcript = _conversation_messages(question, history)
        context = "\n".join(
            f"{message['role'].title()}: {message['content']}" for message in transcript
        )
        if not_answerable:
            result_text = NOT_ANSWERABLE
        elif rows:
            result_text = json.dumps(rows, default=str, ensure_ascii=True, separators=(",", ":"))
        else:
            result_text = f"No usable result. {error or 'The query returned no rows.'}"
        prompt = (
            f"Conversation:\n{context}\n\nGenerated SQL: {sql or NOT_ANSWERABLE}\n"
            f"Database result: {result_text}\n\nWrite a short direct answer to the latest "
            "question using only this result. If it is NOT_ANSWERABLE or unusable, "
            "say the requested data is not available in this NFL database; do not fabricate."
        )
        return self._model_call(
            system="You turn bounded NFL database results into concise plain-English answers.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
            usage=usage,
        )

    def run(self, question: str, history: list[dict] | None = None) -> BaselineResult:
        started = time.perf_counter()
        usage = TokenUsage()
        messages = _conversation_messages(question, history)
        generated = self._generate_sql(messages, usage)
        statement: str | None = None
        rows: list[dict] = []
        error: str | None = None
        sql_errors = 0
        repair_used = False
        not_answerable = False

        for attempt in range(2):
            if generated.strip() == NOT_ANSWERABLE:
                not_answerable = True
                statement = None
                error = None
                break
            try:
                statement, rows = self._execute(generated)
                error = None if rows else "query returned no rows"
            except Exception as exc:
                statement = generated.strip() or None
                rows = []
                error = f"{type(exc).__name__}: {exc}"
                sql_errors += 1
            if rows or attempt == 1:
                break

            repair_used = True
            messages.extend([
                {"role": "assistant", "content": generated},
                {"role": "user", "content": (
                    f"The query could not be used: {error}. Return one revised DuckDB "
                    f"SELECT/WITH statement, or exactly {NOT_ANSWERABLE}."
                )},
            ])
            generated = self._generate_sql(messages, usage)

        answer = self._answer(
            question, history, statement, rows, not_answerable, error, usage
        )
        return BaselineResult(
            answer=answer,
            sql=statement,
            rows=rows,
            latency_seconds=time.perf_counter() - started,
            usage=usage,
            sql_error_count=sql_errors,
            repair_used=repair_used,
            not_answerable=not_answerable,
            error=error,
        )
