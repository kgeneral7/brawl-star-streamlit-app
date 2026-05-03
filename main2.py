import sys
import asyncio
import os
import socket
from dotenv import load_dotenv

# 🛡️ 究極防護一：強制 Requests 永遠只准走 IPv4！(阻絕 IPv6 幽靈連線)
import urllib3.util.connection as urllib3_cn
def allowed_gai_family():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = allowed_gai_family

# 🔧 載入環境變數檔 (.env)
load_dotenv()

# 🔧 終極防護：徹底消滅 Windows 系統上惱人的 WinError 10054 報錯
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import streamlit as st
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
import requests
import time
import csv
import random
import io
from datetime import datetime, timedelta
from collections import defaultdict

# ================= 網頁基本設定 =================
st.set_page_config(page_title="👑 K将軍 荒野戰術大廳", layout="wide", page_icon="🏆")

# ================= 1. 全域快取記憶體 (Session State) =================
# 🛡️ 究極防護二：暴力清洗金鑰 (把不小心加進去的雙引號、單引號、換行全部砍掉)
raw_bs_key = os.getenv("BRAWL_STARS_API_KEY", "")
safe_bs_key = raw_bs_key.replace('"', '').replace("'", "").strip()

if 'gemini_api_key' not in st.session_state: st.session_state.gemini_api_key = ""
if 'bs_api_key' not in st.session_state: st.session_state.bs_api_key = safe_bs_key

if 'is_running' not in st.session_state: st.session_state.is_running = False
if 'data' not in st.session_state: st.session_state.data = []
if 'solo_stats' not in st.session_state: st.session_state.solo_stats = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {'played': 0, 'wins': 0})))
if 'logs' not in st.session_state: st.session_state.logs = []
if 'scraper_mode' not in st.session_state: st.session_state.scraper_mode = "rooms"
if 'duration' not in st.session_state: st.session_state.duration = 60
if 'export_filename' not in st.session_state: st.session_state.export_filename = "brawl_data.csv"

if 'condensed_data' not in st.session_state: st.session_state.condensed_data = {}
if 'mode_map_dict' not in st.session_state: st.session_state.mode_map_dict = defaultdict(set)
if 'all_brawlers' not in st.session_state: st.session_state.all_brawlers = set()
if 'owned_brawlers' not in st.session_state: st.session_state.owned_brawlers = set()
if 'brawler_list' not in st.session_state: st.session_state.brawler_list = [""]
draft_keys = ["ep1", "ep2", "ep3", "ap1", "ap2", "ap3", "eb1", "eb2", "eb3", "ab1", "ab2", "ab3"]
for k in draft_keys:
    if k not in st.session_state: st.session_state[k] = ""

# ================= 2. 核心邏輯函式庫 =================
def log_message(msg):
    st.session_state.logs.append(msg)
    print(f"[LOG] {msg}")

