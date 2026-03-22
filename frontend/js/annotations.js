// frontend/js/annotations.js

/**
 * Annotations & Element Tracker (Feature 5)
 *
 * Exports:
 *   AnnotationMark  — TipTap Mark extension for inline custom annotations
 *   initAnnotationTracker(getEditor, getPanelEl) — scans the document for
 *     auto-numbered elements (figures, tables, equations) and custom annotations
 */

import { Mark, mergeAttributes } from '@tiptap/core';

// ---------------------------------------------------------------------------
// TipTap Mark: custom annotation
// ---------------------------------------------------------------------------

export const AnnotationMark = Mark.create({
    name: 'annotation',

    addAttributes() {
        return {
            annotationId:   { default: null },
            annotationNote: { default: '' },
        };
    },

    parseHTML() {
        return [{
            tag: 'span[data-annotation-id]',
            getAttrs: el => ({
                annotationId:   el.getAttribute('data-annotation-id'),
                annotationNote: el.getAttribute('data-annotation-note') || '',
            }),
        }];
    },

    renderHTML({ HTMLAttributes }) {
        return [
            'span',
            mergeAttributes(
                {
                    'data-annotation-id':   HTMLAttributes.annotationId,
                    'data-annotation-note': HTMLAttributes.annotationNote,
                    class: 'annotation-mark',
                    title: HTMLAttributes.annotationNote,
                },
            ),
            0,
        ];
    },

    addCommands() {
        return {
            setAnnotation: attrs => ({ commands }) =>
                commands.setMark('annotation', attrs),
            unsetAnnotation: () => ({ commands }) =>
                commands.unsetMark('annotation'),
        };
    },
});

// ---------------------------------------------------------------------------
// Tracker
// ---------------------------------------------------------------------------

export function initAnnotationTracker(getEditor, getPanelEl) {
    return {
        scan:             ()     => _scan(getEditor(), getPanelEl()),
        insertAnnotation: ()     => _insertAnnotation(getEditor()),
    };
}

function _insertAnnotation(editor) {
    if (!editor) return;
    const { from, to } = editor.state.selection;
    if (from === to) {
        alert('Select some text first, then click "Add Annotation".');
        return;
    }
    const note = window.prompt('Annotation note:');
    if (!note) return;
    const id = `ann-${Date.now()}`;
    editor.chain().focus().setAnnotation({ annotationId: id, annotationNote: note }).run();
}

function _scan(editor, panelEl) {
    if (!editor || !panelEl) return;

    const html = editor.getHTML();
    const div  = document.createElement('div');
    div.innerHTML = html;

    const sections = [];

    // --- Figures (img elements not inside a figure) + figure elements ---
    const figures = [...div.querySelectorAll('figure, img:not(figure img)')];
    figures.forEach((el, i) => {
        const caption = el.querySelector?.('figcaption')?.textContent?.trim() || '';
        sections.push({
            type:    'Figure',
            number:  i + 1,
            label:   caption ? `Figure ${i + 1}: ${caption}` : `Figure ${i + 1}`,
            tagName: el.tagName,
        });
    });

    // --- Tables ---
    const tables = [...div.querySelectorAll('table')];
    tables.forEach((el, i) => {
        const caption = el.querySelector('caption')?.textContent?.trim() || '';
        sections.push({
            type:   'Table',
            number: i + 1,
            label:  caption ? `Table ${i + 1}: ${caption}` : `Table ${i + 1}`,
        });
    });

    // --- Equations (math nodes render as .math-render-node) ---
    const equations = [...div.querySelectorAll('.math-render-node, math-node')];
    equations.forEach((el, i) => {
        sections.push({
            type:   'Equation',
            number: i + 1,
            label:  `Equation ${i + 1}`,
        });
    });

    // --- Custom annotations ---
    const annotations = [...div.querySelectorAll('[data-annotation-id]')];
    const annotationItems = annotations.map(el => ({
        type: 'Annotation',
        id:   el.getAttribute('data-annotation-id'),
        note: el.getAttribute('data-annotation-note') || '',
        text: el.textContent?.trim().substring(0, 60) || '',
    }));

    // Render
    if (sections.length === 0 && annotationItems.length === 0) {
        panelEl.innerHTML = '<p class="ann-empty">No figures, tables, equations, or annotations in this document.</p>';
        return;
    }

    let html2 = '';

    if (sections.length > 0) {
        html2 += '<ul class="ann-list">';
        for (const s of sections) {
            const iconMap = { Figure: '🖼️', Table: '⊞', Equation: '∑' };
            html2 += `<li class="ann-item">
                <span class="ann-type-badge ann-${s.type.toLowerCase()}">${iconMap[s.type] || ''} ${s.type}</span>
                <span class="ann-label">${s.label}</span>
            </li>`;
        }
        html2 += '</ul>';
    }

    if (annotationItems.length > 0) {
        html2 += '<div class="ann-section-title">Custom Annotations</div><ul class="ann-list">';
        for (const a of annotationItems) {
            html2 += `<li class="ann-item">
                <span class="ann-type-badge ann-annotation">📌</span>
                <span class="ann-label">"${a.text}"</span>
                <span class="ann-note">${a.note}</span>
            </li>`;
        }
        html2 += '</ul>';
    }

    panelEl.innerHTML = html2;
}
