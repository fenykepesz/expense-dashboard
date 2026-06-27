let currentFunds = [];
let selectedFundId = null;
let fundBalanceChart;

async function loadFundsPanel() {
    const [fundsResp, membersResp] = await Promise.all([
        fetch('/api/funds'),
        fetch('/api/household-members'),
    ]);
    currentFunds = await fundsResp.json();
    const members = await membersResp.json();

    const ownerOpts = '<option value="">No owner</option>' +
        members.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');
    document.getElementById('newFundOwnerInput').innerHTML = ownerOpts;

    renderFundsList();
    renderFundSelect();
}

function renderFundsList() {
    const list = document.getElementById('fundsList');
    if (!currentFunds.length) {
        list.innerHTML = '<span style="color:var(--text-secondary);font-size:0.9em;">No funds yet — add one above.</span>';
        return;
    }
    const typeLabels = { pension: 'Pension', study_fund: 'Study Fund', investment: 'Investment', other: 'Other' };
    list.innerHTML = currentFunds.map(f => `
        <span class="cat-pill">
            ${escapeHtml(f.name)}
            <span class="cat-pill-count">${typeLabels[f.fund_type] || f.fund_type}${f.owner_name ? ' · ' + escapeHtml(f.owner_name) : ''}</span>
            <button class="cat-pill-del" title="Delete fund" onclick="deleteFund(${f.id}, '${escapeHtml(f.name).replace(/'/g, "\\'")}')">✕</button>
        </span>
    `).join('');
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
    const name = document.getElementById('newFundNameInput').value.trim();
    const fundType = document.getElementById('newFundTypeInput').value;
    const ownerId = document.getElementById('newFundOwnerInput').value || null;
    if (!name) return;
    const resp = await fetch('/api/funds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, fund_type: fundType, owner_id: ownerId }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add fund'); return; }
    document.getElementById('newFundNameInput').value = '';
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
