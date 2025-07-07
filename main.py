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

class SimpleStockBot:
    def __init__(self):
        self.db_path = "stock.db"
        self.stocks = {
            "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2412": "中華電",
            "2882": "國泰金", "2308": "台達電", "2303": "聯電", "2002": "中鋼"
        }
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            date TEXT,
            message TEXT,
            stock_code TEXT,
            msg_type TEXT
        )
        """)
        conn.commit()
        conn.close()
    
    def analyze(self, text):
        codes = re.findall(r"\d{4}", text)
        found = [c for c in codes if c in self.stocks]
        
        if not found and not any(name in text for name in self.stocks.values()):
            return None
        
        text_lower = text.lower()
        if any(word in text_lower for word in ["買", "賣", "交易"]):
            msg_type = "交易"
        elif any(word in text_lower for word in ["漲", "跌", "價格"]):
            msg_type = "價格"
        else:
            msg_type = "討論"
        
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO messages (date, message, stock_code, msg_type) VALUES (?, ?, ?, ?)",
                    (datetime.now().strftime("%Y-%m-%d"), text, ",".join(found), msg_type))
        conn.commit()
        conn.close()
        
        return {"codes": found, "type": msg_type}
    
    def get_stats(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM messages")
        total = cursor.fetchone()[0]
        conn.close()
        return total

bot = SimpleStockBot()
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 股票 Bot 運行中！"

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
    
    if text.lower() in ["統計", "摘要"]:
        total = bot.get_stats()
        reply = f"📊 已收集 {total} 則股票訊息"
    else:
        result = bot.analyze(text)
        if result:
            codes_text = f"股票: {', '.join(result['codes'])}" if result['codes'] else "一般討論"
            reply = f"📈 已記錄 {result['type']} 資訊\n{codes_text}"
        else:
            return
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
