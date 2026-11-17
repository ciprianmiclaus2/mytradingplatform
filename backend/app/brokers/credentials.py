"""Local storage of SnapTrade credentials: <data>/config/snaptrade.json, owner-only.

The file is readable only by the owner (0600, directory 0700) and is not
part of data backups. The API never returns the secrets themselves.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.brokers.models import SnapTradeCredentials, SnapTradeStatus
from app.persistence.errors import CorruptFileError, PersistenceError

logger = logging.getLogger(__name__)

CONFIG_DIR = "config"
FILE_NAME = "snaptrade.json"


def _hint(secret: str) -> str:
    return secret[-4:] if len(secret) > 8 else ""


class CredentialStore:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / CONFIG_DIR
        self.path = self.directory / FILE_NAME

    def load(self) -> SnapTradeCredentials | None:
        if not self.path.exists():
            return None
        self._tighten()
        try:
            return SnapTradeCredentials.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, ValidationError) as exc:
            raise CorruptFileError(f"{CONFIG_DIR}/{FILE_NAME} cannot be read; set up SnapTrade again") from exc

    def save(self, credentials: SnapTradeCredentials) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        document = {
            "client_id": credentials.client_id,
            "consumer_key": credentials.consumer_key.get_secret_value(),
            "user_id": credentials.user_id,
            "user_secret": credentials.user_secret.get_secret_value() if credentials.user_secret else None,
        }
        # mkstemp creates the file with mode 0600 before anything is written to it.
        fd, tmp_name = tempfile.mkstemp(dir=self.directory, prefix=f".{FILE_NAME}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(document, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)
        except OSError as exc:
            Path(tmp_name).unlink(missing_ok=True)
            raise PersistenceError(f"Failed to save the SnapTrade settings: {exc}") from exc
        logger.info("snaptrade credentials saved", extra={"client_id": credentials.client_id})

    def delete(self) -> bool:
        if not self.path.exists():
            return False
        self.path.unlink()
        logger.info("snaptrade credentials removed")
        return True

    def status(self) -> SnapTradeStatus:
        creds = self.load()
        if creds is None:
            return SnapTradeStatus(configured=False)
        return SnapTradeStatus(
            configured=True,
            personal=creds.personal,
            client_id=creds.client_id,
            user_id=creds.user_id,
            consumer_key_hint=_hint(creds.consumer_key.get_secret_value()),
            user_secret_hint=_hint(creds.user_secret.get_secret_value()) if creds.user_secret else None,
        )

    def _tighten(self) -> None:
        """Repair permissions if the file was copied or edited with a wider mode."""
        try:
            if stat.S_IMODE(self.path.stat().st_mode) & 0o077:
                os.chmod(self.path, 0o600)
                logger.warning("snaptrade credentials file permissions tightened to 0600")
        except OSError:
            pass
