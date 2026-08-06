let currentBankAccounts = [];
let selectedBankAccountId = null;
let currentBankTransactions = [];

async function loadBankAccountsPanel() {
    const [accountsResp, membersResp] = await Promise.all([
        fetch('/api/bank-accounts'),
        fetch('/api/household-members'),
    ]);
    currentBankAccounts = await accountsResp.json();
    const members = await membersResp.json();

    const ownerOpts = '<option value="">No owner</option>' +
        members.map(m => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join('');
    document.getElementById('newBankAccountOwnerInput').innerHTML = ownerOpts;

    const catOpts = (availableCategories.length ? availableCategories : ['Uncategorized'])
        .map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    document.getElementById('newBankTxCategory').innerHTML = catOpts;

    renderBankAccountsList();
    renderBankAccountSelect();
}

function renderBankAccountsList() {
    const list = document.getElementById('bankAccountsList');
    if (!currentBankAccounts.length) {
        list.innerHTML = '<span style="color:var(--text-secondary);font-size:0.9em;">No bank accounts yet — add one above.</span>';
        return;
    }
    list.innerHTML = currentBankAccounts.map(a => `
        <span class="cat-pill">
            ${escapeHtml(a.name)}
            <span class="cat-pill-count">${a.account_number ? '*' + escapeHtml(a.account_number) + ' · ' : ''}${a.owner_name ? escapeHtml(a.owner_name) : 'No owner'}</span>
            <button class="cat-pill-del" title="Delete account" onclick="deleteBankAccount(${a.id}, '${escapeHtml(a.name).replace(/'/g, "\\'")}')">✕</button>
        </span>
    `).join('');
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
        renderBankTransactionsTable([]);
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
}

async function deleteBankAccount(id, name) {
    if (!confirm(`Delete bank account "${name}"? Its transaction history will no longer be shown.`)) return;
    const resp = await fetch(`/api/bank-accounts/${id}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete bank account'); return; }
    currentBankAccounts = result.accounts;
    renderBankAccountsList();
    renderBankAccountSelect();
}

async function onBankAccountChange() {
    const select = document.getElementById('bankAccountSelect');
    selectedBankAccountId = select.value || null;
    if (!selectedBankAccountId) {
        renderBankTransactionsTable([]);
        return;
    }
    const resp = await fetch(`/api/bank-accounts/${selectedBankAccountId}/transactions`);
    currentBankTransactions = await resp.json();
    renderBankTransactionsTable(currentBankTransactions);
}

function renderBankTransactionsTable(transactions) {
    const body = document.getElementById('bankTransactionsBody');
    if (!transactions.length) {
        body.innerHTML = '<tr><td colspan="6" class="no-data">Select an account above to see its transactions.</td></tr>';
        return;
    }
    body.innerHTML = transactions.map(t => `
        <tr class="${t.excluded ? 'tx-excluded' : ''}">
            <td>${escapeHtml(t.date)}</td>
            <td>${escapeHtml(t.description)}</td>
            <td><input type="text" class="tx-note-input" value="${escapeHtml(t.notes || '')}"
                placeholder="Add note…"
                onblur="saveBankTxNote(${t.id}, this.value)"
                onkeydown="if(event.key==='Enter')this.blur()"></td>
            <td><span class="category-cell">${escapeHtml(t.category)}</span></td>
            <td class="amount-cell" style="color:${t.amount >= 0 ? 'var(--success-color)' : 'inherit'};">${formatCurrency(t.amount)}</td>
            <td>
                <div class="tx-actions">
                    <button class="btn-excl" onclick="toggleBankExclude(${t.id})" title="${t.excluded ? 'Restore' : 'Exclude'}">${t.excluded ? '↺' : '⊘'}</button>
                    <button class="btn-excl btn-delete" onclick="deleteBankTransaction(${t.id})" title="Delete permanently">🗑</button>
                </div>
            </td>
        </tr>
    `).join('');
}

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
    renderBankTransactionsTable(result.transactions);
}

async function toggleBankExclude(id) {
    const txn = currentBankTransactions.find(t => t.id === id);
    if (!txn) return;
    const resp = await fetch(`/api/bank-transactions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ excluded: !txn.excluded }),
    });
    if (!resp.ok) { alert('Failed to update transaction'); return; }
    onBankAccountChange();
}

async function saveBankTxNote(id, note) {
    await fetch(`/api/bank-transactions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: note }),
    });
}

async function deleteBankTransaction(id) {
    if (!confirm('Permanently delete this transaction? This cannot be undone.')) return;
    const resp = await fetch(`/api/bank-transactions/${id}`, { method: 'DELETE' });
    if (!resp.ok) { alert('Failed to delete transaction'); return; }
    onBankAccountChange();
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
    currentBankTransactions = result.transactions;
    renderBankTransactionsTable(currentBankTransactions);
}

function resetBankImport() {
    bankImportTransactions = [];
    document.getElementById('bankImportPreview').classList.add('hidden');
    document.getElementById('bankImportPreviewBody').innerHTML = '';
}
