// frontend/js/api.js

/**
 * Handles communication with the local Python backend.
 */

let saveTimeout = null;
const SAVE_DEBOUNCE_MS = 1000;

// Module-level active workspace path (updated by setActiveWorkspace)
let _activeWorkspacePath = null;
export function setActiveWorkspace(path) { _activeWorkspacePath = path; }

/**
 * Debounced API call to save document HTML to the local backend.
 * @param {string} htmlContent - The TipTap Editor's HTML string output.
 * @param {function} onSaveStateChange - Callback function to update UI status text.
 */
export function debouncedSave(htmlContent, onSaveStateChange) {
    onSaveStateChange('Saving...');
    
    if (saveTimeout) {
        clearTimeout(saveTimeout);
    }
    
    saveTimeout = setTimeout(async () => {
        try {
            const response = await fetch('/api/document/save', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ html: htmlContent, workspace_path: _activeWorkspacePath || "" })
            });
            
            if (response.ok) {
                onSaveStateChange('All changes saved');
            } else {
                const errText = await response.text();
                console.error("Failed to save document:", errText);
                onSaveStateChange('Error saving');
            }
        } catch (error) {
            console.error("API connection error:", error);
            onSaveStateChange('Backend offline');
        }
    }, SAVE_DEBOUNCE_MS);
}

/**
 * Uploads an image binary to the backend within the specified workspace.
 * @param {File} file - The image file object.
 * @param {string} workspacePath - The active workspace path to store the asset in.
 * @returns {Promise<string|null>} Resolves to the image URL or null on failure.
 */
export async function uploadImageBinary(file, workspacePath) {
    const formData = new FormData();
    formData.append('file', file);
    if (workspacePath) {
        formData.append('workspace_path', workspacePath);
    }

    try {
        const response = await fetch('/api/media/upload', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            const data = await response.json();
            return data.url;
        } else {
            console.error("Failed to upload image:", await response.text());
            return null;
        }
    } catch (error) {
        console.error("Image upload connection error:", error);
        return null;
    }
}

/**
 * Creates a new workspace via the backend API.
 * @param {string} name - The requested workspace name.
 */
export async function createWorkspace(name) {
    try {
        const response = await fetch('/api/workspace/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (response.ok) {
            return await response.json();
        } else {
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            return { error: err.detail || 'Server error' };
        }
    } catch (e) {
        return { error: e.message || 'Connection failed — is the server running?' };
    }
}

/**
 * Triggers a manual or structural auto-commit.
 */
export async function triggerAutoCommit(workspacePath, reason) {
    try {
        const response = await fetch('/api/document/commit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, trigger: reason })
        });
        if (response.ok) return await response.json();
        return null;
    } catch (e) {
        console.error("Failed to trigger auto-commit:", e);
        return null;
    }
}

/**
 * Loads the current article.html content from the workspace.
 * Called after branch switches to reload the editor.
 * @param {string} workspacePath
 * @returns {Promise<string|null>} HTML string or null on failure.
 */
export async function loadDocument(workspacePath) {
    try {
        const response = await fetch('/api/document/load?workspace_path=' + encodeURIComponent(workspacePath));
        if (response.ok) {
            const data = await response.json();
            return data.html;
        }
        console.error("Failed to load document:", await response.text());
        return null;
    } catch (e) {
        console.error("loadDocument error:", e);
        return null;
    }
}

/**
 * Fetches LFS availability and storage usage for the workspace.
 * @param {string} workspacePath
 * @returns {Promise<object|null>} { lfs_available, lfs_configured, total_mb, file_count }
 */
export async function getLfsStatus(workspacePath) {
    try {
        const response = await fetch('/api/workspace/lfs-status?workspace_path=' + encodeURIComponent(workspacePath));
        if (response.ok) return await response.json();
        return null;
    } catch (e) {
        return null;
    }
}

/**
 * Formats citations via the backend CSL processor.
 * @param {Array}  references    - CSL-JSON reference objects
 * @param {Array}  citationKeys  - Citation keys present in the document
 * @param {string} style         - Style id: "apa" | "ieee" | "nature" | "chicago" | "vancouver"
 * @returns {Promise<object|null>} { style, inline_map, bibliography_html, unresolved_keys }
 */
