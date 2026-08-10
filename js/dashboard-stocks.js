// Long-Term Funds tab: Stocks sub-panel. Holdings are Symbol + Quantity,
// deriving Total/Net Value server-side (approximate 25% capital-gains tax
// on the gain above Cost Basis only — see db.py's _compute_stock_value).
// A separate entity from `funds`: own table, own API, own panel, since the
// fields/columns here don't fit the generic fund shape.
let currentStockHoldings = [];
let stockMembers = [];
let selectedStockHoldingId = null;
let stocksSortCol = 'symbol';
let stocksSortDir = 1;

const STOCK_HOLDING_TYPE_LABELS = { stock: 'Stock', espp: 'ESPP', rsu: 'RSU' };

async function loadStocksPanel() {
    const [holdingsResp, membersResp] = await Promise.all([
        fetch('/api/stock-holdings'),
        fetch('/api/household-members'),
    ]);
    currentStockHoldings = await holdingsResp.json();
    stockMembers = await membersResp.json();

    const ownerOpts = '<option value="">No owner</option>' +
        stockMembers.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');
    document.getElementById('newStockOwnerInput').innerHTML = ownerOpts;

    renderStocksList();
    renderStockValuePicker();
}

async function refreshStockHoldings() {
    const resp = await fetch('/api/stock-holdings');
    currentStockHoldings = await resp.json();
    renderStocksList();
    renderStockValuePicker();
}

function stockTypeOptions(selected) {
    return Object.entries(STOCK_HOLDING_TYPE_LABELS)
        .map(([val, label]) => `<option value="${val}"${selected === val ? ' selected' : ''}>${label}</option>`)
        .join('');
}

function stockOwnerOptions(selectedId) {
    return '<option value="">No owner</option>' + stockMembers.map(m =>
        `<option value="${m.id}"${String(selectedId) === String(m.id) ? ' selected' : ''}>${escapeHtml(m.name)}</option>`
    ).join('');
}

// ── Table: sortable headers, every cell directly editable (same pattern as
// the Manage Funds table) ───────────────────────────────────────────────

function sortStocksColumn(col) {
    stocksSortDir = (stocksSortCol === col) ? -stocksSortDir : 1;
    stocksSortCol = col;
    renderStocksList();
}

function sortStocks(list) {
    return [...list].sort((a, b) => {
        let va = a[stocksSortCol], vb = b[stocksSortCol];
        const aEmpty = va === null || va === undefined || va === '';
        const bEmpty = vb === null || vb === undefined || vb === '';
        if (aEmpty && bEmpty) return 0;
        if (aEmpty) return 1;   // blanks/unset always sort last, both directions
        if (bEmpty) return -1;
        if (typeof va === 'number') return stocksSortDir * (va - vb);
        return stocksSortDir * String(va).localeCompare(String(vb), 'he');
    });
}

function stocksTh(col, label) {
    const active = col === stocksSortCol;
    const arrow = active ? (stocksSortDir === 1 ? ' ▲' : ' ▼') : ' ↕';
    return `<th onclick="sortStocksColumn('${col}')" style="cursor:pointer;white-space:nowrap;">${label}<span style="opacity:${active ? 1 : 0.35};font-size:0.75em;">${arrow}</span></th>`;
}

function renderStocksList() {
    const wrap = document.getElementById('stocksTableWrap');
    let bodyHtml;
    if (!currentStockHoldings.length) {
        bodyHtml = '<tr><td colspan="12" class="no-data">No stock holdings yet — add one above.</td></tr>';
    } else {
        bodyHtml = sortStocks(currentStockHoldings).map(renderStockRow).join('');
    }
    wrap.innerHTML = `
        <table class="transactions-table">
            <thead><tr>
                ${stocksTh('brokerage_firm', 'Brokerage Firm')}
                ${stocksTh('symbol', 'Symbol')}
                ${stocksTh('latest_quantity', 'Quantity')}
                ${stocksTh('latest_date', 'Value Date')}
                ${stocksTh('latest_price', 'Stock Value (unit)')}
                ${stocksTh('latest_total_value', 'Total Value')}
                ${stocksTh('latest_net_value', 'Net Value')}
                ${stocksTh('holding_type', 'Type')}
                ${stocksTh('owner_name', 'Owner')}
                ${stocksTh('cost_basis', 'Cost Basis')}
                ${stocksTh('excluded_from_net_worth', 'Net Worth')}
                <th></th>
            </tr></thead>
            <tbody>${bodyHtml}</tbody>
        </table>
    `;
}

