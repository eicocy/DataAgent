from pathlib import Path
from io import BytesIO
from datetime import UTC, datetime

import pytest
from openpyxl import Workbook
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Dataset, DatasetColumn, User
from app.routers import datasets
from app.services.datasets import recover_interrupted_datasets


@pytest.fixture
def dataset_context(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    previous_override = app.dependency_overrides.get(get_db)

    def override_get_db():
        with testing_sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(datasets, "SessionLocal", testing_sessions)
    monkeypatch.setattr(datasets, "engine", engine)
    monkeypatch.setattr(datasets.settings, "upload_dir", str(tmp_path / "uploads"))
    client = TestClient(app, headers={"Origin": "http://localhost:5173"})
    client.post("/api/v1/auth/register", json={"username": "alice", "password": "safe-password-123"})
    yield client, testing_sessions, Path(tmp_path / "uploads")
    if previous_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_override
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_upload_csv_profiles_columns_and_limits_preview(dataset_context):
    client, sessions, _ = dataset_context
    content = b"order_date,region,sales\n2026-01-01,North,12.5\n2026-01-02,South,8.0\n"

    uploaded = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert uploaded.status_code == 202
    assert uploaded.json()["data"]["status"] == "parsing"
    dataset_id = uploaded.json()["data"]["id"]

    detail = client.get(f"/api/v1/datasets/{dataset_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "ready"
    assert detail.json()["data"]["row_count"] == 2

    columns = client.get(f"/api/v1/datasets/{dataset_id}/columns").json()["data"]
    assert [column["name"] for column in columns] == ["order_date", "region", "sales"]
    preview = client.get(f"/api/v1/datasets/{dataset_id}/preview?offset=1&limit=1")
    assert preview.json()["data"]["rows"] == [{"order_date": "2026-01-02", "region": "South", "sales": 8.0}]
    assert columns[0]["data_type"] == "date"

    with sessions() as db:
        assert db.query(DatasetColumn).filter_by(dataset_id=dataset_id).count() == 3
        assert db.query(Dataset).filter_by(id=dataset_id).one().status == "ready"


def test_non_ascii_headers_keep_safe_sql_names_and_original_labels(dataset_context):
    client, _, _ = dataset_context
    uploaded = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("orders.csv", "产品名称,销售额\n椅子,12\n".encode("utf-8"), "text/csv")},
    )
    dataset_id = uploaded.json()["data"]["id"]

    columns = client.get(f"/api/v1/datasets/{dataset_id}/columns").json()["data"]
    preview = client.get(f"/api/v1/datasets/{dataset_id}/preview").json()["data"]

    assert [item["name"] for item in columns] == ["column_1", "column_2"]
    assert [item["original_name"] for item in columns] == ["产品名称", "销售额"]
    assert preview["columns"] == ["column_1", "column_2"]
    assert preview["rows"] == [{"column_1": "椅子", "column_2": 12}]


def test_rejects_unsupported_and_oversized_files(dataset_context, monkeypatch):
    client, _, _ = dataset_context

    unsupported = client.post("/api/v1/datasets/upload", files={"file": ("data.exe", b"x", "application/octet-stream")})
    assert unsupported.status_code == 415
    assert unsupported.json()["code"] == "DATASET_TYPE_NOT_SUPPORTED"

    monkeypatch.setattr(datasets.settings, "max_upload_bytes", 3)
    oversized = client.post("/api/v1/datasets/upload", files={"file": ("data.csv", b"a,b\n1,2", "text/csv")})
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "DATASET_FILE_TOO_LARGE"


