import os
import json
from collections import defaultdict
from io import StringIO

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QMessageBox, QSplitter, QGroupBox, QHBoxLayout, 
    QLabel, QComboBox, QPushButton, QRadioButton, QSizePolicy, QSpacerItem, 
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox
)
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeatureRequest,
    QgsSpatialIndex,
    QgsWkbTypes,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsCoordinateTransform
)

from ..core.logger import logger
from .base_widget import FormattedOutputWidget

# --- Helper Functions ---

def _to_excel_col(n):
    """Converts a 1-based integer to an Excel-style column name (A, B, ..., Z, AA, ...)."""
    name = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        name = chr(65 + remainder) + name
    return name

def _get_canonical_geometry(geom):
    """Returns a canonical representation of a LineString or single-part MultiLineString geometry to make it direction-insensitive."""
    
    wkb_type = QgsWkbTypes.flatType(geom.wkbType())

    if wkb_type == QgsWkbTypes.LineString:
        points = geom.asPolyline()
        if points and len(points) > 1:
            if points[0].x() > points[-1].x() or (points[0].x() == points[-1].x() and points[0].y() > points[-1].y()):
                return QgsGeometry.fromPolylineXY(points[::-1])
        return geom

    elif wkb_type == QgsWkbTypes.MultiLineString:
        lines = geom.asMultiPolyline()
        # Handle only single-part MultiLineStrings
        if len(lines) == 1:
            points = lines[0]
            if points and len(points) > 1:
                if points[0].x() > points[-1].x() or (points[0].x() == points[-1].x() and points[0].y() > points[-1].y()):
                    return QgsGeometry.fromMultiPolylineXY([points[::-1]])
        return geom

    return geom

def round_geometry_coords(geom, precision=8):
    if geom.isNull() or geom.isEmpty():
        return geom

    wkb_type = QgsWkbTypes.flatType(geom.wkbType())

    if wkb_type == QgsWkbTypes.Point:
        p = geom.asPoint()
        return QgsGeometry.fromPointXY(QgsPointXY(round(p.x(), precision), round(p.y(), precision)))

    if wkb_type == QgsWkbTypes.LineString:
        line = geom.asPolyline()
        new_line = [QgsPointXY(round(p.x(), precision), round(p.y(), precision)) for p in line]
        return QgsGeometry.fromPolylineXY(new_line)

    if wkb_type == QgsWkbTypes.MultiLineString:
        lines = geom.asMultiPolyline()
        new_lines = []
        for line in lines:
            new_line = [QgsPointXY(round(p.x(), precision), round(p.y(), precision)) for p in line]
            new_lines.append(new_line)
        return QgsGeometry.fromMultiPolylineXY(new_lines)
    
    return geom

# --- Main Widget Container ---

class CzyszczenieWidget(QWidget):
    FUNCTIONALITY_NAME = "Czyszczenie"

    def __init__(self, iface, parent=None):
        super(CzyszczenieWidget, self).__init__(parent)
        self.iface = iface
        self.logger = logger
        self.setLayout(QVBoxLayout())
        self.tab_widget = QTabWidget()
        self.layout().addWidget(self.tab_widget)

        self.duplicates_widget = DuplicatesWidget(iface, self)
        self.invalid_geo_widget = InvalidGeometriesWidget(iface, self)

        self.tab_widget.addTab(self.duplicates_widget, "Usuń duble")
        self.tab_widget.addTab(self.invalid_geo_widget, "Usuń błędne geometrie")

    def get_active_tab_widget(self):
        return self.tab_widget.currentWidget()

    def clear_active_output_widget(self):
        active_widget = self.get_active_tab_widget()
        if active_widget and hasattr(active_widget, 'output_widget'):
            active_widget.output_widget.clear_log()

    def get_active_output_widget_text(self):
        active_widget = self.get_active_tab_widget()
        if active_widget and hasattr(active_widget, 'output_widget'):
            return active_widget.output_widget.get_text_for_copy()
        return ""

    def refresh_data(self):
        active_widget = self.get_active_tab_widget()
        if active_widget and hasattr(active_widget, 'refresh_data'):
            active_widget.refresh_data()

# --- Duplicates Tab Widget ---

