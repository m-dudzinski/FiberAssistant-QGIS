import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget, QMessageBox
from qgis.PyQt.QtCore import pyqtSignal

from ..core.settings_manager import SettingsManager

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'ui/scope_selection_widget.ui'))


class ScopeSelectionWidget(QWidget, FORM_CLASS):
    scope_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        """Constructor."""
        super(ScopeSelectionWidget, self).__init__(parent)
        self.setupUi(self)
        self.settings_manager = SettingsManager()

        self.warning_label.hide()  # Initially hide the warning

        self.disable_scope_checkbox.stateChanged.connect(self._on_disable_scope_changed)
        self.scope_combobox.currentIndexChanged.connect(self._on_combobox_selection_changed)
        self.refresh_button.clicked.connect(self._on_refresh_button_clicked)

        self._load_settings()

    def _load_settings(self):
        scoping_disabled = self.settings_manager.get_setting('disable_scoping', False)
        self.disable_scope_checkbox.setChecked(scoping_disabled)
        self._update_ui_state(scoping_disabled)

    def _on_disable_scope_changed(self, state):
        is_checked = state == 2  # Checked state

        if is_checked:
            reply = QMessageBox.warning(self, "Potwierdź wyłączenie ograniczenia",
                                        "UWAGA! Wyłączenie ograniczenia zakresem zadania może spowodować zawieszenie programu lub utratę niezapisanych danych, zwłaszcza przy pracy na dużych zbiorach danych. Czy na pewno chcesz kontynuować?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.settings_manager.set_setting('disable_scoping', True)
                self._update_ui_state(True)
            else:
                self.disable_scope_checkbox.setChecked(False)  # Revert checkbox state
        else:
            self.settings_manager.set_setting('disable_scoping', False)
            self._update_ui_state(False)

    def _update_ui_state(self, scoping_disabled):
        if scoping_disabled:
            self.scope_combobox.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.warning_label.show()
            self.scope_changed.emit("DISABLED")  # Emit a special value when disabled
        else:
            self.scope_combobox.setEnabled(True)
            self.refresh_button.setEnabled(True)
            self.warning_label.hide()
            self._on_combobox_selection_changed(self.scope_combobox.currentIndex())

    def _on_combobox_selection_changed(self, index):
        if self.scope_combobox.isEnabled():
            self.scope_changed.emit(self.scope_combobox.currentText())

    def _on_refresh_button_clicked(self):
        # This method should be overridden or connected to external logic
        # to populate the combobox with actual scope values.
        # For now, we'll just log a message.
        print("Refresh button clicked - implement scope population logic here.")
        # Example: self.populate_scopes(some_list_of_scopes)

    def populate_scopes(self, scopes: list):
        self.scope_combobox.clear()
        if scopes:
            self.scope_combobox.addItems(scopes)
        else:
            self.scope_combobox.addItem("Brak dostępnych zakresów")
            self.scope_combobox.setEnabled(False)
            self.refresh_button.setEnabled(False)

    def get_selected_scope(self):
        if self.disable_scope_checkbox.isChecked():
            return "DISABLED"
        return self.scope_combobox.currentText()