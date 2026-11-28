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

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr = calculate_atr(df, period=period).replace(0, np.nan)
    plus_di = (
        100
        * pd.Series(plus_dm, index=df.index)
        .ewm(alpha=1 / period, min_periods=period, adjust=False)
        .mean()
        / atr
    )
    minus_di = (
        100
        * pd.Series(minus_dm, index=df.index)
        .ewm(alpha=1 / period, min_periods=period, adjust=False)
        .mean()
        / atr
    )

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


def detect_divergence(df, indicator_series, lookback=24):
    """
    Mendeteksi divergensi harga vs indikator pada swing lokal terbaru:
    Mengembalikan string: 'BULL REG', 'BEAR REG', 'BULL HIDDEN', 'BEAR HIDDEN', atau ''.
    """
    if len(df) < lookback + 5 or len(indicator_series.dropna()) < lookback:
        return ""

    sub_df = df.tail(lookback).reset_index(drop=True)
    sub_ind = indicator_series.tail(lookback).reset_index(drop=True)

    # Cari pivot low (2 kiri, 2 kanan)
    pivot_lows = []
    pivot_highs = []
    for i in range(2, len(sub_df) - 2):
        l_val = float(sub_df.loc[i, "Low"])
        if (
            l_val <= float(sub_df.loc[i - 1, "Low"])
            and l_val <= float(sub_df.loc[i - 2, "Low"])
            and l_val <= float(sub_df.loc[i + 1, "Low"])
            and l_val <= float(sub_df.loc[i + 2, "Low"])
            and pd.notna(sub_ind.iloc[i])
        ):
            pivot_lows.append((i, l_val, float(sub_ind.iloc[i])))

        h_val = float(sub_df.loc[i, "High"])
        if (
            h_val >= float(sub_df.loc[i - 1, "High"])
            and h_val >= float(sub_df.loc[i - 2, "High"])
            and h_val >= float(sub_df.loc[i + 1, "High"])
            and h_val >= float(sub_df.loc[i + 2, "High"])
            and pd.notna(sub_ind.iloc[i])
        ):
            pivot_highs.append((i, h_val, float(sub_ind.iloc[i])))

    # Cek Bullish Divergence pada 2 pivot low terakhir (pivot kedua dekat bar terbaru)
    if len(pivot_lows) >= 2:
        idx1, p1, ind1 = pivot_lows[-2]
        idx2, p2, ind2 = pivot_lows[-1]
        if (len(sub_df) - 1 - idx2) <= 5 and (idx2 - idx1) >= 4:
            if p2 < p1 and ind2 > ind1:
                return "BULL REG"
            if p2 > p1 and ind2 < ind1:
                return "BULL HIDDEN"

    # Cek Bearish Divergence pada 2 pivot high terakhir
    if len(pivot_highs) >= 2:
        idx1, p1, ind1 = pivot_highs[-2]
        idx2, p2, ind2 = pivot_highs[-1]
        if (len(sub_df) - 1 - idx2) <= 5 and (idx2 - idx1) >= 4:
            if p2 > p1 and ind2 < ind1:
                return "BEAR REG"
            if p2 < p1 and ind2 > ind1:
                return "BEAR HIDDEN"

    return ""


