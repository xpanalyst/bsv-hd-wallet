from colorama import init, Fore, Style
from db import get_all_addresses, get_all_utxos, save_utxos
from woc import fetch_balances_from_woc, fetch_utxos_for_addresses
init(autoreset=True)


def show_utxos(db_path: str = "wallet.db"):
    utxos = get_all_utxos(db_path)
    if not utxos:
        print("\nBrak niewydanych UTXO w bazie.\n")
        return
    print(f"\n{'TXID':<65} {'Vout':>4} {'Wartość (BSV)':>14}  Adres")
    print("-" * 110)
    for txid, vout, value_sats, address, path in utxos:
        bsv = value_sats / 1e8
        print(f"{Fore.CYAN}{txid:<65}{Style.RESET_ALL} {vout:>4} {bsv:>14.8f}  {address}")
    print("-" * 110)
    total = sum(u[2] for u in utxos)
    print(f"{'Łącznie UTXO: ' + str(len(utxos)):<69} {total/1e8:>14.8f} BSV\n")


def refresh_utxos(db_path: str = "wallet.db"):
    rows = get_all_addresses(db_path)
    if not rows:
        print("Brak adresów w bazie.")
        return
    addresses = [row[2] for row in rows]
    print("\nPobieram salda żeby wyfiltrować aktywne adresy...")
    try:
        balances = fetch_balances_from_woc(addresses)
    except Exception as e:
        print(f"Błąd pobierania sald: {e}")
        return
    active = [addr for addr in addresses if balances.get(addr, 0) > 0]
    if not active:
        print("Żaden adres nie ma salda — brak UTXO do pobrania.")
        return
    print(f"Znaleziono {len(active)} aktywnych adresów. Pobieram UTXO...")
    try:
        utxos = fetch_utxos_for_addresses(active)
        save_utxos(utxos, db_path)
        print(f"Zapisano {len(utxos)} UTXO do bazy.")
    except Exception as e:
        print(f"Błąd pobierania UTXO: {e}")
        return
    show_utxos(db_path)  # ← wyświetl po odświeżeniu


def show_addresses(db_path: str = "wallet.db"):
    rows = get_all_addresses(db_path)
    if not rows:
        print("Brak adresów w bazie.")
        return

    addresses = [row[2] for row in rows]
    print("\nPobieram salda z WhatsOnChain...")
    try:
        balances = fetch_balances_from_woc(addresses)
    except Exception as e:
        print(f"Błąd pobierania sald: {e}")
        balances = {}

    # pobieramy i zapisujemy UTXO w tle
    active = [addr for addr in addresses if balances.get(addr, 0) > 0]
    if active:
        try:
            utxos = fetch_utxos_for_addresses(active)
            save_utxos(utxos, db_path)
        except Exception as e:
            print(f"Błąd zapisywania UTXO: {e}")

    # budujemy słownik {adres: [lista txid]} z bazy
    utxos_by_address = {}
    for txid, vout, value_sats, address, path in get_all_utxos(db_path):
        if address not in utxos_by_address:
            utxos_by_address[address] = []
        utxos_by_address[address].append(f"{txid[:16]}... ({value_sats} sat)")

    print(f"\n{'#':<5} {'Typ':<8} {'Adres':<40} {'Saldo (BSV)':>12}  UTXO")
    print("-" * 110)

    total = 0
    for idx, change, addr, path, label in rows:
        ch_str = "change" if change else "receive"
        sats = balances.get(addr, 0)
        bsv = sats / 1e8
        total += sats
        label_str = f"  [{label}]" if label else ""

        balance_str = (
            f"{Fore.GREEN}{bsv:>12.8f}{Style.RESET_ALL}"
            if sats > 0
            else f"{bsv:>12.8f}"
        )

        # pierwsze UTXO w tej samej linii, kolejne w liniach poniżej
        utxo_list = utxos_by_address.get(addr, [])
        first_utxo = utxo_list[0] if utxo_list else "-"

        print(f"{idx:<5} {ch_str:<8} {addr:<40} {balance_str}  {Fore.CYAN}{first_utxo}{Style.RESET_ALL}{label_str}")

        for extra_utxo in utxo_list[1:]:
            print(f"{'':>66}{Fore.CYAN}{extra_utxo}{Style.RESET_ALL}")

    print("-" * 110)
    print(f"{'RAZEM':<54} {total/1e8:>12.8f} BSV")
