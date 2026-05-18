import sys
import os
import socket
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import csv
import random
import io
import threading
import queue
import json
from datetime import datetime, timedelta
from collections import defaultdict
import streamlit as st
import streamlit.components.v1 as components
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from streamlit_cookies_manager import CookieManager

# 🌟 全域防護鎖 (保護跨執行緒共享的變數)
GLOBAL_LOCK = threading.Lock()

# 🛡️ 究極防護一：強制 Requests 永遠只准走 IPv4！
import urllib3.util.connection as urllib3_cn


def allowed_gai_family():
    return socket.AF_INET


urllib3_cn.allowed_gai_family = allowed_gai_family


def parse_saved_bs_api_keys(raw_keys):
    if not raw_keys:
        return []
    if isinstance(raw_keys, list):
        return [k.strip() for k in raw_keys if k and k.strip()]
    try:
        parsed = json.loads(raw_keys)
        if isinstance(parsed, list):
            return [str(k).strip() for k in parsed if str(k).strip()]
    except Exception:
        pass
    try:
        return [k.strip() for k in raw_keys.replace(",", "\n").splitlines() if k.strip()]
    except Exception:
        return []


def ios_cookie_fallback(cookies_to_set: dict = None, cookies_to_delete: list = None):
    if cookies_to_set is None:
        cookies_to_set = {}
    if cookies_to_delete is None:
        cookies_to_delete = []
    js_cookies = json.dumps(cookies_to_set)
    js_delete = json.dumps(cookies_to_delete)
    script = f"""
<script>
(function() {{
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  if (!isIOS) {{
    return;
  }}
  const parentDoc = (window.parent || window).document;
  const setCookie = (name, value) => {{
    const expires = new Date(Date.now() + 31536000000).toUTCString();
    let cookie = encodeURIComponent(name) + '=' + encodeURIComponent(value);
    cookie += '; expires=' + expires + '; path=/;';
    if (window.location.protocol === 'https:') {{
      cookie += ' Secure; SameSite=None;';
    }} else {{
      cookie += ' SameSite=Lax;';
    }}
    parentDoc.cookie = cookie;
  }};
  const deleteCookie = (name) => {{
    let cookie = encodeURIComponent(name) + '=; max-age=0; path=/;';
    if (window.location.protocol === 'https:') {{
      cookie += ' Secure; SameSite=None;';
    }} else {{
      cookie += ' SameSite=Lax;';
    }}
    parentDoc.cookie = cookie;
  }};
  const cookies = {js_cookies};
  const deleteKeys = {js_delete};
  Object.entries(cookies).forEach(([name, value]) => setCookie(name, value));
  deleteKeys.forEach((name) => deleteCookie(name));
}})();
</script>
"""
    components.html(script, height=0)

# 🚀 終極網路引擎：企業級 HTTP Session 連線池 (搭配 RoyaleAPI Proxy)
# 建立一個全局共享的 Session，讓所有執行緒共用 TCP 連線，模擬真實瀏覽器的 Keep-Alive 行為
HTTP_SESSION = requests.Session()
# 設定連線池大小為 20 (足夠支援 16 核心)，並加入遇到 429 時的自動退避重試機制
retry_strategy = Retry(
    total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
)
adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry_strategy)
HTTP_SESSION.mount("https://", adapter)
HTTP_SESSION.mount("http://", adapter)


# Helper: 建立針對單一 API key 的 Session（每個 key 建一個 session）
def create_http_session(api_key: str):
    s = requests.Session()
    # 使用與全域相同的 adapter 設定以共享連線池性質
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    if api_key:
        s.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
    return s


# Helper: 依 worker id 取得應該使用的 session（若未設定多 session，回退到全域 HTTP_SESSION）
def get_session_for_worker(worker_id: int):
    try:
        sessions = st.session_state.get("http_sessions")
        if sessions and len(sessions) > 0:
            return sessions[worker_id % len(sessions)]
    except Exception:
        pass
    return HTTP_SESSION

# ================= 網頁基本設定 =================
st.set_page_config(page_title="👑 K将軍 荒野戰術大廳", layout="wide", page_icon="🏆")

# ================= 初始化 Cookie 管理器 (強化版) =================
import time as time_module

try:
    cookies = CookieManager(path="/")
    # 🔄 多次嘗試初始化，確保 Cookie 準備就緒
    retry_count = 0
    while not cookies.ready() and retry_count < 20:
        time_module.sleep(0.1)
        retry_count += 1
    if not cookies.ready():
        st.warning("⚠️ Cookie 管理器初始化失敗，部分功能可能不可用")
except Exception as e:
    st.warning(f"⚠️ Cookie 初始化錯誤: {str(e)}")
    cookies = None

# ================= API 設定 =================
BASE_URL = "https://bsproxy.royaleapi.dev/"

# ================= 0. 系統安全驗證 (密碼鎖) =================
try:
    SYSTEM_PASSWORD = st.secrets["APP_PASSWORD"]
except:
    SYSTEM_PASSWORD = "KGeneral2026"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 K将軍 戰術大廳 - 系統鎖定")
    st.markdown("請輸入專屬密碼以啟動系統核心。")

    # 🍪 嘗試從 Cookie 讀取已保存的密碼
    saved_pwd = ""
    if cookies is not None:
        try:
            saved_pwd = cookies.get("system_password", "")
        except:
            saved_pwd = ""

    # 如果有已保存的密碼，嘗試自動登錄
    if saved_pwd and saved_pwd == SYSTEM_PASSWORD:
        st.session_state.authenticated = True
        st.success("✅ 自動驗證成功，系統解鎖中...")
        time.sleep(0.5)
        st.rerun()

    col_pwd1, col_pwd2 = st.columns([1, 2])
    with col_pwd1:
        pwd_input = st.text_input(
            "🔑 請輸入密碼",
            type="password",
            value=saved_pwd if saved_pwd != SYSTEM_PASSWORD else "",
        )
        save_pwd = st.checkbox("💾 記住密碼 (Cookie 存儲)", value=bool(saved_pwd))
        if st.button("解鎖系統", type="primary", use_container_width=True):
            if pwd_input == SYSTEM_PASSWORD:
                st.session_state.authenticated = True
                # 💾 保存密碼到 Cookie
                if save_pwd and cookies is not None:
                    try:
                        cookies["system_password"] = pwd_input
                        cookies.save()
                        ios_cookie_fallback({"system_password": pwd_input}, [])
                        st.success("💾 密碼已保存到瀏覽器 Cookie")
                    except Exception as e:
                        st.warning(f"⚠️ 無法保存密碼到 Cookie: {str(e)}")
                elif not save_pwd and cookies is not None:
                    # 清除 Cookie 中的密碼
                    try:
                        if "system_password" in cookies:
                            cookies["system_password"] = None
                            cookies.save()
                            ios_cookie_fallback({}, ["system_password"])
                    except:
                        pass
                st.success("✅ 密碼正確，系統解鎖中...")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ 密碼錯誤，拒絕存取！")
    st.stop()

