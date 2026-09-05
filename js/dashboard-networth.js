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
    money_market_fund: 'Money Market Funds',
    savings_policy: 'Savings Policies',
    investment_provident_fund: 'Investment Provident Funds',
    real_estate: 'Real Estate',
    stock: 'Stocks',
};

function netWorthGroupOf(s) {
    if (s.kind === 'bank') return 'bank';
    if (s.kind === 'stock') return 'stock';
    return s.fund_type;
}

function netWorthIcon(s) {
    if (s.kind === 'bank') return '🏦';
    if (s.kind === 'stock') return '📈';
    return '💰';
}

// Owner + (for stocks) Type — two different stock holdings can share the
// same Symbol (e.g. an RSU grant and a separate ESPP purchase of the same
// company), so the Type needs to show wherever items are identified by
// name alone, not just in the Manage Stock Holdings table.
function netWorthSubLine(s) {
    const parts = [];
    if (s.owner_name) parts.push(s.owner_name);
    if (s.kind === 'stock' && s.holding_type) {
        parts.push(STOCK_HOLDING_TYPE_LABELS[s.holding_type] || s.holding_type);
    }
    // Bank accounts only, for now — the date their balance last actually
    // moved (most recent transaction on file), same value shown next to
    // the Bank Accounts tab's transaction list so the two can never disagree.
    if (s.kind === 'bank' && s.latest_date) {
        parts.push(`updated ${s.latest_date}`);
    }
    return parts.join(' · ');
}

async function loadNetWorthPanel() {
    const resp = await fetch('/api/net-worth');
    netWorthData = await resp.json();
    renderNetWorthItemPicker();
    renderNetWorthOwnerPicker();
    renderNetWorth();
}

function setNetWorthMode(mode) {
    netWorthMode = mode;
    document.querySelectorAll('#netWorthModePicker .year-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.mode === mode));
    renderNetWorth();
}

// Wires up the shared "All + toggleable pills" behavior used by both the
// item and owner pickers: clicking a pill toggles itself, then the overall
// All button and any per-category All buttons are reconciled to match.
function wirePickerToggle(container, allBtn, btn) {
    btn.addEventListener('click', () => {
        btn.classList.toggle('active');
        syncPickerAllButtons(container, allBtn);
        renderNetWorth();
    });
}

// Real pills only — excludes the overall All button and per-category All
// buttons, both of which are bulk-select controls, not selectable items.
function pickerItemButtons(container) {
    return [...container.querySelectorAll('.year-btn:not(.year-btn-all):not(.category-all-btn)')];
}

// Keeps the overall All button and every per-category All button in sync
// with the actual pill selection, after any individual/category toggle.
function syncPickerAllButtons(container, allBtn) {
    const itemBtns = pickerItemButtons(container);
    const anySelected = itemBtns.some(b => b.classList.contains('active'));
    allBtn.classList.toggle('active', !anySelected);

    container.querySelectorAll('.category-all-btn').forEach(catBtn => {
        const groupItems = itemBtns.filter(b => b.dataset.group === catBtn.dataset.group);
        const allActive = groupItems.length > 0 && groupItems.every(b => b.classList.contains('active'));
        catBtn.classList.toggle('active', allActive);
    });
}

function makeAllPickerButton(container) {
    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'year-btn year-btn-all active';
    allBtn.textContent = 'All';
    allBtn.addEventListener('click', () => {
        container.querySelectorAll('.year-btn').forEach(b => b.classList.remove('active'));
        allBtn.classList.add('active');
        renderNetWorth();
    });
    return allBtn;
}

// Multi-select item picker, grouped by type/Bank Accounts so the list reads
// as categories instead of one flat wall of pills — same grouping + stable
// order as the "By Type" chart view (NET_WORTH_TYPE_LABELS).
function renderNetWorthItemPicker() {
    const container = document.getElementById('netWorthItemPicker');
    container.innerHTML = '';

    // "All" spans the full width as its own row — it toggles everything,
    // so it shouldn't share a grid cell with the category columns below it.
    const allBtn = makeAllPickerButton(container);
    allBtn.classList.add('picker-all-btn');
    container.appendChild(allBtn);

    const grid = document.createElement('div');
    grid.className = 'picker-groups';
    container.appendChild(grid);

    Object.keys(NET_WORTH_TYPE_LABELS).forEach(group => {
        const members = netWorthData.series.filter(s => netWorthGroupOf(s) === group);
        if (!members.length) return;

        const groupDiv = document.createElement('div');
        groupDiv.className = 'picker-group';
        const label = document.createElement('div');
        label.className = 'picker-group-label';
        label.textContent = NET_WORTH_TYPE_LABELS[group];
        groupDiv.appendChild(label);

        const row = document.createElement('div');
        row.className = 'year-picker';

        const categoryAllBtn = document.createElement('button');
        categoryAllBtn.type = 'button';
        categoryAllBtn.className = 'year-btn year-btn-all category-all-btn';
        categoryAllBtn.textContent = 'All';
        categoryAllBtn.dataset.group = group;
        row.appendChild(categoryAllBtn);

        const itemBtns = [];
        members.forEach(s => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'year-btn';
            btn.dataset.key = s.key;
            btn.dataset.group = group;
            const subLine = netWorthSubLine(s);
            btn.innerHTML = `${netWorthIcon(s)} ${escapeHtml(s.name)}` +
                (subLine ? `<span class="picker-owner-sub">${escapeHtml(subLine)}</span>` : '');
            btn.title = subLine;
            wirePickerToggle(container, allBtn, btn);
            row.appendChild(btn);
            itemBtns.push(btn);
        });

        categoryAllBtn.addEventListener('click', () => {
            const allActive = itemBtns.every(b => b.classList.contains('active'));
            itemBtns.forEach(b => b.classList.toggle('active', !allActive));
            syncPickerAllButtons(container, allBtn);
            renderNetWorth();
        });

        groupDiv.appendChild(row);
        grid.appendChild(groupDiv);
    });
}

