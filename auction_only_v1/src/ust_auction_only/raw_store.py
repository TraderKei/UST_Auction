from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


EXTENSIONS = {
    "application/json": ".json",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "text/html": ".html",
    "application/pdf": ".pdf",
    "application/vnd.ms-excel": ".bin",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".bin",
}


@dataclass(frozen=True)
class StoredRaw:
    sha256: str
    path: Path
    size_bytes: int


class RawStore:
    """Content-addressed immutable raw storage."""

    def __init__(self, root: Path):
        self.root = root

    def put(
        self,
        content: bytes,
        source: str,
        content_type: str | None,
        fetched_at: datetime | None = None,
    ) -> StoredRaw:
        fetched_at = fetched_at or datetime.now(UTC)
        digest = hashlib.sha256(content).hexdigest()
        mime = (content_type or "application/octet-stream").split(";", 1)[0].lower()
        extension = EXTENSIONS.get(mime, ".bin")
        target = (
            self.root
            / source
            / fetched_at.strftime("%Y")
            / fetched_at.strftime("%m")
            / fetched_at.strftime("%d")
            / f"{digest}{extension}"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as handle:
                handle.write(content)
        except FileExistsError:
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError(f"raw integrity mismatch: {target}")
        return StoredRaw(digest, target, len(content))
