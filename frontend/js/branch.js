// frontend/js/branch.js

/**
 * API client and UI for REQ-3.2.3 Semantic Branch Management (Git Worktrees).
 * Each branch is a linked worktree — switching changes the active workspace path.
 */

export async function apiBranchCreate(workspacePath, branchName) {
    try {
        const response = await fetch('/api/branch/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, branch_name: branchName }),
        });
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Unknown error' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}

export async function apiBranchSwitch(workspacePath, branchName) {
    try {
        const response = await fetch('/api/branch/switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, branch_name: branchName }),
        });
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Unknown error' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}

export async function apiBranchList(workspacePath) {
    try {
        const response = await fetch(
            `/api/branch/list?workspace_path=${encodeURIComponent(workspacePath)}`
        );
        const data = await response.json();
        if (!response.ok) {
            console.error("List branches failed:", data.detail);
            return null;
        }
        return data.branches;
    } catch (e) {
        console.error("apiBranchList error:", e);
        return null;
    }
}

export async function apiBranchMerge(workspacePath, sourceBranch) {
    try {
        const response = await fetch('/api/branch/merge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, source_branch: sourceBranch }),
        });
        const data = await response.json();
        if (!response.ok) {
            console.error("Merge branch failed:", data.detail);
            return null;
        }
        return data;
    } catch (e) {
        console.error("apiBranchMerge error:", e);
        return null;
    }
}

export async function apiBranchDiff(workspacePath, branchA, branchB) {
    try {
        const params = new URLSearchParams({
            workspace_path: workspacePath,
            branch_a: branchA,
            branch_b: branchB,
        });
        const response = await fetch(`/api/branch/diff?${params}`);
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Unknown error' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}

export async function apiBranchConflicts(workspacePath) {
    try {
        const response = await fetch(
            `/api/branch/conflicts?workspace_path=${encodeURIComponent(workspacePath)}`
        );
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Unknown error' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}

export async function apiBranchDelete(workspacePath, branchName) {
    try {
        const response = await fetch('/api/branch/delete', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, branch_name: branchName }),
        });
        const data = await response.json();
        if (!response.ok) {
            console.error("Delete branch failed:", data.detail);
            return null;
        }
        return data;
    } catch (e) {
        console.error("apiBranchDelete error:", e);
        return null;
    }
}

/**
 * Initializes and manages the Branch Manager UI panel.
 * @param {string} workspacePath - The currently active worktree path.
 * @param {function|null} onSwitchComplete - Called with (newWorktreePath) after a successful switch.
 */
// ── Diff renderer ──────────────────────────────────────────────────────────

function _renderDiff(diffText) {
    if (!diffText || diffText.trim() === '') {
        return '<p class="diff-empty">No differences between branches.</p>';
    }
    const lines = diffText.split('\n');
    let html = '';
    for (const line of lines) {
        let cls = 'diff-ctx';
        if (line.startsWith('+++') || line.startsWith('---')) {
            cls = 'diff-file';
        } else if (line.startsWith('+')) {
            cls = 'diff-add';
        } else if (line.startsWith('-')) {
            cls = 'diff-del';
        } else if (line.startsWith('@@')) {
            cls = 'diff-hunk';
        } else if (line.startsWith('diff ')) {
            cls = 'diff-file';
        }
        html += `<div class="${cls}">${_escHtml(line) || '&nbsp;'}</div>`;
    }
    return html;
}

function _renderConflicts(conflicts) {
    if (!conflicts || conflicts.length === 0) {
        return '<p class="diff-empty">No conflicts detected.</p>';
    }
    return conflicts.map(c => {
        const lines = c.content.split('\n');
        let linesHtml = '';
        for (const line of lines) {
            let cls = 'diff-ctx';
            if (line.startsWith('<<<<<<<')) cls = 'diff-conflict-ours';
            else if (line.startsWith('=======')) cls = 'diff-conflict-sep';
            else if (line.startsWith('>>>>>>>')) cls = 'diff-conflict-theirs';
            linesHtml += `<div class="${cls}">${_escHtml(line) || '&nbsp;'}</div>`;
        }
        return `<div class="diff-file-header">${_escHtml(c.file)}</div>${linesHtml}`;
    }).join('');
}

function _escHtml(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// ── Branch Manager ─────────────────────────────────────────────────────────

export function initBranchManager(workspacePath, onSwitchComplete = null) {
    const panel = document.getElementById('branch-manager-panel');
    const branchList = document.getElementById('branch-list');
    const newBranchInput = document.getElementById('new-branch-input');
    const btnCreateBranch = document.getElementById('btn-create-branch');
    const branchOpStatus = document.getElementById('branch-op-status');
    const diffViewer      = document.getElementById('branch-diff-viewer');
    const diffTitle       = document.getElementById('branch-diff-title');
    const diffBody        = document.getElementById('branch-diff-body');
    const conflictsViewer = document.getElementById('branch-conflicts-viewer');
    const conflictsBody   = document.getElementById('branch-conflicts-body');

    if (!panel) return;

    // activeWorktreePath tracks the current workspace path and updates on switch
    let activeWorktreePath = workspacePath;

    // ── Viewer helpers ────────────────────────────────────────────────────
    const showDiff = (title, html) => {
        if (!diffViewer || !diffBody || !diffTitle) return;
        diffTitle.textContent = title;
        diffBody.innerHTML = html;
        diffViewer.style.display = 'block';
        if (conflictsViewer) conflictsViewer.style.display = 'none';
    };

    const showConflicts = (html) => {
        if (!conflictsViewer || !conflictsBody) return;
        conflictsBody.innerHTML = html;
        conflictsViewer.style.display = 'block';
        if (diffViewer) diffViewer.style.display = 'none';
    };

    document.getElementById('btn-close-diff')?.addEventListener('click', () => {
        if (diffViewer) diffViewer.style.display = 'none';
    });
    document.getElementById('btn-close-conflicts')?.addEventListener('click', () => {
        if (conflictsViewer) conflictsViewer.style.display = 'none';
    });

    const setStatus = (msg, isError = false) => {
        if (branchOpStatus) {
            branchOpStatus.innerText = msg;
            branchOpStatus.style.color = isError ? '#e74c3c' : '#27ae60';
        }
    };

    const refreshBranchList = async () => {
        if (!branchList) return;
        branchList.innerHTML = '<li style="color:#888; font-style:italic;">Loading...</li>';
        const branches = await apiBranchList(activeWorktreePath);

        if (!branches) {
            branchList.innerHTML = '<li style="color:#e74c3c;">Failed to load branches.</li>';
            return;
        }

        branchList.innerHTML = '';
        branches.forEach(branch => {
            const li = document.createElement('li');
            li.style.cssText = 'display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid #eee;';

            const nameSpan = document.createElement('span');
            nameSpan.style.cssText = `font-weight:${branch.active ? 'bold' : 'normal'}; flex:1; color:${branch.active ? '#2980b9' : '#2c3e50'};`;
            nameSpan.innerText = `${branch.active ? '▶ ' : '  '}${branch.name}`;
            nameSpan.title = `${branch.message || ''} (${branch.sha})`;

            const btnSwitch = document.createElement('button');
            btnSwitch.innerText = 'Switch';
            btnSwitch.disabled = branch.active;
            btnSwitch.style.cssText = 'font-size:11px; padding:2px 7px; cursor:pointer;';
            btnSwitch.addEventListener('click', async () => {
                setStatus(`Switching to ${branch.name}...`);
                const res = await apiBranchSwitch(activeWorktreePath, branch.name);
                if (res && !res.error) {
                    activeWorktreePath = res.worktree_path;
                    setStatus(`Switched to '${res.branch_name}'.`);
                    refreshBranchList();
                    if (onSwitchComplete) await onSwitchComplete(res.worktree_path);
                } else {
                    setStatus(`Switch failed: ${res ? res.error : 'No response'}`, true);
                }
            });

            const btnMerge = document.createElement('button');
            btnMerge.innerText = 'Merge →';
            btnMerge.disabled = branch.active;
            btnMerge.style.cssText = 'font-size:11px; padding:2px 7px; cursor:pointer;';
            btnMerge.addEventListener('click', async () => {
                setStatus(`Merging '${branch.name}' into current branch...`);
                const res = await apiBranchMerge(activeWorktreePath, branch.name);
                if (res && res.status === 'success') {
                    setStatus(res.message);
                    refreshBranchList();
                } else if (res && res.status === 'conflict') {
                    setStatus(`Conflict: ${res.message}`, true);
                    const conflictData = await apiBranchConflicts(activeWorktreePath);
                    if (conflictData && !conflictData.error) {
                        showConflicts(_renderConflicts(conflictData.conflicts));
                    }
                } else {
                    setStatus('Merge failed.', true);
                }
            });

            const btnDiff = document.createElement('button');
            btnDiff.innerText = 'Diff';
            btnDiff.disabled = branch.active;
            btnDiff.style.cssText = 'font-size:11px; padding:2px 7px; cursor:pointer;';
            btnDiff.addEventListener('click', async () => {
                setStatus(`Loading diff for '${branch.name}'...`);
                const activeBranch = branches.find(b => b.active);
                const base = activeBranch ? activeBranch.name : branch.name;
                const res = await apiBranchDiff(activeWorktreePath, base, branch.name);
                if (res.error) { setStatus(`Diff failed: ${res.error}`, true); return; }
                setStatus('');
                showDiff(`Diff: ${base} → ${branch.name}`, _renderDiff(res.diff));
            });

            const btnDelete = document.createElement('button');
            btnDelete.innerText = '✕';
            btnDelete.disabled = branch.active;
            btnDelete.title = 'Remove worktree and branch';
            btnDelete.style.cssText = 'font-size:11px; padding:2px 7px; cursor:pointer; color:#e74c3c;';
            btnDelete.addEventListener('click', async () => {
                if (!confirm(`Remove worktree for '${branch.name}'? This cannot be undone.`)) return;
                const res = await apiBranchDelete(activeWorktreePath, branch.name);
                if (res) {
                    setStatus(`Removed '${branch.name}'.`);
                    refreshBranchList();
                } else {
                    setStatus('Remove failed.', true);
                }
            });

            li.appendChild(nameSpan);
            li.appendChild(btnSwitch);
            li.appendChild(btnMerge);
            li.appendChild(btnDiff);
            li.appendChild(btnDelete);
            branchList.appendChild(li);
        });
    };

    if (btnCreateBranch && newBranchInput) {
        btnCreateBranch.addEventListener('click', async () => {
            const raw = newBranchInput.value.trim();
            if (!raw) { setStatus('Enter a branch name.', true); return; }
            const name = raw.replace(/\s+/g, '-');
            if (name !== raw) newBranchInput.value = name;
            setStatus(`Creating worktree for '${name}'...`);
            const res = await apiBranchCreate(activeWorktreePath, name);
            if (res && !res.error) {
                setStatus(`Branch '${res.branch_name}' created.`);
                newBranchInput.value = '';
                refreshBranchList();
            } else {
                setStatus(`Failed: ${res ? res.error : 'No response'}`, true);
            }
        });
    }

    refreshBranchList();
}
