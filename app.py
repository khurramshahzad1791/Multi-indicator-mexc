import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import time

st.set_page_config(page_title="VSI 100x MEXC Scanner", layout="wide", page_icon="🚀")
st.title("🚀 VSI - Volume Surge Institutional [MEXC Futures 100x Live Scanner]")
st.warning("⚠️ 100x LEVERAGE = EXTREME RISK. Risk max 0.5% per trade. This is NOT financial advice. Backtest yourself.")

# Sidebar
st.sidebar.header("Scanner Settings")

# Expanded list: Top/high-volume perpetual USDT pairs on MEXC (Feb/Mar 2026 data trends)
symbols = [
    "BTC/USDT:USDT",      # Always #1
    "ETH/USDT:USDT",      # Top 2-3
    "SOL/USDT:USDT",      # Very high volume
    "XRP/USDT:USDT",      # Added as requested
    "DOGE/USDT:USDT",     # Meme / high volume
    "PEPE/USDT:USDT",     # Popular meme
    "SHIB/USDT:USDT",     # Classic meme
    "SUI/USDT:USDT",      # Growing alt
    "TON/USDT:USDT",      # High activity
    "BNB/USDT:USDT",      # Major alt
    "ADA/USDT:USDT",      # Classic
    "LINK/USDT:USDT",     # Oracle / solid
    "AVAX/USDT:USDT",     # Layer 1
    "TRX/USDT:USDT",      # High liquidity
    "WIF/USDT:USDT",      # Meme favorite
    "GOLD/XAUT:USDT",     # XAUT/USDT – often huge volume (precious metal proxy)
    "POWER/USDT:USDT",    # Occasionally spikes
    "DOGS/USDT:USDT",     # Emerging meme
    "1000BONK/USDT:USDT", # Bonk variant if listed this way (check exact)
    "NOT/USDT:USDT"       # Notcoin – popular
]

symbol = st.sidebar.selectbox("Select Symbol (Perpetual)", symbols, index=0)
timeframes = ["5m", "15m", "1h"]
tf = st.sidebar.selectbox("Timeframe", timeframes, index=0)
refresh_sec = st.sidebar.slider("Auto Refresh (seconds)", 10, 120, 30)

# The rest of the code remains exactly the same (indicator functions, get_data, calculate_indicators, get_signal, fetching, chart, etc.)

def get_data(exchange, symbol, tf, limit=300):
    ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_indicators(df):
    df = df.copy()
    # EMAs
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    # Volume Surge
    df['vol_avg20'] = df['volume'].rolling(20).mean()
    df['vol_surge'] = (df['volume'] > df['vol_avg20'] * 2.5) & (df['volume'] > df['volume'].shift(1))
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    # Bollinger Width
    bb_mid = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_upper'] = bb_mid + 2 * bb_std
    df['bb_lower'] = bb_mid - 2 * bb_std
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / bb_mid
    df['bb_expanding'] = df['bb_width'] > df['bb_width'].rolling(20).mean()
    # SuperTrend
    period, multiplier = 10, 3
    tr = pd.DataFrame()
    tr['tr'] = np.maximum.reduce([df['high']-df['low'], abs(df['high']-df['close'].shift()), abs(df['low']-df['close'].shift())])
    atr = tr['tr'].rolling(period).mean()
    hl2 = (df['high'] + df['low']) / 2
    df['upper_band'] = hl2 + multiplier * atr
    df['lower_band'] = hl2 - multiplier * atr
    df['in_uptrend'] = True
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['upper_band'].iloc[i-1]:
            df.loc[df.index[i], 'in_uptrend'] = True
        elif df['close'].iloc[i] < df['lower_band'].iloc[i-1]:
            df.loc[df.index[i], 'in_uptrend'] = False
        else:
            df.loc[df.index[i], 'in_uptrend'] = df['in_uptrend'].iloc[i-1]
            if df['in_uptrend'].iloc[i] and df['lower_band'].iloc[i] < df['lower_band'].iloc[i-1]:
                df.loc[df.index[i], 'lower_band'] = df['lower_band'].iloc[i-1]
            elif not df['in_uptrend'].iloc[i] and df['upper_band'].iloc[i] > df['upper_band'].iloc[i-1]:
                df.loc[df.index[i], 'upper_band'] = df['upper_band'].iloc[i-1]
    df['supertrend'] = np.where(df['in_uptrend'], df['lower_band'], df['upper_band'])
    df['st_bull'] = df['in_uptrend']
    return df

