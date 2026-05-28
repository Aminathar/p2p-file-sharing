import os
import threading
import tempfile
import platform
import logging
import time
import shutil
import json
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QFileDialog, QProgressBar, QMessageBox,
    QCheckBox, QInputDialog, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QListWidget, QListWidgetItem, QMenu, QComboBox, QTextEdit, QSystemTrayIcon,
    QStyle, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon, QAction, QActionGroup
from core import P2PApp, compute_md5, sanitize_filename, get_local_ip
from web_server import WebServerThread, MAX_CONNECTIONS
from localization import LanguageManager
from settings_manager import SettingsManager
from history_manager import HistoryManager
from recipient_dialog import RecipientSelectionDialog
import sys
import ctypes
from ctypes import windll, byref, c_int, c_bool

# Theme Definitions
DARK_THEME = """
    QMainWindow, QWidget { background-color: #1e1e1e; color: #f0f0f0; }
    QLabel, QLineEdit, QCheckBox, QPushButton, QTableWidget, QListWidget, QTextEdit {
        color: #f0f0f0; font-size: 13px;
    }
    QLineEdit, QTableWidget, QListWidget, QTextEdit {
        background-color: #2b2b2b; border: 1px solid #444; padding: 4px;
    }
    QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #888; background-color: #333; }
    QCheckBox::indicator:checked { background-color: #0078d7; border: 1px solid #0078d7; }
    QPushButton { background-color: #2d2d30; border: 1px solid #555; border-radius: 4px; padding: 6px 10px; }
    QPushButton:hover { background-color: #3a3a3d; }
    QProgressBar { border: 1px solid #444; background: #2d2d30; color: white; text-align: center; }
    QProgressBar::chunk { background-color: #00aa88; width: 10px; }
    QHeaderView::section { background-color: #333; color: white; border: 1px solid #555; }
    QTableWidget { gridline-color: #444; }
    QTabWidget::pane { border: 1px solid #444; }
    QTabBar::tab { background: #2d2d30; color: #f0f0f0; padding: 5px; border: 1px solid #555; border-bottom-color: #444; border-top-left-radius: 4px; border-top-right-radius: 4px; }
    QTabBar::tab:selected { background: #3e3e42; border-bottom-color: #3e3e42; }
    QToolBar { border-bottom: 1px solid #444; background: #222; spacing: 10px; } 
    QToolButton { background: transparent; border: none; color: #ccc; font-size: 16px; font-weight: bold; } 
    QToolButton:hover { color: #fff; background: #333; }

"""

LIGHT_THEME = """
    QMainWindow, QWidget { background-color: #e6e6e6; color: #1a1a1a; }
    QLabel, QLineEdit, QCheckBox, QPushButton, QTableWidget, QListWidget, QTextEdit {
        color: #1a1a1a; font-size: 13px;
    }
    QLineEdit, QTableWidget, QListWidget, QTextEdit {
        background-color: #f9f9f9; border: 1px solid #bbb; padding: 4px; color: #1a1a1a;
    }
    QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #999; background-color: #eee; }
    QCheckBox::indicator:checked { background-color: #0078d7; border: 1px solid #0078d7; }
    QPushButton { background-color: #dcdcdc; border: 1px solid #bbb; border-radius: 4px; padding: 6px 10px; color: #1a1a1a; }
    QPushButton:hover { background-color: #cfcfcf; }
    QProgressBar { border: 1px solid #bbb; background: #e0e0e0; color: black; text-align: center; }
    QProgressBar::chunk { background-color: #00aa88; width: 10px; }
    QHeaderView::section { background-color: #d0d0d0; color: #1a1a1a; border: 1px solid #bbb; }
    QTableWidget { gridline-color: #ccc; }
    QTabWidget::pane { border: 1px solid #bbb; }
    QTabBar::tab { background: #dcdcdc; color: #1a1a1a; padding: 5px; border: 1px solid #bbb; border-bottom-color: #bbb; border-top-left-radius: 4px; border-top-right-radius: 4px; }
    QTabBar::tab:selected { background: #e6e6e6; border-bottom-color: #e6e6e6; }
    QToolBar { border-bottom: 1px solid #bbb; background: #e6e6e6; spacing: 10px; } 
    QToolButton { background: transparent; border: none; color: #333; font-size: 16px; font-weight: bold; } 
    QToolButton:hover { color: #000; background: #d0d0d0; }

"""

log_path = os.path.join(tempfile.gettempdir(), 'p2p_app.log')
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', filename=log_path)
class TimedMessageBox(QMessageBox):
    """QMessageBox with automatic timeout."""
    def __init__(self, timeout_ms=10000, parent=None):
        super().__init__(parent)
        self.timeout_ms = timeout_ms
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.reject)
    def exec(self):
        self.timer.start(self.timeout_ms)
        return super().exec()
