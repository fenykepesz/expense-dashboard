// Look-Through tab: security-level holdings aggregation across every fund
// that's been matched to an institution's regulatory holdings filing (see
// tools/holdings_filing_to_json.py), merged with directly-held
// stock_holdings. Views are read-only aggregation snapshots computed
// server-side (db.py's get_all_securities/get_overlap_holdings/
// get_concentration_rollups/get_direct_fund_overlap) — this file only
// renders them and drives the upload flow.

let lookthroughPendingResult = null;   // the parsed-but-not-yet-confirmed preview payload
let lookthroughSelectedFile = null;
let lookthroughView = 'securities';

// Two of the user's own funds can share an identical display name (a real
// case: two tracks under one savings policy, same Fund Name/Fund #) — this
// keeps every place a fund is named in this file distinguishable.
function fundLabel(f) {
    return f.track_number ? `${f.name} (Track ${f.track_number})` : f.name;
}

const INSTRUMENT_TYPE_LABELS = {
    cash: 'Cash', govt_bond: 'Government Bond', corp_bond: 'Corporate Bond',
    equity_traded: 'Stock', equity_nontraded: 'Stock (non-tradable)',
    etf: 'ETF', mutual_fund: 'Mutual Fund', warrant: 'Warrant', option: 'Option',
    future: 'Future', structured_product: 'Structured Product',
    investment_fund: 'Investment Fund', loan: 'Loan', deposit: 'Deposit',
    real_estate: 'Real Estate',
    fx_swap: 'FX Forward/Swap', interest_rate_swap: 'Interest Rate Swap',
    equity_swap: 'Equity/Index Swap', inflation_swap: 'Inflation (CPI) Swap',
    other: 'Other',
};

// ── Upload panel ─────────────────────────────────────────────────────────

const lookthroughDropzone = document.getElementById('lookthroughDropzone');
const lookthroughFileInput = document.getElementById('lookthroughFileInput');

lookthroughFileInput.addEventListener('change', e => {
    const file = e.target.files[0];
    if (file) selectLookthroughFile(file);
});
lookthroughDropzone.addEventListener('dragover', e => { e.preventDefault(); lookthroughDropzone.classList.add('drag-over'); });
lookthroughDropzone.addEventListener('dragleave', () => lookthroughDropzone.classList.remove('drag-over'));
lookthroughDropzone.addEventListener('drop', e => {
    e.preventDefault();
    lookthroughDropzone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) selectLookthroughFile(file);
});

function selectLookthroughFile(file) {
    lookthroughSelectedFile = file;
    document.getElementById('lookthroughFileName').textContent = file.name;
    document.getElementById('lookthroughAnalyzeBtn').disabled = false;
    document.getElementById('lookthroughPreview').classList.add('hidden');
    lookthroughPendingResult = null;
}

