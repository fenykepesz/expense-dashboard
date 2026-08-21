let currentFunds = [];
let fundMembers = [];
let selectedFundId = null;
let fundBalanceChart;
let fundsSortCol = 'name';
let fundsSortDir = 1;

const FUND_TYPE_LABELS = {
    pension: 'Pension', study_fund: 'Study Fund', provident_fund: 'Provident Fund',
    investment_provident_fund: 'Investment Provident Fund',
    money_market_fund: 'Money Market Fund', savings_policy: 'Savings Policy',
    investment: 'Investment', real_estate: 'Real Estate', other: 'Other',
};

// A fund can charge more than one of these at once (e.g. a deposit fee AND
// a separate balance fee) — see FEE_BASIS_OPTIONS in db.py.
const FEE_BASIS_OPTIONS = ['deposits', 'earnings', 'total'];
const FEE_BASIS_LABELS = { deposits: 'Deposits', earnings: 'Earnings', total: 'Total' };

const FUND_COLUMN_TOOLTIPS = {
    fund_type: 'The category of long-term savings vehicle (pension, study fund, provident fund, etc.).',
    company_name: 'The financial institution or insurer managing this fund.',
    name: 'The name of this specific fund or track.',
    fund_number: 'Your personal account/policy number for this fund, as shown on your own statements.',
    official_fund_number: "The fund/track's official industry-wide identifier — the same for everyone invested in it, not specific to your account.",
    track_number: "This fund's investment track number, as it appears in the institution's regulatory holdings filing (מספר מסלול) — set this and Institution Reg # to include it in Look-Through aggregation.",
    institution_reg_number: "The managing institution's registration number (ח.פ.), as shown on its regulatory holdings filing's cover sheet — used to match this fund to an uploaded Look-Through filing.",
    is_liquid: 'Marks cash-equivalent funds you could withdraw quickly, as opposed to locked long-term savings.',
    fees: "Annual management fee(s) this fund charges, and what they're calculated on — Deposits, Earnings, or Total balance. A fund can charge more than one at once.",
    owner_name: 'Which household member this fund belongs to.',
    excluded_from_net_worth: "Whether this fund counts toward the Net Worth tab's totals.",
    latest_balance: 'The most recently recorded balance for this fund, and when it was recorded.',
};

function thTooltip(text) {
    return ` <span class="tooltip-icon" title="${escapeHtml(text)}" onclick="event.stopPropagation()">ℹ</span>`;
}

async function loadFundsPanel() {
    const [fundsResp, membersResp] = await Promise.all([
        fetch('/api/funds'),
        fetch('/api/household-members'),
    ]);
    currentFunds = await fundsResp.json();
    fundMembers = await membersResp.json();

    const ownerOpts = '<option value="">No owner</option>' +
        fundMembers.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');
    document.getElementById('newFundOwnerInput').innerHTML = ownerOpts;

    renderFundsList();
    renderFundBalancePicker();
}

async function refreshFundsList() {
    const resp = await fetch('/api/funds');
    currentFunds = await resp.json();
    renderFundsList();
}

function fundTypeOptions(selected) {
    return Object.entries(FUND_TYPE_LABELS)
        .map(([val, label]) => `<option value="${val}"${selected === val ? ' selected' : ''}>${label}</option>`)
        .join('');
}

function fundOwnerOptions(selectedId) {
    return '<option value="">No owner</option>' + fundMembers.map(m =>
        `<option value="${m.id}"${String(selectedId) === String(m.id) ? ' selected' : ''}>${escapeHtml(m.name)}</option>`
    ).join('');
}

// ── Table: sortable headers, every cell directly editable ──────────────

function sortFundsColumn(col) {
    fundsSortDir = (fundsSortCol === col) ? -fundsSortDir : 1;
    fundsSortCol = col;
    renderFundsList();
}

