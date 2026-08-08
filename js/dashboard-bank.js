// Bank Accounts tab: account management, import, manual entry, and the
// cash-flow dashboard (all accounts, credit-card-dashboard style)
let currentBankAccounts = [];
let selectedBankAccountId = null;
let editingAccountRiskId = null;
let bankAllTransactions = [];
let bankDisplayTx = [];   // after filters (incl. excluded when status allows)
let bankFilteredTx = [];  // bankDisplayTx minus excluded — feeds charts/cards
let bankMonthlyChart, bankNetChart, bankCategoryChart, bankDescChart, bankAccountChart;
let bankFiltersInitialized = false;

async function loadBankAccountsPanel() {
    const [accountsResp, membersResp, txResp] = await Promise.all([
        fetch('/api/bank-accounts'),
        fetch('/api/household-members'),
        fetch('/api/bank-transactions'),
    ]);
    currentBankAccounts = await accountsResp.json();
    const members = await membersResp.json();
    bankAllTransactions = await txResp.json();

    const ownerOpts = '<option value="">No owner</option>' +
        members.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');
    document.getElementById('newBankAccountOwnerInput').innerHTML = ownerOpts;
    document.getElementById('bankRiskTooltip').title = RISK_LEVEL_TOOLTIP;
    cancelBankAccountRiskEdit();

    const catOpts = (availableCategories.length ? availableCategories : ['Uncategorized'])
        .map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    document.getElementById('newBankTxCategory').innerHTML = catOpts;

    renderBankAccountsList();
    renderBankAccountSelect();
    populateBankFilters();
    applyBankFilters();
}

async function reloadBankTransactions() {
    const resp = await fetch('/api/bank-transactions');
    bankAllTransactions = await resp.json();
    populateBankFilters();
    applyBankFilters();
}

// ── Account management ────────────────────────────────────────────────

function renderBankAccountsList() {
    const list = document.getElementById('bankAccountsList');
    if (!currentBankAccounts.length) {
        list.innerHTML = '<span style="color:var(--text-secondary);font-size:0.9em;">No bank accounts yet — add one above.</span>';
        return;
    }
    list.innerHTML = currentBankAccounts.map(a => `
        <span class="cat-pill"${a.excluded_from_net_worth ? ' style="opacity:0.55;"' : ''}>
            ${escapeHtml(a.name)}
            <span class="cat-pill-count">${a.account_number ? '*' + escapeHtml(a.account_number) + ' · ' : ''}${a.owner_name ? escapeHtml(a.owner_name) : 'No owner'} · Risk: ${escapeHtml(RISK_LEVEL_LABELS[a.risk_level])}${a.excluded_from_net_worth ? ' · ⊘ excluded from Net Worth' : ''}</span>
            <button class="cat-pill-del" title="Edit risk" onclick="startEditBankAccountRisk(${a.id})" style="color:var(--text-secondary);">✎</button>
            <button class="cat-pill-del" title="${a.excluded_from_net_worth ? 'Include in Net Worth' : 'Exclude from Net Worth'}" onclick="toggleBankAccountNetWorthExclude(${a.id})" style="color:var(--text-secondary);">${a.excluded_from_net_worth ? '↺' : '⊘'}</button>
            <button class="cat-pill-del" title="Delete account" onclick="deleteBankAccount(${a.id}, '${escapeHtml(a.name).replace(/'/g, "\\'")}')">✕</button>
        </span>
    `).join('');
}

// ── Risk edit (shared panel below the pill list — pills have no row to
// expand into, unlike the funds table) ─────────────────────────────────

function startEditBankAccountRisk(id) {
    const account = currentBankAccounts.find(a => a.id === id);
    if (!account) return;
    editingAccountRiskId = id;
    document.getElementById('bankAccountRiskEditName').textContent = account.name;
    document.getElementById('editAccountRisk').innerHTML = riskLevelOptions(account.risk_level);
    document.getElementById('editAccountRiskNote').value = account.risk_note || '';
    document.getElementById('bankAccountRiskEditPanel').classList.remove('hidden');
}

