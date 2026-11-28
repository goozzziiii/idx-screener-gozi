import calendar
import numpy as np
import pandas as pd


def calculate_ma(close_series, window):
    return close_series.rolling(window=window).mean()


def calculate_ema(close_series, span):
    return close_series.ewm(span=span, adjust=False).mean()


def calculate_rsi(close_series, rsi_len=14):
    """Wilder's Smoothing (RMA) RSI."""
    delta = close_series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / rsi_len, min_periods=rsi_len, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_len, min_periods=rsi_len, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.where(avg_loss != 0, 100.0).where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)


def calculate_stoch_rsi(close_series, rsi_len=10, stoch_len=10, smooth_k=5, smooth_d=5):
    rsi = calculate_rsi(close_series, rsi_len=rsi_len)
    rsi_min = rsi.rolling(window=stoch_len).min()
    rsi_max = rsi.rolling(window=stoch_len).max()
    denom = (rsi_max - rsi_min).replace(0, np.nan)

    raw_stoch = 100 * ((rsi - rsi_min) / denom)
    k = raw_stoch.rolling(window=smooth_k).mean()
    d = k.rolling(window=smooth_d).mean()
    return k, d


def calculate_macd(close_series, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(close_series, fast)
    ema_slow = calculate_ema(close_series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def calculate_atr(df, period=14):
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def calculate_adx(df, period=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr = calculate_atr(df, period=period).replace(0, np.nan)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean() / atr

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
    adx = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return adx, plus_di, minus_di


def calculate_bollinger_bands(close_series, window=20, num_std=2.0):
    mid = close_series.rolling(window=window).mean()
    std = close_series.rolling(window=window).std()
    upper = mid + (num_std * std)
    lower = mid - (num_std * std)
    return upper, mid, lower


def calculate_obv(close_series, volume_series):
    direction = np.sign(close_series.diff().fillna(0))
    return (direction * volume_series.fillna(0)).cumsum()


def calculate_volume_flow_proxy(df):
    """
    Metrik proxy aliran/penyerapan berbasis OHLCV harian (bukan broker summary asli).
    Membantu mengidentifikasi tekanan jual vs penyerapan (absorption) saat harga turun/pullback.
    """
    o = df["Open"]
    h = df["High"]
    l = df["Low"]
    c = df["Close"]
    v = df["Volume"].fillna(0)

    rng = (h - l).replace(0, np.nan)
    # Posisi close dalam range harian: 0 = di Low, 1 = di High
    close_pos = ((c - l) / rng).fillna(0.5)
    # Signed volume proxy: mengalir positif jika close berada di atas titik tengah range
    signed_vol = v * ((close_pos - 0.5) * 2.0)
    flow_cum = signed_vol.cumsum()

    # Skor penyerapan pada bar terakhir: volume relatif tinggi + close bertahan kuat di range
    vol_ma20 = v.rolling(window=20).mean().replace(0, np.nan)
    rvol = (v / vol_ma20).fillna(1.0)
    lower_wick = (pd.concat([o, c], axis=1).min(axis=1) - l).clip(lower=0)
    lower_wick_ratio = (lower_wick / rng).fillna(0.0)

    is_down_bar = c < o
    dip_absorption = bool(is_down_bar.iloc[-1] and rvol.iloc[-1] >= 1.3 and (close_pos.iloc[-1] >= 0.45 or lower_wick_ratio.iloc[-1] >= 0.35))

    # Divergensi aliran proxy sederhana: harga 5 bar turun/datar, tapi flow_cum 5 bar naik
    price_chg_5 = float(c.iloc[-1] - c.iloc[-6]) if len(c) >= 6 else 0.0
    flow_chg_5 = float(flow_cum.iloc[-1] - flow_cum.iloc[-6]) if len(flow_cum) >= 6 else 0.0
    acc_divergence = bool(price_chg_5 <= 0 and flow_chg_5 > 0)

    flow_series = [
        {"time": idx.strftime("%Y-%m-%d"), "value": round(float(val), 2)}
        for idx, val in flow_cum.tail(120).items()
    ]

    return {
        "dip_absorption": dip_absorption,
        "acc_divergence": acc_divergence,
        "close_pos_today": round(float(close_pos.iloc[-1]), 2),
        "lower_wick_ratio": round(float(lower_wick_ratio.iloc[-1]), 2),
        "flow_series": flow_series,
    }


def detect_smc_patterns(df):
    """Deteksi FVG 3-candle terbaru & Liquidity Sweep 20-bar."""
    fvg_type = ""
    sweep_type = ""
    if len(df) < 25:
        return fvg_type, sweep_type

    c0 = df.iloc[-3]
    c2 = df.iloc[-1]
    if float(c2["Low"]) > float(c0["High"]):
        fvg_type = "BULL FVG"
    elif float(c2["High"]) < float(c0["Low"]):
        fvg_type = "BEAR FVG"

    prev_20 = df.iloc[-21:-1]
    prev_high_20 = float(prev_20["High"].max())
    prev_low_20 = float(prev_20["Low"].min())

    last_high = float(c2["High"])
    last_low = float(c2["Low"])
    last_close = float(c2["Close"])

    if last_low < prev_low_20 and last_close > prev_low_20:
        sweep_type = "SSL SWEEP"
    elif last_high > prev_high_20 and last_close < prev_high_20:
        sweep_type = "BSL SWEEP"

    return fvg_type, sweep_type


def is_last_candle_closed(last_daily_date, tf_name):
    dt = pd.to_datetime(last_daily_date)
    if tf_name == "1d":
        return True
    if tf_name == "1w":
        return dt.weekday() >= 4
    if tf_name == "1m":
        last_day_of_month = calendar.monthrange(dt.year, dt.month)[1]
        remaining_days = last_day_of_month - dt.day
        if remaining_days == 0:
            return True
        if remaining_days <= 2 and dt.weekday() == 4:
            return True
        return False
    return True


def analyze_crt(df, tf_name="1d", last_bar_closed=True, scan_bars=60, min_ticks_ratio=0.001, block_opposite=True):
    """Logika CRT Dynamic dengan deteksi CONFIRMED vs POTENTIAL."""
    if len(df) < 5:
        return None

    sub = df.tail(scan_bars + 2).reset_index()
    date_col = sub.columns[0]
    open_dir = 0
    open_high = None
    open_low = None

    active_setup = None
    markers = []

    for i in range(1, len(sub)):
        c1 = sub.iloc[i - 1]
        c2 = sub.iloc[i]
        is_latest_bar = i == len(sub) - 1
        bar_is_potential = is_latest_bar and (not last_bar_closed)

        o1, h1, l1, cl1 = float(c1["Open"]), float(c1["High"]), float(c1["Low"]), float(c1["Close"])
        o2, h2, l2, cl2 = float(c2["Open"]), float(c2["High"]), float(c2["Low"]), float(c2["Close"])
        t2 = pd.to_datetime(c2[date_col]).strftime("%Y-%m-%d")

        if open_dir != 0:
            if h2 > open_high or l2 < open_low:
                open_dir = 0
                open_high = None
                open_low = None
                if active_setup:
                    active_setup["is_broken"] = True

        c1_range = h1 - l1
        if c1_range <= 0:
            continue
        c1_mid = l1 + (c1_range * 0.5)
        buf = max(1.0, l1 * min_ticks_ratio)

        c2_body_top = max(o2, cl2)
        c2_body_bot = min(o2, cl2)
        body_inside = (c2_body_top <= h1) and (c2_body_bot >= l1)

        bull_base = body_inside and (l2 <= l1 - buf) and (h2 <= h1)
        bear_base = body_inside and (h2 >= h1 + buf) and (l2 >= l1)
        dbl = body_inside and (l2 <= l1 - buf) and (h2 >= h1 + buf)

        sig = 0
        if dbl:
            sig = 3
        elif bull_base:
            sig = 2 if (h2 > c1_mid) else 1
        elif bear_base:
            sig = -2 if (l2 < c1_mid) else -1

        if sig != 0:
            new_dir = 1 if sig in (1, 2) else (-1 if sig in (-1, -2) else 0)
            is_blocked = block_opposite and (open_dir != 0) and (new_dir != 0) and (new_dir != open_dir)

            if not is_blocked:
                if new_dir != 0:
                    open_dir = new_dir
                    open_high = h1
                    open_low = l1

                sig_map = {
                    1: "BULL CRT",
                    2: "BULL (>50%)",
                    -1: "BEAR CRT",
                    -2: "BEAR (>50%)",
                    3: "DBL SWEEP",
                }
                base_name = sig_map[sig]
                sig_name = f"POTENTIAL {base_name}" if bar_is_potential else base_name

                active_setup = {
                    "signal": sig_name,
                    "base_signal": base_name,
                    "status": "POTENTIAL" if bar_is_potential else "CONFIRMED",
                    "dir": new_dir,
                    "crth": round(h1, 2),
                    "crtl": round(l1, 2),
                    "mid50": round(c1_mid, 2),
                    "date_c2": t2,
                    "is_latest": is_latest_bar,
                    "is_broken": False,
                }

                if new_dir == 1:
                    markers.append({
                        "time": t2,
                        "position": "belowBar",
                        "color": "#eab308" if bar_is_potential else "#10b981",
                        "shape": "arrowUp",
                        "text": sig_name,
                    })
                elif new_dir == -1:
                    markers.append({
                        "time": t2,
                        "position": "aboveBar",
                        "color": "#eab308" if bar_is_potential else "#ef4444",
                        "shape": "arrowDown",
                        "text": sig_name,
                    })

    return {
        "active_bias": "BULLISH OPEN" if open_dir == 1 else ("BEARISH OPEN" if open_dir == -1 else "NEUTRAL"),
        "latest_setup": active_setup,
        "markers": markers[-15:],
    }


def compute_all_indicators(df_ohlcv, tf_name="1d", last_daily_date=None):
    """
    Menghitung paket indikator untuk satu DataFrame OHLCV.
    Mengembalikan:
      - summary_fields: dict ringkasan untuk screener
      - chart_overlays: dict overlay/marker untuk chart emiten
    """
    df = df_ohlcv.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if len(df) < 15:
        return {}, {}

    close = df["Close"]
    ma20 = calculate_ma(close, 20)
    ma50 = calculate_ma(close, 50)
    ma200 = calculate_ma(close, 200)
    ema21 = calculate_ema(close, 21)

    rsi14 = calculate_rsi(close, rsi_len=14)
    stoch_k, stoch_d = calculate_stoch_rsi(close, rsi_len=10, stoch_len=10, smooth_k=5, smooth_d=5)
    macd_line, signal_line, macd_hist = calculate_macd(close)
    atr14 = calculate_atr(df, period=14)
    adx14, _, _ = calculate_adx(df, period=14)
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(close, window=20, num_std=2.0)
    obv = calculate_obv(close, df["Volume"])
    flow_proxy = calculate_volume_flow_proxy(df)

    ref_date = last_daily_date if last_daily_date is not None else df.index[-1]
    closed_flag = is_last_candle_closed(ref_date, tf_name)
    crt_info = analyze_crt(df, tf_name=tf_name, last_bar_closed=closed_flag)
    fvg_type, sweep_type = detect_smc_patterns(df)

    last_c = float(close.iloc[-1])
    ma20_v = round(float(ma20.iloc[-1]), 2) if pd.notna(ma20.iloc[-1]) else None
    ma50_v = round(float(ma50.iloc[-1]), 2) if pd.notna(ma50.iloc[-1]) else None
    ma200_v = round(float(ma200.iloc[-1]), 2) if pd.notna(ma200.iloc[-1]) else None
    ema21_v = round(float(ema21.iloc[-1]), 2) if pd.notna(ema21.iloc[-1]) else None

    k_now = float(stoch_k.iloc[-1]) if pd.notna(stoch_k.iloc[-1]) else 50.0
    d_now = float(stoch_d.iloc[-1]) if pd.notna(stoch_d.iloc[-1]) else 50.0
    k_prev = float(stoch_k.iloc[-2]) if len(stoch_k) >= 2 and pd.notna(stoch_k.iloc[-2]) else 50.0
    d_prev = float(stoch_d.iloc[-2]) if len(stoch_d) >= 2 and pd.notna(stoch_d.iloc[-2]) else 50.0

    is_golden_cross = (k_prev <= d_prev) and (k_now > d_now) and (k_now > 0)
    is_oversold = (k_prev <= 20 or d_prev <= 20) and (k_now <= 25)

    is_crt_bull = bool(crt_info and crt_info["active_bias"] == "BULLISH OPEN")
    is_crt_bear = bool(crt_info and crt_info["active_bias"] == "BEARISH OPEN")

    crt_status = ""
    crt_sig = ""
    crt_dir = 0
    if (is_crt_bull or is_crt_bear) and crt_info.get("latest_setup"):
        crt_status = crt_info["latest_setup"]["status"]
        crt_sig = crt_info["latest_setup"]["signal"]
        crt_dir = crt_info["latest_setup"]["dir"]

    summary_fields = {
        "ma20": ma20_v,
        "ma50": ma50_v,
        "ma200": ma200_v,
        "ema21": ema21_v,
        "dist_ma20": round(((last_c - ma20_v) / ma20_v) * 100, 2) if ma20_v else None,
        "above_ma20": bool(ma20_v is not None and last_c > ma20_v),
        "above_ma50": bool(ma50_v is not None and last_c > ma50_v),
        "rsi14": round(float(rsi14.iloc[-1]), 2) if pd.notna(rsi14.iloc[-1]) else None,
        "stoch_k": round(k_now, 2),
        "stoch_d": round(d_now, 2),
        "stoch_os_cross": bool(is_golden_cross and is_oversold),
        "macd": round(float(macd_line.iloc[-1]), 4) if pd.notna(macd_line.iloc[-1]) else None,
        "macd_signal": round(float(signal_line.iloc[-1]), 4) if pd.notna(signal_line.iloc[-1]) else None,
        "macd_hist": round(float(macd_hist.iloc[-1]), 4) if pd.notna(macd_hist.iloc[-1]) else None,
        "atr14": round(float(atr14.iloc[-1]), 2) if pd.notna(atr14.iloc[-1]) else None,
        "adx14": round(float(adx14.iloc[-1]), 2) if pd.notna(adx14.iloc[-1]) else None,
        "bb_upper": round(float(bb_upper.iloc[-1]), 2) if pd.notna(bb_upper.iloc[-1]) else None,
        "bb_mid": round(float(bb_mid.iloc[-1]), 2) if pd.notna(bb_mid.iloc[-1]) else None,
        "bb_lower": round(float(bb_lower.iloc[-1]), 2) if pd.notna(bb_lower.iloc[-1]) else None,
        "obv": int(obv.iloc[-1]) if pd.notna(obv.iloc[-1]) else 0,
        "dip_absorption": flow_proxy["dip_absorption"],
        "acc_divergence": flow_proxy["acc_divergence"],
        "crt_bull": is_crt_bull,
        "crt_bear": is_crt_bear,
        "crt_dir": crt_dir,
        "crt_status": crt_status,
        "crt_sig": crt_sig,
        "fvg": fvg_type,
        "sweep": sweep_type,
    }

    chart_overlays = {
        "crt": crt_info,
        "flow_proxy": flow_proxy["flow_series"],
    }

    return summary_fields, chart_overlays