function sortFunds(list) {
    return [...list].sort((a, b) => {
        let va = a[fundsSortCol], vb = b[fundsSortCol];
        if (fundsSortCol === 'fund_type') { va = FUND_TYPE_LABELS[va] || va; vb = FUND_TYPE_LABELS[vb] || vb; }
        const aEmpty = va === null || va === undefined || va === '';
        const bEmpty = vb === null || vb === undefined || vb === '';
        if (aEmpty && bEmpty) return 0;
        if (aEmpty) return 1;   // blanks/unset always sort last, both directions
        if (bEmpty) return -1;
        if (typeof va === 'number') return fundsSortDir * (va - vb);
        return fundsSortDir * String(va).localeCompare(String(vb), 'he');
    });
}

// ── Column widths: resizable + persisted, same pattern as the credit-card
// transaction table's initTxResize (dashboard-credit-card.js) ─────────────
const FUNDS_COL_DEFAULTS = {
    fund_type: 130, company_name: 110, name: 160, fund_number: 90,
    official_fund_number: 100, track_number: 90, institution_reg_number: 110,
    is_liquid: 60, risk_level: 150, fees: 170,
    owner_name: 110, excluded_from_net_worth: 90, latest_balance: 120, action: 70,
};

function getFundsColWidths() {
    try { return Object.assign({}, FUNDS_COL_DEFAULTS, JSON.parse(localStorage.getItem('fundsColWidths'))); }
    catch { return Object.assign({}, FUNDS_COL_DEFAULTS); }
}

function saveFundsColWidths(w) { localStorage.setItem('fundsColWidths', JSON.stringify(w)); }

function initFundsResize(widths) {
    const table = document.querySelector('#fundsTableWrap table');
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
                const keys = Object.keys(FUNDS_COL_DEFAULTS);
                const cols = table.querySelectorAll('col');
                const saved = {};
                keys.forEach((k, j) => { saved[k] = parseInt(cols[j].style.width); });
                saveFundsColWidths(saved);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    });
}

// Every header except the last (a bare action column, nothing after it to
// resize against) gets a drag handle on its right edge.
const FUNDS_COL_RESIZE_HANDLE = '<div class="col-resize-handle" onclick="event.stopPropagation()"></div>';

function fundsTh(col, label, extraHtml = '') {
    const active = col === fundsSortCol;
    const arrow = active ? (fundsSortDir === 1 ? ' ▲' : ' ▼') : ' ↕';
    return `<th onclick="sortFundsColumn('${col}')" style="cursor:pointer;white-space:nowrap;">${label}${extraHtml}<span style="opacity:${active ? 1 : 0.35};font-size:0.75em;">${arrow}</span>${FUNDS_COL_RESIZE_HANDLE}</th>`;
}

// Fees isn't meaningfully sortable (a fund can have 0-3 fee rows) — a plain,
// non-clickable header with just a tooltip instead of fundsTh's sort wiring.
function fundsThPlain(label, tooltip) {
    return `<th style="white-space:nowrap;">${label}${thTooltip(tooltip)}${FUNDS_COL_RESIZE_HANDLE}</th>`;
}

