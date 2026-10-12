"""Read-only, parameterized verification callbacks for SchemaAwareBinder.

The adapter reads ONLY values/relationships. It cannot execute the final research SQL.
Caller must append returned proof metadata to its own evidence ledger.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from binding_repair import BindingRejected

class SQLiteBindingAdapter:
    def __init__(self, database_paths: dict[str, str]):
        self.database_paths = {k: str(Path(v).resolve()) for k,v in database_paths.items()}

    @contextmanager
    def connect(self, database):
        if database not in self.database_paths:
            raise BindingRejected('UNKNOWN_DATABASE')
        path = Path(self.database_paths[database])
        if not path.is_file():
            raise BindingRejected('DATABASE_NOT_FOUND')
        conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True, timeout=3)
        try:
            conn.execute('PRAGMA query_only=ON')
            conn.set_progress_handler(lambda: 1, 200000)  # bounded work
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _ident(conn, table, column):
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if table not in tables:
            raise BindingRejected('UNKNOWN_TABLE:' + str(table))
        q = lambda name: '"' + name.replace('"','""') + '"'
        cols = {r[1] for r in conn.execute('PRAGMA table_info('+q(table)+')')}
        if column not in cols:
            raise BindingRejected('UNKNOWN_COLUMN:' + str(column))
        return q(table), q(column)

    def probe(self, database, table, column, value):
        with self.connect(database) as conn:
            qt, qc = self._ident(conn, table, column)
            row = conn.execute(f'SELECT 1 FROM {qt} WHERE {qc} = ? LIMIT 1', (value,)).fetchone()
            return row is not None

    def relation(self, database, table, alias_column, alias_value,
                 identifier_column, identifier_value):
        with self.connect(database) as conn:
            qt, qa = self._ident(conn, table, alias_column)
            _, qi = self._ident(conn, table, identifier_column)
            # An exact alias-to-identifier mapping is strong evidence. If the
            # source stores a longer company name, add an authoritative alias
            # registry rather than treating an arbitrary substring as identity.
            rows = conn.execute(
                f'SELECT DISTINCT {qi} FROM {qt} WHERE {qa} = ? LIMIT 2',
                (alias_value,)).fetchall()
            return len(rows)==1 and str(rows[0][0])==str(identifier_value)
