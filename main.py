import sys

# Some Windows consoles default to a non-UTF-8 codepage (cp1251, cp1252, cp866...).
# The app prints emoji/Unicode in many places; without this, those prints raise
# UnicodeEncodeError and can crash background QThreads (e.g. the web server).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from PyQt6.QtWidgets import QApplication
from main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
