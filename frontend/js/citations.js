// frontend/js/citations.js

/**
 * CSL-Based Citation Formatting  (REQ-3.3.4)
 *
 * Detects [@citation-key] markers in the editor, converts the DOI-validated
 * reference map to CSL-JSON, sends to the backend for style-based formatting,
 * then injects inline citations and a bibliography section into the editor.
 *
 * Citation key syntax:  [@<doi-or-custom-key>]
 * Example:              [@10.1234/nature12345]
 *
 * The DOI scanner (doi.js) populates _doiData which is shared here.
 */

import { formatCitations } from './api.js';

// ---------------------------------------------------------------------------
// Pattern that matches citation markers in the document text
// ---------------------------------------------------------------------------
const CITE_KEY_PATTERN = /\[@([^\]]+)\]/g;

// ID of the bibliography section node in the editor — injected as last block
const BIB_SENTINEL = '<!-- veda-bibliography -->';

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Initialises the citation manager.
 *
 * @param {() => object} getEditor  - Returns the TipTap editor instance (lazy, called at format time)
 * @param {Map}    doiValidated     - Map<doi, { doi, status, title, authors, year }> from doi.js
 * @param {() => string} getStyle   - Returns the currently selected style id
 */
export function initCitationManager(getEditor, doiValidated, getStyle, getManualRefs = null) {
    return {
        /**
         * Scans the editor for [@key] markers, formats them with the selected
         * style, and injects results back into the editor.
         * Manual refs (from the Reference Manager) are merged with DOI-validated refs.
         */
        format: () => _format(getEditor(), doiValidated, getStyle(), getManualRefs ? getManualRefs() : []),
    };
}

// ---------------------------------------------------------------------------
// Internal
// ---------------------------------------------------------------------------

/**
 * Normalises a raw citation key to a bare DOI string.
 * Accepts:
 *   10.1109/ICCCI50826.2021.9402322
 *   https://doi.org/10.1109/ICCCI50826.2021.9402322
 *   http://doi.org/10.1109/...
 *   doi:10.1109/...
 */
function _normalizeKey(raw) {
    return raw
        .trim()
        .replace(/^https?:\/\/doi\.org\//i, '')
        .replace(/^doi:/i, '');
}

function _extractKeys(html) {
    const div = document.createElement('div');
    div.innerHTML = html;
    const text = div.textContent || '';
    const keys = [];
    CITE_KEY_PATTERN.lastIndex = 0;
    let m;
    while ((m = CITE_KEY_PATTERN.exec(text)) !== null) {
        // Normalize so both [@10.xxx/...] and [@https://doi.org/10.xxx/...] resolve
        keys.push(_normalizeKey(m[1]));
    }
    return keys;   // duplicates preserved — order matters for numeric styles
}

function _toCSLJson(doiValidated) {
    /**
     * Converts the validated DOI map (from doi.js) to CSL-JSON.
     * The "id" field is the DOI string itself, which must match the
     * [@doi-string] citation key typed in the document.
     */
    const refs = [];
    for (const [doi, r] of doiValidated.entries()) {
        if (r.status === 'retracted' || r.status === 'not-found') continue;

        const entry = {
            id:   doi,
            type: 'article-journal',
            DOI:  doi,
        };
        if (r.title)   entry.title = r.title;
        if (r.year)    entry.issued = { 'date-parts': [[r.year]] };
        if (r.authors && r.authors.length > 0) {
            entry.author = r.authors.map(name => {
                const parts = name.split(' ');
                return {
                    family: parts[parts.length - 1] || name,
                    given:  parts.slice(0, -1).join(' '),
                };
            });
        }
        refs.push(entry);
    }
    return refs;
}

function _replaceCiteKeys(html, inlineMap, unresolvedKeys) {
    /**
     * Replaces [@key] markers with formatted inline citations.
     * The raw key is normalised before lookup so that
     * [@10.xxx/...] and [@https://doi.org/10.xxx/...] both resolve correctly.
     * Unresolved keys get a warning badge instead.
     */
    return html.replace(CITE_KEY_PATTERN, (match, rawKey) => {
        const key = _normalizeKey(rawKey);
        if (inlineMap[key] !== undefined) {
            return inlineMap[key];
        }
        if (unresolvedKeys.includes(key)) {
            return `<span class="cite-unresolved" title="Unresolved citation: ${key}">[?]</span>`;
        }
        return match;  // leave unchanged if key wasn't submitted
    });
}

function _buildBibSection(bibliographyHtml) {
    return (
        `<hr/>` +
        `<h2>References</h2>` +
        `<div class="bibliography">${bibliographyHtml}</div>`
    );
}

async function _format(editor, doiValidated, style, manualRefs = []) {
    if (!editor) return;

    const html = editor.getHTML();
    const keys = _extractKeys(html);
    if (keys.length === 0) return;

    const doiRefs = _toCSLJson(doiValidated);
    const refs    = [...doiRefs, ...manualRefs];
    if (refs.length === 0) return;   // nothing validated or added yet

    const res = await formatCitations(refs, keys, style);
    if (!res || !res.inline_map) return;

    // Replace [@key] markers with formatted inline citations
    CITE_KEY_PATTERN.lastIndex = 0;
    let newHtml = _replaceCiteKeys(html, res.inline_map, res.unresolved_keys || []);

    // Remove any previous bibliography section, then append the new one
    const bibStart = newHtml.indexOf(BIB_SENTINEL);
    if (bibStart !== -1) {
        newHtml = newHtml.substring(0, bibStart);
    }

    if (res.bibliography_html) {
        newHtml += `\n${BIB_SENTINEL}\n${_buildBibSection(res.bibliography_html)}`;
    }

    // Preserve cursor position
    const { from, to } = editor.state.selection;
    editor.commands.setContent(newHtml, false);
    try {
        editor.commands.setTextSelection({ from, to });
    } catch {
        // selection may be out of range if content shrank — ignore
    }
}
