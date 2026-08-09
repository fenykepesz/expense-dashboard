// Net Worth tab: combined monthly trend of fund balances + bank account balances
let netWorthChart;
let netWorthData = null;
let netWorthMode = 'total'; // 'total' | 'type' | 'item'

// Palette lives in shared.js (CHART_PALETTE) — alias kept for readability
const NET_WORTH_PALETTE = CHART_PALETTE;

// Order matters: colorIndex for the "By Type" chart view is derived from
// iteration order, so new types must be APPENDED, never inserted, to keep
// existing types' colors stable for anyone who already has this view open.
const NET_WORTH_TYPE_LABELS = {
    bank: 'Bank Accounts',
    pension: 'Pension',
    study_fund: 'Study Funds',
    investment: 'Investments',
    other: 'Other Funds',
    provident_fund: 'Provident Funds',
};

function netWorthGroupOf(s) {
    return s.kind === 'bank' ? 'bank' : s.fund_type;
}

async function loadNetWorthPanel() {
    const resp = await fetch('/api/net-worth');
    netWorthData = await resp.json();
    renderNetWorthItemPicker();
    renderNetWorth();
}

function setNetWorthMode(mode) {
    netWorthMode = mode;
    document.querySelectorAll('#netWorthModePicker .year-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.mode === mode));
    renderNetWorth();
}

// Multi-select item picker, same UX as the dashboard year picker
function renderNetWorthItemPicker() {
    const container = document.getElementById('netWorthItemPicker');
    container.innerHTML = '';

    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'year-btn year-btn-all active';
    allBtn.textContent = 'All';
    allBtn.addEventListener('click', () => {
        container.querySelectorAll('.year-btn').forEach(b => b.classList.remove('active'));
        allBtn.classList.add('active');
        renderNetWorth();
    });
    container.appendChild(allBtn);

    netWorthData.series.forEach(s => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'year-btn';
        btn.dataset.key = s.key;
        btn.textContent = `${s.kind === 'bank' ? '🏦' : '💰'} ${s.name}`;
        btn.title = s.owner_name || '';
        btn.addEventListener('click', () => {
            allBtn.classList.remove('active');
            btn.classList.toggle('active');
            const anySelected = container.querySelectorAll('.year-btn:not(.year-btn-all).active').length > 0;
            if (!anySelected) allBtn.classList.add('active');
            renderNetWorth();
        });
        container.appendChild(btn);
    });
}

function getSelectedNetWorthSeries() {
    const container = document.getElementById('netWorthItemPicker');
    const allBtn = container.querySelector('.year-btn-all');
    if (!allBtn || allBtn.classList.contains('active')) return netWorthData.series;
    const keys = new Set(
        [...container.querySelectorAll('.year-btn:not(.year-btn-all).active')].map(b => b.dataset.key)
    );
    return netWorthData.series.filter(s => keys.has(s.key));
}

// Sum series values per month; a month is null only while ALL inputs are null
function sumSeries(seriesList, monthCount) {
    return Array.from({ length: monthCount }, (_, i) => {
        let sum = 0, any = false;
        seriesList.forEach(s => {
            if (s.balances[i] !== null) { sum += s.balances[i]; any = true; }
        });
        return any ? sum : null;
    });
}

function renderNetWorth() {
    if (!netWorthData) return;
    const months = netWorthData.months;
    const selected = getSelectedNetWorthSeries();

    renderNetWorthCards(selected, months);
    renderNetWorthChart(selected, months);
    renderNetWorthTable(selected, months);
}

