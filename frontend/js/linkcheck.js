// frontend/js/linkcheck.js

/**
 * URL / Link-Rot Detection  (REQ-3.3.3)
 *
 * On-demand link checker: triggered by the user pressing "Check Links".
 * Sends the current editor HTML to the backend, which extracts all
 * HTTP/HTTPS URLs, checks each one, and returns statuses.
 * Results are rendered in the link-check panel with colour-coded badges.
 */

import { triggerLinkCheck, getLinkStatus } from './api.js';

// Status → [CSS class, badge label]
const _STATUS_UI = {
    'alive':         ['lc-alive',   '✓ Alive'],
    'redirect':      ['lc-redirect','→ Redirect'],
    'dead':          ['lc-dead',    '✗ Dead (404)'],
    'server_error':  ['lc-error',   '⚠ Server Error'],
    'access_denied': ['lc-denied',  '🔒 Access Denied'],
    'unreachable':   ['lc-unreach', '✗ Unreachable'],
    'ssl_warning':   ['lc-ssl',     '⚠ SSL Warning'],
    'unknown':       ['lc-unknown', '? Unknown'],
};

/**
 * Initialises the link-check panel.
 *
 * @param {() => HTMLElement | null} getPanelEl  - returns the panel container
 * @param {() => string | null}      getWorkspacePath - returns active workspace path
 * @returns {{ runCheck: (htmlContent: string) => Promise<void>,
 *             loadExisting: () => Promise<void> }}
 */
export function initLinkChecker(getPanelEl, getWorkspacePath) {
    return {
        runCheck:     (html) => _runCheck(html, getPanelEl(), getWorkspacePath()),
        loadExisting: ()     => _loadExisting(getPanelEl(), getWorkspacePath()),
    };
}

// ---------------------------------------------------------------------------
// Internal
// ---------------------------------------------------------------------------

async function _runCheck(htmlContent, panel, workspacePath) {
    if (!workspacePath) {
        _renderPanel(panel, null, 'No active workspace.');
        return;
    }
    _renderPanel(panel, null, '⏳ Checking links…');
    const res = await triggerLinkCheck(workspacePath, htmlContent);
    if (res && res.results) {
        _renderPanel(panel, res.results);
    } else {
        _renderPanel(panel, null, 'Error: could not reach backend.');
    }
}

async function _loadExisting(panel, workspacePath) {
    if (!workspacePath) return;
    const res = await getLinkStatus(workspacePath);
    if (res && res.results && res.results.length > 0) {
        _renderPanel(panel, res.results);
    }
}

function _badgeHtml(status) {
    const [cls, label] = _STATUS_UI[status] || ['lc-unknown', status];
    return `<span class="lc-badge ${cls}">${label}</span>`;
}

function _escAttr(str) {
    return (str || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function _renderPanel(panel, results, message) {
    if (!panel) return;

    if (message) {
        panel.innerHTML = `<p class="lc-message">${message}</p>`;
        return;
    }

    if (!results || results.length === 0) {
        panel.innerHTML = '<p class="lc-message">No links found in document.</p>';
        return;
    }

    // Sort: dead / unreachable first, then rest alphabetically
    const sorted = [...results].sort((a, b) => {
        const priority = (s) => (s === 'dead' || s === 'unreachable' ? 0 : 1);
        return priority(a.status) - priority(b.status) || a.url.localeCompare(b.url);
    });

    const rows = sorted.map(r => {
        const date = r.checked_at
            ? new Date(r.checked_at * 1000).toLocaleTimeString()
            : '';
        const code = r.http_code ? ` (${r.http_code})` : '';
        return `<li class="lc-item">
            <span class="lc-url" title="${_escAttr(r.url)}">${_escAttr(r.url)}</span>
            ${_badgeHtml(r.status)}
            <span class="lc-meta">${code}${date ? ` · ${date}` : ''}</span>
        </li>`;
    }).join('');

    panel.innerHTML = `<ul class="lc-list">${rows}</ul>`;
}