function renderFundsList() {
    const wrap = document.getElementById('fundsTableWrap');
    const typeFilter = document.getElementById('fundTypeFilter')?.value || 'all';
    const visibleFunds = typeFilter === 'all' ? currentFunds : currentFunds.filter(f => f.fund_type === typeFilter);

    let bodyHtml;
    if (!currentFunds.length) {
        bodyHtml = '<tr><td colspan="14" class="no-data">No funds yet — add one above.</td></tr>';
    } else if (!visibleFunds.length) {
        bodyHtml = '<tr><td colspan="14" class="no-data">No funds match this filter.</td></tr>';
    } else {
        bodyHtml = sortFunds(visibleFunds).map(renderFundRow).join('');
    }

    const w = getFundsColWidths();
    wrap.innerHTML = `
        <table class="transactions-table" style="table-layout:fixed;width:100%;">
            <colgroup>
                <col style="width:${w.fund_type}px;">
                <col style="width:${w.company_name}px;">
                <col style="width:${w.name}px;">
                <col style="width:${w.fund_number}px;">
                <col style="width:${w.official_fund_number}px;">
                <col style="width:${w.track_number}px;">
                <col style="width:${w.institution_reg_number}px;">
                <col style="width:${w.is_liquid}px;">
                <col style="width:${w.risk_level}px;">
                <col style="width:${w.fees}px;">
                <col style="width:${w.owner_name}px;">
                <col style="width:${w.excluded_from_net_worth}px;">
                <col style="width:${w.latest_balance}px;">
                <col style="width:${w.action}px;">
            </colgroup>
            <thead><tr>
                ${fundsTh('fund_type', 'Type', thTooltip(FUND_COLUMN_TOOLTIPS.fund_type))}
                ${fundsTh('company_name', 'Company', thTooltip(FUND_COLUMN_TOOLTIPS.company_name))}
                ${fundsTh('name', 'Fund Name', thTooltip(FUND_COLUMN_TOOLTIPS.name))}
                ${fundsTh('fund_number', 'Fund #', thTooltip(FUND_COLUMN_TOOLTIPS.fund_number))}
                ${fundsTh('official_fund_number', 'Official Fund #', thTooltip(FUND_COLUMN_TOOLTIPS.official_fund_number))}
                ${fundsTh('track_number', 'Track #', thTooltip(FUND_COLUMN_TOOLTIPS.track_number))}
                ${fundsTh('institution_reg_number', 'Institution Reg #', thTooltip(FUND_COLUMN_TOOLTIPS.institution_reg_number))}
                ${fundsTh('is_liquid', 'Liquid', thTooltip(FUND_COLUMN_TOOLTIPS.is_liquid))}
                ${fundsTh('risk_level', 'Risk', thTooltip(RISK_LEVEL_TOOLTIP))}
                ${fundsThPlain('Fees', FUND_COLUMN_TOOLTIPS.fees)}
                ${fundsTh('owner_name', 'Owner', thTooltip(FUND_COLUMN_TOOLTIPS.owner_name))}
                ${fundsTh('excluded_from_net_worth', 'Net Worth', thTooltip(FUND_COLUMN_TOOLTIPS.excluded_from_net_worth))}
                ${fundsTh('latest_balance', 'Latest Value', thTooltip(FUND_COLUMN_TOOLTIPS.latest_balance))}
                <th></th>
            </tr></thead>
            <tbody>${bodyHtml}</tbody>
        </table>
    `;
    initFundsResize(w);
}

function renderFundFeesCell(f) {
    const badges = (f.fees || []).map(fee => `
        <span class="fee-badge">${escapeHtml(FEE_BASIS_LABELS[fee.fee_basis] || fee.fee_basis)} ${fee.fee_percent}%
            <button type="button" class="fee-badge-remove" onclick="deleteFundFee(${fee.id})" title="Remove fee">×</button>
        </span>`).join('');

    const usedBases = new Set((f.fees || []).map(fee => fee.fee_basis));
    const availableBases = FEE_BASIS_OPTIONS.filter(b => !usedBases.has(b));
    const addRow = availableBases.length ? `
        <div class="fee-add-row">
            <select class="fee-basis-input" id="feeBasis-${f.id}">
                ${availableBases.map(b => `<option value="${b}">${FEE_BASIS_LABELS[b]}</option>`).join('')}
            </select>
            <input type="number" step="0.01" class="fee-percent-input" id="feePercent-${f.id}" placeholder="%">
            <button type="button" class="btn-excl" onclick="addFundFee(${f.id})" title="Add fee">+</button>
        </div>` : '';

    return `<div class="fee-badges">${badges}</div>${addRow}`;
}