function renderStockRow(h) {
    const hasLatest = h.latest_quantity !== null && h.latest_quantity !== undefined;
    let netValueCell = '—';
    if (hasLatest) {
        netValueCell = h.latest_net_value !== null
            ? formatCurrency(h.latest_net_value)
            : '<span class="stock-warn" title="Cost basis needed to estimate tax — Net Value will not guess">⚠ Needs cost basis</span>';
    }
    return `
        <tr class="${h.excluded_from_net_worth ? 'tx-excluded' : ''}">
            <td><input type="text" class="tx-note-input" value="${escapeHtml(h.brokerage_firm || '')}" placeholder="Brokerage…" onblur="saveStockTextField(${h.id}, 'brokerage_firm', this)" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td><input type="text" class="tx-note-input" value="${escapeHtml(h.symbol)}" placeholder="Symbol…" onblur="saveStockTextField(${h.id}, 'symbol', this)" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td class="amount-cell">${hasLatest ? formatCurrency(h.latest_quantity) : '—'}</td>
            <td>${hasLatest ? escapeHtml(h.latest_date) : '—'}</td>
            <td class="amount-cell">${hasLatest ? formatCurrency(h.latest_price) : '—'}</td>
            <td class="amount-cell">${hasLatest ? formatCurrency(h.latest_total_value) : '—'}</td>
            <td class="amount-cell">${netValueCell}</td>
            <td><select class="tx-cat-select" onchange="updateStockField(${h.id}, 'holding_type', this.value)">${stockTypeOptions(h.holding_type)}</select></td>
            <td><select class="tx-cat-select" onchange="updateStockField(${h.id}, 'owner_id', this.value || null)">${stockOwnerOptions(h.owner_id)}</select></td>
            <td><input type="number" step="0.01" class="tx-note-input" style="width:100px;" value="${h.cost_basis !== null && h.cost_basis !== undefined ? h.cost_basis : ''}" placeholder="Not set" onblur="saveStockCostBasis(${h.id}, this)" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td>${h.excluded_from_net_worth
                ? '<span style="color:var(--text-secondary);font-size:0.85em;">⊘ Excluded</span>'
                : '<span style="color:var(--success-color);font-size:0.85em;">✓ Included</span>'}</td>
            <td>
                <div class="tx-actions">
                    <button class="btn-excl" onclick="toggleStockNetWorthExclude(${h.id})" title="${h.excluded_from_net_worth ? 'Include in Net Worth' : 'Exclude from Net Worth'}">${h.excluded_from_net_worth ? '↺' : '⊘'}</button>
                    <button class="btn-excl btn-delete" onclick="deleteStockHolding(${h.id}, '${escapeHtml(h.symbol).replace(/'/g, "\\'")}')" title="Delete">🗑</button>
                </div>
            </td>
        </tr>
    `;
}

