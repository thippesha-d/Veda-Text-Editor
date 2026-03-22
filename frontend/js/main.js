// frontend/js/main.js

/**
 * Application Entry Point.
 * Orchestrates the Editor, Toolbar, and all feature modules.
 */
import { initializeEditor, setWorkspacePath } from './editor.js';
import { setupToolbar } from './toolbar.js';
import {
    debouncedSave, createWorkspace, triggerAutoCommit,
    pollWorkspaceStatus, setActiveWorkspace, loadDocument, getLfsStatus,
    loadWorkspace, deleteWorkspace, enableLfs, disableLfs,
    cloneWorkspace, getWorkspaceRemote, setWorkspaceRemote,
} from './api.js';
import { initBranchManager }    from './branch.js';
import { initDoiScanner, _validated as doiValidated } from './doi.js';
import { initLinkChecker }      from './linkcheck.js';
import { initCitationManager }  from './citations.js';
import { initLifecycleManager } from './lifecycle.js';
import { initAnnotationTracker } from './annotations.js';
import { initReferenceManager } from './references.js';
import { initMetadataManager }  from './metadata.js';

// ---------------------------------------------------------------------------
// Restore saved theme on page load (before DOMContentLoaded to avoid flash)
// ---------------------------------------------------------------------------
(function () {
    const saved = localStorage.getItem('veda-theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    // Update theme button label once DOM is ready
    document.addEventListener('DOMContentLoaded', () => {
        const btn = document.getElementById('btn-theme-toggle');
        if (btn) btn.textContent = saved === 'dark' ? '☀️' : '🌙';
    });
})();

// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {

    const statusElement = document.getElementById('save-status');
    const updateSaveStatus = (text) => { if (statusElement) statusElement.innerText = text; };

    // ── Module state ──────────────────────────────────────────────────────
    let currentWorkspacePath = null;
    let lastCommittedWords   = 0;
    let lastHeadingCount     = 0;
    let _citationStyle       = 'apa';

    // ── DOI Scanner ───────────────────────────────────────────────────────
    const doiScanner = initDoiScanner(() => document.getElementById('doi-panel-content'));

    // ── Annotation Tracker ────────────────────────────────────────────────
    const annotationTracker = initAnnotationTracker(
        () => editor,
        () => document.getElementById('annotations-panel-content'),
    );

    // ── Reference Manager ─────────────────────────────────────────────────
    const referenceManager = initReferenceManager(
        () => document.getElementById('references-panel-content'),
        () => currentWorkspacePath,
    );

    // ── Citation Manager (merges DOI + manual refs) ───────────────────────
    const citationManager = initCitationManager(
        () => editor,
        doiValidated,
        () => _citationStyle,
        () => referenceManager.getRefs(),
    );

    // ── Link Checker ──────────────────────────────────────────────────────
    const linkChecker = initLinkChecker(
        () => document.getElementById('lc-panel-content'),
        () => currentWorkspacePath,
    );

    // ── Lifecycle Manager ─────────────────────────────────────────────────
    const lifecycleManager = initLifecycleManager(() => currentWorkspacePath);

    // ── Metadata Manager ──────────────────────────────────────────────────
    const metadataManager = initMetadataManager(
        () => document.getElementById('metadata-panel-content'),
        () => currentWorkspacePath,
    );

    // ── Utilities ─────────────────────────────────────────────────────────
    const countWords = (text) =>
        text.trim().split(/\s+/).filter(w => w.length > 0).length;

    // ── Page tracker ──────────────────────────────────────────────────────
    const editorScrollContainer = document.getElementById('editor-container');
    const pageTrackerBadge      = document.getElementById('page-tracker');
    let currentZoom = 1.0;
    const A4_HEIGHT = 1123;

    const updatePageTracker = () => {
        const canvas = document.getElementById('editor-canvas');
        if (!canvas || !pageTrackerBadge || !editorScrollContainer) return;
        const pm = canvas.querySelector('.ProseMirror');
        if (!pm) return;
        const totalPages = Math.max(1, Math.ceil(pm.offsetHeight / A4_HEIGHT));
        const scaledA4   = A4_HEIGHT * currentZoom;
        const scrollTop  = editorScrollContainer.scrollTop;
        const offset     = scrollTop + editorScrollContainer.clientHeight / 2;
        const currentPage = Math.min(totalPages, Math.max(1, Math.floor(offset / scaledA4) + 1));
        pageTrackerBadge.innerText  = `Page ${currentPage} of ${totalPages}`;
        pageTrackerBadge.style.opacity = '1';
        clearTimeout(pageTrackerBadge._hideTimeout);
        pageTrackerBadge._hideTimeout = setTimeout(() => {
            if (pageTrackerBadge) pageTrackerBadge.style.opacity = '0';
        }, 2000);
    };

    if (editorScrollContainer) {
        editorScrollContainer.addEventListener('scroll', updatePageTracker);
    }

    // ── Editor change callback ────────────────────────────────────────────
    const onEditorChange = (htmlContent) => {
        updateSaveStatus('Unsaved changes…');
        debouncedSave(htmlContent, updateSaveStatus);
        if (!currentWorkspacePath) return;

        const tmp = document.createElement('div');
        tmp.innerHTML = htmlContent;
        const currentText  = tmp.innerText || tmp.textContent || '';
        const currentWords = countWords(currentText);
        const headingCount = tmp.querySelectorAll('h1,h2,h3,h4,h5,h6').length;

        let shouldCommit = false;
        let reason = '';
        if (Math.abs(currentWords - lastCommittedWords) >= 200) {
            shouldCommit = true; reason = 'word_delta'; lastCommittedWords = currentWords;
        } else if (headingCount !== lastHeadingCount) {
            shouldCommit = true; reason = 'heading_change'; lastHeadingCount = headingCount;
        }
        if (shouldCommit) {
            triggerAutoCommit(currentWorkspacePath, reason).then(() => pollStatus());
        }

        updatePageTracker();
        doiScanner.scan(htmlContent);
    };

    // ── Editor initialisation ─────────────────────────────────────────────
    const editor = initializeEditor('editor-canvas', onEditorChange);

    if (editor) {
        setupToolbar(editor, annotationTracker);
        updateSaveStatus('Ready');
    } else {
        updateSaveStatus('Initialization failed');
    }

    // ── Workspace creation ────────────────────────────────────────────────
    const btnCreate       = document.getElementById('btn-create-workspace');
    const inputName       = document.getElementById('workspace-name-input');
    const statusWorkspace = document.getElementById('workspace-status');

    if (btnCreate && inputName) {
        btnCreate.addEventListener('click', async () => {
            const name = inputName.value.trim();
            if (!name) return alert('Please enter a workspace name');
            statusWorkspace.innerText = 'Creating…';
            const res = await createWorkspace(name);
            if (res && res.error) { statusWorkspace.innerText = `Error: ${res.error}`; return; }
            if (!res) { statusWorkspace.innerText = 'Error: no response'; return; }

            statusWorkspace.innerText = `Workspace: ${res.name}`;
            activateWorkspace(res.path);
        });
    }

    // ── Shared workspace activation (used by both Create and Open) ───────
    const btnDeleteWorkspace = document.getElementById('btn-delete-workspace');

    const activateWorkspace = (path, htmlContent = '') => {
        currentWorkspacePath = path;
        lastCommittedWords   = 0;
        lastHeadingCount     = 0;

        setActiveWorkspace(path);
        setWorkspacePath(path);

        if (htmlContent) editor.commands.setContent(htmlContent, false);

        pollStatus();

        getLfsStatus(path).then(lfs => _refreshLfsBadge(lfs));

        linkChecker.loadExisting();
        lifecycleManager.load();
        metadataManager.load();
        referenceManager.load();

        initBranchManager(path, async (newPath) => {
            currentWorkspacePath = newPath;
            setActiveWorkspace(newPath);
            setWorkspacePath(newPath);
            const html = await loadDocument(newPath);
            if (html) editor.commands.setContent(html, false);
        });

        editor.setEditable(true);
        const overlay = document.getElementById('workspace-overlay');
        if (overlay) overlay.style.display = 'none';
        if (btnDeleteWorkspace) btnDeleteWorkspace.disabled = false;
        const btnSetRemote = document.getElementById('btn-set-remote');
        if (btnSetRemote) btnSetRemote.style.display = 'inline';
    };

    // ── Set remote URL ────────────────────────────────────────────────────
    document.getElementById('btn-set-remote')?.addEventListener('click', async () => {
        if (!currentWorkspacePath) return;
        const current = await getWorkspaceRemote(currentWorkspacePath);
        const currentUrl = (current && !current.error) ? (current.url || '') : '';
        const newUrl = window.prompt('GitHub remote URL (origin):', currentUrl);
        if (newUrl === null) return;           // cancelled
        if (!newUrl.trim()) return;
        const res = await setWorkspaceRemote(currentWorkspacePath, newUrl.trim());
        if (res.error) {
            statusWorkspace.innerText = `Remote error: ${res.error}`;
        } else {
            statusWorkspace.innerText = `Remote ${res.action}: ${res.url}`;
        }
    });

    // ── LFS badge + button sync ───────────────────────────────────────────
    const _refreshLfsBadge = (lfs) => {
        const badge      = document.getElementById('lfs-badge');
        const btnEnable  = document.getElementById('btn-lfs-enable');
        const btnDisable = document.getElementById('btn-lfs-disable');
        if (!badge) return;
        badge.style.display = 'inline';
        if (!lfs || !lfs.lfs_available) {
            badge.textContent = 'LFS: Unavailable';
            badge.style.background = '#e0e0e0'; badge.style.color = '#888';
            if (btnEnable)  btnEnable.style.display  = 'none';
            if (btnDisable) btnDisable.style.display = 'none';
        } else if (lfs.lfs_configured) {
            const usage = lfs.total_mb > 0 ? ` (${lfs.total_mb} MB)` : '';
            badge.textContent = `LFS: Active${usage}`;
            badge.style.background = '#d4edda'; badge.style.color = '#155724';
            if (btnEnable)  btnEnable.style.display  = 'none';
            if (btnDisable) btnDisable.style.display = 'inline';
        } else {
            badge.textContent = 'LFS: Off';
            badge.style.background = '#e0e0e0'; badge.style.color = '#888';
            if (btnEnable)  btnEnable.style.display  = 'inline';
            if (btnDisable) btnDisable.style.display = 'none';
        }
    };

    // ── LFS enable ────────────────────────────────────────────────────────
    document.getElementById('btn-lfs-enable')?.addEventListener('click', async () => {
        if (!currentWorkspacePath) return;
        const res = await enableLfs(currentWorkspacePath);
        if (res.error) {
            const badge = document.getElementById('lfs-badge');
            if (badge) { badge.textContent = `LFS Error: ${res.error}`; badge.style.background = '#f8d7da'; badge.style.color = '#721c24'; }
            return;
        }
        const lfs = await getLfsStatus(currentWorkspacePath);
        _refreshLfsBadge(lfs);
    });

    // ── Clone from GitHub ─────────────────────────────────────────────────
    document.getElementById('btn-clone-workspace')?.addEventListener('click', async () => {
        const url = window.prompt('Enter GitHub repository URL to clone:');
        if (!url || !url.trim()) return;
        statusWorkspace.innerText = 'Cloning…';
        const res = await cloneWorkspace(url.trim());
        if (res.error) { statusWorkspace.innerText = `Error: ${res.error}`; return; }
        statusWorkspace.innerText = `Workspace: ${res.name}`;
        activateWorkspace(res.path, res.html);
    });

    // ── Open existing workspace ───────────────────────────────────────────
    document.getElementById('btn-open-workspace')?.addEventListener('click', async () => {
        let folderPath = '';

        if (window.pywebview) {
            const picked = await window.pywebview.api.pick_folder();
            if (!picked || !picked.success) return;
            folderPath = picked.path;
        } else {
            folderPath = window.prompt('Enter the full path to the workspace folder:');
            if (!folderPath) return;
        }

        statusWorkspace.innerText = 'Opening…';
        const res = await loadWorkspace(folderPath);
        if (res.error) {
            statusWorkspace.innerText = `Error: ${res.error}`;
            return;
        }

        statusWorkspace.innerText = `Workspace: ${res.name}`;
        activateWorkspace(res.path, res.html);
    });

    // ── Delete current workspace ──────────────────────────────────────────
    if (btnDeleteWorkspace) {
        btnDeleteWorkspace.addEventListener('click', async () => {
            if (!currentWorkspacePath) return;
            const confirmed = confirm(
                `Permanently delete workspace at:\n${currentWorkspacePath}\n\nThis cannot be undone.`
            );
            if (!confirmed) return;

            const res = await deleteWorkspace(currentWorkspacePath);
            if (res.error) {
                statusWorkspace.innerText = `Error: ${res.error}`;
                return;
            }

            // Reset UI to blank state
            currentWorkspacePath = null;
            lastCommittedWords   = 0;
            lastHeadingCount     = 0;
            setActiveWorkspace(null);
            setWorkspacePath(null);
            editor.commands.setContent('', false);
            editor.setEditable(false);
            statusWorkspace.innerText = 'No workspace';
            btnDeleteWorkspace.disabled = true;
            const lfsBadge = document.getElementById('lfs-badge');
            if (lfsBadge) lfsBadge.style.display = 'none';
            const btnSetRemote = document.getElementById('btn-set-remote');
            if (btnSetRemote) btnSetRemote.style.display = 'none';
            const overlay = document.getElementById('workspace-overlay');
            if (overlay) overlay.style.display = 'flex';
        });
    }

    // ── LFS disable ───────────────────────────────────────────────────────
    document.getElementById('btn-lfs-disable')?.addEventListener('click', async () => {
        if (!currentWorkspacePath) return;
        const confirmed = confirm('Disable Git LFS for this workspace?\n\nLFS filter lines will be removed from .gitattributes. Existing committed LFS objects are unaffected.');
        if (!confirmed) return;

        const res = await disableLfs(currentWorkspacePath);
        if (res.error) {
            const badge = document.getElementById('lfs-badge');
            if (badge) { badge.textContent = `LFS Error: ${res.error}`; badge.style.background = '#f8d7da'; badge.style.color = '#721c24'; }
            return;
        }
        const lfs = await getLfsStatus(currentWorkspacePath);
        _refreshLfsBadge(lfs);
    });

    // ── Git status polling ────────────────────────────────────────────────
    const pollStatus = async () => {
        if (!currentWorkspacePath) return;
        const status = await pollWorkspaceStatus(currentWorkspacePath);
        if (status && status.git_sha) {
            const date = new Date(status.last_auto_commit * 1000);
            statusWorkspace.innerText =
                `Git: ${status.git_sha.substring(0, 7)} @ ${date.toLocaleTimeString()}`;
        }
    };
    setInterval(pollStatus, 10000);

    // ── Manual save ───────────────────────────────────────────────────────
    document.getElementById('btn-manual-save')?.addEventListener('click', () => {
        updateSaveStatus('Saving…');
        debouncedSave(editor.getHTML(), updateSaveStatus);
    });

    // ── App-bar Save As / Print (mirror toolbar actions) ─────────────────
    document.getElementById('btn-save-as-appbar')?.addEventListener('click', () => {
        const htmlContent = editor.getHTML();
        const full = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Veda Export</title></head><body>${htmlContent}</body></html>`;
        if (window.pywebview) {
            window.pywebview.api.save_as(full);
        } else {
            const a = document.createElement('a');
            a.href = 'data:text/html;charset=utf-8,' + encodeURIComponent(full);
            a.download = 'article.html';
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }
    });

    document.getElementById('btn-print-appbar')?.addEventListener('click', () => window.print());

    // ── Theme toggle (app-bar button) ─────────────────────────────────────
    document.getElementById('btn-theme-toggle')?.addEventListener('click', (e) => {
        const btn  = e.currentTarget;
        const html = document.documentElement;
        const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        localStorage.setItem('veda-theme', next);
        btn.textContent = next === 'dark' ? '☀️' : '🌙';
    });

    // ── Zoom controls ─────────────────────────────────────────────────────
    const zoomLevelText   = document.getElementById('zoom-level');
    const editorCanvasEl  = document.getElementById('editor-canvas');

    const applyZoom = () => {
        if (editorCanvasEl) editorCanvasEl.style.transform = `scale(${currentZoom})`;
        if (zoomLevelText)  zoomLevelText.innerText = `${Math.round(currentZoom * 100)}%`;
        updatePageTracker();
    };

    document.getElementById('btn-zoom-in')?.addEventListener('click', () => {
        currentZoom = Math.min(currentZoom + 0.1, 2.5); applyZoom();
    });
    document.getElementById('btn-zoom-out')?.addEventListener('click', () => {
        currentZoom = Math.max(currentZoom - 0.1, 0.5); applyZoom();
    });

    // ── Panel toggles ─────────────────────────────────────────────────────
    const _bindToggle = (btnId, panelId) => {
        const btn   = document.getElementById(btnId);
        const panel = document.getElementById(panelId);
        if (btn && panel) {
            btn.addEventListener('click', () => {
                panel.style.display = panel.style.display === 'none' ? 'flex' : 'none';
            });
        }
    };

    _bindToggle('btn-toggle-branch-panel',      'branch-manager-panel');
    _bindToggle('btn-toggle-doi-panel',         'doi-panel');
    _bindToggle('btn-toggle-lc-panel',          'lc-panel');
    _bindToggle('btn-toggle-cit-panel',         'cit-panel');
    _bindToggle('btn-toggle-lifecycle-panel',   'lifecycle-panel');
    _bindToggle('btn-toggle-annotations-panel', 'annotations-panel');
    _bindToggle('btn-toggle-references-panel',  'references-panel');
    _bindToggle('btn-toggle-metadata-panel',    'metadata-panel');

    // ── Annotation panel refresh ──────────────────────────────────────────
    document.getElementById('btn-refresh-annotations')?.addEventListener('click', () => {
        if (editor) annotationTracker.scan();
    });

    // Also refresh annotations whenever the editor updates
    editor?.on('update', () => {
        const panel = document.getElementById('annotations-panel');
        if (panel && panel.style.display !== 'none') annotationTracker.scan();
    });

    // ── Link check ────────────────────────────────────────────────────────
    document.getElementById('btn-run-link-check')?.addEventListener('click', () => {
        if (editor) linkChecker.runCheck(editor.getHTML());
    });

    // ── Citation formatting ───────────────────────────────────────────────
    document.getElementById('citation-style-select')?.addEventListener('change', (e) => {
        _citationStyle = e.target.value;
    });
    document.getElementById('btn-format-citations')?.addEventListener('click', () => {
        citationManager.format();
    });
});