function cancelBankAccountRiskEdit() {
    editingAccountRiskId = null;
    document.getElementById('bankAccountRiskEditPanel').classList.add('hidden');
}

async function saveBankAccountRisk() {
    if (!editingAccountRiskId) return;
    const riskLevel = parseInt(document.getElementById('editAccountRisk').value, 10);
    const riskNote = document.getElementById('editAccountRiskNote').value.trim();
    const resp = await fetch(`/api/bank-accounts/${editingAccountRiskId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ risk_level: riskLevel, risk_note: riskNote }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to update account'); return; }
    currentBankAccounts = result.accounts;
    cancelBankAccountRiskEdit();
    renderBankAccountsList();
}

function renderBankAccountSelect() {
    const select = document.getElementById('bankAccountSelect');
    const current = select.value;
    select.innerHTML = '<option value="">Select an account…</option>' +
        currentBankAccounts.map(a => `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join('');
    if (current && currentBankAccounts.some(a => String(a.id) === current)) {
        select.value = current;
    } else {
        selectedBankAccountId = null;
    }
}

async function addNewBankAccount() {
    const name = document.getElementById('newBankAccountNameInput').value.trim();
    const accountNumber = document.getElementById('newBankAccountNumberInput').value.trim();
    const ownerId = document.getElementById('newBankAccountOwnerInput').value || null;
    if (!name) return;
    const resp = await fetch('/api/bank-accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, account_number: accountNumber, owner_id: ownerId }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add bank account'); return; }
    document.getElementById('newBankAccountNameInput').value = '';
    document.getElementById('newBankAccountNumberInput').value = '';
    currentBankAccounts = result.accounts;
    renderBankAccountsList();
    renderBankAccountSelect();
    populateBankFilters();
}

async function deleteBankAccount(id, name) {
    if (!confirm(`Delete bank account "${name}"? Its transaction history will no longer be shown.`)) return;
    const resp = await fetch(`/api/bank-accounts/${id}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete bank account'); return; }
    currentBankAccounts = result.accounts;
    renderBankAccountsList();
    renderBankAccountSelect();
    reloadBankTransactions();
}

async function toggleBankAccountNetWorthExclude(id) {
    const account = currentBankAccounts.find(a => a.id === id);
    if (!account) return;
    const resp = await fetch(`/api/bank-accounts/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ excluded_from_net_worth: !account.excluded_from_net_worth }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to update account'); return; }
    currentBankAccounts = result.accounts;
    renderBankAccountsList();
}

function onBankAccountChange() {
    selectedBankAccountId = document.getElementById('bankAccountSelect').value || null;
}

// ── Manual entry ──────────────────────────────────────────────────────

