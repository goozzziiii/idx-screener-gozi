import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import time
import calendar
from datetime import datetime

OUTPUT_DIR = "data"
CHARTS_DIR = os.path.join(OUTPUT_DIR, "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)


def get_all_idx_tickers():
    """Mencari otomatis file Excel/CSV IDX di folder dan mengambil semua kode 4 huruf"""
    files = [f for f in os.listdir(".") if f.endswith((".xlsx", ".xls", ".csv"))]
    if not files:
        print("PERINGATAN: Tidak ada file .xlsx atau .csv ditemukan!")
        return ["BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "TLKM.JK"]

    target_file = files[0]
    print(f"Membaca daftar emiten dari file: {target_file}...")

    try:
        df_list = pd.read_excel(target_file) if target_file.endswith((".xlsx", ".xls")) else pd.read_csv(target_file)
        tickers = []
        for col in df_list.columns:
            for val in df_list[col].dropna():
                clean = str(val).strip().upper()
                if len(clean) == 4 and clean.isalpha() and clean not in ["KODE", "CODE", "NAMA", "NAME"]:
                    tickers.append(f"{clean}.JK")
            if len(set(tickers)) > 500:
                break

        unique_tickers = sorted(list(set(tickers)))
        print(f"Sukses! Ditemukan {len(unique_tickers)} emiten aktif BEI.")
        return unique_tickers
    except Exception as e:
        print(f"Detail error saat membaca {target_file}: {e}")
        return ["BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "TLKM.JK"]


def get_ihsg_returns():
    """Mengunduh data IHSG (^JKSE) 1 tahun untuk kalkulasi Beta masing-masing emiten"""
    try:
        ihsg = yf.download("^JKSE", period="1y", interval="1d", progress=False)
        if ihsg is not None and not ihsg.empty:
            close_col = ihsg["Close"]
            if isinstance(close_col, pd.DataFrame):
                close_col = close_col.iloc[:, 0]
            ret = close_col.pct_change().dropna()
            ret.index = pd.to_datetime(ret.index).tz_localize(None)
            print(f"Data IHSG (^JKSE) berhasil dimuat ({len(ret)} hari bursa).")
            return ret
    except Exception as e:
        print(f"Gagal memuat data IHSG untuk Beta: {e}")
    return None


def calculate_beta(df_daily, ihsg_ret):
    """Menghitung Beta 1 tahun saham terhadap IHSG (^JKSE)"""
    if ihsg_ret is None or len(df_daily) < 60:
        return None
    try:
        stock_close = df_daily["Close"].tail(252).copy()
        stock_close.index = pd.to_datetime(stock_close.index).tz_localize(None)
        stock_ret = stock_close.pct_change().dropna()
        aligned = pd.concat([stock_ret, ihsg_ret], axis=1, join="inner").dropna()
        if len(aligned) < 40:
            return None
        cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])[0][1]
        var = np.var(aligned.iloc[:, 1])
        if var == 0:
            return None
        return round(float(cov / var), 2)
    except Exception:
        return None


def calculate_rsi(close_series, rsi_len=14):
    """Menghitung RSI (Wilder's Smoothing / RMA) standar TradingView"""
    delta = close_series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / rsi_len, min_periods=rsi_len, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_len, min_periods=rsi_len, adjust=False).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_stoch_rsi(close_series, rsi_len=10, stoch_len=10, smooth_k=5, smooth_d=5):
    """Menghitung Stochastic RSI (10, 10, 5, 5) standar TradingView"""
    rsi = calculate_rsi(close_series, rsi_len=rsi_len)
    rsi_min = rsi.rolling(window=stoch_len).min()
    rsi_max = rsi.rolling(window=stoch_len).max()
    denom = (rsi_max - rsi_min).replace(0, float("nan"))

    raw_stoch_rsi = 100 * ((rsi - rsi_min) / denom)
    stoch_rsi_k = raw_stoch_rsi.rolling(window=smooth_k).mean()
    stoch_rsi_d = stoch_rsi_k.rolling(window=smooth_d).mean()

    return stoch_rsi_k, stoch_rsi_d


