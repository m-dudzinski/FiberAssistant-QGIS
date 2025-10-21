
import datetime

class Logger:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Logger, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'full_log_widget'):  # Avoid reinitialization
            return
        self.full_log_widget = None
        self.user_message_widget = None

    def set_full_log_widget(self, widget):
        self.full_log_widget = widget

    def set_user_message_widget(self, widget):
        self.user_message_widget = widget

    def log_user(self, message):
        """Logs a message to the user-facing message widget."""
        if self.user_message_widget:
            timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
            self.user_message_widget.append(f"{timestamp} {message}")

    def log_dev(self, functionality, tab_index, role, description):
        """Logs a detailed message for developers to the full log console."""
        if self.full_log_widget:
            timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
            log_entry = f"{timestamp} F: {functionality} - Z: {tab_index} - R: {role} - D: {description}"
            self.full_log_widget.append(log_entry)

    def log(self, level, user_message, full_log_message=None, function_name=None, event_info=None):
        """Original logging method, can be used for general-purpose logs."""
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
        
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
        elif level == "debug":
            emoji = "🐛 "

        final_full_log_message = full_log_message if full_log_message else user_message
        
        full_console_details = ""
        if function_name:
            full_console_details += f" - F: {function_name}"
        if event_info:
            full_console_details += f" -> E: {event_info}"
        
        full_console_details += f" -> A: {emoji}{final_full_log_message}"

        full_console_output = f'<font color="{color}">{timestamp} - {level.upper()}{full_console_details}</font>'

        if self.full_log_widget:
            self.full_log_widget.append(full_console_output)

    def info(self, user_message, full_log_message=None, function_name=None, event_info=None):
        self.log("info", user_message, full_log_message, function_name, event_info)

    def debug(self, user_message, full_log_message=None, function_name=None, event_info=None):
        self.log("debug", user_message, full_log_message, function_name, event_info)

    def warning(self, user_message, full_log_message=None, function_name=None, event_info=None):
        self.log("warning", user_message, full_log_message, function_name, event_info)

    def error(self, user_message, full_log_message=None, function_name=None, event_info=None):
        self.log("error", user_message, full_log_message, function_name, event_info)

    def success(self, user_message, full_log_message=None, function_name=None, event_info=None):
        self.log("success", user_message, full_log_message, function_name, event_info)

    def export_logs(self, file_path):
        if self.full_log_widget:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.full_log_widget.toPlainText())

logger = Logger()

