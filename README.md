# Veda — Scientific Article Editor

A desktop application for writing, versioning, and managing scientific articles. Built with Python (FastAPI + pywebview) and a browser-based editor (TipTap).

---

## Features

- **WYSIWYG editor** — rich text editing with headings, lists, tables, and mathematical equations (KaTeX)
- **Image embedding** — drag-and-drop with optional Git LFS tracking for large files
- **Git-backed workspaces** — every workspace is a local Git repository with automatic commits
- **Semantic branch management** — create, switch, merge, and diff branches backed by Git worktrees
- **GitHub integration** — clone a repository as a workspace; set or update the `origin` remote
- **DOI detection & validation** — auto-scans article text for DOIs and checks their health
- **Link rot detection** — checks all hyperlinks in the article for broken URLs
- **CSL-based citation formatting** — formats DOI and manual references in APA, MLA, Chicago, and more
- **Article lifecycle state machine** — Draft → Under Review → Published workflow with adverse event alerts
- **Metadata panel** — title, authors, abstract, keywords, tags, journal
- **Manual references manager** — CRUD for custom CSL-JSON references
- **Annotations tracker** — figures, tables, equations, and inline annotation marks
- **Git LFS** — optional large-file storage, with per-workspace enable/disable toggle
- **Dark / Light theme** — persisted in localStorage
- **Save As / Print** — native OS save dialog via pywebview API; `@media print` CSS for PDF export

---

## Requirements

- Python 3.11+
- Windows 10/11 (pywebview uses WebView2 on Windows)
- [Git](https://git-scm.com/) installed and on `PATH`
- (Optional) [Git LFS](https://git-lfs.com/) for large-file tracking

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-org/veda.git
cd veda

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r backend/requirements.txt

# 4. Run the app
python -m backend.main
```

Or use the included launcher:

```
launch.bat
```

---

## Project Structure

```
veda/
├── backend/
│   ├── main.py                  # App entry point — FastAPI + pywebview
│   ├── .env                     # Environment config (PORT, WORKSPACE_DIR)
│   ├── api/
│   │   ├── document_router.py   # Workspace, document, metadata, LFS endpoints
│   │   ├── branch_router.py     # Git branch / worktree endpoints
│   │   ├── references_router.py # DOI validation endpoints
│   │   ├── linkcheck_router.py  # Link health check endpoints
│   │   ├── citations_router.py  # CSL citation formatting endpoints
│   │   └── lifecycle_router.py  # Article lifecycle state machine endpoints
│   ├── services/
│   │   ├── file_service.py      # Workspace / document / metadata I/O
│   │   ├── git_service.py       # Git operations (init, commit, clone, diff, remote)
│   │   ├── branch_service.py    # Worktree management
│   │   ├── lfs_service.py       # Git LFS configure/disable/status
│   │   └── scheduler_service.py # Background auto-commit timer
│   └── tests/                   # Pytest test suite (192 tests)
├── frontend/
│   ├── index.html               # Single-page app shell
│   ├── js/
│   │   ├── main.js              # App entry point — workspace + panel wiring
│   │   ├── editor.js            # TipTap editor initialisation
│   │   ├── toolbar.js           # Formatting toolbar
│   │   ├── api.js               # HTTP client for all backend endpoints
│   │   ├── branch.js            # Branch manager UI + diff / conflict viewer
│   │   ├── doi.js               # DOI scanner UI
│   │   ├── linkcheck.js         # Link checker UI
│   │   ├── citations.js         # Citation manager UI
│   │   ├── lifecycle.js         # Lifecycle manager UI
│   │   ├── annotations.js       # Annotation tracker UI
│   │   ├── references.js        # Manual references UI
│   │   └── metadata.js          # Metadata panel UI
│   └── styles/
│       ├── main.css             # App layout, panels, workspace bar, dark mode
│       └── editor.css           # ProseMirror canvas, diff viewer, print styles
├── workspace/                   # Default workspace storage (git-ignored)
├── dist/                        # PyInstaller build output (git-ignored)
├── build/                       # PyInstaller intermediate files (git-ignored)
├── veda.spec                    # PyInstaller build spec
├── launch.bat                   # Windows launcher script
└── README.md
```

---

## Running Tests

```bash
venv\Scripts\activate
python -m pytest --tb=short -q
```

---

## Building a Distributable

```bash
venv\Scripts\activate
pyinstaller veda.spec
```

Output is in `dist/veda/`. Distribute the entire `dist/veda/` folder — `veda.exe` and `_internal/` must stay together. Workspaces are stored in `dist/veda/workspace/` (next to the exe).

---

## Environment Variables

Configured in `backend/.env`:

| Variable        | Default       | Description                              |
|-----------------|---------------|------------------------------------------|
| `PORT`          | `8000`        | Port the internal FastAPI server runs on |
| `WORKSPACE_DIR` | `./workspace` | Directory where workspaces are stored    |
| `GIT_USER_NAME` | `Veda Editor` | Git author name for auto-commits         |
| `GIT_USER_EMAIL`| `veda@local`  | Git author email for auto-commits        |