# ================= 1. 全域快取記憶體 (Session State) =================
raw_bs_key = ""
try:
    raw_bs_key = st.secrets["BRAWL_STARS_API_KEY"]
except:
    pass
safe_bs_key = raw_bs_key.replace('"', "").replace("'", "").strip()

raw_gem_key = ""
try:
    raw_gem_key = st.secrets["GEMINI_API_KEY"]
except:
    pass

# 🍪 從 Cookie 或環境變量讀取 API KEY (強化版)
if "bs_api_key" not in st.session_state:
    # 優先從 Cookie 讀取，其次從環境變量
    if cookies is not None:
        try:
            st.session_state.bs_api_key = (
                cookies.get("bs_api_key", safe_bs_key) or safe_bs_key
            )
        except:
            st.session_state.bs_api_key = safe_bs_key
    else:
        st.session_state.bs_api_key = safe_bs_key

if "bs_api_keys" not in st.session_state:
    # 優先從 Cookie 讀取多 key 字串，其次使用單一 key
    try:
        raw_keys = None
        if cookies is not None:
            raw_keys = cookies.get("bs_api_keys", None)
        keys = parse_saved_bs_api_keys(raw_keys)
        if keys:
            st.session_state.bs_api_keys = keys
        else:
            st.session_state.bs_api_keys = [st.session_state.bs_api_key] if st.session_state.bs_api_key else []
    except Exception:
        st.session_state.bs_api_keys = [st.session_state.bs_api_key] if st.session_state.bs_api_key else []

if "gemini_api_key" not in st.session_state:
    if cookies is not None:
        try:
            st.session_state.gemini_api_key = (
                cookies.get("gemini_api_key", raw_gem_key) or raw_gem_key
            )
        except:
            st.session_state.gemini_api_key = raw_gem_key
    else:
        st.session_state.gemini_api_key = raw_gem_key

if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "active_tasks" not in st.session_state:
    st.session_state.active_tasks = 0
if "rooms_data" not in st.session_state:
    st.session_state.rooms_data = []
if "solo_stats" not in st.session_state:
    st.session_state.solo_stats = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: {"played": 0, "wins": 0}))
    )
if "solo_data" not in st.session_state:
    st.session_state.solo_data = []
if "logs" not in st.session_state:
    st.session_state.logs = []
if "scraper_modes" not in st.session_state:
    st.session_state.scraper_modes = ["rooms"]
if "duration" not in st.session_state:
    st.session_state.duration = 60
if "worker_count" not in st.session_state:
    st.session_state.worker_count = 4
if "export_filename" not in st.session_state:
    st.session_state.export_filename = "brawl_data"

if "condensed_data" not in st.session_state:
    st.session_state.condensed_data = {}
if "mode_map_dict" not in st.session_state:
    st.session_state.mode_map_dict = defaultdict(set)
if "all_brawlers" not in st.session_state:
    st.session_state.all_brawlers = set()
if "owned_brawlers" not in st.session_state:
    st.session_state.owned_brawlers = set()
if "brawler_list" not in st.session_state:
    st.session_state.brawler_list = [""]
draft_keys = [
    "ep1",
    "ep2",
    "ep3",
    "ap1",
    "ap2",
    "ap3",
    "eb1",
    "eb2",
    "eb3",
    "ab1",
    "ab2",
    "ab3",
]
for k in draft_keys:
    if k not in st.session_state:
        st.session_state[k] = ""


# ================= 2. 核心邏輯函式庫 =================
def log_message(msg):
    with GLOBAL_LOCK:
        st.session_state.logs.append(msg)
    print(f"[LOG] {msg}")


def get_initial_seeds(mode_tag):
    log_message(f"🌱 {mode_tag} 正在初始化種子玩家名單...")
    try:
        url = f"{BASE_URL}v1/rankings/global/players"
        # 使用第一個可用的 session 取得種子
        sess = (
            st.session_state.get("http_sessions")[0]
            if st.session_state.get("http_sessions")
            else HTTP_SESSION
        )
        res = sess.get(url, params={"limit": 50}, timeout=10)
        log_message(f"🔍 {mode_tag} API 回應狀態碼: {res.status_code}")
        if res.status_code == 200:
            items = res.json().get("items", [])
            log_message(f"✅ {mode_tag} 成功獲取 {len(items)} 個種子玩家")
            return [p.get("tag").replace("#", "%23") for p in items]
        else:
            log_message(
                f"❌ {mode_tag} API 請求失敗 (狀態碼: {res.status_code})：{res.text[:200]}"
            )
    except Exception as e:
        log_message(f"⚠️ {mode_tag} 獲取種子玩家失敗: {str(e)}")

    # 如果 API 失敗，使用備用種子玩家
    log_message(f"🔄 {mode_tag} 使用備用種子玩家")
    backup_seeds = [
        "8Q8Q2P2",  # 一些已知的玩家標籤（需要替換為真實的）
        "9P2Q8R2",
        "8L8Q2P2",
        "9R2Q8P2",
        "8Q8Q2P2",
    ]
    return [tag.replace("#", "%23") for tag in backup_seeds]


