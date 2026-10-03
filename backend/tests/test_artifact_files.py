from pathlib import Path

import pytest

from app.artifacts.storage import LocalArtifactStorage


def test_local_artifact_storage_uses_scoped_keys_and_round_trips_bytes(tmp_path):
    storage = LocalArtifactStorage(tmp_path)

    saved = storage.save(
        user_id=7,
        conversation_id=11,
        task_id=13,
        artifact_id=17,
        file_name="报告 / 一季度.pdf",
        content=b"%PDF-test-bytes",
    )

    assert saved.file_name == "报告 _ 一季度.pdf"
    assert saved.storage_key.startswith("u/7/c/11/t/13/a/17-")
    assert saved.storage_key.endswith(".pdf")
    assert storage.read(saved.storage_key) == b"%PDF-test-bytes"
    assert Path(saved.storage_path).is_relative_to(tmp_path.resolve())


@pytest.mark.parametrize(
    "storage_key",
    ["../secret.pdf", "u/7/../../secret.pdf", "/outside.pdf", "u/7/c/11/t/13/a/17-.exe"],
)
def test_local_artifact_storage_rejects_untrusted_or_unsupported_storage_keys(tmp_path, storage_key):
    storage = LocalArtifactStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.read(storage_key)


def test_local_artifact_storage_rejects_invalid_owner_ids(tmp_path):
    storage = LocalArtifactStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.save(
            user_id=-1,
            conversation_id=11,
            task_id=13,
            artifact_id=17,
            file_name="report.pdf",
            content=b"data",
        )