async function addBankTransaction() {
    if (!selectedBankAccountId) { alert('Select an account first'); return; }
    const date = document.getElementById('newBankTxDate').value;
    const description = document.getElementById('newBankTxDescription').value.trim();
    const type = document.getElementById('newBankTxType').value;
    const amount = document.getElementById('newBankTxAmount').value;
    const category = document.getElementById('newBankTxCategory').value;
    if (!date || !description || amount === '') { alert('Date, description, and amount are required'); return; }

    const resp = await fetch(`/api/bank-accounts/${selectedBankAccountId}/transactions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date, description, type, amount: parseFloat(amount), category }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add transaction'); return; }
    document.getElementById('newBankTxDate').value = '';
    document.getElementById('newBankTxDescription').value = '';
    document.getElementById('newBankTxAmount').value = '';
    reloadBankTransactions();
}

// ── File import ───────────────────────────────────────────────────────

let bankImportTransactions = [];

function startBankImport() {
    if (!selectedBankAccountId) { alert('Select an account first — the import goes into the selected account.'); return; }
    document.getElementById('bankImportFile').click();
}

async function onBankImportFileChosen() {
    const input = document.getElementById('bankImportFile');
    const file = input.files[0];
    if (!file || !selectedBankAccountId) return;
    const status = document.getElementById('bankImportStatus');
    status.textContent = `Parsing ${file.name}…`;

    const form = new FormData();
    form.append('file', file);
    const resp = await fetch(`/api/bank-accounts/${selectedBankAccountId}/import`, { method: 'POST', body: form });
    const result = await resp.json();
    input.value = '';
    if (!resp.ok) { status.textContent = ''; alert(result.error || 'Failed to parse the file'); return; }

    bankImportTransactions = result.transactions;
    status.textContent = '';

    const account = currentBankAccounts.find(a => String(a.id) === String(selectedBankAccountId));
    const accountMismatch = result.file_account_number && account && account.account_number
        && !result.file_account_number.includes(account.account_number)
        && !account.account_number.includes(result.file_account_number);

    document.getElementById('bankImportSummary').innerHTML =
        `File account <strong>${escapeHtml(result.file_account_number || 'unknown')}</strong> → importing into <strong>${escapeHtml(account ? account.name : '?')}</strong>.` +
        ` ${result.new_count} new transaction(s), ${result.duplicate_count} duplicate(s) will be skipped.` +
        (result.skipped ? ` ${result.skipped} unparseable row(s) ignored.` : '') +
        (accountMismatch ? `<br><strong style="color:var(--error-color);">⚠ The file's account number doesn't match this account — double-check before confirming!</strong>` : '');

    document.getElementById('bankImportPreviewBody').innerHTML = bankImportTransactions.map(t => `
        <tr class="${t.duplicate ? 'tx-excluded' : ''}">
            <td>${escapeHtml(t.date)}</td>
            <td>${escapeHtml(t.description)}</td>
            <td>${escapeHtml(t.reference || '')}</td>
            <td class="amount-cell" style="color:${t.amount >= 0 ? 'var(--success-color)' : 'inherit'};">${formatCurrency(t.amount)}</td>
            <td class="amount-cell">${t.balance_after === null ? '—' : formatCurrency(t.balance_after)}</td>
            <td>${t.duplicate ? '<span style="color:var(--text-secondary);">duplicate</span>' : '<strong style="color:var(--success-color);">new</strong>'}</td>
        </tr>
    `).join('');
    document.getElementById('bankImportPreview').classList.remove('hidden');
}

async function confirmBankImport() {
    const resp = await fetch(`/api/bank-accounts/${selectedBankAccountId}/import/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transactions: bankImportTransactions }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Import failed'); return; }
    resetBankImport();
    document.getElementById('bankImportStatus').textContent =
        `✅ Imported ${result.inserted} transaction(s)` + (result.skipped_duplicates ? `, skipped ${result.skipped_duplicates} duplicate(s)` : '');
    reloadBankTransactions();
}

function resetBankImport() {
    bankImportTransactions = [];
    document.getElementById('bankImportPreview').classList.add('hidden');
    document.getElementById('bankImportPreviewBody').innerHTML = '';
}

// ── Filters ───────────────────────────────────────────────────────────

function populateBankFilters() {
    const years = [...new Set(bankAllTransactions.map(t => t.year))].sort((a, b) => a - b);
    populateBankYearPicker(years);

    const months = sortMonthsChronologically([...new Set(bankAllTransactions.map(t => t.month))]);
    const categories = [...new Set(bankAllTransactions.map(t => t.category))].sort();
    fillBankSelect('bankMonthFilter', months);
    fillBankSelect('bankCategoryFilter', categories);
    populateBankAccountPicker(currentBankAccounts.map(a => a.name));

    if (!bankFiltersInitialized) {
        document.getElementById('bankSearchDesc').addEventListener('input', debounce(applyBankFilters, 200));
        // The collapsed net chart renders on first expand (a closed <details> has no canvas size)
        document.getElementById('bankNetDetails').addEventListener('toggle', e => {
            if (e.target.open) updateBankNetChart();
        });
        bankFiltersInitialized = true;
    }
}