export async function formatCitations(references, citationKeys, style = 'apa') {
    try {
        const response = await fetch('/api/citations/format', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ references, citation_keys: citationKeys, style }),
        });
        if (response.ok) return await response.json();
        console.error('formatCitations: server error', response.status);
        return null;
    } catch (e) {
        console.error('formatCitations error:', e);
        return null;
    }
}

/**
 * Triggers a link-rot check for all URLs found in the given HTML.
 * @param {string} workspacePath
 * @param {string} htmlContent
 * @returns {Promise<{status: string, results: Array}|null>}
 */
export async function triggerLinkCheck(workspacePath, htmlContent) {
    try {
        const response = await fetch('/api/links/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, html_content: htmlContent }),
        });
        if (response.ok) return await response.json();
        console.error('triggerLinkCheck: server error', response.status);
        return null;
    } catch (e) {
        console.error('triggerLinkCheck error:', e);
        return null;
    }
}

/**
 * Fetches the persisted link-check log without triggering a new check.
 * @param {string} workspacePath
 * @returns {Promise<{status: string, results: Array}|null>}
 */
export async function getLinkStatus(workspacePath) {
    try {
        const response = await fetch('/api/links/status?workspace_path=' + encodeURIComponent(workspacePath));
        if (response.ok) return await response.json();
        return null;
    } catch (e) {
        return null;
    }
}

/**
 * Sends a batch of DOIs to the backend for health validation.
 * @param {string[]} dois - Array of DOI strings to validate.
 * @returns {Promise<{status: string, results: Array}|null>}
 */
export async function validateDois(dois) {
    try {
        const response = await fetch('/api/references/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dois }),
        });
        if (response.ok) return await response.json();
        console.error('validateDois: server error', response.status);
        return null;
    } catch (e) {
        console.error('validateDois error:', e);
        return null;
    }
}

// ---------------------------------------------------------------------------
// Metadata API  (Feature-7)
// ---------------------------------------------------------------------------

/**
 * Fetches document metadata (title, authors, abstract, keywords, tags, …).
 * @param {string} workspacePath
 * @returns {Promise<object|null>}
 */
export async function getMetadata(workspacePath) {
    try {
        const response = await fetch('/api/document/metadata?workspace_path=' + encodeURIComponent(workspacePath));
        if (response.ok) return await response.json();
        return null;
    } catch (e) { return null; }
}

/**
 * Saves document metadata to workspace.json.
 * @param {string} workspacePath
 * @param {object} metadata
 * @returns {Promise<object|null>}
 */
export async function saveMetadata(workspacePath, metadata) {
    try {
        const response = await fetch('/api/document/metadata', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, metadata }),
        });
        if (response.ok) return await response.json();
        return null;
    } catch (e) { return null; }
}

// ---------------------------------------------------------------------------
// Manual References API  (Feature-5)
// ---------------------------------------------------------------------------

/**
 * Fetches all manual references from workspace.json.
 * @param {string} workspacePath
 * @returns {Promise<{refs: Array}|null>}
 */
export async function getManualReferences(workspacePath) {
    try {
        const response = await fetch('/api/references/manual?workspace_path=' + encodeURIComponent(workspacePath));
        if (response.ok) return await response.json();
        return null;
    } catch (e) { return null; }
}

/**
 * Adds or updates a manual reference in workspace.json.
 * @param {string} workspacePath
 * @param {object} ref
 * @returns {Promise<{status, ref}|null>}
 */
export async function saveManualReference(workspacePath, ref) {
    try {
        const response = await fetch('/api/references/manual', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, ref }),
        });
        if (response.ok) return await response.json();
        return null;
    } catch (e) { return null; }
}

/**
 * Deletes a manual reference by ref_id.
 * @param {string} workspacePath
 * @param {string} refId
 * @returns {Promise<object|null>}
 */