function renderFundRow(f) {
    const noteStyle = 'width:100%;max-width:140px;';
    return `
        <tr class="${f.excluded_from_net_worth ? 'tx-excluded' : ''}">
            <td><select class="tx-cat-select" onchange="updateFundField(${f.id}, 'fund_type', this.value)">${fundTypeOptions(f.fund_type)}</select></td>
            <td><input type="text" class="tx-note-input" value="${escapeHtml(f.company_name || '')}" placeholder="Company…" onblur="saveFundTextField(${f.id}, 'company_name', this)" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td><input type="text" class="tx-note-input" value="${escapeHtml(f.name)}" placeholder="Fund name…" onblur="saveFundTextField(${f.id}, 'name', this)" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td><input type="text" class="tx-note-input" value="${escapeHtml(f.fund_number || '')}" placeholder="Fund #…" onblur="saveFundTextField(${f.id}, 'fund_number', this)" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td><input type="text" class="tx-note-input" value="${escapeHtml(f.official_fund_number || '')}" placeholder="Official #…" onblur="saveFundTextField(${f.id}, 'official_fund_number', this)" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td><input type="text" class="tx-note-input" value="${escapeHtml(f.track_number || '')}" placeholder="Track #…" onblur="saveFundTextField(${f.id}, 'track_number', this)" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td><input type="text" class="tx-note-input" value="${escapeHtml(f.institution_reg_number || '')}" placeholder="Institution reg #…" onblur="saveFundTextField(${f.id}, 'institution_reg_number', this)" onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td style="text-align:center;"><input type="checkbox" ${f.is_liquid ? 'checked' : ''} onchange="updateFundField(${f.id}, 'is_liquid', this.checked)"></td>
            <td>
                <select class="tx-cat-select" style="margin-bottom:3px;" onchange="updateFundField(${f.id}, 'risk_level', parseInt(this.value, 10))">${riskLevelOptions(f.risk_level)}</select>
                <input type="text" class="tx-note-input" style="${noteStyle}" value="${escapeHtml(f.risk_note || '')}" placeholder="Note…" onblur="saveFundTextField(${f.id}, 'risk_note', this)" onkeydown="if(event.key==='Enter')this.blur()">
            </td>
            <td>${renderFundFeesCell(f)}</td>
            <td><select class="tx-cat-select" onchange="updateFundField(${f.id}, 'owner_id', this.value || null)">${fundOwnerOptions(f.owner_id)}</select></td>
            <td>${f.excluded_from_net_worth
                ? '<span style="color:var(--text-secondary);font-size:0.85em;">⊘ Excluded</span>'
                : '<span style="color:var(--success-color);font-size:0.85em;">✓ Included</span>'}</td>
            <td class="amount-cell">${f.latest_balance !== null && f.latest_balance !== undefined
                ? `${formatCurrency(f.latest_balance)}<br><span style="font-size:0.72em;color:var(--text-secondary);font-weight:normal;">as of ${escapeHtml(f.latest_balance_date)}</span>`
                : '—'}</td>
            <td>
                <div class="tx-actions">
                    <button class="btn-excl" onclick="toggleFundNetWorthExclude(${f.id})" title="${f.excluded_from_net_worth ? 'Include in Net Worth' : 'Exclude from Net Worth'}">${f.excluded_from_net_worth ? '↺' : '⊘'}</button>
                    <button class="btn-excl btn-delete" onclick="deleteFund(${f.id}, '${escapeHtml(f.name).replace(/'/g, "\\'")}')" title="Delete">🗑</button>
                </div>
            </td>
        </tr>
    `;
}

