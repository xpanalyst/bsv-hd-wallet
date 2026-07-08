from bsv.hd import mnemonic_from_entropy, bip44_derive_xprvs_from_mnemonic
from bsv.constants import BIP44_DERIVATION_PATH
from bsv import PrivateKey
import secrets
from db import get_max_derivation_index, insert_address, init_db
from config import DB_FILE


def get_private_key_for_index(mnemonic: str, derivation_index: int) -> PrivateKey:
    keys = bip44_derive_xprvs_from_mnemonic(
        mnemonic,
        derivation_index,
        derivation_index + 1,
        path=BIP44_DERIVATION_PATH,
        change=0,
        network="testnet",
    )
    xprv = keys[0]

    return PrivateKey(xprv.private_key().wif())


def generate_mnemonic() -> str:
    entropy = secrets.token_bytes(32)
    return mnemonic_from_entropy(entropy)


def insert_addresses(mnemonic: str, count: int = 10, db_path: str = DB_FILE):
    keys = bip44_derive_xprvs_from_mnemonic(
        mnemonic,
        0,
        count,
        path=BIP44_DERIVATION_PATH,
        change=0,
        network="testnet",
    )
    for i, key in enumerate(keys):
        insert_address(i, 0, key.address(), f"{BIP44_DERIVATION_PATH}/0/{i}", db_path)


def generate_next_address(mnemonic: str, db_path: str = DB_FILE) -> tuple:
    mnemonic_bytes = bytearray(mnemonic.encode())
    try:
        next_index = get_max_derivation_index(change=0, db_path=db_path) + 1
        keys = bip44_derive_xprvs_from_mnemonic(
            mnemonic_bytes.decode(),
            next_index,
            next_index + 1,
            path=BIP44_DERIVATION_PATH,
            change=0,
            network="testnet",
        )
        key = keys[0]
        addr = key.address()
        path = f"{BIP44_DERIVATION_PATH}/0/{next_index}"
        insert_address(next_index, 0, addr, path, db_path)
        return next_index, addr, path
    finally:

        for i in range(len(mnemonic_bytes)):
            mnemonic_bytes[i] = 0