def detect_smc_patterns(df):
    """Deteksi FVG (Fair Value Gap) 3-candle terbaru & Liquidity Sweep 20-bar"""
    fvg_type = ""
    sweep_type = ""
    if len(df) < 25:
        return fvg_type, sweep_type

    # 1. Deteksi FVG pada 3 candle terakhir (c0 = i-2, c1 = i-1, c2 = i)
    c0 = df.iloc[-3]
    c2 = df.iloc[-1]
    if float(c2["Low"]) > float(c0["High"]):
        fvg_type = "BULL FVG"
    elif float(c2["High"]) < float(c0["Low"]):
        fvg_type = "BEAR FVG"

    # 2. Deteksi Liquidity Sweep terhadap High/Low 20 bar sebelumnya
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
    """Mengecek apakah candle terakhir di TF tersebut sudah resmi closing"""
    dt = pd.to_datetime(last_daily_date)
    if tf_name == "1d":
        return True
    elif tf_name == "1w":
        return dt.weekday() >= 4
    elif tf_name == "1m":
        last_day_of_month = calendar.monthrange(dt.year, dt.month)[1]
        remaining_days = last_day_of_month - dt.day
        if remaining_days == 0:
            return True
        if remaining_days <= 2 and dt.weekday() == 4:
            return True
        return False
    return True


def analyze_crt(df, tf_name="1d", last_bar_closed=True, scan_bars=60, min_ticks_ratio=0.001, block_opposite=True):
    """Logika CRT V12 Dynamic dengan deteksi CONFIRMED vs POTENTIAL (Bullish & Bearish)"""
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
        is_latest_bar = (i == len(sub) - 1)
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


def process_timeframe(df_raw, clean_ticker, tf_name, last_daily_date, min_bars=12, beta_val=None):
    """Memproses data chart & ringkasan lengkap untuk screener multi-filter"""
    df = df_raw.dropna().copy()
    if len(df) < min_bars:
        return None, None

    df["MA20"] = df["Close"].rolling(window=20).mean()
    df["MA50"] = df["Close"].rolling(window=50).mean()
    df["VOL_MA20"] = df["Volume"].rolling(window=20).mean()
    df["RSI14"] = calculate_rsi(df["Close"], rsi_len=14)
    df["STOCH_K"], df["STOCH_D"] = calculate_stoch_rsi(
        df["Close"], rsi_len=10, stoch_len=10, smooth_k=5, smooth_d=5
    )

    candles, volumes = [], []
    for index, row in df.iterrows():
        date_str = index.strftime("%Y-%m-%d")
        open_p = round(float(row["Open"]), 2)
        high_p = round(float(row["High"]), 2)
        low_p = round(float(row["Low"]), 2)
        close_p = round(float(row["Close"]), 2)
        vol_p = int(row["Volume"])

        candles.append({"time": date_str, "open": open_p, "high": high_p, "low": low_p, "close": close_p})
        volumes.append({"time": date_str, "value": vol_p, "isUp": close_p >= open_p})

    closed_flag = is_last_candle_closed(last_daily_date, tf_name)
    crt_info = analyze_crt(df, tf_name=tf_name, last_bar_closed=closed_flag)
    fvg_type, sweep_type = detect_smc_patterns(df)

    chart_data = {
        "candles": candles,
        "volume": volumes,
        "crt": crt_info,
    }

    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    close_price = round(float(today["Close"]), 2)
    prev_close = round(float(yesterday["Close"]), 2)
    change_pct = round(((close_price - prev_close) / prev_close) * 100, 2) if prev_close != 0 else 0

    # Nilai transaksi (Rp Miliar) & Volume Spike Ratio (vs rata-rata 20 bar)
    val_series = df["Close"] * df["Volume"]
    tx_val_miliar = round(float(val_series.iloc[-1]) / 1_000_000_000, 2)
    avg_tx_miliar = round(float(val_series.tail(20).mean()) / 1_000_000_000, 2)

    vol_now = float(today["Volume"])
    vol_ma20 = float(today["VOL_MA20"]) if pd.notna(today["VOL_MA20"]) else 0
    vol_ratio = round(vol_now / vol_ma20, 2) if vol_ma20 > 0 else 1.0

    ma20_val = round(float(today["MA20"]), 2) if pd.notna(today["MA20"]) else 0
    ma50_val = round(float(today["MA50"]), 2) if pd.notna(today["MA50"]) else 0
    rsi14_val = round(float(today["RSI14"]), 2) if pd.notna(today["RSI14"]) else 50.0
    k_now = round(float(today["STOCH_K"]), 2) if pd.notna(today["STOCH_K"]) else 50.0
    d_now = round(float(today["STOCH_D"]), 2) if pd.notna(today["STOCH_D"]) else 50.0
    k_prev = round(float(yesterday["STOCH_K"]), 2) if pd.notna(yesterday["STOCH_K"]) else 50.0
    d_prev = round(float(yesterday["STOCH_D"]), 2) if pd.notna(yesterday["STOCH_D"]) else 50.0

    dist_ma20_pct = round(((close_price - ma20_val) / ma20_val) * 100, 2) if ma20_val > 0 else 999.0

    is_golden_cross = (k_prev <= d_prev) and (k_now > d_now) and (k_now > 0)
    is_oversold = (k_prev <= 20 or d_prev <= 20) and (k_now <= 25)

    is_crt_bull = bool(crt_info and crt_info["active_bias"] == "BULLISH OPEN")
    is_crt_bear = bool(crt_info and crt_info["active_bias"] == "BEARISH OPEN")

    crt_status = ""
    crt_sig = ""
    crt_dir = 0
    if (is_crt_bull or is_crt_bear) and crt_info["latest_setup"]:
        crt_status = crt_info["latest_setup"]["status"]
        crt_sig = crt_info["latest_setup"]["signal"]
        crt_dir = crt_info["latest_setup"]["dir"]

    summary = {
        "ticker": clean_ticker,
        "close": close_price,
        "change_pct": change_pct,
        "tx_miliar": tx_val_miliar,
        "avg_tx_miliar": avg_tx_miliar,
        "vol_ratio": vol_ratio,
        "beta": beta_val,
        "ma20": ma20_val,
        "ma50": ma50_val,
        "dist_ma20": dist_ma20_pct,
        "rsi14": rsi14_val,
        "stoch_k": k_now,
        "stoch_d": d_now,
        "above_ma20": (ma20_val > 0 and close_price > ma20_val),
        "above_ma50": (ma50_val > 0 and close_price > ma50_val),
        "stoch_os_cross": bool(is_golden_cross and is_oversold),
        "crt_bull": is_crt_bull,
        "crt_bear": is_crt_bear,
        "crt_dir": crt_dir,
        "crt_status": crt_status,
        "crt_sig": crt_sig,
        "fvg": fvg_type,
        "sweep": sweep_type,
    }

    return chart_data, summary


