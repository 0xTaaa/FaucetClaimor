import os, json, math, time, random, csv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
import httpx

from web3 import Web3
from eth_account import Account

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

def ua_headers(origin, referer):
    return {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/json",
        "Origin": origin.rstrip("/") if origin else "",
        "Referer": referer or "",
        "User-Agent": random.choice(USER_AGENTS),
    }

def load_env():
    load_dotenv()
    cfg = {
        # Generate
        "GENERATE_COUNT": int(os.getenv("GENERATE_COUNT", "0")),
        "WALLETS_FILE": os.getenv("WALLETS_FILE", "wallets.json"),
        "FORCE_REGENERATE": os.getenv("FORCE_REGENERATE", "false").lower() == "true",

        # Faucet
        "FAUCET_URL": os.getenv("FAUCET_URL", "").strip(),
        "FAUCET_ORIGIN": os.getenv("FAUCET_ORIGIN", "").strip(),
        "FAUCET_REFERER": os.getenv("FAUCET_REFERER", "").strip(),
        "FAUCET_ENABLE": os.getenv("FAUCET_ENABLE", "false").lower() == "true",
        "FAUCET_SLEEP_MIN": float(os.getenv("FAUCET_SLEEP_MIN", "3")),
        "FAUCET_SLEEP_MAX": float(os.getenv("FAUCET_SLEEP_MAX", "7")),
        "FAUCET_MAX_PER_ADDR_SECONDS": int(os.getenv("FAUCET_MAX_PER_ADDR_SECONDS", "300")),
        "FAUCET_LOG": os.getenv("FAUCET_LOG", "faucet_results.csv"),

        # Transfer
        "RPC_URL": os.getenv("RPC_URL", "").strip(),
        "MODE": os.getenv("MODE", "native").strip().lower(),
        "TARGET_ADDRESS": os.getenv("TARGET_ADDRESS", "").strip(),
        "AMOUNT": os.getenv("AMOUNT", "0.0").strip(),
        "TOKEN_ADDRESS": os.getenv("TOKEN_ADDRESS", "").strip(),
        "MAX_WORKERS": int(os.getenv("MAX_WORKERS", "4")),
        "USE_EIP1559": os.getenv("USE_EIP1559", "true").lower() == "true",
        "SEND_LOG": os.getenv("SEND_LOG", "send_results.csv"),
    }
    return cfg

def generate_wallets(n, out_file, force=False):
    out = Path(out_file)
    if out.exists() and not force:
        print(f"ℹ️ {out_file} exist. skipping generate wallet (set FORCE_REGENERATE=true to replace old wallet.json).")
        return json.loads(out.read_text(encoding="utf-8"))

    wallets = []
    for _ in range(n):
        acct = Account.create()
        wallets.append({"address": acct.address, "private_key": acct.key.hex()})
    out.write_text(json.dumps(wallets, indent=2), encoding="utf-8")
    print(f"✅ Generate {n} wallet -> {out_file}")
    return wallets

def load_wallets(file_):
    p = Path(file_)
    if not p.exists():
        raise FileNotFoundError(f"{file_} Not Found.")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise RuntimeError("wallets.json invalid.")
    return data

def faucet_claim_http2(faucet_url, address, origin, referer, per_addr_timeout_sec=300):
    start = time.time()
    attempt = 0
    with httpx.Client(http2=True, timeout=30) as client:
        # warm-up
        if referer:
            try:
                client.get(referer, headers=ua_headers(origin, referer), timeout=15)
            except Exception:
                pass

        while True:
            attempt += 1
            try:
                r = client.post(faucet_url, headers=ua_headers(origin, referer), json={"to": address}, timeout=30)
                if r.status_code == 200:
                    try:
                        return True, json.dumps(r.json(), ensure_ascii=False)
                    except Exception:
                        return True, r.text.strip()[:400]
                # retryable?
                if r.status_code in (429, 502, 503, 504):
                    last = f"{r.status_code} {r.text.strip()[:200]}"
                else:
                    return False, f"{r.status_code} {r.text.strip()[:200]}"
            except httpx.RequestError as e:
                last = f"network_error: {e}"

            if time.time() - start > per_addr_timeout_sec:
                return False, f"timeout_after_{per_addr_timeout_sec}s: {last}"

            wait = min(60, 3 * (2 ** (attempt - 1))) + random.uniform(0, 2)
            time.sleep(wait)

def run_faucet_for_all(cfg, wallets):
    out = cfg["FAUCET_LOG"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["address", "ok", "response_or_error"])
        print(f"🚰 Faucet: claim for {len(wallets)} address…")
        for item in wallets:
            addr = item["address"]
            time.sleep(random.uniform(cfg["FAUCET_SLEEP_MIN"], cfg["FAUCET_SLEEP_MAX"]))
            ok, msg = faucet_claim_http2(
                cfg["FAUCET_URL"], addr, cfg["FAUCET_ORIGIN"], cfg["FAUCET_REFERER"],
                per_addr_timeout_sec=cfg["FAUCET_MAX_PER_ADDR_SECONDS"]
            )
            print(("✅" if ok else "❌"), addr, "->", msg)
            w.writerow([addr, "yes" if ok else "no", msg])
    print(f"📝 Faucet log -> {out}")

