import os
from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QWidget

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '../ui/logi_widget.ui'))

class LogiWidget(QWidget, FORM_CLASS):
    export_requested = pyqtSignal()

    def __init__(self, parent=None):
        super(LogiWidget, self).__init__(parent)
        self.setupUi(self)
        self.export_button.clicked.connect(self.export_requested)
        self.clean_logs_button.clicked.connect(self.clear_logs)

    def clear_logs(self):
        self.log_text_edit.clear()