// Multi-select owner picker — ANDs with the item picker above, so picking
// an owner narrows the cards/chart/table to just that owner's net worth
// without having to hand-select every one of their funds/accounts.
function renderNetWorthOwnerPicker() {
    const container = document.getElementById('netWorthOwnerPicker');
    container.innerHTML = '';

    const allBtn = makeAllPickerButton(container);
    container.appendChild(allBtn);

    const owners = [...new Set(netWorthData.series.map(s => s.owner_name || 'No Owner'))]
        .sort((a, b) => a.localeCompare(b, 'he'));
    owners.forEach(owner => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'year-btn';
        btn.dataset.owner = owner;
        btn.textContent = `👤 ${owner}`;
        wirePickerToggle(container, allBtn, btn);
        container.appendChild(btn);
    });
}

function getSelectedNetWorthOwners() {
    const container = document.getElementById('netWorthOwnerPicker');
    const allBtn = container.querySelector('.year-btn-all');
    if (!allBtn || allBtn.classList.contains('active')) return null;
    return new Set(
        [...container.querySelectorAll('.year-btn:not(.year-btn-all).active')].map(b => b.dataset.owner)
    );
}

function getSelectedNetWorthSeries() {
    const container = document.getElementById('netWorthItemPicker');
    // .picker-all-btn (not the more generic .year-btn-all, which also matches
    // each category's own "All" button) uniquely identifies the overall toggle.
    const allBtn = container.querySelector('.picker-all-btn');
    let selected;
    if (!allBtn || allBtn.classList.contains('active')) {
        selected = netWorthData.series;
    } else {
        const keys = new Set(pickerItemButtons(container).filter(b => b.classList.contains('active')).map(b => b.dataset.key));
        selected = netWorthData.series.filter(s => keys.has(s.key));
    }

    const owners = getSelectedNetWorthOwners();
    if (owners) selected = selected.filter(s => owners.has(s.owner_name || 'No Owner'));
    return selected;
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
    const fundsTotal = sumSeries(selected.filter(s => s.kind === 'fund' || s.kind === 'stock'), months.length)[last];
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
        const typeSuffix = (s.kind === 'stock' && s.holding_type)
            ? ` <span style="color:var(--text-secondary);font-size:0.85em;">(${escapeHtml(STOCK_HOLDING_TYPE_LABELS[s.holding_type] || s.holding_type)})</span>`
            : '';
        return `
            <tr>
                <td>${netWorthIcon(s)} ${escapeHtml(s.name)}${typeSuffix}</td>
                <td>${escapeHtml(group)}</td>
                <td>${escapeHtml(s.owner_name || '—')}</td>
                <td>${latestIdx === -1 ? '—' : escapeHtml(months[latestIdx])}</td>
                <td class="amount-cell">${latestIdx === -1 ? '—' : formatCurrency(s.balances[latestIdx])}</td>
            </tr>
        `;
    }).join('');
}
