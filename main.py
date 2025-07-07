import os
import sqlite3
import re
import json
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 嘗試導入 Google Sheets 相關模組
try:
    import gspread
    from google.oauth2.service_account import Credentials
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False
    print("⚠️ Google Sheets 模組未安裝，將只使用本地資料庫")

# LINE Bot 設定
LINE_ACCESS_TOKEN = "UMJsgNzJjYZ1YzuNYfrOL6VbtgLPgcmhnotLW9H2Z9vHIHtsONE0kzfGogRrJc0aHIDqMnb+/X3meXbI5SrVek56Sef+UaomLqNN9mWU6HeSC24l7on7qKhlzleVc5w1rjicqTPKLW2YAhlwja6k9AdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "75b5d4235e8990c2cafccb77951f5a06"

# Google Sheets 設定
GOOGLE_SHEETS_CREDENTIALS = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
SHEET_ID = os.environ.get('SHEET_ID')

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

class GoogleSheetsManager:
    def __init__(self):
        self.sheet = None
        self.setup_credentials()
    
    def setup_credentials(self):
        """設定 Google Sheets 認證"""
        if not SHEETS_AVAILABLE:
            print("⚠️ Google Sheets 功能不可用")
            return
            
        try:
            if GOOGLE_SHEETS_CREDENTIALS and SHEET_ID:
                creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
                scope = [
                    'https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive'
                ]
                credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
                gc = gspread.authorize(credentials)
                self.sheet = gc.open_by_key(SHEET_ID).sheet1
                print("✅ Google Sheets 連線成功")
            else:
                print("⚠️ Google Sheets 環境變數未設定")
        except Exception as e:
            print(f"❌ Google Sheets 設定失敗: {e}")
            self.sheet = None
    
    def add_stock_data(self, data):
        """新增資料到 Google Sheets"""
        if not self.sheet:
            return False
        
        try:
            row_data = [
                data['date'],
                data['time'],
                data['message'],
                data['stock_codes'],
                data['stock_names'],
                data['msg_type'],
                data.get('sentiment', '中性'),
                str(data.get('importance', 3)),
                data.get('source', 'LINE Bot'),
                data.get('notes', '')
            ]
            
            # 新增資料
            self.sheet.append_row(row_data)
            
            # 排序（可選，因為會影響效能）
            # self.sort_by_date()
            
            return True
            
        except Exception as e:
            print(f"❌ 新增到 Sheets 失敗: {e}")
            return False
    
    def sort_by_date(self):
        """按日期時間排序"""
        try:
            all_values = self.sheet.get_all_values()
            
            if len(all_values) <= 1:
                return
            
            headers = all_values[0]
            data_rows = all_values[1:]
            
            # 按日期時間排序（最新在上）
            sorted_data = sorted(data_rows, key=lambda x: f"{x[0]} {x[1]}", reverse=True)
            
            # 更新試算表
            self.sheet.clear()
            all_sorted_data = [headers] + sorted_data
            self.sheet.update(values=all_sorted_data, range_name='A1')
            
        except Exception as e:
            print(f"❌ 排序失敗: {e}")
    
    def get_stats(self):
        """從 Google Sheets 取得統計"""
        if not self.sheet:
            return None
        
        try:
            all_values = self.sheet.get_all_values()
            
            if len(all_values) <= 1:
                return {"total": 0, "stocks": 0}
            
            data_rows = all_values[1:]
            total_count = len(data_rows)
            unique_stocks = len(set([row[3] for row in data_rows if row[3]]))
            
            return {
                "total": total_count,
                "stocks": unique_stocks,
                "sheet_url": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
            }
            
        except Exception as e:
            print(f"❌ 取得統計失敗: {e}")
            return None

