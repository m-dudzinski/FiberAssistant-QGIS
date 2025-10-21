import os
import json
from collections import defaultdict

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QSplitter
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon

from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsWkbTypes, QgsPointXY

from ..core.logger import logger
from .base_widget import FormattedOutputWidget

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '../ui/dane_podstawowe_projektu_widget.ui'))

class DanePodstawoweProjektuWidget(QWidget, FORM_CLASS):
    FUNCTIONALITY_NAME = "Dane podstawowe projektu"

    def __init__(self, iface, parent=None):
        super(DanePodstawoweProjektuWidget, self).__init__(parent)
        self.iface = iface
        self.logger = logger
        self.layer_checkboxes = []
        self.layer_checkboxes_id = []
        self.setupUi(self)

        self.splitter.setSizes([400, 150])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

        self._setup_output_widget()
        self._adjust_layout()
        self._connect_signals()
        self._populate_zakres_combobox()
        self._populate_layers_list()
        self._populate_layers_list_id()
        self._setup_initial_state()

    def _setup_output_widget(self):
        self.output_widget = FormattedOutputWidget()
        layout = self.output_widget_placeholder.layout()
        if layout is None:
            layout = QVBoxLayout(self.output_widget_placeholder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output_widget)

    def _adjust_layout(self):
        self.horizontalLayout_bottom_groups.setStretch(0, 3)
        self.horizontalLayout_bottom_groups.setStretch(1, 1)

    def _connect_signals(self):
        self.refresh_button.clicked.connect(self.refresh_data)
        # Tab 1
        self.wybrane_warstwy_radio.toggled.connect(self.layers_scroll_area.setEnabled)
        self.zadanie_checkbox.toggled.connect(self.zadanie_line_edit.setDisabled)
        self.olt_checkbox.toggled.connect(self.olt_line_edit.setDisabled)
        self.mr_checkbox.toggled.connect(self.mr_line_edit.setDisabled)
        self.km_checkbox.toggled.connect(self.km_line_edit.setDisabled)
        self.projektant_checkbox.toggled.connect(self.projektant_line_edit.setDisabled)
        # Tab 2
        self.cb_kabel_kanalowy.toggled.connect(self.le_kabel_kanalowy.setEnabled)
        self.cb_kabel_doziemny.toggled.connect(self.le_kabel_doziemny.setEnabled)
        self.cb_kabel_abonencki_doziemny.toggled.connect(self.le_kabel_abonencki_doziemny.setEnabled)
        self.cb_kabel_abonencki_planowany.toggled.connect(self.le_kabel_abonencki_planowany.setEnabled)
        # Tab 3
        self.wybrane_warstwy_radio_id.toggled.connect(self.layers_scroll_area_id.setEnabled)

    def _populate_zakres_combobox(self):
        self.zakres_combo_box.clear()
        zakres_layer_list = QgsProject.instance().mapLayersByName("zakres_zadania")
        if not zakres_layer_list:
            self.output_widget.log_error("Nie znaleziono warstwy 'zakres_zadania'.")
            return
        if len(zakres_layer_list) > 1:
            self.output_widget.log_warning("Znaleziono więcej niż jedną warstwę o nazwie 'zakres_zadania'. Używana będzie pierwsza z listy.")
        zakres_layer = zakres_layer_list[0]
        for feature in zakres_layer.getFeatures():
            try:
                self.zakres_combo_box.addItem(feature["nazwa"], feature.geometry())
            except KeyError:
                self.output_widget.log_error("Warstwa 'zakres_zadania' nie posiada atrybutu 'nazwa'.")
                self.zakres_combo_box.clear()
                break
        self.output_widget.log_info(f"Znaleziono {self.zakres_combo_box.count()} zakresów.")

    def _populate_layers_list(self):
        self._populate_layer_list_generic(self.layers_grid_layout, self.layer_checkboxes)

    def _populate_layers_list_id(self):
        self._populate_layer_list_generic(self.layers_grid_layout_id, self.layer_checkboxes_id)

    def _populate_layer_list_generic(self, grid_layout, checkbox_list):
        while grid_layout.count():
            child = grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        checkbox_list.clear()
        try:
            wzorzec_path = os.path.join(os.path.dirname(__file__), "..", "templates", "lista_warstw_projektowych.json")
            with open(wzorzec_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            layer_names = data.get("layers", [])
            row, col = 0, 0
            for layer_name in layer_names:
                checkbox = QCheckBox(layer_name)
                checkbox_list.append(checkbox)
                grid_layout.addWidget(checkbox, row, col)
                col += 1
                if col >= 4:
                    col = 0
                    row += 1
        except Exception as e:
            self.output_widget.log_error(f"Nie można wczytać listy warstw z pliku 'lista_warstw_projektowych.json': {e}")

    def _setup_initial_state(self):
        self.layers_scroll_area.setEnabled(False)
        self.layers_scroll_area_id.setEnabled(False)
        self.zadanie_line_edit.setDisabled(self.zadanie_checkbox.isChecked())
        self.olt_line_edit.setDisabled(self.olt_checkbox.isChecked())
        self.mr_line_edit.setDisabled(self.mr_checkbox.isChecked())
        self.km_line_edit.setDisabled(self.km_checkbox.isChecked())
        self.projektant_line_edit.setDisabled(self.projektant_checkbox.isChecked())
        self.le_kabel_kanalowy.setEnabled(self.cb_kabel_kanalowy.isChecked())
        self.le_kabel_doziemny.setEnabled(self.cb_kabel_doziemny.isChecked())
        self.le_kabel_abonencki_doziemny.setEnabled(self.cb_kabel_abonencki_doziemny.isChecked())
        self.le_kabel_abonencki_planowany.setEnabled(self.cb_kabel_abonencki_planowany.isChecked())

    def refresh_data(self):
        self.output_widget.log_info("Odświeżanie list...")
        self._populate_zakres_combobox()
        self._populate_layers_list()
        self._populate_layers_list_id()
        self.output_widget.log_info("Listy zostały zaktualizowane.")

    def run_main_action(self):
        self.output_widget.clear_log()
        current_tab_index = self.tabWidget.currentIndex()
        if current_tab_index == 0:
            self.run_identyfikacja_zadania_action()
        elif current_tab_index == 1:
            self.run_modele_urzadzen_action()
        elif current_tab_index == 2:
            self.run_id_obiektow_action()

    def run_identyfikacja_zadania_action(self):
        self.output_widget.log_info("Uruchomiono walidację parametrów dla 'Identyfikacji zadania'...")
        if not self._is_valid_for_run():
            self.output_widget.log_error("Walidacja nie powiodła się. Przerwana operacja.")
            return
        self.output_widget.log_success("Walidacja pomyślna. Rozpoczynanie operacji...")
        self.output_widget.log_warning("Pamiętaj, że kabel i trakt w zakresie zadania jest zliczany, jeśli jego wierzchołek końcowy znajduje się wewnątrz zakresu. Dlatego upewnij się, że kierunek linii jest ustawiony prawidłowo.")
        selected_geometry = self.zakres_combo_box.currentData()
        data_to_update = self._get_data_to_update()
        layers_to_process = self._get_layers_to_process()
        overwrite = self.nadpisz_radio.isChecked()
        stats = self._process_layers(layers_to_process, selected_geometry, data_to_update, overwrite)
        self._log_summary(stats)

    def _is_valid_for_run(self):
        fields_to_check = [ (self.zadanie_line_edit, self.zadanie_checkbox, "Nazwa zadania"), (self.olt_line_edit, self.olt_checkbox, "Nazwa OLT"), (self.mr_line_edit, self.mr_checkbox, "Numer MR"), (self.km_line_edit, self.km_checkbox, "Numer KM"), (self.projektant_line_edit, self.projektant_checkbox, "Projektant") ]
        for line_edit, checkbox, name in fields_to_check:
            if not line_edit.text() and not checkbox.isChecked():
                self.output_widget.log_error(f"Pole '{name}' jest puste. Uzupełnij je lub zaznacz 'Pomiń'.")
                return False
        layers_to_process = self._get_layers_to_process()
        if not layers_to_process:
            self.output_widget.log_error("Nie wybrano żadnych warstw do przetworzenia.")
            return False
        editable_layers = [layer.name() for layer in layers_to_process if layer.isEditable()]
        if editable_layers:
            self.output_widget.log_error("Następujące warstwy są w trybie edycji. Wyłącz tryb edycji, aby kontynuować:")
            for layer_name in editable_layers:
                self.output_widget.log_error(f"- {layer_name}")
            return False
        return True

    def _get_data_to_update(self):
        data = {}
        if not self.zadanie_checkbox.isChecked() and self.zadanie_line_edit.text():
            data["zadanie"] = (self.zadanie_line_edit.text(), ["zadanie", "Zadanie", "X_zadanie"])
        if not self.olt_checkbox.isChecked() and self.olt_line_edit.text():
            data["olt"] = (self.olt_line_edit.text(), ["OLT", "Id_wezla", "X_OLT"])
        if not self.mr_checkbox.isChecked() and self.mr_line_edit.text():
            data["mr"] = (self.mr_line_edit.text(), ["MR", "X_MR"])
        if not self.km_checkbox.isChecked() and self.km_line_edit.text():
            data["km"] = (self.km_line_edit.text(), ["KM", "Kamień mi", "k_milowy", "X_KM"])
        if not self.projektant_checkbox.isChecked() and self.projektant_line_edit.text():
            data["projektant"] = (self.projektant_line_edit.text(), ["projektant", "X_projektant"])
        return data

    def _get_layers_to_process(self):
        if self.wszystkie_warstwy_radio.isChecked():
            try:
                wzorzec_path = os.path.join(os.path.dirname(__file__), "..", "templates", "lista_warstw_projektowych.json")
                with open(wzorzec_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                layer_names = data.get("layers", [])
                return [l for l_name in layer_names for l in QgsProject.instance().mapLayersByName(l_name) if isinstance(l, QgsVectorLayer)]
            except Exception as e:
                self.output_widget.log_error(f"Nie można wczytać listy warstw z pliku 'lista_warstw_projektowych.json': {e}")
                return []
        else:
            layers = []
            for checkbox in self.layer_checkboxes:
                if checkbox.isChecked():
                    layer_name = checkbox.text()
                    found_layers = QgsProject.instance().mapLayersByName(layer_name)
                    if found_layers:
                        layers.append(found_layers[0])
            return layers

    def _process_layers(self, layers, scope_geom, data_to_update, overwrite):
        stats = { "processed": defaultdict(int), "modified": defaultdict(lambda: defaultdict(int)), "skipped_existing": defaultdict(int), "skipped_outside": defaultdict(list), "objects_modified": defaultdict(set) }
        total_objects_processed = 0
        for layer in layers:
            layer_fields = {field.name() for field in layer.fields()}
            for data_key, (value, attr_names) in data_to_update.items():
                if not any(attr in layer_fields for attr in attr_names):
                    self.output_widget.log_warning(f"Dla warstwy '{layer.name()}' nie odnaleziono żadnego z oczekiwanych pól atrybutów dla '{data_key}' ({', '.join(attr_names)}), więc aktualizacja tego pola została pominięta.")
            layer.startEditing()
            for feature in layer.getFeatures():
                if not self._is_in_scope(feature.geometry(), scope_geom):
                    continue
                total_objects_processed += 1
                stats["processed"][layer.name()] += 1
                for data_key, (value, attr_names) in data_to_update.items():
                    for attr_name in attr_names:
                        field_index = layer.fields().indexOf(attr_name)
                        if field_index != -1:
                            current_value = feature[attr_name]
                            if overwrite or not current_value:
                                if str(current_value) != str(value):
                                    layer.changeAttributeValue(feature.id(), field_index, value)
                                    stats["modified"][layer.name()][attr_name] += 1
                                    stats["objects_modified"][layer.name()].add(feature.id())
                            else:
                                stats["skipped_existing"][layer.name()] += 1
                            break
            layer.commitChanges()
        stats["total_objects_processed"] = total_objects_processed
        return stats

    def _log_summary(self, stats):
        self.output_widget.log_info("--- PODSUMOWANIE ---")
        self.output_widget.log_info(f"Łącznie przetworzono obiektów: {stats.get('total_objects_processed', 0)}")
        for layer_name, count in stats["processed"].items():
            self.output_widget.log_info(f"Warstwa '{layer_name}':")
            self.output_widget.log_info(f"- Przetworzono obiektów w zakresie: {count}")
            num_modified_objects = len(stats["objects_modified"].get(layer_name, set()))
            if num_modified_objects > 0:
                self.output_widget.log_success(f"- Zmieniono wartość dla {num_modified_objects} obiektów.")
            if stats["modified"][layer_name]:
                self.output_widget.log_info("- Podsumowanie zmian atrybutów:")
                for attr, mod_count in sorted(stats["modified"][layer_name].items()):
                    self.output_widget.log_success(f"  - Atrybut '{attr}': zmieniono {mod_count} wartości")
            if stats["skipped_existing"][layer_name]:
                self.output_widget.log_warning(f"- Pominięto (istniejąca wartość): {stats['skipped_existing'][layer_name]} obiektów")
        if stats["skipped_outside"]:
            self.output_widget.log_warning("Pominięto następujące obiekty liniowe (koniec poza zakresem):")
            for layer_name, skipped_list in stats["skipped_outside"].items():
                self.output_widget.log_info(f"- Warstwa '{layer_name}': {', '.join(skipped_list)}")
        self.output_widget.log_success("Zakończono pomyślnie.")

    def run_modele_urzadzen_action(self):
        self.output_widget.log_info("Uruchomiono walidację parametrów dla 'Modeli urządzeń'...")
        self.output_widget.log_warning("UWAGA! Pamiętaj, że kabel i trakt w zakresie zadania jest zliczany, jeśli jego wierzchołek końcowy znajduje się wewnątrz zakresu. Dlatego upewnij się, że kierunek linii jest ustawiony prawidłowo.")
        if not self._is_valid_for_models_run():
            self.output_widget.log_error("Walidacja nie powiodła się. Przerwana operacja.")
            return
        self.output_widget.log_success("Walidacja pomyślna. Rozpoczynanie operacji...")
        selected_geometry = self.zakres_combo_box.currentData()
        overwrite = self.nadpisz_radio_modele.isChecked()
        final_stats = {}
        if self.groupBox_kable_modele.isChecked():
            cable_stats = self._process_kable_models(selected_geometry, overwrite)
            final_stats["Kable"] = cable_stats
        if self.groupBox_pe_modele.isChecked():
            pe_stats = self._process_pe_models(selected_geometry, overwrite)
            final_stats["Punkty Elastyczności"] = pe_stats
        self._log_models_summary(final_stats)

    def _is_valid_for_models_run(self):
        if not self.groupBox_kable_modele.isChecked() and not self.groupBox_pe_modele.isChecked():
            self.output_widget.log_error("Żadna grupa (Kable, PE) nie jest zaznaczona do przetworzenia.")
            return False
        if self.groupBox_kable_modele.isChecked():
            kable_layers = QgsProject.instance().mapLayersByName("kable")
            if not kable_layers:
                self.output_widget.log_error("Warstwa 'kable' nie została znaleziona w projekcie.")
                return False
            kable_layer = kable_layers[0]
            fields = {field.name() for field in kable_layer.fields()}
            if 'rodzaj' not in fields or 'typ' not in fields:
                self.output_widget.log_error("Warstwa 'kable' nie posiada wymaganych atrybutów: 'rodzaj' oraz 'typ'.")
                return False
        if self.groupBox_pe_modele.isChecked():
            pe_layers = QgsProject.instance().mapLayersByName("punkty_elastycznosci")
            if not pe_layers:
                self.output_widget.log_error("Warstwa 'punkty_elastycznosci' nie została znaleziona w projekcie.")
                return False
            pe_layer = pe_layers[0]
            fields = {field.name() for field in pe_layer.fields()}
            required = {'model', 'typ', 'rodzaj', 'status'}
            if not required.issubset(fields):
                missing = required - fields
                self.output_widget.log_error(f"Warstwa 'punkty_elastycznosci' nie posiada wymaganych atrybutów: {', '.join(missing)}.")
                return False
        return True

    def _process_kable_models(self, scope_geom, overwrite):
        stats = defaultdict(lambda: defaultdict(int))
        layer = QgsProject.instance().mapLayersByName("kable")[0]
        target_field = "typ"
        field_index = layer.fields().indexOf(target_field)
        models_to_set = {
            'napowietrzny': (self.cb_kabel_napowietrzny, self.le_kabel_napowietrzny),
            'kanałowy': (self.cb_kabel_kanalowy, self.le_kabel_kanalowy),
            'doziemny': (self.cb_kabel_doziemny, self.le_kabel_doziemny),
            'abonencki napowietrzny': (self.cb_kabel_abonencki_napowietrzny, self.le_kabel_abonencki_napowietrzny),
            'abonencki doziemny': (self.cb_kabel_abonencki_doziemny, self.le_kabel_abonencki_doziemny),
            'abonencki planowany': (self.cb_kabel_abonencki_planowany, self.le_kabel_abonencki_planowany)
        }
        layer.startEditing()
        for feature in layer.getFeatures():
            if not self._is_in_scope(feature.geometry(), scope_geom):
                continue
            rodzaj = feature['rodzaj'] or "brak"
            stats[rodzaj]['processed'] += 1
            if rodzaj in models_to_set:
                checkbox, line_edit = models_to_set[rodzaj]
                if checkbox.isChecked():
                    new_value = line_edit.text()
                    current_value = feature[target_field]
                    if overwrite or not current_value:
                        if str(current_value) != str(new_value):
                            layer.changeAttributeValue(feature.id(), field_index, new_value)
                            stats[rodzaj]['modified'] += 1
                        else:
                            stats[rodzaj]['skipped'] += 1
                    else:
                        stats[rodzaj]['skipped'] += 1
                else:
                    stats[rodzaj]['skipped'] += 1
            else:
                stats[rodzaj]['skipped'] += 1
        layer.commitChanges()
        return stats

    def _process_pe_models(self, scope_geom, overwrite):
        stats = defaultdict(lambda: defaultdict(int))
        layer = QgsProject.instance().mapLayersByName("punkty_elastycznosci")[0]
        target_field = "model"
        field_index = layer.fields().indexOf(target_field)
        cases = {
            'mufa dostępowa': (self.cb_pe_mufa_dostepowa, self.le_pe_mufa_dostepowa),
            'mufa liniowa': (self.cb_pe_mufa_liniowa, self.le_pe_mufa_liniowa),
            'zapas': (self.cb_pe_zapas, self.le_pe_zapas),
            'mufy istniejące': (self.cb_pe_mufy_istniejace, self.le_pe_mufy_istniejace)
        }
        layer.startEditing()
        for feature in layer.getFeatures():
            if not feature.geometry().intersects(scope_geom):
                continue
            typ = feature.attribute('typ')
            rodzaj = feature.attribute('rodzaj')
            status = feature.attribute('status')
            case_key = None
            if typ == 'mufa' and rodzaj == 'dostępowa' and status in ['projektowany', 'nabudowywany', 'przebudowa']:
                case_key = 'mufa dostępowa'
            elif typ == 'mufa' and rodzaj == 'liniowa' and status in ['projektowany', 'nabudowywany', 'przebudowa']:
                case_key = 'mufa liniowa'
            elif typ == 'zapas' and status == 'projektowany':
                case_key = 'zapas'
            elif status == 'istniejący':
                case_key = 'mufy istniejące'
            log_key = case_key or 'inne'
            stats[log_key]['processed'] += 1
            if case_key and cases[case_key][0].isChecked():
                new_value = cases[case_key][1].text()
                current_value = feature[target_field]
                if overwrite or not current_value:
                    if str(current_value) != str(new_value):
                        layer.changeAttributeValue(feature.id(), field_index, new_value)
                        stats[log_key]['modified'] += 1
                    else:
                        stats[log_key]['skipped'] += 1
                else:
                    stats[log_key]['skipped'] += 1
            else:
                stats[log_key]['skipped'] += 1
        layer.commitChanges()
        return stats

    def _log_models_summary(self, stats):
        self.output_widget.log_info("--- PODSUMOWANIE: MODELE URZĄDZEŃ ---")
        for group_name, group_stats in stats.items():
            self.output_widget.log_info(f"Grupa '{group_name}':")
            total_processed = sum(s['processed'] for s in group_stats.values())
            total_modified = sum(s['modified'] for s in group_stats.values())
            total_skipped = sum(s['skipped'] for s in group_stats.values())
            self.output_widget.log_info(f"- Łącznie przetworzono: {total_processed}")
            self.output_widget.log_success(f"- Zmieniono: {total_modified}")
            self.output_widget.log_warning(f"- Pominięto/bez zmian: {total_skipped}")
            if total_modified > 0:
                self.output_widget.log_info("- Podsumowanie zmian (wg rodzaju):")
                for rodzaj, rodzaj_stats in sorted(group_stats.items()):
                    if rodzaj_stats['modified'] > 0:
                        self.output_widget.log_success(f"  - {rodzaj}: zmieniono {rodzaj_stats['modified']} obiektów")
        self.output_widget.log_success("Zakończono pomyślnie.")

    def run_id_obiektow_action(self):
        self.output_widget.log_info("Uruchomiono walidację parametrów dla 'ID obiektów'...")
        self.output_widget.log_warning("UWAGA! Pamiętaj, że kabel i trakt w zakresie zadania jest zliczany, jeśli jego wierzchołek końcowy znajduje się wewnątrz zakresu. Dlatego upewnij się, że kierunek linii jest ustawiony prawidłowo.")
        layers_to_process = self._get_layers_to_process_id()
        if not self._is_valid_for_id_run(layers_to_process):
            self.output_widget.log_error("Walidacja nie powiodła się. Przerwana operacja.")
            return
        self.output_widget.log_success("Walidacja pomyślna. Rozpoczynanie operacji...")
        scope_geom = self.zakres_combo_box.currentData()
        overwrite_all = self.radio_regenerate_all_ids.isChecked()
        all_stats = self._process_ids(layers_to_process, scope_geom, overwrite_all)
        self._log_id_summary(all_stats)

    def _is_valid_for_id_run(self, layers):
        if not layers:
            self.output_widget.log_error("Nie wybrano żadnych warstw do przetworzenia.")
            return False
        for layer in layers:
            if 'id' not in layer.fields().names():
                self.output_widget.log_error(f"Warstwa '{layer.name()}' nie posiada wymaganego atrybutu 'id'.")
                return False
            if layer.isEditable():
                self.output_widget.log_error(f"Warstwa '{layer.name()}' jest w trybie edycji. Wyłącz tryb edycji, aby kontynuować.")
                return False
        return True

    def _get_layers_to_process_id(self):
        if self.wszystkie_warstwy_radio_id.isChecked():
            try:
                wzorzec_path = os.path.join(os.path.dirname(__file__), "..", "templates", "lista_warstw_projektowych.json")
                with open(wzorzec_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                layer_names = data.get("layers", [])
                return [l for l_name in layer_names for l in QgsProject.instance().mapLayersByName(l_name) if isinstance(l, QgsVectorLayer)]
            except Exception as e:
                self.output_widget.log_error(f"Nie można wczytać listy warstw z pliku 'lista_warstw_projektowych.json': {e}")
                return []
        else:
            layers = []
            for checkbox in self.layer_checkboxes_id:
                if checkbox.isChecked():
                    layer_name = checkbox.text()
                    found_layers = QgsProject.instance().mapLayersByName(layer_name)
                    if found_layers:
                        layers.append(found_layers[0])
            return layers

    def _process_ids(self, layers, scope_geom, overwrite_all):
        all_stats = {}
        for layer in layers:
            stats = defaultdict(int)
            id_map = defaultdict(list)
            max_id = 0
            # First pass: analyze all features
            for feature in layer.getFeatures():
                is_valid_id = False
                try:
                    feat_id_val = feature['id']
                    if feat_id_val and str(feat_id_val).strip():
                        id_int = int(feat_id_val)
                        if id_int > 0:
                            id_map[id_int].append(feature.id())
                            if id_int > max_id:
                                max_id = id_int
                            is_valid_id = True
                except (ValueError, TypeError):
                    pass # Invalid conversion, treat as empty
                if not is_valid_id:
                    stats['empty'] += 1
            
            duplicates = {id_val for id_val, fids in id_map.items() if len(fids) > 1}
            stats['valid'] = len(id_map) - len(duplicates)
            for id_val in duplicates:
                stats['duplicated'] += len(id_map[id_val])

            # Second pass: update features in scope
            layer.startEditing()
            features_in_scope = [f for f in layer.getFeatures() if self._is_in_scope(f.geometry(), scope_geom)]
            for feature in features_in_scope:
                stats['processed'] += 1
                try:
                    current_id = int(feature['id'])
                except (ValueError, TypeError):
                    current_id = 0

                is_invalid = (current_id <= 0) or (current_id in duplicates)

                if overwrite_all or is_invalid:
                    max_id += 1
                    layer.changeAttributeValue(feature.id(), layer.fields().indexOf('id'), max_id)
                    stats['assigned'] += 1
                else:
                    stats['skipped'] += 1
            layer.commitChanges()
            all_stats[layer.name()] = stats
        return all_stats

    def _log_id_summary(self, all_stats):
        self.output_widget.log_info("--- PODSUMOWANIE: ID OBIEKTÓW ---")
        for layer_name, stats in all_stats.items():
            self.output_widget.log_info(f"Warstwa '{layer_name}':")
            self.output_widget.log_info(f"- Przetworzono obiektów w zakresie: {stats['processed']}")
            self.output_widget.log_info(f"- Obiekty z prawidłowym ID (przed operacją): {stats['valid']}")
            self.output_widget.log_warning(f"- Obiekty z brakującym ID: {stats['empty']}")
            self.output_widget.log_warning(f"- Obiekty ze zdublowanym ID: {stats['duplicated']}")
            self.output_widget.log_success(f"- Przypisano nowe ID: {stats['assigned']}")
            self.output_widget.log_info(f"- Pominięto (prawidłowe ID): {stats['skipped']}")
        self.output_widget.log_success("Zakończono pomyślnie.")

    def _is_in_scope(self, geom, scope_geom):
        if not geom or not geom.intersects(scope_geom):
            return False
        wkb_type = geom.wkbType()
        if wkb_type in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            last_vertex_point = None
            try:
                if wkb_type == QgsWkbTypes.LineString:
                    polyline = geom.asPolyline()
                    if polyline: last_vertex_point = polyline[-1]
                elif wkb_type == QgsWkbTypes.MultiLineString:
                    multi_polyline = geom.asMultiPolyline()
                    if multi_polyline and multi_polyline[-1]: last_vertex_point = multi_polyline[-1][-1]
                if last_vertex_point and not QgsGeometry.fromPointXY(last_vertex_point).intersects(scope_geom):
                    return False
            except IndexError:
                return False
        return True