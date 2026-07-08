import time
import requests
from config import WOC_BULK_BALANCE_URL, NETWORK
from colorama import Fore, Style


def fetch_tx_hex(txid: str) -> str:
    url = f"https://api.whatsonchain.com/v1/bsv/{NETWORK}/tx/{txid}/hex"
    response = requests.get(url)
    response.raise_for_status()
    return response.text.strip()


def fetch_utxos_for_addresses(addresses: list[str]) -> list[dict]:

    all_utxos = []

    total = len(addresses)

    print(Fore.YELLOW + "\n Pobieranie UTXO...")

    for i, address in enumerate(addresses):

        # progress bar
        percent = int(((i + 1) / total) * 100)

        bar_length = 30
        filled = int(bar_length * (i + 1) / total)

        bar = "█" * filled + "-" * (bar_length - filled)

        print(
            Fore.GREEN +
            f"\r|{bar}| {percent}%  [{i+1}/{total}]",
            end="",
            flush=True
        )

        try:
            url = f"https://api.whatsonchain.com/v1/bsv/{NETWORK}/address/{address}/unspent/all"

            response = requests.get(url)
            response.raise_for_status()

            data = response.json()

            for utxo in data.get("result", []):

                all_utxos.append({
                    "txid": utxo["tx_hash"],
                    "vout": utxo["tx_pos"],
                    "value": utxo["value"],
                    "address": address,
                })

        except Exception as e:

            print(
                Fore.RED +
                f"\nBłąd pobierania UTXO dla {address}: {e}"
            )

        time.sleep(0.2)

    print(Fore.GREEN + "\n Pobieranie zakończone\n")

    return all_utxos


def fetch_balances_from_woc(addresses: list[str]) -> dict[str, int]:
    if not addresses:
        return {}

    chunk_size = 20
    balances = {}

    for i in range(0, len(addresses), chunk_size):
        chunk = addresses[i:i + chunk_size]
        response = requests.post(WOC_BULK_BALANCE_URL, json={"addresses": chunk})
        response.raise_for_status()
        for item in response.json():
            balances[item["address"]] = item["confirmed"]
        if i + chunk_size < len(addresses):
            time.sleep(0.3)

    return balances
