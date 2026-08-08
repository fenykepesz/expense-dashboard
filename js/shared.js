// Shared state and helpers used across multiple tabs
// CVD-validated categorical palette (fixed order, color follows the entity)
const CHART_PALETTE = ['#667eea', '#0d9488', '#c2410c', '#a21caf', '#4d7c0f'];
const INCOME_COLOR = '#0d9488';
const EXPENSE_COLOR = '#c2410c';

// Self-declared risk scale, shared by funds and bank accounts.
// 0 = Not Rated (default); the user always assigns this themselves —
// the tool never infers or suggests a level for a specific fund.
const RISK_LEVEL_LABELS = {
    0: 'Not Rated',
    1: 'Capital Guaranteed',
    2: 'Low Risk',
    3: 'Moderate Risk',
    4: 'High Risk',
    5: 'Very High Risk',
};
const RISK_LEVEL_TOOLTIP =
    'Self-declared risk (you choose, not the tool):\n' +
    '1 - Capital Guaranteed: checking/savings, money-market (כספית)\n' +
    '2 - Low Risk: mostly bonds (מסלול סולידי / אג"ח)\n' +
    '3 - Moderate Risk: mixed stock/bond blend (מסלול כללי)\n' +
    '4 - High Risk: mostly equities (מסלול מנייתי)\n' +
    '5 - Very High Risk: concentrated/leveraged (single stocks, crypto)';

function riskLevelOptions(selected) {
    return Object.entries(RISK_LEVEL_LABELS)
        .map(([val, label]) => `<option value="${val}"${Number(selected) === Number(val) ? ' selected' : ''}>${label}</option>`)
        .join('');
}

let allExpenses = [];
let filteredExpenses = [];
let displayExpenses = [];
let availableCategories = [];

// --- Theme Logic ---
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.getElementById('themeToggle').textContent = '☀️';
    } else {
        document.documentElement.removeAttribute('data-theme');
        document.getElementById('themeToggle').textContent = '🌙';
    }
}

document.getElementById('themeToggle').addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    if (newTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.getElementById('themeToggle').textContent = '☀️';
        localStorage.setItem('theme', 'dark');
    } else {
        document.documentElement.removeAttribute('data-theme');
        document.getElementById('themeToggle').textContent = '🌙';
        localStorage.setItem('theme', 'light');
    }
    updateDashboard(); // Re-render charts to update colors
    if (typeof renderNetWorth === 'function') renderNetWorth();
    if (typeof renderBankDashboard === 'function') renderBankDashboard();
});

// Initialize Theme on Load
initTheme();

// --- Helper Functions ---
// Currency formatter
const formatCurrency = (amount) => {
    return new Intl.NumberFormat('he-IL', {
        currency: 'ILS'
    }).format(amount);
};

// Helper function to sort months chronologically
function sortMonthsChronologically(months) {
    const monthOrder = {
        'January': 1, 'February': 2, 'March': 3, 'April': 4,
        'May': 5, 'June': 6, 'July': 7, 'August': 8,
        'September': 9, 'October': 10, 'November': 11, 'December': 12
    };

    return months.sort((a, b) => (monthOrder[a] || 0) - (monthOrder[b] || 0));
}

// Security: Helper to escape HTML to prevent XSS
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return unsafe;
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function getThemeColors() {
    const computed = getComputedStyle(document.documentElement);
    return {
        textColor: computed.getPropertyValue('--text-primary').trim(),
        gridColor: computed.getPropertyValue('--border-color').trim()
    };
}

function debounce(fn, delayMs) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delayMs);
    };
}
