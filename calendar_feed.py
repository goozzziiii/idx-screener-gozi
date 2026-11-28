import json
import os
from datetime import datetime
from urllib.request import Request, urlopen

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Opsional: isi dengan endpoint JSON kalender ekonomi milikmu jika sudah ada.
# Jika kosong atau gagal diakses, script akan otomatis memakai data terstruktur fallback.
CALENDAR_JSON_URL = ""


def _default_calendar_payload():
    """Data kalender ekonomi & riwayat historis (actual/forecast/previous) untuk grafik."""
    events = [
        {
            "id": "us-cpi-yoy",
            "date": "2026-12-10",
            "time_wib": "20:30 WIB",
            "currency": "USD",
            "impact": "HIGH",
            "event": "US CPI YoY",
            "actual": None,
            "forecast": "2.6%",
            "previous": "2.7%",
            "history": [
                {"period": "2026-06", "actual": 3.0, "forecast": 3.1, "previous": 3.3},
                {"period": "2026-07", "actual": 2.9, "forecast": 3.0, "previous": 3.0},
                {"period": "2026-08", "actual": 2.8, "forecast": 2.8, "previous": 2.9},
                {"period": "2026-09", "actual": 2.7, "forecast": 2.7, "previous": 2.8},
                {"period": "2026-10", "actual": 2.7, "forecast": 2.6, "previous": 2.7},
            ],
        },
        {
            "id": "us-nfp",
            "date": "2026-12-04",
            "time_wib": "20:30 WIB",
            "currency": "USD",
            "impact": "HIGH",
            "event": "US Non-Farm Payrolls",
            "actual": None,
            "forecast": "175K",
            "previous": "182K",
            "history": [
                {"period": "2026-06", "actual": 190, "forecast": 180, "previous": 216},
                {"period": "2026-07", "actual": 164, "forecast": 175, "previous": 190},
                {"period": "2026-08", "actual": 152, "forecast": 165, "previous": 164},
                {"period": "2026-09", "actual": 198, "forecast": 170, "previous": 152},
                {"period": "2026-10", "actual": 182, "forecast": 175, "previous": 198},
            ],
        },
        {
            "id": "bi-rate",
            "date": "2026-12-17",
            "time_wib": "14:20 WIB",
            "currency": "IDR",
            "impact": "HIGH",
            "event": "BI 7-Day Reverse Repo Rate",
            "actual": None,
            "forecast": "5.75%",
            "previous": "5.75%",
            "history": [
                {"period": "2026-06", "actual": 6.00, "forecast": 6.00, "previous": 6.25},
                {"period": "2026-07", "actual": 6.00, "forecast": 6.00, "previous": 6.00},
                {"period": "2026-08", "actual": 5.75, "forecast": 6.00, "previous": 6.00},
                {"period": "2026-09", "actual": 5.75, "forecast": 5.75, "previous": 5.75},
                {"period": "2026-10", "actual": 5.75, "forecast": 5.75, "previous": 5.75},
            ],
        },
        {
            "id": "id-cpi-yoy",
            "date": "2026-12-01",
            "time_wib": "11:00 WIB",
            "currency": "IDR",
            "impact": "MEDIUM",
            "event": "Indonesia Inflation YoY",
            "actual": None,
            "forecast": "2.20%",
            "previous": "2.15%",
            "history": [
                {"period": "2026-06", "actual": 2.51, "forecast": 2.65, "previous": 2.84},
                {"period": "2026-07", "actual": 2.13, "forecast": 2.30, "previous": 2.51},
                {"period": "2026-08", "actual": 2.12, "forecast": 2.18, "previous": 2.13},
                {"period": "2026-09", "actual": 1.98, "forecast": 2.05, "previous": 2.12},
                {"period": "2026-10", "actual": 2.15, "forecast": 2.10, "previous": 1.98},
            ],
        },
        {
            "id": "us-fomc-rate",
            "date": "2026-12-16",
            "time_wib": "02:00 WIB",
            "currency": "USD",
            "impact": "HIGH",
            "event": "Fed Interest Rate Decision",
            "actual": None,
            "forecast": "4.25%",
            "previous": "4.50%",
            "history": [
                {"period": "2026-05", "actual": 5.25, "forecast": 5.25, "previous": 5.25},
                {"period": "2026-06", "actual": 5.00, "forecast": 5.00, "previous": 5.25},
                {"period": "2026-07", "actual": 5.00, "forecast": 5.00, "previous": 5.00},
                {"period": "2026-09", "actual": 4.75, "forecast": 4.75, "previous": 5.00},
                {"period": "2026-11", "actual": 4.50, "forecast": 4.50, "previous": 4.75},
            ],
        },
    ]

    return {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
        "source": "fallback_structured",
        "events": events,
    }


def _fetch_remote_calendar(url):
    """Mengambil feed kalender JSON eksternal jika URL dikonfigurasi."""
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GoziTerminal/1.0)",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=15) as resp:
        raw_text = resp.read().decode("utf-8")
        parsed = json.loads(raw_text)

    if isinstance(parsed, dict) and isinstance(parsed.get("events"), list):
        return {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
            "source": url,
            "events": parsed["events"],
        }
    raise ValueError("Format JSON remote harus berupa object dengan list 'events'.")


def run_calendar_feed():
    if CALENDAR_JSON_URL.strip():
        try:
            payload = _fetch_remote_calendar(CALENDAR_JSON_URL.strip())
            print(f"[CALENDAR OK] Berhasil memuat feed dari {CALENDAR_JSON_URL} ({len(payload['events'])} event).")
        except Exception as e:
            print(f"[CALENDAR WARN] Gagal ambil remote feed ({e}). Memakai fallback data.")
            payload = _default_calendar_payload()
    else:
        print("[CALENDAR INFO] CALENDAR_JSON_URL belum diisi. Memakai data terstruktur & riwayat historis.")
        payload = _default_calendar_payload()

    out_path = os.path.join(OUTPUT_DIR, "economic_calendar.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Sukses menyimpan {out_path} ({len(payload['events'])} event).")


if __name__ == "__main__":
    run_calendar_feed()