def harvest_rooms(duration, worker_count, ctx):
    mode_tag = "[模式 A]"
    q = queue.Queue()
    visited = set()
    seen_battles = set()
    data_lock = threading.Lock()
    end_time = datetime.now() + timedelta(minutes=duration)

    log_message(
        f"🚀 {mode_tag} 啟動 {worker_count} 核心！預計執行到: {end_time.strftime('%H:%M:%S')}"
    )
    seeds = get_initial_seeds(mode_tag)
    if not seeds:
        log_message(f"❌ {mode_tag} 無法取得種子玩家，強制停止。")
        return
    for s in seeds:
        q.put(s)

    def worker(worker_id):
        elite_found = 0
        iteration = 0
        while datetime.now() < end_time and st.session_state.is_running:
            try:
                sess = get_session_for_worker(worker_id)
                current_tag = q.get(timeout=2)
            except queue.Empty:
                continue

            with data_lock:
                if current_tag in visited:
                    q.task_done()
                    continue
                visited.add(current_tag)

            raw_tag = current_tag.replace("%23", "#")
            iteration += 1

            if worker_id == 0 and iteration % 5 == 0:
                elapsed = (datetime.now() - st.session_state.start_time).seconds / 60
                with data_lock:
                    log_message(
                        f"⏱️ {mode_tag} 陣容數: {len(st.session_state.rooms_data)} | 待查: {q.qsize()} 人 | 耗時: {elapsed:.1f}分"
                    )

            try:
                # 🛡️ 每個 worker 會使用分配到的 session（對應不同 API Key）
                res = sess.get(
                    f"{BASE_URL}v1/players/{current_tag}/battlelog",
                    timeout=10,
                )
                if res.status_code == 200:
                    data = res.json().get("items", [])
                    new_tags = []
                    for item in data:
                        battle = item.get("battle", {})
                        if "teams" in battle:
                            for team in battle["teams"]:
                                for p in team:
                                    t = p.get("tag").replace("#", "%23")
                                    new_tags.append(t)

                    with data_lock:
                        for t in new_tags:
                            if t not in visited:
                                q.put(t)

                    b_count, w_count = 0, 0
                    for item in data:
                        result = item.get("battle", {}).get("result")
                        if result in ["victory", "defeat"]:
                            b_count += 1
                            if result == "victory":
                                w_count += 1
                    win_rate = (w_count / b_count * 100) if b_count > 0 else 0
                    if win_rate < 75:
                        q.task_done()
                        continue

                    prof_res = sess.get(
                        f"{BASE_URL}v1/players/{current_tag}",
                        timeout=10,
                    )
                    if (
                        prof_res.status_code == 200
                        and prof_res.json().get("3vs3Victories", 0) >= 5000
                    ):
                        elite_found += 1
                        if elite_found % 3 == 0:
                            log_message(
                                f"{mode_tag} 🏆 核心 {worker_id} 捕獲神仙 {raw_tag}！"
                            )

                        for item in data:
                            battle = item.get("battle", {})
                            if battle.get("type") not in ["soloRanked", "teamRanked"]:
                                continue
                            teams = battle.get("teams", [])
                            if len(teams) != 2:
                                continue
                            b_time = item.get("battleTime")
                            mode = battle.get("mode", "未知")
                            b_id = f"{b_time}_{mode}"

                            with data_lock:
                                if b_id in seen_battles:
                                    continue
                                seen_battles.add(b_id)

                            map_name = item.get("event", {}).get("map") or "未知地圖"
                            result = battle.get("result")
                            if result not in ["victory", "defeat"]:
                                continue

                            elite_idx = -1
                            for i, team in enumerate(teams):
                                for p in team:
                                    if p.get("tag") == raw_tag:
                                        elite_idx = i
                                        break
                                if elite_idx != -1:
                                    break
                            if elite_idx == -1:
                                continue

                            win_idx = (
                                elite_idx if result == "victory" else 1 - elite_idx
                            )
                            win_b, lose_b = [], []
                            for i, team in enumerate(teams):
                                for p in team:
                                    b_name = p.get("brawler", {}).get("name", "未知")
                                    if i == win_idx:
                                        win_b.append(b_name)
                                    else:
                                        lose_b.append(b_name)
                            while len(win_b) < 3:
                                win_b.append("無")
                            while len(lose_b) < 3:
                                lose_b.append("無")

                            with data_lock:
                                st.session_state.rooms_data.append(
                                    {
                                        "對戰時間": b_time,
                                        "遊戲模式": mode,
                                        "地圖名稱": map_name,
                                        "勝利方_英雄1": win_b[0],
                                        "勝利方_英雄2": win_b[1],
                                        "勝利方_英雄3": win_b[2],
                                        "落敗方_英雄1": lose_b[0],
                                        "落敗方_英雄2": lose_b[1],
                                        "落敗方_英雄3": lose_b[2],
                                        "引流大神標籤": raw_tag,
                                    }
                                )
                    elif prof_res.status_code == 403:
                        with GLOBAL_LOCK:
                            st.session_state.is_running = False
                        log_message(f"❌ {mode_tag} Profile API拒絕存取(403)！")
                elif res.status_code == 403:
                    with GLOBAL_LOCK:
                        st.session_state.is_running = False
                    log_message(f"❌ {mode_tag} Battlelog API拒絕存取(403)！")
            except Exception:
                pass

            q.task_done()
            time.sleep(random.uniform(0.1, 0.5))

        with GLOBAL_LOCK:
            st.session_state.active_tasks -= 1
            if st.session_state.active_tasks <= 0:
                st.session_state.is_running = False

    for i in range(worker_count):
        with GLOBAL_LOCK:
            st.session_state.active_tasks += 1
        t = threading.Thread(target=worker, args=(i,))
        t.daemon = True
        add_script_run_ctx(t, ctx)
        t.start()


