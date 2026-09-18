import shutil

import pytest

from ingest.encryption import EncryptionError, decrypt_file, encrypt_file

pytestmark = pytest.mark.skipif(shutil.which("age") is None, reason="age CLI not installed")


def test_encrypt_file_produces_age_encrypted_output(tmp_path, make_age_keypair):
    public_key, _ = make_age_keypair()
    plaintext = tmp_path / "accounts.json"
    plaintext.write_text('{"accounts": []}')

    encrypted = encrypt_file(plaintext, recipient=public_key)

    assert encrypted == tmp_path / "accounts.json.age"
    assert encrypted.exists()
    assert encrypted.read_bytes() != plaintext.read_bytes()


def test_decrypt_file_round_trips_original_content(tmp_path, make_age_keypair):
    public_key, identity = make_age_keypair()
    plaintext = tmp_path / "accounts.json"
    plaintext.write_text('{"accounts": []}')
    encrypted = encrypt_file(plaintext, recipient=public_key)

    decrypted = decrypt_file(encrypted, identity=identity, out_path=tmp_path / "decrypted.json")

    assert decrypted.read_text() == plaintext.read_text()


def test_decrypt_file_raises_on_wrong_identity(tmp_path, make_age_keypair):
    public_key, _ = make_age_keypair("key1.txt")
    _, wrong_identity = make_age_keypair("key2.txt")
    plaintext = tmp_path / "accounts.json"
    plaintext.write_text('{"accounts": []}')
    encrypted = encrypt_file(plaintext, recipient=public_key)

    with pytest.raises(EncryptionError):
        decrypt_file(encrypted, identity=wrong_identity, out_path=tmp_path / "decrypted.json")


def test_encrypt_file_raises_on_invalid_recipient(tmp_path):
    plaintext = tmp_path / "accounts.json"
    plaintext.write_text('{"accounts": []}')

    with pytest.raises(EncryptionError):
        encrypt_file(plaintext, recipient="not-a-real-recipient")
