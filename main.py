import os
import sqlite3
import re
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# LINE Bot 設定
LINE_ACCESS_TOKEN = "UMJsgNzJjYZ1YzuNYfrOL6VbtgLPgcmhnotLW9H2Z9vHIHtsONE0kzfGogRrJc0aHIDqMnb+/X3meXbI5SrVek56Sef+UaomLqNN9mWU6HeSC24l7on7qKhlzleVc5w1rjicqTPKLW2YAhlwja6k9AdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "75b5d4235e8990c2cafccb77951f5a06"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# 股票分析器
class StockBot:
    def __init__(self):
        self.stocks = {
            "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2412": "中華電",
            "2882": "國泰金", "2308": "台達電", "2303": "聯電", "2002": "中鋼",
            "1303": "南亞", "1301": "台塑", "6505": "台塑化", "2886": "兆豐金"
        }
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect("stock.db")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            date TEXT,
            message TEXT,
            stock_code TEXT,
            msg_type TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
        conn.close()
    
    def analyze(self, text):
        # 檢查是否包含股票代號
        codes = re.findall(r"\d{4}", text)
        found_codes = [c for c in codes if c in self.stocks]
        
        # 檢查是否包含股票名稱
        found_names = []
        for code, name in self.stocks.items():
            if name in text:
                found_names.append(code)
        
        all_codes = list(set(found_codes + found_names))
        
        # 判斷訊息類型
        text_lower = text.lower()
        if any(word in text_lower for word in ["買", "賣", "交易", "進場", "出場"]):
            msg_type = "交易"
        elif any(word in text_lower for word in ["漲", "跌", "價格", "目標價"]):
            msg_type = "價格"
        elif any(word in text_lower for word in ["分析", "建議", "看法"]):
            msg_type = "分析"
        else:
            msg_type = "討論"
        
        # 如果有股票相關內容就儲存
        if all_codes or any(name in text for name in self.stocks.values()):
            self.save_message(text, all_codes, msg_type)
            return {
                "found": True,
                "codes": all_codes,
                "type": msg_type
            }
        
        return {"found": False}
    
    def save_message(self, text, codes, msg_type):
        conn = sqlite3.connect("stock.db")
        try:
            conn.execute("""
            INSERT INTO messages (date, message, stock_code, msg_type)
            VALUES (?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d"),
                text,
                ",".join(codes),
                msg_type
            ))
            conn.commit()
        except Exception as e:
            print(f"儲存錯誤: {e}")
        finally:
            conn.close()
    
    def get_stats(self):
        conn = sqlite3.connect("stock.db")
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM messages")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT stock_code) FROM messages WHERE stock_code != ''")
            unique_stocks = cursor.fetchone()[0]
            
            return {"total": total, "stocks": unique_stocks}
        except:
            return {"total": 0, "stocks": 0}
        finally:
            conn.close()

# 建立 Bot 實例
bot = StockBot()
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 股票分析 Bot 運行中！"

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
        # 統計指令
        if text.lower() in ["統計", "摘要", "summary"]:
            stats = bot.get_stats()
            reply_text = f"📊 股票資訊統計\n\n總收集: {stats['total']} 則\n涉及股票: {stats['stocks']} 檔"
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
            return
        
        # 分析股票訊息
        result = bot.analyze(text)
        
        if result["found"]:
            if result["codes"]:
                stock_names = [bot.stocks.get(code, code) for code in result["codes"]]
                codes_text = f"股票: {', '.join([f'{code}({name})' for code, name in zip(result['codes'], stock_names)])}"
            else:
                codes_text = "股票討論"
            
            reply_text = f"📈 已記錄 {result['type']} 資訊\n{codes_text}"
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
    
    except Exception as e:
        print(f"訊息處理錯誤: {e}")
        # 發生錯誤時的預設回覆
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="🤖 Bot 收到訊息了！")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
