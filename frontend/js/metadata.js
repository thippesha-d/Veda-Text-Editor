// frontend/js/metadata.js

/**
 * Document Metadata & Tagging Manager (Feature 7)
 *
 * Manages title, authors, abstract, keywords, tags, journal, version.
 * All data is persisted to workspace.json via the backend API.
 */

import { getMetadata, saveMetadata } from './api.js';

let _current = null;

export function initMetadataManager(getPanelEl, getWorkspacePath) {
    return {
        load: () => _load(getPanelEl(), getWorkspacePath()),
        get:  () => _current,
    };
}

async function _load(panelEl, workspacePath) {
    if (!panelEl || !workspacePath) return;
    const data = await getMetadata(workspacePath);
    _current = data || {};
    _render(panelEl, workspacePath, _current);
}

function _render(panelEl, workspacePath, data) {
    const authorsStr   = Array.isArray(data.authors)  ? data.authors.join(', ')  : (data.authors  || '');
    const keywordsStr  = Array.isArray(data.keywords) ? data.keywords.join(', ') : (data.keywords || '');
    const tagsStr      = Array.isArray(data.tags)     ? data.tags.join(', ')     : (data.tags     || '');

    panelEl.innerHTML = `
    <div class="meta-form">
        <div class="meta-row">
            <label class="meta-label">Title</label>
            <input id="meta-title" class="meta-input" value="${_esc(data.title || '')}" placeholder="Document title"/>
        </div>
        <div class="meta-row">
            <label class="meta-label">Authors</label>
            <input id="meta-authors" class="meta-input" value="${_esc(authorsStr)}" placeholder="Author 1, Author 2, ..."/>
        </div>
        <div class="meta-row">
            <label class="meta-label">Journal / Venue</label>
            <input id="meta-journal" class="meta-input" value="${_esc(data.journal || '')}" placeholder="Journal or conference name"/>
        </div>
        <div class="meta-row">
            <label class="meta-label">Keywords</label>
            <input id="meta-keywords" class="meta-input" value="${_esc(keywordsStr)}" placeholder="keyword1, keyword2, ..."/>
        </div>
        <div class="meta-row">
            <label class="meta-label">Abstract</label>
            <textarea id="meta-abstract" class="meta-input meta-textarea" placeholder="Abstract...">${_esc(data.abstract || '')}</textarea>
        </div>
        <div class="meta-row">
            <label class="meta-label">Tags</label>
            <div id="tags-display" style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:4px;">
                ${(Array.isArray(data.tags) ? data.tags : []).map(t =>
                    `<span class="tag-chip">${_esc(t)}<button class="tag-remove" data-tag="${_esc(t)}">✕</button></span>`
                ).join('')}
            </div>
            <div style="display:flex; gap:6px;">
                <input id="meta-tag-input" class="meta-input" placeholder="Add tag..." style="flex:1; max-width:180px;"/>
                <button id="btn-add-tag" style="padding:3px 10px; cursor:pointer; background:#8e44ad; color:white; border:none; border-radius:4px; font-size:12px;">+ Tag</button>
            </div>
        </div>
        <div class="meta-row">
            <label class="meta-label">Version</label>
            <input id="meta-version" class="meta-input" value="${_esc(data.version || '1')}" placeholder="1" style="max-width:80px;"/>
        </div>
        <div style="margin-top:8px;">
            <button id="btn-save-meta" style="padding:4px 14px; cursor:pointer; background:#2980b9; color:white; border:none; border-radius:4px; font-size:12px;">Save Metadata</button>
            <span id="meta-save-status" style="font-size:12px; color:#888; margin-left:10px;"></span>
        </div>
    </div>`;

    // Bind tag remove buttons
    panelEl.querySelectorAll('.tag-remove').forEach(btn => {
        btn.addEventListener('click', async () => {
            const tag = btn.getAttribute('data-tag');
            const tags = (Array.isArray(_current.tags) ? _current.tags : []).filter(t => t !== tag);
            await _saveField(workspacePath, panelEl, { tags });
        });
    });

    // Bind add tag
    document.getElementById('btn-add-tag')?.addEventListener('click', async () => {
        const input = document.getElementById('meta-tag-input');
        const tag = input?.value.trim();
        if (!tag) return;
        const tags = [...new Set([...(Array.isArray(_current.tags) ? _current.tags : []), tag])];
        await _saveField(workspacePath, panelEl, { tags });
    });

    // Enter key on tag input
    document.getElementById('meta-tag-input')?.addEventListener('keydown', async (e) => {
        if (e.key !== 'Enter') return;
        const tag = e.target.value.trim();
        if (!tag) return;
        const tags = [...new Set([...(Array.isArray(_current.tags) ? _current.tags : []), tag])];
        await _saveField(workspacePath, panelEl, { tags });
    });

    // Bind save button
    document.getElementById('btn-save-meta')?.addEventListener('click', async () => {
        const metadata = _readForm();
        const btn = document.getElementById('btn-save-meta');
        const status = document.getElementById('meta-save-status');
        if (btn) { btn.disabled = true; btn.textContent = '...'; }
        const result = await saveMetadata(workspacePath, metadata);
        if (btn) { btn.disabled = false; btn.textContent = 'Save Metadata'; }
        if (result) {
            _current = result;
            if (status) { status.textContent = 'Saved ✓'; setTimeout(() => { if (status) status.textContent = ''; }, 2000); }
        }
    });
}

function _readForm() {
    const authorsRaw  = document.getElementById('meta-authors')?.value.trim() || '';
    const keywordsRaw = document.getElementById('meta-keywords')?.value.trim() || '';
    return {
        title:    document.getElementById('meta-title')?.value.trim() || '',
        authors:  authorsRaw  ? authorsRaw.split(',').map(s => s.trim()).filter(Boolean)  : [],
        journal:  document.getElementById('meta-journal')?.value.trim() || '',
        keywords: keywordsRaw ? keywordsRaw.split(',').map(s => s.trim()).filter(Boolean) : [],
        abstract: document.getElementById('meta-abstract')?.value.trim() || '',
        version:  document.getElementById('meta-version')?.value.trim() || '1',
        tags:     Array.isArray(_current?.tags) ? _current.tags : [],
    };
}

async function _saveField(workspacePath, panelEl, partial) {
    const merged = { ..._readForm(), ...partial };
    const result = await saveMetadata(workspacePath, merged);
    if (result) {
        _current = result;
        _render(panelEl, workspacePath, _current);
    }
}

function _esc(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}