def test_rejects_malformed_csv_and_duplicate_columns(dataset_context):
    client, _, _ = dataset_context

    malformed = client.post("/api/v1/datasets/upload", files={"file": ("bad.csv", b"\xff\xfe", "text/csv")})
    assert malformed.status_code == 202
    assert client.get(f"/api/v1/datasets/{malformed.json()['data']['id']}").json()["data"]["status"] == "failed"

    duplicate = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("duplicate.csv", b"sales,sales\n1,2\n", "text/csv")},
    )
    assert duplicate.status_code == 202
    duplicate_detail = client.get(f"/api/v1/datasets/{duplicate.json()['data']['id']}").json()["data"]
    assert duplicate_detail["status"] == "failed"
    assert duplicate_detail["parse_error_code"] == "DATASET_DUPLICATE_COLUMNS"


def test_dataset_access_is_scoped_to_owner(dataset_context):
    client, _, _ = dataset_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"x\n1\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={"username": "bobby", "password": "safe-password-123"})

    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 403
    assert client.get(f"/api/v1/datasets/{dataset_id}/preview").status_code == 403
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 403


def test_delete_removes_dataset_file_and_projection(dataset_context):
    client, sessions, upload_dir = dataset_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"sales\n1\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]
    with sessions() as db:
        stored_name = db.query(Dataset).filter_by(id=dataset_id).one().stored_name

    deleted = client.delete(f"/api/v1/datasets/{dataset_id}")

    assert deleted.status_code == 200
    assert not (upload_dir / stored_name).exists()
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404


def test_upload_xlsx_uses_first_nonempty_sheet(dataset_context):
    client, sessions, _ = dataset_context
    workbook = Workbook()
    workbook.active.title = "空白页"
    data = workbook.create_sheet("销售数据")
    data.append(["region", "sales"])
    data.append(["North", 12])
    output = BytesIO()
    workbook.save(output)

    uploaded = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.xlsx", output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert uploaded.status_code == 202
    detail = client.get(f"/api/v1/datasets/{uploaded.json()['data']['id']}").json()["data"]
    assert detail["status"] == "ready"
    assert detail["row_count"] == 1
    with sessions() as db:
        column = db.query(DatasetColumn).filter_by(dataset_id=detail["id"], name="region").one()
        assert column.original_name == "region"


def test_preview_rejects_unknown_columns_and_list_is_owner_scoped(dataset_context):
    client, _, _ = dataset_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"sales,region\n10,North\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]

    invalid_preview = client.get(f"/api/v1/datasets/{dataset_id}/preview?columns=other")
    listing = client.get("/api/v1/datasets?page=1&page_size=10")

    assert invalid_preview.status_code == 422
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] == 1
    assert listing.json()["data"]["items"][0]["id"] == dataset_id


def test_delete_also_drops_mysql_projection(dataset_context):
    client, _, _ = dataset_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"sales\n10\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]

    deleted = client.delete(f"/api/v1/datasets/{dataset_id}")

    assert deleted.status_code == 200
    from sqlalchemy import inspect

    assert not inspect(datasets.engine).has_table(f"dataset_{dataset_id}")


def test_startup_recovery_marks_interrupted_upload_failed(dataset_context):
    _, sessions, upload_dir = dataset_context
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = "interrupted.csv"
    (upload_dir / stored_name).write_text("value\n1\n", encoding="utf-8")
    now = datetime.now(UTC)
    with sessions() as db:
        user_id = db.query(User).filter_by(username="alice").one().id
        dataset = Dataset(
            user_id=user_id,
            original_name="interrupted.csv",
            stored_name=stored_name,
            file_type="csv",
            file_size=8,
            status="parsing",
            created_at=now,
            updated_at=now,
        )
        db.add(dataset)
        db.commit()
        dataset_id = dataset.id

    recover_interrupted_datasets(sessions, datasets.engine, str(upload_dir))

    with sessions() as db:
        recovered = db.get(Dataset, dataset_id)
        assert recovered.status == "failed"
        assert recovered.parse_error_code == "DATASET_PROCESS_INTERRUPTED"
    assert (upload_dir / stored_name).exists()

