import asyncio
import aiohttp
import json
import time
import random
import string
import re
import os
import sys
import datetime
import requests
from urllib.parse import urlparse, parse_qs, urlencode, urljoin, urlunparse
import ddddocr
from aiohttp_socks import ProxyConnector

# ==================== CONFIGURATION ====================
# သင့်ရဲ့ GitHub မှ licenses.json ၏ Raw Link
LICENSE_URL = "https://raw.githubusercontent.com/SmvpnVip/my-vpn-tool/main/licenses.json"
AUTH_CACHE_FILE = ".auth_cache"
PORTAL_URL_PATH = "portal_url_"
PROXY_FILE = "proxies.txt"

TIMEOUT_SEC = 15  
NUM_WORKERS = 1000  

# ANSI color codes
bcyan = "\033[1;36m"
bgreen = "\033[1;32m"
bred = "\033[1;31m"
yellow = "\033[33m"
reset = "\033[0m"

def show_banner():
    try:
        os.system('clear' if os.name == 'posix' else 'cls')
    except:
        pass
    print(f"{bcyan}="*55)
    print(f"   ⚡ RUIJIE  ASYNC EXTREME  ⚡   ")
    print(f"     Telegram@trenzych       ")
    print(f"{bcyan}="*55 + f"{reset}")

# ==================== TELEGRAM ID AUTHENTICATION ====================
def authenticate_user():
    show_banner()
    print("First-time Setup · Telegram ID Authentication")
    
    telegram_id = ""
    if os.path.exists(AUTH_CACHE_FILE):
        try:
            with open(AUTH_CACHE_FILE, "r") as f:
                telegram_id = f.read().strip()
        except:
            pass

    if not telegram_id:
        print("[*] Enter your Telegram ID once (will be remembered)")
        print("[*] Example: 123456789")
        telegram_id = input(f"{bcyan}[ID] Telegram ID: {reset}").strip()
        if telegram_id:
            with open(AUTH_CACHE_FILE, "w") as f:
                f.write(telegram_id)

    print("\nChecking authorization...")
    
    try:
        response = requests.get(LICENSE_URL, timeout=10)
        if response.status_code != 200:
            print(f"{bred}[x] Error connecting to license server.{reset}")
            sys.exit(1)
            
        licenses = response.json()
    except Exception as e:
        print(f"{bred}[x] Connection failed: {e}{reset}")
        sys.exit(1)

    if telegram_id in licenses:
        expire_str = licenses[telegram_id]
        expire_date = datetime.datetime.strptime(expire_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now()

        if now < expire_date:
            left = expire_date - now
            days = left.days
            hours, remainder = divmod(left.seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            print(f"{bgreen}[+] Access Granted! (Verified){reset}")
            print(f"[*] Expires : {expire_str}")
            print(f"[*] Left    : {days}d {hours}h {minutes}m")
            print("="*55)
            time.sleep(2)
        else:
            print(f"{bred}[x] Access Denied: License Expired on {expire_str}!{reset}")
            sys.exit(1)
    else:
        print(f"{bred}[x] Access Denied: Telegram ID ({telegram_id}) not found in license list!{reset}")
        if os.path.exists(AUTH_CACHE_FILE):
            os.remove(AUTH_CACHE_FILE)
        sys.exit(1)

# ==================== PROXY MANAGER ====================
class ProxyManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.proxies = []
        self.bad_proxies = {}
        self.index = 0
        self.lock = asyncio.Lock()
        self.load()

    def _normalize(self, proxy: str):
        proxy = proxy.strip()
        if not proxy:
            return None
        if not proxy.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
            proxy = 'http://' + proxy
        return proxy

    def load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r') as f:
                raw = [line.strip() for line in f if line.strip()]
            self.proxies = [p for p in (self._normalize(r) for r in raw) if p]
        else:
            self.proxies = []

    async def get_next(self):
        async with self.lock:
            if not self.proxies:
                return None
            proxy = self.proxies[self.index % len(self.proxies)]
            self.index += 1
            return proxy

# ==================== MAIN PROGRAM ====================
async def main():
    print(f"\n{bgreen}[+] Authentication Successful! Tool is ready.{reset}")
    portal_url = input("Enter Portal (Session) URL: ").strip()
    if not portal_url:
        print("URL cannot be empty!")
        return
    
    print("Scanner is running... (Press Ctrl+C to stop)")
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    authenticate_user()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")