def get_initial_seeds(api_key):
    log_message("🌱 正在初始化種子玩家名單...")
    
    # 重新組裝最純淨的 Headers
    headers = {
        "Authorization": f"Bearer {api_key}", 
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    try:
        url = "https://api.brawlstars.com/v1/rankings/global/players"
        res = requests.get(url, headers=headers, params={"limit": 50}, timeout=10)
        if res.status_code == 200:
            return [p.get('tag').replace('#', '%23') for p in res.json().get('items', [])]
        elif res.status_code == 403:
            log_message(f"❌ 嚴重錯誤 (403)：API 拒絕存取！")
    except Exception as e:
        log_message(f"⚠️ 獲取種子玩家失敗: {str(e)}")
    return []

def harvest_rooms(api_key, duration):
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    player_queue = set()
    visited_players = set()
    seen_battles = set()
    end_time = datetime.now() + timedelta(minutes=duration)
    log_message(f"🚀 【模式 A：神仙房間陣容版】啟動！預計執行到: {end_time.strftime('%H:%M:%S')}")
    
    seeds = get_initial_seeds(api_key)
    if not seeds:
        log_message("❌ 無法取得種子玩家，收割機強制停止。")
        st.session_state.is_running = False
        return

    for s in seeds: player_queue.add(s)
    elite_found = 0
    iteration_count = 0
    
    while datetime.now() < end_time and player_queue and st.session_state.is_running:
        iteration_count += 1
        if iteration_count % 5 == 0:
            elapsed_time = (datetime.now() - st.session_state.start_time).seconds / 60
            log_message(f"⏱️ 進度: {iteration_count} 玩家已檢查 | 精英玩家: {elite_found} | 累積對戰數: {len(st.session_state.data)} | 已用時間: {elapsed_time:.1f}分鐘")
        current_tag = random.choice(list(player_queue))
        player_queue.remove(current_tag)
        visited_players.add(current_tag)
        raw_tag = current_tag.replace("%23", "#")
        try:
            res = requests.get(f"https://api.brawlstars.com/v1/players/{current_tag}/battlelog", headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json().get('items', [])
                for item in data:
                    battle = item.get('battle', {})
                    if 'teams' in battle:
                        for team in battle['teams']:
                            for p in team:
                                t = p.get('tag').replace('#', '%23')
                                if t not in visited_players: player_queue.add(t)
                b_count, w_count = 0, 0
                for item in data:
                    result = item.get('battle', {}).get('result')
                    if result in ['victory', 'defeat']:
                        b_count += 1
                        if result == 'victory': w_count += 1
                win_rate = (w_count / b_count * 100) if b_count > 0 else 0
                if win_rate < 75:
                    time.sleep(0.1)
                    continue
                
                prof_res = requests.get(f"https://api.brawlstars.com/v1/players/{current_tag}", headers=headers, timeout=10)
                if prof_res.status_code == 200 and prof_res.json().get('3vs3Victories', 0) >= 5000:
                    elite_found += 1
                    log_message(f"[{datetime.now().strftime('%H:%M:%S')}] 🏆 找到神仙 {raw_tag}！")
                    for item in data:
                        battle = item.get('battle', {})
                        if battle.get('type') not in ['soloRanked', 'teamRanked']: continue
                        teams = battle.get('teams', [])
                        if len(teams) != 2: continue
                        b_time = item.get('battleTime')
                        mode = battle.get('mode', '未知')
                        b_id = f"{b_time}_{mode}"
                        if b_id in seen_battles: continue
                        seen_battles.add(b_id)
                        map_name = item.get('event', {}).get('map') or '未知地圖'
                        result = battle.get('result')
                        if result not in ['victory', 'defeat']: continue
                        elite_idx = -1
                        for i, team in enumerate(teams):
                            for p in team:
                                if p.get('tag') == raw_tag:
                                    elite_idx = i; break
                            if elite_idx != -1: break
                        if elite_idx == -1: continue
                        win_idx = elite_idx if result == 'victory' else 1 - elite_idx
                        win_b, lose_b = [], []
                        for i, team in enumerate(teams):
                            for p in team:
                                b_name = p.get('brawler', {}).get('name', '未知')
                                if i == win_idx: win_b.append(b_name)
                                else: lose_b.append(b_name)
                        while len(win_b) < 3: win_b.append('無')
                        while len(lose_b) < 3: lose_b.append('無')
                        st.session_state.data.append({
                            "對戰時間": b_time, "遊戲模式": mode, "地圖名稱": map_name,
                            "勝利方_英雄1": win_b[0], "勝利方_英雄2": win_b[1], "勝利方_英雄3": win_b[2],
                            "落敗方_英雄1": lose_b[0], "落敗方_英雄2": lose_b[1], "落敗方_英雄3": lose_b[2],
                            "引流大神標籤": raw_tag
                        })
                elif prof_res.status_code == 403:
                    log_message("❌ 嚴重錯誤 (403)：API 拒絕存取！")
                    st.session_state.is_running = False
                    break
                elif prof_res.status_code == 429:
                    log_message("⚠️ API 速率限制，等待 5 秒...")
                    time.sleep(5)
            elif res.status_code == 403:
                log_message("❌ 嚴重錯誤 (403)：API 存取被拒絕！")
                st.session_state.is_running = False
                break
            elif res.status_code == 429:
                log_message("⚠️ API 速率限制，等待 5 秒...")
                time.sleep(5)
        except Exception: pass
        time.sleep(0.3)
        if len(player_queue) > 10000: player_queue = set(random.sample(list(player_queue), 5000))
    log_message("✅ 模式 A 任務完畢！")

def harvest_solo(api_key, duration):
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    player_queue = set()
    visited_players = set()
    seen_battles = set()
    end_time = datetime.now() + timedelta(minutes=duration)
    log_message(f"🚀 【模式 B：絕頂單人英雄勝率】啟動！預計執行到: {end_time.strftime('%H:%M:%S')}")
    
    seeds = get_initial_seeds(api_key)
    if not seeds:
        log_message("❌ 無法取得種子玩家，收割機強制停止。")
        st.session_state.is_running = False
        return

    for s in seeds: player_queue.add(s)
    elite_found = 0
    iteration_count = 0
    stats = st.session_state.solo_stats
    
    while datetime.now() < end_time and player_queue and st.session_state.is_running:
        iteration_count += 1
        if iteration_count % 5 == 0:
            elapsed_time = (datetime.now() - st.session_state.start_time).seconds / 60
            log_message(f"⏱️ 進度: {iteration_count} 玩家已檢查 | 精英玩家: {elite_found} | 已用時間: {elapsed_time:.1f}分鐘")
        current_tag = random.choice(list(player_queue))
        player_queue.remove(current_tag)
        visited_players.add(current_tag)
        raw_tag = current_tag.replace("%23", "#")
        try:
            res = requests.get(f"https://api.brawlstars.com/v1/players/{current_tag}/battlelog", headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json().get('items', [])
                for item in data:
                    battle = item.get('battle', {})
                    if 'teams' in battle:
                        for team in battle['teams']:
                            for p in team:
                                t = p.get('tag').replace('#', '%23')
                                if t not in visited_players: player_queue.add(t)
                b_count, w_count = 0, 0
                for item in data:
                    result = item.get('battle', {}).get('result')
                    if result in ['victory', 'defeat']:
                        b_count += 1
                        if result == 'victory': w_count += 1
                win_rate = (w_count / b_count * 100) if b_count > 0 else 0
                if win_rate < 75: continue
                
                prof_res = requests.get(f"https://api.brawlstars.com/v1/players/{current_tag}", headers=headers, timeout=10)
                if prof_res.status_code == 200 and prof_res.json().get('3vs3Victories', 0) >= 5000:
                    elite_found += 1
                    log_message(f"[{datetime.now().strftime('%H:%M:%S')}] 🏆 大神 {raw_tag}！")
                    for item in data:
                        battle = item.get('battle', {})
                        if battle.get('type') not in ['soloRanked', 'teamRanked']: continue
                        b_time = item.get('battleTime')
                        mode = battle.get('mode', '未知')
                        b_id = f"{b_time}_{mode}_{raw_tag}"
                        if b_id in seen_battles: continue
                        seen_battles.add(b_id)
                        map_name = item.get('event', {}).get('map') or '未知地圖'
                        result = battle.get('result')
                        brawler_name = "未知"
                        if 'teams' in battle:
                            for team in battle['teams']:
                                for p in team:
                                    if p.get('tag') == raw_tag: brawler_name = p.get('brawler', {}).get('name')
                        if brawler_name != "未知" and result in ['victory', 'defeat']:
                            stats[mode][map_name][brawler_name]['played'] += 1
                            if result == 'victory': stats[mode][map_name][brawler_name]['wins'] += 1
                elif prof_res.status_code == 403:
                    log_message("❌ 嚴重錯誤 (403)：API 拒絕存取！")
                    st.session_state.is_running = False
                    break
                elif prof_res.status_code == 429:
                    log_message("⚠️ API 速率限制，等待 5 秒...")
                    time.sleep(5)
            elif res.status_code == 403:
                log_message("❌ 嚴重錯誤 (403)：API 存取被拒絕！")
                st.session_state.is_running = False
                break
            elif res.status_code == 429:
                log_message("⚠️ API 速率限制，等待 5 秒...")
                time.sleep(5)
        except Exception: pass
        time.sleep(0.3)
        if len(player_queue) > 10000: player_queue = set(random.sample(list(player_queue), 5000))
    log_message("✅ 模式 B 任務完畢！")

def generate_csv(data, mode):
    if not data: return ""
    output = io.StringIO()
    if mode == "rooms":
        fieldnames = ["對戰時間", "遊戲模式", "地圖名稱", "勝利方_英雄1", "勝利方_英雄2", "勝利方_英雄3", 
                      "落敗方_英雄1", "落敗方_英雄2", "落敗方_英雄3", "引流大神標籤"]
    else:
        fieldnames = ["遊戲模式", "地圖名稱", "英雄名稱", "絕頂局出場次數", "絕頂局勝率(%)"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()

def background_harvest_worker(api_key, duration, mode):
    """背景獨立執行緒管家：參數直接傳遞版"""
    try:
        # 🕵️‍♂️ 印出檢查：讓我們看看傳進來的金鑰到底正不正常！
        key_len = len(api_key)
        if key_len > 10:
            preview = f"{api_key[:5]}...{api_key[-5:]}"
            log_message(f"🕵️‍♂️ [系統檢查] 使用中的金鑰長度: {key_len} 字元, 預覽: {preview}")
        else:
            log_message(f"🕵️‍♂️ [系統檢查] 警告：金鑰長度異常 ({key_len} 字元)")
            
        if mode == "rooms":
            harvest_rooms(api_key, duration)
        else:
            harvest_solo(api_key, duration)
    except Exception as e:
        log_message(f"❌ 發生未預期的錯誤: {str(e)}")
    finally:
        st.session_state.is_running = False

# ----------------- (B) BP 指示器專用函式 -----------------
def process_multiple_csv_files(uploaded_files):
    if not uploaded_files: return False
    temp_condensed = defaultdict(lambda: defaultdict(dict))
    temp_mode_map = defaultdict(set)
    temp_all_brawlers = set()
    total_files_processed = 0
    master_stats = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"plays": 0, "wins": 0})))

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
                    win_team = [row.get(f"勝利方_英雄{i}") for i in range(1,4)]
                    lose_team = [row.get(f"落敗方_英雄{i}") for i in range(1,4)]
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

    if total_files_processed == 0: return False
    for mode, maps in master_stats.items():
        for map_name, brawlers in maps.items():
            for b, s in brawlers.items():
                if s["plays"] > 0:
                    win_rate = round((s["wins"] / s["plays"]) * 100, 1)
                    temp_condensed[mode][map_name][b] = {"plays": s["plays"], "win_rate": win_rate}
    
    st.session_state.condensed_data = temp_condensed
    st.session_state.mode_map_dict = temp_mode_map
    st.session_state.all_brawlers = temp_all_brawlers
    st.session_state.owned_brawlers = set(temp_all_brawlers)
    st.session_state.brawler_list = [""] + sorted(list(temp_all_brawlers))
    st.success(f"✅ 成功融合疊加 {total_files_processed} 份報表！巨量數據已寫入超光速快取。")
    return True

