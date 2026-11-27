import json
import os
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)
WIB = timezone(timedelta(hours=7))


def fetch_dukascopy(instrument_code, interval_str="15m", days_back=4):
    """Menarik harga Spot CFD murni dari Dukascopy tanpa akun/API key"""
    try:
        import dukascopy_python
        from dukascopy_python.instruments import (
            INSTRUMENT_FX_METALS_XAU_USD,
            INSTRUMENT_FX_METALS_XAU_EUR,
            INSTRUMENT_FX_METALS_XAG_USD,
        )

        inst_map = {
            "XAUUSD": INSTRUMENT_FX_METALS_XAU_USD,
            "XAUEUR": INSTRUMENT_FX_METALS_XAU_EUR,
            "XAGUSD": INSTRUMENT_FX_METALS_XAG_USD,
        }
        tf_map = {
            "15m": dukascopy_python.INTERVAL_MIN_15,
            "1h": dukascopy_python.INTERVAL_HOUR_1,
        }

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days_back)

        df = dukascopy_python.fetch(
            instrument=inst_map[instrument_code],
            interval=tf_map[interval_str],
            offer_side=dukascopy_python.OFFER_SIDE_BID,
            start=start_dt,
            end=end_dt,
        )
        if df is not None and not df.empty and len(df) >= 20:
            df.columns = [c.capitalize() for c in df.columns]
            df = df[["Open", "High", "Low", "Close"]].dropna()
            if df.index.tz is None:
                df.index = pd.to_datetime(df.index).tz_localize("UTC")
            else:
                df.index = pd.to_datetime(df.index).tz_convert("UTC")
            return df, "DUKASCOPY_SPOT"
    except Exception as e:
        print(f"Dukascopy fallback ({instrument_code} {interval_str}): {e}")
    return None, None


def fetch_yfinance_fallback(tickers, period="5d", interval="15m"):
    """Cadangan otomatis jika Dukascopy timeout"""
    import yfinance as yf
    for sym in tickers:
        try:
            df = yf.download(sym, period=period, interval=interval, progress=False)
            if df is not None and not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df[["Open", "High", "Low", "Close"]].dropna()
                df.index = pd.to_datetime(df.index).tz_convert("UTC")
                return df, f"YF_{sym}"
        except Exception:
            continue
    return None, None


def format_candles(df, limit=120):
    sub = df.tail(limit)
    out = []
    for ts, row in sub.iterrows():
        out.append({
            "time": int(ts.timestamp()),
            "open": round(float(row["Open"]), 3),
            "high": round(float(row["High"]), 3),
            "low": round(float(row["Low"]), 3),
            "close": round(float(row["Close"]), 3),
        })
    return out


def analyze_pair_metrics(df, lookback=20):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close_now = round(float(last["Close"]), 3)
    close_prev = round(float(prev["Close"]), 3)
    chg_pct = round(((close_now - close_prev) / close_prev) * 100, 3) if close_prev else 0.0

    today_utc = df.index[-1].date()
    df_today = df[df.index.date == today_utc]
    day_open = float(df_today["Open"].iloc[0]) if not df_today.empty else close_prev
    day_high = round(float(df_today["High"].max()), 3) if not df_today.empty else round(float(last["High"]), 3)
    day_low = round(float(df_today["Low"].min()), 3) if not df_today.empty else round(float(last["Low"]), 3)
    day_chg_pct = round(((close_now - day_open) / day_open) * 100, 2) if day_open else 0.0

    recent = df.iloc[-(lookback + 1):-1]
    swing_high = round(float(recent["High"].max()), 3)
    swing_low = round(float(recent["Low"].min()), 3)

    sweep = "NONE"
    if float(last["High"]) > swing_high and close_now < swing_high:
        sweep = "BSL SWEEP"
    elif float(last["Low"]) < swing_low and close_now > swing_low:
        sweep = "SSL SWEEP"

    return {
        "price": close_now,
        "bar_chg_pct": chg_pct,
        "day_chg_pct": day_chg_pct,
        "day_high": day_high,
        "day_low": day_low,
        "swing_high_20": swing_high,
        "swing_low_20": swing_low,
        "sweep": sweep,
    }


def detect_divergence(df_xau, df_other, other_name="XAGUSD", lookback=16):
    aligned = pd.concat(
        [df_xau["High"], df_xau["Low"], df_other["High"], df_other["Low"]],
        axis=1,
        join="inner",
    ).dropna()
    aligned.columns = ["xau_h", "xau_l", "oth_h", "oth_l"]
    if len(aligned) < lookback + 4:
        return "INSUFFICIENT DATA"

    half = lookback // 2
    prev_win = aligned.iloc[-(lookback + 1):-(half + 1)]
    curr_win = aligned.iloc[-(half + 1):-1]

    xau_hh = curr_win["xau_h"].max() > prev_win["xau_h"].max()
    oth_hh = curr_win["oth_h"].max() > prev_win["oth_h"].max()

    xau_ll = curr_win["xau_l"].min() < prev_win["xau_l"].min()
    oth_ll = curr_win["oth_l"].min() < prev_win["oth_l"].min()

    if xau_hh and not oth_hh:
        return f"BEARISH DIV (XAU HH, {other_name} LH)"
    if not xau_hh and oth_hh:
        return f"BEARISH DIV ({other_name} HH, XAU LH)"
    if xau_ll and not oth_ll:
        return f"BULLISH DIV (XAU LL, {other_name} HL)"
    if not xau_ll and oth_ll:
        return f"BULLISH DIV ({other_name} LL, XAU HL)"
    return "ALIGNED (NO DIVERGENCE)"


