import datetime
from qgis.PyQt.QtWidgets import QWidget, QTextEdit, QVBoxLayout, QApplication

class FormattedOutputWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_first_log = True

        # --- UI Setup ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.output_console = QTextEdit()
        self.output_console.setReadOnly(True)
        layout.addWidget(self.output_console)

    def clear_log(self):
        self.output_console.clear()
        self.is_first_log = True

    def get_text_for_copy(self):
        return self.output_console.toPlainText()

    def log_info(self, message):
        self._log("info", message)

    def log_warning(self, message):
        self._log("warning", message)

    def log_error(self, message):
        self._log("error", message)

    def log_success(self, message):
        self._log("success", message)

    def _log(self, level, message):
        color = "black"
        emoji = ""
        
        if level == "error":
            color = "red"
            emoji = "❌ "
        elif level == "warning":
            color = "orange"
            emoji = "⚠️ "
        elif level == "info":
            color = "blue"
            emoji = "ℹ️ "
        elif level == "success":
            color = "green"
            emoji = "✅ "

        if self.is_first_log:
            timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
            formatted_message = f'<font color="{color}">{timestamp} {emoji}{message}</font>'
            self.is_first_log = False
        else:
            if level == "info":
                color = "black"
            # Indent subsequent messages
            formatted_message = f'<div style="margin-left: 20px; color: {color};">{emoji}{message}</div>'

        self.output_console.append(formatted_message)
