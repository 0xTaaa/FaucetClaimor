# OneClick Faucet Tools

A Python **all-in-one script** for:
1. **Generating EVM wallets** in bulk (`wallets.json`)
2. **Claiming faucet** automatically (HTTP API, random User-Agent, retry/backoff, HTTP/2)
3. **Transferring funds** from all wallets in `wallets.json` back to a **main wallet**

Works with most EVM-based testnet faucets that expose a simple HTTP API and **don’t require captcha/login**.

## ⚡ Features
- Generate hundreds of wallets in one run  
- Automatic faucet claim with retry, backoff, random User-Agent  
- Automatic transfer (native or ERC-20 tokens)  
- Easy configuration via `.env`  
- Logs faucet and transfer results into CSV files  
- HTTP/2 client for modern faucet servers (e.g. Caddy/NGINX)  

## 📦 Installation
1. Clone or download the repo  
2. Install Python 3.10+ (Python 3.11 recommended)  
3. Install dependencies:  
   ```bash
   pip install "web3==6.*" "eth-account==0.10.*" "httpx[http2]" python-dotenv

## ⚙️ Configuration

Create a `.env` file in the project root. Example:

```ini
# --- Generate Wallet ---
GENERATE_COUNT=50 #Count Wallet generated
WALLETS_FILE=wallets.json
FORCE_REGENERATE=false

# --- Claim Faucet ---
FAUCET_URL=https://faucet.mars.movachain.com/api/faucet/v1/transfer
FAUCET_ORIGIN=https://faucet.mars.movachain.com
FAUCET_REFERER=https://faucet.mars.movachain.com/
FAUCET_ENABLE=true
FAUCET_SLEEP_MIN=4
FAUCET_SLEEP_MAX=9
FAUCET_MAX_PER_ADDR_SECONDS=300
FAUCET_LOG=faucet_results.csv

# --- Transfer To Main Wallet ---
RPC_URL=https://<your-rpc>
MODE=native
TARGET_ADDRESS=0xYourMainWallet
AMOUNT=0.001
TOKEN_ADDRESS=0x0000000000000000000000000000000000000000 #edit for ERC20 token 
MAX_WORKERS=4
USE_EIP1559=true
SEND_LOG=send_results.csv
```

### Notes

* **FAUCET\_URL** → adjust based on your target faucet (check in DevTools → Network tab)
* Default payload: `{"to": "0x..."}`. Some faucets use `{"address": "0x..."}` → adjust in code if needed.
* **MODE**:

  * `native` → ETH/BNB/MATIC/MARS etc.
  * `erc20` → ERC-20 token (set `TOKEN_ADDRESS`).
* **AMOUNT**:

  * `native` → in Ether units (e.g. `0.001`).
  * `erc20` → in human-readable units (e.g. `10` if token decimals = 18).

---

## ▶️ Usage

Run the script:

```bash
python3 lfg.py
```

It will:

1. Generate wallets → `wallets.json`
2. Claim faucet → log in `faucet_results.csv`
3. Transfer tokens → log in `send_results.csv`

---

## 📁 Outputs

* **wallets.json** → generated wallets with addresses & private keys
* **faucet\_results.csv** → faucet claim results (ok/fail + response)
* **send\_results.csv** → transfer results (ok/error + tx hash)

---

## ⚠️ Limitations

* Works only with faucets **without captcha/login**
* All faucets have **rate-limits** (usually 1 claim / 24h per IP & per address)
* If the blockchain is **stuck/down** (no new blocks), faucet & transfers will fail
* **Never share** `wallets.json` or `.env` publicly (they contain private keys and RPC config!)

---

## 🔮 Roadmap / Ideas

* Proxy rotation support (`proxies.txt`) for multi-wallet farming
* **Disperse mode**: seed gas from one funding wallet to all wallets in `wallets.json`
* Auto-detect faucet payload (`{"to":}` vs `{"address":}`)

---

Made with ❤️ for Testnet Community.

By MikaPrjkt@PrjktSpace | Telegram: [@PeternakID](https://t.me/PeternakID)