class MD5Worker(QThread):
    """Worker thread to compute MD5 hashes without freezing UI."""
    md5_calculated = pyqtSignal(str, str)
    def __init__(self, filepaths):
        super().__init__()
        self.filepaths = filepaths
    def run(self):
        for fp in self.filepaths:
            if os.path.isdir(fp):
                 self.md5_calculated.emit(fp, "Folder")
                 continue
            try:
                time.sleep(0.01)
                md5 = compute_md5(fp)
                self.md5_calculated.emit(fp, md5)
            except Exception as e:
                logging.error(f"MD5 Error for {fp}: {e}")
                self.md5_calculated.emit(fp, "Error")
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("P2P File Sharing App")
        self.settings_manager = SettingsManager()
        self.history_manager = HistoryManager()
        self.lang_manager = LanguageManager()
        
        # Initialize save_dir early
        self.save_dir = self.settings_manager.get("save_dir")
        if not self.save_dir or not os.path.exists(self.save_dir):
             self.save_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        
        # Connect language change signal
        self.lang_manager.language_changed.connect(self.update_ui_text)

        self.setWindowTitle(self.lang_manager.get("window_title"))
        # Restore Window Geometry
        w = self.settings_manager.get("window_width", 980)
        h = self.settings_manager.get("window_height", 680)
        x = self.settings_manager.get("window_x", 100)
        y = self.settings_manager.get("window_y", 100)
        self.resize(w, h)
        self.move(x, y)
        
        self.setMinimumSize(980, 680)
        self.setAcceptDrops(True) # Enable Drag and Drop
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        # Corner Controls (Refresh, Language, Theme)
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(10)

        # Refresh
        refresh_btn = QPushButton("↻")
        refresh_btn.setToolTip("Refresh App (Reset All)")
        refresh_btn.setFixedSize(30, 30)
        refresh_btn.clicked.connect(self.on_app_refresh)
        corner_layout.addWidget(refresh_btn)

        # Language
        self.lang_label = QLabel("Language:")
        corner_layout.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Русский", "ru")
        self.lang_combo.addItem("Қазақша", "kk")
        
        current_lang = self.settings_manager.get("language", "en")
        index = self.lang_combo.findData(current_lang)
        if index >= 0:
            self.lang_combo.setCurrentIndex(index)
        
        # Explicitly apply saved language
        
        self.lang_combo.currentIndexChanged.connect(self.change_language)
        corner_layout.addWidget(self.lang_combo)

        # Theme
        self.theme_btn = QPushButton("Toggle Theme")
        self.theme_btn.clicked.connect(self.toggle_theme)
        corner_layout.addWidget(self.theme_btn)

        # Set as corner widget
        self.tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)
        
        # System Tray Init
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        
        tray_menu = QMenu()
        restore_action = QAction("Restore", self)
        restore_action.triggered.connect(self.showNormal)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        
        tray_menu.addAction(restore_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # Use lambda to bypass potential enum conversion issues in some PyQt6 environments
        self.tray_icon.activated.connect(lambda reason: self.on_tray_icon_activated(reason))
        self._is_quitting = False

        send_tab = QWidget()

        send_layout = QVBoxLayout()
        top_row = QHBoxLayout()
        file_col = QVBoxLayout()
        self.file_btn = QPushButton("Select Files")
        self.file_btn.clicked.connect(self.select_files)
        file_col.addWidget(self.file_btn)
        self.folder_btn = QPushButton("Select Folder")
        self.folder_btn.clicked.connect(self.select_folder)
        file_col.addWidget(self.folder_btn)
        self.clear_file_btn = QPushButton("Clear Files")
        self.clear_file_btn.clicked.connect(self.clear_files)
        file_col.addWidget(self.clear_file_btn)
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels(["Filename", "Size (MB)", "MD5 (Preview)", "Status"])
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.file_table.setSelectionBehavior(self.file_table.SelectionBehavior.SelectRows)
        self.file_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self.show_sender_file_context_menu)
        file_col.addWidget(self.file_table)
        top_row.addLayout(file_col, 3)
        peer_col = QVBoxLayout()
        peer_header = QHBoxLayout()
        peer_header.addWidget(QLabel("Discovered Receivers:"))
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(24, 24)
        self.refresh_btn.setToolTip("Refresh Receiver List")
        self.refresh_btn.clicked.connect(self.search_receivers)
        peer_header.addWidget(self.refresh_btn)
        peer_col.addLayout(peer_header)
        self.search_btn = QPushButton("Search Receivers")
        self.search_btn.clicked.connect(self.search_receivers)
        peer_col.addWidget(self.search_btn)
        self.receiver_list = QListWidget()
        self.receiver_list.itemSelectionChanged.connect(self.on_peer_selected)
        peer_col.addWidget(self.receiver_list)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_to_receiver)
        self.connect_btn.setEnabled(False)
        peer_col.addWidget(self.connect_btn)
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_files)
        self.send_btn.setEnabled(False)
        peer_col.addWidget(self.send_btn)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.disconnect_sender)
        self.disconnect_btn.setEnabled(False)
        peer_col.addWidget(self.disconnect_btn)
        btn_row = QHBoxLayout()
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)
        btn_row.addWidget(self.pause_btn)
        self.stop_btn = QPushButton("Cancel Transfer")
        self.stop_btn.clicked.connect(self.stop_sender_transfer)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.stop_btn)
        peer_col.addLayout(btn_row)
        self.selected_peer_label = QLabel("Selected: none")
        peer_col.addWidget(self.selected_peer_label)
        self.connection_status_label = QLabel("Connection: Disconnected")
        peer_col.addWidget(self.connection_status_label)
        self.auto_refresh_checkbox = QCheckBox("Auto-refresh receivers")
        self.auto_refresh_checkbox.setChecked(False)
        peer_col.addWidget(self.auto_refresh_checkbox)
        top_row.addLayout(peer_col, 1)
        send_layout.addLayout(top_row)
        opts_row = QHBoxLayout()
        self.compress_check = QCheckBox("Enable Compression (zip before sending)")
        opts_row.addWidget(self.compress_check)
        send_layout.addLayout(opts_row)
        actions_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress_label = QLabel("Progress: 0%")
        self.stats_label = QLabel("Speed: - | ETA: -")
        actions_row.addWidget(self.progress)
        actions_row.addWidget(self.progress_label)
        actions_row.addWidget(self.stats_label)
        send_layout.addLayout(actions_row)
        send_tab.setLayout(send_layout)
        self.tabs.addTab(send_tab, "Send")
        pass
        receive_tab = QWidget()
        receive_layout = QVBoxLayout()
        port_row = QHBoxLayout()
        self.listen_port = QLineEdit()
        self.listen_port.setPlaceholderText("Listen Port (5000)")
        port_row.addWidget(self.listen_port)
        self.start_receive_btn = QPushButton("Start Receiving")
        self.start_receive_btn.clicked.connect(self.start_receive_clicked)
        port_row.addWidget(self.start_receive_btn)
        self.stop_receive_btn = QPushButton("Stop Receiving")
        self.stop_receive_btn.clicked.connect(self.stop_receiving)
        self.stop_receive_btn.setEnabled(False)
        port_row.addWidget(self.stop_receive_btn)
        receive_layout.addLayout(port_row)
        recv_settings_row = QHBoxLayout()
        self.save_dir_btn = QPushButton("Set Save Folder")
        self.save_dir_btn.clicked.connect(self.choose_save_folder)
        self.auto_accept_checkbox = QCheckBox("Auto-accept all (connections + file transfers)")
        self.auto_accept_checkbox.setChecked(self.settings_manager.get("auto_accept", False))
        recv_settings_row.addWidget(self.save_dir_btn)
        recv_settings_row.addWidget(self.auto_accept_checkbox)
        receive_layout.addLayout(recv_settings_row)
        receive_layout.addWidget(QLabel("Received Files:"))
        self.received_files_table = QTableWidget()
        self.received_files_table.setColumnCount(4)
        self.received_files_table.setHorizontalHeaderLabels(["Filename", "Size (MB)", "Path", "Status"])
        self.received_files_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.received_files_table.setSelectionBehavior(self.received_files_table.SelectionBehavior.SelectRows)
        self.received_files_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.received_files_table.customContextMenuRequested.connect(self.show_receiver_file_context_menu)
        receive_layout.addWidget(self.received_files_table)
        recv_progress_row = QHBoxLayout()
        self.receiver_progress = QProgressBar()
        self.receiver_progress_label = QLabel("Progress: 0%")
        self.receiver_stats_label = QLabel("Speed: - | ETA: -")
        self.pause_recv_btn = QPushButton("Pause")
        self.pause_recv_btn.clicked.connect(self.toggle_receiver_pause)
        self.pause_recv_btn.setEnabled(False)
        self.stop_recv_btn = QPushButton("Cancel Transfer")
        self.stop_recv_btn.clicked.connect(self.stop_receiver_transfer)
        self.stop_recv_btn.setEnabled(False)
        recv_progress_row.addWidget(QLabel("Transfer Progress:"))
        recv_progress_row.addWidget(self.receiver_progress)
        recv_progress_row.addWidget(self.receiver_progress_label)
        recv_progress_row.addWidget(self.receiver_stats_label)
        recv_progress_row.addWidget(self.pause_recv_btn)
        recv_progress_row.addWidget(self.stop_recv_btn)
        receive_layout.addLayout(recv_progress_row)
        self.receiver_info_label = QLabel("No incoming requests yet.")
        receive_layout.addWidget(self.receiver_info_label)
        receive_tab.setLayout(receive_layout)
        self.tabs.addTab(receive_tab, "Receive")
        
        # History Tab
        history_tab = QWidget()
        history_layout = QVBoxLayout()
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(["Time", "Type", "Filename", "Size (MB)", "Peer", "Status"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self.show_history_context_menu)
        history_layout.addWidget(self.history_table)
        
        self.clear_history_btn = QPushButton("Clear History")
        self.clear_history_btn.clicked.connect(self.clear_history)
        history_layout.addWidget(self.clear_history_btn)
        
        history_tab.setLayout(history_layout)
        self.tabs.addTab(history_tab, "History")
        
        history_tab.setLayout(history_layout)
        self.tabs.addTab(history_tab, "History")
        
        self.populate_history_table()

        # Chat Tab Removed per user request
        # chat_tab = QWidget()
        # ...

        # Mobile Tab
        mobile_tab = QWidget()
        mobile_layout = QVBoxLayout()
        
        # Info Box
        info_box = QWidget()
        info_box.setObjectName("infoBox")
        # Style will be set by apply_theme
        info_layout = QVBoxLayout(info_box)
        
        self.web_status_label = QLabel("Mobile Server: Stopped")
        self.web_status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        self.web_url_label = QLabel("URL: -")
        self.web_url_label.setStyleSheet("font-size: 14px; color: #aaa;")
        
        info_layout.addWidget(self.web_status_label)
        info_layout.addWidget(self.web_url_label)
        
        # OTP Display
        otp_layout = QHBoxLayout()
        self.otp_label = QLabel("Connection Code:")
        self.otp_label.setStyleSheet("font-size: 12px; color: #aaa;")
        self.otp_display = QLabel("-")
        self.otp_display.setStyleSheet("font-size: 24px; font-weight: bold; color: #4CAF50; letter-spacing: 5px; font-family: monospace;")
        otp_layout.addWidget(self.otp_label)
        otp_layout.addWidget(self.otp_display)
        otp_layout.addStretch()
        info_layout.addLayout(otp_layout)
        
        mobile_layout.addWidget(info_box)

        # Controls
        controls_layout = QHBoxLayout()
        self.start_web_btn = QPushButton("Start Mobile Server")
        self.start_web_btn.setMinimumHeight(40)
        self.start_web_btn.clicked.connect(self.start_web_server)
        
        self.stop_web_btn = QPushButton("Stop Server")
        self.stop_web_btn.setMinimumHeight(40)
        self.stop_web_btn.clicked.connect(self.stop_web_server)
        self.stop_web_btn.setEnabled(False)
        
        controls_layout.addWidget(self.start_web_btn)
        controls_layout.addWidget(self.stop_web_btn)
        
        # Reset Code button
        self.reset_code_btn = QPushButton("Reset Code")
        self.reset_code_btn.setMinimumHeight(40)
        self.reset_code_btn.clicked.connect(self.reset_otp_code)
        self.reset_code_btn.setEnabled(False)
        controls_layout.addWidget(self.reset_code_btn)
        
        mobile_layout.addLayout(controls_layout)

        # Shortcuts
        shortcuts_layout = QHBoxLayout()
        
        self.set_folder_btn = QPushButton("Set Shared Folder")
        self.set_folder_btn.clicked.connect(self.choose_save_folder)
        
        self.share_files_btn = QPushButton("Share Files to Mobile...")
        self.share_files_btn.clicked.connect(self.share_files_to_mobile)
        
        shortcuts_layout.addWidget(self.set_folder_btn)
        shortcuts_layout.addWidget(self.share_files_btn)
        mobile_layout.addLayout(shortcuts_layout)
        
        # Connected Devices
        devices_label = QLabel(f"Authorized Devices (0/{MAX_CONNECTIONS})")
        devices_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.devices_count_label = devices_label
        mobile_layout.addWidget(devices_label)
        
        self.devices_list = QListWidget()
        self.devices_list.setMaximumHeight(100)
        self.devices_list.setStyleSheet("font-size: 12px;")
        mobile_layout.addWidget(self.devices_list)

        # Folder Info
        self.mobile_folder_info_label = QLabel("Files in your Shared Folder are visible to mobile.")
        self.mobile_folder_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mobile_layout.addWidget(self.mobile_folder_info_label)
        
        # Folder Info & Stats
        stats_layout = QVBoxLayout()
        self.folder_path_label = QLabel(self.save_dir)
        self.folder_path_label.setStyleSheet("color: #666; font-size: 12px;")
        self.folder_path_label.setWordWrap(True)
        
        self.folder_stats_label = QLabel("Loading stats...")
        self.folder_stats_label.setStyleSheet("font-weight: bold; color: #333;")
        
        stats_layout.addWidget(self.folder_path_label)
        stats_layout.addWidget(self.folder_stats_label)
        mobile_layout.addLayout(stats_layout)
        
        # Mobile History Table
        self.mobile_history_label = QLabel("Mobile Transfer History")
        self.mobile_history_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        mobile_layout.addWidget(self.mobile_history_label)
        
        self.mobile_history_table = QTableWidget()
        self.mobile_history_table.setColumnCount(4)
        self.mobile_history_table.setHorizontalHeaderLabels(["Type", "File", "Size", "Time"])
        self.mobile_history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.mobile_history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mobile_history_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mobile_history_table.customContextMenuRequested.connect(self.show_mobile_context_menu)
        mobile_layout.addWidget(self.mobile_history_table)
        
        self.clear_mobile_hist_btn = QPushButton("Clear Mobile History")
        self.clear_mobile_hist_btn.clicked.connect(self.clear_mobile_history)
        mobile_layout.addWidget(self.clear_mobile_hist_btn)

        self.update_folder_info()
        self.load_mobile_history()
        
        mobile_tab.setLayout(mobile_layout)
        self.tabs.addTab(mobile_tab, "Mobile")

        self.sender_app = None
        self.receiver_app = None
        self.md5_worker = None
        self.filenames = []
        # save_dir already loaded above
        
        self.current_theme = self.settings_manager.get("theme", "dark")
        self.apply_theme()

        # Apply saved language here, after UI is fully built
        saved_lang = self.settings_manager.get("language", "en")
        self.lang_manager.set_language(saved_lang)

        self.update_ui_text()

    def change_language(self, index):
        lang_code = self.lang_combo.currentData()
        self.lang_manager.set_language(lang_code)
        self.settings_manager.set("language", lang_code)
        self.update_ui_text()

    def toggle_theme(self):
        if self.current_theme == "dark":
            self.current_theme = "light"
        else:
            self.current_theme = "dark"
        self.settings_manager.set("theme", self.current_theme)
        self.apply_theme()
        self.update_ui_text() # Update button text if needed

    def apply_theme(self):
        if self.current_theme == "light":
            self.setStyleSheet(LIGHT_THEME)
            self._set_title_bar_color(dark=False)
            
            # Mobile Tab Specifics - Light
            if hasattr(self, 'web_status_label'):
                self.findChild(QWidget, "infoBox").setStyleSheet("background-color: #ffffff; border: 1px solid #ccc; border-radius: 8px; padding: 10px;")
                self.web_status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
                self.web_url_label.setStyleSheet("font-size: 14px; color: #666;")
                self.folder_stats_label.setStyleSheet("font-weight: bold; color: #333;")
                self.folder_path_label.setStyleSheet("color: #666; font-size: 12px;")
                if hasattr(self, 'otp_label'):
                    self.otp_label.setStyleSheet("font-size: 12px; color: #666;")
                    self.otp_display.setStyleSheet("font-size: 24px; font-weight: bold; color: #2e7d32; letter-spacing: 5px; font-family: monospace;")
                
        else:
            self.setStyleSheet(DARK_THEME)
            self._set_title_bar_color(dark=True)
            
            # Mobile Tab Specifics - Dark
            if hasattr(self, 'web_status_label'):
                self.findChild(QWidget, "infoBox").setStyleSheet("background-color: #3d3d3d; border-radius: 8px; border: 1px solid #555; padding: 10px;")
                self.web_status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
                self.web_url_label.setStyleSheet("font-size: 14px; color: #aaa;")
                self.folder_stats_label.setStyleSheet("font-weight: bold; color: #ffffff;")
                self.folder_path_label.setStyleSheet("color: #aaa; font-size: 12px;")
                if hasattr(self, 'otp_label'):
                    self.otp_label.setStyleSheet("font-size: 12px; color: #aaa;")
                    self.otp_display.setStyleSheet("font-size: 24px; font-weight: bold; color: #4CAF50; letter-spacing: 5px; font-family: monospace;")

    def _set_title_bar_color(self, dark=True):
        """
        Force Windows Title Bar to match theme.
        Requires Windows 10 build 1903+ (Build 18362) or Windows 11.
        """
        try:
            hwnd = int(self.winId())
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            # For older Win10 builds it was 19, but 20 is standard for modern versions.
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = 1 if dark else 0
            windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(c_int(value)), 4)
        except Exception as e:
            # Safely ignore if on non-Windows or older version
            print(f"Failed to set title bar color: {e}")

    def start_web_server(self):
        if not self.save_dir or not os.path.exists(self.save_dir):
            QMessageBox.warning(self, "Error", "Save directory not set or invalid.")
            return
            
        current_lang = self.settings_manager.get("language", "en")
        self.web_thread = WebServerThread(self.save_dir, lang_code=current_lang)
        self.web_thread.status_msg.connect(self.update_web_status)
        self.web_thread.error_occurred.connect(self.show_web_error)
        self.web_thread.transfer_log.connect(self.on_web_transfer)
        self.web_thread.otp_generated.connect(self.on_otp_generated)
        self.web_thread.device_connected.connect(self.on_device_connected)
        self.web_thread.start()
        
        self.start_web_btn.setEnabled(False)
        self.stop_web_btn.setEnabled(True)
        self.reset_code_btn.setEnabled(True)
        self.web_active = True

    def stop_web_server(self):
        if hasattr(self, 'web_thread') and self.web_thread:
            self.web_thread.stop()
            self.web_thread.wait() # Wait for thread to finish
            self.web_thread = None
        
        self.start_web_btn.setEnabled(True)
        self.stop_web_btn.setEnabled(False)
        self.reset_code_btn.setEnabled(False)
        self.otp_display.setText("-")
        self.devices_list.clear()
        self.update_devices_count()
        self.web_active = False
        self.web_status_label.setText(self.lang_manager.get("mobile_server_stopped"))
        self.web_url_label.setText("URL: -")

    def update_web_status(self, msg):
        self.web_status_label.setText(msg)
        if "http" in msg:
            url = msg.split(": ", 1)[1]
            self.web_url_label.setText(f"URL: {url}")

    def show_web_error(self, err):
        QMessageBox.critical(self, "Web Server Error", err)
        self.stop_web_server()

    def on_otp_generated(self, otp):
        """Update OTP display when generated."""
        self.otp_display.setText(otp)

    def on_device_connected(self, ip, device_name):
        """Update devices list when a new device is authorized."""
        self.devices_list.addItem(f"{device_name} ({ip})")
        self.update_devices_count()
        # Optionally show a small notification or status update
        print(f"Device connected: {device_name} ({ip})")

    def update_devices_count(self):
        """Update the label showing the number of connected devices."""
        count = self.devices_list.count()
        max_conn = MAX_CONNECTIONS  # Should match MAX_CONNECTIONS in web_server
        self.devices_count_label.setText(self.lang_manager.get("mobile_connections").format(count, max_conn))

    def reset_otp_code(self):
        """Request a new OTP and clear current authorizations."""
        if hasattr(self, 'web_thread') and self.web_thread:
            new_code = self.web_thread.reset_otp()
            self.devices_list.clear()
            self.update_devices_count()
            QMessageBox.information(self, "Code Reset", f"New Connection Code: {new_code}")

    def on_web_transfer(self, direction, filename, size_mb, peer):
        """Handle transfer logs from the web server."""
        # Add to Mobile History Table instead of Main History
        row = self.mobile_history_table.rowCount()
        self.mobile_history_table.insertRow(row)
        
        time_str = time.strftime("%H:%M:%S")
        
        # Determine translation key based on direction
        trans_key = "mobile_upload" if "Upload" in direction else "mobile_download"
        if "Sent" in direction or "Send" in direction: # Fallback
             trans_key = "mobile_sent"

        type_item = QTableWidgetItem(self.lang_manager.get(trans_key))
        type_item.setData(Qt.ItemDataRole.UserRole, trans_key)
        self.mobile_history_table.setItem(row, 0, type_item)
        
        fname_item = QTableWidgetItem(filename)
        # FIX: Store full path
        full_path = os.path.join(self.save_dir, filename)
        fname_item.setData(Qt.ItemDataRole.UserRole, full_path)
        
        self.mobile_history_table.setItem(row, 1, fname_item)
        self.mobile_history_table.setItem(row, 2, QTableWidgetItem(f"{size_mb:.2f} MB"))
        self.mobile_history_table.setItem(row, 3, QTableWidgetItem(time_str))
        
        self.save_mobile_history() # Save change
        
        # Refresh stats since a file was added/downloaded
        self.update_folder_info()
        
        # Optionally show notification
        self.show_notification(f"{direction} Complete", f"{filename} ({size_mb:.2f} MB)")

    def share_files_to_mobile(self):
        """Allow user to pick files to copy to the shared folder and choose recipients."""
        if not self.save_dir or not os.path.exists(self.save_dir):
            QMessageBox.warning(self, "Error", "Please set a Shared Folder first.")
            return

        files, _ = QFileDialog.getOpenFileNames(self, "Select Files to Share")
        if not files:
            return

        # Handle recipient selection
        recipients = ['*']  # Default to all
        if self.web_active and self.web_thread:
            devices = self.web_thread.get_authorized_devices()
            if devices:
                dialog = RecipientSelectionDialog(devices, self.lang_manager, self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    recipients = dialog.get_selected_recipients()
                else:
                    return  # User cancelled sharing
            
        count = 0
        skipped = []
        for file_path in files:
            try:
                # Check for duplicate
                dest_path = os.path.join(self.save_dir, os.path.basename(file_path))
                if os.path.exists(dest_path):
                     skipped.append(os.path.basename(file_path))
                     continue

                if os.path.exists(file_path):
                    shutil.copy2(file_path, self.save_dir)
                    count += 1
                    
                    # Log to Mobile History
                    fname = os.path.basename(file_path)
                    fsize = os.path.getsize(file_path) / (1024 * 1024)
                    
                    row = self.mobile_history_table.rowCount()
                    self.mobile_history_table.insertRow(row)
                    
                    type_item = QTableWidgetItem(self.lang_manager.get("mobile_sent"))
                    type_item.setData(Qt.ItemDataRole.UserRole, "mobile_sent")
                    self.mobile_history_table.setItem(row, 0, type_item)
                    
                    fname_item = QTableWidgetItem(fname)
                    # FIX: Store SOURCE path (so we can open the original file)
                    fname_item.setData(Qt.ItemDataRole.UserRole, file_path)
                    
                    self.mobile_history_table.setItem(row, 1, fname_item)
                    self.mobile_history_table.setItem(row, 2, QTableWidgetItem(f"{fsize:.2f} MB"))
                    self.mobile_history_table.setItem(row, 3, QTableWidgetItem(time.strftime("%H:%M:%S")))

                    # Log to Web Server History if running
                    if self.web_active and self.web_thread:
                         # Set who can see this file
                         self.web_thread.set_file_recipients(fname, recipients)
                         # Log to web history
                         self.web_thread.add_share_history(fname, fsize, recipients)

            except Exception as e:
                print(f"Failed to copy {file_path}: {e}")
                QMessageBox.critical(self, "Share Error", f"Failed to share '{os.path.basename(file_path)}':\n{e}")
        
        self.save_mobile_history() # Save change
        self.update_folder_info()
        
        msg = ""
        if count > 0:
            msg += f"Added {count} files to Mobile Share.\n"
        if skipped:
            msg += f"\nSkipped {len(skipped)} duplicates:\n" + "\n".join(skipped[:5])
            if len(skipped) > 5: msg += "\n..."
            QMessageBox.warning(self, "Files Skipped", msg)
        elif count > 0:
            QMessageBox.information(self, "Success", msg)
            # If server is running, the list updates automatically on refresh

    def update_ui_text(self):
        _ = self.lang_manager.get
        self.setWindowTitle(_("window_title"))
        self.lang_label.setText(_("label_language"))
        self.file_btn.setText(_("select_files"))
        self.folder_btn.setText(_("select_folder"))
        self.clear_file_btn.setText(_("clear_files"))
        self.file_table.setHorizontalHeaderLabels([
            _("header_filename"), _("header_size"), _("header_md5"), _("header_status")
        ])
        self.refresh_btn.setToolTip(_("search_receivers")) # Tooltip for refresh
        self.search_btn.setText(_("search_receivers"))
        self.connect_btn.setText(_("connect"))
        self.send_btn.setText(_("send"))
        self.disconnect_btn.setText(_("disconnect"))
        
        # Pause/Resume handling
        if self.pause_btn.text() in ["Pause", "Пауза", "Кідірту"]:
             self.pause_btn.setText(_("pause"))
        elif self.pause_btn.text() in ["Resume", "Продолжить", "Жалғастыру"]:
             self.pause_btn.setText(_("resume"))

        self.stop_btn.setText(_("cancel_transfer"))
        self.selected_peer_label.setText(
            self.selected_peer_label.text().replace("Selected: ", _("selected_prefix")).replace("Выбрано: ", _("selected_prefix")).replace("Таңдалған: ", _("selected_prefix"))
        )
        if "none" in self.selected_peer_label.text() or "нет" in self.selected_peer_label.text() or "жоқ" in self.selected_peer_label.text():
             self.selected_peer_label.setText(_("selected_none"))

        self.connection_status_label.setText(
             # This one is highly dynamic. We might just leave it or try to translate static parts.
             # For now, let's reset to default if disconnected.
             _("connection_disconnected") if "Disconnect" in self.connection_status_label.text() or "Отключено" in self.connection_status_label.text() or "Ажыратылған" in self.connection_status_label.text() else self.connection_status_label.text()
        )
        self.auto_refresh_checkbox.setText(_("auto_refresh"))
        self.compress_check.setText(_("enable_compression"))
        self.progress_label.setText(self.progress_label.text().replace("Progress: ", _("progress_prefix")).replace("Прогресс: ", _("progress_prefix")))
        
        
        # Tabs
        self.tabs.setTabText(0, _("tab_send"))
        self.tabs.setTabText(1, _("tab_receive"))
        self.tabs.setTabText(2, _("tab_history"))
        # Chat tab removed
        self.tabs.setTabText(3, _("tab_mobile"))
        
        self.listen_port.setPlaceholderText(_("listen_port_placeholder"))
        self.start_receive_btn.setText(_("start_receiving"))
        self.stop_receive_btn.setText(_("stop_receiving"))
        self.save_dir_btn.setText(_("set_save_folder"))
        self.auto_accept_checkbox.setText(_("auto_accept"))
        
        self.received_files_table.setHorizontalHeaderLabels([
             _("header_filename"), _("header_size"), _("header_path"), _("header_status")
        ])
        
        self.receiver_progress_label.setText(self.receiver_progress_label.text().replace("Progress: ", _("progress_prefix")).replace("Прогресс: ", _("progress_prefix")))
        
        if self.pause_recv_btn.text() in ["Pause", "Пауза", "Кідірту"]:
             self.pause_recv_btn.setText(_("pause"))
        elif self.pause_recv_btn.text() in ["Resume", "Продолжить", "Жалғастыру"]:
             self.pause_recv_btn.setText(_("resume"))

        self.stop_recv_btn.setText(_("cancel_transfer"))
        
        # History
        self.history_table.setHorizontalHeaderLabels([
            _("header_timestamp"), _("header_direction"), _("header_filename"), 
            _("header_size"), _("header_peer"), _("header_status")
        ])
        self.clear_history_btn.setText(_("btn_clear_history"))
        
        # Chat related UI updates removed
        # self.chat_input.setPlaceholderText(_("chat_placeholder"))
        # self.chat_send_btn.setText(_("btn_send_chat"))

        if self.receiver_info_label.text() in ["No incoming requests yet.", "Нет входящих запросов.", "Кіріс сұраулар жоқ."]:
             self.receiver_info_label.setText(_("no_incoming"))

        self.theme_btn.setText(_("mode_light") if self.current_theme == "dark" else _("mode_dark"))
    
        # Refresh File Table Statuses
        for row in range(self.file_table.rowCount()):
             # MD5 Status (col 2)
             item = self.file_table.item(row, 2)
             if item:
                 key = item.data(Qt.ItemDataRole.UserRole)
                 if key:
                     item.setText(_(key))
             # Status (col 3)
             item = self.file_table.item(row, 3)
             if item:
                 key = item.data(Qt.ItemDataRole.UserRole)
                 if key:
                     item.setText(_(key))

        # Refresh Received Files Table
        for row in range(self.received_files_table.rowCount()):
             # Status (col 3)
             item = self.received_files_table.item(row, 3)
             if item:
                 key = item.data(Qt.ItemDataRole.UserRole)
                 if key:
                     item.setText(_(key))

        # Refresh History
        self.populate_history_table()
        self.load_mobile_history()
        
        # Refresh Mobile History Headers
        self.mobile_history_table.setHorizontalHeaderLabels([
            _("header_mobile_type"), _("header_mobile_file"), _("header_mobile_size"), _("header_mobile_time")
        ])
        
        # Mobile Tab Content
        self.start_web_btn.setText(_("btn_start_mobile"))
        self.stop_web_btn.setText(_("btn_stop_mobile"))
        self.set_folder_btn.setText(_("btn_set_shared"))
        self.share_files_btn.setText(_("btn_share_files"))
        self.mobile_folder_info_label.setText(_("mobile_folder_info"))
        self.mobile_history_label.setText(_("mobile_hist_label"))
        self.clear_mobile_hist_btn.setText(_("btn_clear_mobile"))
        self.otp_label.setText(_("mobile_auth_code"))
        self.reset_code_btn.setText(_("btn_reset_code"))
        self.update_devices_count()
        
        # Update Web Status Text if stopped
        if "Stopped" in self.web_status_label.text() or "Остановлен" in self.web_status_label.text() or "Тоқтатылды" in self.web_status_label.text():
             self.web_status_label.setText(_("mobile_server_stopped"))
    def on_app_refresh(self):
        """Reset the application state to fresh start."""
        logging.debug("App Refresh initiated")
        self.disconnect_sender()
        # self.clear_files() # Don't clear files on refresh, per user request to allow resume
        self.receiver_list.clear()
        self.selected_peer_label.setText(self.lang_manager.get("selected_none"))
        if self.stop_receive_btn.isEnabled():
            self.stop_receiving()
        self.stop_receive_btn.setEnabled(False)
        self.start_receive_btn.setEnabled(True)
        self.receiver_info_label.setText(self.lang_manager.get("no_incoming"))
        self.received_files_table.setRowCount(0)
        self.receiver_progress.setValue(0)
        self.receiver_progress_label.setText(f"{self.lang_manager.get('progress_prefix')}0%")
        self.connection_status_label.setText(self.lang_manager.get("connection_disconnected"))
        self.progress.setValue(0)
        self.progress_label.setText(f"{self.lang_manager.get('progress_prefix')}0%")
        QMessageBox.information(self, self.lang_manager.get("msg_app_refreshed"), self.lang_manager.get("msg_app_refreshed_body"))
    def select_files(self):
        new_files, _ = QFileDialog.getOpenFileNames(self, self.lang_manager.get("select_files"))
        if not new_files:
            return
        self.add_files(new_files)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.lang_manager.get("select_folder"))
        if not folder:
            return
        self.add_files([folder])

    def get_dir_size(self, start_path):
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(start_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        total_size += os.path.getsize(fp)
        except Exception as e:
            logging.error(f"Error calculating dir size: {e}")
        return total_size

    def add_files(self, new_files):
        """Add files to the list, handling limits and UI updates."""
        if len(self.filenames) + len(new_files) > 50:
            QMessageBox.warning(self, self.lang_manager.get("msg_limit_reached"), self.lang_manager.get("msg_limit_reached_body"))
            return
        existing = set(self.filenames)
        file_statuses = {}
        for row in range(self.file_table.rowCount()):
             name_item = self.file_table.item(row, 0)
             status_item = self.file_table.item(row, 3)
             if name_item and status_item:
                 file_statuses[name_item.text()] = status_item.text()
        for f in new_files:
            if f not in existing:
                self.filenames.append(f)
                existing.add(f)
        self.file_table.setRowCount(0)
        for filepath in self.filenames:
            base_name = os.path.basename(filepath)
            status = file_statuses.get(base_name, "Pending")
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)
            if os.path.isdir(filepath):
                 size_mb = self.get_dir_size(filepath) / (1024 * 1024)
            else:
                 size_mb = os.path.getsize(filepath) / (1024 * 1024)
            self.file_table.setItem(row, 0, QTableWidgetItem(base_name))
            self.file_table.setItem(row, 1, QTableWidgetItem(f"{size_mb:.2f}"))
            
            calc_item = QTableWidgetItem(self.lang_manager.get("status_calculating"))
            calc_item.setData(Qt.ItemDataRole.UserRole, "status_calculating")
            self.file_table.setItem(row, 2, calc_item)
            
            status_display = self.lang_manager.get("status_pending") if status == "Pending" else status
            status_widget = QTableWidgetItem(status_display)
            if status == "Pending":
                 status_widget.setData(Qt.ItemDataRole.UserRole, "status_pending")
            
            if status.lower() in ("sent", "complete"):
                 status_widget.setBackground(Qt.GlobalColor.darkGreen)
                 status_widget.setData(Qt.ItemDataRole.UserRole, "status_success") # Assuming completed means success here
            self.file_table.setItem(row, 3, status_widget)
        logging.debug(f"Selected files (total): {len(self.filenames)}")
        if self.md5_worker and self.md5_worker.isRunning():
            self.md5_worker.terminate()
            self.md5_worker.wait()
        self.md5_worker = MD5Worker(self.filenames)
        self.md5_worker.md5_calculated.connect(self.on_md5_calculated)
        self.md5_worker.start()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                files.append(url.toLocalFile())
        if files:
            # Switch to 'Send' tab if not already there
            self.tabs.setCurrentIndex(0)
            self.add_files(files)
    def clear_files(self):
        self.filenames = []
        self.file_table.setRowCount(0)
        if self.md5_worker and self.md5_worker.isRunning():
            self.md5_worker.terminate()
        logging.debug("Files cleared")
    def on_md5_calculated(self, filepath, md5_hash):
        """Update the table with the calculated MD5."""
        base_name = os.path.basename(filepath)
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item and item.text() == base_name:
                self.file_table.setItem(row, 2, QTableWidgetItem(md5_hash[:8]))
                break
    def search_receivers(self):
        print("🔍 search_receivers called")
        logging.debug("Search receivers initiated")
        self.search_btn.setText(self.lang_manager.get("searching"))
        self.search_btn.setEnabled(False)
        discover_app = P2PApp('send', compress=False)
        try:
            peers = discover_app.discover_peers(timeout=5.0)
            print(f"🔍 Peers returned: {peers}")
            logging.debug(f"Discovered peers: {peers}")
            self._populate_peers_merge(peers)
        except Exception as e:
            print(f"🔍 Search error: {e}")
            logging.error(f"Search error: {e}")
        finally:
            self.search_btn.setText(self.lang_manager.get("search_receivers"))
            self.search_btn.setEnabled(True)
    def _populate_peers_merge(self, peers):
        """Update list with new peers, keeping existing ones."""
        print(f"🔍 Populating peers (merge): {peers}")
        logging.debug(f"Populating peers (merge): {peers}")
        existing_peers = {self.receiver_list.item(i).text() for i in range(self.receiver_list.count())}
        if not peers and not existing_peers:
            print("🔍 No peers found, showing message")
            QMessageBox.information(self, "No Receivers", "No receivers found on the local network.")
            return
        for ip, port in peers:
            peer_str = f"{ip}:{port}"
            if peer_str not in existing_peers:
                print(f"🔍 Adding peer to list: {peer_str}")
                item = QListWidgetItem(peer_str)
                item.setData(Qt.ItemDataRole.UserRole, (ip, port))
                self.receiver_list.addItem(item)
        self.receiver_list.update()
        self.receiver_list.repaint()
        print(f"🔍 List updated, item count: {self.receiver_list.count()}")
    def _populate_peers(self, peers):
        self._populate_peers_merge(peers)
    def update_folder_info(self):
        """Update the folder path and stats in Mobile Tab."""
        if not self.save_dir or not os.path.exists(self.save_dir):
            if hasattr(self, 'folder_path_label'):
                self.folder_path_label.setText("No folder set")
                self.folder_stats_label.setText("0 files, 0.00 MB")
            return

        if hasattr(self, 'folder_path_label'):
            self.folder_path_label.setText(self.save_dir)
            try:
                files = [f for f in os.listdir(self.save_dir) if os.path.isfile(os.path.join(self.save_dir, f))]
                count = len(files)
                total_size = sum(os.path.getsize(os.path.join(self.save_dir, f)) for f in files)
                size_mb = total_size / (1024 * 1024)
                self.folder_stats_label.setText(f"{count} files, {size_mb:.2f} MB")
            except Exception:
                self.folder_stats_label.setText("Error reading folder")

    def _auto_refresh_peers(self):
        """Periodically refresh the peer list."""
        self.update_folder_info()
        
        # Check if connected or sender
        if self.sender_app and self.sender_app.connected:
             return
        
        # Original logic was dependent on checkbox, but checkbox might have been removed or renamed.
        # Assuming we always want auto-refresh now or checking a flag.
        # Let's keep it safe:
        # if self.auto_refresh_checkbox.isChecked(): ... 
        # But for now just print debug and continue discovery
        
        # print("ðŸ”  Auto-refresh triggered")
        if hasattr(self, 'peer_discovery') and self.peer_discovery:
             # Just trigger the discovery thread if available, results come via headers/signals
             # But here we were calling discover_peers synchronously in the past?
             # Let's just use the existing logic if it was working or leave empty if we rely on signals.
             # Based on previous code, it seems it was trying to reuse P2PApp.
             pass
             
        # Re-implement simple discovery if needed or rely on manual refresh.
        # For now, just logging to avoid breaking flow.
        pass
    def _populate_peers_auto(self, peers):
        if self.receiver_list.selectedItems():
            return
        self.receiver_list.repaint()
        print(f"🔍 List updated, item count: {self.receiver_list.count()}")



    def on_peer_selected(self):
        sel = self.receiver_list.selectedItems()
        if not sel:
            self.selected_peer_label.setText(self.lang_manager.get("selected_none"))
            self.connect_btn.setEnabled(False)
            return
        self.connect_btn.setEnabled(True)
        item = sel[0]
        ip, port = item.data(Qt.ItemDataRole.UserRole)
        self.selected_peer_label.setText(f"{self.lang_manager.get('selected_prefix')}{ip}:{port}")
    def connect_to_receiver(self):
        sel = self.receiver_list.selectedItems()
        if not sel:
            QMessageBox.warning(self, self.lang_manager.get("msg_no_receiver"), self.lang_manager.get("msg_no_receiver_body"))
            return
        ip, port = sel[0].data(Qt.ItemDataRole.UserRole)
        try:
            if self.sender_app and self.sender_app.connected:
                logging.warning("Already connected, ignoring connect request")
                QMessageBox.warning(self, self.lang_manager.get("msg_already_connected"), self.lang_manager.get("msg_already_connected_body"))
                return
            compress = self.compress_check.isChecked()
            self.sender_app = P2PApp('send', port=0, compress=compress)
            self._connect_sender_signals(self.sender_app)
            sender_name = platform.node() or "Sender"
            threading.Thread(target=self.sender_app.connect, args=(ip, port, sender_name), daemon=True).start()
            self.connect_btn.setEnabled(False)
            self.send_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(True)
            self.search_btn.setEnabled(False)
            self.connection_status_label.setText(self.lang_manager.get("connection_connecting").format(f"{ip}:{port}"))
            logging.debug(f"Connecting to {ip}:{port}")
        except Exception as e:
            self.show_error(str(e))
            logging.error(f"Connect error: {e}")
    def send_files(self):
        if not self.sender_app or not self.sender_app.connected:
            QMessageBox.warning(self, self.lang_manager.get("msg_not_connected"), self.lang_manager.get("msg_not_connected_body"))
            return
        if not self.filenames:
            QMessageBox.warning(self, self.lang_manager.get("msg_no_files"), self.lang_manager.get("msg_no_files_body"))
            return
        pending_files = []
        for row in range(self.file_table.rowCount()):
            status_item = self.file_table.item(row, 3)
            if status_item:
                text = status_item.text().lower()
                if "sent" not in text and "complete" not in text:
                    if row < len(self.filenames):
                        pending_files.append(self.filenames[row])
        if not pending_files:
            QMessageBox.information(self, self.lang_manager.get("msg_all_sent"), self.lang_manager.get("msg_all_sent_body"))
            return
        try:
            threading.Thread(target=self.sender_app.send_files, args=(None, None, pending_files, None, True), daemon=True).start()
            self.stop_btn.setEnabled(True)
            self.pause_btn.setEnabled(True)
            self.send_btn.setEnabled(False)
            logging.debug(f"Send files initiated for {len(pending_files)} pending files")
        except Exception as e:
            self.show_error(str(e))
            logging.error(f"Send files error: {e}")
    def disconnect_sender(self):
        if self.sender_app and self.sender_app.connected:
            self.sender_app.disconnect()
            self.sender_app = None
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        self.connect_btn.setEnabled(True)
        self.search_btn.setEnabled(True)
        self.selected_peer_label.setText(self.lang_manager.get("selected_none"))
        self.receiver_list.clear()
        self.connection_status_label.setText(self.lang_manager.get("connection_disconnected"))
        logging.debug("Sender disconnected manually")
    def toggle_pause(self):
        if self.sender_app:
            if self.pause_btn.text() in ["Pause", "Пауза", "Кідірту"]:
                self.sender_app.pause_transfer()
                self.pause_btn.setText(self.lang_manager.get("resume"))
            else:
                self.sender_app.resume_transfer()
                self.pause_btn.setText(self.lang_manager.get("pause"))
    def stop_sender_transfer(self):
        if self.sender_app:
            self.sender_app.stop_transfer()
            self.stop_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.pause_btn.setText(self.lang_manager.get("pause"))
            self.send_btn.setEnabled(True)
            for row in range(self.file_table.rowCount()):
                status_item = self.file_table.item(row, 3)
                if status_item:
                    text = status_item.text().lower()
                    if "sending" in text or "resuming" in text:
                        self.file_table.setItem(row, 3, QTableWidgetItem(self.lang_manager.get("status_pending")))
                        for col in range(self.file_table.columnCount()):
                            cell = self.file_table.item(row, col)
                            if cell:
                                cell.setBackground(Qt.GlobalColor.transparent)
    def stop_receiver_transfer(self):
        if self.receiver_app:
            self.receiver_app.stop_transfer()
            self.stop_recv_btn.setEnabled(False)
            self.pause_recv_btn.setEnabled(False)
    def toggle_receiver_pause(self):
        if self.receiver_app:
            if self.pause_recv_btn.text() in ["Pause", "Пауза", "Кідірту"]:
                self.receiver_app.pause_transfer()
                self.pause_recv_btn.setText(self.lang_manager.get("resume"))
            else:
                self.receiver_app.resume_transfer()
                self.pause_recv_btn.setText(self.lang_manager.get("pause"))
    def start_receive_clicked(self):
        try:
            port = int(self.listen_port.text() or "5000")
            if self.receiver_app:
                QMessageBox.warning(self, "Already Receiving", "Receiver is already running.")
                return
            self.receiver_app = P2PApp('receive', port=port, compress=True, save_dir=self.save_dir)
            self._connect_receiver_signals(self.receiver_app)
            threading.Thread(target=self.receiver_app.start, daemon=True).start()
            self.start_receive_btn.setEnabled(False)
            self.stop_receive_btn.setEnabled(True)
            local_ip = get_local_ip("8.8.8.8")
            QMessageBox.information(self, "Receiver", f"Listening on {local_ip}:{port}\nAnnouncing presence for discovery.")
            self.receiver_info_label.setText(f"Receiver Active. Listening on {local_ip}:{port}")
            logging.debug(f"Receiver started on port {port}, IP {local_ip}")
        except ValueError:
            QMessageBox.warning(self, self.lang_manager.get("msg_invalid_port"), self.lang_manager.get("msg_invalid_port_body"))
            logging.error("Invalid port for receiver")
        except Exception as e:
            self.show_error(str(e))
            logging.error(f"Receiver start error: {e}")
    def stop_receiving(self):
        try:
            if self.receiver_app:
                self.receiver_app.stop()
                self.receiver_app = None
            self.start_receive_btn.setEnabled(True)
            self.stop_receive_btn.setEnabled(False)
            QMessageBox.information(self, self.lang_manager.get("msg_stopped"), self.lang_manager.get("msg_stopped_body"))
            self.receiver_info_label.setText(self.lang_manager.get("no_incoming"))
            logging.debug("Receiver stopped")
        except Exception as e:
            self.show_error(str(e))
            logging.error(f"Stop receiver error: {e}")
    def on_incoming_connection(self, sender_name, addr):
        self.receiver_info_label.setText(f"Incoming request from {sender_name} ({addr[0]})")
        logging.debug(f"Incoming connection from {sender_name} ({addr[0]})")
    def on_connection_request(self, sender_name, p2p_app):
        print(f"DEBUG: on_connection_request called for {sender_name}")
        logging.debug(f"DEBUG: on_connection_request called for {sender_name}")
        try:
            start_time = time.time()
            client_socket = p2p_app._pending_client
            if self.auto_accept_checkbox.isChecked():
                logging.debug("Auto-accept is CHECKED")
                try:
                    client_socket.sendall(b"P2P_ACCEPT")
                    self.receiver_info_label.setText(f"Auto-accepted connection from {sender_name}")
                    logging.debug(f"Auto-accepted connection from {sender_name} in {time.time() - start_time:.2f}s")
                    p2p_app.transfer_ready.emit(client_socket)
                    return
                except Exception as e:
                    logging.error(f"Failed to send P2P_ACCEPT: {e}")
                    raise
            
            logging.debug("Show connection dialog...")
            self.showNormal() # Ensure window is not minimized
            self.activateWindow()
            self.raise_()
            
            msg_box = TimedMessageBox(timeout_ms=10000, parent=self)
            msg_box.setWindowTitle(self.lang_manager.get("msg_incoming_conn"))
            msg_box.setText(self.lang_manager.get("msg_incoming_conn_body").format(sender_name))
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg_box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
            
            print("DEBUG: Executing message box")
            ans = msg_box.exec()
            print(f"DEBUG: Message box result: {ans}")
            
            response_time = time.time() - start_time
            if ans == QMessageBox.StandardButton.Yes:
                try:
                    client_socket.sendall(b"P2P_ACCEPT")
                    self.receiver_info_label.setText(f"Accepted connection from {sender_name}")
                    logging.debug(f"Accepted connection from {sender_name} in {response_time:.2f}s")
                    p2p_app.transfer_ready.emit(client_socket)
                except Exception as e:
                    logging.error(f"Failed to send P2P_ACCEPT: {e}")
                    raise
            else:
                try:
                    client_socket.sendall(b"P2P_DENY")
                    client_socket.close()
                    self.receiver_info_label.setText(f"Denied connection from {sender_name}")
                    logging.debug(f"Denied connection from {sender_name} in {response_time:.2f}s")
                except Exception as e:
                    logging.error(f"Failed to send P2P_DENY: {e}")
                    raise
        except Exception as e:
            try:
                client_socket.sendall(b"P2P_DENY")
                client_socket.close()
            except Exception:
                pass
            self.show_error(str(e))
            logging.error(f"Connection request error: {e}")
    def on_transfer_ready(self, client_socket):
        if self.receiver_app:
            self.stop_recv_btn.setEnabled(True)
            self.pause_recv_btn.setEnabled(True)
            threading.Thread(target=self.receiver_app.start_transfer, args=(client_socket,), daemon=True).start()
            logging.debug("Transfer initiated after handshake")
    def on_sender_transfer_completed(self):
        self.connection_status_label.setText(self.lang_manager.get("connection_transfer_complete"))
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        msg_complete = self.lang_manager.get("connection_transfer_complete")
        QMessageBox.information(self, "Success", msg_complete)
        self.show_notification("Transfer Complete", msg_complete)
        self.progress.setValue(0)
        self.progress_label.setText("Progress: 0%")
        self.stats_label.setText("Speed: - | ETA: -")
        logging.debug("Sender transfer completed")
    def on_receiver_transfer_completed(self):
        self.receiver_info_label.setText("Transfer complete. Ready for next transfer.")
        self.stop_recv_btn.setEnabled(False)
        self.pause_recv_btn.setEnabled(False)
        self.pause_recv_btn.setText(self.lang_manager.get("pause"))
        self.show_notification("Transfer Complete", "Incoming files received successfully!")
        logging.debug("Receiver transfer completed")
    def on_transfer_permission_requested(self, num_files, client_socket):
        """Ask user for permission to receive files."""
        try:
            if self.auto_accept_checkbox.isChecked():
                logging.debug(f"Auto-accepting transfer of {num_files} file(s)")
                self.receiver_info_label.setText(f"Auto-accepted transfer of {num_files} file(s)")
                if self.receiver_app:
                    self.receiver_app.submit_permission_response(client_socket, True)
                return
            file_text = "file" if num_files == 1 else "files"
            msg_box = TimedMessageBox(timeout_ms=15000, parent=self)
            msg_box.setWindowTitle(self.lang_manager.get("msg_file_request"))
            msg_box.setText(self.lang_manager.get("msg_file_request_body").format(num_files, file_text))
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            ans = msg_box.exec()
            approved = (ans == QMessageBox.StandardButton.Yes)
            if approved:
                self.receiver_info_label.setText(f"Receiving {num_files} {file_text}...")
                logging.debug(f"User approved transfer of {num_files} file(s)")
            else:
                self.receiver_info_label.setText(f"Denied transfer of {num_files} {file_text}")
                logging.debug(f"User denied transfer of {num_files} file(s)")
            if self.receiver_app:
                self.receiver_app.submit_permission_response(client_socket, approved)
        except Exception as e:
            logging.error(f"Transfer permission error: {e}")
            self.show_error(str(e))
    def on_connection_status(self, msg):
        if not msg:
            return
        logging.debug(f"Connection status: {msg}")
        if any(k in msg for k in ("Receiver", "Incoming", "Accepted", "Denied")):
             self.receiver_info_label.setText(msg)
             if "Receiver listening" in msg:
                 return
        if any(k in msg for k in ("Connected to", "Disconnect", "Connection failed", "rejected")):
            self.connection_status_label.setText(f"Connection: {msg}")
            if "Connected to" in msg:
                self.send_btn.setEnabled(True)
                self.disconnect_btn.setEnabled(True)
                self.connect_btn.setEnabled(False)
                self.search_btn.setEnabled(False)
            elif "Disconnected" in msg or "Connection failed" in msg:
                if self.sender_app:
                     self.send_btn.setEnabled(False)
                     self.stop_btn.setEnabled(False)
                     self.pause_btn.setEnabled(False)
                     self.disconnect_btn.setEnabled(False)
                     self.connect_btn.setEnabled(True)
                     self.search_btn.setEnabled(True)
                     self.selected_peer_label.setText("Selected: none")
        if any(k in msg.lower() for k in ("connected", "disconnected", "rejected", "error")):
             if "Receiver listening" not in msg:
                 pass
    def _connect_sender_signals(self, app_instance):
        app_instance.progress_updated.connect(self.update_sender_progress)
        app_instance.file_status.connect(self.update_sender_file_status)
        app_instance.file_progress.connect(self.update_sender_file_progress)
        app_instance.error_occurred.connect(self.show_error)
        app_instance.connection_status.connect(self.on_connection_status)
        # app_instance.chat_received.connect(self.on_chat_received)
        app_instance.transfer_stats.connect(self.update_sender_stats)
        app_instance.transfer_completed.connect(self.on_sender_transfer_completed)
    def _connect_receiver_signals(self, app_instance):
        app_instance.progress_updated.connect(self.update_receiver_progress)
        app_instance.file_status.connect(self.update_receiver_file_status)
        app_instance.file_progress.connect(self.update_receiver_file_progress)
        app_instance.error_occurred.connect(self.show_error)
        app_instance.connection_status.connect(self.on_connection_status)
        app_instance.incoming_connection.connect(self.on_incoming_connection)
        # app_instance.chat_received.connect(self.on_chat_received)
        app_instance.transfer_stats.connect(self.update_receiver_stats)
        app_instance.connection_requested.connect(self.on_connection_request)
        app_instance.transfer_ready.connect(self.on_transfer_ready)
        app_instance.transfer_completed.connect(self.on_receiver_transfer_completed)
        app_instance.transfer_permission_requested.connect(self.on_transfer_permission_requested)
        app_instance.file_metadata.connect(self.update_receiver_file_metadata)
    def update_receiver_file_metadata(self, filename, size_bytes):
        """Update file size in the receiving table."""
        base = os.path.basename(filename)
        base_sanitized = sanitize_filename(base)
        self._add_to_received_files(filename)
        size_mb = size_bytes / (1024 * 1024)
        for row in range(self.received_files_table.rowCount()):
            item = self.received_files_table.item(row, 0)
            if item:
                table_name = item.text()
                table_sanitized = sanitize_filename(table_name)
                if table_sanitized == base_sanitized:
                    self.received_files_table.setItem(row, 1, QTableWidgetItem(f"{size_mb:.2f}"))
                    break
    def update_sender_progress(self, value):
        self.progress.setValue(value)
        self.progress_label.setText(f"Progress: {value}%")
        if value >= 100:
             self.stats_label.setText("Speed: - | ETA: -")

    def update_sender_stats(self, speed, eta):
        self.stats_label.setText(f"Speed: {speed} | ETA: {eta}")

    def update_receiver_progress(self, value):
        self.receiver_progress.setValue(value)
        self.receiver_progress_label.setText(f"Progress: {value}%")
        if value >= 100:
             self.receiver_stats_label.setText("Speed: - | ETA: -")

    def update_receiver_stats(self, speed, eta):
        self.receiver_stats_label.setText(f"Speed: {speed} | ETA: {eta}")
    def update_sender_file_progress(self, filename, percent):
        base = os.path.basename(filename)
        base_sanitized = sanitize_filename(base)
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item:
                table_name = item.text()
                table_sanitized = sanitize_filename(table_name)
                # Match exact or with .zip (for folders that get zipped)
                if table_sanitized == base_sanitized or \
                   f"{table_sanitized}.zip" == base_sanitized:
                    self.file_table.setItem(row, 3, QTableWidgetItem(f"{percent}%"))
                    break
    def update_receiver_file_progress(self, filename, percent):
        base = os.path.basename(filename)
        base_sanitized = sanitize_filename(base)
        for row in range(self.received_files_table.rowCount()):
            item = self.received_files_table.item(row, 0)
            if item:
                table_name = item.text()
                table_sanitized = sanitize_filename(table_name)
                # Match exact or with .zip (for folders that get zipped)
                if table_sanitized == base_sanitized or \
                   f"{table_sanitized}.zip" == base_sanitized:
                    self.received_files_table.setItem(row, 3, QTableWidgetItem(f"{percent}%"))
                    break
    def update_sender_file_status(self, filename, status):
        base = os.path.basename(filename)
        base_sanitized = sanitize_filename(base)
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item:
                table_name = item.text()
                table_sanitized = sanitize_filename(table_name)
                # Match exact or with .zip (for folders that get zipped)
                if table_sanitized == base_sanitized or \
                   f"{table_sanitized}.zip" == base_sanitized:
                    status_widget = QTableWidgetItem(status)
                    if status.lower() in ("sent", "complete"):
                        status_widget.setBackground(Qt.GlobalColor.darkGreen)
                        status_widget.setData(Qt.ItemDataRole.UserRole, "status_success")
                    elif status == "Pending":
                        status_widget.setData(Qt.ItemDataRole.UserRole, "status_pending")
                    self.file_table.setItem(row, 3, status_widget)

                    # Log history
                    if status.lower() in ("sent", "complete"):
                        try:
                            peer = self.selected_peer_label.text().replace(self.lang_manager.get("selected_prefix"), "")
                            size_mb = self.file_table.item(row, 1).text()
                            self.log_history_entry("Send", base, size_mb, peer, "Success")
                        except Exception as e:
                            logging.error(f"Failed to log sender history: {e}")
                    break
    def update_receiver_file_status(self, filename, status):
        base = os.path.basename(filename)
        base_sanitized = sanitize_filename(base)
        if status.lower() == "receiving":
            self._add_to_received_files(filename)
            self.receiver_info_label.setText(f"Receiving {base}")
        for row in range(self.received_files_table.rowCount()):
            item = self.received_files_table.item(row, 0)
            if item:
                table_name = item.text()
                table_sanitized = sanitize_filename(table_name)
                if table_sanitized == base_sanitized:
                    status_widget = QTableWidgetItem(status)
                    if status.lower() in ("received", "complete"):
                         status_widget.setBackground(Qt.GlobalColor.darkGreen)
                         status_widget.setData(Qt.ItemDataRole.UserRole, "status_success")
                    elif status.lower() == "receiving":
                         status_widget.setData(Qt.ItemDataRole.UserRole, "status_receiving")
                    
                    self.received_files_table.setItem(row, 3, status_widget)
                    
                    if status.lower() in ("received", "complete"):
                        # Log history
                        try:
                            # Attempt to parse sender IP from label or store in a variable
                            peer = "Sender" # Simplified
                            size_mb = self.received_files_table.item(row, 1).text()
                            self.log_history_entry("Receive", base, size_mb, peer, "Success")
                        except Exception as e:
                             logging.error(f"Failed to log receiver history: {e}")
                    break
    def _add_to_received_files(self, filename):
        """Add file to received files table if not already there."""
        base = os.path.basename(filename)
        base_sanitized = sanitize_filename(base)
        for row in range(self.received_files_table.rowCount()):
            item = self.received_files_table.item(row, 0)
            if item:
                table_sanitized = sanitize_filename(item.text())
                if table_sanitized == base_sanitized:
                    return
        row = self.received_files_table.rowCount()
        self.received_files_table.insertRow(row)
        file_path = os.path.join(self.save_dir, base) if self.save_dir else base
        try:
            size_mb = 0
            self.received_files_table.setItem(row, 0, QTableWidgetItem(base))
            self.received_files_table.setItem(row, 1, QTableWidgetItem(f"{size_mb:.2f}"))
            self.received_files_table.setItem(row, 2, QTableWidgetItem(file_path))
            
            status_item = QTableWidgetItem(self.lang_manager.get("status_receiving"))
            status_item.setData(Qt.ItemDataRole.UserRole, "status_receiving")
            self.received_files_table.setItem(row, 3, status_item)
        except Exception as e:
            logging.error(f"Error adding file to received files table: {e}")
    def show_error(self, message):
        if not message:
            return
        if "decrypt" in message.lower():
            message = "Encryption key mismatch or invalid data."
        elif "no files selected" in message.lower():
            message = "No files selected to send."
        QMessageBox.warning(self, "Error", message)
        logging.error(f"Error shown: {message}")
    def choose_save_folder(self):
        d = QFileDialog.getExistingDirectory(self, self.lang_manager.get("set_save_folder"))
        if d:
            self.save_dir = d
            self.settings_manager.set("save_dir", d)
            self.update_ui_text()
            QMessageBox.information(self, "Success", f"Save folder set to:\n{d}")
            
            # Notify Web Server of change
            if hasattr(self, 'web_thread') and self.web_thread and self.web_thread.isRunning():
                self.web_thread.update_directory(self.save_dir)
            if self.receiver_app:
                self.receiver_app.set_save_dir(d)
            logging.debug(f"Save folder set to: {d}")
            
            # Immediately update folder info for Mobile tab
            self.update_folder_info()
    def show_sender_file_context_menu(self, position):
        """Show context menu for sender file table."""
        self._show_file_context_menu(self.file_table, position, is_sender=True)

    def show_receiver_file_context_menu(self, position):
        """Show context menu for receiver file table."""
        self._show_file_context_menu(self.received_files_table, position, is_sender=False)

    def show_history_context_menu(self, position):
        """Show context menu for history table."""
        self._show_file_context_menu(self.history_table, position, is_history=True)

    def show_mobile_context_menu(self, position):
         """Show context menu for mobile history table."""
         self._show_file_context_menu(self.mobile_history_table, position, is_mobile=True)

    def _show_file_context_menu(self, table_widget, position, is_sender=False, is_history=False, is_mobile=False):
        menu = QMenu()
        open_action = menu.addAction("Open")
        props_action = menu.addAction("Properties")
        menu.addSeparator()
        
        # Delete Action
        del_text = self.lang_manager.get("msg_remove_file")
        if not is_sender and not is_history:
             del_text += " (List)"
        delete_list_action = menu.addAction(del_text)
        
        delete_disk_action = None
        if not is_sender and not is_history and not is_mobile: 
             # Receiver table allows disk deletion
             delete_disk_action = menu.addAction("Delete from Disk")

        action = menu.exec(table_widget.viewport().mapToGlobal(position))
        
        if not action: return

        selected_rows = table_widget.selectionModel().selectedRows()
        if not selected_rows: return
        row = selected_rows[0].row()
        
        # Determine File Path
        filepath = None
        if is_sender:
             if row < len(self.filenames):
                 filepath = self.filenames[row]
        elif is_history:
             # History: Col 2 is filename, we don't store full path clearly everywhere but for 'Upload' we might
             # For P2P history check logic. 
             # Current history table columns: Time, Type, Filename, Size, Peer, Status. 
             # We rely on finding it in Download/Shared folder if possible.
             filename = table_widget.item(row, 2).text()
             # Best guess search in save_dir or Downloads
             guess_path = os.path.join(self.save_dir, filename)
             if os.path.exists(guess_path): filepath = guess_path
        elif is_mobile:
             # Mobile: Type, File, Size, Time.
             # FIX: Retrieve stored full path from UserRole
             file_item = table_widget.item(row, 1)
             filepath = file_item.data(Qt.ItemDataRole.UserRole)
             if not filepath:
                 # Fallback to simple join if old history
                 filename = file_item.text()
                 filepath = os.path.join(self.save_dir, filename)
        else:
             # Receiver
             # Columns: Filename, Size, Path, Status. Path is Col 2.
             path_item = table_widget.item(row, 2)
             if path_item: filepath = path_item.text()

        if action == open_action:
             print(f"📂 Attempting to open: {filepath}")
             if filepath and os.path.exists(filepath):
                 self.open_file_in_os(filepath)
             else:
                 print(f"❌ File not found: {filepath}")
                 QMessageBox.warning(self, "Error", f"File not found: {filepath}")
        
        elif action == props_action:
             self.show_file_properties(filepath, table_widget, row)

        elif action == delete_list_action:
             if is_sender:
                 self.remove_selected_file_sender()
             elif is_history:
                 table_widget.removeRow(row)
                 # Note: Ideally remove from underlying list too if one exists
             elif is_mobile:
                 table_widget.removeRow(row)
                 self.save_mobile_history()
             else: # Receiver
                 self.remove_selected_file_receiver()
        
        elif action == delete_disk_action:
             if filepath and os.path.exists(filepath):
                 reply = QMessageBox.question(self, "Delete File", f"Are you sure you want to PERMANENTLY delete '{os.path.basename(filepath)}' from disk?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                 if reply == QMessageBox.StandardButton.Yes:
                     try:
                         os.remove(filepath)
                         if not is_sender: table_widget.removeRow(row)
                         QMessageBox.information(self, "Deleted", "File deleted successfully.")
                     except Exception as e:
                         QMessageBox.critical(self, "Error", f"Failed to delete: {e}")

    def open_file_in_os(self, filepath):
        try:
            if filepath:
                filepath = os.path.normpath(filepath)
                os.startfile(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file: {e}")

    def show_file_properties(self, filepath, table, row):
        name = "Unknown"
        size = "Unknown"
        path = filepath or "Unknown"
        
        if filepath and os.path.exists(filepath):
            name = os.path.basename(filepath)
            size_mb = os.path.getsize(filepath) / (1024*1024)
            size = f"{size_mb:.2f} MB"
        else:
            # Fallback to table data if file missing
            # Logic depends on table, simpler to just say "File not found on disk"
            pass

        info = f"Name: {name}\nPath: {path}\nSize: {size}"
        QMessageBox.information(self, "Properties", info)

    def remove_selected_file_sender(self):
        """Remove selected file from sender file table."""
        selected_rows = self.file_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if row < len(self.filenames):
            # No confirmation for simple list removal, or keep it short
            self.file_table.removeRow(row)
            del self.filenames[row]

    def remove_selected_file_receiver(self):
        """Remove selected file from receiver file table."""
        selected_rows = self.received_files_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        self.received_files_table.removeRow(row)
    def on_app_refresh(self):
        """Reset the application state and UI."""
        logging.info("Refreshing application state...")
        self.receiver_list.clear()
        self.file_table.setRowCount(0)
        self.received_files_table.setRowCount(0)
        self.filenames = []
        self.selected_peer_label.setText("Selected: none")
        self.connection_status_label.setText("Connection: Disconnected")
        self.receiver_info_label.setText("No incoming requests yet.")
        self.file_btn.setEnabled(True)
        self.connect_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        if self.sender_app:
            self.sender_app.stop()
            self.sender_app = None
        QMessageBox.information(self, self.lang_manager.get("msg_app_refreshed"), self.lang_manager.get("msg_app_refreshed_body"))

    def populate_history_table(self):
        self.history_table.setRowCount(0)
        history = self.history_manager.get_history()
        for entry in history:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            self.history_table.setItem(row, 0, QTableWidgetItem(entry.get("timestamp", "")))
            
            direction = entry.get("direction", "")
            direction_display = self.lang_manager.get("direction_send") if direction == "Send" else self.lang_manager.get("direction_receive")
            self.history_table.setItem(row, 1, QTableWidgetItem(direction_display))
            
            self.history_table.setItem(row, 2, QTableWidgetItem(entry.get("filename", "")))
            self.history_table.setItem(row, 3, QTableWidgetItem(str(entry.get("size_mb", ""))))
            
            peer = entry.get("peer", "")
            if peer == "Sender":
                peer = self.lang_manager.get("peer_sender")
            self.history_table.setItem(row, 4, QTableWidgetItem(peer))
            
            status = entry.get("status", "")
            if status == "Success":
                 status = self.lang_manager.get("status_success")
            elif status == "Error":
                 status = self.lang_manager.get("status_error")
            self.history_table.setItem(row, 5, QTableWidgetItem(status))

    def log_history_entry(self, direction, filename, size_mb, peer, status):
        self.history_manager.add_entry(direction, filename, size_mb, peer, status)
        # Add to table directly to avoid reload? Or just reload
        # Reloading is safer for sorting order
        self.populate_history_table()
    
    def clear_history(self):
        self.history_manager.clear_history()
        self.populate_history_table()
        QMessageBox.information(self, self.lang_manager.get("msg_history_cleared"), self.lang_manager.get("msg_history_cleared_body"))

    # Chat related methods removed per user request
    # def send_chat_message(self): ...
    # def on_chat_received(self, sender, message): ...

    @pyqtSlot(QSystemTrayIcon.ActivationReason)
    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def show_notification(self, title, message):
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)


    # def append_chat_message(self, sender, message): ...
        
    def quit_app(self):
        """Actually exit the application."""
        self._is_quitting = True
        self.close()

    def closeEvent(self, event):
        """Minimize to tray on close, or actually quit if requested."""
        if not self._is_quitting:
            event.ignore()
            self.hide()
            self.show_notification("P2P Sharing", "App is still running in the tray.")
            return

        """Ensure threads are stopped and settings saved when window is closed."""
        # Save Settings
        self.settings_manager.set("window_width", self.width())
        self.settings_manager.set("window_height", self.height())
        self.settings_manager.set("window_x", self.x())
        self.settings_manager.set("window_y", self.y())
        self.settings_manager.set("auto_accept", self.auto_accept_checkbox.isChecked())
        
        if self.sender_app:
            self.sender_app.stop()
        if self.receiver_app:
            self.receiver_app.stop()
        
        # Stop Web Server Thread
        if hasattr(self, 'web_thread') and self.web_thread and self.web_thread.isRunning():
            self.web_thread.stop()
            self.web_thread.wait(2000) # Wait up to 2s
            if self.web_thread.isRunning():
                 self.web_thread.terminate()

        if self.md5_worker and self.md5_worker.isRunning():
            self.md5_worker.terminate()
        self.tray_icon.hide()
        event.accept()
        
        # Force exit to ensure all daemon threads (like UDP discovery) are killed
        QApplication.quit()
    def load_mobile_history(self):
        """Load mobile history from JSON."""
        try:
            if os.path.exists("mobile_history.json"):
                with open("mobile_history.json", "r") as f:
                    data = json.load(f)
                    self.mobile_history_table.setRowCount(0)
                    for entry in data:
                         row = self.mobile_history_table.rowCount()
                         self.mobile_history_table.insertRow(row)
                         
                         type_str = entry.get("type", "")
                         type_item = QTableWidgetItem(type_str)
                         # Handle localization for known types
                         if type_str == "Sent to Mobile" or type_str == "mobile_sent":
                             type_item.setText(self.lang_manager.get("mobile_sent"))
                             type_item.setData(Qt.ItemDataRole.UserRole, "mobile_sent")
                         elif type_str == "Mobile Upload" or type_str == "mobile_upload" or "Upload" in type_str:
                             type_item.setText(self.lang_manager.get("mobile_upload"))
                             type_item.setData(Qt.ItemDataRole.UserRole, "mobile_upload")
                         elif type_str == "Mobile Download" or type_str == "mobile_download" or "Download" in type_str:
                             type_item.setText(self.lang_manager.get("mobile_download"))
                             type_item.setData(Qt.ItemDataRole.UserRole, "mobile_download")
                         else:
                             # For others, just leave as is for now, or assume it's data
                             type_item.setData(Qt.ItemDataRole.UserRole, type_str)
                             
                         self.mobile_history_table.setItem(row, 0, type_item)
                         
                         filename_item = QTableWidgetItem(entry.get("file", ""))
                         # FIX: Restore full path
                         full_path = entry.get("path", "")
                         if full_path:
                             filename_item.setData(Qt.ItemDataRole.UserRole, full_path)
                         
                         self.mobile_history_table.setItem(row, 1, filename_item)
                         self.mobile_history_table.setItem(row, 2, QTableWidgetItem(entry.get("size", "")))
                         self.mobile_history_table.setItem(row, 3, QTableWidgetItem(entry.get("time", "")))
        except Exception as e:
            print(f"Failed to load mobile history: {e}")

    def save_mobile_history(self):
        """Save mobile history to JSON."""
        data = []
        try:
            for i in range(self.mobile_history_table.rowCount()):
                type_item = self.mobile_history_table.item(i, 0)
                type_val = type_item.data(Qt.ItemDataRole.UserRole)
                if not type_val: type_val = type_item.text() # Fallback
                
                # FIX: Retrieve full path
                file_item = self.mobile_history_table.item(i, 1)
                full_path = file_item.data(Qt.ItemDataRole.UserRole)
                
                data.append({
                    "type": type_val,
                    "file": file_item.text(),
                    "path": full_path if full_path else "",
                    "size": self.mobile_history_table.item(i, 2).text(),
                    "time": self.mobile_history_table.item(i, 3).text(),
                })
            with open("mobile_history.json", "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Failed to save mobile history: {e}")

    def clear_mobile_history(self):
        self.mobile_history_table.setRowCount(0)
        self.save_mobile_history()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\nForce closed by user (KeyboardInterrupt).")
        sys.exit(0)