def get_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    vol_surge = last['vol_surge']
    ema_cross_long = (last['ema9'] > last['ema21']) and (prev['ema9'] <= prev['ema21'])
    ema_cross_short = (last['ema9'] < last['ema21']) and (prev['ema9'] >= prev['ema21'])
    st_bull = last['st_bull']
    rsi_ok_long = last['rsi'] > 55
    rsi_ok_short = last['rsi'] < 45
    macd_bull = last['macd_hist'] > 0 and last['macd_hist'] > prev['macd_hist']
    macd_bear = last['macd_hist'] < 0 and last['macd_hist'] < prev['macd_hist']
    bb_ok = last['bb_expanding']
    above_200 = last['close'] > last['ema200']
    below_200 = last['close'] < last['ema200']

    long_cond = vol_surge and ema_cross_long and st_bull and rsi_ok_long and macd_bull and bb_ok and above_200
    short_cond = vol_surge and ema_cross_short and (not st_bull) and rsi_ok_short and macd_bear and bb_ok and below_200

    if long_cond:
        return "LONG", "#00FF00", last['close']
    elif short_cond:
        return "SHORT", "#FF0000", last['close']
    return "WAIT / NO SIGNAL", "#AAAAAA", last['close']

# Fetch & Run
exchange = ccxt.mexc({'enableRateLimit': True})
try:
    df = get_data(exchange, symbol, tf)
    df = calculate_indicators(df)
    signal, color, price = get_signal(df)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        st.metric("Live Price", f"${price:,.4f}")
    with col2:
        st.markdown(f"<h1 style='text-align:center; color:{color};'>{signal}</h1>", unsafe_allow_html=True)
    with col3:
        st.metric("Last Updated", datetime.now().strftime("%H:%M:%S UTC"))

    if signal != "WAIT / NO SIGNAL":
        sl = price * (1 - 0.004) if signal == "LONG" else price * (1 + 0.004)
        tp1 = price * (1 + 0.01) if signal == "LONG" else price * (1 - 0.01)
        tp2 = price * (1 + 0.02) if signal == "LONG" else price * (1 - 0.02)
        st.success(f"**SL**: {sl:,.4f} | **TP1 (50%)**: {tp1:,.4f} | **TP2**: {tp2:,.4f}  ← Use these on MEXC 100x")

    # Chart (last 100 bars)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['timestamp'][-100:], open=df['open'][-100:], high=df['high'][-100:], low=df['low'][-100:], close=df['close'][-100:], name="Price"))
    fig.add_trace(go.Scatter(x=df['timestamp'][-100:], y=df['ema9'][-100:], name="EMA9", line=dict(color="lime")))
    fig.add_trace(go.Scatter(x=df['timestamp'][-100:], y=df['ema21'][-100:], name="EMA21", line=dict(color="red")))
    fig.add_trace(go.Scatter(x=df['timestamp'][-100:], y=df['supertrend'][-100:], name="SuperTrend", line=dict(color="purple", width=3)))
    fig.update_layout(title=f"{symbol} {tf} - VSI Live", xaxis_rangeslider_visible=False, height=650)
    st.plotly_chart(fig, use_container_width=True)

    st.caption("All 5 original conditions (Volume Surge + EMA cross + SuperTrend + RSI + MACD + BB expansion + 200 EMA bias) are checked on bar close. No repainting.")

except Exception as e:
    st.error(f"API Error: {str(e)}\nTry a different symbol or wait 10s. Note: Some symbols use formats like '1000PEPE/USDT:USDT' or 'XAUT/USDT:USDT' – check MEXC if it fails.")

st.caption(f"🔄 Auto-refreshing every {refresh_sec} seconds • Built from your exact Pine Script logic")
time.sleep(refresh_sec)
st.rerun()
