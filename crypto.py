import os
import base64
import hmac
import hashlib
import json
import subprocess
from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from config import KEYSTORE_FILE


# parametry Argon2id
ARGON2_TIME_COST    = 3        # liczba iteracji
ARGON2_MEMORY_COST  = 65536    # 64 MB pamięci
ARGON2_PARALLELISM  = 4        # wątki
ARGON2_HASH_LEN     = 32       # długość klucza


def derive_key_from_password(password: str, salt: bytes) -> bytes:
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=Type.ID,  # Argon2id
    )


def _compute_checksum(keystore_without_checksum: dict, password: str) -> str:
    content = json.dumps(keystore_without_checksum, sort_keys=True).encode()
    return hmac.new(password.encode(), content, hashlib.sha256).hexdigest()


def encrypt_mnemonic(mnemonic: str, password: str) -> dict:
    mnemonic_bytes = bytearray(mnemonic.encode("utf-8"))
    salt = os.urandom(32)
    key = derive_key_from_password(password, salt)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, bytes(mnemonic_bytes), None)

    # czyścimy mnemonic z pamięci
    for i in range(len(mnemonic_bytes)):
        mnemonic_bytes[i] = 0

    keystore = {
        "kdf": "argon2id",
        "kdfparams": {
            "salt":        base64.b64encode(salt).decode(),
            "time_cost":   ARGON2_TIME_COST,
            "memory_cost": ARGON2_MEMORY_COST,
            "parallelism": ARGON2_PARALLELISM,
            "hash_len":    ARGON2_HASH_LEN,
        },
        "cipher": "aes-256-gcm",
        "cipherparams": {
            "nonce": base64.b64encode(nonce).decode(),
        },
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }

    # dodajemy checksum żeby wykryć modyfikację pliku
    keystore["checksum"] = _compute_checksum(keystore, password)
    return keystore


def decrypt_mnemonic(keystore: dict, password: str) -> str:
    # weryfikacja checksum przed odszyfrowaniem
    stored_checksum = keystore.pop("checksum", None)
    expected = _compute_checksum(keystore, password)
    keystore["checksum"] = stored_checksum  # przywracamy

    if not hmac.compare_digest(stored_checksum or "", expected):
        raise ValueError("Keystore został zmodyfikowany lub hasło jest błędne.")

    salt       = base64.b64decode(keystore["kdfparams"]["salt"])
    nonce      = base64.b64decode(keystore["cipherparams"]["nonce"])
    ciphertext = base64.b64decode(keystore["ciphertext"])

    key    = derive_key_from_password(password, salt)
    aesgcm = AESGCM(key)

    mnemonic_bytes = bytearray(aesgcm.decrypt(nonce, ciphertext, None))
    mnemonic = mnemonic_bytes.decode("utf-8")

    # czyścimy z pamięci
    for i in range(len(mnemonic_bytes)):
        mnemonic_bytes[i] = 0

    return mnemonic


def secure_keystore_permissions():
    """Ogranicza dostęp do pliku keystore tylko dla aktualnego użytkownika."""
    username = os.environ.get("USERNAME")
    try:
        subprocess.run(
            ["icacls", KEYSTORE_FILE, "/inheritance:r"],
            check=True, capture_output=True
        )
        subprocess.run(
            ["icacls", KEYSTORE_FILE, "/grant:r", f"{username}:F"],
            check=True, capture_output=True
        )
    except Exception as e:
        print(f"Uwaga: nie udało się ustawić uprawnień do pliku: {e}")
