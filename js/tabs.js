// =====================================================================
// Tab Navigation
// =====================================================================
const TAB_IDS = { dashboard: 'dashboardContent', merchants: 'tab-merchants', funds: 'tab-funds', bank: 'tab-bank', networth: 'tab-networth' };

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
    if (name === 'networth') { loadNetWorthPanel(); }
}

// On load: land on the Bank Accounts tab. Categories are awaited first
// because the bank panels build their dropdowns from them.
document.addEventListener('DOMContentLoaded', async () => {
    loadBackupInfo();
    try {
        availableCategories = await fetch('/api/categories').then(r => r.json());
    } catch (e) { /* dropdowns fall back to Uncategorized */ }
    switchTab('bank');
});
