// frontend/js/references.js

/**
 * Manual Reference Manager (Feature 5)
 *
 * Manages manually entered references (Author/Journal/Book/Conference).
 * References are persisted in workspace.json via the backend API.
 * Exposes getRefs() as CSL-JSON so citations.js can include them when formatting.
 */

import {
    getManualReferences,
    saveManualReference,
    deleteManualReference,
} from './api.js';

// ---------------------------------------------------------------------------
// Ref type definitions
// ---------------------------------------------------------------------------

const REF_TYPES = {
    journal:    { label: 'Journal Article', icon: '📄' },
    book:       { label: 'Book',            icon: '📘' },
    conference: { label: 'Conference Paper', icon: '🎤' },
    other:      { label: 'Other',           icon: '📎' },
};

// In-memory store
let _refs = [];

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function initReferenceManager(getPanelEl, getWorkspacePath) {
    return {
        load:    () => _load(getPanelEl(), getWorkspacePath()),
        getRefs: () => _toCSL(_refs),
    };
}

// ---------------------------------------------------------------------------
// Internal
// ---------------------------------------------------------------------------

async function _load(panelEl, workspacePath) {
    if (!panelEl || !workspacePath) return;
    const result = await getManualReferences(workspacePath);
    _refs = result?.refs || [];
    _render(panelEl, workspacePath);
}

