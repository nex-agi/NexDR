# Copyright (c) Nex-AGI. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Streamlit frontend for NexDR with real-time log display."""

import html
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from queue import Queue, Empty

import streamlit as st
import streamlit.components.v1 as components

# Page configuration
st.set_page_config(page_title="NexDR", layout="wide")

# Style definitions
st.markdown(
    """
<style>
    .stApp {
        max-width: 100%;
    }
    .status-running {
        color: #FF9800;
        font-weight: bold;
    }
    .status-completed {
        color: #4CAF50;
        font-weight: bold;
    }
    .status-error {
        color: #F44336;
        font-weight: bold;
    }
    /* Fixed height log container */
    .log-container {
        height: 500px;
        overflow-y: auto;
        overflow-x: auto;
        background-color: #ffffff;  /* White background */
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 15px;
        font-family: 'Courier New', monospace;
        font-size: 12px;
        line-height: 1.4;
        color: #333;  /* Dark text */
    }
    /* Fixed height code block */
    div[data-testid="stCodeBlock"] {
        height: 100%;
        max-height: 500px !important;
    }
    div[data-testid="stCodeBlock"] > div {
        height: 100%;
        max-height: 500px !important;
    }
    div[data-testid="stCodeBlock"] pre {
        height: 100%;
        max-height: 500px !important;
        overflow-y: auto !important;
        overflow-x: auto !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Title
st.title("NexDR - Nex Deep Resaerch Agent")
st.markdown("---")


def read_output(pipe, queue):
    """Read process output in background thread"""
    try:
        for line in iter(pipe.readline, ""):
            if line:
                queue.put(line)
        pipe.close()
    except Exception:
        pass


def contains_emoji(text: str) -> bool:
    """Detect if text contains emoji"""
    # Unicode ranges covering most emojis
    emoji_pattern = re.compile(
        "["
        "\U0001f300-\U0001f9ff"  # Various symbols and pictographs
        "\U0001f600-\U0001f64f"  # Emoticons
        "\U0001f680-\U0001f6ff"  # Transport and map symbols
        "\U0001f1e0-\U0001f1ff"  # Flags
        "\U00002702-\U000027b0"  # Miscellaneous symbols
        "\U000024c2-\U0001f251"  # Enclosed characters
        "]+",
        flags=re.UNICODE,
    )
    return bool(emoji_pattern.search(text))


def find_html_files(workspace_path: Path) -> list:
    """Find HTML files ending with _1-50.html in workspace and sort by number"""
    import re

    if not workspace_path or not workspace_path.exists():
        return []
    pattern = re.compile(r".*_(\d{1,2})\.html$")
    html_files = []
    for f in workspace_path.rglob("*.html"):
        m = pattern.match(f.name)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 50:
                html_files.append(f)

    # Sort by number in filename (ascending)
    def extract_num(f):
        m = pattern.match(f.name)
        return int(m.group(1)) if m else float("inf")

    html_files.sort(key=extract_num)
    return html_files


def find_report_files(workspace_path: Path, report_format: str) -> list:
    """Find corresponding report files based on report format"""
    if not workspace_path or not workspace_path.exists():
        return []

    if report_format == "html":
        # Find html_report.html
        html_report = workspace_path / "html_report.html"
        if html_report.exists():
            return [html_report]
        return []
    elif report_format == "markdown":
        # Find markdown_report.md
        md_report = workspace_path / "markdown_report.md"
        if md_report.exists():
            return [md_report]
        return []
    return []


def get_latest_workspace() -> Path:
    """Get the latest workspace directory (absolute path)"""
    workspaces_dir = Path(os.getcwd()) / "workspaces"
    if not workspaces_dir.exists():
        return None

    workspace_dirs = sorted(
        workspaces_dir.glob("workspace_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if workspace_dirs:
        return workspace_dirs[0]
    return None


# Initialize session state
if "agent_running" not in st.session_state:
    st.session_state["agent_running"] = False
if "agent_process" not in st.session_state:
    st.session_state["agent_process"] = None
if "workspace_path" not in st.session_state:
    st.session_state["workspace_path"] = None
if "log_queue" not in st.session_state:
    st.session_state["log_queue"] = None
if "log_lines" not in st.session_state:
    st.session_state["log_lines"] = []
if "output_thread" not in st.session_state:
    st.session_state["output_thread"] = None
if "current_session_started" not in st.session_state:
    st.session_state["current_session_started"] = (
        False  # Mark if agent has been executed in current session
    )
if "emoji_filter_enabled" not in st.session_state:
    st.session_state["emoji_filter_enabled"] = True  # Default: enable emoji filtering
if "report_format" not in st.session_state:
    st.session_state["report_format"] = "html"  # Default: use HTML format

# Main interface
col1, col2 = st.columns([1, 2])

with col1:
    st.header("📝 Input Query")
    query = st.text_area(
        "Enter your query:",
        value="Please conduct an in-depth analysis of the success of *Black Myth: Wukong*, covering all aspects including development, release, and reviews, and create a presentation report.",
        height=150,
        disabled=st.session_state["agent_running"],
    )

    # Report format selection
    st.session_state["report_format"] = st.radio(
        "Select report format:",
        options=["html", "markdown"],
        format_func=lambda x: "Illustrated Report (.html)"
        if x == "html"
        else "Text Report (.md)",
        index=0 if st.session_state["report_format"] == "html" else 1,
        disabled=st.session_state["agent_running"],
    )

    if not st.session_state["agent_running"]:
        if st.button("🚀 Run Agent", type="primary"):
            if query.strip():
                # Mark that agent has started in current session
                st.session_state["current_session_started"] = True
                # Clear previous workspace path, let system find the latest one
                st.session_state["workspace_path"] = None
                st.session_state["agent_running"] = True
                st.session_state["log_lines"] = []
                st.session_state["log_queue"] = Queue()

                # Build command
                cmd = [
                    "uv",
                    "run",
                    "quick_start.py",
                    "--query",
                    query,
                    "--report_format",
                    st.session_state["report_format"],
                ]

                # Start process (non-blocking, no timeout)
                process = subprocess.Popen(
                    cmd,
                    cwd=os.getcwd(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Merge stderr to stdout
                    text=True,
                    bufsize=1,  # Line buffering
                    universal_newlines=True,
                )
                st.session_state["agent_process"] = process

                # Start output reading thread
                output_thread = threading.Thread(
                    target=read_output,
                    args=(process.stdout, st.session_state["log_queue"]),
                    daemon=True,
                )
                output_thread.start()
                st.session_state["output_thread"] = output_thread

                st.rerun()
            else:
                st.warning("⚠️ Please enter a query")
    else:
        if st.button("⏹️ Stop Agent", type="secondary"):
            if st.session_state["agent_process"]:
                st.session_state["agent_process"].terminate()
                st.session_state["agent_process"].wait(timeout=5)
                st.session_state["agent_process"] = None
            st.session_state["agent_running"] = False
            st.rerun()

    # Display execution status
    st.markdown("---")
    st.subheader("📊 Execution Status")

    if st.session_state["agent_running"]:
        st.markdown(
            '<p class="status-running">🔄 Agent is running...</p>',
            unsafe_allow_html=True,
        )

        # Check process status
        if st.session_state["agent_process"]:
            returncode = st.session_state["agent_process"].poll()
            if returncode is not None:
                # Process has finished
                st.session_state["agent_running"] = False
                if returncode == 0:
                    st.markdown(
                        '<p class="status-completed">✅ Agent completed successfully!</p>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<p class="status-error">❌ Agent execution failed!</p>',
                        unsafe_allow_html=True,
                    )
                st.session_state["agent_process"] = None
                # Don't rerun immediately, let user see final logs
    elif st.session_state["current_session_started"] and get_latest_workspace():
        st.markdown('<p class="status-completed">✅ Ready</p>', unsafe_allow_html=True)
    else:
        st.info("Waiting for execution...")

    # Update workspace path in real-time (only after agent has been executed in current session)
    if st.session_state["current_session_started"]:
        latest_workspace = get_latest_workspace()
        if latest_workspace:
            st.session_state["workspace_path"] = latest_workspace
            st.info(f"Workspace: {latest_workspace.name}")
        else:
            st.session_state["workspace_path"] = None

with col2:
    # Header and filter toggle in same row
    col_header, col_filter = st.columns([3, 1])
    with col_header:
        st.header("📋 Real-time Logs")
    with col_filter:
        st.session_state["emoji_filter_enabled"] = st.checkbox(
            "🔍 Key Info Only",
            value=st.session_state["emoji_filter_enabled"],
            help="When enabled, only shows log lines with emojis (key information)",
        )

    # Read new logs from queue
    if st.session_state["log_queue"]:
        try:
            while True:
                line = st.session_state["log_queue"].get_nowait()
                st.session_state["log_lines"].append(line + "\n")
                # Limit log lines to prevent memory overflow
                if len(st.session_state["log_lines"]) > 1000:
                    st.session_state["log_lines"] = st.session_state["log_lines"][
                        -1000:
                    ]
        except Empty:
            pass

    # Display logs - using fixed height container
    if st.session_state["log_lines"]:
        # Process logs based on filter settings
        if st.session_state["emoji_filter_enabled"]:
            # Only show lines with emojis
            filtered_lines = [
                line for line in st.session_state["log_lines"] if contains_emoji(line)
            ]
            log_text = "".join(filtered_lines)
            total_lines = len(st.session_state["log_lines"])
            filtered_count = len(filtered_lines)
        else:
            # Show all logs
            log_text = "".join(st.session_state["log_lines"])
            total_lines = len(st.session_state["log_lines"])
            filtered_count = total_lines

        # HTML escape to prevent injection
        log_text_escaped = html.escape(log_text)

        # Create fixed height scrolling container with auto-scroll script
        log_html = f"""
        <div id="log-container-{id(st.session_state["log_lines"])}" class="log-container">
            <pre style="margin:0; color:#333;">{log_text_escaped}</pre>
        </div>
        <script>
            // Auto scroll to bottom
            (function() {{
                var container = document.getElementById('log-container-{id(st.session_state["log_lines"])}');
                if (container) {{
                    container.scrollTop = container.scrollHeight;
                }}
            }})();
        </script>
        """
        st.markdown(log_html, unsafe_allow_html=True)

        # Status information
        if st.session_state["agent_running"]:
            if st.session_state["emoji_filter_enabled"]:
                st.caption(
                    "📊 Logs updating in real-time... | Showing: {}/{} lines (filtered)".format(
                        filtered_count, total_lines
                    )
                )
            else:
                st.caption(
                    "📊 Logs updating in real-time... | Total lines: {}".format(
                        total_lines
                    )
                )
        else:
            if st.session_state["emoji_filter_enabled"]:
                st.caption(
                    "✅ Execution completed | Showing: {}/{} lines (filtered)".format(
                        filtered_count, total_lines
                    )
                )
            else:
                st.caption(
                    "✅ Execution completed | Total lines: {}".format(total_lines)
                )
    else:
        # Empty state also shows fixed height container
        st.markdown(
            '<div class="log-container" style="display:flex; align-items:center; justify-content:center; color:#666;">'
            "<div>👈 Real-time logs will appear after running Agent</div>"
            "</div>",
            unsafe_allow_html=True,
        )

# Auto-refresh logic
if st.session_state["agent_running"]:
    time.sleep(1)  # Refresh every 1 second
    st.rerun()

# Report preview
st.markdown("---")
st.header("🎨 Report/Presentation Preview")

# Only show reports after agent has been executed in current session
if st.session_state["current_session_started"] and st.session_state["workspace_path"]:
    report_files = find_report_files(
        st.session_state["workspace_path"], st.session_state["report_format"]
    )

    if report_files:
        report_format_name = (
            "Illustrated Report (.html)"
            if st.session_state["report_format"] == "html"
            else "Text Report (.md)"
        )
        st.info(
            f"Found {len(report_files)} {report_format_name} file(s) | Workspace: {st.session_state['workspace_path'].name}"
        )

        # Iterate through all report files and render each
        for idx, report_file in enumerate(report_files, 1):
            try:
                with open(report_file, "r", encoding="utf-8") as f:
                    file_content = f.read()

                # Display file title
                st.markdown(f"### 📄 {idx}. {report_file.name}")

                # Render content based on format
                if st.session_state["report_format"] == "html":
                    # Render HTML using iframe
                    components.html(file_content, height=800, scrolling=True)

                    # Provide download button and source code view
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.download_button(
                            label=f"📥 Download {report_file.name}",
                            data=file_content,
                            file_name=report_file.name,
                            mime="text/html",
                            key=f"download_{idx}",
                        )

                    # Display HTML source code
                    with st.expander(f"View {report_file.name} source", expanded=False):
                        st.code(file_content, language="html")

                elif st.session_state["report_format"] == "markdown":
                    # Render Markdown content
                    st.markdown(file_content)

                    # Provide download button and source code view
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.download_button(
                            label=f"📥 Download {report_file.name}",
                            data=file_content,
                            file_name=report_file.name,
                            mime="text/markdown",
                            key=f"download_{idx}",
                        )

                    # Display Markdown source code
                    with st.expander(f"View {report_file.name} source", expanded=False):
                        st.code(file_content, language="markdown")

                # Separator (except for last file)
                if idx < len(report_files):
                    st.markdown("---")

            except Exception as e:
                st.error(f"Failed to load {report_file.name}: {str(e)}")
    else:
        if st.session_state["agent_running"]:
            file_type = (
                "HTML" if st.session_state["report_format"] == "html" else "Markdown"
            )
            st.info(f"⏳ Waiting for {file_type} file to be generated...")
        else:
            file_type = (
                "HTML" if st.session_state["report_format"] == "html" else "Markdown"
            )
            st.warning(f"⚠️ No {file_type} files found in workspace")
else:
    st.info("👈 Please run Agent first to generate report/presentation")

# Footer
st.markdown("---")
st.markdown(
    """
<div style='text-align: center; color: #666;'>
    <p>NexDR - Nex-AGI</p>
</div>
""",
    unsafe_allow_html=True,
)
