from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import re
from datetime import datetime

# 嘗試導入 Google Sheets
try:
    import gspread
    from google.oauth2.service_account import Credentials
    import json
    SHEETS_AVAILABLE = True
    print("✅ Google Sheets 模組載入成功")
except ImportError as e:
    SHEETS_AVAILABLE = False
    print(f"❌ Google Sheets 模組載入失敗: {e}")

# LINE Bot 設定
LINE_ACCESS_TOKEN = "UMJsgNzJjYZ1YzuNYfrOL6VbtgLPgcmhnotLW9H2Z9vHIHtsONE0kzfGogRrJc0aHIDqMnb+/X3meXbI5SrVek56Sef+UaomLqNN9mWU6HeSC24l7on7qKhlzleVc5w1rjicqTPKLW2YAhlwja6k9AdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "75b5d4235e8990c2cafccb77951f5a06"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

class GoogleSheetsManager:
    def __init__(self):
        self.sheet = None
        self.error_msg = ""
        self.setup_credentials()
    
    def setup_credentials(self):
        if not SHEETS_AVAILABLE:
            self.error_msg = "Google Sheets 模組未安裝"
            print("❌ Google Sheets 模組不可用")
            return
        
        try:
            # 檢查環境變數
            credentials_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
            sheet_id = os.environ.get('SHEET_ID')
            
            if not credentials_json:
                self.error_msg = "缺少 GOOGLE_SHEETS_CREDENTIALS 環境變數"
                print("❌ 缺少 GOOGLE_SHEETS_CREDENTIALS")
                return
            
            if not sheet_id:
                self.error_msg = "缺少 SHEET_ID 環境變數"
                print("❌ 缺少 SHEET_ID")
                return
            
            # 嘗試解析 JSON
            try:
                creds_dict = json.loads(credentials_json)
                print("✅ JSON 解析成功")
            except json.JSONDecodeError as e:
                self.error_msg = f"JSON 格式錯誤: {e}"
                print(f"❌ JSON 解析失敗: {e}")
                return
            
            # 建立認證
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
            gc = gspread.authorize(credentials)
            print("✅ Google 認證成功")
            
            # 嘗試開啟試算表
            self.sheet = gc.open_by_key(sheet_id).sheet1
            print(f"✅ 試算表連接成功: {sheet_id}")
            
        except Exception as e:
            self.error_msg = f"設定失敗: {str(e)}"
            print(f"❌ Google Sheets 設定失敗: {e}")
            self.sheet = None
    
    def add_data(self, data):
        if not self.sheet:
            return False
        
        try:
            row = [
                data['date'], data['time'], data['message'], 
                data['stock_codes'], data['stock_names'], data['msg_type']
            ]
            self.sheet.append_row(row)
            print("✅ 資料新增到 Google Sheets 成功")
            return True
        except Exception as e:
            print(f"❌ 新增資料失敗: {e}")
            return False
    
    def get_status(self):
        if self.sheet:
            return "✅ 已連接"
        else:
            return f"❌ 未連接: {self.error_msg}"

# 建立 Google Sheets 管理器
sheets_manager = GoogleSheetsManager()

app = Flask(__name__)

@app.route("/")
def home():
    sheets_status = sheets_manager.get_status()
    return f"🤖 股票 Bot 運行中！<br>Google Sheets: {sheets_status}"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    
    try:
        # 測試指令
        if text.lower() in ["測試", "test"]:
            sheets_status = sheets_manager.get_status()
            reply_text = f"✅ Bot 正常運作！\nGoogle Sheets: {sheets_status}"
        
        # Google Sheets 狀態
        elif text.lower() in ["sheets狀態", "google狀態"]:
            reply_text = f"📊 Google Sheets 狀態:\n{sheets_manager.get_status()}"
        
        # 股票訊息處理
        elif any(keyword in text for keyword in ["2330", "台積電", "2317", "鴻海", "買", "賣", "漲", "跌"]):
            # 分析股票訊息
            now = datetime.now()
            
            # 簡單的股票識別
            stock_codes = []
            stock_names = []
            
            if "2330" in text or "台積電" in text:
                stock_codes.append("2330")
                stock_names.append("台積電")
            if "2317" in text or "鴻海" in text:
                stock_codes.append("2317")
                stock_names.append("鴻海")
            
            # 訊息類型
            if any(word in text for word in ["買", "賣", "交易"]):
                msg_type = "交易"
            elif any(word in text for word in ["漲", "跌", "價格"]):
                msg_type = "價格"
            else:
                msg_type = "討論"
            
            # 準備資料
            data = {
                'date': now.strftime("%Y-%m-%d"),
                'time': now.strftime("%H:%M:%S"),
                'message': text,
                'stock_codes': ','.join(stock_codes),
                'stock_names': ','.join(stock_names),
                'msg_type': msg_type
            }
            
            # 嘗試儲存到 Google Sheets
            sheets_success = sheets_manager.add_data(data)
            
            sheets_icon = "✅" if sheets_success else "❌"
            reply_text = f"📈 已記錄 {msg_type} 資訊\n股票: {', '.join(stock_names) if stock_names else '一般討論'}\n📊 Google Sheets: {sheets_icon}"
        
        else:
            reply_text = f"🤖 收到訊息：{text[:30]}..."
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        
    except Exception as e:
        print(f"❌ 處理錯誤: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="❌ 處理發生錯誤")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