def harvest_solo(duration, worker_count, ctx):
    mode_tag = "[模式 B]"
    q = queue.Queue()
    visited = set()
    seen_battles = set()
    data_lock = threading.Lock()
    end_time = datetime.now() + timedelta(minutes=duration)

    log_message(
        f"🚀 {mode_tag} 啟動 {worker_count} 核心！預計執行到: {end_time.strftime('%H:%M:%S')}"
    )
    seeds = get_initial_seeds(mode_tag)
    if not seeds:
        log_message(f"❌ {mode_tag} 無法取得種子玩家，強制停止。")
        return
    for s in seeds:
        q.put(s)

    def worker(worker_id):
        elite_found = 0
        iteration = 0
        stats = st.session_state.solo_stats
        while datetime.now() < end_time and st.session_state.is_running:
            try:
                sess = get_session_for_worker(worker_id)
                current_tag = q.get(timeout=2)
            except queue.Empty:
                continue

            with data_lock:
                if current_tag in visited:
                    q.task_done()
                    continue
                visited.add(current_tag)

            raw_tag = current_tag.replace("%23", "#")
            iteration += 1

            if worker_id == 0 and iteration % 5 == 0:
                elapsed = (datetime.now() - st.session_state.start_time).seconds / 60
                with data_lock:
                    total_samples = sum(
                        s["played"]
                        for md in stats.values()
                        for mp in md.values()
                        for s in mp.values()
                    )
                    log_message(
                        f"⏱️ {mode_tag} 勝率樣本: {total_samples} 筆 | 待查: {q.qsize()} 人 | 耗時: {elapsed:.1f}分"
                    )

            try:
                res = sess.get(
                    f"{BASE_URL}v1/players/{current_tag}/battlelog",
                    timeout=10,
                )
                if res.status_code == 200:
                    data = res.json().get("items", [])
                    new_tags = []
                    for item in data:
                        battle = item.get("battle", {})
                        if "teams" in battle:
                            for team in battle["teams"]:
                                for p in team:
                                    t = p.get("tag").replace("#", "%23")
                                    new_tags.append(t)
                    with data_lock:
                        for t in new_tags:
                            if t not in visited:
                                q.put(t)

                    b_count, w_count = 0, 0
                    for item in data:
                        result = item.get("battle", {}).get("result")
                        if result in ["victory", "defeat"]:
                            b_count += 1
                            if result == "victory":
                                w_count += 1
                    win_rate = (w_count / b_count * 100) if b_count > 0 else 0
                    if win_rate < 75:
                        q.task_done()
                        continue

                    prof_res = sess.get(
                        f"{BASE_URL}v1/players/{current_tag}",
                        timeout=10,
                    )
                    if (
                        prof_res.status_code == 200
                        and prof_res.json().get("3vs3Victories", 0) >= 5000
                    ):
                        elite_found += 1
                        if elite_found % 3 == 0:
                            log_message(
                                f"{mode_tag} 🏆 核心 {worker_id} 捕獲大神 {raw_tag}！"
                            )

                        for item in data:
                            battle = item.get("battle", {})
                            if battle.get("type") not in ["soloRanked", "teamRanked"]:
                                continue
                            b_time = item.get("battleTime")
                            mode = battle.get("mode", "未知")
                            b_id = f"{b_time}_{mode}_{raw_tag}"

                            with data_lock:
                                if b_id in seen_battles:
                                    continue
                                seen_battles.add(b_id)

                            map_name = item.get("event", {}).get("map") or "未知地圖"
                            result = battle.get("result")
                            brawler_name = "未知"
                            if "teams" in battle:
                                for team in battle["teams"]:
                                    for p in team:
                                        if p.get("tag") == raw_tag:
                                            brawler_name = p.get("brawler", {}).get(
                                                "name"
                                            )
                            if brawler_name != "未知" and result in [
                                "victory",
                                "defeat",
                            ]:
                                with data_lock:
                                    stats[mode][map_name][brawler_name]["played"] += 1
                                    if result == "victory":
                                        stats[mode][map_name][brawler_name]["wins"] += 1
                    elif prof_res.status_code == 403:
                        with GLOBAL_LOCK:
                            st.session_state.is_running = False
                        log_message(f"❌ {mode_tag} Profile API拒絕存取(403)！")
                elif res.status_code == 403:
                    with GLOBAL_LOCK:
                        st.session_state.is_running = False
                    log_message(f"❌ {mode_tag} Battlelog API拒絕存取(403)！")
            except Exception:
                pass

            q.task_done()
            time.sleep(random.uniform(0.1, 0.5))

        with GLOBAL_LOCK:
            st.session_state.active_tasks -= 1
            if st.session_state.active_tasks <= 0:
                st.session_state.is_running = False

    for i in range(worker_count):
        with GLOBAL_LOCK:
            st.session_state.active_tasks += 1
        t = threading.Thread(target=worker, args=(i,))
        t.daemon = True
        add_script_run_ctx(t, ctx)
        t.start()


def generate_csv(data, mode):
    if not data:
        return ""
    output = io.StringIO()
    if mode == "rooms":
        fieldnames = [
            "對戰時間",
            "遊戲模式",
            "地圖名稱",
            "勝利方_英雄1",
            "勝利方_英雄2",
            "勝利方_英雄3",
            "落敗方_英雄1",
            "落敗方_英雄2",
            "落敗方_英雄3",
            "引流大神標籤",
        ]
    else:
        fieldnames = [
            "遊戲模式",
            "地圖名稱",
            "英雄名稱",
            "絕頂局出場次數",
            "絕頂局勝率(%)",
        ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


def process_multiple_csv_files(uploaded_files):
    if not uploaded_files:
        return False
    temp_condensed = defaultdict(lambda: defaultdict(dict))
    temp_mode_map = defaultdict(set)
    temp_all_brawlers = set()
    total_files_processed = 0
    master_stats = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: {"plays": 0, "wins": 0}))
    )

    for uploaded_file in uploaded_files:
        try:
            content = uploaded_file.getvalue().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))
            fields = reader.fieldnames
            is_mode_b = "絕頂局勝率(%)" in fields
            is_mode_a = "勝利方_英雄1" in fields
            if not (is_mode_a or is_mode_b):
                st.warning(f"⚠️ 忽略無法辨識的 CSV 格式：{uploaded_file.name}")
                continue
            total_files_processed += 1

            if is_mode_b:
                for row in reader:
                    mode = row["遊戲模式"]
                    map_name = row["地圖名稱"]
                    b_name = row["英雄名稱"]
                    plays = int(row["絕頂局出場次數"])
                    win_rate = float(row["絕頂局勝率(%)"])
                    if b_name and b_name != "無":
                        wins = round(plays * (win_rate / 100))
                        master_stats[mode][map_name][b_name]["plays"] += plays
                        master_stats[mode][map_name][b_name]["wins"] += wins
                        temp_mode_map[mode].add(map_name)
                        temp_all_brawlers.add(b_name)
            else:
                for row in reader:
                    mode = row["遊戲模式"]
                    map_name = row["地圖名稱"]
                    temp_mode_map[mode].add(map_name)
                    win_team = [row.get(f"勝利方_英雄{i}") for i in range(1, 4)]
                    lose_team = [row.get(f"落敗方_英雄{i}") for i in range(1, 4)]
                    for b in win_team:
                        if b and b != "無":
                            master_stats[mode][map_name][b]["plays"] += 1
                            master_stats[mode][map_name][b]["wins"] += 1
                            temp_all_brawlers.add(b)
                    for b in lose_team:
                        if b and b != "無":
                            master_stats[mode][map_name][b]["plays"] += 1
                            temp_all_brawlers.add(b)
        except Exception as e:
            st.error(f"❌ 處理檔案 {uploaded_file.name} 時發生錯誤: {str(e)}")

    if total_files_processed == 0:
        return False
    for mode, maps in master_stats.items():
        for map_name, brawlers in maps.items():
            for b, s in brawlers.items():
                if s["plays"] > 0:
                    win_rate = round((s["wins"] / s["plays"]) * 100, 1)
                    temp_condensed[mode][map_name][b] = {
                        "plays": s["plays"],
                        "win_rate": win_rate,
                    }

    st.session_state.condensed_data = temp_condensed
    st.session_state.mode_map_dict = temp_mode_map
    st.session_state.all_brawlers = temp_all_brawlers
    st.session_state.owned_brawlers = set(temp_all_brawlers)
    st.session_state.brawler_list = [""] + sorted(list(temp_all_brawlers))
    st.success(
        f"✅ 成功融合疊加 {total_files_processed} 份報表！巨量數據已寫入超光速快取。"
    )
    return True


