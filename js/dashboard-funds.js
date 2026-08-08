let currentFunds = [];
let fundMembers = [];
let editingFundId = null;
let selectedFundId = null;
let fundBalanceChart;

const FUND_TYPE_LABELS = { pension: 'Pension', study_fund: 'Study Fund', investment: 'Investment', other: 'Other' };

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

    editingFundId = null;
    renderFundsList();
    renderFundSelect();
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

function renderFundsList() {
    const body = document.getElementById('fundsListBody');
    if (!currentFunds.length) {
        body.innerHTML = '<tr><td colspan="6" class="no-data">No funds yet — add one above.</td></tr>';
        return;
    }
    body.innerHTML = currentFunds.map(f => f.id === editingFundId ? renderFundEditRow(f) : `
        <tr>
            <td>${escapeHtml(f.company_name || '—')}</td>
            <td>${escapeHtml(f.name)}</td>
            <td>${escapeHtml(f.fund_number || '—')}</td>
            <td>${FUND_TYPE_LABELS[f.fund_type] || f.fund_type}</td>
            <td>${f.owner_name ? escapeHtml(f.owner_name) : '—'}</td>
            <td>
                <div class="tx-actions">
                    <button class="btn-excl" onclick="startEditFund(${f.id})" title="Edit">✎</button>
                    <button class="btn-excl btn-delete" onclick="deleteFund(${f.id}, '${escapeHtml(f.name).replace(/'/g, "\\'")}')" title="Delete">🗑</button>
                </div>
            </td>
        </tr>
    `).join('');
}

function renderFundEditRow(f) {
    const inputStyle = 'border:1px solid var(--input-border);background:var(--input-bg);color:var(--text-primary);border-radius:5px;padding:4px 7px;font-size:0.85em;width:100%;';
    return `
        <tr>
            <td><input type="text" id="editFundCompany" value="${escapeHtml(f.company_name || '')}" style="${inputStyle}"></td>
            <td><input type="text" id="editFundName" value="${escapeHtml(f.name)}" style="${inputStyle}"></td>
            <td><input type="text" id="editFundNumber" value="${escapeHtml(f.fund_number || '')}" style="${inputStyle}"></td>
            <td><select id="editFundType" class="tx-cat-select">${fundTypeOptions(f.fund_type)}</select></td>
            <td><select id="editFundOwner" class="tx-cat-select">${fundOwnerOptions(f.owner_id)}</select></td>
            <td>
                <div class="tx-actions">
                    <button class="btn-excl" onclick="saveFundEdit(${f.id})" title="Save">✅</button>
                    <button class="btn-excl" onclick="cancelFundEdit()" title="Cancel">✕</button>
                </div>
            </td>
        </tr>
    `;
}

function startEditFund(id) {
    editingFundId = id;
    renderFundsList();
}

function cancelFundEdit() {
    editingFundId = null;
    renderFundsList();
}

async function saveFundEdit(id) {
    const companyName = document.getElementById('editFundCompany').value.trim();
    const name = document.getElementById('editFundName').value.trim();
    const fundNumber = document.getElementById('editFundNumber').value.trim();
    const fundType = document.getElementById('editFundType').value;
    const ownerId = document.getElementById('editFundOwner').value || null;
    if (!name || !companyName) { alert('Fund name and company name are required'); return; }

    const resp = await fetch(`/api/funds/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name, company_name: companyName, fund_number: fundNumber,
            fund_type: fundType, owner_id: ownerId,
        }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to update fund'); return; }
    currentFunds = result.funds;
    editingFundId = null;
    renderFundsList();
    renderFundSelect();
}

function renderFundSelect() {
    const select = document.getElementById('fundBalanceFundSelect');
    const current = select.value;
    select.innerHTML = '<option value="">Select a fund…</option>' +
        currentFunds.map(f => `<option value="${f.id}">${escapeHtml(f.name)}</option>`).join('');
    if (current && currentFunds.some(f => String(f.id) === current)) {
        select.value = current;
    } else {
        selectedFundId = null;
        renderFundBalancesTable([]);
        renderFundBalanceChart([]);
    }
}

async function addNewFund() {
    const companyName = document.getElementById('newFundCompanyInput').value.trim();
    const name = document.getElementById('newFundNameInput').value.trim();
    const fundNumber = document.getElementById('newFundNumberInput').value.trim();
    const fundType = document.getElementById('newFundTypeInput').value;
    const ownerId = document.getElementById('newFundOwnerInput').value || null;
    if (!name || !companyName) { alert('Fund name and company name are required'); return; }
    const resp = await fetch('/api/funds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name, company_name: companyName, fund_number: fundNumber,
            fund_type: fundType, owner_id: ownerId,
        }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add fund'); return; }
    document.getElementById('newFundCompanyInput').value = '';
    document.getElementById('newFundNameInput').value = '';
    document.getElementById('newFundNumberInput').value = '';
    currentFunds = result.funds;
    renderFundsList();
    renderFundSelect();
}

async function deleteFund(id, name) {
    if (!confirm(`Delete fund "${name}"? Its balance history will no longer be shown.`)) return;
    const resp = await fetch(`/api/funds/${id}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete fund'); return; }
    currentFunds = result.funds;
    renderFundsList();
    renderFundSelect();
}

async function onFundBalanceFundChange() {
    const select = document.getElementById('fundBalanceFundSelect');
    selectedFundId = select.value || null;
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
}

async function deleteFundBalanceEntry(id) {
    if (!confirm('Delete this balance entry?')) return;
    const resp = await fetch(`/api/fund-balances/${id}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete entry'); return; }
    renderFundBalancesTable(result.balances);
    renderFundBalanceChart(result.balances);
}
