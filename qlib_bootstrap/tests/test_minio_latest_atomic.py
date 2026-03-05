import io

from qlib_bootstrap.app.publish_minio import atomic_write_latest


class _DummyCopySource:
    def __init__(self, object_name: str) -> None:
        self.object_name = object_name


class DummyMinioClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def put_object(
        self, bucket_name: str, object_name: str, data: io.BytesIO, length: int
    ) -> None:
        _ = bucket_name
        _ = data.read(length)
        self.calls.append(("put", object_name))

    def copy_object(self, bucket_name: str, object_name: str, source: object) -> None:
        _ = bucket_name
        source_name = getattr(source, "object_name", "")
        self.calls.append(("copy", f"{object_name}<-{source_name}"))

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        _ = bucket_name
        self.calls.append(("remove", object_name))


def test_atomic_write_latest_order(monkeypatch) -> None:
    client = DummyMinioClient()

    monkeypatch.setattr(
        "qlib_bootstrap.app.publish_minio.CopySource",
        lambda bucket_name, object_name: _DummyCopySource(object_name=object_name),
    )

    atomic_write_latest(
        client=client,
        bucket="ljwx-qlib",
        latest_key="artifacts/models/qlib_lightgbm_alpha158/LATEST",
        value="20260304",
    )

    assert client.calls == [
        ("put", "artifacts/models/qlib_lightgbm_alpha158/LATEST.tmp"),
        (
            "copy",
            "artifacts/models/qlib_lightgbm_alpha158/LATEST<-artifacts/models/qlib_lightgbm_alpha158/LATEST.tmp",
        ),
        ("remove", "artifacts/models/qlib_lightgbm_alpha158/LATEST.tmp"),
    ]