# ================= 3. 各頁面渲染模組 =================
def render_home():
    st.title("🏆 K将軍 荒野亂鬥戰術大廳")
    st.markdown("歡迎來到終極戰術大廳！")

    st.divider()
    st.subheader("📡 系統網路狀態 (RoyaleAPI Proxy)")
    st.info("✅ 系統已配置使用 RoyaleAPI Proxy 繞過 IP 白名單限制。")
    st.warning(
        "⚠️ 【重要設定】：請前往 Brawl Stars Developer Portal，建立 API Key 時，將 **Allowed IP Address** 設為：\n\n**45.79.218.79**\n\n然後將產生的 API Key 貼到下方的輸入框中！"
    )
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.info("⚙️ **排位收割機狀態**")
        save_bs_key = st.checkbox(
            "💾 記住 Brawl Stars API Key(s) (Cookie 存儲)",
            value=bool(st.session_state.get("bs_api_keys")),
            key="save_bs_checkbox",
        )

        # 動態渲染每一個 key 欄位，並提供新增/刪除按鈕
        keys = st.session_state.get("bs_api_keys", []) or [""]
        st.markdown("**🔑 已輸入的 API Keys**")
        for i in range(len(keys)):
            c1, c2 = st.columns([9, 1])
            with c1:
                st.text_input(
                    label=f"Key #{i+1}",
                    value=keys[i],
                    key=f"bs_key_{i}",
                )
            with c2:
                if st.button("刪除", key=f"rm_key_{i}"):
                    current_keys = [
                        st.session_state.get(f"bs_key_{j}", "").strip()
                        for j in range(len(keys))
                        if j != i
                    ]
                    st.session_state.bs_api_keys = [k for k in current_keys if k]
                    if f"bs_key_{i}" in st.session_state:
                        del st.session_state[f"bs_key_{i}"]

        if st.button("➕ 新增 API Key", use_container_width=True, key="add_bs_key"):
            current_keys = [
                st.session_state.get(f"bs_key_{j}", "").strip()
                for j in range(len(keys))
            ]
            current_keys.append("")
            st.session_state.bs_api_keys = current_keys

        updated_keys = [
            st.session_state.get(f"bs_key_{i}", "").strip()
            for i in range(len(keys))
        ]
        if updated_keys != st.session_state.get("bs_api_keys", []):
            st.session_state.bs_api_keys = updated_keys or [""]
            valid_keys = [k for k in updated_keys if k]
            st.session_state.bs_api_key = valid_keys[0] if valid_keys else ""
            duplicate_keys = [k for k in valid_keys if valid_keys.count(k) > 1]
            if cookies is not None and not duplicate_keys:
                try:
                    if save_bs_key and valid_keys:
                        cookies["bs_api_keys"] = json.dumps(valid_keys)
                        cookies["bs_api_key"] = valid_keys[0]
                        cookies.save()
                        ios_cookie_fallback({
                            "bs_api_keys": json.dumps(valid_keys),
                            "bs_api_key": valid_keys[0],
                        }, [])
                    else:
                        if "bs_api_keys" in cookies:
                            cookies["bs_api_keys"] = None
                        if "bs_api_key" in cookies:
                            cookies["bs_api_key"] = None
                        cookies.save()
                        ios_cookie_fallback({}, ["bs_api_keys", "bs_api_key"])
                except Exception as e:
                    st.warning(f"⚠️ 無法保存到 Cookie: {str(e)}")

        valid_keys = [k for k in st.session_state.get("bs_api_keys", []) if k]
        duplicate_keys = [k for k in valid_keys if valid_keys.count(k) > 1]
        if valid_keys:
            st.success(
                f"✅ 已輸入 {len(valid_keys)} 組 Brawl Stars Key(s)（含 {len(st.session_state.get('bs_api_keys', [])) - len(valid_keys)} 組空白欄位）"
            )
            if duplicate_keys:
                st.error("❌ 同樣的 KEY 不能使用兩次以上，請移除重複項目。")
        else:
            st.warning("⚠️ 請至少輸入一組 Brawl Stars 金鑰。")

        if st.button("🗑️ 清除已保存的 Brawl Stars Key(s)", use_container_width=True):
            if cookies is not None:
                try:
                    if "bs_api_keys" in cookies:
                        cookies["bs_api_keys"] = None
                    if "bs_api_key" in cookies:
                        cookies["bs_api_key"] = None
                    cookies.save()
                except:
                    pass
            st.session_state.bs_api_key = ""
            st.session_state.bs_api_keys = []
            # 清除動態 widget
            for i in range(0, 32):
                kname = f"bs_key_{i}"
                if kname in st.session_state:
                    del st.session_state[kname]
            st.success("✅ 已清除！")

    with col2:
        st.info("🧠 **BP AI 分析狀態**")
        gemini_input = st.text_input(
            "🔑 Google Gemini API Key",
            type="password",
            value=st.session_state.gemini_api_key,
        )
        save_gemini_key = st.checkbox(
            "💾 記住 Gemini API Key (Cookie 存儲)",
            value=bool(st.session_state.gemini_api_key),
            key="save_gemini_checkbox",
        )
        if gemini_input != st.session_state.gemini_api_key:
            st.session_state.gemini_api_key = gemini_input.strip()
            # 💾 立即保存到 Cookie
            if st.session_state.gemini_api_key and cookies is not None:
                try:
                    if save_gemini_key:
                        cookies["gemini_api_key"] = st.session_state.gemini_api_key
                        cookies.save()
                        ios_cookie_fallback({"gemini_api_key": st.session_state.gemini_api_key}, [])
                    else:
                        # 取消保存時清除 Cookie
                        if "gemini_api_key" in cookies:
                            cookies["gemini_api_key"] = None
                            cookies.save()
                            ios_cookie_fallback({}, ["gemini_api_key"])
                except Exception as e:
                    st.warning(f"⚠️ 無法保存到 Cookie: {str(e)}")
        if st.session_state.gemini_api_key:
            st.success("✅ Gemini 金鑰已準備就緒！")
        else:
            st.warning("⚠️ 請貼上您的 Gemini 金鑰。")

        if st.button("🗑️ 清除已保存的 Gemini Key", use_container_width=True):
            if cookies is not None:
                try:
                    if "gemini_api_key" in cookies:
                        cookies["gemini_api_key"] = None
                        cookies.save()
                except:
                    pass
            st.session_state.gemini_api_key = ""
            st.success("✅ 已清除！")

    st.markdown("### 🧭 系統導覽")
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🚀 排位數據收割機 (連線池強化版)")
        st.write(
            "底層已升級為企業級 **HTTP Session 連線池**，完美突破 TCP 握手風暴偵測，讓您安心開啟多核心運算！"
        )
    with col_b:
        st.subheader("🤖 BP 即時戰術指示器")
        st.write("載入收割機產出的 CSV，提供超光速的選角與 Ban 角建議。")


