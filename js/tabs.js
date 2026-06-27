// =====================================================================
// Tab Navigation
// =====================================================================
const TAB_IDS = { dashboard: 'dashboardContent', import: 'tab-import', merchants: 'tab-merchants', funds: 'tab-funds', bank: 'tab-bank' };

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

function switchTab(name) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    Object.entries(TAB_IDS).forEach(([key, id]) => {
        document.getElementById(id).classList.toggle('hidden', key !== name);
    });
    if (name === 'merchants') { if (!merchantsLoaded) loadMerchants(); loadCategoriesPanel(); loadHouseholdMembersPanel(); }
    if (name === 'dashboard') { loadExpenseData(); loadBackupInfo(); }
    if (name === 'funds') { loadFundsPanel(); }
    if (name === 'bank') { loadBankAccountsPanel(); }
}

// Load data when page loads
document.addEventListener('DOMContentLoaded', () => {
    loadExpenseData();
    loadBackupInfo();
    fetch('/api/categories').then(r => r.json()).then(cats => { availableCategories = cats; });
});
