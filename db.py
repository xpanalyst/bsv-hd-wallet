import sqlite3
from config import DB_FILE


def get_address_index(address: str, db_path: str = DB_FILE) -> int | None:
    """Zwraca derivation_index dla podanego adresu."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT derivation_index FROM addresses WHERE address = ?", (address,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def save_utxos(utxos: list[dict], db_path: str = DB_FILE):
    """
    Zapisuje pobrane UTXO do bazy. Przed zapisem czyści stare wpisy
    żeby nie duplikować przy kolejnych odświeżeniach.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("DELETE FROM utxos WHERE spent = 0")

    for utxo in utxos:
        cur.execute("""
            SELECT id FROM addresses WHERE address = ?
        """, (utxo["address"],))
        row = cur.fetchone()
        if row is None:
            continue
        address_index = row[0]

        cur.execute("""
            INSERT OR IGNORE INTO utxos (txid, vout, value_sats, address_index, spent)
            VALUES (?, ?, ?, ?, 0)
        """, (utxo["txid"], utxo["vout"], utxo["value"], address_index))

    conn.commit()
    conn.close()


def get_all_utxos(db_path: str = DB_FILE) -> list:
    """Zwraca wszystkie niewydane UTXO z adresami."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT u.txid, u.vout, u.value_sats, a.address, a.path
        FROM utxos u
        JOIN addresses a ON u.address_index = a.id
        WHERE u.spent = 0
        ORDER BY u.value_sats DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def init_db(db_path: str = DB_FILE):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            derivation_index INTEGER NOT NULL,
            change INTEGER NOT NULL DEFAULT 0,
            address TEXT NOT NULL UNIQUE,
            path TEXT NOT NULL,
            label TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS utxos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            txid TEXT NOT NULL,
            vout INTEGER NOT NULL,
            value_sats INTEGER NOT NULL,
            address_index INTEGER NOT NULL,
            spent INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(address_index) REFERENCES addresses(derivation_index)
        )
    """)
    conn.commit()
    conn.close()


def get_all_addresses(db_path: str = DB_FILE) -> list:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT derivation_index, change, address, path, COALESCE(label, '')
        FROM addresses
        ORDER BY change, derivation_index
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def get_max_derivation_index(change: int = 0, db_path: str = DB_FILE) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT MAX(derivation_index) FROM addresses WHERE change = ?
    """, (change,))
    row = cur.fetchone()
    conn.close()
    return -1 if row[0] is None else row[0]


def insert_address(derivation_index: int, change: int, address: str, path: str, db_path: str = DB_FILE):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO addresses (derivation_index, change, address, path)
        VALUES (?, ?, ?, ?)
    """, (derivation_index, change, address, path))
    conn.commit()
    conn.close()
