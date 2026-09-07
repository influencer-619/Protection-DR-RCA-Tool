"""Object storage: S3/MinIO with local filesystem fallback (content-addressed by SHA-256)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BytesLike = Union[bytes, bytearray, memoryview]


class StorageService:
    """
    Immutable content-addressed storage.

    Keys: ``{prefix}/{sha256[:2]}/{sha256}`` (optional original suffix).
    Backend: ``local`` | ``s3`` | ``auto`` (try S3, fall back to local).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.backend = (settings.storage_backend or "auto").lower()
        self.bucket = settings.s3_bucket
        self.local_root = Path(settings.local_storage_path).resolve()
        self.local_root.mkdir(parents=True, exist_ok=True)
        self._s3 = None
        self._use_s3 = False
        if self.backend in ("s3", "auto"):
            self._use_s3 = self._init_s3()
            if self.backend == "s3" and not self._use_s3:
                logger.warning("S3 requested but unavailable; using local storage")
                self._use_s3 = False

    def _init_s3(self) -> bool:
        settings = get_settings()
        try:
            import boto3
            from botocore.client import Config
            from botocore.exceptions import BotoCoreError, ClientError

            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name=settings.s3_region,
                use_ssl=settings.s3_use_ssl,
                config=Config(signature_version="s3v4"),
            )
            # Probe connectivity lightly
            try:
                client.head_bucket(Bucket=self.bucket)
            except ClientError:
                try:
                    client.create_bucket(Bucket=self.bucket)
                except (ClientError, BotoCoreError):
                    return False
            self._s3 = client
            return True
        except Exception as exc:  # noqa: BLE001
            logger.info("S3 unavailable (%s); local storage will be used", exc)
            return False

    @staticmethod
    def content_key(sha256: str, prefix: str = "files", suffix: str = "") -> str:
        safe_suffix = ""
        if suffix:
            if not suffix.startswith("."):
                suffix = f".{suffix}"
            safe_suffix = suffix.lower()
        return f"{prefix}/{sha256[:2]}/{sha256}{safe_suffix}"

    def put_bytes(
        self,
        data: BytesLike,
        *,
        sha256: str,
        prefix: str = "files",
        suffix: str = "",
        content_type: Optional[str] = None,
    ) -> str:
        key = self.content_key(sha256, prefix=prefix, suffix=suffix)
        payload = bytes(data)
        if self._use_s3 and self._s3 is not None:
            extra = {}
            if content_type:
                extra["ContentType"] = content_type
            # Do not overwrite: skip if exists
            try:
                self._s3.head_object(Bucket=self.bucket, Key=key)
                return key
            except Exception:  # noqa: BLE001
                pass
            self._s3.put_object(Bucket=self.bucket, Key=key, Body=payload, **extra)
            return key
        return self._put_local(key, payload)

    def _put_local(self, key: str, payload: bytes) -> str:
        path = self.local_root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return key
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(payload)
        tmp.replace(path)
        return key

    def get_bytes(self, key: str) -> bytes:
        if self._use_s3 and self._s3 is not None:
            try:
                obj = self._s3.get_object(Bucket=self.bucket, Key=key)
                return obj["Body"].read()
            except Exception:  # noqa: BLE001
                # fall through to local
                pass
        path = self.local_root / key
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        if self._use_s3 and self._s3 is not None:
            try:
                self._s3.head_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:  # noqa: BLE001
                pass
        return (self.local_root / key).exists()

    def local_path(self, key: str) -> Path:
        return self.local_root / key


_storage: Optional[StorageService] = None


def get_storage() -> StorageService:
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage
