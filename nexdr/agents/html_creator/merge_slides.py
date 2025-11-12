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

"""
HTML Creator - Merge Slides Tool

This module implements the functionality to merge multiple HTML slides into a single
presentation with navigation support. It uses iframe with srcdoc to embed complete HTML content
while maintaining fullscreen display and proper formatting.
"""

import html
import logging
import re
from typing import List

logger = logging.getLogger(__name__)


def extract_background_color(html_content: str) -> str:
    """
    Extract background color from HTML content.

    Looks for background-color or background definitions in:
    1. html { background-color: ... } or html { background: ... }
    2. body { background-color: ... } or body { background: ... }

    Args:
        html_content: HTML content string to extract background color from

    Returns:
        str: Background color value (e.g., '#000000', 'rgb(0,0,0)'),
             defaults to '#1a1a1a' if not found
    """
    default_bg = "#1a1a1a"

    # Try to find background or background-color in html or body tag styles
    # Pattern 1: html { ... background-color: VALUE; ... } or html { ... background: VALUE; ... }
    html_bg_pattern = r"html\s*\{[^}]*background(?:-color)?:\s*([^;}\s]+)"
    # Pattern 2: body { ... background-color: VALUE; ... } or body { ... background: VALUE; ... }
    body_bg_pattern = r"body\s*\{[^}]*background(?:-color)?:\s*([^;}\s]+)"

    # First try to find from html tag
    match = re.search(html_bg_pattern, html_content, re.IGNORECASE | re.DOTALL)
    if match:
        color = match.group(1).strip()
        # Skip if it's a gradient or url (we only want solid colors)
        if not color.startswith(("linear-gradient", "radial-gradient", "url")):
            logger.info(f"Extracted background color from html tag: {color}")
            return color

    # Then try to find from body tag
    match = re.search(body_bg_pattern, html_content, re.IGNORECASE | re.DOTALL)
    if match:
        color = match.group(1).strip()
        # Skip if it's a gradient or url (we only want solid colors)
        if not color.startswith(("linear-gradient", "radial-gradient", "url")):
            logger.info(f"Extracted background color from body tag: {color}")
            return color

    logger.info(f"No background color found in HTML, using default: {default_bg}")
    return default_bg


def build_merged_presentation(
    slide_html_list: List[str], title: str = "Presentation"
) -> str:
    """
    Build a single-page HTML viewer that can paginate through slides using iframe srcdoc.

    Each slide's HTML is embedded as-is in an iframe, preserving all original styles,
    scripts, and content. The viewer provides navigation controls and keyboard shortcuts
    for easy browsing.

    Args:
        slide_html_list: List of HTML content strings (each should be a complete HTML document)
        title: Title for the merged presentation (default: "Presentation")

    Returns:
        str: Complete HTML string for the merged presentation viewer
    """
    if not slide_html_list:
        raise ValueError("slide_html_list cannot be empty")

    # Extract background color from the first slide
    first_slide_html = slide_html_list[0] if slide_html_list else ""
    background_color = extract_background_color(first_slide_html)

    # Create page containers with escaped HTML content
    pages_html = ""
    for idx, slide_html in enumerate(slide_html_list):
        if not slide_html:
            logger.warning(f"Slide {idx} is empty, using placeholder")
            slide_html = "<html><body><h1>Empty Slide</h1></body></html>"

        # Escape HTML content for srcdoc attribute
        escaped_content = html.escape(slide_html, quote=True)
        pages_html += f"""
    <div class="page" id="page-{idx}" data-page="{idx}">
        <iframe srcdoc="{escaped_content}" frameborder="0"></iframe>
    </div>
"""

    total_pages = len(slide_html_list)

    # Build complete HTML template
    merged_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} ({total_pages} slides)</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        html, body {{
            width: 100%;
            height: 100%;
            overflow: hidden;
            background: {background_color};
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: 'Noto Sans SC', sans-serif;
            outline: none;
            align-items: center;
            display: flex;
            justify-content: center;
        }}
        
        body:focus {{
            outline: none;
        }}
        
        /* Page container */
        #pages-container {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
        }}
        
        /* Transparent overlay to capture clicks and maintain focus */
        .page-overlay {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 1;
            pointer-events: none;
        }}
        
        .page {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s ease, visibility 0.3s ease;
            overflow: hidden;
            margin: 0;
            padding: 0;
        }}
        
        .page.active {{
            opacity: 1;
            visibility: visible;
            z-index: 1;
        }}
        
        .page iframe {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: none;
            margin: 0;
            padding: 0;
            display: block;
            overflow: auto;
        }}
        
        /* Navigation bar */
        #navigation {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(10px);
            padding: 12px;
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
            z-index: 10000;
            transition: opacity 0.3s ease;
        }}
        
        #navigation:hover {{
            opacity: 1;
        }}
        
        #navigation {{
            opacity: 0.6;
        }}
        
        #navigation button {{
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: white;
            padding: 8px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-size: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 40px;
            height: 40px;
        }}
        
        #navigation button:hover:not(:disabled) {{
            background: rgba(255, 255, 255, 0.25);
            transform: scale(1.05);
        }}
        
        #navigation button:disabled {{
            opacity: 0.3;
            cursor: not-allowed;
        }}
        
        #navigation button .material-icons {{
            font-size: 20px !important;
        }}
        
        #page-indicator {{
            color: white;
            font-size: 13px;
            font-weight: 500;
            text-align: center;
            padding: 4px 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            white-space: nowrap;
        }}
        
        .button-group {{
            display: flex;
            gap: 6px;
        }}
        
        /* Scrollbar styles */
        ::-webkit-scrollbar {{
            width: 8px;
        }}
        
        ::-webkit-scrollbar-track {{
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        }}
        
        ::-webkit-scrollbar-thumb {{
            background: rgba(255, 255, 255, 0.3);
            border-radius: 4px;
        }}
        
        ::-webkit-scrollbar-thumb:hover {{
            background: rgba(255, 255, 255, 0.5);
        }}
    </style>
