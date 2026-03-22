// frontend/js/doi.js

/**
 * DOI Detection and Backend Dispatch  (REQ-3.3.1)
 *
 * Scans the editor's HTML content for DOI strings on every debounced change,
 * de-duplicates against already-dispatched DOIs, sends new ones to the backend
 * for validation, and renders status badges in the reference panel.
 *
 * Pattern matched: 10\.[0-9]{4,}/[^\s]+   (standard DOI prefix)
 */

import { validateDois } from './api.js';

// Regex with lastIndex reset on each call
const DOI_PATTERN = /\b(10\.[0-9]{4,}\/[^\s<>"']+)/g;

// doi → { status, title, authors, year, flag_reason }
// Exported so citations.js can build CSL-JSON from validated entries.
export const _validated = new Map();
// DOIs currently awaiting a backend response
const _pending = new Set();
// Most-recent detected DOI list — shared across concurrent scan calls so
// every async completion renders the freshest snapshot, not a stale closure copy.
let _lastDetected = [];

// Badge labels and CSS classes per status
const _STATUS_UI = {
    'valid':                 ['doi-valid',    '✓ Valid'],
    'retracted':             ['doi-retracted','✗ Retracted'],
    'corrected':             ['doi-corrected','⚠ Corrected'],
    'expression-of-concern': ['doi-concern',  '⚠ Concern'],
    'not-found':             ['doi-notfound', '? Not Found'],
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Initialises the DOI scanner.
 *
 * @param {() => HTMLElement | null} getPanelEl  - Returns the reference-panel
 *   container element; called each time the panel needs re-rendering.
 * @returns {{ scan: (htmlContent: string) => void }}
 */
export function initDoiScanner(getPanelEl) {
    return {
        scan: (htmlContent) => _scan(htmlContent, getPanelEl()),
    };
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _extractDois(htmlContent) {
    const div = document.createElement('div');
    div.innerHTML = htmlContent;
    const text = div.textContent || div.innerText || '';

    const found = new Set();
    DOI_PATTERN.lastIndex = 0;
    let m;
    while ((m = DOI_PATTERN.exec(text)) !== null) {
        // A single regex match may span multiple adjacent DOIs when they are
        // separated by a non-whitespace character (e.g. "10.1234/a,10.5678/b").
        // Split on every embedded DOI prefix 10.XXXX/ using a lookahead.
        const parts = m[1].split(/(?=10\.[0-9]{4,}\/)/);
        for (const part of parts) {
            const cleaned = part.replace(/[.,;:)}\]]+$/, '');
            if (cleaned) found.add(cleaned);
        }
    }
    return [...found];
}

function _newDois(detected) {
    return detected.filter(doi => !_validated.has(doi) && !_pending.has(doi));
}

async function _scan(htmlContent, panel) {
    const detected = _extractDois(htmlContent);
    // Always update the shared snapshot so any concurrent scan's final render
    // reflects the current document state, not a stale closure copy.
    _lastDetected = detected;

    const toDispatch = _newDois(detected);

    if (toDispatch.length > 0) {
        toDispatch.forEach(doi => _pending.add(doi));
        _renderPanel(panel, _lastDetected);   // show spinners immediately

        try {
            const res = await validateDois(toDispatch);
            if (res && res.results) {
                res.results.forEach(r => {
                    _validated.set(r.doi, r);
                    _pending.delete(r.doi);
                });
            } else {
                // Backend unreachable — remove from pending so retry is possible
                toDispatch.forEach(doi => _pending.delete(doi));
            }
        } catch {
            toDispatch.forEach(doi => _pending.delete(doi));
        }
    }

    // Use _lastDetected (not the local `detected`) so a slower earlier scan
    // cannot overwrite a faster later scan's panel state.
    _renderPanel(panel, _lastDetected);
}

function _badgeHtml(doi) {
    if (_pending.has(doi)) {
        return '<span class="doi-badge doi-pending" title="Validating…">⏳ Pending</span>';
    }
    const r = _validated.get(doi);
    if (!r) return '';
    const [cls, label] = _STATUS_UI[r.status] || ['doi-unknown', r.status];
    const tip = r.flag_reason ? ` title="${_escAttr(r.flag_reason)}"` : '';
    return `<span class="doi-badge ${cls}"${tip}>${label}</span>`;
}

function _escAttr(str) {
    return str.replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function _renderPanel(panel, detected) {
    if (!panel) return;

    if (detected.length === 0) {
        panel.innerHTML = '<p class="doi-empty">No DOIs detected in document.</p>';
        return;
    }

    const rows = detected.map(doi => {
        const r = _validated.get(doi);
        let meta = '';
        if (r && (r.title || r.year)) {
            const titleSnip = r.title
                ? r.title.substring(0, 70) + (r.title.length > 70 ? '…' : '')
                : '';
            meta = `<span class="doi-meta">${_escAttr(titleSnip)}${r.year ? ` (${r.year})` : ''}</span>`;
        }
        return `<li class="doi-item">
            <span class="doi-text" title="${_escAttr(doi)}">${_escAttr(doi)}</span>
            ${_badgeHtml(doi)}
            ${meta}
        </li>`;
    }).join('');

    panel.innerHTML = `<ul class="doi-list">${rows}</ul>`;
}