def calculate_volume_flow_proxy(df):
    """
    Metrik proxy aliran/penyerapan berbasis OHLCV harian (bukan broker summary asli).
    """
    o = df["Open"]
    h = df["High"]
    l = df["Low"]
    c = df["Close"]
    v = df["Volume"].fillna(0)

    rng = (h - l).replace(0, np.nan)
    # Close Location Value (CLV): -1 di Low, +1 di High
    clv = (((c - l) - (h - c)) / rng).fillna(0.0)
    vol_ma20 = v.rolling(window=20).mean().replace(0, np.nan)
    rvol = (v / vol_ma20).fillna(1.0)

    # Signed flow proxy berbobot RVOL
    signed_flow = v * clv
    flow_cum = signed_flow.cumsum()

    lower_wick = (pd.concat([o, c], axis=1).min(axis=1) - l).clip(lower=0)
    lower_wick_ratio = (lower_wick / rng).fillna(0.0)

    is_down_bar = c < o
    dip_absorption = bool(
        is_down_bar.iloc[-1]
        and rvol.iloc[-1] >= 1.3
        and (clv.iloc[-1] >= -0.1 or lower_wick_ratio.iloc[-1] >= 0.35)
    )

    price_chg_5 = float(c.iloc[-1] - c.iloc[-6]) if len(c) >= 6 else 0.0
    flow_chg_5 = float(flow_cum.iloc[-1] - flow_cum.iloc[-6]) if len(flow_cum) >= 6 else 0.0
    acc_divergence = bool(price_chg_5 <= 0 and flow_chg_5 > 0)

    # Low Volume Pullback: harga koreksi ringan (< 0%) di atas MA50 dengan volume < 0.75x MA20
    ma50 = c.rolling(window=50).mean()
    low_vol_pullback = bool(
        len(c) >= 50
        and pd.notna(ma50.iloc[-1])
        and float(c.iloc[-1]) > float(ma50.iloc[-1])
        and float(c.iloc[-1]) < float(c.iloc[-2])
        and float(rvol.iloc[-1]) <= 0.75
    )

    # Breakout + High RVOL: close menembus highest high 20 bar sebelumnya + RVOL >= 1.8
    prev_high_20 = float(h.iloc[-21:-1].max()) if len(h) >= 21 else np.nan
    breakout_high_rvol = bool(
        pd.notna(prev_high_20)
        and float(c.iloc[-1]) > prev_high_20
        and float(rvol.iloc[-1]) >= 1.8
    )

    # Skor Flow / Absorption (-100 s.d. +100) berdasarkan CLV 5 bar terakhir berbobot RVOL
    recent_clv_rvol = (clv * rvol.clip(upper=3.0)).tail(5).mean()
    flow_score = round(float(np.clip(recent_clv_rvol * 50, -100, 100)), 1)

    flow_series = [
        {"time": idx.strftime("%Y-%m-%d"), "value": round(float(val), 2)}
        for idx, val in flow_cum.tail(160).items()
    ]

    return {
        "dip_absorption": dip_absorption,
        "acc_divergence": acc_divergence,
        "low_vol_pullback": low_vol_pullback,
        "breakout_high_rvol": breakout_high_rvol,
        "flow_score": flow_score,
        "flow_series": flow_series,
    }


def detect_smc_patterns(df):
    """
    Deteksi struktur SMC/ICT pada bar terbaru:
      - fvg: 'BULL FVG' | 'BEAR FVG' | ''
      - ifvg: 'BULL iFVG' | 'BEAR iFVG' | ''
      - sweep: 'SSL SWEEP' | 'BSL SWEEP' | ''
      - mss_choch: 'BULL MSS' | 'BEAR MSS' | ''
      - ob_tap: 'BULL OB TAP' | 'BEAR OB TAP' | ''
      - cisd: 'BULL CISD' | 'BEAR CISD' | ''
    """
    out = {
        "fvg": "",
        "ifvg": "",
        "sweep": "",
        "mss_choch": "",
        "ob_tap": "",
        "cisd": "",
    }
    if len(df) < 25:
        return out

    c0 = df.iloc[-3]
    c1 = df.iloc[-2]
    c2 = df.iloc[-1]

    last_open = float(c2["Open"])
    last_high = float(c2["High"])
    last_low = float(c2["Low"])
    last_close = float(c2["Close"])

    # 1. FVG 3-candle terbaru
    if last_low > float(c0["High"]):
        out["fvg"] = "BULL FVG"
    elif last_high < float(c0["Low"]):
        out["fvg"] = "BEAR FVG"

    # 2. iFVG (Inversion FVG dari 15 bar terakhir yang ditembus close terbaru)
    sub_fvg = df.iloc[-16:-1].reset_index(drop=True)
    for k in range(2, len(sub_fvg)):
        b0 = sub_fvg.iloc[k - 2]
        b2 = sub_fvg.iloc[k]
        # Bearish FVG lama ditembus ke atas -> Bullish iFVG
        if float(b2["High"]) < float(b0["Low"]):
            gap_top = float(b0["Low"])
            if float(c1["Close"]) <= gap_top and last_close > gap_top:
                out["ifvg"] = "BULL iFVG"
        # Bullish FVG lama ditembus ke bawah -> Bearish iFVG
        elif float(b2["Low"]) > float(b0["High"]):
            gap_bot = float(b0["High"])
            if float(c1["Close"]) >= gap_bot and last_close < gap_bot:
                out["ifvg"] = "BEAR iFVG"

    # 3. Liquidity Sweep (20 bar)
    prev_20 = df.iloc[-21:-1]
    prev_high_20 = float(prev_20["High"].max())
    prev_low_20 = float(prev_20["Low"].min())

    if last_low < prev_low_20 and last_close > prev_low_20:
        out["sweep"] = "SSL SWEEP"
    elif last_high > prev_high_20 and last_close < prev_high_20:
        out["sweep"] = "BSL SWEEP"

    # 4. MSS / CHoCH (Penembusan swing high/low 10 bar sebelumnya dengan close kuat)
    prev_10 = df.iloc[-11:-1]
    swing_h10 = float(prev_10["High"].max())
    swing_l10 = float(prev_10["Low"].min())
    if last_close > swing_h10 and float(c1["Close"]) <= swing_h10:
        out["mss_choch"] = "BULL MSS"
    elif last_close < swing_l10 and float(c1["Close"]) >= swing_l10:
        out["mss_choch"] = "BEAR MSS"

    # 5. Order Block Tap (menguji zona candle lawan terakhir sebelum impuls 5-15 bar lalu)
    sub_ob = df.iloc[-15:-3].reset_index(drop=True)
    for k in range(len(sub_ob) - 2):
        ob_c = sub_ob.iloc[k]
        imp1 = sub_ob.iloc[k + 1]
        imp2 = sub_ob.iloc[k + 2]
        ob_h, ob_l = float(ob_c["High"]), float(ob_c["Low"])
        ob_rng = max(ob_h - ob_l, 1e-6)
        # Bullish OB: candle merah diikuti 2 candle hijau impulsif (> 1.8x range OB)
        if float(ob_c["Close"]) < float(ob_c["Open"]) and (float(imp2["Close"]) - ob_h) > 1.5 * ob_rng:
            if last_low <= ob_h and last_close >= ob_l:
                out["ob_tap"] = "BULL OB TAP"
        # Bearish OB: candle hijau diikuti 2 candle merah impulsif
        elif float(ob_c["Close"]) > float(ob_c["Open"]) and (ob_l - float(imp2["Close"])) > 1.5 * ob_rng:
            if last_high >= ob_l and last_close <= ob_h:
                out["ob_tap"] = "BEAR OB TAP"

    # 6. CISD (Change in State of Delivery)
    # Penutupan bar terbaru menembus harga pembukaan rangkaian candle berlawanan sebelumnya
    if last_close > last_open and float(c1["Close"]) < float(c1["Open"]):
        if last_close > float(c1["Open"]):
            out["cisd"] = "BULL CISD"
    elif last_close < last_open and float(c1["Close"]) > float(c1["Open"]):
        if last_close < float(c1["Open"]):
            out["cisd"] = "BEAR CISD"

    return out


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
    """Logika CRT Dynamic dengan deteksi CONFIRMED vs POTENTIAL + Mid50 Reclaim."""
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

    # Cek Mid50 Reclaim pada bar terakhir jika ada setup aktif
    mid50_reclaim = False
    if active_setup and not active_setup.get("is_broken") and len(df) >= 2:
        mid_val = active_setup["mid50"]
        prev_c = float(df.iloc[-2]["Close"])
        curr_c = float(df.iloc[-1]["Close"])
        curr_l = float(df.iloc[-1]["Low"])
        if active_setup["dir"] == 1 and (prev_c < mid_val or curr_l < mid_val) and curr_c > mid_val:
            mid50_reclaim = True

    return {
        "active_bias": "BULLISH OPEN" if open_dir == 1 else ("BEARISH OPEN" if open_dir == -1 else "NEUTRAL"),
        "latest_setup": active_setup,
        "mid50_reclaim": mid50_reclaim,
        "markers": markers[-15:],
    }


