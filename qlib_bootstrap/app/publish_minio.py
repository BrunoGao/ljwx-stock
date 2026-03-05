import io
import os
from pathlib import Path
from typing import Protocol

from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error


class MinioLike(Protocol):
    def put_object(
        self, bucket_name: str, object_name: str, data: io.BytesIO, length: int
    ) -> object: ...

    def copy_object(
        self, bucket_name: str, object_name: str, source: CopySource
    ) -> object: ...

    def remove_object(self, bucket_name: str, object_name: str) -> object: ...


def _normalize_endpoint(endpoint: str) -> tuple[str, bool]:
    raw = endpoint.strip()
    if raw.startswith("https://"):
        return raw.replace("https://", "", 1), True
    if raw.startswith("http://"):
        return raw.replace("http://", "", 1), False
    return raw, False


def create_minio_client(endpoint: str, access_key: str, secret_key: str) -> Minio:
    normalized, secure = _normalize_endpoint(endpoint)
    return Minio(
        normalized, access_key=access_key, secret_key=secret_key, secure=secure
    )


def atomic_write_latest(
    client: MinioLike, bucket: str, latest_key: str, value: str
) -> None:
    tmp_key = f"{latest_key}.tmp"
    payload = f"{value.strip()}\n".encode("utf-8")

    client.put_object(
        bucket_name=bucket,
        object_name=tmp_key,
        data=io.BytesIO(payload),
        length=len(payload),
    )
    client.copy_object(
        bucket_name=bucket,
        object_name=latest_key,
        source=CopySource(bucket_name=bucket, object_name=tmp_key),
    )
    client.remove_object(bucket_name=bucket, object_name=tmp_key)


def publish_to_minio(
    local_dir: str,
    minio_endpoint: str,
    bucket: str,
    prefix: str,
    access_key: str | None = None,
    secret_key: str | None = None,
) -> dict[str, object]:
    resolved_access_key = access_key or os.getenv("MINIO_ACCESS_KEY", "")
    resolved_secret_key = secret_key or os.getenv("MINIO_SECRET_KEY", "")

    if resolved_access_key == "" or resolved_secret_key == "":
        raise ValueError("MinIO 凭证缺失，请设置 MINIO_ACCESS_KEY/MINIO_SECRET_KEY")

    local_path = Path(local_dir)
    if not local_path.exists():
        raise FileNotFoundError(f"待发布目录不存在: {local_path}")

    client = create_minio_client(
        endpoint=minio_endpoint,
        access_key=resolved_access_key,
        secret_key=resolved_secret_key,
    )

    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
    except S3Error as exc:
        raise RuntimeError(f"MinIO bucket 检查失败: {exc}") from exc

    uploaded_count = 0
    for file_path in sorted(local_path.rglob("*")):
        if not file_path.is_file():
            continue

        relative_key = file_path.relative_to(local_path).as_posix()
        object_name = (
            f"{prefix.strip('/')}/{relative_key}"
            if relative_key != ""
            else prefix.strip("/")
        )

        try:
            client.fput_object(
                bucket_name=bucket, object_name=object_name, file_path=str(file_path)
            )
        except S3Error as exc:
            raise RuntimeError(f"MinIO 上传失败: {object_name}, {exc}") from exc

        uploaded_count += 1

    return {
        "bucket": bucket,
        "prefix": prefix,
        "local_dir": str(local_path),
        "uploaded_count": uploaded_count,
    }
