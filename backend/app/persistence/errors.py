"""Persistence-layer exceptions.

Messages identify the dataset or file relative to the data directory and are
safe to show to the user; they never include stack traces.
"""

from __future__ import annotations


class PersistenceError(RuntimeError):
    """Base class for all persistence failures."""

    code = "persistence_error"


class LockTimeoutError(PersistenceError):
    """The data write lock could not be acquired in time."""

    code = "persistence_lock_timeout"


class SchemaValidationError(PersistenceError):
    """Data does not conform to the dataset's declared schema."""

    code = "schema_validation_error"


class IncompatibleSchemaError(PersistenceError):
    """A stored file was written with a different dataset or schema version."""

    code = "incompatible_schema"


class CorruptFileError(PersistenceError):
    """A stored file exists but cannot be read."""

    code = "corrupt_file"


class BackupError(PersistenceError):
    """Creating, verifying or restoring a backup failed."""

    code = "backup_error"
