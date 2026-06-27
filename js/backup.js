async function loadBackupInfo() {
    try {
        const resp = await fetch('/api/backup/info');
        const info = await resp.json();

        const statusEl = document.getElementById('backupStatus');
        if (info.last_backup_at) {
            const last = new Date(info.last_backup_at);
            const days = Math.floor((Date.now() - last) / 86400000);
            const label = days === 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`;
            const warn = days >= 30 ? ' ⚠️' : '';
            statusEl.textContent = `Last backup: ${label}${warn}`;
            statusEl.style.color = days >= 30 ? '#f44336' : 'var(--text-secondary)';
        } else {
            statusEl.textContent = 'No backup yet';
            statusEl.style.color = '#f44336';
        }

        const pathInput = document.getElementById('backupPathInput');
        if (pathInput) pathInput.value = info.backup_path || './backups';
    } catch (e) {
        document.getElementById('backupStatus').textContent = 'Backup info unavailable';
    }
}

async function downloadBackup() {
    const btn = event.currentTarget;
    btn.textContent = '⏳ Creating backup…';
    btn.disabled = true;
    try {
        const resp = await fetch('/api/backup');
        if (!resp.ok) { alert('Backup failed'); return; }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = resp.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] || 'backup.zip';
        a.click();
        URL.revokeObjectURL(url);
        await loadBackupInfo();
    } catch (e) {
        alert('Backup failed: ' + e.message);
    } finally {
        btn.textContent = '⬇ Download Backup';
        btn.disabled = false;
    }
}

async function saveBackupPath() {
    const path = document.getElementById('backupPathInput').value.trim();
    if (!path) return;
    const resp = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup_path: path }),
    });
    if (resp.ok) {
        alert(`✅ Backup folder set to: ${path}`);
    } else {
        alert('Failed to save backup path');
    }
}
