import os
import math
import json
from collections import defaultdict

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QSplitter
from qgis.core import QgsProject, QgsDistanceArea, QgsWkbTypes, QgsGeometry

from ..core.logger import logger
from .base_widget import FormattedOutputWidget

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '../ui', 'przeliczanie_dlugosci_widget.ui'))

class PrzeliczanieDlugosciWidget(QWidget, FORM_CLASS):
    FUNCTIONALITY_NAME = "Przeliczanie długości"

    def __init__(self, iface, parent=None):
        super(PrzeliczanieDlugosciWidget, self).__init__(parent)
        self.iface = iface
        self.logger = logger
        self.layer_groups = {}
        self.setupUi(self)

        self._setup_output_widget()
        self._load_layer_groups()
        self._connect_signals()
        self._populate_zakres_combobox()
        self.set_default_settings()

    def _load_layer_groups(self):
        json_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'lista_grup_warstw.json')
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.layer_groups = json.load(f)
            # Ensure keys exist to prevent KeyErrors later
            self.layer_groups.setdefault('CABLE_LAYERS', [])
            self.layer_groups.setdefault('OSLONY_LAYERS', [])
            self.layer_groups.setdefault('TRAKT_LAYERS', [])
            self.output_widget.log_info("Pomyślnie wczytano konfigurację grup warstw.")
        except FileNotFoundError:
            self.layer_groups = {'CABLE_LAYERS': [], 'OSLONY_LAYERS': [], 'TRAKT_LAYERS': []}
            self.output_widget.log_error(f"Nie znaleziono pliku konfiguracyjnego grup warstw: {json_path}")
        except json.JSONDecodeError:
            self.layer_groups = {'CABLE_LAYERS': [], 'OSLONY_LAYERS': [], 'TRAKT_LAYERS': []}
            self.output_widget.log_error(f"Błąd dekodowania pliku JSON: {json_path}")

    def _setup_output_widget(self):
        self.output_widget = FormattedOutputWidget()
        layout = self.output_widget_placeholder.layout()
        if layout is None:
            layout = QVBoxLayout(self.output_widget_placeholder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output_widget)

    def _connect_signals(self):
        self.refresh_button.clicked.connect(self.refresh_data)

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

    def refresh_data(self):
        self.output_widget.log_info("Odświeżanie list...")
        self._load_layer_groups()
        self._populate_zakres_combobox()
        self.output_widget.log_info("Listy zostały zaktualizowane.")

    def set_default_settings(self):
        self.jm_combobox.addItems(["metry", "kilometry"])
        self.pr_combobox.addItems(["0", "1", "2" ,"3", "4"])
        self.pr_combobox.setCurrentText("0")
        self.dlzap_lineedit.setText("30")
        self.wspinst_lineedit.setText("1.03")
        self.wspopt_lineedit.setText("1.01")

    def _to_float(self, value, default=0.0):
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def run_main_action(self):
        self.output_widget.clear_log()
        if not self._is_valid_for_run():
            self.output_widget.log_error("Walidacja nie powiodła się. Przerwana operacja.")
            return

        self.output_widget.log_success("Walidacja pomyślna. Rozpoczynanie operacji...")
        self.output_widget.log_warning("UWAGA! Pamiętaj, że kabel i trakt w zakresie zadania jest zliczany, jeśli jego wierzchołek końcowy znajduje się wewnątrz zakresu. Dlatego upewnij się, że kierunek linii jest ustawiony prawidłowo.")
        self.output_widget.log_warning("UWAGA! Jeśli warstwa nie posiada wymaganego atrybutu (rodzaju długości), obliczenia dla niej zostaną pominięte.")

        selected_layers_names = self._get_selected_layers()
        selected_scope = self.zakres_combo_box.currentData()

        # Get params from UI
        dl_tras_checked = self.dl_tras_checkbox.isChecked()
        dl_inst_checked = self.dl_inst_checkbox.isChecked()
        dl_opt_checked = self.dl_opt_checkbox.isChecked()
        overwrite = self.overwrite_radiobutton.isChecked()
        jm_wsp = 1 if self.jm_combobox.currentText() == "metry" else 0.001
        pr = int(self.pr_combobox.currentText())
        dlzap = self._to_float(self.dlzap_lineedit.text(), 30.0)
        wspinst = self._to_float(self.wspinst_lineedit.text(), 1.03)
        wspopt = self._to_float(self.wspopt_lineedit.text(), 1.01)

        # Initialize counters and logs
        summary = {
            "processed": 0, "in_scope": 0, "modified": defaultdict(int),
            "skipped_geom": 0, "skipped_scope": 0, "identical": defaultdict(int),
            "skipped_attrs": defaultdict(list)
        }

        d = QgsDistanceArea()
        d.setEllipsoid('GRS80')

        for layer_name in selected_layers_names:
            layer = QgsProject.instance().mapLayersByName(layer_name)[0]
            if layer.isEditable():
                self.output_widget.log_error(f"Warstwa '{layer_name}' jest w trybie edycji. Wyłącz tryb edycji i spróbuj ponownie.")
                continue
            
            layer.startEditing()
            all_attrs = layer.fields().names()

            for feature in layer.getFeatures():
                summary["processed"] += 1
                geom = feature.geometry()

                if not self._is_in_scope(geom, selected_scope):
                    summary["skipped_scope"] += 1
                    continue

                if not geom or geom.isNull():
                    summary["skipped_geom"] += 1
                    continue

                wkb_type = geom.wkbType()
                is_line_geometry = wkb_type in [
                    QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString,
                    QgsWkbTypes.LineStringZ, QgsWkbTypes.MultiLineStringZ,
                    QgsWkbTypes.LineStringM, QgsWkbTypes.MultiLineStringM,
                    QgsWkbTypes.LineStringZM, QgsWkbTypes.MultiLineStringZM
                ]

                is_cross_cable = False
                if layer_name in self.layer_groups.get('CABLE_LAYERS', []) and is_line_geometry and not geom.isEmpty():
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
                        try:
                            identyfikator_obiektu = feature['id']
                        except (KeyError, IndexError):
                            identyfikator_obiektu = f"{feature.id()} (ID wewnętrzne - brak atrybutu 'id')"
                        self.output_widget.log_warning(f"Nie można przetworzyć geometrii dla obiektu o identyfikatorze '{identyfikator_obiektu}' na warstwie '{layer_name}': {e}")

                if not is_cross_cable and (not geom.isGeosValid() or geom.isEmpty()):
                    summary["skipped_geom"] += 1
                    continue

                summary["in_scope"] += 1
                
                if is_cross_cable:
                    dl_tras_val_for_calc = 1.0
                else:
                    dl_tras_val_for_calc = d.measureLength(geom)

                # --- NEW CALCULATION BLOCK ---
                dl_inst_metry = 0
                if layer_name in self.layer_groups.get('CABLE_LAYERS', []):
                    x_zapasy_val = self._to_float(feature.attribute('X_zapasy'), 0.0)
                    x_zap_inny_val = self._to_float(feature.attribute('X_zap_inny'), 0.0)
                    dl_inst_metry = (dl_tras_val_for_calc + 30 + (x_zapasy_val * dlzap) + x_zap_inny_val) * wspinst
                
                elif layer_name in self.layer_groups.get('OSLONY_LAYERS', []):
                    dl_inst_metry = (dl_tras_val_for_calc + 4) * wspinst
                
                else: # Includes TRAKT_LAYERS and any others
                    dl_inst_metry = dl_tras_val_for_calc * wspinst

                dl_opt_metry = 0
                if layer_name in self.layer_groups.get('CABLE_LAYERS', []):
                    dl_opt_metry = dl_inst_metry * wspopt

                # --- Calculate final values before update ---
                
                multiplier = 10 ** pr
                
                # Standard rounding for dl_tras
                final_val_tras = round(dl_tras_val_for_calc * jm_wsp, pr)
                
                # Round up for dl_inst
                final_val_inst = math.ceil(dl_inst_metry * jm_wsp * multiplier) / multiplier
                
                # Round up for dl_opt
                final_val_opt = math.ceil(dl_opt_metry * jm_wsp * multiplier) / multiplier

                # Apply the special rule for optical length (only for precision 0)
                if pr == 0 and dl_inst_checked and dl_opt_checked and layer_name in self.layer_groups.get('CABLE_LAYERS', []):
                    if int(final_val_inst) == int(final_val_opt):
                        final_val_opt += 1

                # --- Update feature attributes ---
                update_made = False

                if dl_tras_checked and 'dl_tras' in all_attrs:
                    current_val = self._to_float(feature['dl_tras'])
                    if overwrite or current_val <= 0:
                        if current_val != final_val_tras:
                            feature['dl_tras'] = final_val_tras
                            summary["modified"]["dl_tras"] += 1
                            update_made = True
                        else:
                            summary["identical"]["dl_tras"] += 1
                elif dl_tras_checked:
                    if 'dl_tras' not in summary['skipped_attrs'][layer_name]:
                        summary['skipped_attrs'][layer_name].append('dl_tras')

                if dl_inst_checked and 'dl_inst' in all_attrs:
                    current_val = self._to_float(feature['dl_inst'])
                    if overwrite or current_val <= 0:
                        if current_val != final_val_inst:
                            feature['dl_inst'] = final_val_inst
                            summary["modified"]["dl_inst"] += 1
                            update_made = True
                        else:
                            summary["identical"]["dl_inst"] += 1
                elif dl_inst_checked:
                    if 'dl_inst' not in summary['skipped_attrs'][layer_name]:
                        summary['skipped_attrs'][layer_name].append('dl_inst')

                if dl_opt_checked and 'dl_opt' in all_attrs and layer_name in self.layer_groups.get('CABLE_LAYERS', []):
                    current_val = self._to_float(feature['dl_opt'])
                    if overwrite or current_val <= 0:
                        if current_val != final_val_opt:
                            feature['dl_opt'] = final_val_opt
                            summary["modified"]["dl_opt"] += 1
                            update_made = True
                        else:
                            summary["identical"]["dl_opt"] += 1
                elif dl_opt_checked and layer_name in self.layer_groups.get('CABLE_LAYERS', []):
                     if 'dl_opt' not in summary['skipped_attrs'][layer_name]:
                        summary['skipped_attrs'][layer_name].append('dl_opt')

                if update_made:
                    layer.updateFeature(feature)

            layer.commitChanges()

        self._log_summary(summary)

    def _is_valid_for_run(self):
        # Layer and attribute validation
        selected_layers = self._get_selected_layers()
        if not selected_layers:
            self.output_widget.log_error("Nie wybrano żadnych warstw.")
            return False

        for layer_name in selected_layers:
            layer = QgsProject.instance().mapLayersByName(layer_name)
            if not layer:
                self.output_widget.log_error(f"Warstwa '{layer_name}' nie została znaleziona.")
                return False

        # Length type selection validation
        if not self.dl_tras_checkbox.isChecked() and not self.dl_inst_checkbox.isChecked() and not self.dl_opt_checkbox.isChecked():
            self.output_widget.log_error("Nie wybrano żadnej długości do przeliczenia.")
            return False

        # Calculation mode validation
        if not self.overwrite_radiobutton.isChecked() and not self.fill_missing_radiobutton.isChecked():
            self.output_widget.log_error("Nie wybrano trybu obliczeń.")
            return False

        # Advanced settings validation
        try:
            float(self.dlzap_lineedit.text())
            float(self.wspinst_lineedit.text())
            float(self.wspopt_lineedit.text())
        except ValueError:
            self.output_widget.log_error("Wartości w ustawieniach zaawansowanych muszą być liczbami.")
            return False

        return True

    def _get_selected_layers(self):
        selected_layers = []
        if self.groupBox_kable.isChecked():
            if self.kable_kable_checkbox.isChecked():
                selected_layers.append("kable")
            if self.kable_raport_checkbox.isChecked():
                selected_layers.append("kable_raport")
        if self.groupBox_trakty.isChecked():
            if self.trakty_trakt_checkbox.isChecked():
                selected_layers.append("trakt")
            if self.trakty_wybudowane_trakty_checkbox.isChecked():
                selected_layers.append("wybudowane_trakty")
        if self.groupBox_oslony.isChecked():
            if self.oslony_obiekty_oslonowe_checkbox.isChecked():
                selected_layers.append("obiekty_osłonowe")
        return selected_layers

    def _is_in_scope(self, geom, scope_geom):
        if not geom or not scope_geom or not geom.intersects(scope_geom):
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

    def _log_summary(self, s):
        self.output_widget.log_info("--- PODSUMOWANIE ---")
        self.output_widget.log_info(f"Łącznie przetworzono obiektów: {s['processed']}")
        self.output_widget.log_info(f"- Przetworzono obiektów w zakresie: {s['in_scope']}")
        if s['modified']['dl_tras'] > 0:
            self.output_widget.log_success(f"- Zmodyfikowano obiektów (dl_tras): {s['modified']['dl_tras']}")
        if s['modified']['dl_inst'] > 0:
            self.output_widget.log_success(f"- Zmodyfikowano obiektów (dl_inst): {s['modified']['dl_inst']}")
        if s['modified']['dl_opt'] > 0:
            self.output_widget.log_success(f"- Zmodyfikowano obiektów (dl_opt): {s['modified']['dl_opt']}")
        if s['skipped_geom'] > 0:
            self.output_widget.log_warning(f"- Pominięto obiektów (błędna geometria): {s['skipped_geom']}")
        if s['skipped_scope'] > 0:
            self.output_widget.log_warning(f"- Pominięto obiektów (poza zakresem): {s['skipped_scope']}")
        if s['identical']['dl_tras'] > 0:
            self.output_widget.log_info(f"- Identyczna wartość (dl_tras): {s['identical']['dl_tras']}")
        if s['identical']['dl_inst'] > 0:
            self.output_widget.log_info(f"- Identyczna wartość (dl_inst): {s['identical']['dl_inst']}")
        if s['identical']['dl_opt'] > 0:
            self.output_widget.log_info(f"- Identyczna wartość (dl_opt): {s['identical']['dl_opt']}")
        
        has_skipped = any(attrs for attrs in s['skipped_attrs'].values())
        if has_skipped:
            self.output_widget.log_info("--- POMINIĘTE ATRYBUTY ---")
            for layer_name, attrs in s['skipped_attrs'].items():
                if attrs:
                    self.output_widget.log_warning(f'Warstwa "{layer_name}" nie posiada atrybutów: {", ".join(attrs)} - obliczanie tych danych dla tej warstwy pominięte.')

        self.output_widget.log_success("Zakończono pomyślnie.")