function fillBankSelect(elementId, options) {
    const select = document.getElementById(elementId);
    const existing = Array.from(select.options).slice(1).map(o => o.value);
    options.forEach(option => {
        if (!existing.includes(option)) {
            const el = document.createElement('option');
            el.value = option;
            el.textContent = option;
            select.appendChild(el);
        }
    });
}

function populateBankYearPicker(years) {
    const container = document.getElementById('bankYearFilter');
    const previouslyActive = new Set(
        [...container.querySelectorAll('.year-btn:not(.year-btn-all).active')].map(b => b.dataset.year)
    );
    container.innerHTML = '';

    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'year-btn year-btn-all';
    allBtn.textContent = 'All';
    allBtn.addEventListener('click', () => {
        container.querySelectorAll('.year-btn').forEach(b => b.classList.remove('active'));
        allBtn.classList.add('active');
        applyBankFilters();
    });
    container.appendChild(allBtn);

    let anyActive = false;
    years.forEach(year => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'year-btn';
        btn.textContent = year;
        btn.dataset.year = String(year);
        if (previouslyActive.has(String(year))) { btn.classList.add('active'); anyActive = true; }
        btn.addEventListener('click', () => {
            allBtn.classList.remove('active');
            btn.classList.toggle('active');
            const selected = container.querySelectorAll('.year-btn:not(.year-btn-all).active').length > 0;
            if (!selected) allBtn.classList.add('active');
            applyBankFilters();
        });
        container.appendChild(btn);
    });
    if (!anyActive) allBtn.classList.add('active');
}

// Multi-select account pills — combine any subset of accounts
function populateBankAccountPicker(names) {
    const container = document.getElementById('bankAccountFilter');
    const previouslyActive = new Set(
        [...container.querySelectorAll('.year-btn:not(.year-btn-all).active')].map(b => b.dataset.account)
    );
    container.innerHTML = '';

    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'year-btn year-btn-all';
    allBtn.textContent = 'All';
    allBtn.addEventListener('click', () => {
        container.querySelectorAll('.year-btn').forEach(b => b.classList.remove('active'));
        allBtn.classList.add('active');
        applyBankFilters();
    });
    container.appendChild(allBtn);

    let anyActive = false;
    names.forEach(name => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'year-btn';
        btn.textContent = name;
        btn.dataset.account = name;
        if (previouslyActive.has(name)) { btn.classList.add('active'); anyActive = true; }
        btn.addEventListener('click', () => {
            allBtn.classList.remove('active');
            btn.classList.toggle('active');
            const selected = container.querySelectorAll('.year-btn:not(.year-btn-all).active').length > 0;
            if (!selected) allBtn.classList.add('active');
            applyBankFilters();
        });
        container.appendChild(btn);
    });
    if (!anyActive) allBtn.classList.add('active');
}

function getSelectedBankAccounts() {
    const container = document.getElementById('bankAccountFilter');
    const allBtn = container.querySelector('.year-btn-all');
    if (!allBtn || allBtn.classList.contains('active')) return 'all';
    return [...container.querySelectorAll('.year-btn:not(.year-btn-all).active')]
        .map(b => b.dataset.account);
}

function getSelectedBankYears() {
    const container = document.getElementById('bankYearFilter');
    const allBtn = container.querySelector('.year-btn-all');
    if (!allBtn || allBtn.classList.contains('active')) return 'all';
    return [...container.querySelectorAll('.year-btn:not(.year-btn-all).active')]
        .map(b => parseInt(b.dataset.year));
}

function clearBankDateRange() {
    document.getElementById('bankDateFromFilter').value = '';
    document.getElementById('bankDateToFilter').value = '';
    applyBankFilters();
}

