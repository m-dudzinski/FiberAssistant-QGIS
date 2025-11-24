import os
import json
import csv
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (QWidget, QVBoxLayout, QTableWidgetItem, QApplication, 
                                QFileDialog, QHBoxLayout, QFormLayout, QLabel, 
                                QCheckBox, QPushButton, QFrame, QComboBox, QLineEdit,
                                QSplitter, QSizePolicy)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeatureRequest, 
    QgsCoordinateTransform, QgsCoordinateReferenceSystem, QgsWkbTypes,
    QgsRectangle, QgsPointXY
)

from ..core.logger import logger
from .base_widget import FormattedOutputWidget

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '../ui/wyszukiwarka_widget.ui'))

class WyszukiwarkaWidget(QWidget, FORM_CLASS):
    FUNCTIONALITY_NAME = "Wyszukiwarka"

    def __init__(self, iface, parent=None):
        super(WyszukiwarkaWidget, self).__init__(parent)
        self.iface = iface
        self.logger = logger
        self.found_feature_ids = []
        self.setupUi(self)
        self._setup_output_widget()
        self._setup_layouts_and_widgets()
        self._connect_signals()
        self._populate_layers()

    def _setup_output_widget(self):
        self.output_widget = FormattedOutputWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output_widget)
        self.output_widget_placeholder.setLayout(layout)
        self.logger.set_user_message_widget(self.output_widget.output_console)

    def _setup_layouts_and_widgets(self):
        # --- Setup results table ---
        self.results_table.setSortingEnabled(True)

        # --- Add new buttons to results groupbox ---
        self.export_button = QPushButton("Eksportuj do .csv")
        self.export_button.setToolTip("Eksportuj wyniki do pliku CSV (.csv)")

        self.copy_button = QPushButton("Skopiuj do schowka")
        self.copy_button.setToolTip("Kopiuj wszystkie wyniki do schowka")
        
        self.results_groupbox.layout().itemAt(1).insertWidget(1, self.export_button)
        self.results_groupbox.layout().itemAt(1).insertWidget(2, self.copy_button)

        # --- Reorganize search criteria groupbox ---
        main_search_layout = QHBoxLayout()
        
        left_column_widget = QWidget()
        left_column_layout = QFormLayout(left_column_widget)
        left_column_layout.setContentsMargins(0, 0, 5, 0)
        
        left_column_layout.addRow(self.layer_label, self.layer_combobox)
        left_column_layout.addRow(self.attribute_label, self.attribute_combobox)
        left_column_layout.addRow(self.value_label, self.value_lineedit)
        
        self.show_all_layers_checkbox = QCheckBox("Wyświetl na liście wszystkie istniejące warstwy")
        self.show_all_layers_checkbox.setChecked(False)

        checkboxes_layout = QVBoxLayout()
        checkboxes_layout.addWidget(self.exact_match_checkbox)
        checkboxes_layout.addWidget(self.show_all_layers_checkbox)

        search_controls_layout = QHBoxLayout()
        search_controls_layout.addLayout(checkboxes_layout)
        search_controls_layout.addStretch()
        search_controls_layout.addWidget(self.search_button)
        left_column_layout.addRow(search_controls_layout)

        right_column_widget = QWidget()
        right_column_layout = QVBoxLayout(right_column_widget)
        right_column_layout.setContentsMargins(5, 0, 0, 0)

        self.filter_checkbox = QCheckBox("Dodaj filtrowanie obiektów")
        self.filter_checkbox.setToolTip("Zawęź wyszukiwanie do obiektów spełniających dodatkowy warunek.")
        right_column_layout.addWidget(self.filter_checkbox)

        self.filter_attribute_label = QLabel("Wybierz atrybut do filtrowania:")
        self.filter_attribute_combobox = QComboBox()
        self.filter_value_label = QLabel("Wpisz wartość do filtrowania:")
        self.filter_value_lineedit = QLineEdit()
        self.filter_exact_match_checkbox = QCheckBox("Szukaj dokładnego dopasowania w filtrze")
        self.filter_exact_match_checkbox.setChecked(True)

        right_column_layout.addWidget(self.filter_attribute_label)
        right_column_layout.addWidget(self.filter_attribute_combobox)
        right_column_layout.addWidget(self.filter_value_label)
        right_column_layout.addWidget(self.filter_value_lineedit)
        right_column_layout.addWidget(self.filter_exact_match_checkbox)
        right_column_layout.addStretch()

        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)

        main_search_layout.addWidget(left_column_widget, 1)
        main_search_layout.addWidget(separator)
        main_search_layout.addWidget(right_column_widget, 1)

        old_layout = self.search_criteria_groupbox.layout()
        if old_layout is not None:
            QWidget().setLayout(old_layout)
        self.search_criteria_groupbox.setLayout(main_search_layout)

        self._on_toggle_filter(False)

        # --- Final main layout setup with splitter ---
        new_main_layout = QVBoxLayout()
        self.search_criteria_groupbox.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        new_main_layout.addWidget(self.search_criteria_groupbox)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.results_groupbox)
        splitter.addWidget(self.output_widget_placeholder)
        self.results_groupbox.setMinimumHeight(200)
        self.output_widget_placeholder.setMinimumHeight(200)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([400, 200])
        new_main_layout.addWidget(splitter)

        old_main_layout = self.layout()
        if old_main_layout is not None:
            QWidget().setLayout(old_main_layout)
        self.setLayout(new_main_layout)

    def _connect_signals(self):
        self.layer_combobox.currentIndexChanged.connect(self._on_layer_changed)
        self.search_button.clicked.connect(self.run_main_action)
        self.zoom_button.clicked.connect(self._on_zoom_to_feature_clicked)
        self.select_all_button.clicked.connect(self._on_select_all_clicked)
        self.select_selected_button.clicked.connect(self._on_select_selected_clicked)
        self.copy_button.clicked.connect(self._on_copy_to_clipboard_clicked)
        self.export_button.clicked.connect(self._on_export_to_csv_clicked)
        self.filter_checkbox.toggled.connect(self._on_toggle_filter)
        self.show_all_layers_checkbox.toggled.connect(self._populate_layers)

    def _on_toggle_filter(self, checked):
        self.filter_attribute_label.setEnabled(checked)
        self.filter_attribute_combobox.setEnabled(checked)
        self.filter_value_label.setEnabled(checked)
        self.filter_value_lineedit.setEnabled(checked)
        self.filter_exact_match_checkbox.setEnabled(checked)

    def _populate_layers(self):
        self.layer_combobox.clear()

        # Load essential layers list
        essential_layers_names = []
        try:
            json_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'lista_grup_warstw.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            essential_layers_names = data.get("PROJECT_ESSENTIAL_LAYERS", [])
        except Exception as e:
            self.logger.log_user(f"OSTRZEŻENIE: Nie udało się wczytać listy warstw podstawowych z pliku .json: {e}")

        # Get all vector layers from the project
        all_project_layers = [layer for layer in QgsProject.instance().mapLayers().values() if isinstance(layer, QgsVectorLayer)]

        if not self.show_all_layers_checkbox.isChecked():
            # Default view: Show only essential layers
            essential_project_layers = [layer for layer in all_project_layers if layer.name() in essential_layers_names]
            essential_project_layers.sort(key=lambda l: l.name())
            
            for layer in essential_project_layers:
                self.layer_combobox.addItem(layer.name(), layer)
            self.logger.log_dev(self.FUNCTIONALITY_NAME, 0, "FA", f"Wyświetlono {len(essential_project_layers)} warstw podstawowych.")
        else:
            # Expanded view: Show all layers
            essential_project_layers = []
            other_project_layers = []
            
            for layer in all_project_layers:
                if layer.name() in essential_layers_names:
                    essential_project_layers.append(layer)
                else:
                    other_project_layers.append(layer)

            # Sort both lists alphabetically
            essential_project_layers.sort(key=lambda l: l.name())
            other_project_layers.sort(key=lambda l: l.name())

            # Populate combobox
            for layer in essential_project_layers:
                self.layer_combobox.addItem(layer.name(), layer)
            
            if other_project_layers:
                self.layer_combobox.insertSeparator(self.layer_combobox.count())
                for layer in other_project_layers:
                    self.layer_combobox.addItem(layer.name(), layer)
            
            self.logger.log_dev(self.FUNCTIONALITY_NAME, 0, "FA", f"Wyświetlono wszystkie {len(all_project_layers)} warstwy wektorowe.")

    def _on_layer_changed(self, index):
        self.attribute_combobox.clear()
        self.filter_attribute_combobox.clear()
        if index == -1:
            return
        layer = self.layer_combobox.currentData()
        if layer:
            field_names = [field.name() for field in layer.fields()]
            self.attribute_combobox.addItems(field_names)
            self.filter_attribute_combobox.addItems(field_names)

    def run_main_action(self):
        self.output_widget.clear_log()
        self.results_table.setRowCount(0)
        self.found_feature_ids = []

        layer = self.layer_combobox.currentData()
        if not layer:
            self.logger.log_user("BŁĄD: Nie wybrano warstwy lub wskazana warstwa nie istnieje już w projekcie.")
            return

        if layer.featureCount() == 0:
            self.logger.log_user(f"INFORMACJA: Warstwa '{layer.name()}' jest pusta (nie zawiera żadnych obiektów).")
            return

        expression_parts = []

        attribute_name = self.attribute_combobox.currentText()
        search_value = self.value_lineedit.text()

        if not attribute_name:
            self.logger.log_user(f"BŁĄD: Nie wybrano atrybutu do wyszukiwania.")
            return
        if not search_value:
            self.logger.log_user("BŁĄD: Pole z wartością do wyszukania nie może być puste.")
            return

        field = layer.fields().field(attribute_name)
        is_numeric = field.isNumeric()
        search_value_escaped = search_value.replace("'", "''")
        
        main_expr = self._build_expression(
            attribute_name, search_value, search_value_escaped,
            is_numeric, self.exact_match_checkbox.isChecked()
        )
        if main_expr:
            expression_parts.append(f"({main_expr})")
        else:
            return

        if self.filter_checkbox.isChecked():
            filter_attribute = self.filter_attribute_combobox.currentText()
            filter_value = self.filter_value_lineedit.text()

            if not filter_attribute or not filter_value:
                self.logger.log_user("BŁĄD: Atrybut i wartość dla filtrowania wstępnego nie mogą być puste.")
                return
            
            filter_field = layer.fields().field(filter_attribute)
            filter_is_numeric = filter_field.isNumeric()
            filter_value_escaped = filter_value.replace("'", "''")
            
            filter_expr = self._build_expression(
                filter_attribute, filter_value, filter_value_escaped,
                filter_is_numeric, self.filter_exact_match_checkbox.isChecked()
            )
            if filter_expr:
                expression_parts.append(f"({filter_expr})")
            else:
                return

        if not expression_parts:
            self.logger.log_user("BŁĄD: Nie zdefiniowano żadnych kryteriów wyszukiwania.")
            return

        final_expression = " AND ".join(expression_parts)
        self.logger.log_dev(self.FUNCTIONALITY_NAME, 0, "FA", f"Wygenerowane zapytanie: {final_expression}")

        request = QgsFeatureRequest().setFilterExpression(final_expression)
        
        found_features = list(layer.getFeatures(request))
        self.found_feature_ids = [f.id() for f in found_features]

        if not found_features:
            self.logger.log_user("Nie odnaleziono żadnego obiektu spełniającego ustawione kryteria.")
            return

        self.logger.log_user(f"Znaleziono {len(found_features)} dopasowań. Generowanie listy...")
        self._display_results(found_features, attribute_name, layer)

    def _build_expression(self, attr, val, val_escaped, is_numeric, is_exact):
        attr_quoted = f'\"{attr}\"' # Corrected escaping for attribute name
        if is_exact:
            if is_numeric:
                try:
                    float(val)
                    return f'{attr_quoted} = {val}'
                except ValueError:
                    self.logger.log_user(f"BŁĄD: Wartość '{val}' nie jest poprawną liczbą dla atrybutu numerycznego '{attr}'.")
                    return None
            else:
                return f"{attr_quoted} = '{val_escaped}'"
        else:
            if is_numeric:
                self.logger.log_user(f"OSTRZEŻENIE: Wyszukiwanie fragmentu w polu numerycznym '{attr}' może być wolne.")
                return f"to_string({attr_quoted}) LIKE '%{val_escaped}%'"
            else:
                return f"{attr_quoted} LIKE '%{val_escaped}%'"

    def _display_results(self, features, search_attribute, layer):
        self.results_table.setRowCount(len(features))
        
        all_attributes = [field.name() for field in layer.fields()]
        ordered_attributes = []

        if search_attribute in all_attributes:
            ordered_attributes.append(search_attribute)

        if self.filter_checkbox.isChecked():
            filter_attribute = self.filter_attribute_combobox.currentText()
            if filter_attribute in all_attributes and filter_attribute not in ordered_attributes:
                ordered_attributes.append(filter_attribute)
        
        for attr in all_attributes:
            if attr not in ordered_attributes:
                ordered_attributes.append(attr)

        self.results_table.setColumnCount(len(ordered_attributes))
        self.results_table.setHorizontalHeaderLabels(ordered_attributes)

        for row, feature in enumerate(features):
            for col, attr_name in enumerate(ordered_attributes):
                value = feature[attr_name]
                item = QTableWidgetItem(str(value) if value is not None else "")
                if col == 0:
                    item.setData(Qt.UserRole, feature.id())
                self.results_table.setItem(row, col, item)
        
        self.results_table.resizeColumnsToContents()

    def _on_copy_to_clipboard_clicked(self):
        if self.results_table.rowCount() == 0:
            self.logger.log_user("INFORMACJA: Brak wyników do skopiowania.")
            return

        clipboard = QApplication.clipboard()
        header = [self.results_table.horizontalHeaderItem(c).text() for c in range(self.results_table.columnCount())]
        csv_text = "\t".join(header) + "\n"

        for row in range(self.results_table.rowCount()):
            row_data = [self.results_table.item(row, col).text() for col in range(self.results_table.columnCount())]
            csv_text += "\t".join(row_data) + "\n"
        
        clipboard.setText(csv_text)
        self.logger.log_user(f"Skopiowano {self.results_table.rowCount()} wierszy do schowka.")

    def _on_export_to_csv_clicked(self):
        if self.results_table.rowCount() == 0:
            self.logger.log_user("INFORMACJA: Brak wyników do wyeksportowania.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Eksportuj do .csv", "", "Pliki CSV (*.csv)")

        if not path:
            return

        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')

                headers = [self.results_table.horizontalHeaderItem(c).text() for c in range(self.results_table.columnCount())]
                writer.writerow(headers)

                for row in range(self.results_table.rowCount()):
                    row_data = [self.results_table.item(row, col).text() for col in range(self.results_table.columnCount())]
                    writer.writerow(row_data)
            
            self.logger.log_user(f"Pomyślnie wyeksportowano {self.results_table.rowCount()} wierszy do pliku: {path}")

        except Exception as e:
            self.logger.log_user(f"BŁĄD: Wystąpił nieoczekiwany błąd podczas eksportu do pliku .csv: {e}")

    def _on_zoom_to_feature_clicked(self):
        selected_items = self.results_table.selectedItems()
        if not selected_items:
            self.logger.log_user("INFORMACJA: Nie zaznaczono żadnego obiektu na liście wyników.")
            return

        selected_row = selected_items[0].row()
        feature_id_item = self.results_table.item(selected_row, 0)
        feature_id = feature_id_item.data(Qt.UserRole)

        layer = self.layer_combobox.currentData()
        if not layer:
            return

        feature = layer.getFeature(feature_id)
        if not feature.hasGeometry():
            self.logger.log_user("BŁĄD: Wybrany obiekt nie posiada geometrii, nie można go przybliżyć.")
            return

        geom = feature.geometry()
        canvas = self.iface.mapCanvas()

        canvas_crs = canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        if canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
            geom.transform(transform)

        if geom.type() == QgsWkbTypes.LineGeometry:
            # Center on the midpoint of the line first
            centroid = geom.interpolate(geom.length() / 2).asPoint()
            canvas.setCenter(centroid)
        else:
            centroid = geom.centroid().asPoint()
            canvas.setCenter(centroid)

        # Now, set the desired scale
        canvas.zoomScale(250)

        # Finally, refresh the canvas to apply all changes
        canvas.refresh()

        attribute_name = self.attribute_combobox.currentText()
        attribute_value = feature[attribute_name]
        
        display_id = f"(Feature ID: {feature.id()})"
        if 'id' in feature.fields().names():
            id_val = feature['id']
            if id_val is not None:
                display_id = id_val

        self.logger.log_user(f"Przybliżono do obiektu z ID: {display_id} o atrybucie '{attribute_name}' z wartością '{attribute_value}'")

    def _on_select_all_clicked(self):
        if not self.found_feature_ids:
            self.logger.log_user("INFORMACJA: Lista wyników jest pusta. Brak obiektów do zaznaczenia.")
            return
        
        layer = self.layer_combobox.currentData()
        if layer:
            layer.selectByIds(self.found_feature_ids)
            self.logger.log_user(f"Zaznaczono {len(self.found_feature_ids)} obiektów na warstwie '{layer.name()}'.")

    def _on_select_selected_clicked(self):
        selected_items = self.results_table.selectedItems()
        if not selected_items:
            self.logger.log_user("INFORMACJA: Nie zaznaczono żadnego obiektu na liście wyników.")
            return

        selected_ids = set()
        for item in selected_items:
            feature_id_item = self.results_table.item(item.row(), 0)
            selected_ids.add(feature_id_item.data(Qt.UserRole))

        layer = self.layer_combobox.currentData()
        if layer:
            layer.selectByIds(list(selected_ids))
            self.logger.log_user(f"Zaznaczono {len(selected_ids)} obiektów na warstwie '{layer.name()}'.")

    def refresh_data(self):
        self.logger.log_user("Odświeżanie listy warstw...")
        self._populate_layers()
        self.logger.log_user("Lista warstw została zaktualizowana.")