def render_scraper(sidebar=None):
    st.title("🚀 荒野亂鬥 終極排位收割機")
    sidebar = sidebar if sidebar is not None else st.sidebar
    with sidebar:
        st.header("⚙️ 收割機設定")
        duration = st.number_input(
            "⏳ 執行時間 (分鐘)",
            min_value=1,
            max_value=120,
            value=st.session_state.duration,
        )
        st.session_state.duration = duration

        modes = st.multiselect(
            "🎯 選擇收割模式 (可同時多選！)",
            ["rooms", "solo"],
            default=st.session_state.scraper_modes,
            format_func=lambda x: (
                "模式 A：神仙房陣容收割" if x == "rooms" else "模式 B：大神單人勝率"
            ),
        )
        st.session_state.scraper_modes = modes

        st.divider()
        st.header("⚡ 效能壓榨引擎")
        valid_keys = [k for k in st.session_state.get("bs_api_keys", []) if k]
        max_workers = max(1, len(valid_keys))
        default_worker = min(st.session_state.worker_count, max_workers)
        if max_workers == 1:
            w_count = st.number_input(
                "🚀 併發核心數 (每個模式的分配量)",
                min_value=1,
                max_value=max_workers,
                value=default_worker,
                step=1,
                disabled=len(valid_keys) == 0,
            )
        else:
            w_count = st.slider(
                "🚀 併發核心數 (每個模式的分配量)",
                min_value=1,
                max_value=max_workers,
                value=default_worker,
                step=1,
                disabled=len(valid_keys) == 0,
            )
        st.session_state.worker_count = w_count
        st.caption(
            "🛡️ 核心數上限已限制為目前有效 API Key 的數量。"
        )
        if len(valid_keys) == 0:
            st.warning("請先於首頁輸入至少一組有效的 Brawl Stars API Key。")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button(
            "▶️ 啟動多核心收割陣列",
            disabled=st.session_state.is_running,
            use_container_width=True,
            type="primary",
        ):
            raw_keys = st.session_state.get("bs_api_keys") or []
            keys = [k for k in raw_keys if k]
            if len(set(keys)) != len(keys):
                st.error("❌ 同樣的 KEY 不能使用兩次以上，請先移除重複項目。")
            elif not keys:
                st.error("請先前往【首頁大廳】輸入至少一組 Brawl Stars API Key！")
            elif not st.session_state.scraper_modes:
                st.error("請至少選擇一種收割模式！")
            else:
                # 根據輸入的 keys 自動設定 worker_count（上限 16）
                desired_workers = len(keys)
                if desired_workers > 16:
                    st.warning("⚠️ Worker 上限為 16，將只使用前 16 組 Keys。")
                    desired_workers = 16
                st.session_state.worker_count = desired_workers

                st.session_state.is_running = True
                st.session_state.active_tasks = 0
                st.session_state.rooms_data = []
                st.session_state.solo_data = []
                st.session_state.solo_stats.clear()
                st.session_state.logs = []
                st.session_state.start_time = datetime.now()
                st.session_state.export_filename = (
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                )

                log_message(f"🔑 使用 {len(keys)} 組 API Key，啟動 {st.session_state.worker_count} 個 worker。")
                # 建立每個 API key 的 session 清單，讓每個 worker 使用不同 key
                st.session_state.bs_api_keys = raw_keys
                st.session_state.http_sessions = [create_http_session(k) for k in keys[:16]]

                ctx = get_script_run_ctx()

                if "rooms" in st.session_state.scraper_modes:
                    harvest_rooms(
                        st.session_state.duration, st.session_state.worker_count, ctx
                    )
                if "solo" in st.session_state.scraper_modes:
                    harvest_solo(
                        st.session_state.duration, st.session_state.worker_count, ctx
                    )

                st.rerun()
    with col2:
        if st.button(
            "⏹️ 緊急停止並保留資料",
            disabled=not st.session_state.is_running,
            use_container_width=True,
            type="primary",
        ):
            st.session_state.is_running = False
            st.rerun()
    with col3:
        if st.button(
            "🗑️ 清除日誌與資料",
            disabled=st.session_state.is_running,
            use_container_width=True,
        ):
            st.session_state.logs = []
            st.session_state.rooms_data = []
            st.session_state.solo_data = []
            st.session_state.solo_stats.clear()
            st.rerun()

    st.divider()

    if st.session_state.is_running:
        st.info(
            f"🔄 **多核心收割陣列全速運作中...** (目前有 {st.session_state.active_tasks} 個核心正在背景狂飆！)"
        )
        st.code("\n".join(st.session_state.logs[-25:]), language="plaintext")
        st.info("⏱️ 系統每 3 秒自動更新目前狀態。")
        time.sleep(3)
        st.rerun()

    elif not st.session_state.is_running and st.session_state.logs:
        st.markdown("### 📝 上次執行日誌")
        st.code("\n".join(st.session_state.logs[-25:]), language="plaintext")

    if not st.session_state.is_running:
        if len(st.session_state.solo_stats) > 0:
            export_rows = []
            for map_mode, maps in st.session_state.solo_stats.items():
                for m_name, brawlers in maps.items():
                    for b, s in brawlers.items():
                        if s["played"] >= 1:
                            export_rows.append(
                                {
                                    "遊戲模式": map_mode,
                                    "地圖名稱": m_name,
                                    "英雄名稱": b,
                                    "絕頂局出場次數": s["played"],
                                    "絕頂局勝率(%)": round(
                                        (s["wins"] / s["played"]) * 100, 2
                                    ),
                                }
                            )
            st.session_state.solo_data = export_rows
            st.session_state.solo_stats.clear()

        if st.session_state.rooms_data or st.session_state.solo_data:
            st.subheader("📊 結算結果與下載")
            col_res1, col_res2 = st.columns(2)

            if st.session_state.rooms_data:
                with col_res1:
                    st.success(
                        f"✅ 模式 A：成功存檔 {len(st.session_state.rooms_data)} 筆陣容資料。"
                    )
                    csv_rooms = generate_csv(st.session_state.rooms_data, "rooms")
                    st.download_button(
                        label="⬇️ 下載模式 A (神仙房) 報表",
                        data=csv_rooms.encode("utf-8-sig"),
                        file_name=f"God_Rooms_{st.session_state.export_filename}",
                        mime="text/csv",
                        use_container_width=True,
                        type="primary",
                    )

            if st.session_state.solo_data:
                with col_res2:
                    st.success(
                        f"✅ 模式 B：成功整理 {len(st.session_state.solo_data)} 筆單人勝率。"
                    )
                    csv_solo = generate_csv(st.session_state.solo_data, "solo")
                    st.download_button(
                        label="⬇️ 下載模式 B (單人勝率) 報表",
                        data=csv_solo.encode("utf-8-sig"),
                        file_name=f"Elite_Ranked_{st.session_state.export_filename}",
                        mime="text/csv",
                        use_container_width=True,
                        type="primary",
                    )


