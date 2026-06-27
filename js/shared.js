// Shared state and helpers used across multiple tabs
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
