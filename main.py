import nest_asyncio
nest_asyncio.apply()
import asyncio
from bsv import PrivateKey, P2PKH, Transaction, TransactionInput, TransactionOutput, WhatsOnChainBroadcaster
from bsv.constants import BIP44_DERIVATION_PATH
from bsv.hd import bip44_derive_xprvs_from_mnemonic
from woc import fetch_tx_hex
from hdp import get_private_key_for_index
from db import get_address_index, get_all_utxos, get_max_derivation_index, insert_address
from config import KEYSTORE_FILE, DB_FILE, NETWORK
from colorama import init, Fore, Style
import os
import json
from getpass import getpass
from config import KEYSTORE_FILE, DB_FILE
from crypto import encrypt_mnemonic, decrypt_mnemonic, secure_keystore_permissions
from db import init_db
from hdp import generate_mnemonic, insert_addresses, generate_next_address
from ui import show_addresses, refresh_utxos


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")



def wallet_exists() -> bool:
    return os.path.exists(KEYSTORE_FILE)



def validate_address(address: str) -> bool:
    try:
        from bsv.base58 import base58check_decode
        decoded = base58check_decode(address)

        if len(decoded) != 21:
            return False

        prefix = decoded[0]

        if NETWORK == "test":
            return prefix == 0x6f
        else:
            return prefix == 0x00

    except Exception as e:
        return False


def load_mnemonic_from_keystore(password: str) -> str:
    with open(KEYSTORE_FILE, "r") as f:
        keystore = json.load(f)
    return decrypt_mnemonic(keystore, password)


def create_new_wallet():
    mnemonic = generate_mnemonic()
    print("NOWY MNEMONIC (ZAPISZ NA KARTCE!):")
    print(mnemonic)

    while True:
        password = getpass("Ustaw hasło: ")
        password_confirm = getpass("Potwierdź hasło: ")
        if password == password_confirm:
            break
        print("Hasła nie są zgodne, spróbuj ponownie.\n")

    keystore = encrypt_mnemonic(mnemonic, password)
    with open(KEYSTORE_FILE, "w") as f:
        json.dump(keystore, f, indent=2)

    secure_keystore_permissions()  # ← nowe

    init_db(DB_FILE)
    insert_addresses(mnemonic, count=10, db_path=DB_FILE)
    print(f"\nPortfel utworzony. Dodano 10 adresów odbiorczych.")
    mnemonic = password = password_confirm = ""


def unlock_and_show_addresses():
    if not wallet_exists():
        print("Brak keystore. Najpierw utwórz portfel (opcja 1).")
        return
    password = getpass("Hasło do keystore: ")
    try:
        mnemonic = load_mnemonic_from_keystore(password)
    except Exception as e:
        print(f"Błąd odszyfrowania: {e}")
        return
    if not os.path.exists(DB_FILE):
        init_db(DB_FILE)
        insert_addresses(mnemonic, count=10, db_path=DB_FILE)
    show_addresses(DB_FILE)
    mnemonic = password = ""


def unlock_and_generate_address():
    if not wallet_exists():
        print("Brak keystore.")
        return
    password = getpass("Hasło do keystore: ")
    try:
        mnemonic = load_mnemonic_from_keystore(password)
    except Exception as e:
        print(f"Błąd odszyfrowania: {e}")
        return
    idx, addr, path = generate_next_address(mnemonic)
    print(f"\nNowy adres dodany:\nIndex: {idx}\nAdres: {addr}\nPath : {path}")
    mnemonic = password = ""


async def _broadcast(inputs_data: list, output_address: str, change_address: str, mnemonic: str):
    """Buduje, podpisuje i rozgłasza transakcję."""
    tx = Transaction()

    for item in inputs_data:
        tx_hex = fetch_tx_hex(item["txid"])
        private_key = get_private_key_for_index(mnemonic, item["derivation_index"])

        tx.add_input(TransactionInput(
            source_transaction=Transaction.from_hex(tx_hex),
            source_output_index=item["vout"],
            unlocking_script_template=P2PKH().unlock(private_key),
        ))
        # czyścimy klucz po użyciu
        private_key = None

    # output do odbiorcy
    tx.add_output(TransactionOutput(
        locking_script=P2PKH().lock(output_address),
        satoshis=inputs_data[0]["amount_to_send"],
    ))

    # reszta wraca na nasz kolejny adres
    tx.add_output(TransactionOutput(
        locking_script=P2PKH().lock(change_address),
        change=True,
    ))

    tx.fee()
    tx.sign()

    response = await tx.broadcast(WhatsOnChainBroadcaster(NETWORK))
    print(f"\nStatus: {response.status}")
    try:
        print(f"Opis: {response.description}")
    except:
        pass
    print(f"TXID: {tx.txid()}")