async function analyzeLookthroughFile() {
    if (!lookthroughSelectedFile) return;
    const preview = document.getElementById('lookthroughPreview');
    preview.classList.remove('hidden');
    preview.innerHTML = '<p class="no-data">Analyzing…</p>';

    const formData = new FormData();
    formData.append('file', lookthroughSelectedFile);
    const resp = await fetch('/api/lookthrough/import', { method: 'POST', body: formData });
    const result = await resp.json();
    if (!resp.ok) {
        preview.innerHTML = `<p style="color:var(--error-color);">${escapeHtml(result.error || 'Failed to parse this file.')}</p>`;
        return;
    }

    lookthroughPendingResult = result;
    const warnings = result.unrecognized_sheets.map(u =>
        `<li>${escapeHtml(u.sheet_name)} — ${escapeHtml(u.reason)}</li>`
    ).join('');

    preview.innerHTML = `
        <div style="border:1px solid var(--border-color);border-radius:8px;padding:14px 16px;">
            <p style="margin:0 0 6px;"><strong>${escapeHtml(result.institution_name)}</strong> (${escapeHtml(result.institution_reg_number)}) — Q${result.period_quarter} ${result.period_year}</p>
            <p style="margin:0 0 6px;color:var(--text-secondary);font-size:0.9em;">
                ${result.rows.length} rows matched across ${result.matched_fund_ids.length} of your fund(s).
                ${result.unmatched_track_count ? `${result.unmatched_track_count} rows belonged to tracks you have no fund configured for, and were skipped.` : ''}
            </p>
            ${result.rows.length === 0 ? `<p style="color:var(--error-color);font-size:0.9em;margin:6px 0;">No rows matched any of your funds — check that a fund's Track # and Institution Reg # (Manage Funds table) match this filing.</p>` : ''}
            ${warnings ? `<details style="margin-top:8px;"><summary style="cursor:pointer;color:var(--text-secondary);font-size:0.85em;">${result.unrecognized_sheets.length} sheet(s) needed attention</summary><ul style="font-size:0.82em;color:var(--text-secondary);margin:6px 0 0;">${warnings}</ul></details>` : ''}
            <button class="btn btn-success" style="margin-top:12px;" onclick="confirmLookthroughImport()" ${result.rows.length === 0 ? 'disabled' : ''}>✅ Confirm Import</button>
        </div>
    `;
}

async function confirmLookthroughImport() {
    if (!lookthroughPendingResult) return;
    const resp = await fetch('/api/lookthrough/import/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(lookthroughPendingResult),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to import this filing'); return; }

    lookthroughPendingResult = null;
    lookthroughSelectedFile = null;
    document.getElementById('lookthroughFileName').textContent = '';
    document.getElementById('lookthroughAnalyzeBtn').disabled = true;
    document.getElementById('lookthroughPreview').classList.add('hidden');
    document.getElementById('lookthroughFileInput').value = '';

    await loadLookThroughPanel();
}

// ── Filings list ─────────────────────────────────────────────────────────

async function loadHoldingsFilings() {
    const resp = await fetch('/api/lookthrough/filings');
    const filings = await resp.json();
    renderHoldingsFilings(filings);
}

function renderHoldingsFilings(filings) {
    const body = document.getElementById('lookthroughFilingsBody');
    if (!filings.length) {
        body.innerHTML = '<tr><td colspan="4" class="no-data">No filings imported yet.</td></tr>';
        return;
    }
    body.innerHTML = filings.map(f => `
        <tr>
            <td>${escapeHtml(f.institution_name)} <span style="color:var(--text-secondary);font-size:0.85em;">(${escapeHtml(f.institution_reg_number)})</span></td>
            <td>Q${f.period_quarter} ${f.period_year}</td>
            <td>${escapeHtml((f.imported_at || '').slice(0, 10))}</td>
            <td><button class="btn-excl btn-delete" onclick="deleteHoldingsFiling(${f.id}, '${escapeHtml(f.institution_name).replace(/'/g, "\\'")}')" title="Delete">🗑</button></td>
        </tr>
    `).join('');
}

async function deleteHoldingsFiling(filingId, institutionName) {
    if (!confirm(`Delete the filing for "${institutionName}"? Its holdings will no longer count toward Look-Through aggregation.`)) return;
    const resp = await fetch(`/api/lookthrough/filings/${filingId}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete filing'); return; }
    renderHoldingsFilings(result);
    await renderLookthroughView();
}

// ── Securities table: resizable + sortable + filterable, same pattern as
// the Manage Funds table (dashboard-funds.js) ──────────────────────────────

const LOOKTHROUGH_COL_DEFAULTS = {
    holding: 220, my_ils: 130, pct: 100, type: 140, funds: 190,
    country: 100, sector: 140, currency: 80,
};

function getLookthroughColWidths() {
    try { return Object.assign({}, LOOKTHROUGH_COL_DEFAULTS, JSON.parse(localStorage.getItem('lookthroughColWidths'))); }
    catch { return Object.assign({}, LOOKTHROUGH_COL_DEFAULTS); }
}

function saveLookthroughColWidths(w) { localStorage.setItem('lookthroughColWidths', JSON.stringify(w)); }

