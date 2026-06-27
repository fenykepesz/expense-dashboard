let monthlyChart, categoryChart, merchantChart, cardChart;

// Load data from external JSON file
async function loadExpenseData() {
    const dataStatus = document.getElementById('dataStatus');
    const uploadSection = document.getElementById('uploadSection');
    const dashboardContent = document.getElementById('dashboardContent');

    try {
        const response = await fetch('/api/transactions');

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (!Array.isArray(data)) {
            throw new Error('Unexpected response from server');
        }

        allExpenses = data;
        displayExpenses = [...allExpenses];
        filteredExpenses = allExpenses.filter(e => !e.excluded);

        if (allExpenses.length === 0) {
            dataStatus.className = 'data-status data-error';
            dataStatus.innerHTML = `📭 No transactions yet — use the <strong>Import</strong> tab to load your bank export.`;
            dashboardContent.classList.remove('hidden');
            initializeDashboard();
            switchTab('import');
            return;
        }

        dataStatus.className = 'data-status data-success';
        dataStatus.innerHTML = `✅ Successfully loaded ${allExpenses.length} transactions`;

        setTimeout(() => {
            dataStatus.style.display = 'none';
            // If the user already switched to a different tab, don't force the
            // dashboard back into view.
            const activeTab = document.querySelector('.tab-btn.active');
            if (activeTab && activeTab.dataset.tab !== 'dashboard') return;
            dashboardContent.classList.remove('hidden');
            initializeDashboard();
        }, 1500);

    } catch (error) {
        console.error('Error loading expense data:', error);
        dataStatus.className = 'data-status data-error';
        dataStatus.innerHTML = `❌ Could not reach the server: ${error.message}`;
    }
}

// Setup file upload functionality
function setupFileUpload() {
    const fileInput = document.getElementById('fileInput');
    const uploadSection = document.getElementById('uploadSection');
    const fileName = document.getElementById('fileName');
    const dataStatus = document.getElementById('dataStatus');
    const dashboardContent = document.getElementById('dashboardContent');

    // File input change handler
    fileInput.addEventListener('change', function (e) {
        const file = e.target.files[0];
        if (file) {
            fileName.textContent = `Selected: ${file.name}`;
            handleFileUpload(file);
        }
    });

    // Drag and drop handlers
    uploadSection.addEventListener('dragover', function (e) {
        e.preventDefault();
        uploadSection.style.background = 'rgba(102, 126, 234, 0.1)';
        uploadSection.style.borderColor = '#4a5568';
    });

    uploadSection.addEventListener('dragleave', function (e) {
        e.preventDefault();
        uploadSection.style.background = 'rgba(102, 126, 234, 0.05)';
        uploadSection.style.borderColor = '#667eea';
    });

    uploadSection.addEventListener('drop', function (e) {
        e.preventDefault();
        uploadSection.style.background = 'rgba(102, 126, 234, 0.05)';
        uploadSection.style.borderColor = '#667eea';

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const file = files[0];
            fileName.textContent = `Uploaded: ${file.name}`;
            handleFileUpload(file);
        }
    });

    // File upload handler
    function handleFileUpload(file) {
        const reader = new FileReader();

        reader.onload = function (e) {
            try {
                const content = e.target.result;
                const data = JSON.parse(content);

                if (!Array.isArray(data) || data.length === 0) {
                    throw new Error('Invalid data format or empty dataset');
                }

                allExpenses = data;
                displayExpenses = [...allExpenses];
                filteredExpenses = allExpenses.filter(e => !e.excluded);

                // Update status and show dashboard
                dataStatus.className = 'data-status data-success';
                dataStatus.innerHTML = `✅ Successfully loaded ${allExpenses.length} transactions from ${file.name}`;
                uploadSection.style.display = 'none';

                setTimeout(() => {
                    dataStatus.style.display = 'none';
                    dashboardContent.classList.remove('hidden');
                    initializeDashboard();
                }, 1500);

            } catch (error) {
                console.error('Error parsing file:', error);
                dataStatus.className = 'data-status data-error';
                dataStatus.innerHTML = `❌ Error parsing file: ${error.message}`;
            }
        };

        reader.readAsText(file);
    }
}

