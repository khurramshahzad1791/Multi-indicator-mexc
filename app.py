import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import time

st.set_page_config(page_title="VSI 100x MEXC Scanner", layout="wide", page_icon="🚀")
st.title("🚀 VSI - Volume Surge Institutional [MEXC Futures 100x]")
st.warning("⚠️ 100x LEVERAGE = EXTREME RISK. Risk max 0.5% per trade. Not financial advice.")

# Sidebar
st.sidebar.header("Scanner Settings")
symbols = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT",
    "DOGE/USDT:USDT", "PEPE/USDT:USDT", "SHIB/USDT:USDT", "SUI/USDT:USDT",
    "TON/USDT:USDT", "BNB/USDT:USDT", "ADA/USDT:USDT", "LINK/USDT:USDT",
    "AVAX/USDT:USDT", "TRX/USDT:USDT", "WIF/USDT:USDT", "GOLD/XAUT:USDT"
]
symbol = st.sidebar.selectbox("Select Symbol", symbols, index=0)

tf_options = {"5m": "5m", "15m": "15m", "30m (Half Hourly)": "30m", "1h": "1h", 
              "4h": "4h", "Daily": "1d", "Weekly": "1w"}
tf_display = st.sidebar.selectbox("Timeframe", list(tf_options.keys()), index=0)
tf = tf_options[tf_display]

a1_mode = st.sidebar.checkbox("Only A1 Setups (Highest Probability)", value=False)

refresh_sec = st.sidebar.slider("Auto Refresh (seconds)", 20, 60, 30)

# === INDICATOR FUNCTIONS (same powerful logic) ===
def get_data(exchange, symbol, tf, limit=250):
    ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_indicators(df):
    df = df.copy()
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    df['vol_avg20'] = df['volume'].rolling(20).mean()
    df['vol_surge'] = (df['volume'] > df['vol_avg20'] * (3.5 if a1_mode else 2.5)) & (df['volume'] > df['volume'].shift(1))
    
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    df['macd_hist'] = macd - macd.ewm(span=9, adjust=False).mean()
    
    bb_mid = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_width'] = (bb_mid + 2*bb_std - (bb_mid - 2*bb_std)) / bb_mid
    df['bb_expanding'] = df['bb_width'] > df['bb_width'].rolling(20).mean()
    
    period, mult = 10, 3
    hl2 = (df['high'] + df['low']) / 2
    tr = pd.concat([df['high']-df['low'], abs(df['high']-df['close'].shift()), abs(df['low']-df['close'].shift())], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    df['upper'] = hl2 + mult * atr
    df['lower'] = hl2 - mult * atr
    df['in_uptrend'] = True
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['upper'].iloc[i-1]:
            df.loc[df.index[i], 'in_uptrend'] = True
        elif df['close'].iloc[i] < df['lower'].iloc[i-1]:
            df.loc[df.index[i], 'in_uptrend'] = False
        else:
            df.loc[df.index[i], 'in_uptrend'] = df['in_uptrend'].iloc[i-1]
    df['supertrend'] = np.where(df['in_uptrend'], df['lower'], df['upper'])
    df['st_bull'] = df['in_uptrend']
    return df

def get_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    vol_surge = last['vol_surge']
    ema_cross_long = last['ema9'] > last['ema21'] and prev['ema9'] <= prev['ema21']
    ema_cross_short = last['ema9'] < last['ema21'] and prev['ema9'] >= prev['ema21']
    
    rsi_long = last['rsi'] > (58 if a1_mode else 55)
    rsi_short = last['rsi'] < (42 if a1_mode else 45)
    
    macd_bull = last['macd_hist'] > 0 and last['macd_hist'] > prev['macd_hist'] * (1.5 if a1_mode else 1)
    macd_bear = last['macd_hist'] < 0 and last['macd_hist'] < prev['macd_hist'] * (1.5 if a1_mode else 1)
    
    st_confirmed = last['st_bull'] and df['st_bull'].iloc[-3:].all() if a1_mode else last['st_bull']
    
    bb_ok = last['bb_expanding']
    above_200 = last['close'] > last['ema200']
    below_200 = last['close'] < last['ema200']
    
    long_cond = vol_surge and ema_cross_long and st_confirmed and rsi_long and macd_bull and bb_ok and above_200
    short_cond = vol_surge and ema_cross_short and (not last['st_bull']) and rsi_short and macd_bear and bb_ok and below_200
    
    if long_cond:
        return f"A1 LONG" if a1_mode else "LONG", "#00FF00", last['close']
    if short_cond:
        return f"A1 SHORT" if a1_mode else "SHORT", "#FF0000", last['close']
    return "WAIT / NO SIGNAL", "#AAAAAA", last['close']

# Run
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
        st.metric("Timeframe", tf_display)

    if signal != "WAIT / NO SIGNAL":
        sl = price * (1 - 0.004) if "LONG" in signal else price * (1 + 0.004)
        tp1 = price * (1 + 0.01) if "LONG" in signal else price * (1 - 0.01)
        tp2 = price * (1 + 0.02) if "LONG" in signal else price * (1 - 0.02)
        st.success(f"**SL**: {sl:,.4f} | **TP1 (50%)**: {tp1:,.4f} | **TP2**: {tp2:,.4f}")

    # Chart (fixed with new width parameter)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['timestamp'][-120:], open=df['open'][-120:], high=df['high'][-120:], low=df['low'][-120:], close=df['close'][-120:]))
    fig.add_trace(go.Scatter(x=df['timestamp'][-120:], y=df['ema9'][-120:], name="EMA9", line=dict(color="lime")))
    fig.add_trace(go.Scatter(x=df['timestamp'][-120:], y=df['ema21'][-120:], name="EMA21", line=dict(color="red")))
    fig.add_trace(go.Scatter(x=df['timestamp'][-120:], y=df['supertrend'][-120:], name="SuperTrend", line=dict(color="purple", width=3)))
    fig.update_layout(title=f"{symbol} — {tf_display} — VSI Signal: {signal}", height=650, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, width='stretch')

except Exception as e:
    st.error(f"Error: {str(e)} — Try another symbol or wait 10s.")

st.caption(f"🔄 Auto-refreshing every {refresh_sec}s • A1 = strictest high-probability setups only")
time.sleep(refresh_sec)
st.rerun()
