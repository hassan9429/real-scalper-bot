import time
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime
import threading
from flask import Flask

# ── CONFIG ───────────────────────────────────────────────────
TELEGRAM_TOKEN   = "8771502949:AAHh1uRdKujqL8smH7iSRChlW8SQrbq4z6w"
TELEGRAM_CHAT_ID = "6853922784"

# Indicator settings — same as your Pine Script
EMA_PERIOD = 200
STRENGTH   = 0.25
MIN_DIST   = 5  # minimum candles between signals

# Check every 60 seconds
CHECK_INTERVAL = 60

# ── FLASK SERVER (keeps Render.com free server alive) ────────
app = Flask(__name__)

@app.route("/")
def home():
    return "Real Scalper Bot is running!", 200

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ── TELEGRAM ─────────────────────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       message,
            "parse_mode": "Markdown"
        }, timeout=10)
        if response.json().get("ok"):
            print(f"Telegram sent: {message[:50]}")
        else:
            print(f"Telegram error: {response.json()}")
    except Exception as e:
        print(f"Telegram exception: {e}")

# ── FETCH XAUUSD DATA ────────────────────────────────────────
def fetch_data():
    try:
        # Fetch 1 minute XAUUSD data from Yahoo Finance
        url = "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X"
        params = {
            "interval":  "1m",
            "range":     "1d",
            "includePrePost": False
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, params=params, headers=headers, timeout=15)
        data = response.json()

        chart = data["chart"]["result"][0]
        timestamps = chart["timestamp"]
        quotes = chart["indicators"]["quote"][0]

        df = pd.DataFrame({
            "time":  pd.to_datetime(timestamps, unit="s"),
            "open":  quotes["open"],
            "high":  quotes["high"],
            "low":   quotes["low"],
            "close": quotes["close"],
            "volume":quotes["volume"]
        })

        # Drop rows with missing values
        df = df.dropna().reset_index(drop=True)
        return df

    except Exception as e:
        print(f"Data fetch error: {e}")
        return None

# ── CALCULATE INDICATOR ──────────────────────────────────────
def calculate_signals(df):
    try:
        # EMA 200
        df["ema200"] = ta.ema(df["close"], length=EMA_PERIOD)

        # It_value = (2*Close - High - Low) / (High - Low)
        df["denominator"] = df["high"] - df["low"]
        df["it_value"] = df.apply(
            lambda row: 0 if row["denominator"] == 0
            else (2 * row["close"] - row["high"] - row["low"]) / row["denominator"],
            axis=1
        )

        # Trend
        df["is_uptrend"]   = df["close"] > df["ema200"]
        df["is_downtrend"] = df["close"] < df["ema200"]

        # Signal conditions
        df["strict_buy"] = (
            (df["it_value"] > STRENGTH) &
            (df["it_value"].shift(1) > 0) &
            df["is_uptrend"]
        )
        df["strict_sell"] = (
            (df["it_value"] < -STRENGTH) &
            (df["it_value"].shift(1) < 0) &
            df["is_downtrend"]
        )

        # Spam reduction — min distance between signals
        last_signal_bar = -MIN_DIST - 1
        final_buy  = []
        final_sell = []

        for i in range(len(df)):
            if df["strict_buy"].iloc[i] and (i - last_signal_bar > MIN_DIST):
                final_buy.append(True)
                final_sell.append(False)
                last_signal_bar = i
            elif df["strict_sell"].iloc[i] and (i - last_signal_bar > MIN_DIST):
                final_buy.append(False)
                final_sell.append(True)
                last_signal_bar = i
            else:
                final_buy.append(False)
                final_sell.append(False)

        df["final_buy"]  = final_buy
        df["final_sell"] = final_sell

        return df

    except Exception as e:
        print(f"Calculation error: {e}")
        return None

# ── MAIN BOT LOOP ────────────────────────────────────────────
last_buy_time  = 0
last_sell_time = 0
COOLDOWN_SEC   = 5 * 60  # 5 minutes between same signal

def run_bot():
    global last_buy_time, last_sell_time

    print("Real Scalper Cloud Bot started!")
    send_telegram("🤖 *Real Scalper Bot Started*\nWatching XAUUSD for signals 24/7...")

    while True:
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking signals...")

            df = fetch_data()
            if df is None or len(df) < EMA_PERIOD + 10:
                print("Not enough data — waiting...")
                time.sleep(CHECK_INTERVAL)
                continue

            df = calculate_signals(df)
            if df is None:
                time.sleep(CHECK_INTERVAL)
                continue

            # Check last 2 candles for signals
            now = time.time()
            recent = df.tail(2)

            for _, row in recent.iterrows():
                if row["final_buy"] and (now - last_buy_time > COOLDOWN_SEC):
                    last_buy_time = now
                    msg = (
                        "🟢 *STRONG BUY*\n\n"
                        "Real Scalper @ Sheikh Hassan\n"
                        f"Symbol: XAUUSD\n"
                        f"Price: {row['close']:.3f}\n"
                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    send_telegram(msg)
                    print("STRONG BUY sent!")

                if row["final_sell"] and (now - last_sell_time > COOLDOWN_SEC):
                    last_sell_time = now
                    msg = (
                        "🔴 *STRONG SELL*\n\n"
                        "Real Scalper @ Sheikh Hassan\n"
                        f"Symbol: XAUUSD\n"
                        f"Price: {row['close']:.3f}\n"
                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    send_telegram(msg)
                    print("STRONG SELL sent!")

            print("Check complete — next check in 60 seconds")

        except Exception as e:
            print(f"Bot loop error: {e}")

        time.sleep(CHECK_INTERVAL)

# ── START ────────────────────────────────────────────────────
if __name__ == "__main__":
    # Run Flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Run bot
    run_bot()