function applyBankFilters() {
    const years = getSelectedBankYears();
    const month = document.getElementById('bankMonthFilter').value;
    const type = document.getElementById('bankTypeFilter').value;
    const category = document.getElementById('bankCategoryFilter').value;
    const accounts = getSelectedBankAccounts();
    const status = document.getElementById('bankStatusFilter').value;
    const dateFrom = document.getElementById('bankDateFromFilter').value;
    const dateTo = document.getElementById('bankDateToFilter').value;
    const search = document.getElementById('bankSearchDesc').value.toLowerCase();

    bankDisplayTx = bankAllTransactions.filter(t => {
        const yearMatch = years === 'all' || years.includes(t.year);
        const monthMatch = month === 'all' || t.month === month;
        const typeMatch = type === 'all' || t.type === type;
        const categoryMatch = category === 'all' || t.category === category;
        const accountMatch = accounts === 'all' || accounts.includes(t.account_name);
        const statusMatch = status === 'all'
            || (status === 'active' && !t.excluded)
            || (status === 'excluded' && t.excluded);
        const dateMatch = (!dateFrom || t.date >= dateFrom) && (!dateTo || t.date <= dateTo);
        const searchMatch = t.description.toLowerCase().includes(search);
        return yearMatch && monthMatch && typeMatch && categoryMatch && accountMatch && statusMatch && dateMatch && searchMatch;
    });
    bankFilteredTx = bankDisplayTx.filter(t => !t.excluded);

    renderBankDashboard();
}

// ── Dashboard ─────────────────────────────────────────────────────────

function renderBankDashboard() {
    updateBankSummaryCards();
    updateBankMonthlyChart();
    updateBankNetChart();
    updateBankCategoryChart();
    updateBankDescChart();
    updateBankAccountChart();
    updateBankTransactionsList();
}

function updateBankSummaryCards() {
    const income = bankFilteredTx.filter(t => t.amount > 0).reduce((s, t) => s + t.amount, 0);
    const expenses = -bankFilteredTx.filter(t => t.amount < 0).reduce((s, t) => s + t.amount, 0);
    const net = income - expenses;

    const monthKeys = new Set(bankFilteredTx.map(t => t.date.slice(0, 7)));
    const activeMonths = monthKeys.size;
    const avgMonthlyNet = activeMonths ? net / activeMonths : 0;

    document.getElementById('bankCards').innerHTML = `
        <div class="card">
            <h3>Total Income</h3>
            <div class="amount">${formatCurrency(income)}</div>
        </div>
        <div class="card">
            <h3>Total Expenses</h3>
            <div class="amount">${formatCurrency(expenses)}</div>
        </div>
        <div class="card">
            <h3>Net Cash Flow</h3>
            <div class="amount">${net >= 0 ? '▲' : '▼'} ${formatCurrency(Math.abs(net))}</div>
        </div>
        <div class="card">
            <h3>Active Months</h3>
            <div class="amount">${activeMonths}</div>
        </div>
        <div class="card">
            <h3>Avg Monthly Net</h3>
            <div class="amount">${formatCurrency(avgMonthlyNet)}</div>
        </div>
    `;
}

function bankAxisOptions() {
    return {
        x: {
            ticks: { color: getThemeColors().textColor },
            grid: { color: getThemeColors().gridColor }
        },
        y: {
            beginAtZero: true,
            ticks: { color: getThemeColors().textColor, callback: v => formatCurrency(v) },
            grid: { color: getThemeColors().gridColor }
        }
    };
}

