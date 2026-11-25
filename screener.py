import yfinance as yf
import pandas as pd
import json
import os
import time
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


def calculate_stoch_rsi(close_series, rsi_len=10, stoch_len=10, smooth_k=5, smooth_d=5):
    """Menghitung Stochastic RSI (10, 10, 5, 5) sesuai standar TradingView"""
    delta = close_series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / rsi_len, min_periods=rsi_len, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_len, min_periods=rsi_len, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    rsi_min = rsi.rolling(window=stoch_len).min()
    rsi_max = rsi.rolling(window=stoch_len).max()
    denom = (rsi_max - rsi_min).replace(0, float("nan"))

    raw_stoch_rsi = 100 * ((rsi - rsi_min) / denom)
    stoch_rsi_k = raw_stoch_rsi.rolling(window=smooth_k).mean()
    stoch_rsi_d = stoch_rsi_k.rolling(window=smooth_d).mean()

    return stoch_rsi_k, stoch_rsi_d


def analyze_crt(df, scan_bars=60, min_ticks_ratio=0.001, block_opposite=True):
    """Logika CRT V12 Dynamic (Wick-Only Sweep + Block Opposite + Dynamic Break)"""
    if len(df) < 10:
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
                sig_name = sig_map[sig]

                active_setup = {
                    "signal": sig_name,
                    "dir": new_dir,
                    "crth": round(h1, 2),
                    "crtl": round(l1, 2),
                    "mid50": round(c1_mid, 2),
                    "date_c2": t2,
                    "is_latest": (i == len(sub) - 1),
                    "is_broken": False,
                }

                if new_dir == 1:
                    markers.append({
                        "time": t2,
                        "position": "belowBar",
                        "color": "#00e676",
                        "shape": "arrowUp",
                        "text": sig_name,
                    })
                elif new_dir == -1:
                    markers.append({
                        "time": t2,
                        "position": "aboveBar",
                        "color": "#ff5252",
                        "shape": "arrowDown",
                        "text": sig_name,
                    })

    return {
        "active_bias": "BULLISH OPEN" if open_dir == 1 else ("BEARISH OPEN" if open_dir == -1 else "NEUTRAL"),
        "latest_setup": active_setup,
        "markers": markers[-10:],
    }


