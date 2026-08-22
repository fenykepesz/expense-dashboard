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

// Last-fetched payload per view, keyed by view name — lets sort/filter/
// expand-collapse re-render instantly from what's already on the page
// instead of re-fetching and flashing "Loading…" on every click. Only
// actions that actually change server-side data (import, delete a filing)
// should clear this and force a real refetch.
let lookthroughViewCache = {};

// Two of the user's own funds can share an identical display name (a real
// case: two tracks under one savings policy, same Fund Name/Fund #) — this
// keeps every place a fund is named in this file distinguishable.
function fundLabel(f) {
    return f.track_number ? `${f.name} (Track ${f.track_number})` : f.name;
}

// Two-line column header for the per-fund breakdown columns — company name
// (short, e.g. "Menora"/"Phoenix") on top, Track # underneath, since two of
// the user's own funds can share an identical Fund Name but never a Track #.
function fundColumnHeader(f) {
    const company = f.company_name || f.name;
    const track = f.track_number ? `<br><span style="font-weight:400;font-size:0.78em;color:var(--text-secondary);">${escapeHtml(f.track_number)}</span>` : '';
    return `${escapeHtml(company)}${track}`;
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
    lookthroughViewCache = {};  // deleted filing can change every view's numbers
    await renderLookthroughView();
}

// ── Securities table: resizable + sortable + filterable, same pattern as
// the Manage Funds table (dashboard-funds.js) ──────────────────────────────

// Per-fund/Direct columns are dynamic (their count depends on how many
// funds are active) and rendered with a fixed width, not tracked here or
// individually resizable — only these fixed columns persist a resized width.
const LOOKTHROUGH_COL_DEFAULTS = {
    holding: 220, my_ils: 130, pct: 100, type: 140,
    country: 100, sector: 140, currency: 80,
};
const LOOKTHROUGH_FUND_COL_WIDTH = 120;

function getLookthroughColWidths() {
    try { return Object.assign({}, LOOKTHROUGH_COL_DEFAULTS, JSON.parse(localStorage.getItem('lookthroughColWidths'))); }
    catch { return Object.assign({}, LOOKTHROUGH_COL_DEFAULTS); }
}

function saveLookthroughColWidths(w) { localStorage.setItem('lookthroughColWidths', JSON.stringify(w)); }

