"""Storage service for artifact files"""
import os
import uuid
from typing import BinaryIO, Optional, Tuple
from flask import current_app
import boto3
from botocore.exceptions import ClientError


class StorageService:
    """Service for storing and retrieving artifact files."""

    def __init__(self):
        """Initialize storage service with lazy-loaded S3 client."""
        self._s3_client = None

    @property
    def s3_client(self):
        """Get or create S3 client."""
        if self._s3_client is None:
            endpoint = current_app.config.get('S3_ENDPOINT')
            if endpoint:
                self._s3_client = boto3.client(
                    's3',
                    endpoint_url=endpoint,
                    aws_access_key_id=current_app.config.get('S3_ACCESS_KEY'),
                    aws_secret_access_key=current_app.config.get('S3_SECRET_KEY'),
                    region_name=current_app.config.get('S3_REGION', 'us-east-1')
                )
        return self._s3_client

    @property
    def bucket(self) -> str:
        """Get S3 bucket name."""
        return current_app.config.get('S3_BUCKET', 'sheetstorm-artifacts')

    @property
    def is_s3_configured(self) -> bool:
        """Check if S3 storage is configured."""
        return bool(current_app.config.get('S3_ENDPOINT'))

    def generate_storage_path(self, incident_id: str, original_filename: str) -> Tuple[str, str]:
        """Generate a unique storage path for an artifact.

        Args:
            incident_id: ID of the incident
            original_filename: Original filename

        Returns:
            Tuple of (storage_path, stored_filename)
        """
        # Generate UUID-based filename to prevent overwrites
        ext = os.path.splitext(original_filename)[1] if '.' in original_filename else ''
        stored_filename = f"{uuid.uuid4()}{ext}"
        storage_path = f"incidents/{incident_id}/artifacts/{stored_filename}"
        return storage_path, stored_filename

    def store_file(
        self,
        file_obj: BinaryIO,
        storage_path: str,
        content_type: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Store a file to S3 or local storage.

        Args:
            file_obj: File-like object to store
            storage_path: Path within storage
            content_type: MIME type of the file

        Returns:
            Tuple of (success, storage_type)
        """
        if self.is_s3_configured:
            return self._store_s3(file_obj, storage_path, content_type)
        else:
            return self._store_local(file_obj, storage_path)

    def _store_s3(
        self,
        file_obj: BinaryIO,
        storage_path: str,
        content_type: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Store file to S3."""
        try:
            extra_args = {'ServerSideEncryption': 'AES256'}
            if content_type:
                extra_args['ContentType'] = content_type

            file_obj.seek(0)
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket,
                storage_path,
                ExtraArgs=extra_args
            )
            return True, 's3'
        except ClientError as e:
            current_app.logger.error(f"S3 upload error: {e}")
            return False, 's3'

    def _store_local(self, file_obj: BinaryIO, storage_path: str) -> Tuple[bool, str]:
        """Store file to local filesystem."""
        try:
            # Use a local artifacts directory
            local_path = os.path.join('/app/artifacts', storage_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            file_obj.seek(0)
            with open(local_path, 'wb') as f:
                while True:
                    chunk = file_obj.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)

            return True, 'local'
        except Exception as e:
            current_app.logger.error(f"Local storage error: {e}")
            return False, 'local'

    def retrieve_file(self, storage_path: str, storage_type: str = 'local') -> Optional[BinaryIO]:
        """Retrieve a file from storage.

        Args:
            storage_path: Path within storage
            storage_type: 'local' or 's3'

        Returns:
            File-like object or None
        """
        if storage_type == 's3':
            return self._retrieve_s3(storage_path)
        else:
            return self._retrieve_local(storage_path)

    def _retrieve_s3(self, storage_path: str) -> Optional[BinaryIO]:
        """Retrieve file from S3."""
        try:
            import io
            response = self.s3_client.get_object(Bucket=self.bucket, Key=storage_path)
            return io.BytesIO(response['Body'].read())
        except ClientError as e:
            current_app.logger.error(f"S3 retrieve error: {e}")
            return None

    def _retrieve_local(self, storage_path: str) -> Optional[BinaryIO]:
        """Retrieve file from local filesystem."""
        try:
            local_path = os.path.join('/app/artifacts', storage_path)
            if os.path.exists(local_path):
                return open(local_path, 'rb')
            return None
        except Exception as e:
            current_app.logger.error(f"Local retrieve error: {e}")
            return None

    def delete_file(self, storage_path: str, storage_type: str = 'local') -> bool:
        """Delete a file from storage.

        Args:
            storage_path: Path within storage
            storage_type: 'local' or 's3'

        Returns:
            Success boolean
        """
        if storage_type == 's3':
            return self._delete_s3(storage_path)
        else:
            return self._delete_local(storage_path)

    def _delete_s3(self, storage_path: str) -> bool:
        """Delete file from S3."""
        try:
            self.s3_client.delete_object(Bucket=self.bucket, Key=storage_path)
            return True
        except ClientError as e:
            current_app.logger.error(f"S3 delete error: {e}")
            return False

    def _delete_local(self, storage_path: str) -> bool:
        """Delete file from local filesystem."""
        try:
            local_path = os.path.join('/app/artifacts', storage_path)
            if os.path.exists(local_path):
                os.remove(local_path)
            return True
        except Exception as e:
            current_app.logger.error(f"Local delete error: {e}")
            return False

    def get_presigned_url(self, storage_path: str, expiration: int = 3600) -> Optional[str]:
        """Generate a presigned URL for S3 download.

        Args:
            storage_path: Path within S3
            expiration: URL expiration in seconds

        Returns:
            Presigned URL or None
        """
        if not self.is_s3_configured:
            return None

        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': storage_path},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            current_app.logger.error(f"Presigned URL error: {e}")
            return None


# Singleton instance
storage_service = StorageService()