// Initialize dashboard
function initializeDashboard() {
    populateFilters();
    updateDashboard();
    setupEventListeners();
}

// Populate filter dropdowns
function populateFilters() {
    const years = [...new Set(allExpenses.map(exp => exp.year))].sort((a, b) => a - b);
    const months = [...new Set(allExpenses.map(exp => exp.month))];
    const categories = [...new Set(allExpenses.map(exp => exp.category))].sort();
    const cards = [...new Set(allExpenses.map(exp => exp.card))].sort();

    populateYearPicker(years);
    populateDropdown('monthFilter', sortMonthsChronologically(months));
    populateDropdown('categoryFilter', categories);
    populateDropdown('cardFilter', cards);
}

// Build year picker with toggle buttons
function populateYearPicker(years) {
    const container = document.getElementById('yearFilter');
    container.innerHTML = '';

    // "All" button
    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'year-btn year-btn-all active';
    allBtn.textContent = 'All';
    allBtn.dataset.year = 'all';
    allBtn.addEventListener('click', () => {
        // If All is clicked, deselect everything and select All
        container.querySelectorAll('.year-btn').forEach(b => b.classList.remove('active'));
        allBtn.classList.add('active');
        applyFilters();
    });
    container.appendChild(allBtn);

    // Individual year buttons
    years.forEach(year => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'year-btn';
        btn.textContent = year;
        btn.dataset.year = year;
        btn.addEventListener('click', () => {
            // Deselect "All" button
            allBtn.classList.remove('active');
            // Toggle this year
            btn.classList.toggle('active');
            // If no years are selected, revert to All
            const anySelected = container.querySelectorAll('.year-btn:not(.year-btn-all).active').length > 0;
            if (!anySelected) {
                allBtn.classList.add('active');
            }
            applyFilters();
        });
        container.appendChild(btn);
    });
}

// Get currently selected years from the picker
function getSelectedYears() {
    const container = document.getElementById('yearFilter');
    const allBtn = container.querySelector('.year-btn-all');
    if (allBtn && allBtn.classList.contains('active')) {
        return 'all';
    }
    const selected = [];
    container.querySelectorAll('.year-btn:not(.year-btn-all).active').forEach(btn => {
        selected.push(parseInt(btn.dataset.year));
    });
    return selected;
}

function populateDropdown(elementId, options) {
    const select = document.getElementById(elementId);
    const currentOptions = Array.from(select.options).slice(1).map(opt => opt.value);

    options.forEach(option => {
        if (!currentOptions.includes(option)) {
            const optionElement = document.createElement('option');
            optionElement.value = option;
            optionElement.textContent = option;
            select.appendChild(optionElement);
        }
    });
}

// Setup event listeners
function setupEventListeners() {
    // Year filter uses button click listeners (set up in populateYearPicker)
    document.getElementById('monthFilter').addEventListener('change', applyFilters);
    document.getElementById('categoryFilter').addEventListener('change', applyFilters);
    document.getElementById('cardFilter').addEventListener('change', applyFilters);
    document.getElementById('statusFilter').addEventListener('change', applyFilters);
    document.getElementById('searchMerchant').addEventListener('input', debounce(applyFilters, 200));
    document.getElementById('dateFromFilter').addEventListener('change', applyFilters);
    document.getElementById('dateToFilter').addEventListener('change', applyFilters);
}

function clearDateRange() {
    document.getElementById('dateFromFilter').value = '';
    document.getElementById('dateToFilter').value = '';
    applyFilters();
}