# ================= 3. 各頁面渲染模組 =================
def render_home():
    """🏠 首頁大廳"""
    st.title("🏆 K将軍 荒野亂鬥戰術大廳")
    st.markdown("歡迎來到終極戰術大廳！")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("⚙️ **排位收割機專用**")
        if st.session_state.bs_api_key:
            st.success("✅ Brawl Stars 金鑰已由 `.env` 成功載入！")
        else:
            st.error("❌ 未偵測到 Brawl Stars 金鑰，請檢查 `.env` 檔案。")
        
    with col2:
        st.info("🧠 **BP AI 分析專用**")
        gemini_input = st.text_input("🔑 Google Gemini API Key", type="password", value=st.session_state.gemini_api_key)
        if gemini_input != st.session_state.gemini_api_key:
            st.session_state.gemini_api_key = gemini_input.strip()
            st.rerun()
            
        if st.session_state.gemini_api_key:
            st.success("✅ Gemini 金鑰已準備就緒！")
        else:
            st.warning("⚠️ 請貼上您的 Gemini 金鑰，完成後按下 Enter 鍵。")

    st.divider()
    st.markdown("### 🧭 系統導覽")
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🚀 系統一：排位數據收割機")
        st.write("在背景全自動巡邏神仙房，收集最高端的對戰數據與勝率。")
    with col_b:
        st.subheader("🤖 系統二：BP 即時戰術指示器")
        st.write("載入收割機產出的 CSV，在排位賽 BP 階段提供超光速的選角與 Ban 角建議。")

