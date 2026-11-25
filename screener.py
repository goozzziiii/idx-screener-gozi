<!DOCTYPE html>
<html lang="id" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IDX Technical Screener & Chart</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body {
            background-color: #131722;
            color: #d1d4dc;
            font-family: -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif;
            overflow-x: hidden;
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #131722; }
        ::-webkit-scrollbar-thumb { background: #2a2e39; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #434651; }
        .tv-panel { background-color: #1e222d; border: 1px solid #2a2e39; }
        .tv-hover:hover { background-color: #2a2e39; }
        .tv-active { background-color: #2962ff26; border-left: 3px solid #2962ff; }
    </style>
</head>
<body class="h-screen flex flex-col">

    <!-- Header -->
    <header class="h-12 bg-[#1e222d] border-b border-[#2a2e39] px-4 flex items-center justify-between shrink-0">
        <div class="flex items-center space-x-3">
            <div class="bg-[#2962ff] text-white font-bold px-2 py-0.5 rounded text-sm tracking-wide">IDX</div>
            <div>
                <h1 class="text-sm font-semibold text-white leading-tight">IDX Technical Screener</h1>
                <p id="last-updated" class="text-[11px] text-gray-400">Memuat jadwal pembaruan...</p>
            </div>
        </div>
        <div class="flex items-center space-x-4 text-xs">
            <div class="hidden sm:flex items-center space-x-3">
                <span class="flex items-center"><span class="w-2.5 h-0.5 bg-[#2962ff] mr-1.5"></span>MA 20</span>
                <span class="flex items-center"><span class="w-2.5 h-0.5 bg-[#ff6d00] mr-1.5"></span>MA 50</span>
                <span class="flex items-center"><span class="w-2.5 h-0.5 bg-[#00e676] mr-1.5"></span>CRT Active</span>
            </div>
            <span class="text-gray-500">|</span>
            <span class="text-gray-400">Data: Yahoo Finance (EOD)</span>
        </div>
    </header>

    <!-- Main Workspace -->
    <div class="flex-1 flex flex-col lg:flex-row overflow-hidden">

        <!-- Left Chart Area -->
        <div class="flex-1 flex flex-col border-b lg:border-b-0 lg:border-r border-[#2a2e39] min-h-[380px]">
            <div class="h-12 px-4 bg-[#131722] border-b border-[#2a2e39] flex items-center justify-between shrink-0">
                <div class="flex items-center space-x-3">
                    <span id="chart-ticker" class="text-lg font-bold text-white">BBCA</span>
                    <span class="text-xs px-1.5 py-0.5 rounded bg-[#2a2e39] text-gray-300">IDX • 1D</span>
                    <span id="chart-price" class="text-base font-semibold text-white">-</span>
                    <span id="chart-change" class="text-xs font-medium">-</span>
                    <span id="chart-crt-badge" class="hidden text-[11px] font-semibold px-2 py-0.5 rounded bg-[#00e676]/20 text-[#00e676]">-</span>
                </div>
                <div id="ohlc-legend" class="hidden md:flex items-center space-x-3 text-xs text-gray-400">
                    <span>O: <b id="leg-o" class="text-gray-200 font-normal">-</b></span>
                    <span>H: <b id="leg-h" class="text-gray-200 font-normal">-</b></span>
                    <span>L: <b id="leg-l" class="text-gray-200 font-normal">-</b></span>
                    <span>C: <b id="leg-c" class="text-gray-200 font-normal">-</b></span>
                    <span class="text-[#2962ff]">MA20: <b id="leg-ma20" class="font-normal">-</b></span>
                    <span class="text-[#ff6d00]">MA50: <b id="leg-ma50" class="font-normal">-</b></span>
                </div>
            </div>

            <div id="tv-chart-container" class="flex-1 w-full relative bg-[#131722]"></div>
        </div>

        <!-- Right Screener Panel -->
        <div class="w-full lg:w-[440px] bg-[#1e222d] flex flex-col h-[50vh] lg:h-full shrink-0">

            <div class="p-3 border-b border-[#2a2e39]">
                <div class="relative">
                    <input type="text" id="search-input" placeholder="Cari kode emiten (misal: BBCA, DEWA, ADRO)..."
                        class="w-full bg-[#131722] text-sm text-white placeholder-gray-500 px-3 py-1.5 rounded border border-[#2a2e39] focus:outline-none focus:border-[#2962ff]">
                </div>
            </div>

            <!-- Filter Tabs -->
            <div class="flex border-b border-[#2a2e39] text-xs font-medium bg-[#131722] overflow-x-auto shrink-0">
                <button onclick="setTab('all')" id="tab-all" class="tab-btn px-3 py-2.5 text-white border-b-2 border-[#2962ff] whitespace-nowrap">
                    Semua (<span id="count-all">0</span>)
                </button>
                <button onclick="setTab('crt')" id="tab-crt" class="tab-btn px-3 py-2.5 text-gray-400 hover:text-white whitespace-nowrap">
                    CRT Bull (<span id="count-crt">0</span>)
                </button>
                <button onclick="setTab('stoch')" id="tab-stoch" class="tab-btn px-3 py-2.5 text-gray-400 hover:text-white whitespace-nowrap">
                    StochRSI OS (<span id="count-stoch">0</span>)
                </button>
                <button onclick="setTab('ma20')" id="tab-ma20" class="tab-btn px-3 py-2.5 text-gray-400 hover:text-white whitespace-nowrap">
                    > MA20 (<span id="count-ma20">0</span>)
                </button>
                <button onclick="setTab('ma50')" id="tab-ma50" class="tab-btn px-3 py-2.5 text-gray-400 hover:text-white whitespace-nowrap">
                    > MA50 (<span id="count-ma50">0</span>)
                </button>
            </div>

            <!-- Table Column Headers -->
            <div class="grid grid-cols-12 px-3 py-2 text-[11px] font-semibold text-gray-400 border-b border-[#2a2e39] bg-[#1e222d] shrink-0">
                <div class="col-span-4">EMITEN</div>
                <div class="col-span-3 text-right">HARGA</div>
                <div class="col-span-3 text-right">MA20 / MA50</div>
                <div class="col-span-2 text-right">STOCH RSI</div>
            </div>

            <!-- Stock List -->
            <div id="stock-list" class="flex-1 overflow-y-auto divide-y divide-[#2a2e39]/50">
                <div class="p-8 text-center text-sm text-gray-500">Memuat data screener...</div>
            </div>
        </div>
    </div>

    <script>
        let screenerData = null;
        let currentTab = 'all';
        let selectedTicker = 'BBCA';

        let chart, candleSeries, volumeSeries, ma20Series, ma50Series;
        let crtPriceLines = [];

        function initChart() {
            const container = document.getElementById('tv-chart-container');
            chart = LightweightCharts.createChart(container, {
                layout: {
                    background: { type: 'solid', color: '#131722' },
                    textColor: '#d1d4dc',
                },
                grid: {
                    vertLines: { color: '#1e222d' },
                    horzLines: { color: '#1e222d' },
                },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                rightPriceScale: { borderColor: '#2a2e39' },
                timeScale: { borderColor: '#2a2e39', timeVisible: true },
            });

            candleSeries = chart.addCandlestickSeries({
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            });

            volumeSeries = chart.addHistogramSeries({
                priceFormat: { type: 'volume' },
                priceScaleId: '',
            });
            volumeSeries.priceScale().applyOptions({
                scaleMargins: { top: 0.82, bottom: 0 },
            });

            ma20Series = chart.addLineSeries({ color: '#2962ff', lineWidth: 1.5, priceLineVisible: false });
            ma50Series = chart.addLineSeries({ color: '#ff6d00', lineWidth: 1.5, priceLineVisible: false });

            chart.subscribeCrosshairMove((param) => {
                if (!param.time || !param.seriesData) return;
                const c = param.seriesData.get(candleSeries);
                const m20 = param.seriesData.get(ma20Series);
                const m50 = param.seriesData.get(ma50Series);
                if (c) {
                    document.getElementById('leg-o').textContent = c.open.toLocaleString('id-ID');
                    document.getElementById('leg-h').textContent = c.high.toLocaleString('id-ID');
                    document.getElementById('leg-l').textContent = c.low.toLocaleString('id-ID');
                    document.getElementById('leg-c').textContent = c.close.toLocaleString('id-ID');
                }
                if (m20) document.getElementById('leg-ma20').textContent = m20.value.toLocaleString('id-ID');
                if (m50) document.getElementById('leg-ma50').textContent = m50.value.toLocaleString('id-ID');
            });

            window.addEventListener('resize', () => {
                chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
            });
        }

        async function loadStockChart(ticker) {
            selectedTicker = ticker;
            renderStockList();

            const summary = screenerData.all_data[ticker];
            if (summary) {
                document.getElementById('chart-ticker').textContent = ticker;
                document.getElementById('chart-price').textContent = 'Rp ' + summary.close.toLocaleString('id-ID');
                const chgEl = document.getElementById('chart-change');
                const sign = summary.change_pct > 0 ? '+' : '';
                chgEl.textContent = `${sign}${summary.change_pct}%`;
                chgEl.className = `text-xs font-medium ${summary.change_pct >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'}`;
            }

            try {
                const res = await fetch(`data/charts/${ticker}.json`);
                const data = await res.json();

                candleSeries.setData(data.candles);
                volumeSeries.setData(data.volume);
                ma20Series.setData(data.ma20);
                ma50Series.setData(data.ma50);

                // Hapus garis CRT lama
                crtPriceLines.forEach(line => candleSeries.removePriceLine(line));
                crtPriceLines = [];
                candleSeries.setMarkers([]);

                const crtBadge = document.getElementById('chart-crt-badge');
                crtBadge.classList.add('hidden');

                // Gambar panah & garis CRT jika tersedia
                if (data.crt) {
                    if (data.crt.markers && data.crt.markers.length > 0) {
                        candleSeries.setMarkers(data.crt.markers);
                    }

                    const setup = data.crt.latest_setup;
                    if (setup && !setup.is_broken) {
                        const isBull = setup.dir === 1;
                        const col = isBull ? '#00e676' : (setup.dir === -1 ? '#ff5252' : '#ff9800');

                        crtBadge.textContent = `${setup.signal} (${setup.date_c2})`;
                        crtBadge.className = `text-[11px] font-semibold px-2 py-0.5 rounded ${
                            isBull ? 'bg-[#00e676]/20 text-[#00e676]' : 'bg-[#ff5252]/20 text-[#ff5252]'
                        }`;

                        crtPriceLines.push(candleSeries.createPriceLine({
                            price: setup.crth, color: col, lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: 'CRTH'
                        }));
                        crtPriceLines.push(candleSeries.createPriceLine({
                            price: setup.mid50, color: col, lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '50%'
                        }));
                        crtPriceLines.push(candleSeries.createPriceLine({
                            price: setup.crtl, color: col, lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: 'CRTL'
                        }));
                    }
                }

                if (data.candles.length > 0) {
                    const last = data.candles[data.candles.length - 1];
                    document.getElementById('leg-o').textContent = last.open.toLocaleString('id-ID');
                    document.getElementById('leg-h').textContent = last.high.toLocaleString('id-ID');
                    document.getElementById('leg-l').textContent = last.low.toLocaleString('id-ID');
                    document.getElementById('leg-c').textContent = last.close.toLocaleString('id-ID');
                }
                if (data.ma20.length > 0) document.getElementById('leg-ma20').textContent = data.ma20[data.ma20.length - 1].value.toLocaleString('id-ID');
                if (data.ma50.length > 0) document.getElementById('leg-ma50').textContent = data.ma50[data.ma50.length - 1].value.toLocaleString('id-ID');

                chart.timeScale().fitContent();
            } catch (err) {
                console.error("Gagal memuat chart:", err);
            }
        }

        function setTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('text-white', 'border-b-2', 'border-[#2962ff]');
                btn.classList.add('text-gray-400');
            });
            const activeBtn = document.getElementById(`tab-${tab}`);
            activeBtn.classList.remove('text-gray-400');
            activeBtn.classList.add('text-white', 'border-b-2', 'border-[#2962ff]');
            renderStockList();
        }

        function renderStockList() {
            if (!screenerData) return;
            const query = document.getElementById('search-input').value.trim().toUpperCase();

            let list = [];
            if (currentTab === 'all') list = Object.values(screenerData.all_data);
            else if (currentTab === 'crt') list = screenerData.crt_bull_active || [];
            else if (currentTab === 'stoch') list = screenerData.stoch_golden_cross || [];
            else if (currentTab === 'ma20') list = screenerData.above_ma20 || [];
            else if (currentTab === 'ma50') list = screenerData.above_ma50 || [];

            if (query) {
                list = list.filter(item => item.ticker.includes(query));
            }

            const container = document.getElementById('stock-list');
            if (list.length === 0) {
                container.innerHTML = `<div class="p-8 text-center text-xs text-gray-500">Tidak ada emiten yang memenuhi kriteria.</div>`;
                return;
            }

            container.innerHTML = list.map(item => {
                const isSelected = item.ticker === selectedTicker;
                const chgColor = item.change_pct >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]';
                const sign = item.change_pct > 0 ? '+' : '';
                const crtTag = item.crt_sig ? `<span class="ml-1 text-[9px] px-1 rounded bg-[#00e676]/20 text-[#00e676]">${item.crt_sig}</span>` : '';

                return `
                <div onclick="loadStockChart('${item.ticker}')"
                     class="grid grid-cols-12 items-center px-3 py-2.5 cursor-pointer tv-hover transition-colors ${isSelected ? 'tv-active' : ''}">
                    <div class="col-span-4">
                        <div class="font-bold text-sm text-white flex items-center">${item.ticker}${crtTag}</div>
                        <div class="text-[10px] text-gray-500">IDX</div>
                    </div>
                    <div class="col-span-3 text-right">
                        <div class="text-xs font-semibold text-white">${item.close.toLocaleString('id-ID')}</div>
                        <div class="text-[11px] ${chgColor}">${sign}${item.change_pct}%</div>
                    </div>
                    <div class="col-span-3 text-right text-[11px]">
                        <div class="text-[#2962ff]">${item.ma20.toLocaleString('id-ID')}</div>
                        <div class="text-[#ff6d00]">${item.ma50.toLocaleString('id-ID')}</div>
                    </div>
                    <div class="col-span-2 text-right text-[11px]">
                        <div class="text-gray-200">K: ${item.stoch_k}</div>
                        <div class="text-gray-500">D: ${item.stoch_d}</div>
                    </div>
                </div>`;
            }).join('');
        }

        async function initApp() {
            initChart();
            try {
                const res = await fetch('data/screener_idx.json?t=' + Date.now());
                screenerData = await res.json();

                document.getElementById('last-updated').textContent = `Update: ${screenerData.last_updated}`;
                document.getElementById('count-all').textContent = Object.keys(screenerData.all_data).length;
                document.getElementById('count-crt').textContent = (screenerData.crt_bull_active || []).length;
                document.getElementById('count-stoch').textContent = (screenerData.stoch_golden_cross || []).length;
                document.getElementById('count-ma20').textContent = (screenerData.above_ma20 || []).length;
                document.getElementById('count-ma50').textContent = (screenerData.above_ma50 || []).length;

                renderStockList();
                const initialTicker = screenerData.all_data['BBCA'] ? 'BBCA' : Object.keys(screenerData.all_data)[0];
                if (initialTicker) loadStockChart(initialTicker);
            } catch (err) {
                document.getElementById('stock-list').innerHTML =
                    `<div class="p-6 text-center text-xs text-red-400">Gagal memuat data JSON.</div>`;
            }
        }

        document.getElementById('search-input').addEventListener('input', renderStockList);
        initApp();
    </script>
</body>
</html>
