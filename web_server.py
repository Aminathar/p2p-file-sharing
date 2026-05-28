import http.server
import socketserver
import os
import re
import threading
import socket
import logging
import datetime
import json
import random
import string
from PyQt6.QtCore import QThread, pyqtSignal
import urllib.parse
import shutil


def _parse_multipart_boundary(content_type):
    """Extract the boundary token from a multipart/form-data Content-Type."""
    m = re.search(r'boundary=([^;]+)', content_type or '')
    if not m:
        return None
    return m.group(1).strip().strip('"')


class _BoundedReader:
    """Wrap a raw socket-like rfile so that read(N) never blocks past Content-Length.

    `http.server`'s `self.rfile` is a raw `BufferedReader` over the socket — calling
    `read(N)` on it will block until N bytes arrive, but the client only sends
    `Content-Length` bytes and then waits for a response. This wrapper bounds every
    read by the number of bytes left in the request body.
    """
    def __init__(self, rfile, length):
        self._rfile = rfile
        self._remaining = max(0, int(length))

    def read(self, n=-1):
        if self._remaining <= 0:
            return b''
        want = self._remaining if n < 0 else min(n, self._remaining)
        data = self._rfile.read(want)
        self._remaining -= len(data)
        return data

    def readline(self, limit=-1):
        if self._remaining <= 0:
            return b''
        want = self._remaining if limit < 0 else min(limit, self._remaining)
        line = self._rfile.readline(want)
        self._remaining -= len(line)
        return line


def stream_multipart_file(rfile, content_type, save_path, content_length=None):
    """Stream the first uploaded file part from a multipart/form-data body to disk.

    `rfile` is the socket file from `http.server`; it is NOT length-limited, so
    callers must pass the request's `Content-Length` to bound reading. Returns
    the original client-side filename, or None if no file part was found.

    Single-pass parser with one shared read buffer — any bytes already pulled
    from the socket past a part boundary stay in the buffer for the next part.
    """
    boundary_token = _parse_multipart_boundary(content_type)
    if not boundary_token or content_length is None:
        return None

    bounded = _BoundedReader(rfile, content_length)
    boundary = b'--' + boundary_token.encode()
    end_boundary = b'\r\n' + boundary
    keep = len(end_boundary)
    chunk_sz = 64 * 1024

    buf = b''

    def refill():
        nonlocal buf
        more = bounded.read(chunk_sz)
        if not more:
            return False
        buf += more
        return True

    def read_line_from_buf():
        """Pop one CRLF-terminated line from buf, refilling as needed. Returns None on EOF."""
        nonlocal buf
        while True:
            i = buf.find(b'\r\n')
            if i >= 0:
                line = buf[:i + 2]
                buf = buf[i + 2:]
                return line
            if not refill():
                if buf:
                    line, buf = buf, b''
                    return line
                return None

    # 1) Advance past the opening boundary line.
    while True:
        line = read_line_from_buf()
        if line is None:
            return None
        if line.startswith(boundary):
            break

    # 2) Walk parts.
    while True:
        # Read part headers (until blank line).
        headers = {}
        while True:
            hline = read_line_from_buf()
            if hline is None:
                return None
            stripped = hline.rstrip(b'\r\n')
            if not stripped:
                break
            if b':' in stripped:
                k, v = stripped.split(b':', 1)
                headers[k.strip().lower()] = v.strip()

        disposition = headers.get(b'content-disposition', b'').decode('utf-8', errors='replace')
        fname_match = re.search(r'filename\*?="?([^";]+)"?', disposition)
        client_filename = fname_match.group(1) if fname_match else None

        if client_filename:
            # Stream this part's body to disk, stopping at end_boundary.
            with open(save_path, 'wb') as out:
                while True:
                    idx = buf.find(end_boundary)
                    if idx >= 0:
                        out.write(buf[:idx])
                        buf = buf[idx + len(end_boundary):]
                        break
                    if len(buf) > keep:
                        out.write(buf[:-keep])
                        buf = buf[-keep:]
                    if not refill():
                        if buf:
                            out.write(buf)
                            buf = b''
                        return client_filename
            return client_filename

        # Non-file part — drop bytes until end_boundary, keep what's after.
        while True:
            idx = buf.find(end_boundary)
            if idx >= 0:
                buf = buf[idx + len(end_boundary):]
                break
            if len(buf) > keep:
                buf = buf[-keep:]
            if not refill():
                return None

        # Determine if this was the terminal boundary (`--{boundary}--`).
        while len(buf) < 2:
            if not refill():
                return None
        if buf.startswith(b'--'):
            return None
        # Consume the trailing CRLF on the boundary line and loop to next part.
        if buf.startswith(b'\r\n'):
            buf = buf[2:]
        # Continue to read headers of next part.