def test_new_parse_publishes_version_with_hash_and_transformations(dataset_context):
    from app.models import DatasetVersion
    client, sessions, root = dataset_context
    uploaded = client.post('/api/v1/datasets/upload', files={'file': ('input.csv', b'Code,Amount\n001,10\n002,20\n', 'text/csv')})
    identifier = uploaded.json()['data']['id']
    with sessions() as db:
        dataset = db.get(Dataset, identifier)
        version = db.get(DatasetVersion, dataset.current_version_id)
        assert version.dataset_id == identifier
        assert len(version.source_checksum) == 64
        assert version.original_available
        assert version.schema_json['columns'][0]['semantic_type'] == 'Identifier'
        assert version.transformations_json
        assert version.projection_table == f'dataset_{identifier}'

def test_failed_parse_keeps_accepted_source_until_delete(dataset_context):
    client, sessions, root = dataset_context
    uploaded = client.post('/api/v1/datasets/upload', files={'file': ('bad.csv', b'x,x\n1,2\n', 'text/csv')})
    identifier = uploaded.json()['data']['id']
    with sessions() as db:
        source = root / db.get(Dataset, identifier).stored_name
    assert source.exists()
    assert client.delete(f'/api/v1/datasets/{identifier}').status_code == 200
    assert not source.exists()

def test_lease_loss_does_not_publish_version_or_delete_source(dataset_context):
    from app.services.datasets import process_dataset
    from app.models import DatasetVersion
    from sqlalchemy import inspect
    client, sessions, root = dataset_context
    now = datetime.now(UTC)
    root.mkdir(exist_ok=True)
    source = root / 'lease.csv'
    source.write_text('measure\n10\n', encoding='utf-8')
    with sessions() as db:
        owner = db.query(User).first()
        dataset = Dataset(user_id=owner.id, original_name='lease.csv', stored_name=source.name, file_type='csv', file_size=10, status='parsing', created_at=now, updated_at=now)
        db.add(dataset); db.commit(); identifier = dataset.id
    process_dataset(identifier, sessions, datasets.engine, str(root), lease_guard=lambda db, lock: not lock)
    with sessions() as db:
        assert db.get(Dataset, identifier).current_version_id is None
        assert db.query(DatasetVersion).count() == 0
    assert source.exists()
    assert not inspect(datasets.engine).has_table(f'dataset_{identifier}')

def test_dataset_version_cross_dataset_reference_rejected(dataset_context):
    from app.services.datasets import DatasetService
    from fastapi import HTTPException
    client, sessions, root = dataset_context
    identifiers = [client.post('/api/v1/datasets/upload', files={'file': ('input.csv', b'value\n1\n', 'text/csv')}).json()['data']['id'] for _ in range(2)]
    with sessions() as db:
        first, second = [db.get(Dataset, identifier) for identifier in identifiers]
        with pytest.raises(HTTPException):
            DatasetService(db, datasets.engine).get_version(first, second.current_version_id)
        metadata = DatasetService(db, datasets.engine).model_metadata(first, db.query(DatasetColumn).filter_by(dataset_id=first.id).all())
        assert metadata['profile']['row_count'] == 1
        assert 'sample_values' not in str(metadata)

def test_expired_parse_failure_cannot_overwrite_dataset_status(dataset_context):
    from app.services.datasets import process_dataset
    client, sessions, root = dataset_context
    now = datetime.now(UTC)
    root.mkdir(exist_ok=True)
    source = root / 'expired.csv'
    source.write_text('a,a\n1,2\n', encoding='utf-8')
    with sessions() as db:
        dataset = Dataset(user_id=db.query(User).first().id, original_name='expired.csv', stored_name=source.name, file_type='csv', file_size=10, status='parsing', created_at=now, updated_at=now)
        db.add(dataset); db.commit(); identifier = dataset.id
    calls = 0
    def guard(db, lock):
        nonlocal calls
        calls += 1
        return calls == 1
    process_dataset(identifier, sessions, datasets.engine, str(root), lease_guard=guard)
    with sessions() as db:
        assert db.get(Dataset, identifier).status == 'parsing'
    assert source.exists()