def render_scraper():
    """🚀 收割機頁面"""
    st.title("🚀 荒野亂鬥 終極排位收割機")
    with st.sidebar:
        st.header("⚙️ 收割機設定")
        duration = st.number_input("⏳ 執行時間 (分鐘)", min_value=1, max_value=120, value=st.session_state.duration)
        st.session_state.duration = duration
        mode = st.radio("🎯 選擇收割模式", 
                       ["rooms", "solo"], 
                       index=0 if st.session_state.scraper_mode == "rooms" else 1,
                       format_func=lambda x: "模式 A：神仙房陣容收割" if x == "rooms" else "模式 B：大神單人勝率")
        st.session_state.scraper_mode = mode

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("▶️ 啟動收割機", disabled=st.session_state.is_running, use_container_width=True):
            if not st.session_state.bs_api_key:
                st.error("系統未讀取到 Brawl Stars API Key，請檢查 `.env`！")
            else:
                st.session_state.is_running = True
                st.session_state.data = []
                st.session_state.solo_stats.clear()
                st.session_state.logs = []
                st.session_state.start_time = datetime.now()
                st.session_state.export_filename = f"brawl_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                
                ctx = get_script_run_ctx()
                # 🌟 改版重點：直接把參數傳進去，不讓它依賴 Thread 裡面的環境變數
                t = threading.Thread(
                    target=background_harvest_worker, 
                    args=(st.session_state.bs_api_key, st.session_state.duration, st.session_state.scraper_mode)
                )
                add_script_run_ctx(t, ctx)
                t.start()
                st.rerun()
    with col2:
        if st.button("⏹️ 緊急停止並保留資料", disabled=not st.session_state.is_running, use_container_width=True, type="primary"):
            st.session_state.is_running = False
            st.rerun()
    with col3:
        if st.button("🗑️ 清除日誌與資料", disabled=st.session_state.is_running, use_container_width=True):
            st.session_state.logs = []
            st.session_state.data = []
            st.session_state.solo_stats.clear()
            st.rerun()

    st.divider()

    if st.session_state.is_running:
        st.info("🔄 收割機背景全速運作中...")
        st.code("\n".join(st.session_state.logs[-25:]), language="plaintext")
        time.sleep(1.5)
        st.rerun()

    elif not st.session_state.is_running and st.session_state.logs:
        st.markdown("### 📝 上次執行日誌")
        st.code("\n".join(st.session_state.logs[-25:]), language="plaintext")

    if not st.session_state.is_running:
        if st.session_state.scraper_mode == "solo" and len(st.session_state.solo_stats) > 0:
            export_rows = []
            for map_mode, maps in st.session_state.solo_stats.items():
                for m_name, brawlers in maps.items():
                    for b, s in brawlers.items():
                        if s['played'] >= 1: 
                            export_rows.append({"遊戲模式": map_mode, "地圖名稱": m_name, "英雄名稱": b, "絕頂局出場次數": s['played'], "絕頂局勝率(%)": round((s['wins']/s['played'])*100, 2)})
            if export_rows: st.session_state.data = export_rows
            st.session_state.solo_stats.clear()

        if st.session_state.data:
            st.subheader("📊 結算結果")
            st.success(f"✅ 成功存檔！共收集/整理了 {len(st.session_state.data)} 筆數據。")
            csv_data = generate_csv(st.session_state.data, st.session_state.scraper_mode)
            st.download_button(
                label="⬇️ 點此下載 CSV 報表",
                data=csv_data.encode('utf-8-sig'),
                file_name=st.session_state.export_filename, 
                mime="text/csv",
                use_container_width=True,
                type="primary"
            )