// Select/checkbox-equivalent fields: save immediately + full re-render.
async function updateStockField(id, field, value) {
    const resp = await fetch(`/api/stock-holdings/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to update stock holding'); renderStocksList(); return; }
    currentStockHoldings = result.holdings;
    renderStocksList();
}

// Text fields: save on blur only if changed, without a full re-render —
// mirrors saveFundTextField. Symbol/Brokerage feed the value-entry picker
// below, so those two specifically refresh it.
async function saveStockTextField(id, field, inputEl) {
    const holding = currentStockHoldings.find(h => h.id === id);
    if (!holding) return;
    const value = inputEl.value.trim();
    const previous = holding[field] || '';
    if (value === previous) return;

    const resp = await fetch(`/api/stock-holdings/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to update stock holding'); inputEl.value = previous; return; }
    currentStockHoldings = result.holdings;
    if (field === 'symbol' || field === 'brokerage_firm') renderStockValuePicker();
}

// Cost Basis: a number input where an EMPTY value means "unset" (null),
// not zero — those are different, meaningful states (see db.py's schema
// comment on stock_holdings.cost_basis).
async function saveStockCostBasis(id, inputEl) {
    const holding = currentStockHoldings.find(h => h.id === id);
    if (!holding) return;
    const raw = inputEl.value.trim();
    const value = raw === '' ? null : parseFloat(raw);
    const previous = holding.cost_basis;
    if (value === previous || (value === null && previous === null)) return;

    const resp = await fetch(`/api/stock-holdings/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cost_basis: value }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to update stock holding'); renderStocksList(); return; }
    currentStockHoldings = result.holdings;
    renderStocksList();
}

async function toggleStockNetWorthExclude(id) {
    const holding = currentStockHoldings.find(h => h.id === id);
    if (!holding) return;
    const resp = await fetch(`/api/stock-holdings/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ excluded_from_net_worth: !holding.excluded_from_net_worth }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to update stock holding'); return; }
    currentStockHoldings = result.holdings;
    renderStocksList();
}

async function deleteStockHolding(id, symbol) {
    if (!confirm(`Delete stock holding "${symbol}"? Its value history will no longer be shown.`)) return;
    const resp = await fetch(`/api/stock-holdings/${id}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete stock holding'); return; }
    currentStockHoldings = result.holdings;
    if (selectedStockHoldingId === id) {
        selectedStockHoldingId = null;
        renderStockValuesTable([]);
    }
    renderStocksList();
    renderStockValuePicker();
}

async function addNewStockHolding() {
    const symbol = document.getElementById('newStockSymbolInput').value.trim();
    const brokerageFirm = document.getElementById('newStockBrokerageInput').value.trim();
    const holdingType = document.getElementById('newStockTypeInput').value;
    const ownerId = document.getElementById('newStockOwnerInput').value || null;
    const costBasisRaw = document.getElementById('newStockCostBasisInput').value.trim();
    const costBasis = costBasisRaw === '' ? null : parseFloat(costBasisRaw);
    if (!symbol) { alert('Symbol is required'); return; }
    const resp = await fetch('/api/stock-holdings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            symbol, brokerage_firm: brokerageFirm, holding_type: holdingType,
            owner_id: ownerId, cost_basis: costBasis,
        }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add stock holding'); return; }
    document.getElementById('newStockSymbolInput').value = '';
    document.getElementById('newStockBrokerageInput').value = '';
    document.getElementById('newStockCostBasisInput').value = '';
    currentStockHoldings = result.holdings;
    renderStocksList();
    renderStockValuePicker();
}

// ── Record a Value panel ─────────────────────────────────────────────────

function renderStockValuePicker() {
    const select = document.getElementById('stockValueHoldingSelect');
    const previous = select.value;
    select.innerHTML = '<option value="">Select a holding…</option>' +
        currentStockHoldings.map(h =>
            `<option value="${h.id}">${escapeHtml(h.symbol)}${h.brokerage_firm ? ' — ' + escapeHtml(h.brokerage_firm) : ''}</option>`
        ).join('');
    if (currentStockHoldings.some(h => String(h.id) === previous)) select.value = previous;
}

function onStockValueHoldingChange() {
    const select = document.getElementById('stockValueHoldingSelect');
    const holdingId = select.value ? parseInt(select.value, 10) : null;
    selectedStockHoldingId = holdingId;
    const qtyInput = document.getElementById('newStockValueQuantity');
    if (!holdingId) {
        renderStockValuesTable([]);
        return;
    }
    const holding = currentStockHoldings.find(h => h.id === holdingId);
    // Pre-fill from the last recorded quantity — most check-ins only the
    // price actually changed, so this is usually a no-op for the user.
    if (holding && holding.latest_quantity !== null && holding.latest_quantity !== undefined) {
        qtyInput.value = holding.latest_quantity;
    }
    loadStockValuesFor(holdingId);
}

async function loadStockValuesFor(holdingId) {
    const resp = await fetch(`/api/stock-holdings/${holdingId}/values`);
    const values = await resp.json();
    renderStockValuesTable(values);
}

function renderStockValuesTable(values) {
    const body = document.getElementById('stockValuesBody');
    if (!values.length) {
        body.innerHTML = '<tr><td colspan="4" class="no-data">Select a holding above to see its value history.</td></tr>';
        return;
    }
    body.innerHTML = values.map(v => `
        <tr>
            <td>${escapeHtml(v.date)}</td>
            <td class="amount-cell">${formatCurrency(v.quantity)}</td>
            <td class="amount-cell">${formatCurrency(v.price_per_unit)}</td>
            <td><button class="btn-excl btn-delete" onclick="deleteStockValueEntry(${v.id})" title="Delete">🗑</button></td>
        </tr>
    `).join('');
}

async function addStockValueEntry() {
    const select = document.getElementById('stockValueHoldingSelect');
    const holdingId = select.value;
    const date = document.getElementById('newStockValueDate').value;
    const quantity = document.getElementById('newStockValueQuantity').value;
    const price = document.getElementById('newStockValuePrice').value;
    if (!holdingId) { alert('Select a holding first'); return; }
    if (!date || quantity === '' || price === '') { alert('Date, quantity, and price are required'); return; }
    const resp = await fetch(`/api/stock-holdings/${holdingId}/values`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date, quantity: parseFloat(quantity), price_per_unit: parseFloat(price) }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add value entry'); return; }
    document.getElementById('newStockValueDate').value = '';
    document.getElementById('newStockValuePrice').value = '';
    renderStockValuesTable(result.values);
    await refreshStockHoldings();
}

async function deleteStockValueEntry(valueId) {
    const resp = await fetch(`/api/stock-values/${valueId}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete value entry'); return; }
    renderStockValuesTable(result.values);
    await refreshStockHoldings();
}