function renderNetWorthCards(selected, months) {
    const cards = document.getElementById('netWorthCards');
    if (!months.length || !selected.length) {
        cards.innerHTML = '';
        return;
    }
    const last = months.length - 1;
    const total = sumSeries(selected, months.length);
    const fundsTotal = sumSeries(selected.filter(s => s.kind === 'fund'), months.length)[last];
    const bankTotal = sumSeries(selected.filter(s => s.kind === 'bank'), months.length)[last];
    const change = last > 0 && total[last - 1] !== null && total[last] !== null
        ? total[last] - total[last - 1] : null;

    cards.innerHTML = `
        <div class="card">
            <h3>Net Worth (${escapeHtml(months[last])})</h3>
            <div class="amount">${formatCurrency(total[last] || 0)}</div>
        </div>
        <div class="card">
            <h3>Long-Term Funds</h3>
            <div class="amount">${formatCurrency(fundsTotal || 0)}</div>
        </div>
        <div class="card">
            <h3>Bank Accounts</h3>
            <div class="amount">${formatCurrency(bankTotal || 0)}</div>
        </div>
        <div class="card">
            <h3>1-Month Change</h3>
            <div class="amount">${change === null ? '—' : (change >= 0 ? '▲ ' : '▼ ') + formatCurrency(Math.abs(change))}</div>
        </div>
    `;
}

function renderNetWorthChart(selected, months) {
    const ctx = document.getElementById('netWorthChart');
    if (netWorthChart) netWorthChart.destroy();

    let datasets = [];
    if (netWorthMode === 'total') {
        datasets = [{ label: 'Net Worth', data: sumSeries(selected, months.length), colorIndex: 0 }];
    } else if (netWorthMode === 'type') {
        // Fixed group order keeps each group's color stable across filters
        Object.keys(NET_WORTH_TYPE_LABELS).forEach((group, i) => {
            const members = selected.filter(s => netWorthGroupOf(s) === group);
            if (members.length) {
                datasets.push({
                    label: NET_WORTH_TYPE_LABELS[group],
                    data: sumSeries(members, months.length),
                    colorIndex: i,
                });
            }
        });
    } else {
        // Color index follows the item's position in the FULL list, so
        // filtering never repaints the survivors
        netWorthData.series.forEach((s, i) => {
            if (selected.includes(s)) {
                datasets.push({ label: s.name, data: s.balances, colorIndex: i });
            }
        });
    }

    const chartDatasets = datasets.map(d => {
        const color = NET_WORTH_PALETTE[d.colorIndex % NET_WORTH_PALETTE.length];
        return {
            label: d.label,
            data: d.data,
            borderColor: color,
            backgroundColor: color + '26',
            borderWidth: 2,
            // Second trip through the palette gets a dash as secondary encoding
            borderDash: d.colorIndex >= NET_WORTH_PALETTE.length ? [6, 4] : [],
            pointRadius: months.length > 24 ? 0 : 3,
            fill: netWorthMode === 'total',
            spanGaps: false,
            tension: 0.3,
        };
    });

    netWorthChart = new Chart(ctx, {
        type: 'line',
        data: { labels: months, datasets: chartDatasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: chartDatasets.length > 1,
                    position: 'top',
                    labels: { color: getThemeColors().textColor },
                },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${formatCurrency(ctx.raw)}`,
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: getThemeColors().textColor },
                    grid: { color: getThemeColors().gridColor },
                },
                y: {
                    ticks: {
                        color: getThemeColors().textColor,
                        callback: v => formatCurrency(v),
                    },
                    grid: { color: getThemeColors().gridColor },
                },
            },
        },
    });
}

function renderNetWorthTable(selected, months) {
    const body = document.getElementById('netWorthTableBody');
    if (!months.length || !selected.length) {
        body.innerHTML = '<tr><td colspan="5" class="no-data">No balance data yet — add fund balances or bank transactions first.</td></tr>';
        return;
    }
    body.innerHTML = selected.map(s => {
        let latestIdx = -1;
        for (let i = s.balances.length - 1; i >= 0; i--) {
            if (s.balances[i] !== null) { latestIdx = i; break; }
        }
        const group = NET_WORTH_TYPE_LABELS[netWorthGroupOf(s)] || '';
        return `
            <tr>
                <td>${s.kind === 'bank' ? '🏦' : '💰'} ${escapeHtml(s.name)}</td>
                <td>${escapeHtml(group)}</td>
                <td>${escapeHtml(s.owner_name || '—')}</td>
                <td>${latestIdx === -1 ? '—' : escapeHtml(months[latestIdx])}</td>
                <td class="amount-cell">${latestIdx === -1 ? '—' : formatCurrency(s.balances[latestIdx])}</td>
            </tr>
        `;
    }).join('');
}