// Apply filters
function applyFilters() {
    const selectedYears = getSelectedYears();
    const monthFilter = document.getElementById('monthFilter').value;
    const categoryFilter = document.getElementById('categoryFilter').value;
    const cardFilter = document.getElementById('cardFilter').value;
    const searchTerm = document.getElementById('searchMerchant').value.toLowerCase();

    const statusFilter = document.getElementById('statusFilter').value;
    const dateFrom = document.getElementById('dateFromFilter').value;
    const dateTo = document.getElementById('dateToFilter').value;

    displayExpenses = allExpenses.filter(expense => {
        const yearMatch = selectedYears === 'all' || selectedYears.includes(expense.year);
        const monthMatch = monthFilter === 'all' || expense.month === monthFilter;
        const categoryMatch = categoryFilter === 'all' || expense.category === categoryFilter;
        const cardMatch = cardFilter === 'all' || expense.card === cardFilter;
        const merchantMatch = expense.merchant.toLowerCase().includes(searchTerm);
        const statusMatch = statusFilter === 'all'
            || (statusFilter === 'active' && !expense.excluded)
            || (statusFilter === 'excluded' && expense.excluded);
        const dateMatch = (!dateFrom || expense.date >= dateFrom) && (!dateTo || expense.date <= dateTo);

        return yearMatch && monthMatch && categoryMatch && cardMatch && merchantMatch && statusMatch && dateMatch;
    });
    filteredExpenses = displayExpenses.filter(e => !e.excluded);

    updateDashboard();
}

// Update entire dashboard
function updateDashboard() {
    updateSummaryCards();
    updateCharts();
    updateTransactionsList();
}

// Update summary cards
function updateSummaryCards() {
    const totalSpent = filteredExpenses.reduce((sum, exp) => sum + exp.amount, 0);
    const avgTransaction = filteredExpenses.length > 0 ? totalSpent / filteredExpenses.length : 0;
    const transactionCount = filteredExpenses.length;

    // Count unique year-month pairs that have actual spending (> 0)
    // Dec 2024 and Dec 2025 count as 2 separate months
    // Months with $0 spending are excluded as data-less
    const monthTotals = {};
    filteredExpenses.forEach(exp => {
        const key = `${exp.year}-${exp.month}`;
        monthTotals[key] = (monthTotals[key] || 0) + exp.amount;
    });
    // Only count months where total spending > 0
    const monthsWithData = Object.values(monthTotals).filter(total => total > 0).length;
    const monthlyAverage = monthsWithData > 0 ? totalSpent / monthsWithData : 0;

    document.getElementById('summaryCards').innerHTML = `
        <div class="card">
            <h3>Total Spent</h3>
            <div class="amount">${formatCurrency(totalSpent)}</div>
        </div>
        <div class="card">
            <h3>Transactions</h3>
            <div class="amount">${transactionCount}</div>
        </div>
        <div class="card">
            <h3>Average per Transaction</h3>
            <div class="amount">${formatCurrency(avgTransaction)}</div>
        </div>
        <div class="card">
            <h3>Active Months</h3>
            <div class="amount">${monthsWithData}</div>
        </div>
        <div class="card">
            <h3>Monthly Average</h3>
            <div class="amount">${formatCurrency(monthlyAverage)}</div>
        </div>
    `;
}

// Update all charts
function updateCharts() {
    updateMonthlyChart();
    updateCategoryChart();
    updateMerchantChart();
    updateCardChart();
}

// Monthly spending chart (Year-over-Year Comparison)
function updateMonthlyChart() {
    // Group data by year and month
    const yearlyData = {};
    const years = [...new Set(filteredExpenses.map(exp => exp.year))].sort();

    // If "All Years" is selected, we show multiple lines.
    // If a specific year is selected, we still show standard line.

    years.forEach(year => {
        yearlyData[year] = {};
    });

    filteredExpenses.forEach(exp => {
        yearlyData[exp.year][exp.month] = (yearlyData[exp.year][exp.month] || 0) + exp.amount;
    });

    const allMonths = Object.keys(sortMonthsChronologically([
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]));

    // Pre-defined colors for different years to keep consistency
    const colors = [
        '#667eea', // Blue
        '#f5576c', // Pink/Red
        '#43e97b', // Green
        '#f093fb', // Purple
        '#fa709a'  // Orange-ish
    ];

    const datasets = years.map((year, index) => {
        return {
            label: year.toString(),
            data: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
                .map(month => yearlyData[year][month] || 0),
            borderColor: colors[index % colors.length],
            backgroundColor: colors[index % colors.length] + '20', // Add transparency
            borderWidth: 3,
            fill: false, // Don't fill for comparison clarity
            tension: 0.4
        };
    });

    const ctx = document.getElementById('monthlyChart');
    if (monthlyChart) monthlyChart.destroy();

    monthlyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: { color: getThemeColors().textColor }
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return context.dataset.label + ': ' + formatCurrency(context.raw);
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: getThemeColors().textColor },
                    grid: { color: getThemeColors().gridColor }
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: getThemeColors().textColor,
                        callback: function (value) {
                            return formatCurrency(value);
                        }
                    },
                    grid: { color: getThemeColors().gridColor }
                }
            }
        }
    });
}

