async function loadHouseholdMembersPanel() {
    const resp = await fetch('/api/household-members');
    const members = await resp.json();
    const list = document.getElementById('householdMembersList');
    if (!members.length) {
        list.innerHTML = '<span style="color:var(--text-secondary);font-size:0.9em;">No household members yet — add one above.</span>';
        return;
    }
    list.innerHTML = members.map(m => `
        <span class="cat-pill">
            ${escapeHtml(m.name)}
            <button class="cat-pill-del" title="Remove member" onclick="deleteHouseholdMember(${m.id}, '${escapeHtml(m.name).replace(/'/g, "\\'")}')">✕</button>
        </span>
    `).join('');
}

async function addNewHouseholdMember() {
    const input = document.getElementById('newHouseholdMemberInput');
    const name = input.value.trim();
    if (!name) return;
    const resp = await fetch('/api/household-members', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
    });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to add household member'); return; }
    input.value = '';
    loadHouseholdMembersPanel();
}

async function deleteHouseholdMember(id, name) {
    if (!confirm(`Remove household member "${name}"?`)) return;
    const resp = await fetch(`/api/household-members/${id}`, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) { alert(result.error || 'Failed to remove household member'); return; }
    loadHouseholdMembersPanel();
}
