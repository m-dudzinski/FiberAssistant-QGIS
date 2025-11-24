import os
import json
from collections import defaultdict

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget, QCheckBox, QVBoxLayout
from qgis.core import (
    QgsProject,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsCoordinateTransform
)

from .base_widget import FormattedOutputWidget
from ..core.logger import logger

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '../ui/wykorzystanie_infrastruktury_widget.ui'))

class WykorzystanieInfrastrukturyWidget(QWidget, FORM_CLASS):
    FUNCTIONALITY_NAME = "Wykorzystanie infrastruktury"

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.project = QgsProject.instance()
        self.logger = logger
        self.setupUi(self)

        self.infra_layers_checkboxes = []
        self.usage_layers_checkboxes = []

        self._setup_output_widget()
        self._populate_layer_lists()
        self._populate_zakres_combobox()
        self._connect_signals()

    def _setup_output_widget(self):
        self.output_widget = FormattedOutputWidget()
        layout = QVBoxLayout(self.output_widget_placeholder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output_widget)
        self.splitter.setSizes([400, 200])

    def _populate_layer_lists(self):
        self._populate_layers_from_group("INFRASTRUCTURE_LAYERS", self.gridLayout_infra_layers, self.infra_layers_checkboxes)
        self._populate_layers_from_group("SET_USAGE_LAYERS", self.gridLayout_usage_layers, self.usage_layers_checkboxes)

    def _populate_layers_from_group(self, group_name, layout, checkbox_list):
        # Clear existing widgets
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        checkbox_list.clear()
        
        try:
            json_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'lista_grup_warstw.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            layer_names = data.get(group_name, [])
            if not layer_names:
                self.output_widget.log_warning(f"Nie znaleziono warstw w grupie '{group_name}' w pliku konfiguracyjnym.")
                layout.parentWidget().setVisible(False)
                return

            row, col = 0, 0
            for layer_name in layer_names:
                checkbox = QCheckBox(layer_name)
                checkbox.setChecked(True)
                layout.addWidget(checkbox, row, col)
                checkbox_list.append(checkbox)
                col += 1
                if col >= 2:
                    col = 0
                    row += 1
        except Exception as e:
            self.output_widget.log_error(f"Błąd podczas wczytywania warstw z grupy '{group_name}': {e}")

    def _populate_zakres_combobox(self):
        self.zakres_combo_box.clear()
        zakres_layer_list = self.project.mapLayersByName("zakres_zadania")
        if not zakres_layer_list:
            self.output_widget.log_error("Nie znaleziono warstwy 'zakres_zadania'.")
            return

        zakres_layer = zakres_layer_list[0]
        if "nazwa" not in zakres_layer.fields().names():
            self.output_widget.log_error("Warstwa 'zakres_zadania' nie posiada atrybutu 'nazwa'.")
            return

        features_to_add = sorted(
            [(feature["nazwa"], feature.geometry()) for feature in zakres_layer.getFeatures() if feature.attribute("nazwa")],
            key=lambda f: f[0]
        )

        for nazwa, geom in features_to_add:
            self.zakres_combo_box.addItem(nazwa, geom)

        self.output_widget.log_info(f"Znaleziono {self.zakres_combo_box.count()} zakresów.")

    def _connect_signals(self):
        self.refresh_button.clicked.connect(self._populate_zakres_combobox)

    def run_main_action(self):
        self.output_widget.clear_log()
        self.output_widget.log_info("Uruchomiono funkcjonalność 'Wykorzystanie infrastruktury'.")
        self.output_widget.log_warning("UWAGA! Pamiętaj, że kabel i trakt w zakresie zadania jest zliczany, jeśli jego wierzchołek końcowy znajduje się wewnątrz zakresu. Dlatego upewnij się, że kierunek linii jest ustawiony prawidłowo.")
        self.output_widget.log_info("Przed uruchomieniem upewnij się, że wierzchołki obiektów na projekcie są styczne z infrastrukturą!")

        # --- 1. Walidacja ---
        selected_infra_layers_names = [cb.text() for cb in self.infra_layers_checkboxes if cb.isChecked()]
        selected_usage_layers_names = [cb.text() for cb in self.usage_layers_checkboxes if cb.isChecked()]
        scope_geom = self.zakres_combo_box.currentData()
        overwrite = self.overwrite_radio.isChecked()

        if not self._validate_inputs(selected_infra_layers_names, selected_usage_layers_names, scope_geom):
            return

        # Exclude 'obiekty_punktowe'
        if 'obiekty_punktowe' in selected_infra_layers_names:
            selected_infra_layers_names.remove('obiekty_punktowe')
            self.output_widget.log_info("Warstwa 'obiekty_punktowe' została pominięta w przetwarzaniu zgodnie z założeniami.")

        if not selected_infra_layers_names:
            self.output_widget.log_error("Po odfiltrowaniu nie pozostały żadne warstwy infrastruktury do przetworzenia.")
            return

        infra_layers = [self.project.mapLayersByName(name)[0] for name in selected_infra_layers_names]
        usage_layers = [self.project.mapLayersByName(name)[0] for name in selected_usage_layers_names]

        if not self._validate_layers(infra_layers + usage_layers):
            return

        # --- 2. Przygotowanie ---
        self.output_widget.log_info("Przygotowywanie... Sprawdzanie układów współrzędnych i budowanie indeksu przestrzennego.")
        
        target_crs = self.project.crs()
        
        # --- CRS Handling for scope_geom ---
        zakres_layer = self.project.mapLayersByName("zakres_zadania")[0]
        scope_crs = zakres_layer.crs()
        self.output_widget.log_info(f"Układ współrzędnych warstwy 'zakres_zadania': {scope_crs.authid()}")
        self.output_widget.log_info(f"Układ współrzędnych projektu: {target_crs.authid()}")
        
        if scope_crs != target_crs:
            self.output_widget.log_warning("Wykryto różnicę w układach współrzędnych. Transformowanie geometrii zakresu do układu projektu.")
            transform_scope = QgsCoordinateTransform(scope_crs, target_crs, self.project)
            scope_geom.transform(transform_scope)

        usage_vertices = set()
        cable_vertices = set()
        pe_vertices = set()

        for layer in usage_layers:
            source_crs = layer.crs()
            transform_to_proj = QgsCoordinateTransform(source_crs, target_crs, self.project) if source_crs != target_crs else None
            
            # Create a query geometry in the layer's CRS for setFilterRect
            query_scope_geom = QgsGeometry(scope_geom)
            if source_crs != target_crs:
                transform_to_layer_crs = QgsCoordinateTransform(target_crs, source_crs, self.project)
                query_scope_geom.transform(transform_to_layer_crs)

            request = QgsFeatureRequest().setFilterRect(query_scope_geom.boundingBox())
            for feature in layer.getFeatures(request):
                geom = feature.geometry()
                if transform_to_proj:
                    geom.transform(transform_to_proj)

                if geom.intersects(scope_geom):
                    current_set = set()
                    for vertex in geom.vertices():
                        current_set.add((round(vertex.x(), 3), round(vertex.y(), 3)))
                    
                    usage_vertices.update(current_set)
                    if layer.name() == 'kable':
                        cable_vertices.update(current_set)
                    elif layer.name() == 'punkty_elastycznosci':
                        pe_vertices.update(current_set)

        self.output_widget.log_info(f"Znaleziono {len(usage_vertices)} unikalnych wierzchołków na warstwach świadczących o wykorzystaniu ({len(cable_vertices)} z kabli, {len(pe_vertices)} z PE).")

        # --- Get MR value from scope ---
        mr_value = None
        selected_scope_name = self.zakres_combo_box.currentText()
        if 'MR' in zakres_layer.fields().names():
            request = QgsFeatureRequest().setFilterExpression(f"\"nazwa\" = '{selected_scope_name}'")
            scope_features = list(zakres_layer.getFeatures(request))
            if scope_features:
                mr_value = scope_features[0]['MR']
                self.output_widget.log_info(f"Pobrano wartość MR '{mr_value}' z wybranego zakresu.")
            else:
                self.output_widget.log_warning("Nie można było odnaleźć obiektu wybranego zakresu, aby pobrać wartość MR.")
        else:
            self.output_widget.log_warning("Warstwa 'zakres_zadania' nie posiada atrybutu 'MR'. Atrybut 'X_MR' nie będzie aktualizowany.")

        usage_vertices = set()
        cable_vertices = set()
        pe_vertices = set()

        for layer in usage_layers:
            source_crs = layer.crs()
            transform_to_proj = QgsCoordinateTransform(source_crs, target_crs, self.project) if source_crs != target_crs else None
            
            query_scope_geom = QgsGeometry(scope_geom)
            if source_crs != target_crs:
                transform_to_layer_crs = QgsCoordinateTransform(target_crs, source_crs, self.project)
                query_scope_geom.transform(transform_to_layer_crs)

            request = QgsFeatureRequest().setFilterRect(query_scope_geom.boundingBox())
            for feature in layer.getFeatures(request):
                geom = feature.geometry()
                if transform_to_proj:
                    geom.transform(transform_to_proj)

                if geom.intersects(scope_geom):
                    current_set = set()
                    for vertex in geom.vertices():
                        current_set.add((round(vertex.x(), 3), round(vertex.y(), 3)))
                    
                    usage_vertices.update(current_set)
                    if layer.name() == 'kable':
                        cable_vertices.update(current_set)
                    elif layer.name() == 'punkty_elastycznosci':
                        pe_vertices.update(current_set)

        self.output_widget.log_info(f"Znaleziono {len(usage_vertices)} unikalnych wierzchołków na warstwach świadczących o wykorzystaniu ({len(cable_vertices)} z kabli, {len(pe_vertices)} z PE).")

        # --- 3. Przetwarzanie ---
        stats = self._initialize_stats()
        
        for layer in infra_layers:
            layer.startEditing()

        try:
            for layer in infra_layers:
                self.output_widget.log_info(f"Przetwarzanie warstwy: {layer.name()}...")
                layer_stats = self._process_infra_layer(layer, scope_geom, usage_vertices, cable_vertices, pe_vertices, overwrite, target_crs, mr_value)
                self._aggregate_stats(stats, layer_stats, layer.name())

            for layer in infra_layers:
                layer.commitChanges()
            
            self.output_widget.log_info("Wszystkie zmiany zostały pomyślnie zapisane.")
            self._log_summary(stats)

        except Exception as e:
            self.output_widget.log_error(f"Krytyczny błąd podczas przetwarzania: {e}. Wszystkie zmiany zostały wycofane.")
            for layer in infra_layers:
                layer.rollBack()
            return

    def _validate_inputs(self, infra_layers, usage_layers, scope_geom):
        if not scope_geom or scope_geom.isEmpty():
            self.output_widget.log_error("Nie wybrano prawidłowego zakresu zadania.")
            return False
        if not infra_layers:
            self.output_widget.log_error("Nie wybrano żadnej warstwy infrastruktury do sprawdzenia.")
            return False
        if not usage_layers:
            self.output_widget.log_error("Nie wybrano żadnej warstwy świadczącej o wykorzystaniu.")
            return False
        return True

    def _validate_layers(self, layers):
        for layer in layers:
            if layer.isEditable():
                self.output_widget.log_error(f"Warstwa '{layer.name()}' jest w trybie edycji. Wyłącz tryb edycji, aby kontynuować.")
                return False
            if layer.name() in [cb.text() for cb in self.infra_layers_checkboxes if cb.isChecked() and cb.text() != 'obiekty_punktowe']:
                if "X_wykorzystanie" not in layer.fields().names():
                    self.output_widget.log_error(f"Warstwa infrastruktury '{layer.name()}' nie posiada wymaganego atrybutu 'X_wykorzystanie'.")
                    return False
        return True

    def _initialize_stats(self):
        return defaultdict(lambda: defaultdict(int))

    def _process_infra_layer(self, layer, scope_geom, usage_vertices, cable_vertices, pe_vertices, overwrite, target_crs, mr_value):
        layer_stats = self._initialize_stats()
        source_crs = layer.crs()
        transform_to_proj = QgsCoordinateTransform(source_crs, target_crs, self.project) if source_crs != target_crs else None

        wykorzystanie_idx = layer.fields().indexOf("X_wykorzystanie")
        mr_idx = layer.fields().indexOf("X_MR")
        
        query_scope_geom = QgsGeometry(scope_geom)
        if source_crs != target_crs:
            transform_to_layer_crs = QgsCoordinateTransform(target_crs, source_crs, self.project)
            query_scope_geom.transform(transform_to_layer_crs)

        request = QgsFeatureRequest().setFilterRect(query_scope_geom.boundingBox())
        for feature in layer.getFeatures(request):
            geom = feature.geometry()
            if not geom or geom.isEmpty():
                layer_stats[layer.name()]['skipped_no_geometry'] += 1
                continue
            
            if transform_to_proj:
                geom.transform(transform_to_proj)

            if not self._is_in_scope(geom, scope_geom):
                layer_stats[layer.name()]['skipped_outside_scope'] += 1
                continue
            
            layer_stats[layer.name()]['processed'] += 1
            
            feature_vertices = set((round(v.x(), 3), round(v.y(), 3)) for v in geom.vertices())
            
            is_used = any(v in usage_vertices for v in feature_vertices)
            new_value = "TAK" if is_used else "NIE"
            old_value = feature.attribute(wykorzystanie_idx)
            
            # --- Początek refaktoryzacji logiki ---

            # Zawsze zbieraj statystyki styczności, jeśli obiekt jest używany
            if is_used:
                is_touching_cable = any(v in cable_vertices for v in feature_vertices)
                is_touching_pe = any(v in pe_vertices for v in feature_vertices)
                if is_touching_cable:
                    layer_stats[layer.name()]['coincident_with_cable'] += 1
                elif is_touching_pe:
                    layer_stats[layer.name()]['coincident_only_with_pe'] += 1
                else:
                    layer_stats[layer.name()]['coincident_with_other'] += 1

            # Sprawdź, czy można dokonać aktualizacji atrybutów
            can_update = overwrite or (old_value is None or str(old_value).strip() == '')

            if not can_update:
                layer_stats[layer.name()]['skipped_existing_value'] += 1
                continue

            # Aktualizuj X_MR, jeśli obiekt jest używany (kluczowa poprawka)
            if is_used and mr_idx != -1 and mr_value is not None:
                can_update_mr = overwrite or (feature.attribute(mr_idx) is None or str(feature.attribute(mr_idx)).strip() == '')
                if can_update_mr:
                    layer.changeAttributeValue(feature.id(), mr_idx, mr_value)
                else:
                    layer_stats[layer.name()]['skipped_mr_update'] += 1

            # Aktualizuj X_wykorzystanie, tylko jeśli wartość się zmienia
            if old_value != new_value:
                layer.changeAttributeValue(feature.id(), wykorzystanie_idx, new_value)
                if new_value == "TAK":
                    layer_stats[layer.name()]['changed_to_tak'] += 1
                else:
                    layer_stats[layer.name()]['changed_to_nie'] += 1
            
            # --- Koniec refaktoryzacji logiki ---

        
        return layer_stats

    def _is_in_scope(self, geom, scope_geom):
        if not geom.intersects(scope_geom):
            return False
        
        wkb_type = geom.wkbType()
        if QgsWkbTypes.geometryType(wkb_type) == QgsWkbTypes.LineGeometry:
            if geom.numVertices() > 0:
                last_vertex = geom.vertexAt(geom.numVertices() - 1)
                if not QgsGeometry.fromPointXY(last_vertex).within(scope_geom):
                    return False
            else:
                return False
        return True

    def _aggregate_stats(self, total_stats, layer_stats, layer_name):
        for stat, value in layer_stats[layer_name].items():
            total_stats[layer_name][stat] = value

    def _log_summary(self, stats):
        self.output_widget.log_info("--- PODSUMOWANIE ---")
        total_processed_all = 0
        
        for layer_name in sorted(stats.keys()):
            layer_stats = stats[layer_name]
            total_processed = layer_stats.get('processed', 0)
            total_processed_all += total_processed
            
            self.output_widget.log_info(f"Warstwa '{layer_name}':")
            self.output_widget.log_info(f"  - Ilość łącznie przetworzonych obiektów: {total_processed}")
            
            if total_processed > 0:
                changed_to_tak = layer_stats.get('changed_to_tak', 0)
                changed_to_nie = layer_stats.get('changed_to_nie', 0)
                skipped_existing = layer_stats.get('skipped_existing_value', 0)
                skipped_mr = layer_stats.get('skipped_mr_update', 0)

                self.output_widget.log_success(f"  - Ilość obiektów ze stycznością do kabli: {layer_stats.get('coincident_with_cable', 0)}")
                self.output_widget.log_success(f"  - Ilość obiektów ze stycznością wyłącznie do PE: {layer_stats.get('coincident_only_with_pe', 0)}")
                self.output_widget.log_info(f"  - Ilość obiektów ze stycznością do innych obiektów: {layer_stats.get('coincident_with_other', 0)}")
                
                if changed_to_tak > 0:
                    self.output_widget.log_success(f"  - Ilość obiektów, którym zmieniono X_wykorzystanie na 'TAK': {changed_to_tak}")
                if changed_to_nie > 0:
                    self.output_widget.log_success(f"  - Ilość obiektów, którym zmieniono X_wykorzystanie na 'NIE': {changed_to_nie}")
                if skipped_existing > 0:
                    self.output_widget.log_warning(f"  - Ilość obiektów pominiętych (istniejąca wartość X_wykorzystanie): {skipped_existing}")
                if skipped_mr > 0:
                    self.output_widget.log_warning(f"  - Ilość obiektów, dla których pominięto aktualizację X_MR (istniejąca wartość): {skipped_mr}")

            skipped_outside = layer_stats.get('skipped_outside_scope', 0)
            if skipped_outside > 0:
                self.output_widget.log_warning(f"  - Ilość obiektów pominiętych (koniec poza zakresem): {skipped_outside}")

            skipped_no_geom = layer_stats.get('skipped_no_geometry', 0)
            if skipped_no_geom > 0:
                self.output_widget.log_warning(f"  - Ilość obiektów pominiętych (brak geometrii): {skipped_no_geom}")

        self.output_widget.log_info(f"\nŁącznie przetworzono obiektów we wszystkich warstwach: {total_processed_all}")
        self.output_widget.log_success("Zakończono pomyślnie.")


		
    def refresh_data(self):
        """Called by the main dialog to refresh data."""
        self.output_widget.log_info("Odświeżanie list...")
        self._populate_zakres_combobox()
        self._populate_layer_lists()
        self.output_widget.log_info("Listy zostały zaktualizowane.")