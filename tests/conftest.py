import subprocess

import pytest


@pytest.fixture
def make_age_keypair(tmp_path):
    def _make(name="key.txt"):
        key_path = tmp_path / name
        subprocess.run(["age-keygen", "-o", str(key_path)], check=True, capture_output=True)
        key_text = key_path.read_text()
        public_key = next(
            line.split(": ")[1].strip()
            for line in key_text.splitlines()
            if line.startswith("# public key:")
        )
        return public_key, key_text

    return _make
