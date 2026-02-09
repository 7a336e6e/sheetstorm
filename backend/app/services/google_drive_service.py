"""Google Drive integration service for artifact upload and case folder management.

Supports OAuth2 linking, automatic CASE-xxxx directory creation with standard
IR folder structure, file upload, and listing.
"""
import io
import json
from typing import Optional, Dict, Any, List, Tuple
from flask import current_app


class GoogleDriveService:
    """Service for Google Drive operations.

    Directory structure created per incident:
        <root_directory>/
        └── CASE-<incident_number>/
            ├── Artifacts/
            ├── Evidence/
            ├── Logs/
            ├── Reports/
            └── Notes/
    """

    CASE_SUBFOLDERS = ['Artifacts', 'Evidence', 'Logs', 'Reports', 'Notes']

    def __init__(self):
        """Initialize with lazy-loaded Google API client."""
        self._credentials_cache: Dict[str, Any] = {}

    @staticmethod
    def get_oauth_config() -> Dict[str, str]:
        """Get Google OAuth2 configuration from app config."""
        return {
            'client_id': current_app.config.get('GOOGLE_DRIVE_CLIENT_ID', ''),
            'client_secret': current_app.config.get('GOOGLE_DRIVE_CLIENT_SECRET', ''),
            'redirect_uri': current_app.config.get(
                'GOOGLE_DRIVE_REDIRECT_URI',
                'http://127.0.0.1:5000/api/v1/google-drive/oauth/callback'
            ),
        }

    @staticmethod
    def is_configured() -> bool:
        """Check if Google Drive OAuth is configured."""
        return bool(
            current_app.config.get('GOOGLE_DRIVE_CLIENT_ID')
            and current_app.config.get('GOOGLE_DRIVE_CLIENT_SECRET')
        )

    def get_auth_url(self, state: str = '') -> str:
        """Generate Google OAuth2 authorization URL.

        Args:
            state: CSRF state parameter

        Returns:
            Authorization URL string
        """
        config = self.get_oauth_config()
        from urllib.parse import urlencode

        params = {
            'client_id': config['client_id'],
            'redirect_uri': config['redirect_uri'],
            'response_type': 'code',
            'scope': 'https://www.googleapis.com/auth/drive.file',
            'access_type': 'offline',
            'prompt': 'consent',
            'state': state,
        }

        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Dict with access_token, refresh_token, expires_in
        """
        import requests
        config = self.get_oauth_config()

        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'code': code,
                'client_id': config['client_id'],
                'client_secret': config['client_secret'],
                'redirect_uri': config['redirect_uri'],
                'grant_type': 'authorization_code',
            },
        )

        if response.status_code != 200:
            current_app.logger.error(f"Google OAuth token exchange failed: {response.text}")
            raise ValueError(f"Token exchange failed: {response.json().get('error_description', 'Unknown error')}")

        return response.json()

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh an expired access token.

        Args:
            refresh_token: The refresh token from initial OAuth

        Returns:
            Dict with new access_token, expires_in
        """
        import requests
        config = self.get_oauth_config()

        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'refresh_token': refresh_token,
                'client_id': config['client_id'],
                'client_secret': config['client_secret'],
                'grant_type': 'refresh_token',
            },
        )

        if response.status_code != 200:
            raise ValueError("Failed to refresh access token")

        return response.json()

    def _get_headers(self, access_token: str) -> Dict[str, str]:
        """Build authorization headers."""
        return {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }

    def get_user_info(self, access_token: str) -> Dict[str, str]:
        """Get the authenticated user's Google Drive info.

        Returns:
            Dict with user email and storage quota info
        """
        import requests

        response = requests.get(
            'https://www.googleapis.com/drive/v3/about?fields=user,storageQuota',
            headers=self._get_headers(access_token),
        )
        response.raise_for_status()
        data = response.json()

        return {
            'email': data.get('user', {}).get('emailAddress', ''),
            'display_name': data.get('user', {}).get('displayName', ''),
            'storage_used': data.get('storageQuota', {}).get('usage', '0'),
            'storage_limit': data.get('storageQuota', {}).get('limit', '0'),
        }

    def list_folders(self, access_token: str, parent_id: str = 'root') -> List[Dict[str, str]]:
        """List folders in a given parent directory.

        Args:
            access_token: Valid Google access token
            parent_id: Parent folder ID (default 'root')

        Returns:
            List of folder dicts with id, name
        """
        import requests

        query = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        response = requests.get(
            'https://www.googleapis.com/drive/v3/files',
            headers=self._get_headers(access_token),
            params={
                'q': query,
                'fields': 'files(id,name,createdTime)',
                'orderBy': 'name',
                'pageSize': 100,
            },
        )
        response.raise_for_status()

        return response.json().get('files', [])

    def create_folder(self, access_token: str, name: str, parent_id: str = 'root') -> Dict[str, str]:
        """Create a folder in Google Drive.

        Args:
            access_token: Valid Google access token
            name: Folder name
            parent_id: Parent folder ID

        Returns:
            Dict with id, name of created folder
        """
        import requests

        metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id],
        }

        response = requests.post(
            'https://www.googleapis.com/drive/v3/files',
            headers={
                **self._get_headers(access_token),
                'Content-Type': 'application/json',
            },
            json=metadata,
        )
        response.raise_for_status()

        return response.json()

    def find_folder(self, access_token: str, name: str, parent_id: str = 'root') -> Optional[Dict[str, str]]:
        """Find a folder by name in a parent directory.

        Returns:
            Folder dict or None if not found
        """
        import requests

        query = (
            f"'{parent_id}' in parents "
            f"and name='{name}' "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        response = requests.get(
            'https://www.googleapis.com/drive/v3/files',
            headers=self._get_headers(access_token),
            params={'q': query, 'fields': 'files(id,name)', 'pageSize': 1},
        )
        response.raise_for_status()

        files = response.json().get('files', [])
        return files[0] if files else None

    def ensure_case_structure(
        self,
        access_token: str,
        root_folder_id: str,
        incident_number: int,
    ) -> Dict[str, str]:
        """Ensure the CASE-xxxx folder structure exists, creating it if needed.

        Args:
            access_token: Valid Google access token
            root_folder_id: ID of the root incidents folder
            incident_number: Incident number for folder name

        Returns:
            Dict mapping subfolder name → folder ID
            e.g. {'case': 'id', 'Artifacts': 'id', 'Reports': 'id', ...}
        """
        case_name = f"CASE-{incident_number:04d}"
        result = {}

        # Find or create case folder
        case_folder = self.find_folder(access_token, case_name, root_folder_id)
        if not case_folder:
            case_folder = self.create_folder(access_token, case_name, root_folder_id)
        result['case'] = case_folder['id']

        # Find or create subfolders
        for subfolder in self.CASE_SUBFOLDERS:
            folder = self.find_folder(access_token, subfolder, case_folder['id'])
            if not folder:
                folder = self.create_folder(access_token, subfolder, case_folder['id'])
            result[subfolder] = folder['id']

        return result

    def upload_file(
        self,
        access_token: str,
        folder_id: str,
        filename: str,
        content: bytes,
        mime_type: str = 'application/octet-stream',
    ) -> Dict[str, Any]:
        """Upload a file to a Google Drive folder.

        Args:
            access_token: Valid Google access token
            folder_id: Target folder ID
            filename: Name for the file in Drive
            content: File content as bytes
            mime_type: MIME type of the file

        Returns:
            Dict with id, name, webViewLink of uploaded file
        """
        import requests

        # Use multipart upload for files
        metadata = json.dumps({
            'name': filename,
            'parents': [folder_id],
        })

        boundary = '----SheetStormUploadBoundary'
        body = (
            f'--{boundary}\r\n'
            f'Content-Type: application/json; charset=UTF-8\r\n\r\n'
            f'{metadata}\r\n'
            f'--{boundary}\r\n'
            f'Content-Type: {mime_type}\r\n\r\n'
        ).encode('utf-8') + content + f'\r\n--{boundary}--\r\n'.encode('utf-8')

        response = requests.post(
            'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink,size',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': f'multipart/related; boundary={boundary}',
            },
            data=body,
        )
        response.raise_for_status()

        return response.json()

    def list_files(
        self,
        access_token: str,
        folder_id: str,
    ) -> List[Dict[str, Any]]:
        """List files in a Google Drive folder.

        Args:
            access_token: Valid Google access token
            folder_id: Folder ID to list

        Returns:
            List of file dicts with id, name, mimeType, size, createdTime
        """
        import requests

        query = f"'{folder_id}' in parents and trashed=false"
        response = requests.get(
            'https://www.googleapis.com/drive/v3/files',
            headers=self._get_headers(access_token),
            params={
                'q': query,
                'fields': 'files(id,name,mimeType,size,createdTime,webViewLink)',
                'orderBy': 'createdTime desc',
                'pageSize': 100,
            },
        )
        response.raise_for_status()

        return response.json().get('files', [])

    def delete_file(self, access_token: str, file_id: str) -> bool:
        """Delete a file from Google Drive.

        Returns:
            True if deleted successfully
        """
        import requests

        response = requests.delete(
            f'https://www.googleapis.com/drive/v3/files/{file_id}',
            headers=self._get_headers(access_token),
        )
        return response.status_code == 204


# Singleton instance
google_drive_service = GoogleDriveService()