def run_screener():
    all_tickers = get_all_idx_tickers()
    ihsg_ret = get_ihsg_returns()

    results = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
        "breadth": {"up": 0, "down": 0, "flat": 0, "above_ma20_pct": 0, "above_ma50_pct": 0, "bear_crt_count": 0},
        "1d": {"all_data": {}},
        "1w": {"all_data": {}},
        "1m": {"all_data": {}},
    }

    batch_size = 100
    total_batches = (len(all_tickers) + batch_size - 1) // batch_size

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i : i + batch_size]
        current_batch_num = (i // batch_size) + 1
        print(f"\n[Batch {current_batch_num}/{total_batches}] Mengunduh {len(batch)} saham (5y untuk 1D, 1W, 1M)...")

        try:
            data = yf.download(batch, period="5y", interval="1d", group_by="ticker", threads=True, progress=False)
        except Exception as e:
            print(f"Gagal mengunduh batch {current_batch_num}: {e}")
            continue

        for ticker in batch:
            try:
                if ticker not in data.columns.levels[0]:
                    continue
                df_daily = data[ticker].dropna().copy()
                if len(df_daily) < 40:
                    continue

                clean_ticker = ticker.replace(".JK", "")
                last_daily_date = df_daily.index[-1]
                beta_val = calculate_beta(df_daily, ihsg_ret)

                # 1. Daily (1D - 320 bar terakhir untuk chart & MA200 dinamis)
                chart_1d, sum_1d = process_timeframe(df_daily.tail(320), clean_ticker, "1d", last_daily_date, min_bars=30, beta_val=beta_val)

                # 2. Weekly (1W - tutup Jumat)
                df_weekly = df_daily.resample("W-FRI").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()
                chart_1w, sum_1w = process_timeframe(df_weekly, clean_ticker, "1w", last_daily_date, min_bars=20, beta_val=beta_val)

                # 3. Monthly (1M - tutup akhir bulan)
                df_monthly = df_daily.resample("ME").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()
                chart_1m, sum_1m = process_timeframe(df_monthly, clean_ticker, "1m", last_daily_date, min_bars=12, beta_val=beta_val)

                if not chart_1d or not sum_1d:
                    continue

                with open(os.path.join(CHARTS_DIR, f"{clean_ticker}.json"), "w") as cf:
                    json.dump({"ticker": clean_ticker, "1d": chart_1d, "1w": chart_1w, "1m": chart_1m}, cf)

                if sum_1d:
                    results["1d"]["all_data"][clean_ticker] = sum_1d
                if sum_1w:
                    results["1w"]["all_data"][clean_ticker] = sum_1w
                if sum_1m:
                    results["1m"]["all_data"][clean_ticker] = sum_1m

            except Exception:
                continue

        time.sleep(2)

    for tf in ["1d", "1w", "1m"]:
        results[tf]["all_data"] = dict(sorted(results[tf]["all_data"].items()))

    # Hitung Market Breadth dari data 1D
    daily_items = list(results["1d"]["all_data"].values())
    total_d = len(daily_items)
    if total_d > 0:
        up_cnt = sum(1 for x in daily_items if x["change_pct"] > 0)
        down_cnt = sum(1 for x in daily_items if x["change_pct"] < 0)
        flat_cnt = total_d - up_cnt - down_cnt
        abv_20 = round((sum(1 for x in daily_items if x["above_ma20"]) / total_d) * 100, 1)
        abv_50 = round((sum(1 for x in daily_items if x["above_ma50"]) / total_d) * 100, 1)
        bear_crt_cnt = sum(1 for x in daily_items if x.get("crt_bear"))
        results["breadth"] = {
            "up": up_cnt,
            "down": down_cnt,
            "flat": flat_cnt,
            "above_ma20_pct": abv_20,
            "above_ma50_pct": abv_50,
            "bear_crt_count": bear_crt_cnt,
        }

    with open(os.path.join(OUTPUT_DIR, "screener_idx.json"), "w") as f:
        json.dump(results, f)

    print(f"\nSELESAI TOTAL! Berhasil memindai {len(results['1d']['all_data'])} emiten aktif IDX.")
    generate_macro_and_rrg(results["breadth"])


def generate_macro_and_rrg(breadth_data):
    """Menghasilkan data Makro, Komoditas, & Relative Rotation Graph (RRG) 11 Sektor IDX berbasis Proxy Saham Utama"""
    print("\nMengunduh data Makro, Komoditas & Proxy 11 Sektor IDX untuk RRG...")

    macro_tickers = {
        "IHSG": "^JKSE",
        "USDIDR": "USDIDR=X",
        "GOLD": "GC=F",
        "SILVER": "SI=F",
        "OIL": "CL=F",
        "BTC": "BTC-USD",
    }

    # Keranjang saham proxy likuid untuk masing-masing 11 Sektor IDX
    sector_baskets = {
        "IDXFINANCE": ["BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK"],
        "IDXENERGY": ["ADRO.JK", "PTBA.JK", "ITMG.JK", "PGAS.JK"],
        "IDXBASIC": ["BRPT.JK", "TPIA.JK", "MDKA.JK", "ANTM.JK"],
        "IDXINDUST": ["ASII.JK", "UNTR.JK", "HEXA.JK"],
        "IDXNONCYC": ["ICBP.JK", "INDF.JK", "UNVR.JK", "MYOR.JK"],
        "IDXCYCLIC": ["MAPI.JK", "ACES.JK", "ERAA.JK"],
        "IDXHEALTH": ["KLBF.JK", "MIKA.JK", "HEAL.JK"],
        "IDXPROPERT": ["BSDE.JK", "PWON.JK", "CTRA.JK", "SMRA.JK"],
        "IDXTECHNO": ["GOTO.JK", "EMTK.JK", "BUKA.JK"],
        "IDXINFRA": ["TLKM.JK", "ISAT.JK", "EXCL.JK", "JSMR.JK"],
        "IDXTRANS": ["BIRD.JK", "ASSA.JK", "SMDR.JK"],
    }

    all_proxy_tickers = sorted(list({t for basket in sector_baskets.values() for t in basket}))
    all_symbols = list(macro_tickers.values()) + all_proxy_tickers

    try:
        raw = yf.download(all_symbols, period="1y", interval="1d", group_by="ticker", threads=True, progress=False)
    except Exception as e:
        print(f"Gagal mengunduh data makro/sektor: {e}")
        return

    macro_out = {}
    for label, sym in macro_tickers.items():
        try:
            df_s = raw[sym].dropna()
            if len(df_s) < 2:
                continue
            close_now = round(float(df_s["Close"].iloc[-1]), 2)
            close_prev = round(float(df_s["Close"].iloc[-2]), 2)
            chg_pct = round(((close_now - close_prev) / close_prev) * 100, 2) if close_prev else 0
            spark = [round(float(x), 2) for x in df_s["Close"].tail(20).tolist()]
            macro_out[label] = {
                "symbol": sym,
                "close": close_now,
                "change_pct": chg_pct,
                "sparkline": spark,
            }
        except Exception:
            continue

    # Hitung RRG (RS-Ratio & RS-Momentum) mingguan 11 Sektor terhadap IHSG (^JKSE)
    rrg_out = []
    try:
        ihsg_daily = raw["^JKSE"]["Close"].dropna()
        ihsg_weekly = ihsg_daily.resample("W-FRI").last()

        for sec_name, tickers in sector_baskets.items():
            try:
                # Buat indeks sektor sintetis (equal-weighted index basis 1000) dari keranjang saham sektor
                sec_closes = []
                for t in tickers:
                    if t in raw.columns.levels[0]:
                        s = raw[t]["Close"].dropna()
                        if len(s) > 60:
                            sec_closes.append(s / float(s.iloc[0]) * 1000.0)

                if not sec_closes:
                    continue

                sec_daily_idx = pd.concat(sec_closes, axis=1).mean(axis=1).dropna()
                sec_weekly = sec_daily_idx.resample("W-FRI").last()

                df_rel = pd.concat([sec_weekly, ihsg_weekly], axis=1, join="inner").dropna()
                df_rel.columns = ["sec", "ihsg"]
                if len(df_rel) < 20:
                    continue

                # Relative Strength (RS) & Normalisasi JdK Style (berpusat di 100)
                rs = (df_rel["sec"] / df_rel["ihsg"]) * 100
                rs_mean = rs.rolling(window=14).mean()
                rs_std = rs.rolling(window=14).std().replace(0, np.nan)
                rs_ratio = 100 + ((rs - rs_mean) / rs_std)

                rs_mom_raw = rs_ratio.pct_change(periods=1) * 100
                mom_mean = rs_mom_raw.rolling(window=10).mean()
                mom_std = rs_mom_raw.rolling(window=10).std().replace(0, np.nan)
                rs_momentum = 100 + ((rs_mom_raw - mom_mean) / mom_std)

                valid = pd.DataFrame({
                    "rs_ratio": rs_ratio,
                    "rs_momentum": rs_momentum,
                }).dropna().tail(8)

                if valid.empty:
                    continue

                latest = valid.iloc[-1]
                r_val = round(float(latest["rs_ratio"]), 2)
                m_val = round(float(latest["rs_momentum"]), 2)

                if r_val >= 100 and m_val >= 100:
                    quadrant = "LEADING"
                elif r_val >= 100 and m_val < 100:
                    quadrant = "WEAKENING"
                elif r_val < 100 and m_val < 100:
                    quadrant = "LAGGING"
                else:
                    quadrant = "IMPROVING"

                d_chg = round(((float(sec_daily_idx.iloc[-1]) - float(sec_daily_idx.iloc[-2])) / float(sec_daily_idx.iloc[-2])) * 100, 2) if len(sec_daily_idx) >= 2 else 0

                tail_points = [
                    {
                        "date": idx.strftime("%Y-%m-%d"),
                        "x": round(float(row["rs_ratio"]), 2),
                        "y": round(float(row["rs_momentum"]), 2),
                    }
                    for idx, row in valid.iterrows()
                ]

                rrg_out.append({
                    "sector": sec_name,
                    "symbol": f"{len(sec_closes)} Proxy Stocks",
                    "close": round(float(sec_daily_idx.iloc[-1]), 2),
                    "change_pct": d_chg,
                    "rs_ratio": r_val,
                    "rs_momentum": m_val,
                    "quadrant": quadrant,
                    "tail": tail_points,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"Error kalkulasi RRG: {e}")

    payload = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
        "breadth": breadth_data,
        "macro": macro_out,
        "rrg": rrg_out,
    }

    with open(os.path.join(OUTPUT_DIR, "market_macro.json"), "w") as f:
        json.dump(payload, f)
    print(f"Sukses menyimpan data/market_macro.json ({len(rrg_out)} sektor RRG).")


if __name__ == "__main__":
    run_screener()