def compute_all_indicators(df_ohlcv, tf_name="1d", last_daily_date=None):
    """
    Menghitung paket indikator lengkap untuk 6 kategori screener & overlay chart.
    """
    df = df_ohlcv.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if len(df) < 15:
        return {}, {}

    close = df["Close"]
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else float(close.iloc[-1])
    last_c = float(close.iloc[-1])

    # Moving Averages lengkap untuk Trend & MA section
    ma9 = calculate_ma(close, 9)
    ma14 = calculate_ma(close, 14)
    ma20 = calculate_ma(close, 20)
    ema21 = calculate_ema(close, 21)
    ma50 = calculate_ma(close, 50)
    ma100 = calculate_ma(close, 100)
    ma200 = calculate_ma(close, 200)

    def _val(series, idx=-1, dec=2):
        if len(series) < abs(idx):
            return None
        v = series.iloc[idx]
        return round(float(v), dec) if pd.notna(v) else None

    ma9_v = _val(ma9)
    ma14_v = _val(ma14)
    ma20_v = _val(ma20)
    ema21_v = _val(ema21)
    ma50_v = _val(ma50)
    ma100_v = _val(ma100)
    ma200_v = _val(ma200)

    # Trend flags
    perfect_alignment = bool(
        all(x is not None for x in [ma9_v, ma14_v, ma20_v, ma50_v, ma100_v, ma200_v])
        and (last_c > ma9_v > ma14_v > ma20_v > ma50_v > ma100_v > ma200_v)
    )

    ma20_prev = _val(ma20, -2)
    ma50_prev = _val(ma50, -2)
    golden_cross = bool(
        all(x is not None for x in [ma20_v, ma50_v, ma20_prev, ma50_prev])
        and (ma20_prev <= ma50_prev)
        and (ma20_v > ma50_v)
    )

    pullback_ma20_ema21 = bool(
        ma20_v is not None
        and ema21_v is not None
        and ma50_v is not None
        and last_c > ma50_v
        and abs((last_c - ema21_v) / ema21_v) <= 0.015
    )

    rsi14 = calculate_rsi(close, rsi_len=14)
    rsi14_v = _val(rsi14)

    oversold_uptrend = bool(
        ma200_v is not None
        and rsi14_v is not None
        and last_c > ma200_v
        and rsi14_v <= 40.0
    )

    stoch_k, stoch_d = calculate_stoch_rsi(close, rsi_len=10, stoch_len=10, smooth_k=5, smooth_d=5)
    macd_line, signal_line, macd_hist = calculate_macd(close)
    atr14 = calculate_atr(df, period=14)
    adx14, _, _ = calculate_adx(df, period=14)
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(close, window=20, num_std=2.0)
    obv = calculate_obv(close, df["Volume"])
    flow_proxy = calculate_volume_flow_proxy(df)

    # Divergence Detection (RSI, MACD Hist, StochRSI K, OBV)
    div_rsi = detect_divergence(df, rsi14)
    div_macd = detect_divergence(df, macd_hist)
    div_stoch = detect_divergence(df, stoch_k)
    div_obv = detect_divergence(df, obv)

    ref_date = last_daily_date if last_daily_date is not None else df.index[-1]
    closed_flag = is_last_candle_closed(ref_date, tf_name)
    crt_info = analyze_crt(df, tf_name=tf_name, last_bar_closed=closed_flag)
    smc_info = detect_smc_patterns(df)

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
    crth_v = None
    crtl_v = None
    mid50_v = None
    mid50_reclaim = bool(crt_info and crt_info.get("mid50_reclaim"))

    if crt_info and crt_info.get("latest_setup") and not crt_info["latest_setup"].get("is_broken"):
        setup = crt_info["latest_setup"]
        crt_status = setup["status"]
        crt_sig = setup["signal"]
        crt_dir = setup["dir"]
        crth_v = setup["crth"]
        crtl_v = setup["crtl"]
        mid50_v = setup["mid50"]

    summary_fields = {
        # Trend & Moving Averages
        "ma9": ma9_v,
        "ma14": ma14_v,
        "ma20": ma20_v,
        "ema21": ema21_v,
        "ma50": ma50_v,
        "ma100": ma100_v,
        "ma200": ma200_v,
        "dist_ma20": round(((last_c - ma20_v) / ma20_v) * 100, 2) if ma20_v else None,
        "above_ma20": bool(ma20_v is not None and last_c > ma20_v),
        "above_ma50": bool(ma50_v is not None and last_c > ma50_v),
        "perfect_alignment": perfect_alignment,
        "golden_cross": golden_cross,
        "pullback_ma20_ema21": pullback_ma20_ema21,
        "oversold_uptrend": oversold_uptrend,

        # Oscillators & Volatility
        "rsi14": rsi14_v,
        "stoch_k": round(k_now, 2),
        "stoch_d": round(d_now, 2),
        "stoch_os_cross": bool(is_golden_cross and is_oversold),
        "macd": _val(macd_line, -1, 4),
        "macd_signal": _val(signal_line, -1, 4),
        "macd_hist": _val(macd_hist, -1, 4),
        "atr14": _val(atr14),
        "adx14": _val(adx14),
        "bb_upper": _val(bb_upper),
        "bb_mid": _val(bb_mid),
        "bb_lower": _val(bb_lower),

        # Divergence
        "div_rsi": div_rsi,
        "div_macd": div_macd,
        "div_stoch": div_stoch,
        "div_obv": div_obv,

        # Volume & Flow Proxy
        "obv": int(obv.iloc[-1]) if pd.notna(obv.iloc[-1]) else 0,
        "dip_absorption": flow_proxy["dip_absorption"],
        "acc_divergence": flow_proxy["acc_divergence"],
        "low_vol_pullback": flow_proxy["low_vol_pullback"],
        "breakout_high_rvol": flow_proxy["breakout_high_rvol"],
        "flow_score": flow_proxy["flow_score"],

        # CRT & Price Action
        "crt_bull": is_crt_bull,
        "crt_bear": is_crt_bear,
        "crt_dir": crt_dir,
        "crt_status": crt_status,
        "crt_sig": crt_sig,
        "crth": crth_v,
        "crtl": crtl_v,
        "mid50": mid50_v,
        "mid50_reclaim": mid50_reclaim,

        # SMC / ICT
        "fvg": smc_info["fvg"],
        "ifvg": smc_info["ifvg"],
        "sweep": smc_info["sweep"],
        "mss_choch": smc_info["mss_choch"],
        "ob_tap": smc_info["ob_tap"],
        "cisd": smc_info["cisd"],
    }

    chart_overlays = {
        "crt": crt_info,
        "flow_proxy": flow_proxy["flow_series"],
    }

    return summary_fields, chart_overlays