function updateBankMonthlyChart() {
    const byMonth = {};
    bankFilteredTx.forEach(t => {
        const key = t.date.slice(0, 7);
        byMonth[key] = byMonth[key] || { income: 0, expense: 0 };
        if (t.amount >= 0) byMonth[key].income += t.amount;
        else byMonth[key].expense += -t.amount;
    });
    const months = Object.keys(byMonth).sort();

    const ctx = document.getElementById('bankMonthlyChart');
    if (bankMonthlyChart) bankMonthlyChart.destroy();
    bankMonthlyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: months,
            datasets: [
                {
                    label: 'Income',
                    data: months.map(m => byMonth[m].income),
                    borderColor: INCOME_COLOR,
                    backgroundColor: INCOME_COLOR + '20',
                    borderWidth: 3, fill: false, tension: 0.3,
                },
                {
                    label: 'Expenses',
                    data: months.map(m => byMonth[m].expense),
                    borderColor: EXPENSE_COLOR,
                    backgroundColor: EXPENSE_COLOR + '20',
                    borderWidth: 3, fill: false, tension: 0.3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: true, position: 'top', labels: { color: getThemeColors().textColor } },
                tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${formatCurrency(ctx.raw)}` } },
            },
            scales: bankAxisOptions(),
        },
    });
}

// Diverging bars around zero — collapsed by default, rendered on expand
function updateBankNetChart() {
    const details = document.getElementById('bankNetDetails');
    if (!details || !details.open) return;

    const byMonth = {};
    bankFilteredTx.forEach(t => {
        const key = t.date.slice(0, 7);
        byMonth[key] = (byMonth[key] || 0) + t.amount;
    });
    const months = Object.keys(byMonth).sort();
    const values = months.map(m => byMonth[m]);
    // Symmetric scale so zero sits in the vertical middle, rounded to a clean step
    const rawPeak = Math.max(...values.map(Math.abs), 1) * 1.1;
    const step = Math.pow(10, Math.floor(Math.log10(rawPeak)));
    const peak = Math.ceil(rawPeak / step) * step;

    const ctx = document.getElementById('bankNetChart');
    if (bankNetChart) bankNetChart.destroy();
    bankNetChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: months,
            datasets: [{
                data: values,
                backgroundColor: values.map(v => v >= 0 ? INCOME_COLOR : EXPENSE_COLOR),
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.raw >= 0 ? 'Surplus' : 'Deficit'}: ${formatCurrency(ctx.raw)}`,
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: getThemeColors().textColor },
                    grid: { display: false },
                },
                y: {
                    min: -peak,
                    max: peak,
                    ticks: { color: getThemeColors().textColor, callback: v => formatCurrency(v) },
                    grid: {
                        // Emphasize the zero baseline
                        color: c => c.tick.value === 0 ? getThemeColors().textColor : getThemeColors().gridColor,
                        lineWidth: c => c.tick.value === 0 ? 2 : 1,
                    },
                },
            },
        },
    });
}

function updateBankCategoryChart() {
    const byCategory = {};
    bankFilteredTx.forEach(t => {
        if (t.amount < 0) byCategory[t.category] = (byCategory[t.category] || 0) - t.amount;
    });
    const sorted = Object.entries(byCategory).sort(([, a], [, b]) => b - a);

    const ctx = document.getElementById('bankCategoryChart');
    if (bankCategoryChart) bankCategoryChart.destroy();
    bankCategoryChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sorted.map(([c]) => c),
            datasets: [{
                data: sorted.map(([, v]) => v),
                backgroundColor: sorted.map((_, i) => CHART_PALETTE[i % CHART_PALETTE.length]),
                borderRadius: 4,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => formatCurrency(ctx.raw) } },
            },
            scales: {
                x: {
                    ticks: { color: getThemeColors().textColor, callback: v => formatCurrency(v) },
                    grid: { color: getThemeColors().gridColor }
                },
                y: { ticks: { color: getThemeColors().textColor }, grid: { display: false } }
            },
        },
    });
}

function updateBankDescChart() {
    const byDesc = {};
    bankFilteredTx.forEach(t => {
        if (t.amount < 0) byDesc[t.description] = (byDesc[t.description] || 0) - t.amount;
    });
    const top = Object.entries(byDesc).sort(([, a], [, b]) => b - a).slice(0, 10);

    const ctx = document.getElementById('bankDescChart');
    if (bankDescChart) bankDescChart.destroy();
    bankDescChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: top.map(([d]) => d),
            datasets: [{
                label: 'Total',
                data: top.map(([, v]) => v),
                backgroundColor: 'rgba(102, 126, 234, 0.8)',
                borderColor: '#667eea',
                borderWidth: 1,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => formatCurrency(ctx.raw) } },
            },
            scales: {
                x: {
                    ticks: { color: getThemeColors().textColor, maxRotation: 45, minRotation: 45 },
                    grid: { color: getThemeColors().gridColor }
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: getThemeColors().textColor, callback: v => formatCurrency(v) },
                    grid: { color: getThemeColors().gridColor }
                }
            },
        },
    });
}

