let allMerchants = [];
let merchantsLoaded = false;

async function loadMerchants() {
    const [merchantResp, catResp] = await Promise.all([
        fetch('/api/merchants'),
        fetch('/api/categories'),
    ]);
    allMerchants = await merchantResp.json();
    availableCategories = await catResp.json();

    // Populate category filter with categories actually present in the data
    const usedCats = [...new Set(allMerchants.map(m => m.category))].sort();
    const catFilter = document.getElementById('merchantCatFilter');
    catFilter.innerHTML = '<option value="all">All Categories</option>' +
        usedCats.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    catFilter.value = 'all';

    applyMerchantsFiltersAndSort();
    merchantsLoaded = true;
}

function renderMerchantTable(merchants) {
    const body = document.getElementById('merchantsBody');
    if (!merchants.length) {
        body.innerHTML = '<tr><td colspan="5" class="no-data">No transactions in database yet.</td></tr>';
        return;
    }
    body.innerHTML = merchants.map(m => {
        const cats = availableCategories.includes(m.category)
            ? availableCategories
            : [m.category, ...availableCategories];
        const opts = cats.map(c =>
            `<option value="${escapeHtml(c)}"${c === m.category ? ' selected' : ''}>${escapeHtml(c)}</option>`
        ).join('');
        return `
        <tr data-merchant="${escapeHtml(m.merchant)}">
            <td>${escapeHtml(m.merchant)}</td>
            <td>
                <select class="merchant-cat-select" onchange="onMerchantCatChange(this)">
                    ${opts}
                </select>
            </td>
            <td style="text-align:center;">${m.count}</td>
            <td style="text-align:center;">
                <label class="save-rule-label">
                    <input type="checkbox" class="merchant-save-rule"> Save rule
                    <span class="tooltip-icon" title="Also saves this merchant→category mapping to category_rules.json, so future imports categorize it automatically.">ℹ</span>
                </label>
            </td>
            <td>
                <button class="btn-save-merchant" onclick="saveMerchant(this)">Save</button>
            </td>
        </tr>`;
    }).join('');
}

function onMerchantCatChange(select) {
    const row = select.closest('tr');
    row.querySelector('.btn-save-merchant').classList.add('visible');
}

async function saveMerchant(btn) {
    const row = btn.closest('tr');
    const merchant = row.dataset.merchant;
    const newCategory = row.querySelector('.merchant-cat-select').value;
    const saveRule = row.querySelector('.merchant-save-rule').checked;

    btn.textContent = 'Saving…';
    btn.disabled = true;

    try {
        const resp = await fetch('/api/merchants', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ merchant, new_category: newCategory, save_rule: saveRule }),
        });
        if (!resp.ok) { alert('Save failed'); return; }
        btn.textContent = '✓ Saved';
        btn.style.background = '#4caf50';
        setTimeout(() => {
            btn.textContent = 'Save';
            btn.style.background = '';
            btn.classList.remove('visible');
            btn.disabled = false;
            row.querySelector('.merchant-save-rule').checked = false;
        }, 1500);
        // Update local cache
        const m = allMerchants.find(x => x.merchant === merchant);
        if (m) m.category = newCategory;
        // Refresh dashboard if on dashboard tab
        const dashVisible = !document.getElementById('dashboardContent').classList.contains('hidden');
        if (dashVisible) {
            allExpenses.forEach(e => { if (e.merchant === merchant) e.category = newCategory; });
            filteredExpenses.forEach(e => { if (e.merchant === merchant) e.category = newCategory; });
            updateDashboard();
        }
    } catch (err) {
        alert('Error: ' + err.message);
        btn.disabled = false;
    }
}

let merchantSortCol = 'count';
let merchantSortAsc = false;

function sortMerchants(col) {
    if (merchantSortCol === col) {
        merchantSortAsc = !merchantSortAsc;
    } else {
        merchantSortCol = col;
        merchantSortAsc = col !== 'count'; // count defaults desc, others asc
    }
    // Update header indicators
    document.querySelectorAll('.sortable-th').forEach(th => {
        const isActive = th.dataset.col === col;
        th.classList.toggle('sort-asc', isActive && merchantSortAsc);
        th.classList.toggle('sort-desc', isActive && !merchantSortAsc);
        th.querySelector('.sort-indicator').textContent = isActive ? (merchantSortAsc ? '▲' : '▼') : '↕';
    });
    applyMerchantsFiltersAndSort();
}

function applyMerchantsFiltersAndSort() {
    const q = document.getElementById('merchantSearch').value.toLowerCase();
    const cat = document.getElementById('merchantCatFilter').value;

    let result = allMerchants.filter(m => {
        const matchesText = m.merchant.toLowerCase().includes(q);
        const matchesCat = cat === 'all' || m.category === cat;
        return matchesText && matchesCat;
    });

    result = [...result].sort((a, b) => {
        let va = a[merchantSortCol], vb = b[merchantSortCol];
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        if (va < vb) return merchantSortAsc ? -1 : 1;
        if (va > vb) return merchantSortAsc ? 1 : -1;
        return 0;
    });

    renderMerchantTable(result);
}

// Keep old name as alias so existing oninput still works
function filterMerchantTable() { applyMerchantsFiltersAndSort(); }

async function loadCategoriesPanel() {
    const resp = await fetch('/api/categories/details');
    const cats = await resp.json();
    const list = document.getElementById('categoriesList');
    list.innerHTML = cats.map(c => `
        <span class="cat-pill${c.is_builtin ? '' : ' is-custom'}">
            ${escapeHtml(c.name)}
            <span class="cat-pill-count" title="${c.count} merchant${c.count !== 1 ? 's' : ''}">(${c.count})</span>
            ${c.name === 'Uncategorized'
                ? '<span class="cat-pill-lock" title="Required — cannot be deleted">🔒</span>'
                : `<button class="cat-pill-del" title="Delete category" onclick="deleteCategory('${escapeHtml(c.name).replace(/'/g, "\\'")}')">✕</button>`
            }
        </span>
    `).join('');
}

async function addNewCategory() {
    const input = document.getElementById('newCategoryInput');
    const name = input.value.trim();
    if (!name) return;
    const resp = await fetch('/api/categories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add category'); return; }
    input.value = '';
    await loadMerchants();
    loadCategoriesPanel();
    alert(`✅ Category "${name}" added.`);
}

async function deleteCategory(name) {
    if (!confirm(`Delete category "${name}"?\n\nAll transactions in this category will be moved to "Uncategorized".`)) return;
    const resp = await fetch(`/api/categories/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to delete category'); return; }
    availableCategories = result.categories;
    allMerchants.forEach(m => { if (m.category === name) m.category = 'Uncategorized'; });
    allExpenses.forEach(e => { if (e.category === name) e.category = 'Uncategorized'; });
    filteredExpenses.forEach(e => { if (e.category === name) e.category = 'Uncategorized'; });
    loadCategoriesPanel();
    await loadMerchants();
}