export async function deleteManualReference(workspacePath, refId) {
    try {
        const response = await fetch(
            `/api/references/manual/${encodeURIComponent(refId)}?workspace_path=${encodeURIComponent(workspacePath)}`,
            { method: 'DELETE' }
        );
        if (response.ok) return await response.json();
        return null;
    } catch (e) { return null; }
}

// ---------------------------------------------------------------------------
// Lifecycle API  (REQ-3.4.1–3.4.4)
// ---------------------------------------------------------------------------

/**
 * Fetches the current lifecycle state for a workspace.
 * @param {string} workspacePath
 * @returns {Promise<object|null>}
 */
export async function getLifecycleState(workspacePath) {
    try {
        const response = await fetch('/api/lifecycle/state?workspace_path=' + encodeURIComponent(workspacePath));
        if (response.ok) return await response.json();
        return null;
    } catch (e) {
        return null;
    }
}

/**
 * Transitions the article to a new lifecycle state.
 * @param {string} workspacePath
 * @param {string} newState
 * @param {string} note
 * @returns {Promise<object|null>}
 */
export async function transitionLifecycle(workspacePath, newState, note = '') {
    try {
        const response = await fetch('/api/lifecycle/transition', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, new_state: newState, note }),
        });
        if (response.ok) return await response.json();
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        return { detail: err.detail || 'Transition failed' };
    } catch (e) {
        return null;
    }
}

/**
 * Registers the article's own published DOI and publisher URL.
 * @param {string} workspacePath
 * @param {string} doi
 * @param {string} publisherUrl
 * @returns {Promise<object|null>}
 */
export async function setArticleDoi(workspacePath, doi, publisherUrl = '') {
    try {
        const response = await fetch('/api/lifecycle/article-doi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, doi, publisher_url: publisherUrl }),
        });
        if (response.ok) return await response.json();
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        return { detail: err.detail || 'Failed to set DOI' };
    } catch (e) {
        return null;
    }
}

/**
 * Acknowledges (dismisses) all active lifecycle alerts.
 * @param {string} workspacePath
 * @returns {Promise<object|null>}
 */
export async function acknowledgeAlerts(workspacePath) {
    try {
        const response = await fetch('/api/lifecycle/alerts/acknowledge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath }),
        });
        if (response.ok) return await response.json();
        return null;
    } catch (e) {
        return null;
    }
}

// ---------------------------------------------------------------------------

/**
 * Polls the backend for the latest commit status.
 */
export async function pollWorkspaceStatus(workspacePath) {
    try {
        const response = await fetch('/api/workspace/status?workspace_path=' + encodeURIComponent(workspacePath));
        if (response.ok) return await response.json();
        return null;
    } catch (e) {
        return null;
    }
}

export async function enableLfs(workspacePath) {
    try {
        const response = await fetch('/api/workspace/lfs-enable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath }),
        });
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Failed to enable LFS' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}

export async function disableLfs(workspacePath) {
    try {
        const response = await fetch('/api/workspace/lfs-disable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath }),
        });
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Failed to disable LFS' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}

export async function loadWorkspace(workspacePath) {
    try {
        const response = await fetch('/api/workspace/load', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath }),
        });
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Failed to load workspace' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}

export async function deleteWorkspace(workspacePath) {
    try {
        const response = await fetch('/api/workspace/delete', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath }),
        });
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Failed to delete workspace' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}

export async function cloneWorkspace(remoteUrl) {
    try {
        const response = await fetch('/api/workspace/clone', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ remote_url: remoteUrl }),
        });
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Clone failed' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}

export async function getWorkspaceRemote(workspacePath) {
    try {
        const response = await fetch('/api/workspace/remote?workspace_path=' + encodeURIComponent(workspacePath));
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Failed to get remote' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}

export async function setWorkspaceRemote(workspacePath, remoteUrl) {
    try {
        const response = await fetch('/api/workspace/remote', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_path: workspacePath, remote_url: remoteUrl }),
        });
        const data = await response.json();
        if (!response.ok) return { error: data.detail || 'Failed to set remote' };
        return data;
    } catch (e) {
        return { error: e.message || 'Network error' };
    }
}
