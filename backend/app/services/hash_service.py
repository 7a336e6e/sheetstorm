"""Hash computation service for evidence integrity"""
import hashlib
from typing import BinaryIO, Dict, Tuple


class HashService:
    """Service for computing file hashes for evidence integrity."""

    CHUNK_SIZE = 8192  # 8KB chunks for memory efficiency

    @staticmethod
    def compute_hashes(file_obj: BinaryIO) -> Dict[str, str]:
        """Compute MD5, SHA256, and SHA512 hashes for a file.

        Args:
            file_obj: File-like object to hash

        Returns:
            Dictionary with 'md5', 'sha256', and 'sha512' keys
        """
        md5_hash = hashlib.md5()
        sha256_hash = hashlib.sha256()
        sha512_hash = hashlib.sha512()

        # Reset file position
        file_obj.seek(0)

        # Read in chunks to handle large files
        while True:
            chunk = file_obj.read(HashService.CHUNK_SIZE)
            if not chunk:
                break
            md5_hash.update(chunk)
            sha256_hash.update(chunk)
            sha512_hash.update(chunk)

        # Reset file position for subsequent reads
        file_obj.seek(0)

        return {
            'md5': md5_hash.hexdigest(),
            'sha256': sha256_hash.hexdigest(),
            'sha512': sha512_hash.hexdigest()
        }

    @staticmethod
    def compute_hash(file_obj: BinaryIO, algorithm: str = 'sha256') -> str:
        """Compute a single hash for a file.

        Args:
            file_obj: File-like object to hash
            algorithm: Hash algorithm ('md5', 'sha256', 'sha512')

        Returns:
            Hexadecimal hash string
        """
        algorithms = {
            'md5': hashlib.md5,
            'sha256': hashlib.sha256,
            'sha512': hashlib.sha512
        }

        if algorithm not in algorithms:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        hash_obj = algorithms[algorithm]()
        file_obj.seek(0)

        while True:
            chunk = file_obj.read(HashService.CHUNK_SIZE)
            if not chunk:
                break
            hash_obj.update(chunk)

        file_obj.seek(0)
        return hash_obj.hexdigest()

    @staticmethod
    def verify_hashes(file_obj: BinaryIO, expected_hashes: Dict[str, str]) -> Tuple[bool, Dict[str, bool]]:
        """Verify file hashes against expected values.

        Args:
            file_obj: File-like object to verify
            expected_hashes: Dictionary with expected hash values

        Returns:
            Tuple of (all_match, individual_results)
        """
        computed = HashService.compute_hashes(file_obj)
        results = {}

        for algo, expected in expected_hashes.items():
            if algo in computed:
                results[algo] = computed[algo].lower() == expected.lower()

        all_match = all(results.values()) if results else False
        return all_match, results

    @staticmethod
    def hash_string(value: str, algorithm: str = 'sha256') -> str:
        """Hash a string value.

        Args:
            value: String to hash
            algorithm: Hash algorithm

        Returns:
            Hexadecimal hash string
        """
        algorithms = {
            'md5': hashlib.md5,
            'sha256': hashlib.sha256,
            'sha512': hashlib.sha512
        }

        if algorithm not in algorithms:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        return algorithms[algorithm](value.encode('utf-8')).hexdigest()
