import os
from dotenv import load_dotenv

# 1. 檢查系統有沒有成功找到並載入檔案 (回傳 True 代表成功，False 代表找不到)
is_loaded = load_dotenv()
print(f"🔍 1. .env 檔案載入狀態: {is_loaded}")

# 2. 檢查到底讀到了什麼東西
bs_key = os.getenv("BRAWL_STARS_API_KEY")
print(f"🔑 2. Brawl Stars 金鑰: {bs_key}")

gemini_key = os.getenv("GEMINI_API_KEY")
print(f"🔑 3. Gemini 金鑰: {gemini_key}")