def run_screener():
    all_tickers = get_all_idx_tickers()

    results = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
        "above_ma20": [],
        "above_ma50": [],
        "stoch_golden_cross": [],
        "crt_bull_active": [],
        "all_data": {},
    }

    batch_size = 100
    total_batches = (len(all_tickers) + batch_size - 1) // batch_size

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i : i + batch_size]
        current_batch_num = (i // batch_size) + 1
        print(f"\n[Batch {current_batch_num}/{total_batches}] Mengunduh {len(batch)} saham...")

        try:
            data = yf.download(batch, period="1y", interval="1d", group_by="ticker", threads=True, progress=False)
        except Exception as e:
            print(f"Gagal mengunduh batch {current_batch_num}: {e}")
            continue

        for ticker in batch:
            try:
                if ticker not in data.columns.levels[0]:
                    continue
                df = data[ticker].dropna().copy()
                if len(df) < 50:
                    continue

                df["MA20"] = df["Close"].rolling(window=20).mean()
                df["MA50"] = df["Close"].rolling(window=50).mean()
                df["STOCH_K"], df["STOCH_D"] = calculate_stoch_rsi(
                    df["Close"], rsi_len=10, stoch_len=10, smooth_k=5, smooth_d=5
                )

                clean_ticker = ticker.replace(".JK", "")

                candles = []
                ma20_series = []
                ma50_series = []
                volumes = []

                for index, row in df.iterrows():
                    date_str = index.strftime("%Y-%m-%d")
                    open_p = round(float(row["Open"]), 2)
                    high_p = round(float(row["High"]), 2)
                    low_p = round(float(row["Low"]), 2)
                    close_p = round(float(row["Close"]), 2)
                    vol_p = int(row["Volume"])

                    candles.append({
                        "time": date_str,
                        "open": open_p,
                        "high": high_p,
                        "low": low_p,
                        "close": close_p,
                    })

                    vol_color = "rgba(38, 166, 154, 0.5)" if close_p >= open_p else "rgba(239, 83, 80, 0.5)"
                    volumes.append({
                        "time": date_str,
                        "value": vol_p,
                        "color": vol_color,
                    })

                    if pd.notna(row["MA20"]):
                        ma20_series.append({"time": date_str, "value": round(float(row["MA20"]), 2)})
                    if pd.notna(row["MA50"]):
                        ma50_series.append({"time": date_str, "value": round(float(row["MA50"]), 2)})

                crt_info = analyze_crt(df)

                chart_payload = {
                    "ticker": clean_ticker,
                    "candles": candles,
                    "volume": volumes,
                    "ma20": ma20_series,
                    "ma50": ma50_series,
                    "crt": crt_info,
                }
                with open(os.path.join(CHARTS_DIR, f"{clean_ticker}.json"), "w") as cf:
                    json.dump(chart_payload, cf)

                today = df.iloc[-1]
                yesterday = df.iloc[-2]

                if (
                    pd.isna(today["MA50"])
                    or pd.isna(today["STOCH_K"])
                    or pd.isna(today["STOCH_D"])
                    or pd.isna(yesterday["STOCH_K"])
                    or pd.isna(yesterday["STOCH_D"])
                ):
                    continue

                close_price = round(float(today["Close"]), 2)
                prev_close = round(float(yesterday["Close"]), 2)
                change_pct = round(((close_price - prev_close) / prev_close) * 100, 2) if prev_close != 0 else 0

                ma20_val = round(float(today["MA20"]), 2)
                ma50_val = round(float(today["MA50"]), 2)
                k_now = round(float(today["STOCH_K"]), 2)
                d_now = round(float(today["STOCH_D"]), 2)
                k_prev = round(float(yesterday["STOCH_K"]), 2)
                d_prev = round(float(yesterday["STOCH_D"]), 2)

                stock_summary = {
                    "ticker": clean_ticker,
                    "close": close_price,
                    "change_pct": change_pct,
                    "ma20": ma20_val,
                    "ma50": ma50_val,
                    "stoch_k": k_now,
                    "stoch_d": d_now,
                }
                results["all_data"][clean_ticker] = stock_summary

                if close_price > ma20_val:
                    results["above_ma20"].append(stock_summary)
                if close_price > ma50_val:
                    results["above_ma50"].append(stock_summary)

                # StochRSI (10,10,5,5) Wajib Golden Cross DI AREA OVERSOLD (<= 20)
                is_golden_cross = (k_prev <= d_prev) and (k_now > d_now)
                is_oversold = (k_prev <= 20 or d_prev <= 20) and (k_now <= 25)
                if is_golden_cross and is_oversold:
                    results["stoch_golden_cross"].append(stock_summary)

                # CRT Bullish Aktif (Belum tertembus harga)
                if crt_info and crt_info["active_bias"] == "BULLISH OPEN":
                    stock_summary["crt_sig"] = crt_info["latest_setup"]["signal"]
                    results["crt_bull_active"].append(stock_summary)

            except Exception:
                continue

        time.sleep(2)

    results["all_data"] = dict(sorted(results["all_data"].items()))
    results["above_ma20"].sort(key=lambda x: x["ticker"])
    results["above_ma50"].sort(key=lambda x: x["ticker"])
    results["stoch_golden_cross"].sort(key=lambda x: x["ticker"])
    results["crt_bull_active"].sort(key=lambda x: x["ticker"])

    with open(os.path.join(OUTPUT_DIR, "screener_idx.json"), "w") as f:
        json.dump(results, f)

    print(f"\nSELESAI TOTAL! Berhasil memindai {len(results['all_data'])} emiten aktif IDX.")
    print(f"- Above MA20: {len(results['above_ma20'])} saham")
    print(f"- Above MA50: {len(results['above_ma50'])} saham")
    print(f"- StochRSI Oversold Cross: {len(results['stoch_golden_cross'])} saham")
    print(f"- CRT Bullish Active: {len(results['crt_bull_active'])} saham")


if __name__ == "__main__":
    run_screener()
