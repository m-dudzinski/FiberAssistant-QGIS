
import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog

from ..core.settings_manager import SettingsManager

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '../ui/settings_dialog.ui'))


class SettingsDialog(QDialog, FORM_CLASS):
    def __init__(self, main_dialog, parent=None):
        """Constructor."""
        super(SettingsDialog, self).__init__(parent)
        self.setupUi(self)
        self.main_dialog = main_dialog

        self.load_settings()

        self.buttonBox.accepted.connect(self.save_and_broadcast)

    def load_settings(self):
        """Load settings and set the state of the checkboxes."""
        settings = SettingsManager()
        self.checkBox_experimental.setChecked(settings.are_experimental_features_enabled())
        self.checkBox_disable_scope.setChecked(settings.is_scope_limitation_disabled())

    def save_and_broadcast(self):
        """Save the current state of the checkboxes and notify the main dialog."""
        settings = SettingsManager()
        settings.set_experimental_features_enabled(self.checkBox_experimental.isChecked())
        settings.set_scope_limitation_disabled(self.checkBox_disable_scope.isChecked())
        
        if self.main_dialog:
            self.main_dialog.broadcast_settings_changed()
