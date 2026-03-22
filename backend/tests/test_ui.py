import subprocess
import time
import pytest
import os
import tempfile
import sys

@pytest.fixture(scope="module")
def app_server():
    # Setup temp workspace
    port = 8010
    env = os.environ.copy()
    temp_dir = tempfile.mkdtemp()
    env["WORKSPACE_DIR"] = temp_dir
    env["PORT"] = str(port)
    
    # Start server using the virtual environment python
    python_exe = sys.executable
    proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "backend.main:app", "--port", str(port)],
        env=env
    )
    time.sleep(2) # Wait for server to start
    
    yield f"http://localhost:{port}"
    
    proc.terminate()
    proc.wait()

def test_create_workspace_ui(page, app_server):
    page.goto(app_server)
    
    # Check title
    assert "Scientific Article Editor" in page.title()
    
    # Wait for the input to appear
    page.wait_for_selector("#workspace-name-input")
    
    # Type into input
    page.fill("#workspace-name-input", "UI Test Workspace")
    
    # Click create
    page.click("#btn-create-workspace")
    
    # Verify status changes to Loaded
    page.wait_for_selector("id=workspace-status", state="visible")
    status_text = page.inner_text("id=workspace-status")
    
    # There could be a slight delay, wait until it contains "Git:"
    page.wait_for_function("document.getElementById('workspace-status').innerText.includes('Git:')", timeout=5000)
    
    status_text = page.inner_text("id=workspace-status")
    assert "Git:" in status_text

def test_zoom_controls(page, app_server):
    page.goto(app_server)
    page.wait_for_selector("#btn-zoom-in")
    
    # Check initial zoom
    zoom_text = page.inner_text("#zoom-level")
    assert "100%" in zoom_text
    
    # Click zoom in twice
    page.click("#btn-zoom-in")
    page.click("#btn-zoom-in")
    
    zoom_text = page.inner_text("#zoom-level")
    assert "120%" in zoom_text
    
    # Check CSS transform on canvas
    transform = page.evaluate("document.getElementById('editor-canvas').style.transform")
    assert "scale(1.2)" in transform
    
    # Click zoom out
    page.click("#btn-zoom-out")
    zoom_text = page.inner_text("#zoom-level")
    assert "110%" in zoom_text
