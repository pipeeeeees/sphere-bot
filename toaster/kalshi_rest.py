import os
import requests

# Example usage:
#   python toaster/kalshi_rest.py WC-2026-ARG
# or:
#   TICKER=WC-2026-ARG python toaster/kalshi_rest.py

ticker = os.environ.get("TICKER") or (os.sys.argv[1] if len(os.sys.argv) > 1 else "WC-2026-ARG")
url = f"https://external-api.kalshi.com/trade-api/v2/markets/{ticker}"

response = requests.get(url, timeout=20)
response.raise_for_status()
data = response.json()

market = data.get("market") or {}
yes_price = market.get("yes_ask") or market.get("yes_bid") or market.get("last_price")

if yes_price is None:
    print(f"No price found for market {ticker}")
else:
    print(f"Current cost for a 'Yes' contract on {ticker}: {yes_price} cents")