// Category spending chart
function updateCategoryChart() {
    const categoryData = {};
    filteredExpenses.forEach(exp => {
        categoryData[exp.category] = (categoryData[exp.category] || 0) + exp.amount;
    });

    const sorted = Object.entries(categoryData).sort(([, a], [, b]) => b - a);
    const categories = sorted.map(([c]) => c);
    const amounts = sorted.map(([, v]) => v);

    const colors = [
        '#667eea', '#764ba2', '#f093fb', '#f5576c',
        '#4facfe', '#00f2fe', '#43e97b', '#38f9d7',
        '#ffecd2', '#fcb69f', '#a8edea', '#fed6e3',
        '#ff9a9e', '#a18cd1', '#ffeaa7', '#dfe6e9'
    ];

    const ctx = document.getElementById('categoryChart');
    if (categoryChart) categoryChart.destroy();

    categoryChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: categories,
            datasets: [{
                data: amounts,
                backgroundColor: categories.map((_, i) => colors[i % colors.length]),
                borderRadius: 4,
            }]
        },
        options: {
            indexAxis: 'y',
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
                    ticks: {
                        color: getThemeColors().textColor,
                        callback: v => formatCurrency(v)
                    },
                    grid: { color: getThemeColors().gridColor }
                },
                y: {
                    ticks: { color: getThemeColors().textColor },
                    grid: { display: false }
                }
            }
        }
    });
}

// Top merchants chart
function updateMerchantChart() {
    const merchantData = {};
    filteredExpenses.forEach(exp => {
        merchantData[exp.merchant] = (merchantData[exp.merchant] || 0) + exp.amount;
    });

    const sortedMerchants = Object.entries(merchantData)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 10);

    const merchants = sortedMerchants.map(([merchant,]) => merchant);
    const amounts = sortedMerchants.map(([, amount]) => amount);

    const ctx = document.getElementById('merchantChart');
    if (merchantChart) merchantChart.destroy();

    merchantChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: merchants,
            datasets: [{
                label: 'Total Spent',
                data: amounts,
                backgroundColor: 'rgba(102, 126, 234, 0.8)',
                borderColor: '#667eea',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    ticks: {
                        color: getThemeColors().textColor,
                        maxRotation: 45,
                        minRotation: 45
                    },
                    grid: { color: getThemeColors().gridColor }
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: getThemeColors().textColor,
                        callback: function (value) {
                            return formatCurrency(value);
                        }
                    },
                    grid: { color: getThemeColors().gridColor }
                }
            }
        }
    });
}

// Card spending chart
function updateCardChart() {
    const cardData = {};
    filteredExpenses.forEach(exp => {
        cardData[exp.card] = (cardData[exp.card] || 0) + exp.amount;
    });

    const cards = Object.keys(cardData);
    const amounts = Object.values(cardData);

    const ctx = document.getElementById('cardChart');
    if (cardChart) cardChart.destroy();

    cardChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: cards.map(card => `Card *${card}`),
            datasets: [{
                data: amounts,
                backgroundColor: [
                    '#667eea', '#764ba2', '#f093fb', '#f5576c',
                    '#4facfe', '#00f2fe', '#43e97b', '#38f9d7'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return context.label + ': ' + formatCurrency(context.raw);
                        }
                    }
                }
            }
        }
    });
}

// ── Transaction table: sort + resizable columns ───────────────────────
let txSortCol = 'date', txSortDir = -1;

const TX_COL_DEFAULTS = { date:110, vendor:220, note:170, category:150, card:95, amount:95, action:64 };

