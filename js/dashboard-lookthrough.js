// Look-Through tab: security-level holdings aggregation across every fund
// that's been matched to an institution's regulatory holdings filing (see
// tools/holdings_filing_to_json.py) — plus a merge with directly-held
// stock_holdings. Views are read-only aggregation snapshots computed
// server-side (db.py's get_security_holdings/get_overlap_holdings/
// get_concentration_rollups/get_merged_direct_indirect) — this file only
// renders them and drives the upload flow.

let lookthroughPendingResult = null;   // the parsed-but-not-yet-confirmed preview payload
let lookthroughSelectedFile = null;
let lookthroughView = 'securities';

const INSTRUMENT_TYPE_LABELS = {
    cash: 'Cash', govt_bond: 'Government Bond', corp_bond: 'Corporate Bond',
    equity_traded: 'Stock', equity_nontraded: 'Stock (non-tradable)',
    etf: 'ETF', mutual_fund: 'Mutual Fund', warrant: 'Warrant', option: 'Option',
    future: 'Future', structured_product: 'Structured Product',
    investment_fund: 'Investment Fund', loan: 'Loan', deposit: 'Deposit',
    real_estate: 'Real Estate', other: 'Other',
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
    } else if (lookthroughView === 'overlap') {
        const data = await fetch('/api/lookthrough/overlap').then(r => r.json());
        body.innerHTML = data.securities.length
            ? renderSecuritiesTable(data, { showOverlapCols: true })
            : '<p class="no-data">No security is currently held in more than one fund.</p>';
    } else if (lookthroughView === 'concentration') {
        const data = await fetch('/api/lookthrough/concentration').then(r => r.json());
        body.innerHTML = renderConcentrationView(data);
    } else if (lookthroughView === 'merged') {
        const data = await fetch('/api/lookthrough/merged').then(r => r.json());
        body.innerHTML = renderMergedView(data);
    }
}

function renderSecuritiesTable(data, { showOverlapCols = false } = {}) {
    const funds = data.active_funds;
    const rows = data.securities;
    if (!rows.length) {
        return '<p class="no-data">No look-through holdings yet — import a filing above, and make sure at least one fund has a Track # and Institution Reg # set (Manage Funds table).</p>';
    }
    const fundHeaders = funds.map(f => `
        <th>${escapeHtml(f.name)}<br><span style="font-weight:400;font-size:0.78em;color:var(--text-secondary);">${escapeHtml(FUND_TYPE_LABELS[f.fund_type] || f.fund_type)}</span></th>
    `).join('');
    const overlapHeaders = showOverlapCols ? '<th>Funds</th><th>Max Single Fund</th>' : '';

    const bodyRows = rows.map(s => {
        const fundCells = funds.map(f => {
            const v = s.by_fund[f.id];
            return `<td class="amount-cell">${v ? formatCurrency(v) : '—'}</td>`;
        }).join('');
        const overlapCells = showOverlapCols
            ? `<td class="amount-cell">${s.fund_count}</td><td class="amount-cell">${s.max_single_fund_share !== null ? (s.max_single_fund_share * 100).toFixed(1) + '%' : '—'}</td>`
            : '';
        const conflictTitle = s.classification_conflict
            ? `title="Varies across contributing funds: ${escapeHtml([...s.sector_values, ...s.country_values, ...s.currency_values].join(', '))}"`
            : '';
        return `
            <tr>
                <td>${escapeHtml(s.security_name || s.issuer_name || '—')}${s.classification_conflict ? ` <span class="stock-warn" ${conflictTitle}>⚠</span>` : ''}</td>
                <td>${escapeHtml(s.issuer_name || '—')}</td>
                <td>${escapeHtml(INSTRUMENT_TYPE_LABELS[s.instrument_type] || s.instrument_type)}</td>
                <td class="amount-cell">${formatCurrency(s.combined_value)}</td>
                <td>${escapeHtml(s.sector || '—')}</td>
                <td>${escapeHtml(s.country || '—')}</td>
                <td>${escapeHtml(s.currency || '—')}</td>
                ${fundCells}
                ${overlapCells}
            </tr>
        `;
    }).join('');

    return `
        <div style="overflow-x:auto;">
            <table class="transactions-table">
                <thead><tr>
                    <th>Security</th><th>Issuer</th><th>Type</th><th>Combined Value</th>
                    <th>Sector</th><th>Country</th><th>Currency</th>
                    ${fundHeaders}
                    ${overlapHeaders}
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
            bank's bonds, counted as one counterparty exposure.
        </p>
        <div style="overflow-x:auto;">
            <table class="transactions-table">
                <thead><tr><th>Issuer</th><th>Combined Value</th><th>Instrument Types</th><th>Funds</th></tr></thead>
                <tbody>${data.same_issuer_cross_type.map(g => `
                    <tr>
                        <td>${escapeHtml(g.issuer_name || g.issuer_number || '—')}</td>
                        <td class="amount-cell">${formatCurrency(g.combined_value)}</td>
                        <td>${g.instrument_types.map(t => escapeHtml(INSTRUMENT_TYPE_LABELS[t] || t)).join(', ')}</td>
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

function renderMergedView(data) {
    if (!data.merged.length && !data.unmatched_direct.length) {
        return '<p class="no-data">No look-through holdings or direct stock holdings yet.</p>';
    }
    const mergedRows = data.merged.map(e => `
        <tr>
            <td>${escapeHtml(e.security_name || '—')}</td>
            <td>${escapeHtml(e.security_number)}</td>
            <td class="amount-cell">${formatCurrency(e.indirect_value)}</td>
            <td class="amount-cell">${formatCurrency(e.direct_value)}</td>
            <td class="amount-cell">${formatCurrency(e.combined_value)}</td>
        </tr>
    `).join('');
    const unmatchedRows = data.unmatched_direct.map(u => `
        <tr>
            <td>${escapeHtml(u.symbol)}</td>
            <td class="amount-cell">${formatCurrency(u.value)}</td>
            <td><span class="stock-warn" title="Set an ISIN on this holding (Manage Stock Holdings table, Long-Term Funds tab) to include it in this merge.">⚠ Needs ISIN</span></td>
        </tr>
    `).join('');

    return `
        <div style="overflow-x:auto;">
            <table class="transactions-table">
                <thead><tr><th>Security</th><th>ISIN</th><th>Via Funds</th><th>Held Directly</th><th>Combined</th></tr></thead>
                <tbody>${mergedRows || '<tr><td colspan="5" class="no-data">No merged entries yet.</td></tr>'}</tbody>
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
