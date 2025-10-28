import os
import json
import math
from collections import defaultdict

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget, QCheckBox, QVBoxLayout
from qgis.core import (
    QgsProject,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsSpatialIndex,
    QgsVectorLayer
)

from .base_widget import FormattedOutputWidget
from ..core.logger import logger

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '../ui/stycznosc_wierzcholkow_widget.ui'))

class StycznoscWierzcholkowWidget(QWidget, FORM_CLASS):
    FUNCTIONALITY_NAME = "Styczność wierzchołków"

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.project = QgsProject.instance()
        self.logger = logger
        self.setupUi(self)

        self.infra_checkboxes_kable = []
        self.infra_checkboxes_trakty = []
        self.infra_checkboxes_pe = []
        self.trakty_group_checkboxes = {}
        self.pe_group_checkboxes = {}

        self._setup_output_widget()
        self._populate_layer_lists()
        self._populate_zakres_combobox()
        self._connect_signals()
        self._setup_initial_state()

    def _setup_output_widget(self):
        self.output_widget = FormattedOutputWidget()
        layout = QVBoxLayout(self.output_widget_placeholder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output_widget)
        self.splitter.setSizes([400, 200])

    def _populate_zakres_combobox(self):
        self.zakres_combo_box.clear()
        zakres_layer_list = self.project.mapLayersByName("zakres_zadania")
        if not zakres_layer_list:
            self.output_widget.log_error("Nie znaleziono warstwy 'zakres_zadania'.")
            return

        zakres_layer = zakres_layer_list[0]
        for feature in zakres_layer.getFeatures():
            try:
                self.zakres_combo_box.addItem(feature["nazwa"], feature.geometry())
            except KeyError:
                self.output_widget.log_error("Warstwa 'zakres_zadania' nie posiada atrybutu 'nazwa'.")
                self.zakres_combo_box.clear()
                break
        self.output_widget.log_info(f"Znaleziono {self.zakres_combo_box.count()} zakresów.")

    def _populate_layer_lists(self):
        self._populate_infra_layers(self.verticalLayout_infra_kable, self.infra_checkboxes_kable)
        self._populate_infra_layers(self.verticalLayout_infra_trakty, self.infra_checkboxes_trakty)
        self._populate_infra_layers(self.verticalLayout_infra_pe, self.infra_checkboxes_pe)
        self._populate_groups("trakt", "trakt", self.trakty_group_checkboxes, self.verticalLayout_groups_trakty)
        self._populate_groups("punkty_elastycznosci", "typ", self.pe_group_checkboxes, self.verticalLayout_groups_pe)

    def _populate_infra_layers(self, layout, checkbox_list):
        try:
            json_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'lista_grup_warstw.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            infra_layers = data.get("INFRASTRUCTURE_LAYERS", [])
            if not infra_layers:
                layout.parentWidget().setVisible(False)
                return
            for layer_name in infra_layers:
                checkbox = QCheckBox(layer_name)
                checkbox.setChecked(True)
                layout.addWidget(checkbox)
                checkbox_list.append(checkbox)
        except Exception as e:
            self.output_widget.log_error(f"Błąd podczas wczytywania warstw infrastruktury: {e}")

    def _populate_groups(self, layer_name, field, checkbox_dict, layout):
        layer = self.project.mapLayersByName(layer_name)
        if not layer:
            self.output_widget.log_warning(f"Nie znaleziono warstwy '{layer_name}'.")
            layout.parentWidget().setVisible(False)
            return
        try:
            unique_values = layer[0].uniqueValues(layer[0].fields().indexOf(field))
            for value in sorted(unique_values):
                if not value: continue
                checkbox = QCheckBox(str(value))
                checkbox.setChecked(True)
                layout.addWidget(checkbox)
                checkbox_dict[str(value)] = checkbox
        except Exception as e:
            self.output_widget.log_error(f"Błąd podczas wczytywania grup dla '{layer_name}': {e}")

    def _connect_signals(self):
        self.refresh_button.clicked.connect(self._populate_zakres_combobox)
        self.groupBox_experimental_kable.toggled.connect(self.spinBox_max_dist_kable.setEnabled)
        self.groupBox_experimental_trakty.toggled.connect(self.spinBox_max_dist_trakty.setEnabled)
        self.groupBox_experimental_pe.toggled.connect(self.spinBox_max_dist_pe.setEnabled)

    def _setup_initial_state(self):
        self.spinBox_max_dist_kable.setEnabled(False)
        self.spinBox_max_dist_trakty.setEnabled(False)
        self.spinBox_max_dist_pe.setEnabled(False)

    def run_main_action(self):
        self.output_widget.clear_log()
        current_tab_index = self.tabWidget.currentIndex()
        if current_tab_index == 0:
            self.run_kable_check()
        elif current_tab_index == 1:
            self.run_trakty_check()
        elif current_tab_index == 2:
            self.run_pe_check()

    def _get_scope_geometry(self):
        scope_geom = self.zakres_combo_box.currentData()
        if not scope_geom or scope_geom.isEmpty():
            self.output_widget.log_error("Nie wybrano prawidłowego zakresu zadania.")
            return None
        return scope_geom

    def run_kable_check(self):
        self.output_widget.log_info("Rozpoczynam sprawdzanie styczności dla: Kable...")
        scope_geom = self._get_scope_geometry()
        if not scope_geom: return

        layer_name = "kable"
        layer = self.project.mapLayersByName(layer_name)
        if not layer: return self.output_widget.log_error(f"Nie znaleziono warstwy '{layer_name}'.")
        layer = layer[0]

        if layer.isEditable(): return self.output_widget.log_error(f"Warstwa '{layer.name()}' jest w trybie edycji. Wyłącz tryb edycji, aby kontynuować.")

        auto_fix = self.checkBox_auto_fix_kable.isChecked()
        experimental_enabled = self.groupBox_experimental_kable.isChecked()
        max_distance = self.spinBox_max_dist_kable.value()
        
        self._run_check_logic(layer, scope_geom, auto_fix, experimental_enabled, max_distance, 'kable')

    def run_trakty_check(self):
        self.output_widget.log_info("Rozpoczynam sprawdzanie styczności dla: Trakty...")
        scope_geom = self._get_scope_geometry()
        if not scope_geom: return

        layer_name = "trakt"
        layer = self.project.mapLayersByName(layer_name)
        if not layer: return self.output_widget.log_error(f"Nie znaleziono warstwy '{layer_name}'.")
        layer = layer[0]

        if layer.isEditable(): return self.output_widget.log_error(f"Warstwa '{layer.name()}' jest w trybie edycji. Wyłącz tryb edycji, aby kontynuować.")
            
        auto_fix = self.checkBox_auto_fix_trakty.isChecked()
        experimental_enabled = self.groupBox_experimental_trakty.isChecked()
        max_distance = self.spinBox_max_dist_trakty.value()

        self._run_check_logic(layer, scope_geom, auto_fix, experimental_enabled, max_distance, 'trakty')

    def run_pe_check(self):
        self.output_widget.log_info("Rozpoczynam sprawdzanie styczności dla: PE...")
        scope_geom = self._get_scope_geometry()
        if not scope_geom: return

        layer_name = "punkty_elastycznosci"
        layer = self.project.mapLayersByName(layer_name)
        if not layer: return self.output_widget.log_error(f"Nie znaleziono warstwy '{layer_name}'.")
        layer = layer[0]

        if layer.isEditable(): return self.output_widget.log_error(f"Warstwa '{layer.name()}' jest w trybie edycji. Wyłącz tryb edycji, aby kontynuować.")

        auto_fix = self.checkBox_auto_fix_pe.isChecked()
        experimental_enabled = self.groupBox_experimental_pe.isChecked()
        max_distance = self.spinBox_max_dist_pe.value()

        self._run_check_logic(layer, scope_geom, auto_fix, experimental_enabled, max_distance, 'pe')

    def _run_check_logic(self, layer, scope_geom, auto_fix, experimental_enabled, max_distance, check_type):
        infra_checkboxes = getattr(self, f"infra_checkboxes_{check_type}")
        infra_layers = [self.project.mapLayersByName(cb.text())[0] for cb in infra_checkboxes if cb.isChecked() and self.project.mapLayersByName(cb.text())]
        infra_points = self._get_points_from_layers(infra_layers, scope_geom)

        pa_points, pe_points = set(), set()
        if check_type in ['kable', 'pe']:
            pa_layer = self.project.mapLayersByName("lista_pa")
            if pa_layer:
                pa_points = self._get_points_from_layers([pa_layer[0]], scope_geom)
        if check_type == 'kable':
            pe_layer = self.project.mapLayersByName("punkty_elastycznosci")
            if pe_layer:
                pe_points = self._get_points_from_layers([pe_layer[0]], scope_geom)

        stats = self._init_stats()
        layer.startEditing()
        try:
            for feature in layer.getFeatures():
                if not self._is_in_scope(feature.geometry(), scope_geom):
                    stats['skipped_out_of_scope'] += 1
                    continue
                
                new_geom, stats_update = self._process_feature(feature, infra_points, pa_points, pe_points, auto_fix, experimental_enabled, max_distance, check_type)
                
                if stats_update:
                    self._update_stats(stats, stats_update)
                    if stats_update['fixed'] > 0:
                        layer.changeGeometry(feature.id(), new_geom)
                        self._log_fixed_feature(feature, stats_update['fixed'], check_type)
                    if stats_update['non_coincident'] > 0:
                        self._log_non_coincident_feature(feature, stats_update['non_coincident'], check_type, stats_update.get('missing_endpoints'), stats_update.get('non_coincident_indices'))
        finally:
            layer.commitChanges()
        
        self.output_widget.log_info("Zakończono sprawdzanie.")
        self._log_stats(stats, check_type)

    def _process_feature(self, feature, infra_points, pa_points, pe_points, auto_fix, experimental_enabled, max_distance, check_type):
        geom = feature.geometry()
        stats_update = defaultdict(int)

        group_name = "BRAK"
        if check_type == 'kable':
            group_name = feature.attribute('rodzaj') or "BRAK"
        elif check_type == 'trakty':
            group_name = feature.attribute('trakt') or "BRAK"
        elif check_type == 'pe':
            group_name = feature.attribute('typ') or "BRAK"
        stats_update['group'] = group_name

        stats_update['processed_objects'] = 1
        if geom.isEmpty():
            stats_update['skipped_other'] = 1
            return geom, stats_update

        if check_type != 'pe':
            try:
                dl_tras_val = feature.attribute('dl_tras')
                if isinstance(dl_tras_val, (int, float)):
                    stats_update['total_length'] = float(dl_tras_val)
                else:
                    stats_update['total_length'] = 0.0
            except (KeyError, TypeError):
                stats_update['total_length'] = 0.0

        new_geom_points = list(geom.vertices())
        stats_update['total_vertices'] = len(new_geom_points)
        
        vertices_to_check_indices = list(range(len(new_geom_points)))
        doziemny_types = ["doziemny", "abonencki doziemny", "TOK ziemny"]
        if check_type in ['kable', 'trakty'] and group_name in doziemny_types:
            vertices_to_check_indices = [0, len(new_geom_points) - 1] if len(new_geom_points) > 1 else [0]

        grupa_abonencka_def = ["abonencki napowietrzny", "abonencki doziemny", "abonencki planowany"]
        if check_type == 'kable' and group_name in grupa_abonencka_def and auto_fix:
            if self._check_coincidence_point(new_geom_points[0], pa_points) and self._check_coincidence_point(new_geom_points[-1], pe_points):
                new_geom_points.reverse()

        for i in vertices_to_check_indices:
            point = new_geom_points[i]
            target_points = infra_points
            
            if check_type == 'kable' and group_name in grupa_abonencka_def:
                if i == 0: target_points = pe_points
                elif i == len(new_geom_points) - 1: target_points = pa_points
            elif check_type == 'pe':
                target_points = infra_points.union(pa_points)

            is_coincident = self._check_coincidence_point(point, target_points)

            if is_coincident:
                if check_type == 'pe' and self._check_coincidence_point(point, pa_points):
                    stats_update['coincident_pa'] += 1
                else:
                    stats_update['coincident'] += 1
            else:
                stats_update['non_coincident'] += 1
                stats_update.setdefault('non_coincident_indices', []).append(i)
                if check_type == 'kable' and group_name in grupa_abonencka_def:
                    if i == 0: stats_update.setdefault('missing_endpoints', []).append("PE")
                    if i == len(new_geom_points) - 1: stats_update.setdefault('missing_endpoints', []).append("PA")
                
                if auto_fix:
                    nearest_point = self._find_nearest_point(point, target_points, experimental_enabled, max_distance)
                    if nearest_point:
                        new_geom_points[i] = nearest_point
                        stats_update['fixed'] += 1
                        if check_type == 'pe' and self._check_coincidence_point(nearest_point, pa_points):
                            stats_update['fixed_pa'] += 1
                        else:
                            stats_update['fixed_infra'] += 1
                    else:
                        stats_update['skipped_fix'] += 1
        
        # Convert all points to QgsPointXY before creating the new geometry
        points_xy = [QgsPointXY(p) for p in new_geom_points]
        final_geom = QgsGeometry.fromPointXY(points_xy[0]) if geom.type() == QgsWkbTypes.PointGeometry else QgsGeometry.fromPolylineXY(points_xy)
        return final_geom, stats_update

    def _get_points_from_layers(self, layers, scope_geom, precision=8):
        points = set()
        if not layers:
            return points
        for layer in layers:
            if not isinstance(layer, QgsVectorLayer):
                continue
            try:
                index = QgsSpatialIndex(layer.getFeatures())
                for feature in layer.getFeatures(index.intersects(scope_geom.boundingBox())):
                    if scope_geom.intersects(feature.geometry()):
                        for vertex in feature.geometry().vertices():
                            points.add((round(vertex.x(), precision), round(vertex.y(), precision)))
            except Exception as e:
                self.output_widget.log_error(f"Błąd podczas przetwarzania warstwy '{layer.name()}': {e}")
        return points

    def _find_nearest_point(self, point, point_set, experimental_enabled, max_distance):
        min_dist_sq, nearest_point_tuple = float('inf'), None
        if not point_set:
            return None

        point_xy = QgsPointXY(point)

        for p_tuple in point_set:
            p_geom = QgsPointXY(p_tuple[0], p_tuple[1])
            dist_sq = point_xy.sqrDist(p_geom)
            if dist_sq < min_dist_sq:
                min_dist_sq, nearest_point_tuple = dist_sq, p_tuple
        
        if experimental_enabled and math.sqrt(min_dist_sq) > max_distance:
            return None
        
        if nearest_point_tuple:
            return QgsPointXY(nearest_point_tuple[0], nearest_point_tuple[1])
        return None

    def _check_coincidence_point(self, point, point_set, precision=8):
        return (round(point.x(), precision), round(point.y(), precision)) in point_set

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

    def _init_stats(self):
        return {
            'groups': defaultdict(lambda: {
                'processed_objects': 0, 'total_length': 0.0, 'total_vertices': 0,
                'coincident': 0, 'coincident_pa': 0, 'non_coincident': 0,
                'fixed': 0, 'fixed_infra': 0, 'fixed_pa': 0,
                'missing_endpoints': [],
                'non_coincident_indices': []
            }),
            'skipped_out_of_scope': 0, 'skipped_other': 0, 'skipped_fix': 0
        }

    def _update_stats(self, stats, update):
        # Global stats
        stats['skipped_other'] += update.pop('skipped_other', 0)
        stats['skipped_fix'] += update.pop('skipped_fix', 0)

        # Per-group stats
        group = update.pop('group')
        group_stats = stats['groups'][group]

        # Explicitly handle length to avoid type issues
        length_to_add = update.pop('total_length', 0.0)
        group_stats['total_length'] += length_to_add

        # Handle the rest of the stats
        for key, value in update.items():
            if key in ['missing_endpoints', 'non_coincident_indices']:
                group_stats[key].extend(value)
            else:
                group_stats[key] += value

    def _log_stats(self, stats, check_type):
        self.output_widget.log_info("--- Statystyki ---")
        total_processed = sum(data['processed_objects'] for data in stats['groups'].values())
        total_non_coincident = sum(data['non_coincident'] for data in stats['groups'].values())
        total_fixed = sum(data['fixed'] for data in stats['groups'].values())

        self.output_widget.log_info(f"Łącznie przetworzono obiektów: {total_processed}")
        self.output_widget.log_warning(f"Znaleziono wierzchołków bez styczności: {total_non_coincident}")
        self.output_widget.log_success(f"Naprawiono wierzchołków: {total_fixed}")

        for group, data in sorted(stats['groups'].items()):
            self.output_widget.log_info(f"Grupa: {group}")
            self.output_widget.log_info(f"  Przetworzone obiekty: {data['processed_objects']}")
            
            total_verts = data['coincident'] + data['coincident_pa'] + data['non_coincident']
            self.output_widget.log_info("  Wierzchołki:")
            self.output_widget.log_info(f"    - łącznie: {total_verts}")
            self.output_widget.log_info(f"    - styczne: {data['coincident'] + data['coincident_pa']}")
            self.output_widget.log_info(f"    - bez styczności: {data['non_coincident']}")
            self.output_widget.log_info(f"    - naprawione: {data['fixed']}")
            
            if check_type == 'pe':
                if data['coincident_pa'] > 0: self.output_widget.log_info(f"    - w tym styczne z PA: {data['coincident_pa']}")
                if data['fixed_pa'] > 0: self.output_widget.log_success(f"    - w tym naprawione do PA: {data['fixed_pa']}")
                if data['fixed_infra'] > 0: self.output_widget.log_success(f"    - w tym naprawione do infrastruktury: {data['fixed_infra']}")

        if stats['skipped_out_of_scope'] > 0: self.output_widget.log_info(f"Pominięte (poza zakresem): {stats['skipped_out_of_scope']}")
        if stats['skipped_other'] > 0: self.output_widget.log_warning(f"Pominięte (błędna geometria): {stats['skipped_other']}")
        if stats['skipped_fix'] > 0: self.output_widget.log_warning(f"Pominięte (nie znaleziono obiektu do dociągnięcia w pobliżu): {stats['skipped_fix']}")

    def _log_non_coincident_feature(self, feature, count, feature_type, missing_endpoints=None, non_coincident_indices=None):
        id_val = feature.attribute('id')
        fid_display = id_val if id_val not in [None, 0, ''] else 'NULL'

        name_part = ""
        if feature_type in ['kable', 'pe']:
            nazwa_val = feature.attribute('nazwa')
            nazwa_display = nazwa_val if nazwa_val else 'BRAK'
            name_part = f"o nazwie: {nazwa_display} i "

        if feature_type == 'pe':
            msg = f"UWAGA! Znaleziono PE {name_part}ID: {fid_display}, który nie ma styczności z infrastrukturą ani PA."
        else:
            dl_tras_val = feature.attribute('dl_tras')
            dl_tras_display = f"{dl_tras_val:.1f}" if isinstance(dl_tras_val, (int, float)) else (dl_tras_val or 'N/A')
            msg = f"UWAGA! Znaleziono {feature_type} {name_part}ID: {fid_display} i dł. tras. {dl_tras_display} [m], który posiada: {count} [szt] wierzchołków bez styczności z infrastrukturą."
            if missing_endpoints:
                msg += f" (brak styczności z {' / '.join(missing_endpoints)})"
            if non_coincident_indices:
                human_readable_indices = [i + 1 for i in non_coincident_indices]
                msg += f". Nr tych wierzchołków: {', '.join(map(str, sorted(human_readable_indices)))}"
        self.output_widget.log_warning(msg)

    def _log_fixed_feature(self, feature, count, feature_type):
        id_val = feature.attribute('id')
        fid_display = id_val if id_val not in [None, 0, ''] else 'NULL'

        name_part = ""
        if feature_type in ['kable', 'pe']:
            nazwa_val = feature.attribute('nazwa')
            nazwa_display = nazwa_val if nazwa_val else 'BRAK'
            name_part = f"o nazwie: {nazwa_display} i "

        if feature_type == 'pe':
            msg = f"Dla PE {name_part}ID: {fid_display}, wykonano dociągnięcie do najbliższego obiektu."
        else:
            dl_tras_val = feature.attribute('dl_tras')
            dl_tras_display = f"{dl_tras_val:.1f}" if isinstance(dl_tras_val, (int, float)) else (dl_tras_val or 'N/A')
            msg = f"Dla {feature_type} {name_part}ID: {fid_display} i dł. tras. {dl_tras_display} [m], wykonano dociągnięcie dla: {count} [szt] wierzchołków do infrastruktury."
