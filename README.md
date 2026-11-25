# 📊 GOZI TERMINAL | IDX Market & Technical Workspace

Web terminal analisis teknikal dan *screener* saham Bursa Efek Indonesia (IDX) bergaya Bloomberg & TradingView. Dilengkapi dengan pembaruan data harian otomatis via GitHub Actions, dukungan *multi-timeframe* (`1D`, `1W`, `1M`), indikator teknikal dinamis, deteksi **Candle Range Theory (CRT)**, serta *drawing tools* interaktif.

---

## ✨ Fitur Utama

* **Interactive Technical Chart (TradingView Lightweight Charts)**
  * Mendukung timeframe **Daily (`1D`)**, **Weekly (`1W`)**, dan **Monthly (`1M`)**.
  * Kustomisasi tampilan chart (Dark/Light mode, warna body/wick/border candlestick).
* **Indikator Teknikal & Deteksi CRT Otomatis**
  * **Moving Average (`MA1` & `MA2`):** Mendukung SMA/EMA dengan periode dan warna yang bisa diatur langsung dari UI.
  * **Candle Range Theory (CRT):** Deteksi otomatis status `CONFIRMED` maupun `POTENTIAL` beserta garis level `CRTH`, `50% Mid`, dan `CRTL`.
  * **Sub-Pane Oscillators:** Dilengkapi **RSI (14)** dan **Stochastic RSI (10, 10, 5, 5)** standar TradingView.
* **TradingView-Style Drawing Tools**
  * Mendukung *Trendline*, *Extended Ray*, *Horizontal/Vertical Line*, *Rectangle/Zone*, *Fibonacci Retracement*, *Long/Short Position Box*, dan *Text Annotation*.
  * Objek gambar bisa dipilih, digeser, diubah ukurannya (*anchor handles*), diedit warnanya, dan tersimpan otomatis di `localStorage` per emiten & timeframe.
* **Multi-Filter IDX Screener & Full-Screen Table**
  * Filter emiten berdasarkan harga, nilai transaksi (Rp Miliar), status *CRT Bull* (`Confirmed`/`Potential`), posisi *Moving Average*, *StochRSI*, dan *RSI*.
  * Mode tabel layar penuh (*Full Screen*) untuk membandingkan seluruh metrik emiten sekaligus.
* **Otomatisasi Data Harian (GitHub Actions)**
  * Dijalankan secara terjadwal melalui `.github/workflows/daily_screener.yml` untuk mengunduh data historis 5 tahun dari Yahoo Finance dan memperbarui file JSON secara otomatis.

---

## 📂 Struktur Repository

```text
├── .github/workflows/
│   └── daily_screener.yml    # Otomatisasi update data harian via GitHub Actions
├── data/
│   ├── charts/               # Data historis OHLCV & level CRT per emiten (<TICKER>.json)
│   └── screener_idx.json     # Ringkasan seluruh emiten IDX untuk tabel screener
├── daftar_saham.xlsx.xlsx    # Daftar emiten aktif BEI (sumber kode ticker)
├── index.html                # Antarmuka utama web workspace (HTML + Tailwind + JS)
├── screener.py               # Engine Python penarik data Yahoo Finance & kalkulasi teknikal
├── requirements.txt          # Dependensi Python (yfinance, pandas, openpyxl)
└── README.md                 # Dokumentasi proyek