def get_web3(rpc):
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        raise RuntimeError("Cant Connect to RPC.")
    return w3

def suggest_fees(w3: Web3, use_1559: bool):
    if use_1559:
        latest = w3.eth.get_block("latest")
        base = latest.get("baseFeePerGas")
        if base is not None:
            tip = w3.to_wei(2, "gwei")
            return {"maxFeePerGas": base * 2 + tip, "maxPriorityFeePerGas": tip}
    return {"gasPrice": w3.eth.gas_price * 2}

ERC20_ABI = [
    {"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],
     "name":"transfer","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"stateMutability":"view","type":"function"},
]

def token_contract(w3, addr):
    return w3.eth.contract(address=Web3.to_checksum_address(addr), abi=ERC20_ABI)

def human_to_token(amount_str, decimals):
    return int(round(float(amount_str) * (10 ** decimals)))

def send_from_wallet(w3, mode, target, amount, token_addr, use_1559, wallet):
    addr = Web3.to_checksum_address(wallet["address"])
    pk = wallet["private_key"]
    fees = suggest_fees(w3, use_1559)
    chain_id = w3.eth.chain_id
    nonce = w3.eth.get_transaction_count(addr)

    if mode == "native":
        value = w3.to_wei(amount, "ether")
        tx = {
            "chainId": chain_id,
            "to": Web3.to_checksum_address(target),
            "value": value,
            "nonce": nonce,
            **fees
        }
        # gas estimate
        try:
            est = w3.eth.estimate_gas({"from": addr, "to": tx["to"], "value": value})
            tx["gas"] = math.ceil(est * 1.2)
        except Exception:
            tx["gas"] = 21000
    else:
        if not Web3.is_address(token_addr):
            return {"address": addr, "status": "ERROR", "error": "TOKEN_ADDRESS invalid"}
        ctr = token_contract(w3, token_addr)
        decimals = ctr.functions.decimals().call()
        amt = human_to_token(amount, decimals)
        tx = ctr.functions.transfer(Web3.to_checksum_address(target), amt).build_transaction({
            "chainId": chain_id, "from": addr, "nonce": nonce, **fees
        })
        try:
            est = w3.eth.estimate_gas(tx)
            tx["gas"] = math.ceil(est * 1.3)
        except Exception:
            tx["gas"] = 120000

    try:
        signed = w3.eth.account.sign_transaction(tx, private_key=pk)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
        tx_hash = w3.eth.send_raw_transaction(raw)
        return {"address": addr, "status": "SENT", "tx_hash": tx_hash.hex()}
    except Exception as e:
        return {"address": addr, "status": "ERROR", "error": f"{type(e).__name__}: {e}"}

def run_transfers(cfg, wallets):
    w3 = get_web3(cfg["RPC_URL"])
    mode = cfg["MODE"]
    target = cfg["TARGET_ADDRESS"]
    amount = cfg["AMOUNT"]
    token_addr = cfg["TOKEN_ADDRESS"]
    use_1559 = cfg["USE_EIP1559"]

    print(f"🚀 Transfer {mode} dari {len(wallets)} wallet -> {target}")
    results = []
    with ThreadPoolExecutor(max_workers=cfg["MAX_WORKERS"]) as ex:
        futs = [ex.submit(send_from_wallet, w3, mode, target, amount, token_addr, use_1559, w) for w in wallets]
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            if res["status"] == "SENT":
                print(f"✅ {res['address']} -> {res['tx_hash']}")
            else:
                print(f"❌ {res['address']} -> {res['status']} {res.get('error','')}")

    out = cfg["SEND_LOG"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["address","status","tx_hash","error"])
        w.writeheader()
        for r in results:
            w.writerow({"address": r.get("address"),
                        "status": r.get("status"),
                        "tx_hash": r.get("tx_hash",""),
                        "error": r.get("error","")})
    print(f"📝 Send log -> {out}")

def main():
    cfg = load_env()

    if cfg["GENERATE_COUNT"] > 0 or cfg["FORCE_REGENERATE"]:
        generate_wallets(cfg["GENERATE_COUNT"], cfg["WALLETS_FILE"], force=cfg["FORCE_REGENERATE"])

    wallets = load_wallets(cfg["WALLETS_FILE"])

    if cfg["FAUCET_ENABLE"]:
        if not cfg["FAUCET_URL"]:
            print("⚠️ FAUCET_ENABLE=true but FAUCET_URL empty, skipping faucet.")
        else:
            run_faucet_for_all(cfg, wallets)

    if not cfg["RPC_URL"]:
        print("⚠️ RPC_URL empty. skipping transfer.")
    elif not cfg["TARGET_ADDRESS"]:
        print("⚠️ TARGET_ADDRESS empty. Skipping transfer.")
    else:
        run_transfers(cfg, wallets)

if __name__ == "__main__":
    main()
