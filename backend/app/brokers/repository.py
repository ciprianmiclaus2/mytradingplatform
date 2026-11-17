"""Broker data persistence: data/brokers/{accounts,positions}.parquet and status.json.

This is a cache of what SnapTrade returned at the last refresh; it can be
rebuilt at any time by refreshing.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import PurePosixPath

import pyarrow as pa

from app.brokers.models import BrokerAccount, BrokerPosition
from app.persistence.jsonfile import read_json, write_json
from app.persistence.parquet import ParquetStore
from app.persistence.schemas import DatasetSchema, register_dataset

UTC_TS = pa.timestamp("us", tz="UTC")
DECIMAL = pa.decimal128(28, 10)
STATUS_FILE = PurePosixPath("brokers/status.json")

BROKER_ACCOUNTS = register_dataset(
    DatasetSchema(
        "broker_accounts",
        1,
        pa.schema(
            [
                pa.field("id", pa.string(), nullable=False),
                pa.field("name", pa.string(), nullable=False),
                pa.field("number", pa.string(), nullable=False),
                pa.field("status", pa.string(), nullable=True),
                pa.field("kind", pa.string(), nullable=False),
                pa.field("net_value", pa.float64(), nullable=True),
                pa.field("net_value_currency", pa.string(), nullable=True),
                pa.field("listed_at", UTC_TS, nullable=False),
                pa.field("positions_refreshed_at", UTC_TS, nullable=True),
                pa.field("data_as_of", UTC_TS, nullable=True),
            ]
        ),
        key=("id",),
        path=PurePosixPath("brokers/accounts.parquet"),
        description="Broker accounts as last listed by SnapTrade",
    )
)

BROKER_POSITIONS = register_dataset(
    DatasetSchema(
        "broker_positions",
        1,
        pa.schema(
            [
                pa.field("account_id", pa.string(), nullable=False),
                pa.field("symbol", pa.string(), nullable=False),
                pa.field("ticker", pa.string(), nullable=True),
                pa.field("description", pa.string(), nullable=True),
                pa.field("kind", pa.string(), nullable=False),
                pa.field("units", DECIMAL, nullable=False),
                pa.field("price", DECIMAL, nullable=True),
                pa.field("cost_basis", DECIMAL, nullable=True),
                pa.field("multiplier", DECIMAL, nullable=False),
                pa.field("currency", pa.string(), nullable=True),
                pa.field("cash_equivalent", pa.bool_(), nullable=False),
            ]
        ),
        path=PurePosixPath("brokers/positions.parquet"),
        description="Broker positions per account at the last refresh",
    )
)


class BrokerRepository:
    def __init__(self, store: ParquetStore) -> None:
        self.store = store

    # -- accounts ----------------------------------------------------------------

    def accounts(self) -> list[BrokerAccount]:
        return [BrokerAccount(**r) for r in self.store.read(BROKER_ACCOUNTS).to_pylist()]

    def modify_accounts(self, change: Callable[[list[BrokerAccount]], list[BrokerAccount]]) -> list[BrokerAccount]:
        result: list[BrokerAccount] = []

        def transform(table: pa.Table) -> pa.Table:
            nonlocal result
            result = change([BrokerAccount(**r) for r in table.to_pylist()])
            return pa.Table.from_pylist([a.model_dump() for a in result], schema=BROKER_ACCOUNTS.schema)

        self.store.update(BROKER_ACCOUNTS, transform)
        return result

    # -- positions ---------------------------------------------------------------

    def positions(self, account_id: str | None = None) -> list[BrokerPosition]:
        rows = self.store.read(BROKER_POSITIONS).to_pylist()
        return [BrokerPosition(**r) for r in rows if account_id is None or r["account_id"] == account_id]

    def replace_positions(self, account_ids: set[str], positions: list[BrokerPosition]) -> None:
        """Replace every stored position of ``account_ids`` with ``positions``."""

        def transform(table: pa.Table) -> pa.Table:
            kept = [r for r in table.to_pylist() if r["account_id"] not in account_ids]
            rows = kept + [p.model_dump() for p in positions]
            return pa.Table.from_pylist(rows, schema=BROKER_POSITIONS.schema)

        self.store.update(BROKER_POSITIONS, transform)

    # -- status ------------------------------------------------------------------

    def accounts_refreshed_at(self) -> datetime | None:
        doc = read_json(self.store, STATUS_FILE)
        value = doc.get("accounts_refreshed_at") if isinstance(doc, dict) else None
        return datetime.fromisoformat(value) if isinstance(value, str) else None

    def set_accounts_refreshed_at(self, when: datetime) -> None:
        write_json(self.store, STATUS_FILE, {"accounts_refreshed_at": when.isoformat()})

    def clear(self) -> None:
        """Forget all cached broker data (when SnapTrade is disconnected)."""
        with self.store.lock.hold():
            self.store.delete(BROKER_ACCOUNTS)
            self.store.delete(BROKER_POSITIONS)
            self.store.resolve(STATUS_FILE).unlink(missing_ok=True)
