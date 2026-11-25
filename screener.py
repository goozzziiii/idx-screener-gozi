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
        print("PERINGATAN: Tidak ada file .xlsx atau .csv ditemukan di folder E:\\idx-screener!")
        return ["BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "TLKM.JK"]

    target_file = files[0]
    print(f"Membaca daftar emiten dari file: {target_file}...")

    try:
        df_list = pd.read_excel(target_file) if target_file.endswith((".xlsx", ".xls")) else pd.read_csv(target_file)
        
        tickers = []
        # Pindai seluruh kolom untuk menemukan sel berisi 4 huruf kapital (kode saham)
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

def run_screener():
    all_tickers = get_all_idx_tickers()
    
    results = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
        "above_ma20": [],
        "above_ma50": [],
        "stoch_golden_cross": [],
        "all_data": {}
    }

    batch_size = 100
    total_batches = (len(all_tickers) + batch_size - 1) // batch_size

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i + batch_size]
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

                # Hitung Moving Average (MA20 & MA50)
                df["MA20"] = df["Close"].rolling(window=20).mean()
                df["MA50"] = df["Close"].rolling(window=50).mean()

                # Hitung Stochastic Oscillator (14, 3, 3)
                low_14 = df["Low"].rolling(window=14).min()
                high_14 = df["High"].rolling(window=14).max()
                raw_k = 100 * ((df["Close"] - low_14) / (high_14 - low_14))
                df["STOCH_K"] = raw_k.rolling(window=3).mean()
                df["STOCH_D"] = df["STOCH_K"].rolling(window=3).mean()

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
                        "close": close_p
                    })

                    vol_color = "rgba(38, 166, 154, 0.5)" if close_p >= open_p else "rgba(239, 83, 80, 0.5)"
                    volumes.append({
                        "time": date_str,
                        "value": vol_p,
                        "color": vol_color
                    })

                    if pd.notna(row["MA20"]):
                        ma20_series.append({"time": date_str, "value": round(float(row["MA20"]), 2)})
                    if pd.notna(row["MA50"]):
                        ma50_series.append({"time": date_str, "value": round(float(row["MA50"]), 2)})

                # Simpan file JSON chart individual
                chart_payload = {
                    "ticker": clean_ticker,
                    "candles": candles,
                    "volume": volumes,
                    "ma20": ma20_series,
                    "ma50": ma50_series
                }
                with open(os.path.join(CHARTS_DIR, f"{clean_ticker}.json"), "w") as cf:
                    json.dump(chart_payload, cf)

                # Evaluasi kondisi candle terakhir
                today = df.iloc[-1]
                yesterday = df.iloc[-2]

                if pd.isna(today["MA50"]) or pd.isna(today["STOCH_K"]) or pd.isna(yesterday["STOCH_K"]):
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
                    "stoch_d": d_now
                }
                results["all_data"][clean_ticker] = stock_summary

                if close_price > ma20_val:
                    results["above_ma20"].append(stock_summary)
                if close_price > ma50_val:
                    results["above_ma50"].append(stock_summary)
                if (k_prev <= d_prev) and (k_now > d_now):
                    results["stoch_golden_cross"].append(stock_summary)

            except Exception:
                continue

        time.sleep(2)

    # Urutkan kode saham sesuai abjad A-Z
    results["all_data"] = dict(sorted(results["all_data"].items()))
    results["above_ma20"].sort(key=lambda x: x["ticker"])
    results["above_ma50"].sort(key=lambda x: x["ticker"])
    results["stoch_golden_cross"].sort(key=lambda x: x["ticker"])

    with open(os.path.join(OUTPUT_DIR, "screener_idx.json"), "w") as f:
        json.dump(results, f)

    print(f"\nSELESAI TOTAL! Berhasil memindai {len(results['all_data'])} emiten aktif IDX.")
    print(f"- Above MA20: {len(results['above_ma20'])} saham")
    print(f"- Above MA50: {len(results['above_ma50'])} saham")
    print(f"- Stoch Cross: {len(results['stoch_golden_cross'])} saham")

if __name__ == "__main__":
    run_screener()