function _render(panelEl, workspacePath) {
    let html = `
    <div class="ref-mgr">
        <button id="btn-ref-add" style="padding:3px 12px; cursor:pointer; background:#2980b9; color:white; border:none; border-radius:4px; font-size:12px; margin-bottom:8px;">+ Add Reference</button>
        <div id="ref-add-form" style="display:none; background:#f9f9f9; border:1px solid #ddd; border-radius:4px; padding:10px; margin-bottom:8px;">
            <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:6px;">
                <label style="font-size:12px;">Type:
                    <select id="ref-type-select" style="padding:2px 6px; border-radius:3px; border:1px solid #ccc; font-size:12px;">
                        ${Object.entries(REF_TYPES).map(([k,v]) => `<option value="${k}">${v.icon} ${v.label}</option>`).join('')}
                    </select>
                </label>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
                <input id="ref-authors"  placeholder="Authors (comma-separated)" style="padding:4px 6px; border:1px solid #ccc; border-radius:3px; font-size:12px;"/>
                <input id="ref-title"    placeholder="Title" style="padding:4px 6px; border:1px solid #ccc; border-radius:3px; font-size:12px;"/>
                <input id="ref-venue"    placeholder="Journal / Publisher / Conference" style="padding:4px 6px; border:1px solid #ccc; border-radius:3px; font-size:12px;"/>
                <input id="ref-year"     placeholder="Year" style="padding:4px 6px; border:1px solid #ccc; border-radius:3px; font-size:12px; max-width:80px;"/>
                <input id="ref-volume"   placeholder="Volume / Pages" style="padding:4px 6px; border:1px solid #ccc; border-radius:3px; font-size:12px;"/>
                <input id="ref-doi"      placeholder="DOI (optional)" style="padding:4px 6px; border:1px solid #ccc; border-radius:3px; font-size:12px;"/>
            </div>
            <div style="display:flex; gap:6px; margin-top:8px;">
                <button id="btn-ref-save" style="padding:3px 12px; cursor:pointer; background:#27ae60; color:white; border:none; border-radius:4px; font-size:12px;">Save</button>
                <button id="btn-ref-cancel" style="padding:3px 12px; cursor:pointer; background:#e0e0e0; color:#444; border:none; border-radius:4px; font-size:12px;">Cancel</button>
            </div>
        </div>`;

    if (_refs.length === 0) {
        html += '<p style="font-size:12px; color:#999; font-style:italic;">No manual references added yet.</p>';
    } else {
        html += '<ul class="ref-list">';
        for (const ref of _refs) {
            const icon = REF_TYPES[ref.type]?.icon || '📎';
            const authorsText = ref.authors ? ref.authors.split(',')[0].trim() + (ref.authors.includes(',') ? ' et al.' : '') : 'Unknown';
            html += `<li class="ref-item" data-ref-id="${ref.ref_id}">
                <span class="ref-icon">${icon}</span>
                <span class="ref-body">
                    <span class="ref-title">${ref.title || '(No title)'}</span>
                    <span class="ref-meta">${authorsText}${ref.year ? `, ${ref.year}` : ''}${ref.venue ? ` — ${ref.venue}` : ''}</span>
                    <span class="ref-key">[@${ref.ref_id}]</span>
                </span>
                <button class="btn-ref-delete" data-ref-id="${ref.ref_id}" style="padding:2px 8px; cursor:pointer; background:#e74c3c; color:white; border:none; border-radius:3px; font-size:11px; margin-left:auto; flex-shrink:0;">✕</button>
            </li>`;
        }
        html += '</ul>';
    }

    html += '</div>';
    panelEl.innerHTML = html;

    // Bind Add button
    document.getElementById('btn-ref-add')?.addEventListener('click', () => {
        const form = document.getElementById('ref-add-form');
        if (form) form.style.display = form.style.display === 'none' ? 'block' : 'none';
    });

    // Bind Cancel
    document.getElementById('btn-ref-cancel')?.addEventListener('click', () => {
        const form = document.getElementById('ref-add-form');
        if (form) form.style.display = 'none';
    });

    // Bind Save
    document.getElementById('btn-ref-save')?.addEventListener('click', async () => {
        const ref = {
            type:    document.getElementById('ref-type-select')?.value || 'journal',
            authors: document.getElementById('ref-authors')?.value.trim() || '',
            title:   document.getElementById('ref-title')?.value.trim() || '',
            venue:   document.getElementById('ref-venue')?.value.trim() || '',
            year:    document.getElementById('ref-year')?.value.trim() || '',
            volume:  document.getElementById('ref-volume')?.value.trim() || '',
            doi:     document.getElementById('ref-doi')?.value.trim() || '',
        };
        if (!ref.title && !ref.authors) return alert('Please enter at least a title or author.');
        const btn = document.getElementById('btn-ref-save');
        if (btn) { btn.disabled = true; btn.textContent = '...'; }
        const result = await saveManualReference(workspacePath, ref);
        if (result?.ref) {
            // Update or add in local store
            _refs = _refs.filter(r => r.ref_id !== result.ref.ref_id);
            _refs.push(result.ref);
        }
        _render(panelEl, workspacePath);
    });

    // Bind delete buttons
    panelEl.querySelectorAll('.btn-ref-delete').forEach(btn => {
        btn.addEventListener('click', async () => {
            const refId = btn.getAttribute('data-ref-id');
            await deleteManualReference(workspacePath, refId);
            _refs = _refs.filter(r => r.ref_id !== refId);
            _render(panelEl, workspacePath);
        });
    });
}

// ---------------------------------------------------------------------------
// Convert to CSL-JSON for the citation formatter
// ---------------------------------------------------------------------------

function _toCSL(refs) {
    return refs.map(r => {
        const typeMap = { journal: 'article-journal', book: 'book', conference: 'paper-conference', other: 'document' };
        const entry = {
            id:   r.ref_id,
            type: typeMap[r.type] || 'document',
        };
        if (r.title) entry.title = r.title;
        if (r.year)  entry.issued = { 'date-parts': [[parseInt(r.year) || 0]] };
        if (r.doi)   entry.DOI = r.doi;
        if (r.venue) {
            if (r.type === 'book') entry.publisher = r.venue;
            else entry['container-title'] = r.venue;
        }
        if (r.authors) {
            entry.author = r.authors.split(',').map(name => {
                const parts = name.trim().split(' ');
                return { family: parts[parts.length - 1] || name.trim(), given: parts.slice(0, -1).join(' ') };
            });
        }
        return entry;
    });
}
