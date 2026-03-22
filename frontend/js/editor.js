// frontend/js/editor.js

/**
 * Encapsulates TipTap Editor initialization and configuration.
 */
import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import TextStyle from '@tiptap/extension-text-style';
import Color from '@tiptap/extension-color';
import FontFamily from '@tiptap/extension-font-family';
import TextAlign from '@tiptap/extension-text-align';
import Underline from '@tiptap/extension-underline';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableCell from '@tiptap/extension-table-cell';
import TableHeader from '@tiptap/extension-table-header';
import { ResizableImage } from './resizableImage.js';
import { MathNode } from './mathNode.js';
import { AnnotationMark } from './annotations.js';
import { uploadImageBinary } from './api.js';
import { openCropperModal } from './cropperModal.js';

// Module-level workspace path, updated when a workspace is created
let _workspacePath = null;

export function setWorkspacePath(path) {
    _workspacePath = path;
}

export function getWorkspacePath() {
    return _workspacePath;
}

export function initializeEditor(containerId, onChangeCallback, workspacePath = null) {
    _workspacePath = workspacePath;
    const element = document.getElementById(containerId);

    if (!element) {
        console.error(`Editor container #${containerId} not found.`);
        return null;
    }

    const editor = new Editor({
        element: element,
        extensions: [
            StarterKit,
            // TextStyle must precede Color and FontFamily (they extend its mark)
            TextStyle,
            Color,
            FontFamily,
            TextAlign.configure({ types: ['heading', 'paragraph'] }),
            Underline,
            // Table must precede TableRow / TableCell / TableHeader
            Table.configure({ resizable: true }),
            TableRow,
            TableCell,
            TableHeader,
            AnnotationMark,
            MathNode,
            ResizableImage.configure({
                inline: true,
                allowBase64: true,
            }),
        ],
        editorProps: {
            handleDrop: function(view, event, slice, moved) {
                if (!moved && event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0]) {
                    const file = event.dataTransfer.files[0];
                    if (file.type.startsWith('image/')) {
                        event.preventDefault();
                        const coordinates = view.posAtCoords({ left: event.clientX, top: event.clientY });
                        openCropperModal(file, (croppedFile) => {
                            uploadImageBinary(croppedFile, _workspacePath).then(url => {
                                if (url && coordinates) {
                                    view.dispatch(view.state.tr.insert(
                                        coordinates.pos,
                                        view.state.schema.nodes.image.create({ src: url })
                                    ));
                                }
                            });
                        });
                        return true;
                    }
                }
                return false;
            },
            handlePaste: function(view, event) {
                if (event.clipboardData && event.clipboardData.files && event.clipboardData.files[0]) {
                    const file = event.clipboardData.files[0];
                    if (file.type.startsWith('image/')) {
                        event.preventDefault();
                        openCropperModal(file, (croppedFile) => {
                            uploadImageBinary(croppedFile, _workspacePath).then(url => {
                                if (url) {
                                    view.dispatch(view.state.tr.replaceSelectionWith(
                                        view.state.schema.nodes.image.create({ src: url })
                                    ));
                                }
                            });
                        });
                        return true;
                    }
                }
                return false;
            },
        },
        editable: false,
        content: `
            <h1>Untitled Document</h1>
            <p>Start writing your scientific article here...</p>
        `,
        onUpdate: ({ editor }) => {
            const html = editor.getHTML();
            onChangeCallback(html);
        },
    });

    return editor;
}