function getTxColWidths() {
    try { return Object.assign({}, TX_COL_DEFAULTS, JSON.parse(localStorage.getItem('txColWidths'))); }
    catch { return Object.assign({}, TX_COL_DEFAULTS); }
}

function saveTxColWidths(w) { localStorage.setItem('txColWidths', JSON.stringify(w)); }

function sortTxColumn(col) {
    txSortDir = (txSortCol === col) ? -txSortDir : (col === 'amount' ? -1 : 1);
    txSortCol = col;
    updateTransactionsList();
}

function initTxResize(widths) {
    const table = document.querySelector('#transactionsList table');
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
            const onUp = ev => {
                handle.classList.remove('resizing');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                const keys = Object.keys(TX_COL_DEFAULTS);
                const cols = table.querySelectorAll('col');
                const saved = {};
                keys.forEach((k, j) => { saved[k] = parseInt(cols[j].style.width); });
                saveTxColWidths(saved);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    });
}

// Update transactions list
function updateTransactionsList() {
    const transactionsList = document.getElementById('transactionsList');

    if (displayExpenses.length === 0) {
        transactionsList.innerHTML = `
            <div class="empty-state">
                <h3>No transactions found</h3>
                <p>Try adjusting your filters or add some expense data</p>
            </div>
        `;
        const pill = document.getElementById('excludedPill');
        if (pill) pill.style.display = 'none';
        return;
    }

    const pageSizeEl = document.getElementById('txPageSize');
    const pageSize = pageSizeEl ? parseInt(pageSizeEl.value) : 0;

    const sorted = [...displayExpenses].sort((a, b) => {
        let va, vb;
        if (txSortCol === 'amount')    { va = a.amount;   vb = b.amount; }
        else if (txSortCol === 'vendor'){ va = a.merchant; vb = b.merchant; }
        else if (txSortCol === 'category'){ va = a.category; vb = b.category; }
        else if (txSortCol === 'card') { va = a.card;    vb = b.card; }
        else                           { va = a.date;    vb = b.date; }
        if (typeof va === 'number') return txSortDir * (va - vb);
        return txSortDir * String(va).localeCompare(String(vb), 'he');
    });
    const sortedTransactions = pageSize === 0 ? sorted : sorted.slice(0, pageSize);

    const totalCountEl = document.getElementById('txTotalCount');
    if (totalCountEl) totalCountEl.textContent = filteredExpenses.length;

    const excludedInView = displayExpenses.filter(e => e.excluded);
    const pill = document.getElementById('excludedPill');
    if (pill) {
        if (excludedInView.length > 0) {
            const excTotal = excludedInView.reduce((s, e) => s + e.amount, 0);
            pill.textContent = `⊘ ${excludedInView.length} excluded · ${formatCurrency(excTotal)}`;
            pill.style.display = 'inline-flex';
        } else {
            pill.style.display = 'none';
        }
    }

    const si = col => col === txSortCol ? (txSortDir === -1 ? ' ▼' : ' ▲') : ' ↕';
    const th = (col, label, extra='') =>
        `<th onclick="sortTxColumn('${col}')" style="cursor:pointer;position:relative;${extra}">${label}<span style="opacity:${col===txSortCol?1:0.35};font-size:0.75em;">${si(col)}</span><div class="col-resize-handle" onclick="event.stopPropagation()"></div></th>`;

    const w = getTxColWidths();

    transactionsList.innerHTML = `
        <table class="transactions-table" style="table-layout:fixed;width:100%;">
            <colgroup>
                <col style="width:${w.date}px;">
                <col style="width:${w.vendor}px;">
                <col style="width:${w.note}px;">
                <col style="width:${w.category}px;">
                <col style="width:${w.card}px;">
                <col style="width:${w.amount}px;">
                <col style="width:${w.action}px;">
            </colgroup>
            <thead>
                <tr>
                    ${th('date','Date')}
                    ${th('vendor','Vendor Name')}
                    <th style="position:relative;">Note<div class="col-resize-handle" onclick="event.stopPropagation()"></div></th>
                    ${th('category','Category')}
                    ${th('card','Card Number')}
                    ${th('amount','Amount')}
                    <th></th>
                </tr>
            </thead>
            <tbody>
                ${sortedTransactions.map(t => `
                    <tr class="${t.excluded ? 'tx-excluded' : ''}">
                        <td>${escapeHtml(t.date)}</td>
                        <td style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(t.merchant)}</td>
                        <td><input type="text" class="tx-note-input" value="${escapeHtml(t.notes || '')}"
                            placeholder="Add note…"
                            onblur="saveTxNote(${t.id}, this.value)"
                            onkeydown="if(event.key==='Enter')this.blur()"></td>
                        <td><span class="tx-cat-text" onclick="startEditCategory(this, '${escapeHtml(t.merchant).replace(/'/g, "\\'")}')">${escapeHtml(t.category)}</span></td>
                        <td class="card-cell">*${escapeHtml(t.card)}</td>
                        <td class="amount-cell">${formatCurrency(t.amount)}</td>
                        <td>
                            <div class="tx-actions">
                                <button class="btn-excl" onclick="toggleExclude(${t.id})" title="${t.excluded ? 'Restore' : 'Exclude'}">${t.excluded ? '↺' : '⊘'}</button>
                                <button class="btn-excl btn-delete" onclick="deleteTransaction(${t.id})" title="Delete permanently">🗑</button>
                            </div>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    initTxResize(w);
}