// Select/checkbox fields: the change is a discrete, final action, so save
// immediately and re-render (updates the row's own display, e.g. Type label).
async function updateFundField(id, field, value) {
    const resp = await fetch(`/api/funds/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to update fund'); renderFundsList(); return; }
    currentFunds = result.funds;
    renderFundsList();
}

// Text fields: save on blur, only if changed (matches the notes-input pattern
// used elsewhere), and WITHOUT a full re-render — the input already shows
// what was typed, and re-rendering mid-interaction-elsewhere would be
// disruptive. company_name/name/fund_number feed the balance picker below,
// so that one specifically needs a refresh.
async function saveFundTextField(id, field, inputEl) {
    const fund = currentFunds.find(f => f.id === id);
    if (!fund) return;
    const value = inputEl.value.trim();
    const previous = fund[field] || '';
    if (value === previous) return;

    const resp = await fetch(`/api/funds/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to update fund'); inputEl.value = previous; return; }
    currentFunds = result.funds;
    if (field === 'company_name' || field === 'name' || field === 'fund_number') {
        renderFundBalancePicker();
    }
}

// ── Cascading Company → Fund Name → Fund # picker for balance entry ────
// Resolves to a specific fund as soon as the choice is unambiguous: e.g.
// picking a company with only one fund selects it immediately; the Fund
// Name / Fund # dropdowns only appear when more than one fund still matches.
const NO_COMPANY_SENTINEL = '__no_company__';

function fundsForCompany(company) {
    return currentFunds.filter(f => (f.company_name || NO_COMPANY_SENTINEL) === company);
}

function renderFundBalancePicker() {
    const companySelect = document.getElementById('fundBalanceCompanySelect');
    const previousCompany = companySelect.value;
    const companies = [...new Set(currentFunds.map(f => f.company_name || NO_COMPANY_SENTINEL))]
        .sort((a, b) => {
            if (a === NO_COMPANY_SENTINEL) return 1;
            if (b === NO_COMPANY_SENTINEL) return -1;
            return a.localeCompare(b);
        });
    companySelect.innerHTML = '<option value="">Select a company…</option>' +
        companies.map(c => `<option value="${escapeHtml(c)}">${c === NO_COMPANY_SENTINEL ? '(No company set)' : escapeHtml(c)}</option>`).join('');

    if (previousCompany && companies.includes(previousCompany)) {
        companySelect.value = previousCompany;
        onFundBalanceCompanyChange();
    } else {
        resetFundNameSelect();
        resetFundNumberSelect();
        showSelectedFundInfo(null);
        loadFundBalancesFor(null);
    }
}

function resetFundNameSelect() {
    const sel = document.getElementById('fundBalanceNameSelect');
    sel.innerHTML = '<option value="">Select a fund name…</option>';
    sel.disabled = true;
}

function resetFundNumberSelect() {
    const sel = document.getElementById('fundBalanceNumberSelect');
    sel.innerHTML = '<option value="">Select a fund #…</option>';
    sel.disabled = true;
    sel.style.display = 'none';
}

function onFundBalanceCompanyChange() {
    const company = document.getElementById('fundBalanceCompanySelect').value;
    resetFundNumberSelect();
    if (!company) {
        resetFundNameSelect();
        showSelectedFundInfo(null);
        loadFundBalancesFor(null);
        return;
    }
    const matches = fundsForCompany(company);
    if (matches.length === 1) {
        showResolvedFundName(matches[0]);
        showSelectedFundInfo(matches[0]);
        loadFundBalancesFor(matches[0].id);
        return;
    }
    const nameSelect = document.getElementById('fundBalanceNameSelect');
    const names = [...new Set(matches.map(f => f.name))].sort((a, b) => a.localeCompare(b));
    nameSelect.innerHTML = '<option value="">Select a fund name…</option>' +
        names.map(n => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join('');
    nameSelect.disabled = false;
    showSelectedFundInfo(null);
    loadFundBalancesFor(null);
}

function onFundBalanceNameChange() {
    const company = document.getElementById('fundBalanceCompanySelect').value;
    const name = document.getElementById('fundBalanceNameSelect').value;
    if (!name) {
        resetFundNumberSelect();
        showSelectedFundInfo(null);
        loadFundBalancesFor(null);
        return;
    }
    const matches = fundsForCompany(company).filter(f => f.name === name);
    if (matches.length === 1) {
        resetFundNumberSelect();
        showSelectedFundInfo(matches[0]);
        loadFundBalancesFor(matches[0].id);
        return;
    }
    const numSelect = document.getElementById('fundBalanceNumberSelect');
    numSelect.innerHTML = '<option value="">Select a fund #…</option>' +
        matches.map(f => `<option value="${f.id}">${escapeHtml(f.fund_number || '(no number)')}</option>`).join('');
    numSelect.disabled = false;
    numSelect.style.display = '';
    showSelectedFundInfo(null);
    loadFundBalancesFor(null);
}

function onFundBalanceNumberChange() {
    const fundId = document.getElementById('fundBalanceNumberSelect').value;
    const fund = currentFunds.find(f => String(f.id) === fundId);
    showSelectedFundInfo(fund || null);
    loadFundBalancesFor(fundId || null);
}

// Show the auto-resolved fund name as a single disabled option, so the
// user can see which name was picked even without choosing it explicitly.
function showResolvedFundName(fund) {
    const sel = document.getElementById('fundBalanceNameSelect');
    sel.innerHTML = `<option value="${escapeHtml(fund.name)}" selected>${escapeHtml(fund.name)}</option>`;
    sel.disabled = true;
}

// One-line confirmation of the fully-resolved fund — the Fund # dropdown
// stays hidden whenever it isn't needed to disambiguate, so this is the
// only place a resolved-by-company-alone or resolved-by-name fund number
// is shown to the user.
function showSelectedFundInfo(fund) {
    const el = document.getElementById('fundBalanceSelectedInfo');
    if (!fund) { el.textContent = ''; return; }
    const parts = [fund.company_name || '(No company)', fund.name];
    if (fund.fund_number) parts.push(`#${fund.fund_number}`);
    el.textContent = `Selected: ${parts.join(' — ')}`;
}

async function loadFundBalancesFor(fundId) {
    selectedFundId = fundId || null;
    if (!selectedFundId) {
        renderFundBalancesTable([]);
        renderFundBalanceChart([]);
        return;
    }
    const resp = await fetch(`/api/funds/${selectedFundId}/balances`);
    const balances = await resp.json();
    renderFundBalancesTable(balances);
    renderFundBalanceChart(balances);
}

async function addNewFund() {
    const companyName = document.getElementById('newFundCompanyInput').value.trim();
    const name = document.getElementById('newFundNameInput').value.trim();
    const fundNumber = document.getElementById('newFundNumberInput').value.trim();
    const officialFundNumber = document.getElementById('newFundOfficialNumberInput').value.trim();
    const fundType = document.getElementById('newFundTypeInput').value;
    const ownerId = document.getElementById('newFundOwnerInput').value || null;
    const isLiquid = document.getElementById('newFundLiquidInput').checked;
    if (!name || !companyName) { alert('Fund name and company name are required'); return; }
    const resp = await fetch('/api/funds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name, company_name: companyName, fund_number: fundNumber,
            official_fund_number: officialFundNumber,
            fund_type: fundType, owner_id: ownerId, is_liquid: isLiquid,
        }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add fund'); return; }
    document.getElementById('newFundCompanyInput').value = '';
    document.getElementById('newFundNameInput').value = '';
    document.getElementById('newFundNumberInput').value = '';
    document.getElementById('newFundOfficialNumberInput').value = '';
    document.getElementById('newFundLiquidInput').checked = false;
    currentFunds = result.funds;
    renderFundsList();
    renderFundBalancePicker();
}

async function addFundFee(fundId) {
    const basisSelect = document.getElementById(`feeBasis-${fundId}`);
    const percentInput = document.getElementById(`feePercent-${fundId}`);
    const feeBasis = basisSelect.value;
    const feePercent = percentInput.value.trim();
    if (feePercent === '') { alert('Enter a fee percentage'); return; }
    const resp = await fetch(`/api/funds/${fundId}/fees`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fee_basis: feeBasis, fee_percent: parseFloat(feePercent) }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add fee'); return; }
    currentFunds = result.funds;
    renderFundsList();
}

async function deleteFundFee(feeId) {
    const resp = await fetch(`/api/fund-fees/${feeId}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete fee'); return; }
    currentFunds = result.funds;
    renderFundsList();
}

async function toggleFundNetWorthExclude(id) {
    const fund = currentFunds.find(f => f.id === id);
    if (!fund) return;
    const resp = await fetch(`/api/funds/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ excluded_from_net_worth: !fund.excluded_from_net_worth }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to update fund'); return; }
    currentFunds = result.funds;
    renderFundsList();
}

async function deleteFund(id, name) {
    if (!confirm(`Delete fund "${name}"? Its balance history will no longer be shown.`)) return;
    const resp = await fetch(`/api/funds/${id}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete fund'); return; }
    currentFunds = result.funds;
    renderFundsList();
    renderFundBalancePicker();
}

function renderFundBalancesTable(balances) {
    const body = document.getElementById('fundBalancesBody');
    if (!balances.length) {
        body.innerHTML = '<tr><td colspan="4" class="no-data">Select a fund above to see its balance history.</td></tr>';
        return;
    }
    body.innerHTML = balances.map(b => `
        <tr>
            <td>${escapeHtml(b.date)}</td>
            <td class="amount-cell">${formatCurrency(b.balance)}</td>
            <td class="amount-cell">${formatCurrency(b.contribution)}</td>
            <td><button class="btn-excl btn-delete" onclick="deleteFundBalanceEntry(${b.id})" title="Delete entry">🗑</button></td>
        </tr>
    `).join('');
}

function renderFundBalanceChart(balances) {
    const sorted = [...balances].sort((a, b) => a.date.localeCompare(b.date));
    const ctx = document.getElementById('fundBalanceChart');
    if (fundBalanceChart) fundBalanceChart.destroy();

    fundBalanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: sorted.map(b => b.date),
            datasets: [{
                label: 'Balance',
                data: sorted.map(b => b.balance),
                borderColor: '#667eea',
                backgroundColor: 'rgba(102, 126, 234, 0.15)',
                borderWidth: 3,
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => formatCurrency(ctx.raw)
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: getThemeColors().textColor },
                    grid: { color: getThemeColors().gridColor }
                },
                y: {
                    ticks: {
                        color: getThemeColors().textColor,
                        callback: v => formatCurrency(v)
                    },
                    grid: { color: getThemeColors().gridColor }
                }
            }
        }
    });
}

async function addFundBalanceEntry() {
    if (!selectedFundId) { alert('Select a fund first'); return; }
    const date = document.getElementById('newFundBalanceDate').value;
    const balance = document.getElementById('newFundBalanceAmount').value;
    const contribution = document.getElementById('newFundContribution').value || 0;
    if (!date || balance === '') { alert('Date and balance are required'); return; }

    const resp = await fetch(`/api/funds/${selectedFundId}/balances`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date, balance: parseFloat(balance), contribution: parseFloat(contribution) }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add balance'); return; }
    document.getElementById('newFundBalanceDate').value = '';
    document.getElementById('newFundBalanceAmount').value = '';
    document.getElementById('newFundContribution').value = '';
    renderFundBalancesTable(result.balances);
    renderFundBalanceChart(result.balances);
    refreshFundsList(); // Latest Value column needs to reflect the new entry
}

async function deleteFundBalanceEntry(id) {
    if (!confirm('Delete this balance entry?')) return;
    const resp = await fetch(`/api/fund-balances/${id}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete entry'); return; }
    renderFundBalancesTable(result.balances);
    renderFundBalanceChart(result.balances);
    refreshFundsList(); // Latest Value column needs to reflect the deletion
}
