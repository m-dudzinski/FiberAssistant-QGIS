import os
import json
from collections import defaultdict

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsFeatureRequest,
    QgsSpatialIndex,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem
)

from ..core.logger import logger
from .base_widget import FormattedOutputWidget

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '../ui/zarzadzanie_PE_widget.ui'))

class ZarzadzaniePEWidget(QWidget, FORM_CLASS):
    FUNCTIONALITY_NAME = "Zarządzanie PE"

    def __init__(self, iface, parent=None):
        super(ZarzadzaniePEWidget, self).__init__(parent)
        self.iface = iface
        self.project = QgsProject.instance()
        self.logger = logger
        self.setupUi(self)

        self.splitter.setSizes([400, 150])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

        self.attribute_mapping_widgets = [
            (self.source_attr_combobox_1, self.target_attr_combobox_1),
            (self.source_attr_combobox_2, self.target_attr_combobox_2),
            (self.source_attr_combobox_3, self.target_attr_combobox_3),
            (self.source_attr_combobox_4, self.target_attr_combobox_4),
        ]

        self._setup_output_widget()
        self._connect_signals()
        self._populate_zakres_combobox()
        self._populate_layer_comboboxes()
        self._populate_wspolrzedne_layers_combobox()

    def _setup_output_widget(self):
        self.output_widget = FormattedOutputWidget()
        layout = self.output_widget_placeholder.layout()
        if layout is None:
            layout = QVBoxLayout(self.output_widget_placeholder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output_widget)

    def _connect_signals(self):
        self.refresh_button.clicked.connect(self.refresh_data)
        self.source_layer_combobox.currentIndexChanged.connect(self._on_source_layer_changed)
        self.target_layer_combobox.currentIndexChanged.connect(self._on_target_layer_changed)
        self.wspolrzedne_show_all_layers_checkbox.toggled.connect(self._populate_wspolrzedne_layers_combobox)

    def run_main_action(self):
        self.output_widget.clear_log()
        current_tab_index = self.tabWidget.currentIndex()
        if current_tab_index == 0:
            self.run_identyfikacja_prg_action()
        elif current_tab_index == 1:
            self.run_wspolrzedne_pe_action()

    def refresh_data(self):
        self.output_widget.log_info("Odświeżanie list...")
        self._populate_zakres_combobox()
        self._populate_layer_comboboxes()
        self._populate_wspolrzedne_layers_combobox()
        self.output_widget.log_info("Listy zostały zaktualizowane.")

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
            [(f["nazwa"], f.geometry()) for f in zakres_layer.getFeatures() if f.attribute("nazwa")],
            key=lambda item: item[0]
        )

        for nazwa, geom in features_to_add:
            self.zakres_combo_box.addItem(nazwa, geom)

        self.output_widget.log_info(f"Znaleziono {self.zakres_combo_box.count()} zakresów.")

    def _populate_wspolrzedne_layers_combobox(self):
        self.wspolrzedne_layer_combobox.clear()

        essential_layers_names = []
        try:
            json_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'lista_grup_warstw.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            essential_layers_names = data.get("PROJECT_ESSENTIAL_LAYERS", [])
        except Exception as e:
            self.logger.log_user(f"OSTRZEŻENIE: Nie udało się wczytać listy warstw podstawowych z pliku .json: {e}")

        all_project_layers = [layer for layer in QgsProject.instance().mapLayers().values() if isinstance(layer, QgsVectorLayer)]

        if not self.wspolrzedne_show_all_layers_checkbox.isChecked():
            essential_project_layers = [layer for layer in all_project_layers if layer.name() in essential_layers_names]
            essential_project_layers.sort(key=lambda l: l.name())
            
            for layer in essential_project_layers:
                self.wspolrzedne_layer_combobox.addItem(layer.name(), layer)
        else:
            essential_project_layers = []
            other_project_layers = []
            
            for layer in all_project_layers:
                if layer.name() in essential_layers_names:
                    essential_project_layers.append(layer)
                else:
                    other_project_layers.append(layer)

            essential_project_layers.sort(key=lambda l: l.name())
            other_project_layers.sort(key=lambda l: l.name())

            for layer in essential_project_layers:
                self.wspolrzedne_layer_combobox.addItem(layer.name(), layer)
            
            if other_project_layers:
                self.wspolrzedne_layer_combobox.insertSeparator(self.wspolrzedne_layer_combobox.count())
                for layer in other_project_layers:
                    self.wspolrzedne_layer_combobox.addItem(layer.name(), layer)

        # Set default selection
        default_layer_name = "punkty_elastycznosci"
        index = self.wspolrzedne_layer_combobox.findText(default_layer_name)
        if index != -1:
            self.wspolrzedne_layer_combobox.setCurrentIndex(index)
        else:
            self.wspolrzedne_layer_combobox.insertItem(0, "wybierz z listy...")
            self.wspolrzedne_layer_combobox.setCurrentIndex(0)

    def _populate_layer_comboboxes(self):
        point_layers = [
            layer.name() for layer in self.project.mapLayers().values() 
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == 0 # 0 for points
        ]
        
        self.source_layer_combobox.clear()
        self.source_layer_combobox.addItems(point_layers)
        prg_index = self.source_layer_combobox.findText("prg_punkty_adresowe")
        if prg_index != -1:
            self.source_layer_combobox.setCurrentIndex(prg_index)

        self.target_layer_combobox.clear()
        self.target_layer_combobox.addItems(point_layers)
        pe_index = self.target_layer_combobox.findText("punkty_elastycznosci")
        if pe_index != -1:
            self.target_layer_combobox.setCurrentIndex(pe_index)

    def _on_source_layer_changed(self):
        layer_name = self.source_layer_combobox.currentText()
        layer = self.project.mapLayersByName(layer_name)
        if not layer: return
        
        fields = [field.name() for field in layer[0].fields()]
        for source_cb, _ in self.attribute_mapping_widgets:
            source_cb.clear()
            source_cb.addItem("wybierz z listy...")
            source_cb.addItems(fields)
        
        self._set_default_mappings()

    def _on_target_layer_changed(self):
        layer_name = self.target_layer_combobox.currentText()
        layer = self.project.mapLayersByName(layer_name)
        if not layer: return

        fields = [field.name() for field in layer[0].fields()]
        for _, target_cb in self.attribute_mapping_widgets:
            target_cb.clear()
            target_cb.addItem("wybierz z listy...")
            target_cb.addItems(fields)

        self._set_default_mappings()

    def _set_default_mappings(self):
        defaults = [("teryt", "terc"), ("simc", "simc"), ("ulic", "ulic"), ("numer", "nr")]
        for i, (source_default, target_default) in enumerate(defaults):
            source_cb, target_cb = self.attribute_mapping_widgets[i]
            
            # Source layer always defaults to placeholder
            source_cb.setCurrentIndex(0)

            # Target layer tries to find default, otherwise sets placeholder
            target_items = [target_cb.itemText(i) for i in range(target_cb.count())]
            try:
                # Find the index of the first item that matches case-insensitively
                target_idx = next(i for i, item in enumerate(target_items) if item.lower() == target_default.lower())
                target_cb.setCurrentIndex(target_idx)
            except StopIteration:
                # Not found, default to placeholder
                target_cb.setCurrentIndex(0)

    def run_identyfikacja_prg_action(self):
        self.output_widget.log_info("Uruchomiono 'Identyfikację PRG'...")

        # 1. Walidacja
        source_layer, target_layer, scope_geom = self._validate_inputs()
        if not all([source_layer, target_layer, scope_geom]):
            self.output_widget.log_error("Walidacja nie powiodła się. Przerwana operacja.")
            return

        mappings = self._get_attribute_mappings()
        if not mappings:
            self.output_widget.log_error("Nie zdefiniowano żadnych mapowań atrybutów. Sprawdź, czy wszystkie pola zostały wybrane.")
            return

        self.output_widget.log_success("Walidacja pomyślna. Rozpoczynanie operacji...")

        # 2. Pobranie opcji z UI
        overwrite = self.nadpisz_radio.isChecked()
        fill_ulic = self.ulic_checkbox.isChecked()
        check_distance = self.groupBox_zasieg.isChecked()
        max_distance = self.distance_spinbox.value()

        # 3. Obsługa CRS
        processing_crs = QgsCoordinateReferenceSystem("EPSG:2180")
        zakres_layer = self.project.mapLayersByName("zakres_zadania")[0]
        source_transform, target_transform, scope_transform = self._prepare_crs_transforms(source_layer, target_layer, zakres_layer.crs(), processing_crs)

        # Transformacja geometrii zakresu
        scope_geom_proc = QgsGeometry(scope_geom)
        if scope_transform:
            scope_geom_proc.transform(scope_transform)

        # 4. Przygotowanie warstwy tymczasowej i indeksu
        mem_source_layer, stats = self._build_in_memory_source_layer(source_layer, source_transform, scope_geom_proc, max_distance if check_distance else 0, processing_crs)
        if not mem_source_layer:
            self.output_widget.log_error("Nie udało się stworzyć tymczasowej warstwy źródłowej. Przerwana operacja.")
            return
        
        source_index = QgsSpatialIndex(mem_source_layer.getFeatures())
        
        # 5. Główna pętla
        target_layer.startEditing()
        
        request = QgsFeatureRequest().setFilterRect(scope_geom.boundingBox())
        
        for target_feature in target_layer.getFeatures(request):
            target_geom = QgsGeometry(target_feature.geometry())
            if not target_geom.intersects(scope_geom):
                continue

            stats['processed'] += 1
            
            target_geom_proc = QgsGeometry(target_geom)
            if target_transform:
                target_geom_proc.transform(target_transform)

            nearest_ids = source_index.nearestNeighbor(target_geom_proc.asPoint(), 1)
            
            if not nearest_ids:
                stats['skipped_no_source_found'] += 1
                continue

            nearest_source_feature = mem_source_layer.getFeature(nearest_ids[0])
            distance = target_geom_proc.distance(QgsGeometry(nearest_source_feature.geometry()))

            if check_distance and distance > max_distance:
                stats['distance_exceeded'] += 1
                obj_id = target_feature.attribute('id') or f"FID: {target_feature.id()}"
                obj_nazwa = target_feature.attribute('nazwa') or "brak"
                self.output_widget.log_warning(f"UWAGA! Dla obiektu o nr id: {obj_id} oraz nazwie: {obj_nazwa}, odległość dopasowania wyniosła {distance:.2f} [m], konieczna ręczna weryfikacja poprawności dopasowania.")

            # Aktualizacja atrybutów
            changed_something = False
            for source_attr, target_attr in mappings.items():
                current_value = target_feature[target_attr]
                
                if not overwrite and (current_value is not None and str(current_value) != ''):
                    stats['skipped_existing_value'] += 1
                    continue

                source_value = nearest_source_feature[source_attr]

                if target_attr.lower() == 'ulic' and fill_ulic:
                    s_val_str = str(source_value).strip().upper()
                    if source_value is None or s_val_str == '' or s_val_str == 'NULL':
                        source_value = '99999'

                if str(current_value) != str(source_value):
                    target_layer.changeAttributeValue(target_feature.id(), target_layer.fields().indexOf(target_attr), source_value)
                    changed_something = True
            
            if changed_something:
                stats['updated'] += 1

        target_layer.commitChanges()
        self._log_summary(stats)

    def _validate_inputs(self):
        source_layer_name = self.source_layer_combobox.currentText()
        target_layer_name = self.target_layer_combobox.currentText()
        scope_geom = self.zakres_combo_box.currentData()

        if not source_layer_name or not target_layer_name or source_layer_name == "wybierz z listy..." or target_layer_name == "wybierz z listy...":
            self.output_widget.log_error("Błąd: Warstwa źródłowa lub docelowa nie została wybrana.")
            return None, None, None

        for source_cb, target_cb in self.attribute_mapping_widgets:
            if source_cb.currentText() == "wybierz z listy..." or target_cb.currentText() == "wybierz z listy...":
                self.output_widget.log_error("Błąd: Nie wszystkie mapowania atrybutów zostały zdefiniowane. Sprawdź, czy wszystkie pola zostały wybrane.")
                return None, None, None
            
        source_layer_list = self.project.mapLayersByName(source_layer_name)
        target_layer_list = self.project.mapLayersByName(target_layer_name)

        if not source_layer_list:
            self.output_widget.log_error(f"Błąd: Nie znaleziono warstwy źródłowej: '{source_layer_name}'.")
            return None, None, None
        if not target_layer_list:
            self.output_widget.log_error(f"Błąd: Nie znaleziono warstwy docelowej: '{target_layer_name}'.")
            return None, None, None

        source_layer = source_layer_list[0]
        target_layer = target_layer_list[0]

        if target_layer.isEditable():
            self.output_widget.log_error(f"Błąd: Warstwa docelowa '{target_layer.name()}' jest w trybie edycji. Wyłącz tryb edycji, aby kontynuować.")
            return None, None, None

        if not scope_geom or scope_geom.isEmpty():
            self.output_widget.log_error("Błąd: Nie wybrano prawidłowego zakresu zadania.")
            return None, None, None
            
        return source_layer, target_layer, scope_geom

    def _get_attribute_mappings(self):
        mappings = {}
        for source_cb, target_cb in self.attribute_mapping_widgets:
            source_attr = source_cb.currentText()
            target_attr = target_cb.currentText()
            if source_attr and target_attr and source_attr != "wybierz z listy..." and target_attr != "wybierz z listy...":
                mappings[source_attr] = target_attr
        return mappings

    def _prepare_crs_transforms(self, source_layer, target_layer, scope_crs, processing_crs):
        source_crs = source_layer.crs()
        target_crs = target_layer.crs()
        project_crs = self.project.crs()

        self.output_widget.log_info(f"Układ współrzędnych projektu: {project_crs.authid()}")
        self.output_widget.log_info(f"Układ warstwy źródłowej ('{source_layer.name()}'): {source_crs.authid()}")
        self.output_widget.log_info(f"Układ warstwy docelowej ('{target_layer.name()}'): {target_crs.authid()}")
        self.output_widget.log_info(f"Układ zakresu ('zakres_zadania'): {scope_crs.authid()}")

        source_transform, target_transform, scope_transform = None, None, None
        
        if source_crs != processing_crs:
            self.output_widget.log_warning(f"Warstwa '{source_layer.name()}' będzie transformowana do {processing_crs.authid()}.")
            source_transform = QgsCoordinateTransform(source_crs, processing_crs, self.project)

        if target_crs != processing_crs:
            self.output_widget.log_warning(f"Warstwa '{target_layer.name()}' będzie transformowana do {processing_crs.authid()}.")
            target_transform = QgsCoordinateTransform(target_crs, processing_crs, self.project)
            
        if scope_crs != processing_crs:
            self.output_widget.log_warning(f"Zakres będzie transformowany do {processing_crs.authid()}.")
            scope_transform = QgsCoordinateTransform(scope_crs, processing_crs, self.project)
            
        return source_transform, target_transform, scope_transform

    def _build_in_memory_source_layer(self, source_layer, transform, scope_geom_proc, buffer, processing_crs):
        stats = defaultdict(int)
        mem_layer = QgsVectorLayer(f"Point?crs={processing_crs.authid()}", "temporary_source_prg", "memory")
        provider = mem_layer.dataProvider()
        provider.addAttributes(source_layer.fields())
        mem_layer.updateFields()

        search_rect = scope_geom_proc.boundingBox().buffered(buffer)
        
        # Transform search rectangle back to source layer CRS for filtering
        source_crs = source_layer.crs()
        if source_crs != processing_crs:
            reverse_transform = QgsCoordinateTransform(processing_crs, source_crs, self.project)
            search_geom = QgsGeometry.fromRect(search_rect)
            search_geom.transform(reverse_transform)
            request_rect = search_geom.boundingBox()
        else:
            request_rect = search_rect
            
        request = QgsFeatureRequest().setFilterRect(request_rect)
        
        new_features = []
        for feature in source_layer.getFeatures(request):
            new_feat = QgsFeature()
            new_feat.setFields(mem_layer.fields())
            for field in source_layer.fields().names():
                new_feat[field] = feature[field]
            
            geom = QgsGeometry(feature.geometry())
            if transform:
                geom.transform(transform)
            
            new_feat.setGeometry(geom)
            new_features.append(new_feat)

        provider.addFeatures(new_features)
        mem_layer.updateExtents()
        self.output_widget.log_info(f"Stworzono tymczasową warstwę w pamięci z {mem_layer.featureCount()} obiektami źródłowymi.")
        return mem_layer, stats

    def _log_summary(self, stats):
        self.output_widget.log_info("--- PODSUMOWANIE ---")
        self.output_widget.log_info(f"Łącznie przetworzonych obiektów w zakresie: {stats['processed']}")
        self.output_widget.log_success(f"Zaktualizowano atrybuty dla: {stats['updated']} obiektów")
        if self.groupBox_zasieg.isChecked():
            self.output_widget.log_warning(f"Ilość obiektów z przekroczoną odległością graniczną: {stats['distance_exceeded']}")
        if not self.nadpisz_radio.isChecked():
            self.output_widget.log_warning(f"Pominięto (istniejąca wartość): {stats['skipped_existing_value']} razy")
        if stats['skipped_no_source_found'] > 0:
            self.output_widget.log_error(f"Pominięto (nie znaleziono obiektu źródłowego): {stats['skipped_no_source_found']} obiektów")
        self.output_widget.log_success("Zakończono pomyślnie.")

    def run_wspolrzedne_pe_action(self):
        self.output_widget.log_info("Uruchomiono 'Współrzędne obiektów'...")

        # 1. Walidacja
        selected_layer = self.wspolrzedne_layer_combobox.currentData()
        if not selected_layer:
            self.output_widget.log_error("BŁĄD: Nie wybrano warstwy lub wskazana warstwa nie istnieje już w projekcie.")
            return

        layer_name = selected_layer.name()
        
        required_fields = {"geo_szer", "geo_dl"}
        layer_fields = {field.name() for field in selected_layer.fields()}

        if not required_fields.issubset(layer_fields):
            missing = required_fields - layer_fields
            self.output_widget.log_error(f"Błąd: Warstwa '{layer_name}' nie posiada wymaganych atrybutów: {', '.join(missing)}.")
            return

        if selected_layer.isEditable():
            self.output_widget.log_error(f"Błąd: Warstwa '{layer_name}' jest w trybie edycji. Wyłącz tryb edycji, aby kontynuować.")
            return

        scope_geom = self.zakres_combo_box.currentData()
        if not scope_geom or scope_geom.isEmpty():
            self.output_widget.log_error("Błąd: Nie wybrano prawidłowego zakresu zadania.")
            return

        self.output_widget.log_success("Walidacja pomyślna. Rozpoczynanie operacji...")

        # 2. Przetwarzanie
        overwrite = self.nadpisz_radio_wspolrzedne.isChecked()
        stats = defaultdict(int)

        # Ustawienie docelowego CRS na układ projektu
        target_crs = self.project.crs()
        source_crs = selected_layer.crs()
        transform = None
        if source_crs != target_crs:
            self.output_widget.log_info(f"Wykryto różnicę w układach współrzędnych. Geometria zostanie przeliczona do układu projektu: {target_crs.authid()}.")
            transform = QgsCoordinateTransform(source_crs, target_crs, self.project)

        selected_layer.startEditing()
        
        request = QgsFeatureRequest().setFilterRect(scope_geom.boundingBox())
        
        for feature in selected_layer.getFeatures(request):
            geom = feature.geometry()
            if not geom.intersects(scope_geom):
                continue

            stats['processed'] += 1

            # Pobranie starych wartości
            old_szer = feature['geo_szer']
            old_dl = feature['geo_dl']

            if not overwrite and (old_szer is not None and str(old_szer) != '') and (old_dl is not None and str(old_dl) != ''):
                stats['skipped_existing_value'] += 1
                continue

            # Transformacja i pobranie nowych współrzędnych
            point_geom = QgsGeometry(geom)
            if transform:
                point_geom.transform(transform)
            
            point = point_geom.asPoint()
            new_dl = round(point.x(), 8) # $x
            new_szer = round(point.y(), 8) # $y

            # Aktualizacja atrybutów
            changed_szer = False
            if str(old_szer) != str(new_szer):
                selected_layer.changeAttributeValue(feature.id(), selected_layer.fields().indexOf('geo_szer'), new_szer)
                stats['updated_szer'] += 1
                changed_szer = True

            changed_dl = False
            if str(old_dl) != str(new_dl):
                selected_layer.changeAttributeValue(feature.id(), selected_layer.fields().indexOf('geo_dl'), new_dl)
                stats['updated_dl'] += 1
                changed_dl = True
            
            if changed_szer or changed_dl:
                stats['objects_changed'] += 1

        selected_layer.commitChanges()
        self._log_wspolrzedne_summary(stats, layer_name)

    def _log_wspolrzedne_summary(self, stats, layer_name):
        self.output_widget.log_info("--- PODSUMOWANIE ---")
        self.output_widget.log_info(f"Warstwa: '{layer_name}'")
        self.output_widget.log_info(f"Współrzędne zapisano w układzie odniesienia projektu: {self.project.crs().authid()}")
        self.output_widget.log_info(f"Łącznie przetworzonych obiektów w zakresie: {stats['processed']}")
        self.output_widget.log_success(f"Liczba obiektów, którym zmieniono atrybuty: {stats['objects_changed']}")
        self.output_widget.log_info(f"  - Zaktualizowano 'geo_szer' dla: {stats['updated_szer']} obiektów")
        self.output_widget.log_info(f"  - Zaktualizowano 'geo_dl' dla: {stats['updated_dl']} obiektów")
        if not self.nadpisz_radio_wspolrzedne.isChecked() and stats['skipped_existing_value'] > 0:
            self.output_widget.log_info(f"Pominięto (istniejąca wartość): {stats['skipped_existing_value']} obiektów")
        self.output_widget.log_success("Zakończono pomyślnie.")
            