class DuplicatesWidget(QWidget):
    FUNCTIONALITY_NAME = "Czyszczenie / Usuń duble"

    def __init__(self, iface, parent=None):
        super(DuplicatesWidget, self).__init__(parent)
        self.iface = iface
        self.logger = logger
        self.feature_map = {}

        self._setup_ui_dynamically()
        self._connect_signals()
        self._populate_initial_data()
        self._setup_initial_state()

    def _setup_ui_dynamically(self):
        main_layout = QVBoxLayout(self)
        
        self.settings_groupbox = QGroupBox("Ustawienia")
        self.settings_groupbox.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        settings_layout = QVBoxLayout(self.settings_groupbox)

        scope_layout = QHBoxLayout()
        scope_layout.addWidget(QLabel("Wybierz zakres ograniczający:"))
        self.zakres_combo_box = QComboBox()
        self.zakres_combo_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        scope_layout.addWidget(self.zakres_combo_box)
        self.refresh_button = QPushButton("Odśwież")
        scope_layout.addWidget(self.refresh_button)
        settings_layout.addLayout(scope_layout)

        layer_layout = QHBoxLayout()
        layer_layout.addWidget(QLabel("Wybierz warstwę do sprawdzenia:"))
        self.layer_combobox = QComboBox()
        self.layer_combobox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layer_layout.addWidget(self.layer_combobox)
        self.show_all_layers_checkbox = QCheckBox("Wyświetl na liście wszystkie istniejące warstwy")
        self.show_all_layers_checkbox.setChecked(False)
        layer_layout.addWidget(self.show_all_layers_checkbox)
        settings_layout.addLayout(layer_layout)

        criteria_groupbox = QGroupBox("Uznaj za dubel, jeśli obiekty mają:")
        criteria_layout = QVBoxLayout(criteria_groupbox)
        self.radio_geom_only = QRadioButton("identyczną geometrię (bez względu na atrybuty)")
        self.radio_geom_only.setChecked(True)
        self.radio_geom_and_attributes = QRadioButton("identyczną geometrię ORAZ identyczne wartości atrybutów (z pominięciem pól 'id' i 'fid')")
        self.reversed_geom_checkbox = QCheckBox("Uznaj za dubel obiekty liniowe, nawet jeśli mają odwróconą kolejność wierzchołków (wolniejsze)")
        self.reversed_geom_checkbox.setChecked(False)
        criteria_layout.addWidget(self.radio_geom_only)
        criteria_layout.addWidget(self.radio_geom_and_attributes)
        criteria_layout.addWidget(self.reversed_geom_checkbox)
        settings_layout.addWidget(criteria_groupbox)

        check_layout = QHBoxLayout()
        check_layout.addStretch()
        self.check_duplicates_button = QPushButton("Sprawdź duplikaty")
        check_layout.addWidget(self.check_duplicates_button)
        settings_layout.addLayout(check_layout)

        self.results_groupbox = QGroupBox("Wyniki")
        results_layout = QVBoxLayout(self.results_groupbox)
        self.results_table = QTableWidget()
        self.results_table.setSortingEnabled(True)
        results_layout.addWidget(self.results_table)

        results_actions_layout = QHBoxLayout()
        results_actions_layout.addStretch()
        self.zoom_to_feature_button = QPushButton("Przybliż do obiektu")
        self.delete_selected_button = QPushButton("Usuń zaznaczone")
        self.delete_all_button = QPushButton("Usuń wszystkie duplikaty (zostaw nr 1)")
        results_actions_layout.addWidget(self.zoom_to_feature_button)
        results_actions_layout.addWidget(self.delete_selected_button)
        results_actions_layout.addWidget(self.delete_all_button)
        results_layout.addLayout(results_actions_layout)

        self.output_widget_placeholder = QWidget()
        self.output_widget = FormattedOutputWidget()
        output_layout = QVBoxLayout(self.output_widget_placeholder)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(self.output_widget)
        self.logger.set_user_message_widget(self.output_widget.output_console)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.results_groupbox)
        splitter.addWidget(self.output_widget_placeholder)
        splitter.setSizes([300, 150])

        main_layout.addWidget(self.settings_groupbox)
        main_layout.addWidget(splitter)

    def _connect_signals(self):
        self.refresh_button.clicked.connect(self.refresh_data)
        self.check_duplicates_button.clicked.connect(self.run_check_action)
        self.delete_all_button.clicked.connect(self.run_delete_all_action)
        self.delete_selected_button.clicked.connect(self.run_delete_selected_action)
        self.zoom_to_feature_button.clicked.connect(self._on_zoom_to_feature_clicked)
        self.results_table.itemSelectionChanged.connect(self._update_button_states)
        self.layer_combobox.currentIndexChanged.connect(self._on_layer_changed)
        self.show_all_layers_checkbox.toggled.connect(self._populate_layers_combobox)

    def refresh_data(self):
        self.output_widget.log_info("Odświeżanie list...")
        self._populate_zakres_combobox()
        self._populate_layers_combobox()
        self.output_widget.log_info("Listy zostały zaktualizowane.")

    def _populate_initial_data(self):
        self._populate_zakres_combobox()
        self._populate_layers_combobox()

    def _setup_initial_state(self):
        self.delete_all_button.setEnabled(False)
        self.delete_selected_button.setEnabled(False)
        self.zoom_to_feature_button.setEnabled(False)

    def _update_button_states(self):
        selected_rows_count = len(self.results_table.selectionModel().selectedRows())
        self.delete_selected_button.setEnabled(selected_rows_count > 0)
        self.zoom_to_feature_button.setEnabled(selected_rows_count == 1)

    def _on_layer_changed(self):
        self._setup_initial_state()
        self.results_table.clearContents()
        self.results_table.setRowCount(0)
        self.feature_map.clear()

    def _is_valid_for_check(self):
        if self.zakres_combo_box.count() == 0: self.output_widget.log_error("Brak dostępnych zakresów. Dodaj warstwę 'zakres_zadania'."); return False
        layer = self.layer_combobox.currentData()
        if not layer: self.output_widget.log_error("Nie wybrano warstwy do sprawdzenia."); return False
        if layer.isEditable(): self.output_widget.log_error(f"Warstwa '{layer.name()}' jest w trybie edycji. Wyłącz tryb edycji, aby kontynuować."); return False
        return True

    def run_check_action(self):
        self.output_widget.clear_log()
        self._setup_initial_state()
        self.results_table.setColumnCount(0); self.results_table.setRowCount(0)
        self.feature_map.clear()

        if not self._is_valid_for_check(): return

        self.output_widget.log_info("Rozpoczynam sprawdzanie duplikatów...")
        self.output_widget.log_warning("UWAGA! Pamiętaj, że kabel i trakt w zakresie zadania jest zliczany, jeśli jego wierzchołek końcowy znajduje się wewnątrz zakresu. Dlatego upewnij się, że kierunek linii jest ustawiony prawidłowo.")

        layer = self.layer_combobox.currentData()
        scope_geom = self.zakres_combo_box.currentData()
        compare_attributes = self.radio_geom_and_attributes.isChecked()
        check_reversed = self.reversed_geom_checkbox.isChecked()

        try:
            index = QgsSpatialIndex(layer.getFeatures())
            intersecting_ids = index.intersects(scope_geom.boundingBox())
            request = QgsFeatureRequest().setFilterFids(intersecting_ids)
            features_in_scope = [f for f in layer.getFeatures(request) if self._is_in_scope(f.geometry(), scope_geom)]

            total_searched = len(features_in_scope)
            self.output_widget.log_info(f"Przeszukano {total_searched} obiektów w zakresie zadania.")

            if not features_in_scope: self.output_widget.log_success("Nie znaleziono żadnych obiektów w podanym zakresie."); return

            geometries = defaultdict(list)
            for feature in features_in_scope:
                geom = feature.geometry()
                if geom and not geom.isEmpty() and geom.isGeosValid():
                    rounded_geom = round_geometry_coords(geom)
                    key_geom = _get_canonical_geometry(rounded_geom) if check_reversed else rounded_geom
                    geometries[key_geom.asWkb()].append(feature)

            duplicate_groups = []
            geometrically_identical_but_different_attrs = 0

            for feature_list in geometries.values():
                if len(feature_list) > 1:
                    if not compare_attributes:
                        duplicate_groups.append(feature_list)
                    else:
                        attr_groups = self._group_by_attributes(feature_list)
                        if len(attr_groups) > 1:
                            max_group_size = max(len(group) for group in attr_groups)
                            geometrically_identical_but_different_attrs += (len(feature_list) - max_group_size)
                        for group in attr_groups:
                            if len(group) > 1: duplicate_groups.append(group)
            
            if not duplicate_groups: 
                self.output_widget.log_success("Nie znaleziono żadnych duplikatów.")
                if compare_attributes and geometrically_identical_but_different_attrs > 0: self.output_widget.log_info(f"Znaleziono {geometrically_identical_but_different_attrs} obiektów o tej samej geometrii, ale innych atrybutach.")
                return

            self._display_results(duplicate_groups, layer)

            num_duplicates = sum(len(group) - 1 for group in duplicate_groups)
            self.output_widget.log_success(f"Znaleziono obiektów zdublowanych: {num_duplicates}")
            if compare_attributes and geometrically_identical_but_different_attrs > 0: self.output_widget.log_info(f"Znaleziono obiektów o tej samej geometrii, ale innych atrybutach: {geometrically_identical_but_different_attrs}")

            self.output_widget.log_warning("<b>UWAGA!</b> Opcja 'Usuń wszystkie duplikaty' pozostawia obiekt z nr 1 w każdej grupie. Jeśli uważasz, że inny obiekt jest prawidłowy, ręcznie zaznacz w tabeli te, które chcesz usunąć i skorzystaj z opcji 'Usuń zaznaczone'.")

            self.delete_all_button.setEnabled(True)
            self._update_button_states()

        except Exception as e:
            self.output_widget.log_error(f"Wystąpił nieoczekiwany błąd: {e}")
            self.logger.log_dev(self.FUNCTIONALITY_NAME, 0, "ERROR", str(e))

    def _display_results(self, duplicate_groups, layer):
        self.results_table.clear()
        self.feature_map.clear()
        fields = layer.fields()
        field_names = fields.names()

        headers = ["Grupa", "Nr w grupie"] + field_names
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)

        row = 0
        for i, group in enumerate(duplicate_groups, 1):
            for j, feature in enumerate(group, 1):
                self.results_table.insertRow(row)
                self.feature_map[row] = feature.id()

                group_item = QTableWidgetItem(_to_excel_col(i)); group_item.setFlags(group_item.flags() & ~Qt.ItemIsEditable)
                self.results_table.setItem(row, 0, group_item)

                num_item = QTableWidgetItem(str(j)); num_item.setFlags(num_item.flags() & ~Qt.ItemIsEditable)
                self.results_table.setItem(row, 1, num_item)

                for k, field_name in enumerate(field_names):
                    attr_val = str(feature[field_name] or "")
                    attr_item = QTableWidgetItem(attr_val); attr_item.setFlags(attr_item.flags() & ~Qt.ItemIsEditable)
                    self.results_table.setItem(row, 2 + k, attr_item)

                row += 1
        
        self.results_table.resizeColumnsToContents()

    def _on_zoom_to_feature_clicked(self):
        selected_rows = self.results_table.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            self.output_widget.log_info("Proszę zaznaczyć dokładnie jeden obiekt na liście.")
            return

        selected_row = selected_rows[0].row()
        feature_id = self.feature_map.get(selected_row)

        if feature_id is None:
            self.output_widget.log_error("Nie można odnaleźć ID obiektu dla zaznaczonego wiersza.")
            return

        layer = self.layer_combobox.currentData()
        if not layer:
            return

        feature = layer.getFeature(feature_id)
        if not feature.hasGeometry():
            self.output_widget.log_error("Wybrany obiekt nie posiada geometrii, nie można go przybliżyć.")
            return

        geom = feature.geometry()
        canvas = self.iface.mapCanvas()

        canvas_crs = canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        if canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
            geom.transform(transform)

        wkb_type = QgsWkbTypes.flatType(geom.wkbType())
        if wkb_type == QgsWkbTypes.LineString or wkb_type == QgsWkbTypes.MultiLineString:
            centroid = geom.interpolate(geom.length() / 2).asPoint()
        else:
            centroid = geom.centroid().asPoint()
        
        canvas.setCenter(centroid)
        canvas.zoomScale(250)
        canvas.refresh()

        self.output_widget.log_info(f"Przybliżono do obiektu o ID: {feature.id()}")

    def run_delete_all_action(self):
        to_delete_ids = []
        for row in range(self.results_table.rowCount()):
            try:
                if int(self.results_table.item(row, 1).text()) > 1:
                    to_delete_ids.append(self.feature_map[row])
            except (ValueError, AttributeError):
                continue

        if not to_delete_ids:
            self.output_widget.log_warning("Brak duplikatów (o numerze > 1) do usunięcia.")
            return
        self._delete_features(to_delete_ids, f"wszystkie {len(to_delete_ids)} znalezione duplikaty (pozostawiając nr 1 w każdej grupie)")

    def run_delete_selected_action(self):
        selected_rows = {index.row() for index in self.results_table.selectedIndexes()}
        if not selected_rows:
            self.output_widget.log_warning("Nie zaznaczono żadnych obiektów w tabeli wyników.")
            return

        selected_ids = [self.feature_map[row] for row in selected_rows]
        self._delete_features(selected_ids, f"{len(selected_ids)} zaznaczone obiekty")

    def _delete_features(self, feature_ids, description):
        if not feature_ids: self.output_widget.log_warning("Brak obiektów do usunięcia."); return

        warning_text = f"Czy na pewno chcesz usunąć {description}? Tej operacji nie można cofnąć."
        if "(pozostawiając nr 1 w każdej grupie)" in description:
            warning_text += "\n\nObiekt z numerem 1 w każdej grupie zostanie zachowany. Jeśli chcesz usunąć inny obiekt, użyj opcji \"Usuń zaznaczone\""

        reply = QMessageBox.warning(self, "Potwierdzenie usunięcia", warning_text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No: self.output_widget.log_info("Operacja usuwania anulowana przez użytkownika."); return

        layer = self.layer_combobox.currentData()
        layer.startEditing()
        layer.deleteFeatures(feature_ids)
        layer.commitChanges()

        self.output_widget.log_success(f"Pomyślnie usunięto {len(feature_ids)} obiektów.")
        self.run_check_action()

    def _populate_zakres_combobox(self):
        self.zakres_combo_box.clear()
        zakres_layer_list = QgsProject.instance().mapLayersByName("zakres_zadania")
        if not zakres_layer_list:
            self.output_widget.log_error("Nie znaleziono warstwy 'zakres_zadania'.")
            return
        
        zakres_layer = zakres_layer_list[0]
        
        scopes = []
        try:
            # Upewnij się, że atrybut 'nazwa' istnieje
            if "nazwa" not in zakres_layer.fields().names():
                self.output_widget.log_error("Warstwa 'zakres_zadania' nie posiada atrybutu 'nazwa'.")
                return

            for feature in zakres_layer.getFeatures():
                # Dodajemy tylko te zakresy, które mają nazwę
                if feature["nazwa"]:
                    scopes.append((feature["nazwa"], feature.geometry()))
        except Exception as e:
            self.output_widget.log_error(f"Błąd podczas wczytywania zakresów: {e}")
            return

        # Sortowanie listy zakresów alfabetycznie po nazwie
        scopes.sort(key=lambda x: x[0])

        # Dodanie posortowanych elementów do comboboxa
        for name, geom in scopes:
            self.zakres_combo_box.addItem(name, geom)

    def _populate_layers_combobox(self):
        self.layer_combobox.clear()

        # Load essential layers list
        essential_layers_names = []
        try:
            json_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'lista_grup_warstw.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            essential_layers_names = data.get("PROJECT_ESSENTIAL_LAYERS", [])
        except Exception as e:
            self.output_widget.log_error(f"OSTRZEŻENIE: Nie udało się wczytać listy warstw podstawowych z pliku .json: {e}")

        # Get all vector layers from the project
        all_project_layers = [layer for layer in QgsProject.instance().mapLayers().values() if isinstance(layer, QgsVectorLayer)]

        if not self.show_all_layers_checkbox.isChecked():
            # Default view: Show only essential layers
            essential_project_layers = [layer for layer in all_project_layers if layer.name() in essential_layers_names]
            essential_project_layers.sort(key=lambda l: l.name())
            
            for layer in essential_project_layers:
                self.layer_combobox.addItem(layer.name(), layer)
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

    def _is_in_scope(self, geom, scope_geom):
        if not geom or not scope_geom or not geom.intersects(scope_geom): return False
        wkb_type = geom.wkbType()
        if wkb_type in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            last_vertex_point = None
            try:
                if wkb_type == QgsWkbTypes.LineString:
                    polyline = geom.asPolyline()
                    if polyline:
                        last_vertex_point = polyline[-1]
                elif wkb_type == QgsWkbTypes.MultiLineString:
                    multi_polyline = geom.asMultiPolyline()
                    if multi_polyline and multi_polyline[-1]:
                        last_vertex_point = multi_polyline[-1][-1]
                
                if last_vertex_point and not QgsGeometry.fromPointXY(last_vertex_point).intersects(scope_geom):
                    return False
            except IndexError:
                return False
        return True

    def _group_by_attributes(self, features):
        attr_groups = defaultdict(list)
        ignore_fields = {'id', 'fid'}
        if not features: return []
        fields_to_compare = [field.name() for field in features[0].fields() if field.name() not in ignore_fields]
        for feature in features:
            try: attr_values = tuple(feature[name] for name in fields_to_compare); attr_groups[attr_values].append(feature)
            except KeyError: continue
        return list(attr_groups.values())

# --- Invalid Geometries Tab Widget (Unchanged) ---

class InvalidGeometriesWidget(QWidget):
    FUNCTIONALITY_NAME = "Czyszczenie / Błędne geometrie"

    def __init__(self, iface, parent=None):
        super(InvalidGeometriesWidget, self).__init__(parent)
        self.iface = iface
        self.logger = logger
        self.feature_map = {}
        self.cable_layers = []

        self._setup_ui_dynamically()
        self._load_layer_groups()
        self._connect_signals()
        self._populate_initial_data()
        self._setup_initial_state()

    def _load_layer_groups(self):
        json_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'lista_grup_warstw.json')
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                layer_groups = json.load(f)
            self.cable_layers = layer_groups.get('CABLE_LAYERS', [])
            self.output_widget.log_info("Pomyślnie wczytano konfigurację grup warstw.")
        except FileNotFoundError:
            self.cable_layers = []
            self.output_widget.log_error(f"Nie znaleziono pliku konfiguracyjnego grup warstw: {json_path}")
        except json.JSONDecodeError:
            self.cable_layers = []
            self.output_widget.log_error(f"Błąd dekodowania pliku JSON: {json_path}")

    def _setup_ui_dynamically(self):
        main_layout = QVBoxLayout(self)
        
        self.settings_groupbox = QGroupBox("Ustawienia")
        self.settings_groupbox.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        settings_layout = QVBoxLayout(self.settings_groupbox)

        scope_layout = QHBoxLayout()
        scope_layout.addWidget(QLabel("Wybierz zakres ograniczający:"))
        self.zakres_combo_box = QComboBox()
        self.zakres_combo_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        scope_layout.addWidget(self.zakres_combo_box)
        self.refresh_button = QPushButton("Odśwież")
        scope_layout.addWidget(self.refresh_button)
        settings_layout.addLayout(scope_layout)

        layer_layout = QHBoxLayout()
        layer_layout.addWidget(QLabel("Wybierz warstwę do sprawdzenia:"))
        self.layer_combobox = QComboBox()
        self.layer_combobox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layer_layout.addWidget(self.layer_combobox)
        self.show_all_layers_checkbox = QCheckBox("Wyświetl na liście wszystkie istniejące warstwy")
        self.show_all_layers_checkbox.setChecked(False)
        layer_layout.addWidget(self.show_all_layers_checkbox)
        settings_layout.addLayout(layer_layout)

        check_layout = QHBoxLayout()
        check_layout.addStretch()
        self.check_button = QPushButton("Sprawdź geometrie")
        check_layout.addWidget(self.check_button)
        settings_layout.addLayout(check_layout)

        self.results_groupbox = QGroupBox("Wyniki")
        results_layout = QVBoxLayout(self.results_groupbox)
        self.results_table = QTableWidget()
        self.results_table.setSortingEnabled(True)
        results_layout.addWidget(self.results_table)

        results_actions_layout = QHBoxLayout()
        results_actions_layout.addStretch()
        self.zoom_to_feature_button = QPushButton("Przybliż do obiektu")
        self.delete_selected_button = QPushButton("Usuń zaznaczone")
        self.delete_all_button = QPushButton("Usuń wszystkie")
        results_actions_layout.addWidget(self.zoom_to_feature_button)
        results_actions_layout.addWidget(self.delete_selected_button)
        results_actions_layout.addWidget(self.delete_all_button)
        results_layout.addLayout(results_actions_layout)

        self.output_widget_placeholder = QWidget()
        self.output_widget = FormattedOutputWidget()
        output_layout = QVBoxLayout(self.output_widget_placeholder)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(self.output_widget)
        self.logger.set_user_message_widget(self.output_widget.output_console)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.results_groupbox)
        splitter.addWidget(self.output_widget_placeholder)
        splitter.setSizes([300, 150])

        main_layout.addWidget(self.settings_groupbox)
        main_layout.addWidget(splitter)

    def _connect_signals(self):
        self.refresh_button.clicked.connect(self.refresh_data)
        self.check_button.clicked.connect(self.run_check_action)
        self.delete_all_button.clicked.connect(self.run_delete_all_action)
        self.delete_selected_button.clicked.connect(self.run_delete_selected_action)
        self.zoom_to_feature_button.clicked.connect(self._on_zoom_to_feature_clicked)
        self.results_table.itemSelectionChanged.connect(self._update_button_states)
        self.layer_combobox.currentIndexChanged.connect(self._on_layer_changed)
        self.show_all_layers_checkbox.toggled.connect(self._populate_layers_combobox)

    def refresh_data(self):
        self.output_widget.log_info("Odświeżanie list...")
        self._load_layer_groups()
        self._populate_zakres_combobox()
        self._populate_layers_combobox()
        self.output_widget.log_info("Listy zostały zaktualizowane.")

    def _populate_initial_data(self):
        self._populate_zakres_combobox()
        self._populate_layers_combobox()

    def _setup_initial_state(self):
        self.delete_all_button.setEnabled(False)
        self.delete_selected_button.setEnabled(False)
        self.zoom_to_feature_button.setEnabled(False)

    def _update_button_states(self):
        selected_rows_count = len(self.results_table.selectionModel().selectedRows())
        self.delete_selected_button.setEnabled(selected_rows_count > 0)
        self.zoom_to_feature_button.setEnabled(selected_rows_count == 1)

    def _on_layer_changed(self):
        self._setup_initial_state()
        self.results_table.clearContents()
        self.results_table.setRowCount(0)
        self.feature_map.clear()

    def run_check_action(self):
        self.output_widget.clear_log()
        self._setup_initial_state()
        self.results_table.setColumnCount(0); self.results_table.setRowCount(0)
        self.feature_map.clear()

        layer = self.layer_combobox.currentData()
        if not layer:
            self.output_widget.log_error("Nie wybrano warstwy do sprawdzenia.")
            return
        if self.zakres_combo_box.count() == 0:
            self.output_widget.log_error("Brak dostępnych zakresów. Dodaj warstwę 'zakres_zadania'.")
            return
        if layer.isEditable():
            self.output_widget.log_error(f"Warstwa '{layer.name()}' jest w trybie edycji. Wyłącz tryb edycji, aby kontynuować.")
            return

        scope_geom = self.zakres_combo_box.currentData()
        self.output_widget.log_info(f"Rozpoczynam sprawdzanie geometrii w warstwie '{layer.name()}'...")

        request = QgsFeatureRequest().setFilterRect(scope_geom.boundingBox())
        
        searched_count = 0
        invalid_features = []
        
        for feature in layer.getFeatures(request):
            if not feature.geometry().intersects(scope_geom):
                continue
            
            searched_count += 1
            geom = feature.geometry()
            layer_name = layer.name()
            reason = None

            # Skip cross cables from invalid geometry check.
            wkb_type = geom.wkbType()
            is_line_geometry = wkb_type in [
                QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString,
                QgsWkbTypes.LineStringZ, QgsWkbTypes.MultiLineStringZ,
                QgsWkbTypes.LineStringM, QgsWkbTypes.MultiLineStringM,
                QgsWkbTypes.LineStringZM, QgsWkbTypes.MultiLineStringZM
            ]
            
            is_cross_cable = False
            if layer_name in self.cable_layers and is_line_geometry and not geom.isEmpty():
                try:
                    all_vertices = []
                    if geom.isMultipart():
                        lines = geom.asMultiPolyline()
                        for line in lines:
                            all_vertices.extend(line)
                    else:
                        all_vertices = geom.asPolyline()

                    if len(all_vertices) == 2:
                        start_point, end_point = all_vertices
                        if start_point.distance(end_point) < 0.0001:
                            is_cross_cable = True
                except Exception as e:
                    # In case of geometry processing error, log it but don't crash.
                    # Treat it as not a cross cable and let it be evaluated by the next checks.
                    self.logger.log_dev(self.FUNCTIONALITY_NAME, feature.id(), "ERROR", f"Could not determine if feature {feature.id()} is a cross cable: {e}")

            if is_cross_cable:
                self.logger.log_dev(self.FUNCTIONALITY_NAME, feature.id(), "INFO", f"Skipping cross cable (ID: {feature.id()}) from invalid geometry check.")
                continue

            if not geom or geom.isNull():
                reason = "Geometria typu None/Null"
            elif geom.isEmpty():
                reason = "Pusta geometria (isEmpty)"
            elif not geom.isGeosValid():
                reason = "Niepoprawna geometria (błąd GEOS)"
            elif geom.length() == 0: # This will now only catch non-cable zero-length geoms
                reason = "Geometria o zerowej długości"
            elif geom.wkbType() in [QgsWkbTypes.Point, QgsWkbTypes.PointZ, QgsWkbTypes.PointM, QgsWkbTypes.PointZM]:
                if geom.asPoint() == QgsPoint(0, 0):
                    reason = "Punkt o współrzędnych (0,0)"

            if reason:
                invalid_features.append((feature, reason))

        self.output_widget.log_info(f"Przeszukano obiektów w zakresie zadania: {searched_count}")
        if not invalid_features:
            self.output_widget.log_success("Nie znaleziono obiektów z błędną geometrią.")
            return

        self._display_results(invalid_features, layer)
        self.output_widget.log_warning(f"Znaleziono {len(invalid_features)} obiektów z błędami geometrii.")
        self.delete_all_button.setEnabled(True)
        self._update_button_states()

    def _display_results(self, invalid_features, layer):
        self.results_table.clear()
        self.feature_map.clear()
        
        all_field_names = layer.fields().names()
        
        display_field_names = list(all_field_names)
        headers = ["Powód"]
        
        if 'id' in display_field_names:
            display_field_names.remove('id')
            headers.append('id')
            
        headers.extend(display_field_names)

        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)

        for row, (feature, reason) in enumerate(invalid_features):
            self.results_table.insertRow(row)
            self.feature_map[row] = feature.id()

            reason_item = QTableWidgetItem(reason)
            reason_item.setFlags(reason_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 0, reason_item)

            for col_idx, field_name in enumerate(headers[1:], 1):
                attr_val = str(feature[field_name] or "")
                attr_item = QTableWidgetItem(attr_val)
                attr_item.setFlags(attr_item.flags() & ~Qt.ItemIsEditable)
                self.results_table.setItem(row, col_idx, attr_item)
        
        self.results_table.resizeColumnsToContents()

    def _on_zoom_to_feature_clicked(self):
        selected_rows = self.results_table.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            self.output_widget.log_info("Proszę zaznaczyć dokładnie jeden obiekt na liście.")
            return

        selected_row = selected_rows[0].row()
        feature_id = self.feature_map.get(selected_row)

        if feature_id is None:
            self.output_widget.log_error("Nie można odnaleźć ID obiektu dla zaznaczonego wiersza.")
            return

        layer = self.layer_combobox.currentData()
        if not layer:
            return

        feature = layer.getFeature(feature_id)
        if not feature.hasGeometry():
            self.output_widget.log_error("Wybrany obiekt nie posiada geometrii, nie można go przybliżyć.")
            return

        geom = feature.geometry()
        canvas = self.iface.mapCanvas()

        canvas_crs = canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        if canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
            geom.transform(transform)

        wkb_type = QgsWkbTypes.flatType(geom.wkbType())
        if wkb_type == QgsWkbTypes.LineString or wkb_type == QgsWkbTypes.MultiLineString:
            centroid = geom.interpolate(geom.length() / 2).asPoint()
        else:
            centroid = geom.centroid().asPoint()
        
        canvas.setCenter(centroid)
        canvas.zoomScale(250)
        canvas.refresh()

        self.output_widget.log_info(f"Przybliżono do obiektu o ID: {feature.id()}")

    def run_delete_all_action(self):
        all_ids = list(self.feature_map.values())
        if not all_ids: self.output_widget.log_warning("Brak obiektów do usunięcia."); return
        self._delete_features(all_ids, f"wszystkie {len(all_ids)} znalezione obiekty")

    def run_delete_selected_action(self):
        selected_rows = {index.row() for index in self.results_table.selectedIndexes()}
        if not selected_rows: self.output_widget.log_warning("Nie zaznaczono żadnych obiektów w tabeli wyników."); return
        selected_ids = [self.feature_map[row] for row in selected_rows]
        self._delete_features(selected_ids, f"{len(selected_ids)} zaznaczone obiekty")

    def _delete_features(self, feature_ids, description):
        if not feature_ids: self.output_widget.log_warning("Brak obiektów do usunięcia."); return

        reply = QMessageBox.warning(self, "Potwierdzenie usunięcia", f"Czy na pewno chcesz usunąć {description}? Tej operacji nie można cofnąć.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No: self.output_widget.log_info("Operacja usuwania anulowana przez użytkownika."); return

        layer = self.layer_combobox.currentData()
        layer.startEditing()
        layer.deleteFeatures(feature_ids)
        layer.commitChanges()

        self.output_widget.log_success(f"Pomyślnie usunięto {len(feature_ids)} obiektów.")
        self.run_check_action()

    def _populate_zakres_combobox(self):
        self.zakres_combo_box.clear()
        zakres_layer_list = QgsProject.instance().mapLayersByName("zakres_zadania")
        if not zakres_layer_list:
            self.output_widget.log_error("Nie znaleziono warstwy 'zakres_zadania'.")
            return
        
        zakres_layer = zakres_layer_list[0]
        
        scopes = []
        try:
            # Upewnij się, że atrybut 'nazwa' istnieje
            if "nazwa" not in zakres_layer.fields().names():
                self.output_widget.log_error("Warstwa 'zakres_zadania' nie posiada atrybutu 'nazwa'.")
                return

            for feature in zakres_layer.getFeatures():
                # Dodajemy tylko te zakresy, które mają nazwę
                if feature["nazwa"]:
                    scopes.append((feature["nazwa"], feature.geometry()))
        except Exception as e:
            self.output_widget.log_error(f"Błąd podczas wczytywania zakresów: {e}")
            return

        # Sortowanie listy zakresów alfabetycznie po nazwie
        scopes.sort(key=lambda x: x[0])

        # Dodanie posortowanych elementów do comboboxa
        for name, geom in scopes:
            self.zakres_combo_box.addItem(name, geom)

    def _populate_layers_combobox(self):
        self.layer_combobox.clear()

        # Load essential layers list
        essential_layers_names = []
        try:
            json_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'lista_grup_warstw.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            essential_layers_names = data.get("PROJECT_ESSENTIAL_LAYERS", [])
        except Exception as e:
            self.output_widget.log_error(f"OSTRZEŻENIE: Nie udało się wczytać listy warstw podstawowych z pliku .json: {e}")

        # Get all vector layers from the project
        all_project_layers = [layer for layer in QgsProject.instance().mapLayers().values() if isinstance(layer, QgsVectorLayer)]

        if not self.show_all_layers_checkbox.isChecked():
            # Default view: Show only essential layers
            essential_project_layers = [layer for layer in all_project_layers if layer.name() in essential_layers_names]
            essential_project_layers.sort(key=lambda l: l.name())
            
            for layer in essential_project_layers:
                self.layer_combobox.addItem(layer.name(), layer)
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