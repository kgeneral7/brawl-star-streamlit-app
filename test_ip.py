import streamlit as st
import socket
from urllib.parse import urlparse

st.title("🌐 神搜：網址轉 IP 解析器")
st.write("輸入任何網址（例如你的 Streamlit 雲端網址），我幫你把底層 IP 挖出來！")

# 1. 建立輸入框
url_input = st.text_input("🔗 請輸入網址 (URL)：", placeholder="例如：https://my-app.streamlit.app 或 google.com")

if url_input:
    try:
        # 2. 清洗網址：把 https:// 和後面的路徑去掉，只留核心網域
        # 如果使用者輸入 https://google.com/search，這段會把它變成 google.com
        domain = urlparse(url_input).netloc
        if not domain: 
            domain = url_input # 如果使用者沒打 https://，直接拿輸入的字
            
        # 3. 核心魔法：呼叫 DNS 系統查 IP
        ip_address = socket.gethostbyname(domain)
        
        st.success(f"✅ 解析成功！")
        st.markdown(f"- **目標網域：** `{domain}`")
        st.markdown(f"- **對應 IP：** `{ip_address}`")
        
    except socket.gaierror:
        st.error("❌ 解析失敗：找不到這個網址，請確認拼字是否正確（不要輸入結尾的斜線或子路徑）。")
    except Exception as e:
        st.error(f"❌ 發生未知的錯誤：{e}")