def send_transaction():
    if not wallet_exists():
        print("Brak portfela.")
        return

    # pobieramy UTXO z bazy
    utxos = get_all_utxos(DB_FILE)
    if not utxos:
        print("Brak UTXO w bazie. Użyj opcji 2 żeby odświeżyć.")
        return

    # wyświetlamy dostępne UTXO
    print("\nDostępne UTXO:")
    total_available = sum(u[2] for u in utxos)
    for txid, vout, value_sats, address, path in utxos:
        print(f"  {txid[:20]}... | {value_sats} sat | {address}")
    print(f"Łącznie dostępne: {total_available} sat\n")

    # pytamy o dane transakcji
    output_address = input("Adres odbiorcy: ").strip()

    if not validate_address(output_address):
        print("Nieprawidłowy adres BSV. Sprawdź czy dobrze skopiowałeś.")
        return
    
    try:
        amount_sats = int(input("Kwota do wysłania (satoshi): ").strip())
    except ValueError:
        print("Nieprawidłowa kwota.")
        return

    if amount_sats <= 0:
        print("Kwota musi być większa od zera.")
        return

    if amount_sats > total_available:
        print(f"Za mało środków. Masz {total_available} sat, chcesz wysłać {amount_sats} sat.")
        return

    # sortujemy UTXO od największego żeby używać jak najmniej wejść
    utxos_sorted = sorted(utxos, key=lambda u: u[2], reverse=True)

    selected = []
    selected_total = 0
    for txid, vout, value_sats, address, path in utxos_sorted:
        selected.append({
            "txid": txid,
            "vout": vout,
            "value_sats": value_sats,
            "address": address,
            "amount_to_send": amount_sats,
        })
        selected_total += value_sats
        if selected_total >= amount_sats:
            break

    print(f"\nWybrano {len(selected)} UTXO pokrywających {selected_total} sat.")

    # odblokowujemy portfel
    password = getpass("Hasło do keystore: ")
    try:
        mnemonic = load_mnemonic_from_keystore(password)
    except Exception:
        print("Błędne hasło.")
        return
    finally:
        password = ""

    # dla każdego UTXO pobieramy derivation_index
    inputs_data = []
    for utxo in selected:
        idx = get_address_index(utxo["address"], DB_FILE)
        if idx is None:
            print(f"Nie znaleziono indeksu dla adresu {utxo['address']}")
            mnemonic = ""
            return
        inputs_data.append({
            "txid":             utxo["txid"],
            "vout":             utxo["vout"],
            "derivation_index": idx,
            "amount_to_send":   amount_sats,
        })

    # adres reszty — kolejny wolny adres w naszym portfelu
    next_index = get_max_derivation_index(change=0, db_path=DB_FILE) + 1
    change_keys = bip44_derive_xprvs_from_mnemonic(
        mnemonic,
        next_index,
        next_index + 1,
        path=BIP44_DERIVATION_PATH,
        change=0,
        network="testnet",
    )
    change_address = change_keys[0].address()

    # zapisujemy adres reszty do bazy żeby go nie zgubić
    insert_address(next_index, 0, change_address, f"{BIP44_DERIVATION_PATH}/0/{next_index}", DB_FILE)
    print(f"Adres reszty: {change_address}")

    # potwierdzenie przed wysłaniem
    print(f"\nPodsumowanie:")
    print(f"  Odbiorca : {output_address}")
    print(f"  Kwota    : {amount_sats} sat ({amount_sats / 1e8:.8f} BSV)")
    print(f"  Reszta na: {change_address}")
    confirm = input("\nWysłać? (tak/nie): ").strip().lower()

    if confirm != "tak":
        print("Anulowano.")
        mnemonic = ""
        return

    try:
        asyncio.run(_broadcast(inputs_data, output_address, change_address, mnemonic))
    except Exception as e:
        print(f"Błąd podczas wysyłania: {e}")
    finally:
        mnemonic = ""



def main_menu():
    clear_screen()
    while True:
        print(Fore.GREEN + "=" * 35)
        print(Fore.GREEN + "           PORTFEL BSV ")
        print(Fore.GREEN + "=" * 35)
        print("1. Utwórz nowy portfel")
        print("2. Odblokuj portfel i wyświetl adresy")
        print("3. Wygeneruj nowy adres")
        print("4. Odśwież UTXO")
        print("5. Wyślij transakcję")
        print("6. Wyjście")

        choice = input(
            Fore.YELLOW + "\nWybierz opcję (1-6): "
        ).strip()
        clear_screen()

        if choice == "1":
            if wallet_exists():
                print("Keystore już istnieje – nie tworzę drugiego.")
            else:
                create_new_wallet()
        elif choice == "2":
            unlock_and_show_addresses()
        elif choice == "3":
            unlock_and_generate_address()
        elif choice == "4":
            refresh_utxos(DB_FILE)
        elif choice == "5":
            send_transaction()
        elif choice == "6":
            print("Zamykam program.")
            break
        else:
            print("Nieprawidłowy wybór.")

        input("\nNaciśnij ENTER aby wrócić do menu...")
        clear_screen()


if __name__ == "__main__":
    main_menu()
