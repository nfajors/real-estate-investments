"""Object storage: encrypted local filesystem (default) or S3-compatible.

Local files are encrypted with AES-256-GCM (random nonce per object). S3
objects use server-side encryption. Downloads always go through short-lived
signed URLs – storage keys are never exposed directly.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import get_settings
from ..security import sign_payload

_MAGIC = b"AXM1"


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def signed_url(self, key: str, filename: str, content_type: str, inline: bool = True) -> str: ...


class LocalEncryptedStorage:
    def __init__(self, root: str, key: bytes):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.aead = AESGCM(key)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("Invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        nonce = secrets.token_bytes(12)
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(_MAGIC + nonce + self.aead.encrypt(nonce, data, key.encode()))
        os.replace(tmp, p)

    def get(self, key: str) -> bytes:
        raw = self._path(key).read_bytes()
        if raw[:4] != _MAGIC:
            raise ValueError("Corrupt or unencrypted object")
        return self.aead.decrypt(raw[4:16], raw[16:], key.encode())

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def signed_url(self, key: str, filename: str, content_type: str, inline: bool = True) -> str:
        token = sign_payload({"k": key, "fn": filename, "ct": content_type, "in": inline})
        return f"/api/files/{token}"


class S3Storage:  # pragma: no cover - exercised only against real S3/MinIO
    def __init__(self, bucket: str, endpoint_url: str | None, region: str | None):
        import boto3

        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                               ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_url(self, key: str, filename: str, content_type: str, inline: bool = True) -> str:
        disposition = f'{"inline" if inline else "attachment"}; filename="{filename}"'
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key, "ResponseContentType": content_type,
                    "ResponseContentDisposition": disposition},
            ExpiresIn=get_settings().signed_url_seconds,
        )


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_backend == "s3":  # pragma: no cover
            if not s.s3_bucket:
                raise RuntimeError("AXIOM_S3_BUCKET is required for the s3 storage backend")
            _storage = S3Storage(s.s3_bucket, s.s3_endpoint_url, s.s3_region)
        else:
            _storage = LocalEncryptedStorage(s.storage_path, s.encryption_key_bytes())
    return _storage