def render_bp(sidebar=None):
    st.title("🤖 K将軍 BP 即時戰術指示器")
    sidebar = sidebar if sidebar is not None else st.sidebar
    with sidebar:
        st.header("📂 數據庫載入")
        uploaded_files = st.file_uploader(
            "選擇一個或多個 CSV", type=["csv"], accept_multiple_files=True
        )
        if uploaded_files:
            if st.button("📥 融合載入", type="primary", use_container_width=True):
                with st.spinner("🧠 處理中..."):
                    if process_multiple_csv_files(uploaded_files):
                        time.sleep(0.5)
                        st.rerun()
        st.divider()
        st.header("🎒 英雄池設定")
        if st.session_state.all_brawlers:
            selected_brawlers = st.multiselect(
                "選擇你擁有的英雄",
                options=sorted(list(st.session_state.all_brawlers)),
                default=list(st.session_state.owned_brawlers),
            )
            st.session_state.owned_brawlers = set(selected_brawlers)
        else:
            st.info("請先載入數據庫。")

    if not st.session_state.condensed_data:
        st.info("👈 請先從左側邊欄載入數據庫。")
        st.stop()

    st.subheader("🗺️ 1. 當前戰場環境")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        selected_mode = st.selectbox(
            "遊戲模式", sorted(list(st.session_state.mode_map_dict.keys()))
        )
    with col_m2:
        selected_map = st.selectbox(
            "地圖名稱",
            sorted(list(st.session_state.mode_map_dict.get(selected_mode, []))),
        )
    with col_m3:
        first_pick = st.radio(
            "開局首搶", ["我方先選 (藍方 First Pick)", "敵方先選 (紅方 First Pick)"]
        )

    st.divider()
    col_draft_title, col_clear_btn = st.columns([4, 1])
    with col_draft_title:
        st.subheader("⚔️ 2. 即時選角狀態")
    with col_clear_btn:
        if st.button("🧹 清空所有選角", use_container_width=True):
            for k in draft_keys:
                st.session_state[k] = ""
            st.rerun()

    b_list = st.session_state.brawler_list
    col_e, col_a, col_eb, col_ab = st.columns(4)
    with col_e:
        st.markdown("### 🔴 敵方已選")
        st.selectbox("Enemy Pick 1", b_list, key="ep1")
        st.selectbox("Enemy Pick 2", b_list, key="ep2")
        st.selectbox("Enemy Pick 3", b_list, key="ep3")
    with col_a:
        st.markdown("### 🔵 我方已選")
        st.selectbox("Ally Pick 1", b_list, key="ap1")
        st.selectbox("Ally Pick 2", b_list, key="ap2")
        st.selectbox("Ally Pick 3", b_list, key="ap3")
    with col_eb:
        st.markdown("### 🚫 敵方 Ban")
        st.selectbox("Enemy Ban 1", b_list, key="eb1")
        st.selectbox("Enemy Ban 2", b_list, key="eb2")
        st.selectbox("Enemy Ban 3", b_list, key="eb3")
    with col_ab:
        st.markdown("### 🚫 我方 Ban")
        st.selectbox("Ally Ban 1", b_list, key="ab1")
        st.selectbox("Ally Ban 2", b_list, key="ab2")
        st.selectbox("Ally Ban 3", b_list, key="ab3")

    st.divider()
    if st.button(
        "⚡ 呼叫 AI 分析並提供選角建議 ⚡", type="primary", use_container_width=True
    ):
        if not st.session_state.gemini_api_key:
            st.error("請先前往【首頁大廳】設定 Gemini API Key！")
        else:
            enemies = [
                st.session_state[k]
                for k in ["ep1", "ep2", "ep3"]
                if st.session_state[k]
            ]
            allies = [
                st.session_state[k]
                for k in ["ap1", "ap2", "ap3"]
                if st.session_state[k]
            ]
            bans = [
                st.session_state[k]
                for k in ["eb1", "eb2", "eb3", "ab1", "ab2", "ab3"]
                if st.session_state[k]
            ]
            unavailable_brawlers = set(enemies + allies + bans)
            stats_list = []
            if (
                selected_mode in st.session_state.condensed_data
                and selected_map in st.session_state.condensed_data[selected_mode]
            ):
                for b, s in st.session_state.condensed_data[selected_mode][
                    selected_map
                ].items():
                    if b in unavailable_brawlers:
                        continue
                    if b not in st.session_state.owned_brawlers:
                        continue
                    if s["plays"] >= 3:
                        stats_list.append(
                            {"name": b, "plays": s["plays"], "win_rate": s["win_rate"]}
                        )
            # ... 前面計算 stats_list 和 top_winrate 的程式碼保持不變 ...
            top_winrate = sorted(stats_list, key=lambda x: x["win_rate"], reverse=True)[
                :15
            ]
            str_enemies = ", ".join(enemies) if enemies else "None (敵方尚未選角)"
            str_allies = ", ".join(allies) if allies else "None (我方尚未選角)"
            str_bans = ", ".join(bans) if bans else "None"

            # 📊 1. 戰場情報資料餵食
            prompt_data = f"""
            【當前戰場情報】
            - 🎯 遊戲模式：{selected_mode}
            - 🗺️ 地圖名稱：{selected_map}
            - 🎲 開局先攻權：{first_pick}
            - 🔴 敵方已選：{str_enemies}
            - 🔵 我方已選：{str_allies}
            - 🚫 雙方已 Ban：{str_bans}

            【我方可用高勝率資料庫 Top 15 (已過濾未擁有及被 Ban 英雄)】
            """
            for i, s in enumerate(top_winrate, 1):
                prompt_data += f"{i}. {s['name']} (勝率 {s['win_rate']}%, 絕頂局出場 {s['plays']} 次)\n"

            # 🧠 2. 階段性戰術任務指派
            if not enemies and not allies and len(bans) < 6:
                task_instruction = f"""
                【當前任務：禁用 (Ban) 階段】
                雙方尚未選角，請給出最致命的 3 個 Ban 位建議。

                🔥 思考邏輯：
                1. 地圖毒瘤：找出在「{selected_mode} - {selected_map}」中勝率與出場率最可怕的英雄。
                2. 首搶權博弈：
                   - 如果【我方先選】：請大膽放出一隻「版本最強」留給我們首搶，並 Ban 掉它的天敵 (Counter)。
                   - 如果【敵方先選】：務必把勝率最高、最難處理的強勢角全部 Ban 死，絕不留給對手。
                3. 明確指示：除了推薦 Ban 誰，必須明確指出「Ban 完這三隻後，我們第一選 (First Pick) 應該無腦搶誰」。
                """
            else:
                task_instruction = """
                【當前任務：選角 (Pick) 階段】
                請根據目前雙方的陣容，從「可用高勝率資料庫」中挑選出 1~3 隻最能贏下這場比賽的英雄。

                🔥 思考邏輯：
                1. 絕對克制 (Counter)：針對【敵方已選】的陣容，找出能完美反制的英雄（如：反坦、刺客抓投擲、破牆角）。
                2. 陣容連動 (Synergy)：檢視【我方已選】，確保陣容完整（控制、爆發、奶媽、遠程消耗）。避免陣容過於單一（例如全脆皮、全近戰）。
                3. 補位思維：根據遊戲模式，我們目前缺什麼定位？（例如：寶石模式缺中路扛線、賞金模式缺狙擊手）。

                📋 輸出格式要求 (請嚴格遵守排版)：
                - 👑 **推薦首選**：[英雄名稱] (勝率 XX%) - 簡述戰術理由 (克制誰/配合誰)。
                - ⚔️ **備用選項**：[英雄名稱] (勝率 XX%) - 簡述戰術理由。
                - ⚠️ **陣容弱點警告**：一句話提醒我方陣容目前最怕敵方選出什麼類型的角色。
                """

            # 🤖 3. 全局系統人設與鐵則
            system_prompt = f"""
            你是一位世界頂級的《荒野亂鬥》(Brawl Stars) 電競賽事主教練。
            你的任務是在排位賽的 BP 階段，根據大數據與當前戰況，為我方下達最精確、最具威脅性的戰術指令。

            【🚨 最高鐵則 - 違者嚴懲】
            1. 絕對限制：你【只能、必須】從我提供的「可用高勝率資料庫」名單中推薦英雄！絕不能推薦名單外、玩家未擁有或已經被選/被Ban的角色！
            2. 數據說話：嚴格基於我提供的「勝率」與「出場數」進行評估，絕不可憑空捏造不存在的數據。
            3. 語氣設定：冷靜、專業、果斷。嚴禁打招呼、嚴禁廢話、嚴禁罐頭回覆，直接切入戰術核心。
            4. 排版要求：使用 Markdown 重點條列式與粗體標示，讓選手能在一秒內看懂指令。

            {task_instruction}
            """

            with st.status("🧠 呼叫 AI 教練中...", expanded=True) as status:
                # ... 下面的 API 連線程式碼保持不變 ...
                try:
                    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={st.session_state.gemini_api_key}"
                    list_res = requests.get(list_url, timeout=20)
                    if list_res.status_code != 200:
                        raise Exception(f"API Key 錯誤 ({list_res.status_code})")
                    available_models = [
                        m["name"].replace("models/", "")
                        for m in list_res.json().get("models", [])
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                        and "vision" not in m["name"].lower()
                    ]
                    target_model = next(
                        (m for m in available_models if "flash" in m.lower()),
                        available_models[0] if available_models else None,
                    )
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={st.session_state.gemini_api_key}"
                    response = requests.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json={
                            "system_instruction": {"parts": [{"text": system_prompt}]},
                            "contents": [{"parts": [{"text": prompt_data}]}],
                            "generationConfig": {"temperature": 0.5},
                        },
                        timeout=45,
                    )
                    if response.status_code == 200:
                        st.success("🎯 戰術指示抵達！")
                        st.info(
                            response.json()["candidates"][0]["content"]["parts"][0][
                                "text"
                            ]
                        )
                        status.update(
                            label="✅ 解析完畢", state="complete", expanded=False
                        )
                    else:
                        raise Exception(response.text)
                except Exception as e:
                    status.update(label="❌ 分析錯誤", state="error")
                    st.error(str(e))


# ================= 4. 側邊欄導航路由 (Router) =================
sidebar = st.sidebar
sidebar.title("🧭 系統導航")
page = sidebar.radio(
    "前往", ["🏠 首頁大廳", "🚀 排位數據收割機", "🤖 BP 即時戰術指示器"]
)
sidebar.divider()
sidebar_page = sidebar.empty()
main_page = st.container()

with main_page:
    if page == "🏠 首頁大廳":
        render_home()
    elif page == "🚀 排位數據收割機":
        render_scraper(sidebar_page)
    elif page == "🤖 BP 即時戰術指示器":
        render_bp(sidebar_page)