function startEditCategory(span, merchant) {
    const current = span.textContent;
    const cats = availableCategories.length ? availableCategories : [current];
    const list = cats.includes(current) ? cats : [current, ...cats];
    const opts = list.map(c => `<option value="${escapeHtml(c)}"${c === current ? ' selected' : ''}>${escapeHtml(c)}</option>`).join('');
    const td = span.parentElement;
    td.innerHTML = `<select class="tx-cat-select" onchange="changeTxCategory(this, '${merchant.replace(/'/g, "\\'")}')">${opts}</select>`;
    const select = td.querySelector('select');
    select.focus();
    select.addEventListener('blur', () => {
        // If no change was saved, just revert this cell back to a static label.
        if (document.body.contains(select)) updateTransactionsList();
    });
}

async function changeTxCategory(select, merchant) {
    const newCategory = select.value;
    const resp = await fetch('/api/merchants', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ merchant, new_category: newCategory, save_rule: true }),
    });
    if (!resp.ok) { alert('Failed to update category'); select.value = select.dataset.prev || select.value; return; }
    // Update all in-memory transactions for this merchant
    allExpenses.forEach(e => { if (e.merchant === merchant) e.category = newCategory; });
    filteredExpenses = displayExpenses.filter(e => !e.excluded);
    updateDashboard();
}

async function saveTxNote(id, note) {
    const expense = allExpenses.find(e => e.id === id);
    if (!expense || expense.notes === note) return;
    const resp = await fetch(`/api/transactions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: note }),
    });
    if (resp.ok) expense.notes = note;
}

async function toggleExclude(id) {
    const expense = allExpenses.find(e => e.id === id);
    if (!expense) return;
    const newExcluded = !expense.excluded;
    const resp = await fetch(`/api/transactions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ excluded: newExcluded }),
    });
    if (!resp.ok) { alert('Failed to update transaction'); return; }
    expense.excluded = newExcluded;
    filteredExpenses = displayExpenses.filter(e => !e.excluded);
    updateDashboard();
}

async function deleteTransaction(id) {
    const expense = allExpenses.find(e => e.id === id);
    if (!expense) return;
    if (!confirm(`Permanently delete this transaction?\n\n${expense.merchant} — ${formatCurrency(expense.amount)} on ${expense.date}\n\nThis cannot be undone.`)) return;
    const resp = await fetch(`/api/transactions/${id}`, { method: 'DELETE' });
    if (!resp.ok) { alert('Failed to delete transaction'); return; }
    allExpenses = allExpenses.filter(e => e.id !== id);
    displayExpenses = displayExpenses.filter(e => e.id !== id);
    filteredExpenses = filteredExpenses.filter(e => e.id !== id);
    updateDashboard();
}
