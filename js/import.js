let importedTransactions = [];

const importDropzone = document.getElementById('importDropzone');
const importFileInput = document.getElementById('importFileInput');

importFileInput.addEventListener('change', e => {
    const file = e.target.files[0];
    if (file) selectImportFile(file);
});

importDropzone.addEventListener('dragover', e => { e.preventDefault(); importDropzone.classList.add('drag-over'); });
importDropzone.addEventListener('dragleave', () => importDropzone.classList.remove('drag-over'));
importDropzone.addEventListener('drop', e => {
    e.preventDefault();
    importDropzone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) selectImportFile(file);
});

const DROPZONE_FULL_HTML = `
    <div style="font-size:2em;">📂</div>
    <strong>Drag &amp; drop a file here</strong>
    <p>or <span style="color:#667eea;cursor:pointer;" onclick="document.getElementById('importFileInput').click()">browse to choose</span></p>
    <p id="importFileName" style="color:#667eea;margin-top:8px;font-weight:600;"></p>`;

function selectImportFile(file) {
    const dz = document.getElementById('importDropzone');
    dz.classList.add('compact');
    dz.innerHTML = `
        <span style="font-size:0.9em;">📄 <strong>${escapeHtml(file.name)}</strong></span>
        <span style="font-size:0.82em;color:#667eea;cursor:pointer;white-space:nowrap;margin-left:12px;"
              onclick="document.getElementById('importFileInput').click()">Change file</span>`;
    document.getElementById('importBtn').disabled = false;
    document.getElementById('importBtn')._file = file;
    document.getElementById('importPreview').classList.add('hidden');
}

async function runImport() {
    const file = document.getElementById('importBtn')._file;
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    const usd = document.getElementById('fxUsd').value;
    const eur = document.getElementById('fxEur').value;
    const gbp = document.getElementById('fxGbp').value;
    if (usd) formData.append('usd_rate', usd);
    if (eur) formData.append('eur_rate', eur);
    if (gbp) formData.append('gbp_rate', gbp);

    document.getElementById('importBtn').textContent = 'Processing…';
    document.getElementById('importBtn').disabled = true;

    try {
        const resp = await fetch('/api/import', { method: 'POST', body: formData });
        const result = await resp.json();
        if (!resp.ok) { alert(result.error || 'Import failed'); return; }

        importedTransactions = result.transactions;
        showImportPreview(result);
    } catch (err) {
        alert('Import error: ' + err.message);
    } finally {
        document.getElementById('importBtn').textContent = 'Import';
        document.getElementById('importBtn').disabled = false;
    }
}

function importCategoryOpts(current) {
    const cats = availableCategories.length ? availableCategories : ['Uncategorized'];
    const list = cats.includes(current) ? cats : [current, ...cats];
    return list.map(c =>
        `<option value="${escapeHtml(c)}"${c === current ? ' selected' : ''}>${escapeHtml(c)}</option>`
    ).join('');
}

function onImportCatChange(select, idx) {
    importedTransactions[idx].category = select.value;
    const row = select.closest('tr');
    row.classList.toggle('import-uncategorized', select.value === 'Uncategorized');
}

function renderImportPreviewBody() {
    const visible = importedTransactions;
    document.getElementById('importPreviewBody').innerHTML = visible.map((t, i) => `
        <tr class="${t.category === 'Uncategorized' ? 'import-uncategorized' : ''}">
            <td>${escapeHtml(t.date)}</td>
            <td>${escapeHtml(t.merchant)}</td>
            <td>
                <select style="font-size:0.82em;padding:3px 6px;border-radius:5px;border:1px solid var(--input-border);background:var(--input-bg);color:var(--text-primary);"
                    onchange="onImportCatChange(this, ${i})">
                    ${importCategoryOpts(t.category)}
                </select>
            </td>
            <td class="card-cell">*${escapeHtml(t.card)}</td>
            <td class="amount-cell">${formatCurrency(t.amount)}</td>
        </tr>
    `).join('');
}

function showImportPreview(result) {
    const preview = document.getElementById('importPreview');
    const warning = document.getElementById('importDuplicateWarning');

    const uncatCount = result.transactions.filter(t => t.category === 'Uncategorized').length;
    let summary = `Found ${result.transactions.length} transactions`;
    if (uncatCount > 0) summary += ` — <span style="color:#ffc107;">⚠ ${uncatCount} uncategorized</span>`;
    document.getElementById('importSummary').innerHTML = summary;

    if (result.duplicate_count > 0) {
        warning.textContent = `⚠️ ${result.duplicate_count} transaction(s) look like duplicates (same date, merchant, amount, and card already in the database). You can still import — duplicates will be added as separate entries.`;
        warning.classList.remove('hidden');
    } else {
        warning.classList.add('hidden');
    }

    // Skipped (zero / negative) panel
    const skipped = result.skipped || [];
    const skippedPanel = document.getElementById('skippedPanel');
    if (skipped.length > 0) {
        document.getElementById('skippedSummary').textContent =
            `ℹ️ ${skipped.length} transaction${skipped.length > 1 ? 's' : ''} skipped (zero or negative amount) — click to view`;
        document.getElementById('skippedBody').innerHTML = skipped.map(t => `
            <tr>
                <td>${escapeHtml(t.date)}</td>
                <td>${escapeHtml(t.merchant)}</td>
                <td class="card-cell">*${escapeHtml(t.card)}</td>
                <td class="amount-cell" style="color:var(--text-secondary);">${formatCurrency(t.amount)}</td>
                <td style="color:var(--text-secondary);font-size:0.85em;">${t.skip_reason === 'negative' ? 'Refund / credit' : 'Zero amount'}</td>
            </tr>
        `).join('');
        skippedPanel.classList.remove('hidden');
    } else {
        skippedPanel.classList.add('hidden');
    }

    renderImportPreviewBody();
    preview.classList.remove('hidden');
}

async function confirmImport() {
    document.getElementById('importConfirmBtn').textContent = 'Saving…';
    document.getElementById('importConfirmBtn').disabled = true;

    try {
        const resp = await fetch('/api/import/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transactions: importedTransactions }),
        });
        const result = await resp.json();
        if (!resp.ok) { alert(result.error || 'Save failed'); return; }

        alert(`✅ Successfully imported ${result.inserted} transactions.`);
        resetImport();
        // Refresh dashboard data
        const data = await fetch('/api/transactions').then(r => r.json());
        allExpenses = data;
        displayExpenses = [...allExpenses];
        filteredExpenses = allExpenses.filter(e => !e.excluded);
        updateDashboard();
        merchantsLoaded = false;
        switchTab('dashboard');
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        document.getElementById('importConfirmBtn').textContent = '✅ Confirm Import';
        document.getElementById('importConfirmBtn').disabled = false;
    }
}

function resetImport() {
    importedTransactions = [];
    document.getElementById('importFileInput').value = '';
    document.getElementById('importBtn').disabled = true;
    document.getElementById('importBtn')._file = null;
    document.getElementById('importPreview').classList.add('hidden');
    const dz = document.getElementById('importDropzone');
    dz.classList.remove('compact');
    dz.innerHTML = DROPZONE_FULL_HTML;
}
