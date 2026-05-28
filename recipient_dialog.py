from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, 
    QPushButton, QLabel, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt

class RecipientSelectionDialog(QDialog):
    """Dialog for selecting which mobile devices should receive shared files."""
    
    def __init__(self, devices, lang_manager, parent=None):
        """
        Args:
            devices: Dict of {ip: {'name': str, 'connected_at': str}}
            lang_manager: LanguageManager instance for translations
            parent: Parent widget
        """
        super().__init__(parent)
        self.devices = devices
        self.lang_manager = lang_manager
        self.selected_recipients = []
        
        self.setWindowTitle(lang_manager.get("recipient_dialog_title"))
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title_label = QLabel(self.lang_manager.get("select_recipients"))
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # "All Devices" checkbox
        self.all_devices_checkbox = QCheckBox(self.lang_manager.get("all_devices"))
        self.all_devices_checkbox.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        self.all_devices_checkbox.stateChanged.connect(self.on_all_devices_changed)
        layout.addWidget(self.all_devices_checkbox)
        
        # Separator
        separator = QLabel()
        separator.setStyleSheet("border-bottom: 1px solid #ccc; margin: 5px 0;")
        layout.addWidget(separator)
        
        # Device list (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: 1px solid #ccc; border-radius: 4px;")
        
        device_widget = QWidget()
        device_layout = QVBoxLayout(device_widget)
        
        self.device_checkboxes = {}
        
        if not self.devices:
            no_devices_label = QLabel(self.lang_manager.get("mobile_no_devices"))
            no_devices_label.setStyleSheet("color: #888; padding: 20px; text-align: center;")
            no_devices_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            device_layout.addWidget(no_devices_label)
        else:
            for ip, info in self.devices.items():
                device_name = info.get('name', 'Unknown')
                connected_at = info.get('connected_at', '')
                
                checkbox = QCheckBox(f"{device_name} ({ip})")
                checkbox.setProperty('ip', ip)
                checkbox.stateChanged.connect(self.on_device_checkbox_changed)
                
                # Add timestamp as tooltip
                if connected_at:
                    checkbox.setToolTip(f"Connected: {connected_at}")
                
                self.device_checkboxes[ip] = checkbox
                device_layout.addWidget(checkbox)
        
        device_layout.addStretch()
        scroll.setWidget(device_widget)
        layout.addWidget(scroll)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton(self.lang_manager.get("btn_cancel"))
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton(self.lang_manager.get("btn_ok"))
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def on_all_devices_changed(self, state):
        """Handle 'All Devices' checkbox state change."""
        is_checked = state == Qt.CheckState.Checked.value
        
        # Disable/enable individual checkboxes
        for checkbox in self.device_checkboxes.values():
            checkbox.setEnabled(not is_checked)
            if is_checked:
                checkbox.setChecked(False)
    
    def on_device_checkbox_changed(self):
        """Handle individual device checkbox state change."""
        # If any device is checked, uncheck "All Devices"
        any_checked = any(cb.isChecked() for cb in self.device_checkboxes.values())
        if any_checked:
            self.all_devices_checkbox.setChecked(False)
    
    def get_selected_recipients(self):
        """Get list of selected recipient IPs or ['*'] for all devices.
        
        Returns:
            List of IP addresses, or ['*'] if "All Devices" is selected
        """
        if self.all_devices_checkbox.isChecked():
            return ['*']
        
        selected = []
        for ip, checkbox in self.device_checkboxes.items():
            if checkbox.isChecked():
                selected.append(ip)
        
        return selected if selected else ['*']  # Default to all if none selected
