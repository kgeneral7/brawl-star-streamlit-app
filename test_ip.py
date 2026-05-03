import requests

# ⚠️ 請將下方雙引號內的文字，換成你的 Brawl Stars API Key
API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6IjYwMGZjN2Y0LWUxOGMtNDNkMi1iNTZjLWFiMjA5MjZmYjRiNSIsImlhdCI6MTc3Nzc3MDU0OSwic3ViIjoiZGV2ZWxvcGVyLzU1Y2JlNTBhLTJhN2UtN2VhYy0wYzBmLTZmYmQyN2VlOTE2OSIsInNjb3BlcyI6WyJicmF3bHN0YXJzIl0sImxpbWl0cyI6W3sidGllciI6ImRldmVsb3Blci9zaWx2ZXIiLCJ0eXBlIjoidGhyb3R0bGluZyJ9LHsiY2lkcnMiOlsiMTE4LjE2Ny4xOTUuMTc5Il0sInR5cGUiOiJjbGllbnQifV19.a2Vllplbyz1UpuA3WiJvBehsI_UDqLUt9g3O-pUnZQNhfu2qwRk9DKhb4q0Ipk3rm-sJCC69RH2SmbLZ86fRmg"

headers = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}

print("📡 正在向 Supercell 發送 X 光測試連線...")
res = requests.get(
    "https://api.brawlstars.com/v1/rankings/global/players?limit=1", headers=headers
)

print(f"\n📊 【伺服器狀態碼】: {res.status_code}")
print(f"💬 【官方詳細回應】: {res.text}")
