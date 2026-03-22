// frontend/js/mathNode.js

/**
 * Custom TipTap Node Extension for Mathematical Equation Rendering via KaTeX.
 * Parses standard LaTeX syntax inline ($...$) and in display mode ($$...$$).
 */
import { Node, mergeAttributes, InputRule } from '@tiptap/core';

export const MathNode = Node.create({
    name: 'mathNode',
    group: 'inline',
    inline: true,
    atom: true, // Treated as a single undeletable block character unless fully selected

    addAttributes() {
        return {
            latex: { default: '' },
            displayMode: { default: false }
        };
    },

    parseHTML() {
        return [
            { tag: 'span[data-math]' }
        ];
    },

    renderHTML({ HTMLAttributes }) {
        // Fallback semantic HTML for serialization
        return ['span', mergeAttributes(HTMLAttributes, { 'data-math': '' }), HTMLAttributes.latex];
    },

    addNodeView() {
        return ({ node, getPos, editor }) => {
            const dom = document.createElement('span');
            dom.classList.add('math-render-node');
            
            if (node.attrs.displayMode) {
                dom.classList.add('math-display');
            }

            // Centralized render logic
            const renderMath = () => {
                if (!window.katex) {
                    dom.innerText = 'Loading KaTeX...';
                    return;
                }

                try {
                    window.katex.render(node.attrs.latex, dom, { 
                        throwOnError: true,
                        displayMode: node.attrs.displayMode
                    });
                    dom.classList.remove('math-error');
                    dom.title = 'Click to edit equation';
                } catch(err) {
                    // Fallback to raw LaTeX string with error highlight
                    dom.innerText = node.attrs.latex || 'Empty Equation';
                    dom.classList.add('math-error');
                    dom.title = err.message;
                }
            };

            // Render immediately on creation
            renderMath();

            // Real-time re-rendering trigger (Click-to-edit behavior)
            dom.addEventListener('click', (e) => {
                e.preventDefault();
                // Simple browser prompt for modifying the LaTeX payload
                const newLatex = prompt('Edit Equation (LaTeX):', node.attrs.latex);
                if (newLatex !== null && typeof getPos === 'function') {
                    // Dispatch state mutation to TipTap store
                    editor.view.dispatch(
                        editor.view.state.tr.setNodeMarkup(getPos(), undefined, {
                            ...node.attrs,
                            latex: newLatex
                        })
                    );
                }
            });

            return {
                dom,
                update: (updatedNode) => {
                    // Triggered when TipTap internal state for this exact node mutates
                    if (updatedNode.type.name !== this.name) return false;
                    node = updatedNode;
                    renderMath();
                    return true;
                }
            };
        };
    },

    addInputRules() {
        // Regex to intercept $E=mc^2$ and wrap cleanly
        const inlineMathRegex = /(?:^|\s)\$([^$]+)\$$/;
        // Regex to intercept $$x^2$$
        const displayMathRegex = /^\$\$([^$]+)\$\$$/;

        return [
            new InputRule({
                find: inlineMathRegex,
                handler: ({ state, range, match }) => {
                    const { tr } = state;
                    // Account for the leading space matched by (?:^|\s)
                    const matchLength = match[0].length;
                    const valueLength = match[1].length + 2; // +2 for the $ signs
                    const spaces = matchLength - valueLength;
                    
                    const start = range.from + spaces;
                    const end = range.to;
                    const latex = match[1];

                    if (latex) {
                        tr.replaceWith(start, end, this.type.create({ latex, displayMode: false }));
                    }
                }
            }),
            new InputRule({
                find: displayMathRegex,
                handler: ({ state, range, match }) => {
                    const { tr } = state;
                    const start = range.from;
                    const end = range.to;
                    const latex = match[1];

                    if (latex) {
                        tr.replaceWith(start, end, this.type.create({ latex, displayMode: true }));
                    }
                }
            })
        ];
    }
});