def render_bp():
    """🤖 BP 指示器頁面"""
    st.title("🤖 K将軍 BP 即時戰術指示器")
    with st.sidebar:
        st.header("📂 數據庫載入 (支援多檔疊加)")
        uploaded_files = st.file_uploader("請選擇一個或多個 CSV 檔案", type=["csv"], accept_multiple_files=True)
        if uploaded_files:
            if st.button("📥 融合載入已選檔案", type="primary", use_container_width=True):
                with st.spinner("🧠 正在融合疊加巨量數據庫..."):
                    if process_multiple_csv_files(uploaded_files):
                        time.sleep(0.5)
                        st.rerun()
        st.divider()
        st.header("🎒 英雄池設定")
        if st.session_state.all_brawlers:
            selected_brawlers = st.multiselect(
                "請選擇你擁有的英雄 (預設全選)", 
                options=sorted(list(st.session_state.all_brawlers)),
                default=list(st.session_state.owned_brawlers)
            )
            st.session_state.owned_brawlers = set(selected_brawlers)
        else:
            st.info("請先載入數據庫才能設定英雄池。")

    if not st.session_state.condensed_data:
        st.info("👈 請先從左側邊欄載入數據庫 (可同時上傳多份先前的收割報表)。")
        st.stop()

    st.subheader("🗺️ 1. 當前戰場環境")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        modes = sorted(list(st.session_state.mode_map_dict.keys()))
        selected_mode = st.selectbox("遊戲模式", modes)
    with col_m2:
        maps = sorted(list(st.session_state.mode_map_dict.get(selected_mode, [])))
        selected_map = st.selectbox("地圖名稱", maps)
    with col_m3:
        first_pick = st.radio("開局首搶", ["我方先選 (藍方 First Pick)", "敵方先選 (紅方 First Pick)"])

    st.divider()

    col_draft_title, col_clear_btn = st.columns([4, 1])
    with col_draft_title: st.subheader("⚔️ 2. 即時選角狀態")
    with col_clear_btn:
        if st.button("🧹 清空所有選角", use_container_width=True):
            for k in draft_keys: st.session_state[k] = ""
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

    if st.button("⚡ 呼叫 AI 分析並提供選角建議 ⚡", type="primary", use_container_width=True):
        if not st.session_state.gemini_api_key:
            st.error("請先前往首頁設定 Gemini API Key！")
        else:
            enemies = [st.session_state[k] for k in ["ep1", "ep2", "ep3"] if st.session_state[k]]
            allies = [st.session_state[k] for k in ["ap1", "ap2", "ap3"] if st.session_state[k]]
            bans = [st.session_state[k] for k in ["eb1", "eb2", "eb3", "ab1", "ab2", "ab3"] if st.session_state[k]]
            
            unavailable_brawlers = set(enemies + allies + bans)
            stats_list = []
            if selected_mode in st.session_state.condensed_data and selected_map in st.session_state.condensed_data[selected_mode]:
                for b, s in st.session_state.condensed_data[selected_mode][selected_map].items():
                    if b in unavailable_brawlers: continue 
                    if b not in st.session_state.owned_brawlers: continue
                    if s["plays"] >= 3: 
                        stats_list.append({"name": b, "plays": s["plays"], "win_rate": s["win_rate"]})
            
            top_winrate = sorted(stats_list, key=lambda x: x["win_rate"], reverse=True)[:15]

            str_enemies = ", ".join(enemies) if enemies else "None (敵方尚未選角)"
            str_allies = ", ".join(allies) if allies else "None (我方尚未選角)"
            str_bans = ", ".join(bans) if bans else "None"

            prompt_data = f"""
            【目前戰場情報】
            - 遊戲模式：{selected_mode}
            - 地圖名稱：{selected_map}
            - 開局先攻權：{first_pick}  
            - 敵方已選英雄：{str_enemies}
            - 我方已選英雄：{str_allies}
            - 雙方已禁用 (Ban)：{str_bans}

            【資料庫精煉：當前地圖勝率最高 且 我方擁有 的可用英雄 Top 15】\n"""
            for i, s in enumerate(top_winrate, 1):
                prompt_data += f"{s['name']} (勝率 {s['win_rate']}%, 出場 {s['plays']} 次)\n"

            if not enemies and not allies and len(bans) < 6:
                task_instruction = """現在是「禁用 (Ban) 階段」。
                1. 根據上傳的資料推薦我們最該 Ban 掉的 3 隻高勝率/高出場率英雄。
                2. 請特別考量【開局先攻權】。如果我方先選，可以放出一隻版本之子讓我們首搶；如果敵方先選，務必把最強的毒瘤 Ban 掉。
                3. 請一定要給第一隻要選的角色。"""
            else:
                task_instruction = """現在是「選角 (Pick) 階段」。
                1. 請從我提供的數據中，挑選出 1~3 隻最能「克制敵方陣容」且能「配合我方陣容」的英雄。
                2. 簡潔有力地說明戰術理由。"""

            system_prompt = f"""你是一個內建於系統中的《荒野亂鬥》實戰 BP 輔助機器人。
            【規則】
            - 回答必須精簡俐落，像電競教練在選手耳邊下達指令。
            - 你的建議必須「絕對嚴格地」只能從我提供的可用英雄清單中挑選，因為這些都是使用者帳號中確實擁有的角色。
            - 務必考量【開局先攻權】與【敵我已選陣容】的康特關係。
            - 使用繁體中文回答。
            - 不要提供任何與選角無關的廢話，直接給出最精確的 Ban/Pick 建議和戰術指示。
            - 只能按照資料的結果來分析，不能憑空捏造英雄數據或勝率資訊。
            
            {task_instruction}"""

            with st.status("🧠 啟動超光速分析與 AI 連線中...", expanded=True) as status:
                try:
                    status.write("📡 [步驟 1] 正在向 Google 伺服器探測您的專屬模型清單...")
                    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={st.session_state.gemini_api_key}"
                    list_res = requests.get(list_url, timeout=20)
                    if list_res.status_code != 200: raise Exception(f"無法取得模型清單，請確認 API Key。錯誤碼：{list_res.status_code}")
                        
                    available_models = [m['name'].replace('models/', '') for m in list_res.json().get('models', []) 
                                        if 'generateContent' in m.get('supportedGenerationMethods', []) and 'vision' not in m['name'].lower()]
                    target_model = next((m for m in available_models if 'flash' in m.lower()), available_models[0] if available_models else None)
                    if not target_model: raise Exception("找不到任何支援對話的 Gemini 模型！")
                        
                    status.write(f"🎯 [步驟 2] 成功鎖定可用模型：{target_model}")
                    status.write("🌐 [步驟 3] 正在傳送精煉數據給 AI 大腦思考...")

                    headers = {'Content-Type': 'application/json'}
                    payload = {
                        "system_instruction": {"parts": [{"text": system_prompt}]},
                        "contents": [{"parts": [{"text": prompt_data}]}],
                        "generationConfig": {"temperature": 0.5}
                    }
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={st.session_state.gemini_api_key}"
                    
                    max_retries = 3
                    ai_reply = None
                    for attempt in range(max_retries):
                        try:
                            response = requests.post(url, headers=headers, json=payload, timeout=45)
                            if response.status_code == 200:
                                ai_reply = response.json()['candidates'][0]['content']['parts'][0]['text']
                                break
                            elif response.status_code in [429, 503]:
                                if attempt < max_retries - 1:
                                    wait_sec = 15
                                    status.write(f"⚠️ 伺服器忙碌 (錯誤碼 {response.status_code})，系統於 {wait_sec} 秒後自動重試...")
                                    time.sleep(wait_sec)
                                    continue
                                else: raise Exception(f"Google 伺服器持續塞車 ({response.status_code})。請稍後再試！")
                            else: raise Exception(f"伺服器錯誤 ({response.status_code}):\n{response.text}")
                        except requests.exceptions.Timeout:
                            if attempt < max_retries - 1:
                                status.write(f"⚠️ 連線逾時，系統將於 5 秒後自動重試...")
                                time.sleep(5)
                                continue
                            else: raise Exception("連線持續逾時 (Read timed out)。")

                    if ai_reply:
                        status.update(label="✅ AI 戰術解析完畢！", state="complete", expanded=False)
                        st.success("🎯 教練戰術指示已抵達！")
                        st.info(ai_reply)
                    else: raise Exception("無法取得戰術分析。")

                except Exception as e:
                    status.update(label="❌ 分析發生錯誤", state="error")
                    st.error(str(e))

# ================= 4. 側邊欄導航路由 (Router) =================
st.sidebar.title("🧭 系統導航")
page = st.sidebar.radio("前往", ["🏠 首頁大廳", "🚀 排位數據收割機", "🤖 BP 即時戰術指示器"])
st.sidebar.divider()

if page == "🏠 首頁大廳":
    render_home()
elif page == "🚀 排位數據收割機":
    render_scraper()
elif page == "🤖 BP 即時戰術指示器":
    render_bp()