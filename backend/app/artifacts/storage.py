from __future__ import annotations

import mimetypes
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path


_ALLOWED_EXTENSIONS = {
    "csv", "docx", "html", "json", "md", "pdf", "png", "svg", "xlsx", "zip",
}
_STORAGE_KEY = re.compile(
    r"u/[1-9]\d*/c/[1-9]\d*/t/[1-9]\d*/a/[1-9]\d*-[a-f0-9]{32}\.(?:"
    + "|".join(sorted(_ALLOWED_EXTENSIONS))
    + r")\Z"
)
_BAD_DISPLAY_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


@dataclass(frozen=True)
class StoredArtifactFile:
    storage_key: str
    file_name: str
    mime_type: str
    size_bytes: int
    storage_path: str


class LocalArtifactStorage:
    """Write bounded export files under server-generated, owner-scoped keys."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    @staticmethod
    def safe_file_name(file_name: str, extension: str) -> str:
        normalized = unicodedata.normalize("NFC", str(file_name or "")).strip()
        cleaned = _BAD_DISPLAY_CHARS.sub("_", normalized).strip(" .")[:180]
        if not cleaned:
            cleaned = "artifact"
        suffix = f".{extension}"
        if not cleaned.lower().endswith(suffix):
            cleaned = f"{cleaned[: max(1, 180 - len(suffix))]}{suffix}"
        return cleaned

    def _path(self, storage_key: str) -> Path:
        if not isinstance(storage_key, str) or not _STORAGE_KEY.fullmatch(storage_key):
            raise ValueError("Invalid artifact storage key")
        path = (self.root / Path(*storage_key.split("/"))).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Artifact path escapes storage root")
        return path

    def save(
        self,
        *,
        user_id: int,
        conversation_id: int,
        task_id: int,
        artifact_id: int,
        file_name: str,
        content: bytes,
    ) -> StoredArtifactFile:
        if any(type(value) is not int or value <= 0 for value in
               (user_id, conversation_id, task_id, artifact_id)):
            raise ValueError("Artifact owner IDs must be positive integers")
        if not isinstance(content, bytes) or not content:
            raise ValueError("Artifact content must be non-empty bytes")

        supplied = unicodedata.normalize("NFC", str(file_name or "")).strip()
        suffix = Path(supplied.replace("\\", "/").split("/")[-1]).suffix.lower().lstrip(".")
        if suffix not in _ALLOWED_EXTENSIONS:
            raise ValueError("Unsupported artifact extension")

        key = f"u/{user_id}/c/{conversation_id}/t/{task_id}/a/{artifact_id}-{uuid.uuid4().hex}.{suffix}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + f".{uuid.uuid4().hex}.part")
        try:
            with temp.open("xb") as stream:
                stream.write(content)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

        safe_name = self.safe_file_name(supplied, suffix)
        mime = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        if suffix == "svg":
            mime = "image/svg+xml"
        return StoredArtifactFile(key, safe_name, mime, len(content), str(path))

    def read(self, storage_key: str) -> bytes:
        return self._path(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        path = self._path(storage_key)
        path.unlink(missing_ok=True)
        parent = path.parent
        while parent != self.root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
