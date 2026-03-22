// frontend/js/toolbar.js

/**
 * Manages the editor toolbar state and dispatches formatting commands.
 * Handles buttons (data-action), font-family select, and font-color input.
 */
import { uploadImageBinary } from './api.js';
import { getWorkspacePath } from './editor.js';

export function setupToolbar(editor, annotationTracker) {
    const toolbar          = document.getElementById('editor-toolbar');
    const imageUploadInput = document.getElementById('image-upload-input');
    const fontFamilySelect = document.getElementById('font-family-select');
    const fontColorInput   = document.getElementById('font-color-input');

    if (!toolbar) return;

    // ── Button dispatch ────────────────────────────────────────────────────
    toolbar.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;
        const action = btn.getAttribute('data-action');

        switch (action) {
            // History
            case 'undo':   editor.chain().focus().undo().run();  break;
            case 'redo':   editor.chain().focus().redo().run();  break;

            // Clipboard
            case 'copy': {
                const { from, to } = editor.state.selection;
                const text = editor.state.doc.textBetween(from, to, '\n');
                if (text && navigator.clipboard) {
                    navigator.clipboard.writeText(text).catch(() => document.execCommand('copy'));
                } else {
                    document.execCommand('copy');
                }
                break;
            }
            case 'paste':
                if (navigator.clipboard) {
                    navigator.clipboard.readText().then(text => {
                        if (text) editor.chain().focus().insertContent(text).run();
                    }).catch(() => {});
                }
                break;

            // Character formatting
            case 'bold':      editor.chain().focus().toggleBold().run();      break;
            case 'italic':    editor.chain().focus().toggleItalic().run();    break;
            case 'underline': editor.chain().focus().toggleUnderline().run(); break;

            // Headings
            case 'h1': editor.chain().focus().toggleHeading({ level: 1 }).run(); break;
            case 'h2': editor.chain().focus().toggleHeading({ level: 2 }).run(); break;
            case 'h3': editor.chain().focus().toggleHeading({ level: 3 }).run(); break;

            // Block formatting
            case 'blockquote':    editor.chain().focus().toggleBlockquote().run();    break;
            case 'bulletList':    editor.chain().focus().toggleBulletList().run();    break;
            case 'orderedList':   editor.chain().focus().toggleOrderedList().run();   break;

            // Text alignment
            case 'align-left':    editor.chain().focus().setTextAlign('left').run();    break;
            case 'align-center':  editor.chain().focus().setTextAlign('center').run();  break;
            case 'align-right':   editor.chain().focus().setTextAlign('right').run();   break;
            case 'align-justify': editor.chain().focus().setTextAlign('justify').run(); break;

            // Tables
            case 'insertTable':
                editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
                break;
            case 'addRowAfter':    editor.chain().focus().addRowAfter().run();    break;
            case 'deleteRow':      editor.chain().focus().deleteRow().run();      break;
            case 'addColumnAfter': editor.chain().focus().addColumnAfter().run(); break;
            case 'deleteColumn':   editor.chain().focus().deleteColumn().run();   break;

            // Image
            case 'image':
                if (imageUploadInput) imageUploadInput.click();
                break;

            // Custom annotation
            case 'add-annotation':
                if (annotationTracker) annotationTracker.insertAnnotation();
                break;

            // Save as local copy
            case 'save-as': {
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
                break;
            }

            // Print
            case 'print':
                window.print();
                break;
        }

        updateToolbarState(editor);
    });

    // ── Font family select ─────────────────────────────────────────────────
    if (fontFamilySelect) {
        fontFamilySelect.addEventListener('change', () => {
            const val = fontFamilySelect.value;
            if (val) {
                editor.chain().focus().setFontFamily(val).run();
            } else {
                editor.chain().focus().unsetFontFamily().run();
            }
            updateToolbarState(editor);
        });
    }

    // ── Font color input ───────────────────────────────────────────────────
    if (fontColorInput) {
        fontColorInput.addEventListener('input', () => {
            editor.chain().focus().setColor(fontColorInput.value).run();
        });
    }

    // ── Image file input ───────────────────────────────────────────────────
    if (imageUploadInput) {
        imageUploadInput.addEventListener('change', async (event) => {
            const file = event.target.files[0];
            if (file) {
                const imageUrl = await uploadImageBinary(file, getWorkspacePath());
                if (imageUrl) editor.chain().focus().setImage({ src: imageUrl }).run();
            }
            imageUploadInput.value = '';
        });
    }

    // ── Selection / transaction change → sync toolbar state ───────────────
    editor.on('selectionUpdate', () => updateToolbarState(editor));
    editor.on('transaction',     () => updateToolbarState(editor));
}

// ---------------------------------------------------------------------------

export function updateToolbarState(editor) {
    const toolbar = document.getElementById('editor-toolbar');
    if (!toolbar) return;

    toolbar.querySelectorAll('button[data-action]').forEach(btn => {
        const action = btn.getAttribute('data-action');
        let active = false;
        switch (action) {
            case 'bold':          active = editor.isActive('bold');                     break;
            case 'italic':        active = editor.isActive('italic');                   break;
            case 'underline':     active = editor.isActive('underline');                break;
            case 'h1':            active = editor.isActive('heading', { level: 1 });    break;
            case 'h2':            active = editor.isActive('heading', { level: 2 });    break;
            case 'h3':            active = editor.isActive('heading', { level: 3 });    break;
            case 'blockquote':    active = editor.isActive('blockquote');               break;
            case 'bulletList':    active = editor.isActive('bulletList');               break;
            case 'orderedList':   active = editor.isActive('orderedList');              break;
            case 'align-left':    active = editor.isActive({ textAlign: 'left' });     break;
            case 'align-center':  active = editor.isActive({ textAlign: 'center' });   break;
            case 'align-right':   active = editor.isActive({ textAlign: 'right' });    break;
            case 'align-justify': active = editor.isActive({ textAlign: 'justify' });  break;
        }
        btn.classList.toggle('is-active', active);
    });

    // Sync color picker
    const colorInput = document.getElementById('font-color-input');
    if (colorInput) {
        const c = editor.getAttributes('textStyle').color;
        if (c && /^#[0-9a-fA-F]{6}$/.test(c)) colorInput.value = c;
    }

    // Sync font family select
    const fontSelect = document.getElementById('font-family-select');
    if (fontSelect) {
        fontSelect.value = editor.getAttributes('textStyle').fontFamily || '';
    }
}
