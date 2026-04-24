"""
S3-compatible storage integration. Supports AWS S3, Cloudflare R2, MinIO.
All uploads return public-readable URLs when bucket policy allows.
"""

import mimetypes
import uuid
from pathlib import Path

import boto3
import structlog
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.exceptions import ExternalServiceError

logger = structlog.get_logger(__name__)


def _get_client():
    kwargs = {
        "region_name": settings.s3_region,
        "aws_access_key_id": settings.s3_access_key_id,
        "aws_secret_access_key": settings.s3_secret_access_key,
    }
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    return boto3.client("s3", **kwargs)


class StorageClient:
    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self._client = _get_client()

    def upload_bytes(
        self,
        data: bytes,
        key: str,
        *,
        content_type: str | None = None,
        public: bool = False,
    ) -> str:
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        if public:
            extra["ACL"] = "public-read"

        try:
            self._client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)
        except ClientError as exc:
            raise ExternalServiceError(f"S3 upload failed: {exc}") from exc

        return self._object_url(key)

    def upload_file(self, path: str | Path, *, prefix: str = "", public: bool = False) -> str:
        path = Path(path)
        ext = path.suffix
        key = f"{prefix}/{uuid.uuid4()}{ext}".lstrip("/")
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

        try:
            self._client.upload_file(
                str(path),
                self.bucket,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    **({"ACL": "public-read"} if public else {}),
                },
            )
        except ClientError as exc:
            raise ExternalServiceError(f"S3 file upload failed: {exc}") from exc

        return self._object_url(key)

    def generate_presigned_url(self, key: str, *, expires_in: int = 3600) -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except ClientError as exc:
            raise ExternalServiceError(f"Failed to generate presigned URL: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise ExternalServiceError(f"S3 delete failed: {exc}") from exc

    def _object_url(self, key: str) -> str:
        if settings.s3_endpoint_url:
            return f"{settings.s3_endpoint_url}/{self.bucket}/{key}"
        return f"https://{self.bucket}.s3.{settings.s3_region}.amazonaws.com/{key}"


media_storage = StorageClient(settings.s3_bucket_media)
export_storage = StorageClient(settings.s3_bucket_exports)