# Improved HTML Template with History
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>P2P Mobile Share</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta charset="utf-8">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; background: #eef2f5; color: #333; margin: 0; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }
        
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }
        h2 { margin: 0; color: #2c3e50; font-size: 1.5em; }
        select#lang-select { padding: 5px; border-radius: 4px; border: 1px solid #ccc; background: white; }

        .upload-section { border: 2px dashed #0078d7; background: #f8fbff; padding: 25px; text-align: center; margin-bottom: 30px; border-radius: 8px; transition: background 0.3s; }
        .upload-section:active { background: #eef6ff; }
        
        .file-list { list-style: none; padding: 0; margin-top: 10px; }
        .file-list li { padding: 15px 0; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between; align-items: center; }
        .file-list li:last-child { border-bottom: none; }
        
        .file-info { display: flex; flex-direction: column; overflow: hidden; margin-right: 15px; }
        .file-name { font-weight: 500; font-size: 1em; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .file-size { font-size: 0.8em; color: #888; margin-top: 4px; }
        
        .btn { background: #0078d7; color: white; padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-size: 1em; width: 100%; box-sizing: border-box; }
        .btn:active { background: #0063b1; transform: translateY(1px); }
        
        .btn-download { background: #28a745; font-size: 0.85em; padding: 8px 12px; width: auto; text-decoration: none; display: inline-block; white-space: nowrap; }
        .btn-download:active { background: #218838; }

        input[type="file"] { margin-bottom: 15px; width: 100%; }
        
        h3 { color: #555; font-size: 1.1em; border-bottom: 2px solid #0078d7; padding-bottom: 5px; display: inline-block; margin-top: 10px; }
        
        /* Tabs */
        .tab-bar { display: flex; margin-bottom: 20px; border-bottom: 1px solid #ddd; }
        .tab { padding: 10px 20px; cursor: pointer; border-bottom: 3px solid transparent; color: #888; font-weight: 500; }
        .tab.active { border-bottom-color: #0078d7; color: #0078d7; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .history-list { font-size: 0.9em; }
        .history-item { background: #f9f9f9; padding: 10px; margin-bottom: 8px; border-radius: 4px; border: 1px solid #eee; display: flex; justify-content: space-between; align-items: center;}
        .history-info { display: flex; flex-direction: column; }
        .history-type { font-weight: bold; margin-right: 5px; }
        .history-path { font-family: monospace; color: #666; font-size: 0.85em; margin-top: 4px; word-break: break-all; }
        .history-time { font-size: 0.8em; color: #999; text-align: right; min-width: 60px; }

        /* Modal */
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); align-items: center; justify-content: center; }
        .modal-content { background-color: white; padding: 25px; border-radius: 12px; width: 90%; max-width: 400px; text-align: center; box-shadow: 0 5px 20px rgba(0,0,0,0.2); animation: popin 0.3s ease; }
        .modal h3 { color: #d9534f; border-bottom: none; margin-top: 0; }
        .modal p { color: #555; margin-bottom: 20px; }
        .close-btn { background: #aaa; color: white; padding: 8px 20px; border-radius: 6px; border: none; font-size: 1em; cursor: pointer; }
        .close-btn:active { background: #888; }
        @keyframes popin { from {transform: scale(0.8); opacity: 0;} to {transform: scale(1); opacity: 1;} }

        /* Search & Filter */
        .search-box { margin-bottom: 15px; position: relative; }
        .search-box input { width: 100%; padding: 12px 15px; border: 1px solid #ddd; border-radius: 8px; font-size: 1em; box-sizing: border-box; outline: none; transition: border-color 0.3s; }
        .search-box input:focus { border-color: #0078d7; }
        
        .filter-tags { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 5px; margin-bottom: 15px; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
        .filter-tags::-webkit-scrollbar { display: none; }
        .filter-tag { padding: 6px 14px; background: #eee; border-radius: 20px; font-size: 0.9em; color: #555; white-space: nowrap; cursor: pointer; user-select: none; transition: all 0.2s; border: 1px solid transparent; }
        .filter-tag.active { background: #0078d7; color: white; }
    </style>
    <script>
        const translations = {
            'en': {
                'title': 'P2P Mobile Share', 'upload_header': '📤 Upload File', 'upload_btn': 'Upload File',
                'files_header': '📥 Available Files', 'download': 'Download', 
                'tab_files': 'Files', 'tab_history': 'History', 'history_header': '📜 Transfer History',
                'msg_duplicate_title': 'File Already Exists', 'msg_duplicate_body': 'A file with this name already exists in the shared folder.', 'btn_ok': 'OK',
                'filter_all': 'All', 'filter_img': 'Images', 'filter_audio': 'Audio', 'filter_video': 'Video', 'filter_doc': 'Docs', 'search_placeholder': 'Search files...'
            },
            'ru': {
                'title': 'P2P Мобильный Обмен', 'upload_header': '📤 Загрузить файл', 'upload_btn': 'Загрузить',
                'files_header': '📥 Доступные файлы', 'download': 'Скачать',
                'tab_files': 'Файлы', 'tab_history': 'История', 'history_header': '📜 История передачи',
                'msg_duplicate_title': 'Файл уже существует', 'msg_duplicate_body': 'Файл с таким именем уже есть в общей папке.', 'btn_ok': 'ОК',
                'filter_all': 'Все', 'filter_img': 'Изображения', 'filter_audio': 'Аудио', 'filter_video': 'Видео', 'filter_doc': 'Документы', 'search_placeholder': 'Поиск файлов...'
            },
            'kk': {
                'title': 'P2P Мобильді Алмасу', 'upload_header': '📤 Файлды жүктеу', 'upload_btn': 'Жүктеу',
                'files_header': '📥 Қолжетімді файлдар', 'download': 'Жүктеу',
                'tab_files': 'Файлдар', 'tab_history': 'Тарих', 'history_header': '📜 Тасымалдау тарихы',
                'msg_duplicate_title': 'Файл бар', 'msg_duplicate_body': 'Бұл атпен файл бөлісу қалтасында бар.', 'btn_ok': 'Жарайды',
                'filter_all': 'Барлығы', 'filter_img': 'Суреттер', 'filter_audio': 'Аудио', 'filter_video': 'Видео', 'filter_doc': 'Құжаттар', 'search_placeholder': 'Файлдарды іздеу...'
            }
        };

        const serverMessage = "{server_message}";
        let currentFilter = 'all';

        function setLanguage(lang) {
            if (!translations[lang]) lang = 'en';
            const t = translations[lang];
            document.querySelectorAll('[data-trn]').forEach(el => {
                const key = el.getAttribute('data-trn');
                if (t[key]) el.innerText = t[key];
            });
            document.getElementById('search-input').placeholder = t['search_placeholder'];
            localStorage.setItem('p2p_lang', lang);
        }

        function switchTab(tabId) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            document.querySelector(`.tab[data-target="${tabId}"]`).classList.add('active');
            document.getElementById(tabId).classList.add('active');
            localStorage.setItem('p2p_tab', tabId);
        }

        function filterFiles() {
            const query = document.getElementById('search-input').value.toLowerCase();
            const listItems = document.querySelectorAll('.file-list li');
            let hasVisible = false;

            listItems.forEach(li => {
                const name = li.querySelector('.file-name').innerText.toLowerCase();
                const ext = name.split('.').pop();
                
                // Determine type
                let type = 'other';
                if (['jpg','jpeg','png','gif','bmp','webp'].includes(ext)) type = 'img';
                else if (['mp3','wav','ogg','m4a','flac'].includes(ext)) type = 'audio';
                else if (['mp4','mkv','avi','mov','webm'].includes(ext)) type = 'video';
                else if (['pdf','doc','docx','txt','xls','xlsx','ppt','pptx'].includes(ext)) type = 'doc';

                // Filter logic
                const matchesSearch = name.includes(query);
                const matchesType = currentFilter === 'all' || currentFilter === type;

                if (matchesSearch && matchesType) {
                    li.style.display = 'flex';
                    hasVisible = true;
                } else {
                    li.style.display = 'none';
                }
            });
            
            // Show/Hide 'No files' message if needed (could separate element for this)
        }

        function setFilter(filterType) {
            currentFilter = filterType;
            document.querySelectorAll('.filter-tag').forEach(tag => {
                if (tag.getAttribute('data-filter') === filterType) tag.classList.add('active');
                else tag.classList.remove('active');
            });
            filterFiles();
        }

        document.addEventListener('DOMContentLoaded', () => {
            const savedLang = localStorage.getItem('p2p_lang') || '{current_lang}';
            const langSelect = document.getElementById('lang-select');
            langSelect.value = savedLang;
            setLanguage(savedLang);

            langSelect.addEventListener('change', (e) => setLanguage(e.target.value));

            const savedTab = localStorage.getItem('p2p_tab') || 'files';
            switchTab(savedTab);
            document.querySelectorAll('.tab').forEach(t => {
                t.addEventListener('click', () => switchTab(t.getAttribute('data-target')));
            });

            // Search & Filter Listeners
            document.getElementById('search-input').addEventListener('input', filterFiles);
            document.querySelectorAll('.filter-tag').forEach(tag => {
                tag.addEventListener('click', () => setFilter(tag.getAttribute('data-filter')));
            });

            if (serverMessage === 'error_duplicate') {
                showModal('msg_duplicate_title', 'msg_duplicate_body');
            }
        });

        function showModal(titleKey, bodyKey) {
            const modal = document.getElementById('modal');
            const t = translations[localStorage.getItem('p2p_lang') || 'en'] || translations['en'];
            
            document.getElementById('modal-title').innerText = t[titleKey];
            document.getElementById('modal-body').innerText = t[bodyKey];
            document.getElementById('modal-btn').innerText = t['btn_ok'];
            
            modal.style.display = 'flex';
        }

        function closeModal() {
            document.getElementById('modal').style.display = 'none';
        }
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 data-trn="title">P2P Mobile Share</h2>
            <select id="lang-select">
                <option value="en">English</option>
                <option value="ru">Русский</option>
                <option value="kk">Қазақша</option>
            </select>
        </div>

        <div class="tab-bar">
            <div class="tab active" data-target="files" data-trn="tab_files">Files</div>
            <div class="tab" data-target="history" data-trn="tab_history">History</div>
        </div>
        
        <div id="files" class="tab-content active">
            <div class="upload-section">
                <h3 id="upload-header" data-trn="upload_header">📤 Upload File</h3>
                <form method="POST" enctype="multipart/form-data">
                    <input type="file" name="file" required>
                    <button type="submit" id="upload-btn" class="btn" data-trn="upload_btn">Upload File</button>
                </form>
            </div>

            <h3 data-trn="files_header">📥 Available Files</h3>
            
            <!-- Search & Filter Controls -->
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Search files...">
            </div>
            <div class="filter-tags">
                <div class="filter-tag active" data-filter="all" data-trn="filter_all">All</div>
                <div class="filter-tag" data-filter="img" data-trn="filter_img">Images</div>
                <div class="filter-tag" data-filter="audio" data-trn="filter_audio">Audio</div>
                <div class="filter-tag" data-filter="video" data-trn="filter_video">Video</div>
                <div class="filter-tag" data-filter="doc" data-trn="filter_doc">Docs</div>
            </div>

            <ul class="file-list">
                {file_list}
            </ul>
        </div>

        <div id="history" class="tab-content">
            <h3 data-trn="history_header">📜 Transfer History</h3>
            <div class="history-list">
                {history_list}
            </div>
        </div>
    </div>

    <!-- Modal -->
    <div id="modal" class="modal">
        <div class="modal-content">
            <h3 id="modal-title">Error</h3>
            <p id="modal-body">Something went wrong.</p>
            <button id="modal-btn" class="close-btn" onclick="closeModal()">OK</button>
        </div>
    </div>
</body>
</html>
"""

# Authorization HTML Template
AUTH_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>P2P Mobile Share - Authorization</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta charset="utf-8">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .auth-container { max-width: 400px; width: 100%; background: white; padding: 40px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.3); }
        h2 { margin: 0 0 10px 0; color: #333; font-size: 1.8em; text-align: center; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; font-size: 0.9em; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #555; font-weight: 500; font-size: 0.9em; }
        input[type="text"] { width: 100%; padding: 12px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 1em; box-sizing: border-box; transition: border-color 0.3s; }
        input[type="text"]:focus { outline: none; border-color: #667eea; }
        .btn-submit { width: 100%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px; border: none; border-radius: 8px; font-size: 1.1em; font-weight: 600; cursor: pointer; transition: transform 0.2s; }
        .btn-submit:active { transform: scale(0.98); }
        .error { background: #fee; border: 1px solid #fcc; color: #c33; padding: 12px; border-radius: 8px; margin-bottom: 20px; text-align: center; display: none; }
        .error.show { display: block; }
        .code-input { text-align: center; font-size: 1.5em; letter-spacing: 0.3em; font-weight: bold; }
        .icon { text-align: center; font-size: 3em; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="auth-container">
        <div class="icon">🔐</div>
        <h2>Authorization Required</h2>
        <p class="subtitle">Enter the code displayed on your PC</p>
        
        <div id="error-msg" class="error">{error_message}</div>
        
        <form method="POST" action="/auth">
            <div class="form-group">
                <label for="otp">Connection Code</label>
                <input type="text" id="otp" name="otp" class="code-input" maxlength="6" pattern="[0-9]{6}" required autofocus placeholder="000000">
            </div>
            
            <div class="form-group">
                <label for="device_name">Device Name</label>
                <input type="text" id="device_name" name="device_name" placeholder="My Phone" required>
            </div>
            
            <button type="submit" class="btn-submit">Connect</button>
        </form>
    </div>
    
    <script>
        const errorMsg = "{error_message}";
        if (errorMsg) {
            document.getElementById('error-msg').classList.add('show');
        }
        
        // Auto-focus and format OTP input
        const otpInput = document.getElementById('otp');
        otpInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/[^0-9]/g, '');
        });
    </script>
</body>
</html>
"""


SHARED_DIR = "" 
DEFAULT_LANG = "en"
WEB_HISTORY = [] # List of dicts: {type, filename, time, path, size}
WEB_HISTORY_FILE = "web_history.json"

# Authorization
CURRENT_OTP = ""
AUTHORIZED_DEVICES = {}  # {ip: {'name': str, 'connected_at': str}}
SHARED_FILES = {}  # {filename: {'recipients': [ips or '*'], 'shared_at': str}}
MAX_CONNECTIONS = 20

def generate_otp():
    """Generate a random 6-digit OTP."""
    return ''.join(random.choices(string.digits, k=6))

def load_web_history():
    """Load web history from JSON file."""
    global WEB_HISTORY
    try:
        if os.path.exists(WEB_HISTORY_FILE):
            with open(WEB_HISTORY_FILE, 'r', encoding='utf-8') as f:
                WEB_HISTORY = json.load(f)
    except Exception as e:
        print(f"Failed to load web history: {e}")
        WEB_HISTORY = []

def save_web_history():
    """Save web history to JSON file."""
    try:
        with open(WEB_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(WEB_HISTORY, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Failed to save web history: {e}")

class MobileRequestHandler(http.server.SimpleHTTPRequestHandler):
    def get_client_ip(self):
        """Get the client's IP address."""
        return self.client_address[0]
    
    def is_authorized(self):
        """Check if the client is authorized."""
        client_ip = self.get_client_ip()
        return client_ip in AUTHORIZED_DEVICES
    
    def check_file_access(self, filename):
        """Check if client has access to the file."""
        client_ip = self.get_client_ip()
        
        # Case-insensitive lookup
        # Iterate to find match because we might have multiple casing (though unlikely)
        # Better: just check lower() if we normalize keys, but let's just loop for safety and debug
        
        # Debug Log
        # print(f"🔍 Access Check: File='{filename}' IP='{client_ip}' Shared_Keys={list(SHARED_FILES.keys())}")
        
        # Exact match
        if filename in SHARED_FILES:
            file_data = SHARED_FILES[filename]
        else:
            # Case-insensitive match attempt
            found_key = next((k for k in SHARED_FILES if k.lower() == filename.lower()), None)
            if found_key:
                file_data = SHARED_FILES[found_key]
            else:
                # File not explicitly shared via app logic -> Default Public (Files dropped in folder)
                # This explains why "Default Public" is risky if keys don't match.
                return True

        recipients = file_data.get('recipients', ['*'])
        
        # '*' means all devices
        if '*' in recipients:
             return True
        
        # Check if client IP is in recipients list
        access_granted = client_ip in recipients
        if not access_granted:
             print(f"⛔ Access Denied: {client_ip} tried to access '{filename}' (Allowed: {recipients})")
        return access_granted
    
    def get_page_content(self, server_msg=""):
        # 1. Build File List (filtered by access)
        file_items = ""
        client_ip = self.get_client_ip()
        try:
            if os.path.exists(SHARED_DIR):
                files = sorted(os.listdir(SHARED_DIR))
                for f in files:
                    fp = os.path.join(SHARED_DIR, f)
                    if os.path.isfile(fp) and self.check_file_access(f):
                        size_mb = os.path.getsize(fp) / (1024 * 1024)
                        file_items += f'''
                        <li>
                            <div class="file-info"><span class="file-name">{f}</span><span class="file-size">{size_mb:.2f} MB</span></div>
                            <a href="/{f}" class="btn btn-download" data-trn="download" download>Download</a>
                        </li>'''
                if not file_items:
                    file_items = "<li style='text-align:center; color:#888; padding:20px;'>No files in shared folder.</li>"
            else:
                file_items = f"<li>Shared directory not found: {SHARED_DIR}</li>"
        except Exception as e:
            file_items = f"<li>Error listing files: {e}</li>"

        # 2. Build History List
        history_items = ""
        if WEB_HISTORY:
            for entry in reversed(WEB_HISTORY):
                # Check visibility for Shared files
                if entry.get('type') == 'Shared':
                    recipients = entry.get('recipients', ['*'])
                    if '*' not in recipients and client_ip not in recipients:
                        continue

                icon = "📤" if entry['type'] == "Upload" else ("💻" if entry['type'] == 'Shared' else "📥")
                color = "#0078d7" if entry['type'] == "Upload" else ("#666666" if entry['type'] == 'Shared' else "#28a745")
                if entry['type'] == 'Upload':
                    path_display = f"Saved to: {entry['path']}"
                elif entry['type'] == 'Shared':
                    path_display = "Shared from PC"
                else:
                    path_display = "Downloaded to Mobile"
                
                history_items += f'''
                <div class="history-item">
                    <div class="history-info">
                        <div style="font-weight:500;"><span style="color:{color}; margin-right:5px;">{icon}</span>{entry['filename']}</div>
                        <div class="history-path">{path_display}</div>
                    </div>
                    <div class="history-time">{entry['time']}</div>
                </div>'''
        else:
                history_items = "<div style='text-align:center; color:#888; padding:20px;'>No history yet.</div>"

        # 3. Render Template
        return HTML_TEMPLATE.replace("{file_list}", file_items) \
                            .replace("{history_list}", history_items) \
                            .replace("{server_message}", server_msg) \
                            .replace("{current_lang}", DEFAULT_LANG)

    def do_GET(self):
        # Check authorization for main page and downloads
        if self.path == '/' or self.path.startswith('/download'):
            if not self.is_authorized():
                # Show authorization page
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(AUTH_TEMPLATE.replace("{error_message}", "").encode('utf-8'))
                return
        
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self.get_page_content().encode('utf-8'))
        else:
            # Serve file - check authorization and file access
            if not self.is_authorized():
                self.send_error(403, "Unauthorized")
                return
            
            requested_path = urllib.parse.unquote(self.path).lstrip('/')
            
            # Check file access permission
            if not self.check_file_access(requested_path):
                self.send_error(403, "Access denied to this file")
                return
            full_path = os.path.join(SHARED_DIR, requested_path)
            
            if not os.path.abspath(full_path).startswith(os.path.abspath(SHARED_DIR)):
                self.send_error(403, "Access denied")
                return

            if os.path.exists(full_path) and os.path.isfile(full_path):
                 try:
                     size_mb = os.path.getsize(full_path) / (1024 * 1024)
                     if hasattr(self.server, 'log_transfer'):
                         self.server.log_transfer("Mobile Download", requested_path, size_mb, "Mobile")
                     
                     # Log Download to Web History
                     WEB_HISTORY.append({
                        'type': 'Download',
                        'filename': requested_path,
                        'path': '-',
                        'time': datetime.datetime.now().strftime("%H:%M:%S"),
                        'size': size_mb
                     })
                     save_web_history()
                 except Exception as e:
                     logging.warning(f"Failed to log download: {e}")
                 super().do_GET()
            else:
                 self.send_error(404, "File not found")

    def translate_path(self, path):
        path = urllib.parse.unquote(path)
        path = path.lstrip('/')
        return os.path.join(SHARED_DIR, path)

    def do_POST(self):
        # Handle authorization
        if self.path == '/auth':
            try:
                content_type = self.headers.get('Content-Type')
                if not content_type or 'application/x-www-form-urlencoded' not in content_type:
                    self.send_error(400, "Bad Request")
                    return
                
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                
                # Parse form data
                params = {}
                for param in post_data.split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        params[urllib.parse.unquote_plus(key)] = urllib.parse.unquote_plus(value)
                
                otp = params.get('otp', '').strip()
                device_name = params.get('device_name', 'Unknown Device').strip()
                client_ip = self.get_client_ip()
                
                # Validate OTP
                if otp == CURRENT_OTP and len(AUTHORIZED_DEVICES) < MAX_CONNECTIONS:
                    # Authorize device
                    AUTHORIZED_DEVICES[client_ip] = {
                        'name': device_name,
                        'connected_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    print(f"✅ Authorized device: {device_name} ({client_ip})")
                    
                    # Notify server thread about new device
                    if hasattr(self.server, 'on_device_connected'):
                        self.server.on_device_connected(client_ip, device_name)
                    
                    # Redirect to main page
                    self.send_response(303)
                    self.send_header('Location', '/')
                    self.end_headers()
                    return
                else:
                    # Invalid OTP or max connections reached
                    error_msg = "Invalid code" if otp != CURRENT_OTP else "Maximum connections reached"
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(AUTH_TEMPLATE.replace("{error_message}", error_msg).encode('utf-8'))
                    return
                    
            except Exception as e:
                logging.error(f"Auth error: {e}")
                self.send_error(500, "Server error")
                return
        
        # Handle file upload - check authorization
        if not self.is_authorized():
            self.send_error(403, "Unauthorized")
            return
        
        try:
            content_type = self.headers.get('Content-Type')
            if not content_type or 'multipart/form-data' not in content_type:
                self.send_error(400, "Bad Request")
                return

            try:
                content_length = int(self.headers.get('Content-Length', 0))
            except (TypeError, ValueError):
                content_length = 0
            if content_length <= 0:
                self.send_error(411, "Length Required")
                return

            # Stream upload to a temporary path first, so we can reject duplicates
            # without ever creating the real file.
            tmp_path = os.path.join(SHARED_DIR, f".upload_{random.randint(100000, 999999)}.part")
            try:
                client_filename = stream_multipart_file(
                    self.rfile, content_type, tmp_path, content_length=content_length
                )
            except Exception:
                if os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except OSError: pass
                raise

            if not client_filename:
                if os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except OSError: pass
                self.send_error(400, "No file found")
                return

            filename = os.path.basename(client_filename)
            save_path = os.path.join(SHARED_DIR, filename)

            # Exact Duplicate Check
            if os.path.exists(save_path):
                try: os.remove(tmp_path)
                except OSError: pass
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(self.get_page_content("error_duplicate").encode('utf-8'))
                return

            os.replace(tmp_path, save_path)

            # Log to PC App
            size_mb = 0
            try:
                size_mb = os.path.getsize(save_path) / (1024 * 1024)
                if hasattr(self.server, 'log_transfer'):
                    self.server.log_transfer("Mobile Upload", filename, size_mb, "Mobile")
            except OSError:
                pass

            # Add to Web History
            WEB_HISTORY.append({
                'type': 'Upload',
                'filename': filename,
                'path': save_path,
                'time': datetime.datetime.now().strftime("%H:%M:%S"),
                'size': size_mb
            })
            save_web_history()

            # Redirect (Auto-refresh)
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
            return
        except Exception as e:
            self.send_error(500, f"Upload failed: {e}")

class WebServerThread(QThread):
    status_msg = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    transfer_log = pyqtSignal(str, str, float, str)
    otp_generated = pyqtSignal(str)  # Emits the OTP code
    device_connected = pyqtSignal(str, str)  # Emits (ip, device_name)

    def __init__(self, directory, port=8000, lang_code="en"):
        super().__init__()
        self.directory = directory
        self.port = port
        self.lang_code = lang_code
        self.httpd = None
        self._is_running = False

    def run(self):
        global SHARED_DIR, DEFAULT_LANG, CURRENT_OTP, AUTHORIZED_DEVICES, SHARED_FILES
        SHARED_DIR = self.directory
        DEFAULT_LANG = self.lang_code
        load_web_history()  # Load history when server starts
        
        # Generate OTP
        CURRENT_OTP = generate_otp()
        AUTHORIZED_DEVICES.clear()  # Clear previous authorizations
        SHARED_FILES.clear()       # Clear previous file permissions
        self.otp_generated.emit(CURRENT_OTP)
        print(f"🔑 Generated OTP: {CURRENT_OTP}")
        
        try:
            print("📡 Starting web server...")
            print(f"📁 Shared directory: {self.directory}")
            print(f"🔌 Port: {self.port}")
            
            socketserver.TCPServer.allow_reuse_address = True
            self.httpd = socketserver.TCPServer(("", self.port), MobileRequestHandler)
            self.httpd.log_transfer = self.emit_transfer_log
            self.httpd.on_device_connected = self.on_device_connected_callback
            
            self._is_running = True
            local_ip = self.get_local_ip()
            url = f"http://{local_ip}:{self.port}"
            self.status_msg.emit(f"Server Running: {url}")
            print(f"✅ Web Server running at: {url}")
            print(f"📂 Serving directory: {self.directory}")
            
            self.httpd.serve_forever()
        except OSError as e:
            print(f"❌ OSError: {e}")
            if e.errno == 98 or e.errno == 10048:
                 self.error_occurred.emit(f"Port {self.port} is busy.")
                 print(f"⚠️ Port {self.port} is already in use")
            else:
                 self.error_occurred.emit(str(e))
                 print(f"⚠️ OS Error: {e}")
        except Exception as e:
            print(f"❌ Unexpected error starting web server: {e}")
            print(f"❌ Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))
        finally:
            self._is_running = False
            print("🛑 Web server stopped")

    def update_directory(self, new_dir):
        """Update the shared directory dynamically."""
        global SHARED_DIR
        SHARED_DIR = new_dir
        self.directory = new_dir
        print(f"Web Server: Directory updated to {new_dir}")

    def emit_transfer_log(self, direction, filename, size_mb, peer):
        self.transfer_log.emit(direction, filename, size_mb, peer)
    
    def on_device_connected_callback(self, ip, device_name):
        """Called when a new device is authorized."""
        self.device_connected.emit(ip, device_name)
    
    def get_authorized_devices(self):
        """Get list of authorized devices."""
        return dict(AUTHORIZED_DEVICES)
    
    def reset_otp(self):
        """Generate new OTP and clear all authorizations."""
        global CURRENT_OTP, AUTHORIZED_DEVICES
        CURRENT_OTP = generate_otp()
        AUTHORIZED_DEVICES.clear()
        self.otp_generated.emit(CURRENT_OTP)
        print(f"🔄 Reset OTP: {CURRENT_OTP}")
        return CURRENT_OTP
    
    def set_file_recipients(self, filename, recipients):
        """Set which devices can access a file.
        
        Args:
            filename: Name of the file
            recipients: List of IP addresses, or ['*'] for all devices
        """
        global SHARED_FILES
        SHARED_FILES[filename] = {
            'recipients': recipients,
            'shared_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        print(f"📁 File '{filename}' shared with: {recipients}")

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        self.status_msg.emit("Server Stopped")

    def get_local_ip(self):
        print("🔍 Detecting local IP address...")
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            print(f"✅ Detected IP: {ip}")
            return ip
        except Exception as e:
            print(f"⚠️ IP detection failed: {e}")
            print("⚠️ Falling back to 127.0.0.1 (localhost only)")
            return "127.0.0.1"

    def add_share_history(self, filename, size_mb, recipients=None):
        """Add a 'Shared from PC' entry to the web history."""
        global WEB_HISTORY
        WEB_HISTORY.append({
            'type': 'Shared',
            'filename': filename,
            'path': '-',
            'time': datetime.datetime.now().strftime("%H:%M:%S"),
            'size': size_mb,
            'recipients': recipients or ['*']
        })
        save_web_history()