function updateBankAccountChart() {
    const byAccount = {};
    bankFilteredTx.forEach(t => {
        if (t.amount < 0) byAccount[t.account_name] = (byAccount[t.account_name] || 0) - t.amount;
    });
    const names = Object.keys(byAccount);

    const ctx = document.getElementById('bankAccountChart');
    if (bankAccountChart) bankAccountChart.destroy();
    bankAccountChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: names,
            datasets: [{
                data: names.map(n => byAccount[n]),
                backgroundColor: names.map((_, i) => CHART_PALETTE[i % CHART_PALETTE.length]),
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { color: getThemeColors().textColor } },
                tooltip: { callbacks: { label: ctx => `${ctx.label}: ${formatCurrency(ctx.raw)}` } },
            },
        },
    });
}

// ── Transactions table ────────────────────────────────────────────────

let bankSortCol = 'date', bankSortDir = -1;

function sortBankColumn(col) {
    bankSortDir = (bankSortCol === col) ? -bankSortDir : (col === 'amount' ? -1 : 1);
    bankSortCol = col;
    updateBankTransactionsList();
}

function updateBankTransactionsList() {
    const listEl = document.getElementById('bankTransactionsList');

    if (bankDisplayTx.length === 0) {
        listEl.innerHTML = `
            <div class="empty-state">
                <h3>No transactions found</h3>
                <p>Try adjusting your filters, or import a bank export above</p>
            </div>
        `;
        const pill = document.getElementById('bankExcludedPill');
        if (pill) pill.style.display = 'none';
        return;
    }

    const pageSizeEl = document.getElementById('bankTxPageSize');
    const pageSize = pageSizeEl ? parseInt(pageSizeEl.value) : 50;

    const sorted = [...bankDisplayTx].sort((a, b) => {
        let va, vb;
        if (bankSortCol === 'amount')        { va = a.amount;       vb = b.amount; }
        else if (bankSortCol === 'description') { va = a.description; vb = b.description; }
        else if (bankSortCol === 'type')     { va = a.type;         vb = b.type; }
        else if (bankSortCol === 'category') { va = a.category;     vb = b.category; }
        else if (bankSortCol === 'account')  { va = a.account_name; vb = b.account_name; }
        else                                 { va = a.date;         vb = b.date; }
        if (typeof va === 'number') return bankSortDir * (va - vb);
        return bankSortDir * String(va).localeCompare(String(vb), 'he');
    });
    const rows = pageSize === 0 ? sorted : sorted.slice(0, pageSize);

    const totalCountEl = document.getElementById('bankTxTotalCount');
    if (totalCountEl) totalCountEl.textContent = bankFilteredTx.length;

    const excludedInView = bankDisplayTx.filter(t => t.excluded);
    const pill = document.getElementById('bankExcludedPill');
    if (pill) {
        if (excludedInView.length > 0) {
            const excTotal = excludedInView.reduce((s, t) => s + t.amount, 0);
            pill.textContent = `⊘ ${excludedInView.length} excluded · ${formatCurrency(excTotal)}`;
            pill.style.display = 'inline-flex';
        } else {
            pill.style.display = 'none';
        }
    }

    const si = col => col === bankSortCol ? (bankSortDir === -1 ? ' ▼' : ' ▲') : ' ↕';
    const th = (col, label) =>
        `<th onclick="sortBankColumn('${col}')" style="cursor:pointer;white-space:nowrap;">${label}<span style="opacity:${col === bankSortCol ? 1 : 0.35};font-size:0.75em;">${si(col)}</span></th>`;

    listEl.innerHTML = `
        <table class="transactions-table">
            <thead>
                <tr>
                    ${th('date', 'Date')}
                    ${th('description', 'Description')}
                    ${th('type', 'Type')}
                    <th>Note</th>
                    ${th('category', 'Category')}
                    ${th('account', 'Account')}
                    ${th('amount', 'Amount')}
                    <th></th>
                </tr>
            </thead>
            <tbody>
                ${rows.map(t => `
                    <tr class="${t.excluded ? 'tx-excluded' : ''}">
                        <td>${escapeHtml(t.date)}</td>
                        <td>${escapeHtml(t.description)}</td>
                        <td><span class="category-cell" style="background-color:${t.type === 'income' ? INCOME_COLOR : EXPENSE_COLOR};">${t.type === 'income' ? 'Income' : 'Expense'}</span></td>
                        <td class="note-col"><input type="text" class="tx-note-input" value="${escapeHtml(t.notes || '')}"
                            placeholder="Add note…"
                            onblur="saveBankTxNote(${t.id}, this.value)"
                            onkeydown="if(event.key==='Enter')this.blur()"></td>
                        <td><span class="tx-cat-text" onclick="startEditBankCategory(this, ${t.id})">${escapeHtml(t.category)}</span></td>
                        <td>${escapeHtml(t.account_name || '')}</td>
                        <td class="amount-cell" style="color:${t.amount >= 0 ? 'var(--success-color)' : 'inherit'};">${formatCurrency(t.amount)}</td>
                        <td>
                            <div class="tx-actions">
                                <button class="btn-excl" onclick="toggleBankExclude(${t.id})" title="${t.excluded ? 'Restore' : 'Exclude'}">${t.excluded ? '↺' : '⊘'}</button>
                                <button class="btn-excl btn-delete" onclick="deleteBankTransaction(${t.id})" title="Delete permanently">🗑</button>
                            </div>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function startEditBankCategory(span, id) {
    const current = span.textContent;
    const cats = availableCategories.length ? availableCategories : [current];
    const list = cats.includes(current) ? cats : [current, ...cats];
    const opts = list.map(c => `<option value="${escapeHtml(c)}"${c === current ? ' selected' : ''}>${escapeHtml(c)}</option>`).join('');
    const td = span.parentElement;
    td.innerHTML = `<select class="tx-cat-select" onchange="changeBankTxCategory(this, ${id})">${opts}</select>`;
    const select = td.querySelector('select');
    select.focus();
    select.addEventListener('blur', () => {
        if (document.body.contains(select)) updateBankTransactionsList();
    });
}

async function changeBankTxCategory(select, id) {
    const newCategory = select.value;
    const resp = await fetch(`/api/bank-transactions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: newCategory }),
    });
    if (!resp.ok) { alert('Failed to update category'); return; }
    const txn = bankAllTransactions.find(t => t.id === id);
    if (txn) txn.category = newCategory;
    applyBankFilters();
}

async function toggleBankExclude(id) {
    const txn = bankAllTransactions.find(t => t.id === id);
    if (!txn) return;
    const resp = await fetch(`/api/bank-transactions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ excluded: !txn.excluded }),
    });
    if (!resp.ok) { alert('Failed to update transaction'); return; }
    txn.excluded = !txn.excluded ? 1 : 0;
    applyBankFilters();
}

async function saveBankTxNote(id, note) {
    const txn = bankAllTransactions.find(t => t.id === id);
    if (!txn || txn.notes === note) return;
    const resp = await fetch(`/api/bank-transactions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: note }),
    });
    if (resp.ok) txn.notes = note;
}

async function deleteBankTransaction(id) {
    const txn = bankAllTransactions.find(t => t.id === id);
    if (!txn) return;
    if (!confirm(`Permanently delete this transaction?\n\n${txn.description} — ${formatCurrency(txn.amount)} on ${txn.date}\n\nThis cannot be undone.`)) return;
    const resp = await fetch(`/api/bank-transactions/${id}`, { method: 'DELETE' });
    if (!resp.ok) { alert('Failed to delete transaction'); return; }
    bankAllTransactions = bankAllTransactions.filter(t => t.id !== id);
    applyBankFilters();
}