def run_metals_feed():
    print("Mengunduh Spot CFD XAUUSD, XAUEUR & XAGUSD (15m & 1h)...")

    xau_15m, src_xau = fetch_dukascopy("XAUUSD", "15m", days_back=4)
    if xau_15m is None:
        xau_15m, src_xau = fetch_yfinance_fallback(["XAUUSD=X", "GC=F"], "5d", "15m")

    xag_15m, src_xag = fetch_dukascopy("XAGUSD", "15m", days_back=4)
    if xag_15m is None:
        xag_15m, src_xag = fetch_yfinance_fallback(["XAGUSD=X", "SI=F"], "5d", "15m")

    eur_15m, src_eur = fetch_dukascopy("XAUEUR", "15m", days_back=4)
    if eur_15m is None:
        fx_15m, _ = fetch_yfinance_fallback(["EURUSD=X"], "5d", "15m")
        if xau_15m is not None and fx_15m is not None:
            common = xau_15m.index.intersection(fx_15m.index)
            eur_15m = pd.DataFrame({
                "Open": xau_15m.loc[common, "Open"] / fx_15m.loc[common, "Open"],
                "High": xau_15m.loc[common, "High"] / fx_15m.loc[common, "Low"],
                "Low": xau_15m.loc[common, "Low"] / fx_15m.loc[common, "High"],
                "Close": xau_15m.loc[common, "Close"] / fx_15m.loc[common, "Close"],
            }).dropna()
            src_eur = "YF_SYNTHETIC"

    xau_1h, _ = fetch_dukascopy("XAUUSD", "1h", days_back=15)
    if xau_1h is None:
        xau_1h, _ = fetch_yfinance_fallback(["XAUUSD=X", "GC=F"], "1mo", "1h")

    xag_1h, _ = fetch_dukascopy("XAGUSD", "1h", days_back=15)
    if xag_1h is None:
        xag_1h, _ = fetch_yfinance_fallback(["XAGUSD=X", "SI=F"], "1mo", "1h")

    eur_1h, _ = fetch_dukascopy("XAUEUR", "1h", days_back=15)
    if eur_1h is None:
        fx_1h, _ = fetch_yfinance_fallback(["EURUSD=X"], "1mo", "1h")
        if xau_1h is not None and fx_1h is not None:
            common_1h = xau_1h.index.intersection(fx_1h.index)
            eur_1h = pd.DataFrame({
                "Open": xau_1h.loc[common_1h, "Open"] / fx_1h.loc[common_1h, "Open"],
                "High": xau_1h.loc[common_1h, "High"] / fx_1h.loc[common_1h, "Low"],
                "Low": xau_1h.loc[common_1h, "Low"] / fx_1h.loc[common_1h, "High"],
                "Close": xau_1h.loc[common_1h, "Close"] / fx_1h.loc[common_1h, "Close"],
            }).dropna()

    if xau_15m is None or xag_15m is None or eur_15m is None:
        print("Gagal mengunduh salah satu pasangan utama.")
        return

    common_gsr = xau_15m.index.intersection(xag_15m.index)
    gsr_now = round(float(xau_15m.loc[common_gsr, "Close"].iloc[-1] / xag_15m.loc[common_gsr, "Close"].iloc[-1]), 2)

    now_wib = datetime.now(WIB)
    utc_hour = datetime.now(timezone.utc).hour
    if 0 <= utc_hour < 7:
        session = "ASIA SESSION"
    elif 7 <= utc_hour < 12:
        session = "LONDON SESSION"
    elif 12 <= utc_hour < 17:
        session = "LONDON / NY OVERLAP"
    elif 17 <= utc_hour < 21:
        session = "NEW YORK SESSION"
    else:
        session = "POST-NY / ROLLOVER"

    payload = {
        "last_updated": now_wib.strftime("%Y-%m-%d %H:%M:%S WIB"),
        "session": session,
        "gold_silver_ratio": gsr_now,
        "divergence": {
            "15m": {
                "vs_xagusd": detect_divergence(xau_15m, xag_15m, "XAGUSD", lookback=16),
                "vs_xaueur": detect_divergence(xau_15m, eur_15m, "XAUEUR", lookback=16),
            },
            "1h": {
                "vs_xagusd": detect_divergence(xau_1h, xag_1h, "XAGUSD", lookback=16),
                "vs_xaueur": detect_divergence(xau_1h, eur_1h, "XAUEUR", lookback=16),
            },
        },
        "pairs": {
            "XAUUSD": {
                "source": src_xau,
                "metrics": analyze_pair_metrics(xau_15m),
                "15m": format_candles(xau_15m, limit=120),
                "1h": format_candles(xau_1h, limit=120),
            },
            "XAUEUR": {
                "source": src_eur,
                "metrics": analyze_pair_metrics(eur_15m),
                "15m": format_candles(eur_15m, limit=120),
                "1h": format_candles(eur_1h, limit=120),
            },
            "XAGUSD": {
                "source": src_xag,
                "metrics": analyze_pair_metrics(xag_15m),
                "15m": format_candles(xag_15m, limit=120),
                "1h": format_candles(xag_1h, limit=120),
            },
        },
    }

    with open(os.path.join(OUTPUT_DIR, "metals_divergence.json"), "w") as f:
        json.dump(payload, f)

    print(f"Sukses menyimpan data/metals_divergence.json | Sumber: {src_xau} | Sesi: {session}")


if __name__ == "__main__":
    run_metals_feed()
