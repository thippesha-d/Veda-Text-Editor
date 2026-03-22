// frontend/js/lifecycle.js

/**
 * Article Lifecycle State Machine UI (REQ-3.4.1–3.4.4)
 *
 * - Renders a coloured state badge in the workspace bar
 * - Provides a transition dropdown + Apply button
 * - Shows article DOI input (enabled only in preprint / published)
 * - Displays a persistent red alert banner on adverse events (retraction, etc.)
 * - Loads current state when a workspace opens
 */

import {
    getLifecycleState,
    transitionLifecycle,
    setArticleDoi,
    acknowledgeAlerts,
} from './api.js';

const STATE_LABELS = {
    draft:        'Draft',
    submitted:    'Submitted',
    under_review: 'Under Review',
    preprint:     'Pre-print',
    published:    'Published',
    retracted:    'Retracted',
};

const STATE_COLORS = {
    draft:        { bg: '#e8e8e8', fg: '#555' },
    submitted:    { bg: '#fff3cd', fg: '#856404' },
    under_review: { bg: '#cce5ff', fg: '#004085' },
    preprint:     { bg: '#d4edda', fg: '#155724' },
    published:    { bg: '#155724', fg: '#ffffff' },
    retracted:    { bg: '#c0392b', fg: '#ffffff' },
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function initLifecycleManager(getWorkspacePath) {
    return {
        load: () => _load(getWorkspacePath()),
    };
}

// ---------------------------------------------------------------------------
// Internal
// ---------------------------------------------------------------------------

async function _load(workspacePath) {
    if (!workspacePath) return;
    const data = await getLifecycleState(workspacePath);
    if (!data) return;
    _renderBadge(data.state);
    _renderPanel(data, workspacePath);
    _renderAlertBanner(data.alerts || [], workspacePath);
}

function _renderBadge(state) {
    const badge = document.getElementById('lifecycle-badge');
    if (!badge) return;
    const colors = STATE_COLORS[state] || { bg: '#e8e8e8', fg: '#555' };
    badge.textContent = STATE_LABELS[state] || state;
    badge.style.background = colors.bg;
    badge.style.color = colors.fg;
    badge.style.display = 'inline-block';
}

function _renderPanel(data, workspacePath) {
    const panel = document.getElementById('lifecycle-panel-content');
    if (!panel) return;

    const { state, state_label, allowed_transitions, article_doi, publisher_url } = data;
    const doiEnabled = state === 'preprint' || state === 'published';

    let html = `<div style="margin-bottom:10px;">
        <strong style="font-size:13px;">Current State:</strong>
        <span style="font-size:13px; margin-left:6px;">${state_label}</span>
    </div>`;

    if (allowed_transitions && allowed_transitions.length > 0) {
        html += `<div style="display:flex; align-items:center; gap:8px; margin-bottom:10px; flex-wrap:wrap;">
            <label style="font-size:13px;">Transition to:</label>
            <select id="lifecycle-transition-select" style="padding:3px 8px; border-radius:4px; border:1px solid #ccc; font-size:13px;">
                ${allowed_transitions.map(s =>
                    `<option value="${s}">${STATE_LABELS[s] || s}</option>`
                ).join('')}
            </select>
            <input type="text" id="lifecycle-note-input" placeholder="Optional note..."
                style="padding:3px 8px; border-radius:4px; border:1px solid #ccc; font-size:13px; flex:1; max-width:200px;"/>
            <button id="btn-lifecycle-transition"
                style="padding:3px 12px; cursor:pointer; background:#2c3e50; color:white; border:none; border-radius:4px; font-size:12px;">
                Apply
            </button>
        </div>`;
    } else {
        html += `<p style="font-size:12px; color:#888; margin-bottom:8px;">No further transitions available.</p>`;
    }

    html += `<div style="opacity:${doiEnabled ? 1 : 0.5}; margin-bottom:4px;">
        <label style="font-size:13px; display:block; margin-bottom:4px;">Article DOI (own published DOI):</label>
        <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
            <input type="text" id="lifecycle-doi-input" placeholder="10.xxxx/..."
                value="${article_doi || ''}" ${doiEnabled ? '' : 'disabled'}
                style="padding:3px 8px; border-radius:4px; border:1px solid #ccc; font-size:13px; flex:1; max-width:240px;"/>
            <input type="text" id="lifecycle-url-input" placeholder="Publisher URL (optional)"
                value="${publisher_url || ''}" ${doiEnabled ? '' : 'disabled'}
                style="padding:3px 8px; border-radius:4px; border:1px solid #ccc; font-size:13px; flex:1; max-width:260px;"/>
            <button id="btn-lifecycle-set-doi" ${doiEnabled ? '' : 'disabled'}
                style="padding:3px 12px; cursor:${doiEnabled ? 'pointer' : 'not-allowed'};
                       background:${doiEnabled ? '#2980b9' : '#ccc'}; color:white;
                       border:none; border-radius:4px; font-size:12px;">
                Save
            </button>
        </div>
        ${!doiEnabled ? '<span style="font-size:11px; color:#888;">Available in Pre-print or Published state.</span>' : ''}
    </div>`;

    panel.innerHTML = html;

    // Bind transition button
    const btnTransition = document.getElementById('btn-lifecycle-transition');
    if (btnTransition) {
        btnTransition.addEventListener('click', async () => {
            const sel = document.getElementById('lifecycle-transition-select');
            const noteEl = document.getElementById('lifecycle-note-input');
            const newState = sel ? sel.value : '';
            const note = noteEl ? noteEl.value.trim() : '';
            if (!newState) return;
            btnTransition.disabled = true;
            btnTransition.textContent = '...';
            const result = await transitionLifecycle(workspacePath, newState, note);
            btnTransition.disabled = false;
            btnTransition.textContent = 'Apply';
            if (result) {
                _renderBadge(result.state);
                _renderPanel(result, workspacePath);
                _renderAlertBanner(result.alerts || [], workspacePath);
            }
        });
    }

    // Bind DOI save button
    const btnDoi = document.getElementById('btn-lifecycle-set-doi');
    if (btnDoi && doiEnabled) {
        btnDoi.addEventListener('click', async () => {
            const doiEl = document.getElementById('lifecycle-doi-input');
            const urlEl = document.getElementById('lifecycle-url-input');
            const doi = doiEl ? doiEl.value.trim() : '';
            const url = urlEl ? urlEl.value.trim() : '';
            btnDoi.disabled = true;
            btnDoi.textContent = '...';
            const result = await setArticleDoi(workspacePath, doi, url);
            btnDoi.disabled = false;
            btnDoi.textContent = 'Save';
            if (!result || result.detail) {
                alert(result?.detail || 'Failed to save DOI');
            }
        });
    }
}

function _renderAlertBanner(alerts, workspacePath) {
    const banner = document.getElementById('lifecycle-alert-banner');
    if (!banner) return;

    const unacked = alerts.filter(a => !a.acknowledged);
    if (unacked.length === 0) {
        banner.style.display = 'none';
        return;
    }

    banner.style.display = 'flex';
    const messages = unacked.map(a => `[${a.type.toUpperCase()}] ${a.message}`).join(' | ');
    banner.innerHTML = `
        <span style="flex:1;">⚠️ ${messages}</span>
        <button id="btn-dismiss-alerts"
            style="padding:2px 10px; cursor:pointer; background:white; color:#c0392b;
                   border:1px solid white; border-radius:4px; font-size:12px; margin-left:12px;">
            Dismiss
        </button>`;

    const btnDismiss = document.getElementById('btn-dismiss-alerts');
    if (btnDismiss) {
        btnDismiss.addEventListener('click', async () => {
            await acknowledgeAlerts(workspacePath);
            banner.style.display = 'none';
        });
    }
}
