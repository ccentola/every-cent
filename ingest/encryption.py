import subprocess
import tempfile
from pathlib import Path


class EncryptionError(Exception):
    """Raised when the age CLI fails to encrypt or decrypt a file."""


def encrypt_file(path: Path, recipient: str, out_path: Path | None = None) -> Path:
    out_path = Path(out_path) if out_path else Path(f"{path}.age")
    result = subprocess.run(
        ["age", "-r", recipient, "-o", str(out_path), str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise EncryptionError(f"age encryption failed: {result.stderr}")
    return out_path


def decrypt_file(path: Path, identity: str, out_path: Path | None = None) -> Path:
    out_path = Path(out_path) if out_path else Path(str(path).removesuffix(".age"))
    with tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False) as identity_file:
        identity_file.write(identity)
        identity_path = identity_file.name
    try:
        result = subprocess.run(
            ["age", "-d", "-i", identity_path, "-o", str(out_path), str(path)],
            capture_output=True,
            text=True,
        )
    finally:
        Path(identity_path).unlink()
    if result.returncode != 0:
        raise EncryptionError(f"age decryption failed: {result.stderr}")
    return out_path
