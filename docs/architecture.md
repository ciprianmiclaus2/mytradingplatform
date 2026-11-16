# Architecture

My Trading Platform runs locally as a modular monolith: one FastAPI backend process and one React frontend. See the [README](../README.md) for the overview. This document records the design decisions behind each layer as it's built.

## Backend layers

```text
api/            HTTP routes: request/response models only, no business logic
<domain>/       services: portfolio, positions, transactions, market_data, strategies
persistence/    the only code that reads or writes files in DATA_DIR
schemas/        shared API models and the error envelope
```

## Persistence

| Module | Responsibility |
|---|---|
| `persistence/data_dirs.py` | Creates the directory layout and checks the data schema version |
| `persistence/locking.py` | `DataLock`: the single re-entrant write lock |
| `persistence/schemas.py` | `DatasetSchema` declarations, the dataset registry, and validation |
| `persistence/parquet.py` | `ParquetStore`: validated, locked, atomic Parquet reads and writes |
| `persistence/duckdb.py` | Read-only analytical SQL over Parquet files |
| `persistence/derived.py` | Rebuildable derived data (materialised views) and staleness detection |
| `persistence/backup.py` | `BackupManager`: create, prune, verify and restore backups |
| `persistence/__init__.py` | `open_persistence()`: the startup sequence |

### Datasets and schemas

Every persisted dataset is declared once as a `DatasetSchema`, which holds:

- its name and version;
- its Arrow schema, including whether each column may be null;
- optional unique key columns;
- for single-file datasets, its path.

The dataset name and version are written into each Parquet file's metadata.

- **On write:** columns must match exactly by name and type, with no implicit casting. Columns that may not be null must have no nulls, and key values must be unique.
- **On read:** a file whose dataset name, version or columns differ raises `IncompatibleSchemaError`, and an unreadable file raises `CorruptFileError`. In both cases the file is never overwritten.

Money and quantities are stored as Arrow `decimal128` values, so they stay exact. The persistence layer works with Arrow tables. Services convert them to Python `Decimal` values, because pandas would turn decimal columns into generic object columns.

### Writes

The write protocol follows §14.1 of the plan:

1. Acquire the lock.
2. Validate the data.
3. Write a temporary file `.tmp-*` in the same directory.
4. Flush and `fsync` it.
5. `os.replace` it over the original and `fsync` the directory.
6. Release the lock.

If any step fails, the original file is left untouched and the temporary file is removed. Any temporary files left by a crash are deleted on the next startup.

### Locking

There is one data-wide write lock, combining:

- a re-entrant thread lock, which serialises writers inside the backend process;
- an OS file lock at `metadata/.write.lock`, which serialises the backend with the maintenance scripts.

Because there is only one lock, an update that touches several files is consistent whenever the caller holds the lock across all of them. Reads take no lock: atomic replacement means a reader always sees a complete file. If the lock can't be acquired in time, a `LockTimeoutError` is raised, which the API reports as HTTP 503.

### Derived data

Some data is computed entirely from other files, for example `positions.parquet` from the transaction ledger, or `history.parquet` from the daily close-price files. Each such dataset is registered as a `DerivedDataset` with:

- its source files or globs;
- a function that builds it from those sources.

Whenever derived data is written, a SHA-256 fingerprint of its sources is stored in its metadata under `x_source_fingerprint`. If a crash happens after a source was written but before the derived file was, the fingerprints no longer match. The next startup, or `scripts/rebuild_derived.py`, then rebuilds it.

### Backups

- **Contents:** each backup is `backups/<UTC timestamp>Z-<reason>/` with a `manifest.json` of SHA-256 checksums. It covers the `portfolios`, `positions`, `transactions`, `strategies` and `metadata` folders. Market data is excluded because it can be downloaded again.
- **Creation:** backups are assembled in a temporary staging folder and then renamed into place, so a half-written backup never looks complete. Only the newest `BACKUP_RETENTION_COUNT` backups are kept.
- **Restoring:** the checksums are verified first, the current state is backed up, and then each file is replaced atomically. A backup made with a different data schema version is refused.
- **When backups are taken:** on startup, but skipped if nothing changed since the last backup. Services will also take one before destructive operations.

### Startup sequence

`open_persistence()` runs these steps in order. Any incompatibility stops startup with a clear error.

1. Create the directories and check the schema version.
2. Remove leftover temporary files.
3. Validate every registered dataset file.
4. Rebuild stale derived data.
5. Back up the now-consistent state.

### Analytical queries

`persistence.duckdb.query(sql, sources, params)` opens a short-lived in-memory DuckDB connection, so no database file is ever created. It exposes each `ParquetSource` (a file or glob) as a SQL view, runs the query with bound parameters, and returns an Arrow table. A source with no files yet appears as an empty view with its declared schema.
