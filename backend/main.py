# backend/main.py
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import filedialog
import uvicorn
import webview
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# ── Frozen / development path resolution ────────────────────────────────────
if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle; data files are extracted to sys._MEIPASS
    _BASE = sys._MEIPASS
    # Workspaces live next to the executable (writable location)
    _WORKSPACE_DEFAULT = os.path.join(os.path.dirname(sys.executable), "workspace")
else:
    # Normal development run: project root is one level above backend/
    _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _WORKSPACE_DEFAULT = os.path.join(_BASE, "workspace")


class VedaAPI:
    """Exposed to the frontend as window.pywebview.api — handles OS-level operations."""

    def pick_folder(self) -> dict:
        """Opens a native OS folder picker dialog. Returns the selected path."""
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(
            parent=root,
            title='Select Workspace Folder',
        )
        root.destroy()
        if folder:
            return {'success': True, 'path': folder}
        return {'success': False, 'path': ''}

    def save_as(self, html_content: str, default_filename: str = 'article.html') -> dict:
        """Opens a native OS Save As dialog and writes the HTML file."""
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        filepath = filedialog.asksaveasfilename(
            parent=root,
            defaultextension='.html',
            filetypes=[('HTML files', '*.html'), ('All files', '*.*')],
            initialfile=default_filename,
            title='Save Article As',
        )
        root.destroy()
        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            return {'success': True, 'path': filepath}
        return {'success': False}

# Load environment variables
load_dotenv(os.path.join(_BASE, "backend", ".env"))
# Default workspace dir if not set by .env
os.environ.setdefault("WORKSPACE_DIR", _WORKSPACE_DEFAULT)

# Import API routers
from backend.api.document_router import router as document_router
from backend.api.branch_router import router as branch_router
from backend.api.references_router import router as references_router
from backend.api.linkcheck_router import router as linkcheck_router
from backend.api.citations_router import router as citations_router
from backend.api.lifecycle_router import router as lifecycle_router
from backend.services.scheduler_service import start_scheduler
from fastapi import Response
from fastapi.responses import FileResponse

# Initialize FastAPI
app = FastAPI(title="Scientific Article Editor API")

# Setup CORS for local embedded browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(document_router)
app.include_router(branch_router)
app.include_router(references_router)
app.include_router(linkcheck_router)
app.include_router(citations_router)
app.include_router(lifecycle_router)

# Dynamic per-workspace asset serving - replaces the global /assets static mount
@app.get("/api/workspace/assets/{workspace_folder}/{filename}")
async def serve_workspace_asset(workspace_folder: str, filename: str):
    """Dynamically serves an image from a specific workspace's assets/ subdirectory."""
    base_workspace_dir = os.environ.get("WORKSPACE_DIR", "./workspace")
    workspace_dir_abs = os.path.abspath(os.path.join(base_workspace_dir, workspace_folder))
    asset_path = os.path.abspath(os.path.join(workspace_dir_abs, "assets", filename))
    # Security: ensure path is inside the workspace dir
    if os.path.exists(asset_path) and asset_path.startswith(workspace_dir_abs):
        return FileResponse(asset_path)
    return Response(status_code=404, content="Asset not found")

# Mount frontend directory as static files
frontend_dir = os.path.join(_BASE, "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


def start_server(port: int):
    """Starts the Uvicorn ASGI server in a dedicated thread."""
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    
    # Start background auto-commit scheduler
    start_scheduler()
    
    # Run the internal FastAPI server asynchronously
    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()

    # Wait for the server to be ready before opening the window
    time.sleep(1)

    # Create the native desktop window wrapper and point it to our local server
    webview.create_window(
        title="Scientific Article Editor",
        url=f"http://127.0.0.1:{port}/",
        js_api=VedaAPI(),
        width=1200,
        height=850,
        min_size=(800, 600)
    )
    
    # Blocks exact thread until the desktop window is closed
    webview.start()