class EnhancedStockBot:
    def __init__(self):
        self.stocks = {
            "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2412": "中華電",
            "2882": "國泰金", "2308": "台達電", "2303": "聯電", "2002": "中鋼",
            "1303": "南亞", "1301": "台塑", "6505": "台塑化", "2886": "兆豐金",
            "2891": "中信金", "2880": "華南金", "2881": "富邦金", "2892": "第一金",
            "2395": "研華", "3008": "大立光", "2409": "友達", "2408": "南亞科"
        }
        self.sheets_manager = GoogleSheetsManager()
        self.init_db()
    
    def init_db(self):
        """初始化本地資料庫"""
        conn = sqlite3.connect("stock.db")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            date TEXT,
            time TEXT,
            message TEXT,
            stock_code TEXT,
            stock_name TEXT,
            msg_type TEXT,
            sentiment TEXT,
            importance INTEGER,
            synced_to_sheets BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
        conn.close()
    
    def analyze_enhanced(self, text):
        """增強版股票分析"""
        # 識別股票代號
        codes = re.findall(r"\d{4}", text)
        found_codes = [c for c in codes if c in self.stocks]
        
        # 識別股票名稱
        found_names = []
        for code, name in self.stocks.items():
            if name in text:
                found_names.append(code)
        
        all_codes = list(set(found_codes + found_names))
        stock_names = [self.stocks.get(code, code) for code in all_codes]
        
        # 訊息類型分類
        text_lower = text.lower()
        if any(word in text_lower for word in ["買", "賣", "交易", "進場", "出場", "加碼", "減碼"]):
            msg_type = "交易"
        elif any(word in text_lower for word in ["漲", "跌", "價格", "目標價", "支撐", "壓力"]):
            msg_type = "價格"
        elif any(word in text_lower for word in ["分析", "建議", "看法", "預測", "技術面", "基本面"]):
            msg_type = "分析"
        elif any(word in text_lower for word in ["新聞", "消息", "公告", "財報"]):
            msg_type = "新聞"
        else:
            msg_type = "討論"
        
        # 情緒分析
        positive_words = ["漲", "上漲", "看好", "買進", "看多", "強勢", "獲利", "讚", "好", "棒"]
        negative_words = ["跌", "下跌", "看壞", "賣出", "看空", "弱勢", "虧損", "差", "糟"]
        
        pos_count = sum(1 for word in positive_words if word in text)
        neg_count = sum(1 for word in negative_words if word in text)
        
        if pos_count > neg_count:
            sentiment = "正面"
        elif neg_count > pos_count:
            sentiment = "負面"
        else:
            sentiment = "中性"
        
        # 重要性評分
        importance = 1
        if all_codes: importance += 1
        if any(word in text_lower for word in ["買", "賣", "目標價"]): importance += 1
        if len(text) > 20: importance += 1
        if any(word in text_lower for word in ["重要", "注意", "關鍵"]): importance += 1
        importance = min(importance, 5)
        
        # 如果是股票相關訊息
        if all_codes or any(name in text for name in self.stocks.values()):
            now = datetime.now()
            
            data = {
                'date': now.strftime("%Y-%m-%d"),
                'time': now.strftime("%H:%M:%S"),
                'message': text,
                'stock_codes': ','.join(all_codes),
                'stock_names': ','.join(stock_names),
                'msg_type': msg_type,
                'sentiment': sentiment,
                'importance': importance,
                'source': 'LINE Bot'
            }
            
            # 儲存到本地資料庫
            self.save_to_local_db(data)
            
            # 儲存到 Google Sheets
            sheets_success = self.sheets_manager.add_stock_data(data)
            
            return {
                "found": True,
                "codes": all_codes,
                "names": stock_names,
                "type": msg_type,
                "sentiment": sentiment,
                "importance": importance,
                "sheets_synced": sheets_success
            }
        
        return {"found": False}
    
    def save_to_local_db(self, data):
        """儲存到本地資料庫"""
        conn = sqlite3.connect("stock.db")
        try:
            conn.execute("""
            INSERT INTO messages (date, time, message, stock_code, stock_name, msg_type, sentiment, importance, synced_to_sheets)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data['date'], data['time'], data['message'], data['stock_codes'], 
                data['stock_names'], data['msg_type'], data['sentiment'], 
                data['importance'], True
            ))
            conn.commit()
        except Exception as e:
            print(f"本地儲存失敗: {e}")
        finally:
            conn.close()
    
    def get_local_stats(self):
        """取得本地統計"""
        conn = sqlite3.connect("stock.db")
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM messages")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT stock_code) FROM messages WHERE stock_code != ''")
            stocks = cursor.fetchone()[0]
            return {"total": total, "stocks": stocks}
        except:
            return {"total": 0, "stocks": 0}
        finally:
            conn.close()

# 建立 Bot 實例
bot = EnhancedStockBot()
app = Flask(__name__)

@app.route("/")
def home():
    sheets_status = "✅" if bot.sheets_manager.sheet else "❌"
    return f"🤖 股票分析 Bot 運行中！Google Sheets: {sheets_status}"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print(f"處理錯誤: {e}")
    
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    
    try:
        # Google Sheets 統計指令
        if text.lower() in ["sheets統計", "試算表", "google統計"]:
            sheets_stats = bot.sheets_manager.get_stats()
            
            if sheets_stats:
                reply_text = f"""📊 Google Sheets 統計

📈 總記錄數：{sheets_stats['total']} 則
🎯 涉及股票：{sheets_stats['stocks']} 檔

🔗 查看試算表：
{sheets_stats['sheet_url']}

💡 試算表會自動按日期排序"""
            else:
                reply_text = "❌ 無法連接到 Google Sheets"
            
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return
        
        # 本地統計
        if text.lower() in ["統計", "摘要", "summary"]:
            local_stats = bot.get_local_stats()
            sheets_status = "✅ 已連接" if bot.sheets_manager.sheet else "❌ 未連接"
            
            reply_text = f"""📊 股票資訊統計

📈 本地收集：{local_stats['total']} 則
🎯 涉及股票：{local_stats['stocks']} 檔
📋 Google Sheets：{sheets_status}

💡 輸入「sheets統計」查看試算表資料"""
            
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return
        
        # 分析股票訊息
        result = bot.analyze_enhanced(text)
        
        if result["found"]:
            if result["codes"]:
                codes_text = f"股票: {', '.join([f'{code}({name})' for code, name in zip(result['codes'], result['names'])])}"
            else:
                codes_text = "股票討論"
            
            sheets_icon = "✅" if result.get("sheets_synced") else "❌"
            
            reply_text = f"""📈 已記錄 {result['type']} 資訊
{codes_text}
😊 情緒: {result['sentiment']}
⭐ 重要性: {result['importance']}/5
📊 Google Sheets: {sheets_icon}"""
            
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    
    except Exception as e:
        print(f"訊息處理錯誤: {e}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🤖 處理中發生錯誤，請稍後再試"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
