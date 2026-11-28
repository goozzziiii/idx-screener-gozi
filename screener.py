import json
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

from indicators import compute_all_indicators

OUTPUT_DIR = "data"
CHARTS_DIR = os.path.join(OUTPUT_DIR, "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)


def get_all_idx_tickers():
    """Mencari otomatis file Excel/CSV IDX di folder dan mengambil semua kode 4 huruf."""
    files = [f for f in os.listdir(".") if f.endswith((".xlsx", ".xls", ".csv"))]
    if not files:
        print("PERINGATAN: Tidak ada file .xlsx atau .csv ditemukan! Pakai daftar fallback.")
        return ["BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "TLKM.JK"]

    target_file = files[0]
    print(f"Membaca daftar emiten dari file: {target_file}...")

    try:
        df_list = (
            pd.read_excel(target_file)
            if target_file.endswith((".xlsx", ".xls"))
            else pd.read_csv(target_file)
        )
        tickers = []
        for col in df_list.columns:
            for val in df_list[col].dropna():
                clean = str(val).strip().upper()
                if (
                    len(clean) == 4
                    and clean.isalpha()
                    and clean not in ["KODE", "CODE", "NAMA", "NAME"]
                ):
                    tickers.append(f"{clean}.JK")
            if len(set(tickers)) > 500:
                break

        unique_tickers = sorted(list(set(tickers)))
        print(f"Sukses! Ditemukan {len(unique_tickers)} emiten aktif BEI.")
        return unique_tickers
    except Exception as e:
        print(f"Detail error saat membaca {target_file}: {e}")
        return ["BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "TLKM.JK"]


def _extract_close_series(df_or_panel, ticker=None):
    """Mengambil seri harga Close yang bersih (1D Series, index tz-naive, tanpa NaN)."""
    if df_or_panel is None or df_or_panel.empty:
        return pd.Series(dtype="float64")

    if isinstance(df_or_panel.columns, pd.MultiIndex):
        if ticker is not None:
            lvl0 = df_or_panel.columns.get_level_values(0)
            lvl1 = df_or_panel.columns.get_level_values(1)
            if ticker in lvl0:
                sub = df_or_panel[ticker]
            elif ticker in lvl1:
                sub = df_or_panel.xs(ticker, axis=1, level=1)
            else:
                return pd.Series(dtype="float64")
        else:
            sub = df_or_panel

        if isinstance(sub.columns, pd.MultiIndex):
            if "Close" in sub.columns.get_level_values(0):
                close_col = sub["Close"]
            elif "Close" in sub.columns.get_level_values(1):
                close_col = sub.xs("Close", axis=1, level=1)
            else:
                return pd.Series(dtype="float64")
        else:
            if "Close" not in sub.columns:
                return pd.Series(dtype="float64")
            close_col = sub["Close"]
    else:
        if "Close" not in df_or_panel.columns:
            return pd.Series(dtype="float64")
        close_col = df_or_panel["Close"]

    if isinstance(close_col, pd.DataFrame):
        close_col = close_col.iloc[:, 0]

    s = pd.to_numeric(close_col, errors="coerce").dropna()
    if len(s) > 0:
        s.index = pd.to_datetime(s.index).tz_localize(None)
        s = s.sort_index()
        s = s[~s.index.duplicated(keep="last")]
    return s


def _extract_ohlcv_df(data_panel, ticker):
    """Mengambil DataFrame OHLCV bersih untuk satu ticker dari hasil yf.download."""
    if data_panel is None or data_panel.empty:
        return pd.DataFrame()

    if isinstance(data_panel.columns, pd.MultiIndex):
        lvl0 = data_panel.columns.get_level_values(0)
        lvl1 = data_panel.columns.get_level_values(1)
        if ticker in lvl0:
            sub = data_panel[ticker].copy()
        elif ticker in lvl1:
            sub = data_panel.xs(ticker, axis=1, level=1).copy()
        else:
            return pd.DataFrame()
    else:
        sub = data_panel.copy()

    required = ["Open", "High", "Low", "Close", "Volume"]
    if not all(col in sub.columns for col in required):
        return pd.DataFrame()

    df = sub[required].copy()
    for col in required:
        col_data = df[col]
        if isinstance(col_data, pd.DataFrame):
            col_data = col_data.iloc[:, 0]
        df[col] = pd.to_numeric(col_data, errors="coerce")

    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0)
    if len(df) > 0:
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
    return df


def get_ihsg_returns():
    """Mengunduh data IHSG (^JKSE) 1 tahun untuk kalkulasi Beta masing-masing emiten."""
    try:
        ihsg = yf.download("^JKSE", period="1y", interval="1d", progress=False, auto_adjust=False)
        close_s = _extract_close_series(ihsg, "^JKSE")
        if len(close_s) >= 2:
            ret = close_s.pct_change().dropna()
            print(f"Data IHSG (^JKSE) berhasil dimuat ({len(ret)} return harian).")
            return ret
    except Exception as e:
        print(f"Gagal memuat data IHSG untuk Beta: {e}")
    return None


def calculate_beta(df_daily, ihsg_ret):
    """Menghitung Beta 1 tahun saham terhadap IHSG (^JKSE)."""
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


def process_timeframe(df_raw, clean_ticker, tf_name, last_daily_date, min_bars=12, beta_val=None):
    """Memproses data OHLCV, metrik likuiditas, serta indikator dari indicators.py."""
    df = df_raw.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if len(df) < min_bars or len(df) < 2:
        return None, None

    df["VOL_MA20"] = df["Volume"].rolling(window=20).mean()

    candles, volumes = [], []
    for index, row in df.iterrows():
        date_str = index.strftime("%Y-%m-%d")
        open_p = round(float(row["Open"]), 2)
        high_p = round(float(row["High"]), 2)
        low_p = round(float(row["Low"]), 2)
        close_p = round(float(row["Close"]), 2)
        vol_p = int(row["Volume"]) if pd.notna(row["Volume"]) else 0

        candles.append({
            "time": date_str,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
        })
        volumes.append({
            "time": date_str,
            "value": vol_p,
            "isUp": close_p >= open_p,
        })

    ind_summary, ind_overlays = compute_all_indicators(
        df, tf_name=tf_name, last_daily_date=last_daily_date
    )

    chart_data = {
        "tf": tf_name,
        "candles": candles,
        "volume": volumes,
        **ind_overlays,
    }

    today = df.iloc[-1]
    yesterday = df.iloc[-2]
    last_date = df.index[-1].strftime("%Y-%m-%d")

    close_price = round(float(today["Close"]), 2)
    prev_close = round(float(yesterday["Close"]), 2)
    change_pct = (
        round(((close_price - prev_close) / prev_close) * 100, 2)
        if prev_close != 0
        else 0.0
    )

    val_series = df["Close"] * df["Volume"]
    tx_val_miliar = round(float(val_series.iloc[-1]) / 1_000_000_000, 2)
    avg_tx_miliar = round(float(val_series.tail(20).mean()) / 1_000_000_000, 2)

    vol_now = float(today["Volume"]) if pd.notna(today["Volume"]) else 0.0
    vol_ma20 = float(today["VOL_MA20"]) if pd.notna(today["VOL_MA20"]) else 0.0
    vol_ratio = round(vol_now / vol_ma20, 2) if vol_ma20 > 0 else 1.0

    summary = {
        "ticker": clean_ticker,
        "last_date": last_date,
        "close": close_price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "tx_miliar": tx_val_miliar,
        "avg_tx_miliar": avg_tx_miliar,
        "vol_ratio": vol_ratio,
        "beta": beta_val,
        **ind_summary,
    }

    return chart_data, summary


def run_screener():
    all_tickers = get_all_idx_tickers()
    ihsg_ret = get_ihsg_returns()

    results = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
        "breadth": {
            "up": 0,
            "down": 0,
            "flat": 0,
            "above_ma20_pct": 0,
            "above_ma50_pct": 0,
            "bear_crt_count": 0,
        },
        "1d": {"all_data": {}},
        "1w": {"all_data": {}},
        "1m": {"all_data": {}},
    }

    batch_size = 100
    total_batches = (len(all_tickers) + batch_size - 1) // batch_size

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i : i + batch_size]
        current_batch_num = (i // batch_size) + 1
        print(
            f"\n[Batch {current_batch_num}/{total_batches}] Mengunduh {len(batch)} saham "
            f"(5y untuk 1D, 1W, 1M)..."
        )

        try:
            data = yf.download(
                batch,
                period="5y",
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=False,
            )
        except Exception as e:
            print(f"Gagal mengunduh batch {current_batch_num}: {e}")
            continue

        for ticker in batch:
            try:
                df_daily = _extract_ohlcv_df(data, ticker)
                if len(df_daily) < 40:
                    continue

                clean_ticker = ticker.replace(".JK", "")
                last_daily_date = df_daily.index[-1]
                beta_val = calculate_beta(df_daily, ihsg_ret)

                # 1. Daily (1D - 320 bar terakhir)
                chart_1d, sum_1d = process_timeframe(
                    df_daily.tail(320),
                    clean_ticker,
                    "1d",
                    last_daily_date,
                    min_bars=30,
                    beta_val=beta_val,
                )

                # 2. Weekly (1W - tutup Jumat)
                df_weekly = (
                    df_daily.resample("W-FRI")
                    .agg({
                        "Open": "first",
                        "High": "max",
                        "Low": "min",
                        "Close": "last",
                        "Volume": "sum",
                    })
                    .dropna(subset=["Open", "High", "Low", "Close"])
                )
                chart_1w, sum_1w = process_timeframe(
                    df_weekly,
                    clean_ticker,
                    "1w",
                    last_daily_date,
                    min_bars=20,
                    beta_val=beta_val,
                )

                # 3. Monthly (1M - tutup akhir bulan)
                df_monthly = (
                    df_daily.resample("ME")
                    .agg({
                        "Open": "first",
                        "High": "max",
                        "Low": "min",
                        "Close": "last",
                        "Volume": "sum",
                    })
                    .dropna(subset=["Open", "High", "Low", "Close"])
                )
                chart_1m, sum_1m = process_timeframe(
                    df_monthly,
                    clean_ticker,
                    "1m",
                    last_daily_date,
                    min_bars=12,
                    beta_val=beta_val,
                )

                if not chart_1d or not sum_1d:
                    continue

                with open(os.path.join(CHARTS_DIR, f"{clean_ticker}.json"), "w") as cf:
                    json.dump(
                        {"ticker": clean_ticker, "1d": chart_1d, "1w": chart_1w, "1m": chart_1m},
                        cf,
                    )

                if sum_1d:
                    results["1d"]["all_data"][clean_ticker] = sum_1d
                if sum_1w:
                    results["1w"]["all_data"][clean_ticker] = sum_1w
                if sum_1m:
                    results["1m"]["all_data"][clean_ticker] = sum_1m

            except Exception as e:
                print(f"[TICKER ERR] {ticker}: {e}")
                continue

        time.sleep(2)

    for tf in ["1d", "1w", "1m"]:
        results[tf]["all_data"] = dict(sorted(results[tf]["all_data"].items()))

    # Hitung Market Breadth lengkap dari data 1D
    daily_items = list(results["1d"]["all_data"].values())
    total_d = len(daily_items)
    if total_d > 0:
        up_cnt = sum(1 for x in daily_items if x["change_pct"] > 0)
        down_cnt = sum(1 for x in daily_items if x["change_pct"] < 0)
        flat_cnt = total_d - up_cnt - down_cnt
        abv_20 = round((sum(1 for x in daily_items if x.get("above_ma20")) / total_d) * 100, 1)
        abv_50 = round((sum(1 for x in daily_items if x.get("above_ma50")) / total_d) * 100, 1)
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
    """Menghasilkan data Makro (termasuk DXY, BTC, GOLD, OIL), & RRG 11 Sektor IDX."""
    print("\nMengunduh data Makro (IHSG, DXY, USDIDR, GOLD, OIL, BTC) & Proxy 11 Sektor IDX...")

    macro_tickers = {
        "IHSG": "^JKSE",
        "DXY": "DX-Y.NYB",
        "USDIDR": "USDIDR=X",
        "GOLD": "GC=F",
        "OIL": "CL=F",
        "BTC": "BTC-USD",
    }

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
    all_symbols = list(dict.fromkeys(list(macro_tickers.values()) + all_proxy_tickers))

    try:
        raw = yf.download(
            all_symbols,
            period="1y",
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
        )
    except Exception as e:
        print(f"Gagal mengunduh data makro/sektor: {e}")
        return

    macro_out = {}
    for label, sym in macro_tickers.items():
        try:
            close_series = _extract_close_series(raw, sym)
            if len(close_series) < 2:
                print(f"[MACRO WARN] {label} ({sym}) data kurang dari 2 bar.")
                continue

            close_now = round(float(close_series.iloc[-1]), 2)
            close_prev = round(float(close_series.iloc[-2]), 2)
            chg_pct = (
                round(((close_now - close_prev) / close_prev) * 100, 2)
                if close_prev != 0
                else 0.0
            )
            last_dt = close_series.index[-1].strftime("%Y-%m-%d")

            hist_tail = close_series.tail(60)
            history = [
                {"date": idx.strftime("%Y-%m-%d"), "close": round(float(val), 2)}
                for idx, val in hist_tail.items()
            ]
            spark = [item["close"] for item in history[-20:]]

            print(
                f"[MACRO OK] {label} ({sym}) | tgl={last_dt} | "
                f"prev={close_prev} -> now={close_now} ({chg_pct:+}%)"
            )

            macro_out[label] = {
                "symbol": sym,
                "last_date": last_dt,
                "close": close_now,
                "prev_close": close_prev,
                "change_pct": chg_pct,
                "sparkline": spark,
                "history": history,
            }
        except Exception as e:
            print(f"[MACRO ERR] {label} ({sym}): {e}")
            continue

    # Hitung RRG (RS-Ratio & RS-Momentum) mingguan 11 Sektor terhadap IHSG (^JKSE)
    rrg_out = []
    try:
        ihsg_daily = _extract_close_series(raw, "^JKSE")
        ihsg_weekly = ihsg_daily.resample("W-FRI").last().dropna()

        for sec_name, tickers in sector_baskets.items():
            try:
                sec_closes = []
                for t in tickers:
                    s = _extract_close_series(raw, t)
                    if len(s) > 60 and float(s.iloc[0]) != 0:
                        sec_closes.append(s / float(s.iloc[0]) * 1000.0)

                if not sec_closes:
                    continue

                sec_daily_idx = pd.concat(sec_closes, axis=1).mean(axis=1).dropna()
                if len(sec_daily_idx) < 2:
                    continue

                sec_weekly = sec_daily_idx.resample("W-FRI").last().dropna()

                df_rel = pd.concat([sec_weekly, ihsg_weekly], axis=1, join="inner").dropna()
                df_rel.columns = ["sec", "ihsg"]
                if len(df_rel) < 20:
                    continue

                rs = (df_rel["sec"] / df_rel["ihsg"]) * 100
                rs_mean = rs.rolling(window=14).mean()
                rs_std = rs.rolling(window=14).std().replace(0, np.nan)
                rs_ratio = 100 + ((rs - rs_mean) / rs_std)

                rs_mom_raw = rs_ratio.pct_change(periods=1) * 100
                mom_mean = rs_mom_raw.rolling(window=10).mean()
                mom_std = rs_mom_raw.rolling(window=10).std().replace(0, np.nan)
                rs_momentum = 100 + ((rs_mom_raw - mom_mean) / mom_std)

                valid = (
                    pd.DataFrame({"rs_ratio": rs_ratio, "rs_momentum": rs_momentum})
                    .dropna()
                    .tail(20)
                )

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

                d_chg = (
                    round(
                        ((float(sec_daily_idx.iloc[-1]) - float(sec_daily_idx.iloc[-2]))
                         / float(sec_daily_idx.iloc[-2]))
                        * 100,
                        2,
                    )
                    if float(sec_daily_idx.iloc[-2]) != 0
                    else 0.0
                )

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
            except Exception as e:
                print(f"[RRG ERR] {sec_name}: {e}")
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
