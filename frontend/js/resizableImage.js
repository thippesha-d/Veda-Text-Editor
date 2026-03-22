// frontend/js/resizableImage.js

import Image from '@tiptap/extension-image';
import { mergeAttributes } from '@tiptap/core';

/**
 * Custom TipTap Image Node with native drag-to-resize handles.
 */
export const ResizableImage = Image.extend({
    addAttributes() {
        return {
            ...this.parent?.(),
            width: {
                default: '100%',
                renderHTML: attributes => {
                    return { width: attributes.width };
                }
            },
            height: {
                default: 'auto',
                renderHTML: attributes => {
                    return { height: attributes.height };
                }
            }
        };
    },

    addNodeView() {
        return ({ node, getPos, editor }) => {
            const wrapper = document.createElement('span');
            wrapper.classList.add('image-resize-wrapper');

            const img = document.createElement('img');
            img.src = node.attrs.src;
            img.style.width = node.attrs.width || '100%';
            img.style.height = node.attrs.height || 'auto';
            if (node.attrs.alt) img.alt = node.attrs.alt;
            if (node.attrs.title) img.title = node.attrs.title;

            // Custom resize handle
            const handle = document.createElement('div');
            handle.classList.add('image-resize-handle');

            let isResizing = false;
            let startWidth = 0;
            let startHeight = 0;
            let startX = 0;
            let startY = 0;

            handle.addEventListener('mousedown', (e) => {
                e.preventDefault();
                isResizing = true;
                startWidth = img.offsetWidth;
                startHeight = img.offsetHeight;
                startX = e.clientX;
                startY = e.clientY;

                const onMouseMove = (moveEvent) => {
                    if (!isResizing) return;
                    // Calculate precise delta
                    const diffX = moveEvent.clientX - startX;
                    const diffY = moveEvent.clientY - startY;

                    const newWidth = startWidth + diffX;
                    const newHeight = startHeight + diffY;

                    img.style.width = `${newWidth}px`;
                    img.style.height = `${newHeight}px`;
                };

                const onMouseUp = () => {
                    if (isResizing) {
                        isResizing = false;
                        document.removeEventListener('mousemove', onMouseMove);
                        document.removeEventListener('mouseup', onMouseUp);

                        // Dispatch mutation update to TipTap AST to permanently save sizing inline
                        if (typeof getPos === 'function') {
                            editor.view.dispatch(
                                editor.view.state.tr.setNodeMarkup(getPos(), undefined, {
                                    ...node.attrs,
                                    width: img.style.width,
                                    height: img.style.height
                                })
                            );
                        }
                    }
                };

                document.addEventListener('mousemove', onMouseMove);
                document.addEventListener('mouseup', onMouseUp);
            });

            wrapper.appendChild(img);
            wrapper.appendChild(handle);

            return {
                dom: wrapper,
            };
        };
    }
});
