# 荒野亂鬥 終極排位收割機 (Streamlit 版)

這是一個基於 Streamlit 的 Brawl Stars 數據刮取應用，用於收集精英玩家的對戰數據和英雄勝率統計。

## 功能

- **模式 A**: 神仙房完整陣容收割 - 收集精英玩家的團隊對戰組成
- **模式 B**: 絕頂大神單人英雄勝率 - 統計英雄在不同地圖的勝率

## 本地運行

1. 安裝依賴：
   ```bash
   pip install -r requirements.txt
   ```

2. 運行應用：
   ```bash
   streamlit run app.py
   ```

3. 在瀏覽器中打開顯示的 URL。

## 部署到 Streamlit Cloud

1. 將代碼上傳到 GitHub 倉庫。

2. 前往 [Streamlit Cloud](https://share.streamlit.io/) 並登入。

3. 點擊 "New app"。

4. 選擇您的 GitHub 倉庫和分支。

5. 設定主文件為 `app.py`。

6. 點擊 "Deploy"。

## 安全注意事項

- API Key 會在網路請求中暴露，請謹慎使用。
- 建議使用專用的 API Key，並定期輪換。
- 不要在公共倉庫中提交 API Key。

## 使用說明

1. 輸入您的 Brawl Stars API Key。
2. 設定執行時間（分鐘）。
3. 選擇刮取模式。
4. 點擊"啟動收割機"。
5. 等待刮取完成，然後下載 CSV 文件。

注意：刮取過程可能需要幾分鐘，請耐心等待。