function initLookthroughResize() {
    const table = document.querySelector('#lookthroughSecuritiesTableWrap table');
    if (!table) return;
    const handles = table.querySelectorAll('.col-resize-handle');
    handles.forEach((handle, i) => {
        handle.addEventListener('mousedown', e => {
            e.preventDefault();
            e.stopPropagation();
            const col = table.querySelectorAll('col')[i];
            const startX = e.clientX;
            const startW = parseInt(col.style.width);
            handle.classList.add('resizing');
            const onMove = ev => {
                const newW = Math.max(50, startW + ev.clientX - startX);
                col.style.width = newW + 'px';
            };
            const onUp = () => {
                handle.classList.remove('resizing');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                const keys = Object.keys(LOOKTHROUGH_COL_DEFAULTS);
                const cols = table.querySelectorAll('col');
                const saved = {};
                keys.forEach((k, j) => { saved[k] = parseInt(cols[j].style.width); });
                saveLookthroughColWidths(saved);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    });
}

const LOOKTHROUGH_RESIZE_HANDLE = '<div class="col-resize-handle" onclick="event.stopPropagation()"></div>';

let lookthroughSortCol = 'my_ils';
let lookthroughSortDir = -1;
let lookthroughFilter = { search: '', type: 'all', fund: 'all' };

const LOOKTHROUGH_SORT_ACCESSORS = {
    holding: s => (s.security_name || s.issuer_name || '').toLowerCase(),
    my_ils: s => s.combined_value,
    pct: s => s.pct_of_total,
    type: s => INSTRUMENT_TYPE_LABELS[s.instrument_type] || s.instrument_type || '',
    country: s => s.country || '',
    sector: s => s.sector || '',
    currency: s => s.currency || '',
};

function lookthroughTh(col, label) {
    const active = col === lookthroughSortCol;
    const arrow = active ? (lookthroughSortDir === 1 ? ' ▲' : ' ▼') : ' ↕';
    return `<th onclick="sortLookthroughColumn('${col}')" style="cursor:pointer;white-space:nowrap;">${escapeHtml(label)}<span style="opacity:${active ? 1 : 0.35};font-size:0.75em;">${arrow}</span>${LOOKTHROUGH_RESIZE_HANDLE}</th>`;
}

function sortLookthroughColumn(col) {
    if (lookthroughSortCol === col) {
        lookthroughSortDir *= -1;
    } else {
        lookthroughSortCol = col;
        lookthroughSortDir = col === 'holding' ? 1 : -1;
    }
    renderLookthroughView();
}

function sortSecuritiesRows(rows) {
    const acc = LOOKTHROUGH_SORT_ACCESSORS[lookthroughSortCol];
    if (!acc) return rows;
    return [...rows].sort((a, b) => {
        const va = acc(a), vb = acc(b);
        const aEmpty = va === '' || va === null || va === undefined;
        const bEmpty = vb === '' || vb === null || vb === undefined;
        if (aEmpty && bEmpty) return 0;
        if (aEmpty) return 1;   // blanks/unset always sort last, both directions
        if (bEmpty) return -1;
        if (typeof va === 'number') return lookthroughSortDir * (va - vb);
        return lookthroughSortDir * String(va).localeCompare(String(vb), 'he');
    });
}

function filterSecuritiesRows(rows) {
    const { search, type, fund } = lookthroughFilter;
    return rows.filter(s => {
        if (search) {
            const hay = `${s.security_name || ''} ${s.issuer_name || ''}`.toLowerCase();
            if (!hay.includes(search.toLowerCase())) return false;
        }
        if (type !== 'all' && s.instrument_type !== type) return false;
        if (fund === 'direct') {
            if (!s.direct_value) return false;
        } else if (fund !== 'all') {
            if (!s.by_fund || !(fund in s.by_fund)) return false;
        }
        return true;
    });
}

// ── Views ────────────────────────────────────────────────────────────────

function setLookthroughView(view) {
    lookthroughView = view;
    document.querySelectorAll('#lookthroughViewPicker .year-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.view === view));
    renderLookthroughView();
}

async function renderLookthroughView() {
    const body = document.getElementById('lookthroughViewBody');
    body.innerHTML = '<p class="no-data">Loading…</p>';

    if (lookthroughView === 'securities') {
        const data = await fetch('/api/lookthrough/securities').then(r => r.json());
        body.innerHTML = renderSecuritiesTable(data);
        initLookthroughResize();
    } else if (lookthroughView === 'overlap') {
        const data = await fetch('/api/lookthrough/overlap').then(r => r.json());
        body.innerHTML = data.securities.length
            ? renderSecuritiesTable(data, { showOverlapCols: true })
            : '<p class="no-data">No security is currently held in more than one fund.</p>';
        initLookthroughResize();
    } else if (lookthroughView === 'concentration') {
        const data = await fetch('/api/lookthrough/concentration').then(r => r.json());
        body.innerHTML = renderConcentrationView(data);
    } else if (lookthroughView === 'merged') {
        const data = await fetch('/api/lookthrough/merged').then(r => r.json());
        body.innerHTML = renderDirectBreakdownView(data);
    }
}

function renderSecuritiesTable(data, { showOverlapCols = false } = {}) {
    const funds = data.active_funds;
    const allRows = data.securities;
    if (!allRows.length) {
        return '<p class="no-data">No look-through holdings yet — import a filing above, and make sure at least one fund has a Track # and Institution Reg # set (Manage Funds table).</p>';
    }

    const typeOptions = [...new Set(data.securities.map(s => s.instrument_type).filter(Boolean))]
        .sort((a, b) => (INSTRUMENT_TYPE_LABELS[a] || a).localeCompare(INSTRUMENT_TYPE_LABELS[b] || b));
    const filterBar = `
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px;">
            <input type="text" id="lookthroughSearchInput" placeholder="Search issuer/security…" value="${escapeHtml(lookthroughFilter.search)}"
                oninput="lookthroughFilter.search=this.value; renderLookthroughView();"
                style="height:32px;padding:0 10px;border:1px solid var(--input-border);border-radius:8px;background:var(--input-bg);color:var(--text-primary);font-size:0.85em;width:200px;">
            <select onchange="lookthroughFilter.type=this.value; renderLookthroughView();"
                style="height:32px;padding:0 8px;border:1px solid var(--input-border);border-radius:8px;background:var(--input-bg);color:var(--text-primary);font-size:0.85em;">
                <option value="all">All Types</option>
                ${typeOptions.map(t => `<option value="${t}" ${lookthroughFilter.type === t ? 'selected' : ''}>${escapeHtml(INSTRUMENT_TYPE_LABELS[t] || t)}</option>`).join('')}
            </select>
            <select onchange="lookthroughFilter.fund=this.value; renderLookthroughView();"
                style="height:32px;padding:0 8px;border:1px solid var(--input-border);border-radius:8px;background:var(--input-bg);color:var(--text-primary);font-size:0.85em;">
                <option value="all">All Funds/Direct</option>
                ${funds.map(f => `<option value="${f.id}" ${lookthroughFilter.fund === String(f.id) ? 'selected' : ''}>${escapeHtml(fundLabel(f))}</option>`).join('')}
                <option value="direct" ${lookthroughFilter.fund === 'direct' ? 'selected' : ''}>Direct only</option>
            </select>
        </div>
    `;

    let rows = filterSecuritiesRows(allRows);
    rows = sortSecuritiesRows(rows);
    if (!rows.length) {
        return filterBar + '<p class="no-data">No securities match this filter.</p>';
    }

    const w = getLookthroughColWidths();
    const overlapCol = showOverlapCols ? '<col style="width:120px;">' : '';
    const overlapTh = showOverlapCols ? `<th style="white-space:nowrap;">Max Single Fund${LOOKTHROUGH_RESIZE_HANDLE}</th>` : '';

    const bodyRows = rows.map(s => {
        const holdingName = s.security_name || s.issuer_name || '—';
        const issuerSub = (s.issuer_name && s.issuer_name !== holdingName)
            ? `<br><span style="font-weight:400;font-size:0.78em;color:var(--text-secondary);">${escapeHtml(s.issuer_name)}</span>` : '';
        const conflictTitle = s.classification_conflict
            ? `title="Varies across contributing funds: ${escapeHtml([...s.sector_values, ...s.country_values, ...s.currency_values].join(', '))}"`
            : '';
        const unbalancedWarn = s.has_unbalanced_fund
            ? ' <span class="stock-warn" title="At least one contributing fund has no recorded balance yet — its share is counted as 0 until you add one.">⚠</span>'
            : '';

        const contributorNames = [];
        const contributorDetails = [];
        funds.forEach(f => {
            if (s.by_fund && s.by_fund[f.id]) {
                contributorNames.push(fundLabel(f));
                contributorDetails.push(`${fundLabel(f)}: ${formatCurrency(s.by_fund[f.id])}`);
            }
        });
        if (s.direct_value) {
            contributorNames.push('Direct');
            contributorDetails.push(`Direct: ${formatCurrency(s.direct_value)}`);
        }

        const overlapCell = showOverlapCols
            ? `<td class="amount-cell">${s.max_single_fund_share !== null && s.max_single_fund_share !== undefined ? (s.max_single_fund_share * 100).toFixed(1) + '%' : '—'}</td>`
            : '';

        return `
            <tr>
                <td>${escapeHtml(holdingName)}${issuerSub}${s.classification_conflict ? ` <span class="stock-warn" ${conflictTitle}>⚠</span>` : ''}</td>
                <td class="amount-cell">${formatCurrency(s.combined_value)}${unbalancedWarn}</td>
                <td class="amount-cell">${(s.pct_of_total * 100).toFixed(2)}%</td>
                <td>${s.instrument_type ? escapeHtml(INSTRUMENT_TYPE_LABELS[s.instrument_type] || s.instrument_type) : '—'}</td>
                <td title="${escapeHtml(contributorDetails.join('; '))}">${escapeHtml(contributorNames.join(', ') || '—')}</td>
                <td>${escapeHtml(s.country || '—')}</td>
                <td>${escapeHtml(s.sector || '—')}</td>
                <td>${escapeHtml(s.currency || '—')}</td>
                ${overlapCell}
            </tr>
        `;
    }).join('');

    return filterBar + `
        <div id="lookthroughSecuritiesTableWrap" style="overflow-x:auto;">
            <table class="transactions-table" style="table-layout:fixed;width:100%;">
                <colgroup>
                    <col style="width:${w.holding}px;">
                    <col style="width:${w.my_ils}px;">
                    <col style="width:${w.pct}px;">
                    <col style="width:${w.type}px;">
                    <col style="width:${w.funds}px;">
                    <col style="width:${w.country}px;">
                    <col style="width:${w.sector}px;">
                    <col style="width:${w.currency}px;">
                    ${overlapCol}
                </colgroup>
                <thead><tr>
                    ${lookthroughTh('holding', 'Holding')}
                    ${lookthroughTh('my_ils', 'My ILS (Invested)')}
                    ${lookthroughTh('pct', '% of Invested')}
                    ${lookthroughTh('type', 'Type')}
                    <th style="white-space:nowrap;">Funds/Positions${LOOKTHROUGH_RESIZE_HANDLE}</th>
                    ${lookthroughTh('country', 'Country')}
                    ${lookthroughTh('sector', 'Sector')}
                    ${lookthroughTh('currency', 'Currency')}
                    ${overlapTh}
                </tr></thead>
                <tbody>${bodyRows}</tbody>
            </table>
        </div>
    `;
}

function renderRollupTable(title, rows) {
    if (!rows.length) return '';
    const body = rows.map(r => `
        <tr>
            <td>${escapeHtml(r.label)}</td>
            <td class="amount-cell">${formatCurrency(r.value)}</td>
            <td class="amount-cell">${(r.pct_of_portfolio * 100).toFixed(1)}%</td>
            <td class="amount-cell">${r.pct_of_named !== null ? (r.pct_of_named * 100).toFixed(1) + '%' : '—'}</td>
        </tr>
    `).join('');
    return `
        <h4 style="margin:20px 0 8px;">${escapeHtml(title)}</h4>
        <div style="overflow-x:auto;">
            <table class="transactions-table">
                <thead><tr><th>Category</th><th>Value</th><th>% of Portfolio</th><th>% of Named</th></tr></thead>
                <tbody>${body}</tbody>
            </table>
        </div>
    `;
}

function renderConcentrationView(data) {
    if (!data.total_portfolio) {
        return '<p class="no-data">No look-through holdings yet — import a filing above.</p>';
    }
    const crossType = data.same_issuer_cross_type.length ? `
        <h4 style="margin:20px 0 8px;">Same Issuer, Multiple Instrument Types</h4>
        <p style="color:var(--text-secondary);font-size:0.85em;margin:0 0 8px;">
            Exposure to the same issuer summed across instrument types — e.g. a bank's stock plus that
            bank's bonds, counted as one counterparty exposure, broken down by how much sits in each type.
        </p>
        <div style="overflow-x:auto;">
            <table class="transactions-table">
                <thead><tr><th>Issuer</th><th>Combined Value</th><th>Breakdown by Type</th><th>Funds</th></tr></thead>
                <tbody>${data.same_issuer_cross_type.map(g => `
                    <tr>
                        <td>${escapeHtml(g.issuer_name || g.issuer_number || '—')}</td>
                        <td class="amount-cell">${formatCurrency(g.combined_value)}</td>
                        <td>${Object.entries(g.type_breakdown)
                            .sort((a, b) => b[1] - a[1])
                            .map(([t, v]) => `${escapeHtml(INSTRUMENT_TYPE_LABELS[t] || t)}: ${formatCurrency(v)}`)
                            .join(', ')}</td>
                        <td class="amount-cell">${g.fund_count}</td>
                    </tr>
                `).join('')}</tbody>
            </table>
        </div>` : '';

    return `
        <p style="color:var(--text-secondary);font-size:0.9em;margin:0 0 8px;">Total look-through value: ${formatCurrency(data.total_portfolio)}</p>
        ${renderRollupTable('By Sector', data.by_sector)}
        ${renderRollupTable('By Country', data.by_country)}
        ${renderRollupTable('By Currency', data.by_currency)}
        ${crossType}
    `;
}

function renderDirectBreakdownView(data) {
    if (!data.breakdown.length && !data.unmatched_direct.length) {
        return '<p class="no-data">No direct stock holdings yet.</p>';
    }
    const funds = data.active_funds || [];
    const rows = data.breakdown.map(e => {
        const contributorDetails = funds
            .filter(f => e.by_fund && e.by_fund[f.id])
            .map(f => `${fundLabel(f)}: ${formatCurrency(e.by_fund[f.id])}`);
        const contributorNames = funds
            .filter(f => e.by_fund && e.by_fund[f.id])
            .map(f => fundLabel(f));
        return `
            <tr>
                <td>${escapeHtml(e.symbol)}</td>
                <td class="amount-cell">${formatCurrency(e.direct_value)}</td>
                <td class="amount-cell">${formatCurrency(e.indirect_value)}</td>
                <td title="${escapeHtml(contributorDetails.join('; '))}">${escapeHtml(contributorNames.join(', ') || (e.indirect_value ? '—' : 'None'))}</td>
            </tr>
        `;
    }).join('');
    const unmatchedRows = data.unmatched_direct.map(u => `
        <tr>
            <td>${escapeHtml(u.symbol)}</td>
            <td class="amount-cell">${formatCurrency(u.value)}</td>
            <td><span class="stock-warn" title="Set an ISIN on this holding (Manage Stock Holdings table, Long-Term Funds tab) to include it in this breakdown.">⚠ Needs ISIN</span></td>
        </tr>
    `).join('');

    return `
        <p style="color:var(--text-secondary);font-size:0.85em;margin:0 0 8px;">
            What you hold directly, and how much of that same security also shows up inside your funds —
            a 0 there is a real answer, not missing data.
        </p>
        <div style="overflow-x:auto;">
            <table class="transactions-table">
                <thead><tr><th>Symbol</th><th>Held Directly</th><th>Also Held Via Funds</th><th>Which Fund(s)</th></tr></thead>
                <tbody>${rows || '<tr><td colspan="4" class="no-data">No direct holdings with an ISIN yet.</td></tr>'}</tbody>
            </table>
        </div>
        ${data.unmatched_direct.length ? `
        <h4 style="margin:20px 0 8px;">Direct Holdings Without an ISIN</h4>
        <div style="overflow-x:auto;">
            <table class="transactions-table">
                <thead><tr><th>Symbol</th><th>Value</th><th></th></tr></thead>
                <tbody>${unmatchedRows}</tbody>
            </table>
        </div>` : ''}
    `;
}

// ── Entry point ──────────────────────────────────────────────────────────

async function loadLookThroughPanel() {
    await loadHoldingsFilings();
    await renderLookthroughView();
}