// Fund/Direct columns sit BETWEEN the fixed ones (Type and Country) and
// their count varies by how many funds are active, so a handle's position
// among all handles no longer lines up with its <col>'s position among all
// <col>s. Each handle instead carries its own target col-index (data-col-
// index) and, for fixed columns only, which LOOKTHROUGH_COL_DEFAULTS key to
// persist under (data-col-key) — dynamic columns get a handle with no key,
// so they resize within the session but aren't saved (their set changes
// too often across imports to make a saved width meaningful).
function initLookthroughResize() {
    const table = document.querySelector('#lookthroughSecuritiesTableWrap table');
    if (!table) return;
    const cols = table.querySelectorAll('col');
    const handles = table.querySelectorAll('.col-resize-handle');
    handles.forEach(handle => {
        const idx = parseInt(handle.dataset.colIndex, 10);
        const key = handle.dataset.colKey || null;
        handle.addEventListener('mousedown', e => {
            e.preventDefault();
            e.stopPropagation();
            const col = cols[idx];
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
                if (key) {
                    const widths = getLookthroughColWidths();
                    widths[key] = parseInt(col.style.width);
                    saveLookthroughColWidths(widths);
                }
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    });
}

function resizeHandle(colIndex, colKey = '') {
    const keyAttr = colKey ? ` data-col-key="${colKey}"` : '';
    return `<div class="col-resize-handle" data-col-index="${colIndex}"${keyAttr} onclick="event.stopPropagation()"></div>`;
}

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

const LOOKTHROUGH_COLUMN_TOOLTIPS = {
    holding: "The security's name — or the issuer's name for holdings without a separate security identity (cash, loans, deposits). The issuer shows as a sub-line whenever it adds information beyond the holding name.",
    my_ils: "Your personal ILS exposure to this holding — direct stock holdings and fund-derived exposure combined. Fund-derived exposure is your own recorded balance in that fund, weighted by this holding's share of the fund's total.",
    pct: "This holding's share of everything you personally hold here — direct and fund-derived combined.",
    type: 'The kind of instrument. Derivative/hedging types (options, futures, swaps) are grouped as "Derivatives & Hedging" in the Concentration pie chart, but shown individually here.',
    country: "Country of economic exposure, as reported by the filing. Blank if the filing never reports it for this instrument type (common for cash) — a ⚠ appears if your funds reported it inconsistently for the same holding.",
    sector: "Industry sector, as reported by the filing. Blank if never reported for this instrument type — a ⚠ appears if your funds reported it inconsistently for the same holding.",
    currency: "The holding's currency, as reported by the filing. Blank if never reported, or if it's genuinely a mix (e.g. one bank cash row spanning several currencies) — hover the ⚠ next to the holding name to see what was found.",
};

function lookthroughTh(col, label, colIndex) {
    const active = col === lookthroughSortCol;
    const arrow = active ? (lookthroughSortDir === 1 ? ' ▲' : ' ▼') : ' ↕';
    const tooltip = LOOKTHROUGH_COLUMN_TOOLTIPS[col] ? thTooltip(LOOKTHROUGH_COLUMN_TOOLTIPS[col]) : '';
    return `<th onclick="sortLookthroughColumn('${col}')" style="cursor:pointer;white-space:nowrap;">${escapeHtml(label)}${tooltip}<span style="opacity:${active ? 1 : 0.35};font-size:0.75em;">${arrow}</span>${resizeHandle(colIndex, col)}</th>`;
}

function sortLookthroughColumn(col) {
    if (lookthroughSortCol === col) {
        lookthroughSortDir *= -1;
    } else {
        lookthroughSortCol = col;
        lookthroughSortDir = col === 'holding' ? 1 : -1;
    }
    rerenderLookthroughView();
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

const LOOKTHROUGH_VIEW_ENDPOINTS = {
    securities: '/api/lookthrough/securities',
    overlap: '/api/lookthrough/overlap',
    concentration: '/api/lookthrough/concentration',
    merged: '/api/lookthrough/merged',
};

// Fetches the current view's data fresh from the server, caches it, then
// renders. Use this after anything that actually changes server-side data
// (import, delete a filing) or on first load / view switch — NOT for pure
// UI-state changes (sort, filter, expand/collapse), which should call
// rerenderLookthroughView() instead so they don't refetch or flash "Loading…".
async function renderLookthroughView() {
    const body = document.getElementById('lookthroughViewBody');
    body.innerHTML = '<p class="no-data">Loading…</p>';
    const data = await fetch(LOOKTHROUGH_VIEW_ENDPOINTS[lookthroughView]).then(r => r.json());
    lookthroughViewCache[lookthroughView] = data;
    renderLookthroughViewFromCache();
}

// Re-renders the current view from whatever's already cached — no network
// round-trip, no "Loading…" flash. Falls back to a real fetch only if
// nothing has been loaded for this view yet.
function rerenderLookthroughView() {
    if (!lookthroughViewCache[lookthroughView]) {
        renderLookthroughView();
        return;
    }
    renderLookthroughViewFromCache();
}

function renderLookthroughViewFromCache() {
    const body = document.getElementById('lookthroughViewBody');
    const data = lookthroughViewCache[lookthroughView];

    if (lookthroughView === 'securities') {
        body.innerHTML = renderSecuritiesTable(data);
        initLookthroughResize();
    } else if (lookthroughView === 'overlap') {
        body.innerHTML = data.securities.length
            ? renderSecuritiesTable(data, { showOverlapCols: true })
            : '<p class="no-data">No security is currently held in more than one fund.</p>';
        initLookthroughResize();
    } else if (lookthroughView === 'concentration') {
        body.innerHTML = renderConcentrationView(data);
    } else if (lookthroughView === 'merged') {
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
                oninput="lookthroughFilter.search=this.value; rerenderLookthroughView();"
                style="height:32px;padding:0 10px;border:1px solid var(--input-border);border-radius:8px;background:var(--input-bg);color:var(--text-primary);font-size:0.85em;width:200px;">
            <select onchange="lookthroughFilter.type=this.value; rerenderLookthroughView();"
                style="height:32px;padding:0 8px;border:1px solid var(--input-border);border-radius:8px;background:var(--input-bg);color:var(--text-primary);font-size:0.85em;">
                <option value="all">All Types</option>
                ${typeOptions.map(t => `<option value="${t}" ${lookthroughFilter.type === t ? 'selected' : ''}>${escapeHtml(INSTRUMENT_TYPE_LABELS[t] || t)}</option>`).join('')}
            </select>
            <span style="font-size:0.85em;color:var(--text-secondary);">Held in:</span>
            <select onchange="lookthroughFilter.fund=this.value; rerenderLookthroughView();"
                style="height:32px;padding:0 8px;border:1px solid var(--input-border);border-radius:8px;background:var(--input-bg);color:var(--text-primary);font-size:0.85em;">
                <option value="all">Any fund/position</option>
                ${funds.map(f => `<option value="${f.id}" ${lookthroughFilter.fund === String(f.id) ? 'selected' : ''}>${escapeHtml(fundLabel(f))}</option>`).join('')}
                <option value="direct" ${lookthroughFilter.fund === 'direct' ? 'selected' : ''}>Direct holding</option>
            </select>
            ${thTooltip('This only narrows which rows are shown, to ones this fund/position holds. It doesn\'t change the numbers — My ILS, %, and every fund column still reflect everything you own, not just this selection.')}
        </div>
    `;

    let rows = filterSecuritiesRows(allRows);
    rows = sortSecuritiesRows(rows);
    if (!rows.length) {
        return filterBar + '<p class="no-data">No securities match this filter.</p>';
    }

    // Direct is its own column only when at least one row actually has a
    // direct value — checked against the full unfiltered set so the column
    // doesn't appear/disappear as filters change.
    const hasDirect = allRows.some(s => s.direct_value);

    const w = getLookthroughColWidths();

    // Column layout, in render order, so col-index bookkeeping (needed for
    // resize) stays correct regardless of how many funds are active:
    // Holding, My ILS, % of Invested, Type, [one column per fund],
    // [Direct, if any], Country, Sector, Currency, [Max Single Fund].
    let i = 0;
    const cols = [];
    const heads = [];

    cols.push(`<col style="width:${w.holding}px;">`); heads.push(lookthroughTh('holding', 'Holding', i++));
    cols.push(`<col style="width:${w.my_ils}px;">`); heads.push(lookthroughTh('my_ils', 'My ILS (Invested)', i++));
    cols.push(`<col style="width:${w.pct}px;">`); heads.push(lookthroughTh('pct', '% of Invested', i++));
    cols.push(`<col style="width:${w.type}px;">`); heads.push(lookthroughTh('type', 'Type', i++));
    funds.forEach(f => {
        cols.push(`<col style="width:${LOOKTHROUGH_FUND_COL_WIDTH}px;">`);
        const fundTooltip = thTooltip(`This holding's value inside ${fundLabel(f)} — your recorded balance in this fund, weighted by the holding's share of the fund's total.`);
        heads.push(`<th style="white-space:nowrap;">${fundColumnHeader(f)}${fundTooltip}${resizeHandle(i++)}</th>`);
    });
    if (hasDirect) {
        cols.push(`<col style="width:${LOOKTHROUGH_FUND_COL_WIDTH}px;">`);
        const directTooltip = thTooltip('This holding\'s value from your directly-held stock positions (Manage Stock Holdings), matched by ISIN.');
        heads.push(`<th style="white-space:nowrap;">Direct${directTooltip}${resizeHandle(i++)}</th>`);
    }
    cols.push(`<col style="width:${w.country}px;">`); heads.push(lookthroughTh('country', 'Country', i++));
    cols.push(`<col style="width:${w.sector}px;">`); heads.push(lookthroughTh('sector', 'Sector', i++));
    cols.push(`<col style="width:${w.currency}px;">`); heads.push(lookthroughTh('currency', 'Currency', i++));
    if (showOverlapCols) {
        cols.push('<col style="width:120px;">');
        const overlapTooltip = thTooltip("The largest single fund's share of this holding's combined value — how concentrated it is in one place versus spread across your funds.");
        heads.push(`<th style="white-space:nowrap;">Max Single Fund${overlapTooltip}${resizeHandle(i++)}</th>`);
    }

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

        const fundCells = funds.map(f => {
            const v = s.by_fund && s.by_fund[f.id];
            return `<td class="amount-cell">${v ? formatCurrency(v) : '—'}</td>`;
        }).join('');
        const directCell = hasDirect
            ? `<td class="amount-cell">${s.direct_value ? formatCurrency(s.direct_value) : '—'}</td>` : '';

        const overlapCell = showOverlapCols
            ? `<td class="amount-cell">${s.max_single_fund_share !== null && s.max_single_fund_share !== undefined ? (s.max_single_fund_share * 100).toFixed(1) + '%' : '—'}</td>`
            : '';

        return `
            <tr>
                <td>${escapeHtml(holdingName)}${issuerSub}${s.classification_conflict ? ` <span class="stock-warn" ${conflictTitle}>⚠</span>` : ''}</td>
                <td class="amount-cell">${formatCurrency(s.combined_value)}${unbalancedWarn}</td>
                <td class="amount-cell">${(s.pct_of_total * 100).toFixed(2)}%</td>
                <td>${s.instrument_type ? escapeHtml(INSTRUMENT_TYPE_LABELS[s.instrument_type] || s.instrument_type) : '—'}</td>
                ${fundCells}
                ${directCell}
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
                <colgroup>${cols.join('')}</colgroup>
                <thead><tr>${heads.join('')}</tr></thead>
                <tbody>${bodyRows}</tbody>
            </table>
        </div>
    `;
}

// Per-section top-10/show-all state — a plain object keyed by rollup field,
// re-rendered (not toggled via CSS) on click same as every other filter in
// this file, so it survives a full renderLookthroughView() refresh.
let lookthroughCategoryExpanded = { type: false, sector: false, country: false, currency: false };

function toggleCategoryExpand(key) {
    lookthroughCategoryExpanded[key] = !lookthroughCategoryExpanded[key];
    rerenderLookthroughView();
}

// Whole-section collapse (Type/Sector/Country/Currency/cross-type table down to
// just its header) — separate from the top-10 toggle above, tracked as a Set
// since most sections start expanded and only a few get collapsed.
let lookthroughSectionCollapsed = new Set();

function toggleSection(key) {
    if (lookthroughSectionCollapsed.has(key)) lookthroughSectionCollapsed.delete(key);
    else lookthroughSectionCollapsed.add(key);
    rerenderLookthroughView();
}

function renderSectionHeader(key, title) {
    const collapsed = lookthroughSectionCollapsed.has(key);
    const icon = collapsed ? '▸' : '▾';
    return `<h4 style="margin:20px 0 4px;cursor:pointer;user-select:none;" onclick="toggleSection('${key}')">
        <span style="display:inline-block;width:1em;color:var(--text-secondary);">${icon}</span>${escapeHtml(title)}
    </h4>`;
}

// Which merged rows (Equity Exposure, Fixed Income Exposure, Derivatives &
// Hedging) currently have their sub-type breakdown expanded — keyed by
// "tableKey:label" so Sector/Type/etc. never collide with each other.
let lookthroughBreakdownExpanded = new Set();

function toggleTypeBreakdown(id) {
    if (lookthroughBreakdownExpanded.has(id)) lookthroughBreakdownExpanded.delete(id);
    else lookthroughBreakdownExpanded.add(id);
    rerenderLookthroughView();
}

// Fund cells + Direct cell for one row (parent or sub-row) — shared so a
// sub-type's own row reads exactly like its parent's, just for its own slice.
function renderCategoryCells(entry, funds, fundTotals, directTotal, hasDirect) {
    const fundCells = funds.map(f => {
        const amt = (entry.by_fund && entry.by_fund[f.id]) || 0;
        if (!amt) return '<td class="amount-cell">—</td>';
        const total = fundTotals[f.id];
        const pct = total ? (amt / total * 100).toFixed(1) : '0.0';
        return `<td class="amount-cell">${formatCurrency(amt)}<br><span style="font-size:0.78em;color:var(--text-secondary);">${pct}% of fund</span></td>`;
    }).join('');
    const directCell = hasDirect
        ? (entry.direct
            ? `<td class="amount-cell">${formatCurrency(entry.direct)}<br><span style="font-size:0.78em;color:var(--text-secondary);">${(entry.direct / directTotal * 100).toFixed(1)}% of direct</span></td>`
            : '<td class="amount-cell">—</td>')
        : '';
    return { fundCells, directCell };
}

// Category | Your ILS | Total % | one column per fund (₪ + % of THAT fund's
// own total in this category) | Direct — replaces the old dual-denominator
// (% of Portfolio / % of Named) table, which the user found confusing once
// they actually had real data to look at. Top 10 rows shown by default
// (rows are already sorted by value server-side), with a toggle to see
// the rest — nothing is summed away into an "Other" bucket the way the
// pie charts do, every category stays individually inspectable. A merged
// row (Equity Exposure etc.) gets a clickable +/- to expand into its own
// sub-type rows (Stock/ETF/Mutual Fund), each with its own full breakdown
// — collapsed by default so the table isn't cluttered until asked for.
function renderCategoryTable(key, title, rows, data) {
    if (!rows.length) return '';
    if (lookthroughSectionCollapsed.has(key)) return renderSectionHeader(key, title);
    const funds = data.active_funds || [];
    const fundTotals = data.fund_totals || {};
    const directTotal = data.direct_total || 0;
    const hasDirect = directTotal > 0;

    const TOP_N = 10;
    const expanded = lookthroughCategoryExpanded[key];
    const visibleRows = expanded ? rows : rows.slice(0, TOP_N);

    const fundHeaders = funds.map(f => `<th style="white-space:nowrap;">${fundColumnHeader(f)}</th>`).join('');
    const directHeader = hasDirect ? '<th>Direct</th>' : '';

    const body = visibleRows.map(r => {
        const { fundCells, directCell } = renderCategoryCells(r, funds, fundTotals, directTotal, hasDirect);

        const breakdownEntries = r.type_breakdown ? Object.entries(r.type_breakdown) : [];
        const hasBreakdown = breakdownEntries.length > 1;
        const breakdownId = `${key}:${r.label}`;
        const isBreakdownOpen = hasBreakdown && lookthroughBreakdownExpanded.has(breakdownId);
        const toggleIcon = hasBreakdown
            ? `<span onclick="toggleTypeBreakdown('${breakdownId.replace(/'/g, "\\'")}')" style="cursor:pointer;display:inline-block;width:1.1em;color:var(--text-secondary);user-select:none;">${isBreakdownOpen ? '−' : '+'}</span> `
            : '<span style="display:inline-block;width:1.1em;"></span> ';

        const parentRow = `
            <tr>
                <td>${toggleIcon}${escapeHtml(r.label)}</td>
                <td class="amount-cell">${formatCurrency(r.value)}</td>
                <td class="amount-cell">${(r.pct_of_portfolio * 100).toFixed(1)}%</td>
                ${fundCells}
                ${directCell}
            </tr>
        `;

        const subRows = isBreakdownOpen
            ? breakdownEntries
                .sort((a, b) => b[1].value - a[1].value)
                .map(([t, sub]) => {
                    const cells = renderCategoryCells(sub, funds, fundTotals, directTotal, hasDirect);
                    return `
                        <tr style="background:var(--table-header-bg);">
                            <td style="padding-left:2.2em;color:var(--text-secondary);">${escapeHtml(INSTRUMENT_TYPE_LABELS[t] || t)}</td>
                            <td class="amount-cell">${formatCurrency(sub.value)}</td>
                            <td class="amount-cell">${(sub.pct_of_portfolio * 100).toFixed(1)}%</td>
                            ${cells.fundCells}
                            ${cells.directCell}
                        </tr>
                    `;
                }).join('')
            : '';

        return parentRow + subRows;
    }).join('');

    const toggle = rows.length > TOP_N
        ? `<button class="btn-excl" style="margin-top:8px;" onclick="toggleCategoryExpand('${key}')">${expanded ? `Show top ${TOP_N} only` : `Show all ${rows.length}`}</button>`
        : '';

    return `
        ${renderSectionHeader(key, title)}
        <p style="color:var(--text-secondary);font-size:0.78em;margin:0 0 8px;">
            Your ILS / Total % are your personal value and its share of your whole portfolio.
            Each fund column shows that fund's ₪ amount here and what % of THAT fund's own total
            it represents — e.g. "₪200 (15% of fund)" means Energy is 15% of that one fund, not
            of everything you own.
        </p>
        <div style="overflow-x:auto;">
            <table class="transactions-table">
                <thead><tr>
                    <th>Category</th><th>Your ILS</th><th>Total %</th>
                    ${fundHeaders}
                    ${directHeader}
                </tr></thead>
                <tbody>${body}</tbody>
            </table>
        </div>
        ${toggle}
    `;
}

function renderConcentrationView(data) {
    if (!data.total_portfolio) {
        return '<p class="no-data">No look-through holdings yet — import a filing above.</p>';
    }
    const crossTypeCollapsed = lookthroughSectionCollapsed.has('crossType');
    const crossType = data.same_issuer_cross_type.length ? (
        crossTypeCollapsed
            ? renderSectionHeader('crossType', 'Same Issuer, Multiple Instrument Types')
            : `
        ${renderSectionHeader('crossType', 'Same Issuer, Multiple Instrument Types')}
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
        </div>`
    ) : '';

    return `
        <p style="color:var(--text-secondary);font-size:0.9em;margin:0 0 8px;">Total look-through value: ${formatCurrency(data.total_portfolio)}</p>
        ${renderCategoryTable('type', 'By Type', data.by_type.map(r => ({ ...r, label: INSTRUMENT_TYPE_LABELS[r.label] || r.label })), data)}
        ${renderCategoryTable('sector', 'By Sector', data.by_sector, data)}
        ${renderCategoryTable('country', 'By Country', data.by_country, data)}
        ${renderCategoryTable('currency', 'By Currency', data.by_currency, data)}
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
    lookthroughViewCache = {};  // tab (re)opened or a filing was just imported — nothing cached is trustworthy
    await loadHoldingsFilings();
    await renderLookthroughView();
}
