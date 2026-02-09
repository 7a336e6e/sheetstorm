"""Encryption service for sensitive data"""
import os
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken


class EncryptionService:
    """Service for encrypting and decrypting sensitive data.

    Uses Fernet symmetric encryption for compromised account passwords
    and integration credentials.
    """

    _instance = None
    _fernet = None

    def __new__(cls):
        """Ensure singleton pattern — only one EncryptionService instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize Fernet cipher from the FERNET_KEY environment variable."""
        if self._fernet is None:
            key = os.getenv('FERNET_KEY')
            if key:
                self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    @property
    def is_configured(self) -> bool:
        """Check if encryption is properly configured."""
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a string value.

        Args:
            plaintext: String to encrypt

        Returns:
            Encrypted bytes

        Raises:
            RuntimeError: If encryption is not configured
        """
        if not self._fernet:
            raise RuntimeError("Encryption not configured. Set FERNET_KEY environment variable.")

        return self._fernet.encrypt(plaintext.encode('utf-8'))

    def decrypt(self, ciphertext: bytes) -> Optional[str]:
        """Decrypt encrypted bytes.

        Args:
            ciphertext: Encrypted bytes to decrypt

        Returns:
            Decrypted string or None if decryption fails

        Raises:
            RuntimeError: If encryption is not configured
        """
        if not self._fernet:
            raise RuntimeError("Encryption not configured. Set FERNET_KEY environment variable.")

        try:
            return self._fernet.decrypt(ciphertext).decode('utf-8')
        except InvalidToken:
            return None

    def encrypt_dict(self, data: dict, fields: list) -> dict:
        """Encrypt specified fields in a dictionary.

        Args:
            data: Dictionary with data
            fields: List of field names to encrypt

        Returns:
            Dictionary with specified fields encrypted
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                result[f'{field}_encrypted'] = self.encrypt(str(result[field]))
                del result[field]
        return result

    def decrypt_dict(self, data: dict, fields: list) -> dict:
        """Decrypt specified fields in a dictionary.

        Args:
            data: Dictionary with encrypted data
            fields: List of field names to decrypt (without '_encrypted' suffix)

        Returns:
            Dictionary with specified fields decrypted
        """
        result = data.copy()
        for field in fields:
            encrypted_field = f'{field}_encrypted'
            if encrypted_field in result and result[encrypted_field]:
                decrypted = self.decrypt(result[encrypted_field])
                if decrypted:
                    result[field] = decrypted
                del result[encrypted_field]
        return result

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key.

        Returns:
            Base64-encoded key string
        """
        return Fernet.generate_key().decode('utf-8')


# Singleton instance
encryption_service = EncryptionService()