</head>
<body>
    <!-- Page container -->
    <div id="pages-container">
{pages_html}
    </div>
    
    <!-- Navigation bar -->
    <div id="navigation">
        <div class="button-group">
            <button id="first-btn" title="First page (Home)">
                <span class="material-icons">first_page</span>
            </button>
            <button id="last-btn" title="Last page (End)">
                <span class="material-icons">last_page</span>
            </button>
        </div>
        <div class="button-group">
            <button id="prev-btn" title="Previous page (Page Up / ↑)">
                <span class="material-icons">chevron_left</span>
            </button>
            <button id="next-btn" title="Next page (Page Down / ↓)">
                <span class="material-icons">chevron_right</span>
            </button>
        </div>
        <div id="page-indicator">1 / {total_pages}</div>
    </div>
    
    <script>
        // Page state
        let currentPage = 0;
        const totalPages = {total_pages};
        
        // Initialize
        function init() {{
            // Make body focusable to capture keyboard events
            document.body.tabIndex = -1;
            document.body.focus();

            // Refocus on body when clicking anywhere on the page
            document.addEventListener('click', function(e) {{
                // Don't interfere with button clicks
                if (!e.target.closest('#navigation button')) {{
                    document.body.focus();
                }}
            }}, true);

            // Periodically check and restore focus if needed
            setInterval(function() {{
                if (document.activeElement && document.activeElement.tagName === 'IFRAME') {{
                    document.body.focus();
                }}
            }}, 1000);

            showPage(0);
            updateNavigation();
        }}
        
        // Show specified page
        function showPage(pageIndex) {{
            if (pageIndex < 0 || pageIndex >= totalPages) return;

            // Hide all pages
            document.querySelectorAll('.page').forEach(page => {{
                page.classList.remove('active');
            }});

            // Show current page
            const page = document.getElementById(`page-${{pageIndex}}`);
            if (page) {{
                page.classList.add('active');
                currentPage = pageIndex;
                updateNavigation();
            }}
        }}
        
        // Update navigation button states
        function updateNavigation() {{
            document.getElementById('page-indicator').textContent = `${{currentPage + 1}} / ${{totalPages}}`;
            document.getElementById('prev-btn').disabled = currentPage === 0;
            document.getElementById('first-btn').disabled = currentPage === 0;
            document.getElementById('next-btn').disabled = currentPage === totalPages - 1;
            document.getElementById('last-btn').disabled = currentPage === totalPages - 1;
        }}
        
        // Navigation functions
        function nextPage() {{
            if (currentPage < totalPages - 1) {{
                showPage(currentPage + 1);
            }}
        }}
        
        function prevPage() {{
            if (currentPage > 0) {{
                showPage(currentPage - 1);
            }}
        }}
        
        function firstPage() {{
            showPage(0);
        }}
        
        function lastPage() {{
            showPage(totalPages - 1);
        }}
        
        // Event listeners
        document.getElementById('next-btn').addEventListener('click', nextPage);
        document.getElementById('prev-btn').addEventListener('click', prevPage);
        document.getElementById('first-btn').addEventListener('click', firstPage);
        document.getElementById('last-btn').addEventListener('click', lastPage);
        
        // Keyboard events - use window to ensure we capture all keyboard events
        window.addEventListener('keydown', (e) => {{
            switch(e.key) {{
                case 'PageDown':
                case 'ArrowDown':
                case 'ArrowRight':
                    e.preventDefault();
                    nextPage();
                    break;
                case 'PageUp':
                case 'ArrowUp':
                case 'ArrowLeft':
                    e.preventDefault();
                    prevPage();
                    break;
                case 'Home':
                    e.preventDefault();
                    firstPage();
                    break;
                case 'End':
                    e.preventDefault();
                    lastPage();
                    break;
            }}
        }}, true);
        
        // Mouse wheel support
        let wheelTimeout;
        document.addEventListener('wheel', (e) => {{
            clearTimeout(wheelTimeout);
            wheelTimeout = setTimeout(() => {{
                if (e.deltaY > 0) {{
                    nextPage();
                }} else if (e.deltaY < 0) {{
                    prevPage();
                }}
            }}, 100);
        }}, {{ passive: true }});
        
        // Initialize page
        init();
    </script>
</body>
</html>
"""

    return merged_html
