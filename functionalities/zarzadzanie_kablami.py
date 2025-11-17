print("START ZARZADZANIE KABLAMI")
import os
import math
from collections import defaultdict

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsSpatialIndex,
    QgsFeatureRequest,
    QgsPointXY,
    QgsRectangle,
    QgsWkbTypes,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextScope
)

from ..core.logger import logger
from .base_widget import FormattedOutputWidget

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '../ui/zarzadzanie_kablami_widget.ui'))

class ZarzadzanieKablamiWidget(QWidget, FORM_CLASS):
    FUNCTIONALITY_NAME = "Zarządzanie kablami"

    def __init__(self, iface, parent=None):
        super(ZarzadzanieKablamiWidget, self).__init__(parent)
        self.iface = iface
        self.project = QgsProject.instance()
        self.logger = logger
        self.setupUi(self)

        self._setup_output_widget()
        self._connect_signals()
        self._populate_zakres_combobox()
        self.target_crs = QgsCoordinateReferenceSystem("EPSG:2180")

    def _setup_output_widget(self):
        self.output_widget = FormattedOutputWidget()
        layout = self.output_widget_placeholder.layout()
        if layout is None:
            layout = QVBoxLayout(self.output_widget_placeholder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output_widget)
        self.splitter.setSizes([400, 200])

    def _connect_signals(self):
        self.refresh_button.clicked.connect(self._populate_zakres_combobox)

    def _get_selected_rodzaje(self):
        selected = []
        
        if self.groupBox_grupa_rozdzielcza.isChecked():
            if self.cb_rodzaj_napowietrzny.isChecked():
                selected.append('napowietrzny')
            if self.cb_rodzaj_kanalowy.isChecked():
                selected.append('kanałowy')
            if self.cb_rodzaj_doziemny.isChecked():
                selected.append('doziemny')

        if self.groupBox_grupa_abonencka.isChecked():
            if self.cb_rodzaj_abonencki_napowietrzny.isChecked():
                selected.append('abonencki napowietrzny')
            if self.cb_rodzaj_abonencki_doziemny.isChecked():
                selected.append('abonencki doziemny')
            if self.cb_rodzaj_abonencki_inny.isChecked():
                selected.append('abonencki_inny')
        
        return selected

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

    def _setup_checkbox_groups(self):
        self.checkbox_groups = {
            self.cb_grupa_rozdzielcza: [
                self.cb_rodzaj_napowietrzny,
                self.cb_rodzaj_kanalowy,
                self.cb_rodzaj_doziemny
            ],
            self.cb_grupa_abonencka: [
                self.cb_rodzaj_abonencki_napowietrzny,
                self.cb_rodzaj_abonencki_doziemny,
                self.cb_rodzaj_abonencki_inny
            ]
        }

        for group_cb, sub_checkboxes in self.checkbox_groups.items():
            group_cb.setTristate(True)
            # Set initial state based on children
            self._on_sub_checkbox_changed(group_cb, sub_checkboxes)
    
    def run_main_action(self):
        self.output_widget.clear_log()
        current_tab_index = self.tabWidget.currentIndex()

        self.output_widget.log_warning("UWAGA! Pamiętaj, że kabel i trakt w zakresie zadania jest zliczany, jeśli jego wierzchołek końcowy znajduje się wewnątrz zakresu. Dlatego upewnij się, że kierunek linii jest ustawiony prawidłowo.")

        if not self._validate_prerequisites():
            self.output_widget.log_error("Przerwano działanie funkcji z powodu niespełnienia wymagań.")
            return

        if current_tab_index == 0:
            self.run_identification_attributes_action()
        elif current_tab_index == 1:
            self.run_s_attributes_action()

    def run_identification_attributes_action(self):
        self.output_widget.log_info("Uruchomiono: Atrybuty identyfikacyjne.")
        scope_geom = self.zakres_combo_box.currentData()
        if not scope_geom or scope_geom.isEmpty():
            self.output_widget.log_error("Nie wybrano prawidłowego zakresu zadania.")
            return

        selected_rodzaje = self._get_selected_rodzaje()
        if not selected_rodzaje:
            self.output_widget.log_error("Nie wybrano żadnego rodzaju kabla do przetworzenia.")
            return

        overwrite = self.radio_nadpisz.isChecked()
        stats = self._init_stats()

        process_abonencka = any('abonencki' in s for s in selected_rodzaje)
        if process_abonencka:
            self._update_pe_coordinates(scope_geom, stats, overwrite)

        self._process_kable(scope_geom, selected_rodzaje, overwrite, stats)
        
        self._log_summary(stats, overwrite)
        self.output_widget.log_success("Zakończono działanie funkcjonalności.")

    def run_s_attributes_action(self):
        self.output_widget.log_info("Uruchomiono: Atrybuty inwestycyjne s_.")
        
        scope_geom = self.zakres_combo_box.currentData()
        if not scope_geom or scope_geom.isEmpty():
            self.output_widget.log_error("Nie wybrano prawidłowego zakresu zadania.")
            return

        if not self.groupBox_s_status.isChecked() and not self.groupBox_s_inv_type.isChecked():
            self.output_widget.log_error("Nie wybrano żadnej operacji do wykonania. Zaznacz grupę 's_status' lub 's_inv_type'.")
            return

        kable_layer = self.project.mapLayersByName("kable")[0]
        transformed_scope = self._get_transformed_scope(scope_geom)
        
        features_to_process = []
        stats = defaultdict(lambda: defaultdict(int))
        stats['summary']['skipped_no_rule_features'] = []
        
        for feature in kable_layer.getFeatures():
            if self._is_in_scope(feature.geometry(), kable_layer.crs(), transformed_scope):
                features_to_process.append(feature)
            else:
                stats['summary']['skipped_outside'] += 1
        
        stats['summary']['total_in_scope'] = len(features_to_process)
        self.output_widget.log_info(f"Znaleziono {len(features_to_process)} obiektów w zakresie.")

        overwrite = self.radio_nadpisz_s.isChecked()
        process_s_status = self.groupBox_s_status.isChecked()
        process_s_inv_type = self.groupBox_s_inv_type.isChecked()
        selected_s_status = self.comboBox_s_status.currentText()

        kable_layer.startEditing()
        success = False
        try:
            for feature in features_to_process:
                stats['summary']['processed'] += 1
                rodzaj = feature['rodzaj'] or ''
                trakt = feature['trakt'] or ''

                if process_s_status:
                    target_s_status = 's0' if rodzaj == 'abonencki planowany' else selected_s_status
                    self._update_attribute(feature, kable_layer, 's_status', target_s_status, overwrite, stats[rodzaj], 's_status_changed', 's_status_unchanged', 's_status_skipped')

                if process_s_inv_type:
                    target_s_inv_type = None
                    if rodzaj in ['doziemny', 'abonencki doziemny']:
                        target_s_inv_type = 'i6'
                    elif rodzaj in ['napowietrzny', 'abonencki napowietrzny']:
                        if trakt == 'TOK napowietrzny':
                            target_s_inv_type = 'i4'
                        else:
                            target_s_inv_type = 'i5'
                    
                    if target_s_inv_type:
                        self._update_attribute(feature, kable_layer, 's_inv_type', target_s_inv_type, overwrite, stats[rodzaj], 's_inv_type_changed', 's_inv_type_unchanged', 's_inv_type_skipped')
                    else:
                        stats['summary']['skipped_no_rule_features'].append(feature)

            success = True
        finally:
            if success:
                kable_layer.commitChanges()
                self.output_widget.log_success("Zmiany zostały pomyślnie zapisane.")
            else:
                kable_layer.rollBack()
                self.output_widget.log_error("Wystąpił błąd. Zmiany zostały wycofane.")
        
        self._log_s_attributes_summary(stats, overwrite)
        self.output_widget.log_success("Zakończono działanie funkcjonalności.")

    def _validate_prerequisites(self):
        self.output_widget.log_info("Sprawdzanie wymagań wstępnych...")
        layers_to_check = {
            "kable": ["rodzaj", "nazwa", "id", "pe_poczatk", "pe_koncowy", "dl_tras", 
                      "X_PE_szer", "X_PE_dlug", "X_ID_ADRES", "X_ADRES", "X_dzialka",
                      "s_inv_type", "s_status", "trakt"],
            "punkty_elastycznosci": ["nazwa", "status", "geo_szer", "geo_dl"],
            "lista_pa": ["Id_budynku", "Miejscowos", "Ulica", "Numer porz", "X_dzialka"],
            "zakres_zadania": ["nazwa"]
        }
        valid = True
        for layer_name, required_fields in layers_to_check.items():
            layers = self.project.mapLayersByName(layer_name)
            if not layers:
                self.output_widget.log_error(f"Brak warstwy '{layer_name}' w projekcie.")
                valid = False
                continue
            layer = layers[0]
            if layer.isEditable():
                self.output_widget.log_error(f"Warstwa '{layer_name}' jest w trybie edycji. Wyłącz tryb edycji, aby kontynuować.")
                valid = False

            existing_fields = {field.name() for field in layer.fields()}
            missing_fields = set(required_fields) - existing_fields
            if missing_fields:
                self.output_widget.log_error(f"Warstwa '{layer_name}' nie posiada wymaganych atrybutów: {', '.join(missing_fields)}")
                valid = False
        if valid:
            self.output_widget.log_success("Wszystkie wymagane warstwy i atrybuty istnieją.")
        return valid

    def _init_stats(self):
        return {
            'rozdzielcza': defaultdict(int),
            'abonencka': defaultdict(int),
            'pe_coords': defaultdict(int),
            'skipped_bad_geom': 0
        }

    def _get_transformed_scope(self, scope_geom):
        zakres_layer = self.project.mapLayersByName("zakres_zadania")[0]
        source_crs = zakres_layer.crs()
        
        if source_crs == self.target_crs:
            return QgsGeometry(scope_geom)

        transformer = QgsCoordinateTransform(source_crs, self.target_crs, self.project)
        transformed_geom = QgsGeometry(scope_geom)
        transformed_geom.transform(transformer)
        return transformed_geom

    def _update_pe_coordinates(self, scope_geom, stats, overwrite):
        self.output_widget.log_info("Aktualizowanie współrzędnych dla obiektów PE w zakresie...")
        pe_layer = self.project.mapLayersByName("punkty_elastycznosci")[0]
        
        target_crs = self.project.crs()
        source_crs = pe_layer.crs()
        transform = None
        if source_crs != target_crs:
            self.output_widget.log_info(f"Wykryto różnicę w układach współrzędnych. Geometria PE zostanie przeliczona do układu projektu: {target_crs.authid()}.")
            transform = QgsCoordinateTransform(source_crs, target_crs, self.project)

        pe_layer.startEditing()
        success = False
        try:
            request = QgsFeatureRequest().setFilterRect(scope_geom.boundingBox())
            
            features_in_scope = [f for f in pe_layer.getFeatures(request) if f.geometry().intersects(scope_geom)]
            
            stats['pe_coords']['found_in_scope'] = len(features_in_scope)
            self.output_widget.log_info(f"Znaleziono {stats['pe_coords']['found_in_scope']} obiektów PE w zakresie.")

            for feature in features_in_scope:
                stats['pe_coords']['processed'] += 1

                old_szer = feature['geo_szer']
                old_dl = feature['geo_dl']

                if not overwrite and (old_szer is not None and str(old_szer) != '') and (old_dl is not None and str(old_dl) != ''):
                    stats['pe_coords']['skipped_existing_value'] += 1
                    continue

                point_geom = QgsGeometry(feature.geometry())
                if transform:
                    point_geom.transform(transform)
                
                if point_geom.isNull() or point_geom.isEmpty():
                    stats['pe_coords']['skipped_bad_geom'] += 1
                    continue

                point = point_geom.asPoint()
                new_dl = round(point.x(), 8)
                new_szer = round(point.y(), 8)

                changed = False
                if str(old_szer) != str(new_szer):
                    pe_layer.changeAttributeValue(feature.id(), pe_layer.fields().indexOf('geo_szer'), new_szer)
                    changed = True

                if str(old_dl) != str(new_dl):
                    pe_layer.changeAttributeValue(feature.id(), pe_layer.fields().indexOf('geo_dl'), new_dl)
                    changed = True
                
                if changed:
                    stats['pe_coords']['updated'] += 1

            success = True
        finally:
            if success:
                pe_layer.commitChanges()
            else:
                pe_layer.rollBack()
                self.output_widget.log_error("Wycofano zmiany z powodu błędu podczas aktualizacji współrzędnych PE.")

    def _process_kable(self, scope_geom, selected_rodzaje, overwrite, stats):
        kable_layer = self.project.mapLayersByName("kable")[0]
        pe_layer = self.project.mapLayersByName("punkty_elastycznosci")[0]
        pa_layer = self.project.mapLayersByName("lista_pa")[0]

        pe_index = QgsSpatialIndex(pe_layer.getFeatures())
        pa_index = QgsSpatialIndex(pa_layer.getFeatures())

        transformed_scope = self._get_transformed_scope(scope_geom)
        
        features_to_process = []
        all_features = kable_layer.getFeatures()

        for feature in all_features:
            rodzaj = feature['rodzaj'] or ''
            
            process_this_feature = False
            if rodzaj in selected_rodzaje:
                process_this_feature = True
            elif 'abonencki_inny' in selected_rodzaje and 'abonencki' in rodzaj and rodzaj not in ['abonencki napowietrzny', 'abonencki doziemny']:
                process_this_feature = True

            if process_this_feature:
                if self._is_in_scope(feature.geometry(), kable_layer.crs(), transformed_scope):
                    features_to_process.append(feature)
                else:
                    group = 'abonencka' if 'abonencki' in rodzaj else 'rozdzielcza'
                    stats[group]['skipped_outside'] += 1

        kable_layer.startEditing()
        success = False
        try:
            for feature in features_to_process:
                rodzaj = feature['rodzaj'] or ''
                group = 'abonencka' if 'abonencki' in rodzaj else 'rozdzielcza'
                stats[group]['processed'] += 1
                if 'abonencki' in rodzaj:
                    self._process_abonencka_cable(feature, kable_layer, pe_layer, pa_layer, pe_index, pa_index, overwrite, stats[group])
                else:
                    self._process_rozdzielcza_cable(feature, kable_layer, pe_layer, pe_index, overwrite, stats[group])
            success = True
        finally:
            if success:
                kable_layer.commitChanges()
            else:
                kable_layer.rollBack()
                self.output_widget.log_error("Wycofano zmiany na warstwie 'kable' z powodu błędu.")

    def _process_rozdzielcza_cable(self, cable_feat, kable_layer, pe_layer, pe_index, overwrite, stats):
        geom = QgsGeometry(cable_feat.geometry())
        wkb_type = geom.wkbType()

        if wkb_type not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString] or geom.isEmpty():
            stats['skipped_bad_geom'] += 1
            return

        start_point, end_point = self._get_line_endpoints(geom)
        if not start_point or not end_point:
            stats['skipped_bad_geom'] += 1
            return

        start_pe_feats = self._find_stitched_features(start_point, pe_layer, pe_index)
        end_pe_feats = self._find_stitched_features(end_point, pe_layer, pe_index)

        if not start_pe_feats:
            self._log_cable_warning(cable_feat, "początek", "PE")
            self._update_attribute(cable_feat, kable_layer, "pe_poczatk", None, overwrite, stats)
            stats['unstitched_start'] += 1
        else:
            if len(start_pe_feats) > 1:
                self._log_multi_stitch_warning(cable_feat, start_pe_feats, "PE")
                stats['multi_stitch'] += 1
            pe_name = start_pe_feats[0]['nazwa']
            self._update_attribute(cable_feat, kable_layer, "pe_poczatk", pe_name, overwrite, stats, 
                                   changed_stat_key='pe_poczatk_set', unchanged_stat_key='pe_poczatk_unchanged')

        if not end_pe_feats:
            self._log_cable_warning(cable_feat, "koniec", "PE")
            self._update_attribute(cable_feat, kable_layer, "pe_koncowy", None, overwrite, stats)
            stats['unstitched_end'] += 1
        else:
            if len(end_pe_feats) > 1:
                self._log_multi_stitch_warning(cable_feat, end_pe_feats, "PE")
                stats['multi_stitch'] += 1
            pe_name = end_pe_feats[0]['nazwa']
            self._update_attribute(cable_feat, kable_layer, "pe_koncowy", pe_name, overwrite, stats, 
                                   changed_stat_key='pe_koncowy_set', unchanged_stat_key='pe_koncowy_unchanged')

    def _process_abonencka_cable(self, cable_feat, kable_layer, pe_layer, pa_layer, pe_index, pa_index, overwrite, stats):
        geom = QgsGeometry(cable_feat.geometry())
        wkb_type = geom.wkbType()

        if wkb_type not in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString] or geom.isEmpty():
            stats['skipped_bad_geom'] += 1
            return

        _, end_point_check = self._get_line_endpoints(geom)
        if not end_point_check:
            stats['skipped_bad_geom'] += 1
            return

        if self._find_stitched_features(end_point_check, pe_layer, pe_index):
            new_geom = None
            if wkb_type == QgsWkbTypes.LineString:
                points = geom.asPolyline()
                points.reverse()
                new_geom = QgsGeometry.fromPolylineXY(points)
            elif wkb_type == QgsWkbTypes.MultiLineString:
                multi_points = geom.asMultiPolyline()
                reversed_parts = [part[::-1] for part in multi_points]
                reversed_parts.reverse()
                new_geom = QgsGeometry.fromMultiPolylineXY(reversed_parts)

            if new_geom and not new_geom.isEmpty():
                kable_layer.changeGeometry(cable_feat.id(), new_geom)
                geom = new_geom
                stats['reversed'] += 1
        
        start_point, end_point = self._get_line_endpoints(geom)
        if not start_point or not end_point:
            stats['skipped_bad_geom'] += 1
            return

        start_pe_feats = self._find_stitched_features(start_point, pe_layer, pe_index)
        end_pa_feats = self._find_stitched_features(end_point, pa_layer, pa_index)

        if not start_pe_feats:
            self._log_cable_warning(cable_feat, "początek", "PE")
            self._update_attribute(cable_feat, kable_layer, "pe_poczatk", None, overwrite, stats)
            stats['unstitched_start'] += 1
        else:
            pe_to_use = start_pe_feats[0]
            if len(start_pe_feats) > 1:
                stats['multi_stitch'] += 1
                self._log_multi_stitch_warning(cable_feat, start_pe_feats, "PE", True)
                non_existing = [f for f in start_pe_feats if f['status'] != 'istniejący']
                if non_existing:
                    pe_to_use = non_existing[0]
            
            self._update_attribute(cable_feat, kable_layer, "pe_poczatk", pe_to_use['nazwa'], overwrite, stats, 
                                   'pe_poczatk_set', 'pe_poczatk_unchanged')
            self._update_attribute(cable_feat, kable_layer, "X_PE_szer", pe_to_use['geo_szer'], overwrite, stats, 
                                   'X_PE_szer_set', 'X_PE_szer_unchanged')
            self._update_attribute(cable_feat, kable_layer, "X_PE_dlug", pe_to_use['geo_dl'], overwrite, stats, 
                                   'X_PE_dlug_set', 'X_PE_dlug_unchanged')

        is_doziemny = cable_feat['rodzaj'] == 'abonencki doziemny'
        if not end_pa_feats:
            if not is_doziemny:
                self._log_cable_warning(cable_feat, "koniec", "PA")
                stats['unstitched_end'] += 1
            self._update_attribute(cable_feat, kable_layer, "pe_koncowy", None, overwrite, stats)
        else:
            pa_to_use = end_pa_feats[0]
            if len(end_pa_feats) > 1:
                stats['multi_stitch'] += 1
                self._log_multi_stitch_warning(cable_feat, end_pa_feats, "PA")

            miejscowosc, ulica, numer = pa_to_use['Miejscowos'], pa_to_use['Ulica'], pa_to_use['Numer porz']
            adres_parts = [m for m in [miejscowosc, ulica, numer] if m and str(m).strip() not in ['NULL', 'None', '']]
            adres_pe_koncowy = " ".join(map(str, adres_parts))
            adres_x_adres = f"{miejscowosc or ''}, {ulica or ''} {numer or ''}".replace(" ,", ",").strip(", ")

            self._update_attribute(cable_feat, kable_layer, "pe_koncowy", adres_pe_koncowy, overwrite, stats, 
                                   'pe_koncowy_set', 'pe_koncowy_unchanged')
            self._update_attribute(cable_feat, kable_layer, "X_ID_ADRES", pa_to_use['Id_budynku'], overwrite, stats, 
                                   'X_ID_ADRES_set', 'X_ID_ADRES_unchanged')
            self._update_attribute(cable_feat, kable_layer, "X_ADRES", adres_x_adres, overwrite, stats, 
                                   'X_ADRES_set', 'X_ADRES_unchanged')
            self._update_attribute(cable_feat, kable_layer, "X_dzialka", pa_to_use['X_dzialka'], overwrite, stats, 
                                   'X_dzialka_set', 'X_dzialka_unchanged')

    def _get_line_endpoints(self, geom):
        wkb_type = geom.wkbType()
        if wkb_type == QgsWkbTypes.LineString:
            polyline = geom.asPolyline()
            return (polyline[0], polyline[-1]) if len(polyline) >= 2 else (None, None)
        elif wkb_type == QgsWkbTypes.MultiLineString:
            multi_polyline = geom.asMultiPolyline()
            if multi_polyline and multi_polyline[0] and multi_polyline[-1]:
                if len(multi_polyline[0]) > 0 and len(multi_polyline[-1]) > 0:
                    return multi_polyline[0][0], multi_polyline[-1][-1]
        return None, None

    def _find_stitched_features(self, point, layer, index, precision=6):
        search_rect = QgsRectangle(point.x() - 0.000001, point.y() - 0.000001, point.x() + 0.000001, point.y() + 0.000001)
        candidate_ids = index.intersects(search_rect)
        
        stitched_features = []
        if not candidate_ids: return stitched_features

        request = QgsFeatureRequest().setFilterFids(candidate_ids)
        for feature in layer.getFeatures(request):
            if feature.geometry().type() == QgsWkbTypes.PointGeometry:
                feat_point = feature.geometry().asPoint()
                if round(feat_point.x(), precision) == round(point.x(), precision) and \
                   round(feat_point.y(), precision) == round(point.y(), precision):
                    stitched_features.append(feature)
        return stitched_features

    def _update_attribute(self, feature, layer, field_name, value, overwrite, stats, 
                          changed_stat_key=None, unchanged_stat_key=None, skipped_stat_key=None):
        current_value = feature[field_name]
        if not overwrite and (current_value is not None and str(current_value).strip() != ''):
            if skipped_stat_key: stats[skipped_stat_key] += 1
            return

        field_idx = layer.fields().indexOf(field_name)
        if field_idx != -1:
            new_value = value if value is not None else None
            if str(current_value) != str(new_value):
                layer.changeAttributeValue(feature.id(), field_idx, new_value)
                if changed_stat_key: stats[changed_stat_key] += 1
            elif overwrite:
                if unchanged_stat_key: stats[unchanged_stat_key] += 1

    def _is_in_scope(self, geom, source_crs, scope_geom_metric):
        if not geom or geom.isEmpty() or not scope_geom_metric or scope_geom_metric.isEmpty():
            return False

        if source_crs == self.target_crs:
            geom_metric = geom
        else:
            transformer = QgsCoordinateTransform(source_crs, self.target_crs, self.project)
            geom_metric = QgsGeometry(geom)
            geom_metric.transform(transformer)

        if not geom_metric.intersects(scope_geom_metric):
            return False

        wkb_type = geom_metric.wkbType()
        if wkb_type in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
            _, last_vertex_point = self._get_line_endpoints(geom_metric)
            if last_vertex_point and not QgsGeometry.fromPointXY(last_vertex_point).intersects(scope_geom_metric):
                return False
        return True

    def _log_cable_warning(self, feature, end_type, point_type):
        msg = f"UWAGA! Kabel o nazwie: {feature['nazwa']}, id: {feature['id']}, ma niedociągnięty {end_type} do {point_type}!"
        self.output_widget.log_warning(msg)

    def _log_multi_stitch_warning(self, feature, stitched_features, point_type, is_abonencki_pe=False):
        msg = f"UWAGA! Kabel o id: {feature['id']}, nazwie: {feature['nazwa']}, ma styczność z więcej niż jednym {point_type}! Konieczna ręczna weryfikacja."
        if is_abonencki_pe:
            msg += " Domyślnie wybrano obiekt o statusie innym niż 'istniejący'."
        self.output_widget.log_warning(msg)

    def _log_summary(self, stats, overwrite):
        self.output_widget.log_info("--- PODSUMOWANIE: Atrybuty identyfikacyjne ---")
        groups = [('rozdzielcza', "Grupa Rozdzielcza"), ('abonencka', "Grupa Abonencka")]
        
        for group_key, group_name in groups:
            s = stats[group_key]
            if not s['processed']: continue
            
            self.output_widget.log_info("")
            self.output_widget.log_info(f"--- <b>{group_name}</b> ---")
            self.output_widget.log_info(f"Łącznie przetworzonych obiektów: {s['processed']}")
            if group_key == 'abonencka':
                self.output_widget.log_info(f"Ilość obiektów z odwróconą geometrią: {s['reversed']}")
            self.output_widget.log_info(f"Ilość obiektów ze stycznością do wielu punktów (wymaga weryfikacji): {s['multi_stitch']}")
            
            # Log for pe_poczatk
            msg_poczatk = f"✅ Ustawiono 'pe_poczatk' dla: {s.get('pe_poczatk_set', 0)} obiektów"
            if overwrite and s.get('pe_poczatk_unchanged', 0) > 0:
                msg_poczatk += f" | dla {s.get('pe_poczatk_unchanged', 0)} obiektów był już poprawny"
            self.output_widget.log_success(msg_poczatk)

            # Log for pe_koncowy
            msg_koncowy = f"✅ Ustawiono 'pe_koncowy' dla: {s.get('pe_koncowy_set', 0)} obiektów"
            if overwrite and s.get('pe_koncowy_unchanged', 0) > 0:
                msg_koncowy += f" | dla {s.get('pe_koncowy_unchanged', 0)} obiektów był już poprawny"
            self.output_widget.log_success(msg_koncowy)

            self.output_widget.log_warning(f"Ilość obiektów z niedociągniętym początkiem: {s['unstitched_start']}")
            self.output_widget.log_warning(f"Ilość obiektów z niedociągniętym końcem: {s['unstitched_end']}")
            
            if group_key == 'abonencka':
                self.output_widget.log_info("Przypisania atrybutów dla grupy abonenckiej:")
                
                x_attrs = [
                    ('X_ID_ADRES', 'X_ID_ADRES_set', 'X_ID_ADRES_unchanged'),
                    ('X_ADRES', 'X_ADRES_set', 'X_ADRES_unchanged'),
                    ('X_PE_szer', 'X_PE_szer_set', 'X_PE_szer_unchanged'),
                    ('X_PE_dlug', 'X_PE_dlug_set', 'X_PE_dlug_unchanged'),
                    ('X_dzialka', 'X_dzialka_set', 'X_dzialka_unchanged')
                ]
                for attr_name, changed_key, unchanged_key in x_attrs:
                    msg_x = f"✅ - {attr_name}: {s.get(changed_key, 0)} razy"
                    if overwrite and s.get(unchanged_key, 0) > 0:
                        msg_x += f" | dla {s.get(unchanged_key, 0)} przypadków był już poprawny"
                    self.output_widget.log_success(msg_x)

            self.output_widget.log_info(f"Ilość obiektów pominiętych (koniec poza zakresem): {s['skipped_outside']}")

        if stats['skipped_bad_geom']:
            self.output_widget.log_warning(f"Ilość obiektów pominiętych (nieprawidłowa geometria): {stats['skipped_bad_geom']}")

        if stats['pe_coords']:
            self.output_widget.log_info("")
            self.output_widget.log_info("--- <b>Aktualizacja współrzędnych PE</b> ---")
            self.output_widget.log_info(f"Znaleziono w zakresie: {stats['pe_coords'].get('found_in_scope', 0)} obiektów PE.")
            self.output_widget.log_success(f"Zmieniono współrzędne dla: {stats['pe_coords']['updated']} obiektów PE.")
            if stats['pe_coords']['skipped_existing_value'] > 0:
                self.output_widget.log_info(f"Pominięto (istniejąca wartość, tryb bez nadpisywania): {stats['pe_coords']['skipped_existing_value']} obiektów.")

    def _log_s_attributes_summary(self, stats, overwrite):
        self.output_widget.log_info("--- PODSUMOWANIE: Atrybuty inwestycyjne s_ ---")
        summary = stats['summary']
        self.output_widget.log_info(f"Łącznie przetworzono obiektów w zakresie: {summary.get('processed', 0)}")
        self.output_widget.log_info(f"Pominięto obiektów (koniec poza zakresem): {summary.get('skipped_outside', 0)}")

        rodzaje = sorted([k for k in stats if k != 'summary'])
        
        total_s_status_changed = sum(stats[r]['s_status_changed'] for r in rodzaje)
        total_s_inv_type_changed = sum(stats[r]['s_inv_type_changed'] for r in rodzaje)

        if self.groupBox_s_status.isChecked():
            self.output_widget.log_info("\n--- s_status ---")
            self.output_widget.log_success(f"Łącznie zmieniono wartość dla: {total_s_status_changed} obiektów.")
            for r in rodzaje:
                if stats[r]['s_status_changed'] > 0:
                    self.output_widget.log_info(f"  - Dla rodzaju '{r}': {stats[r]['s_status_changed']} obiektów")
            if overwrite:
                total_unchanged = sum(stats[r]['s_status_unchanged'] for r in rodzaje)
                self.output_widget.log_info(f"Nie zmieniono (ta sama wartość): {total_unchanged} obiektów.")
            else:
                total_skipped = sum(stats[r]['s_status_skipped'] for r in rodzaje)
                self.output_widget.log_info(f"Pominięto (istniejąca wartość): {total_skipped} obiektów.")

        if self.groupBox_s_inv_type.isChecked():
            self.output_widget.log_info("\n--- s_inv_type ---")
            self.output_widget.log_success(f"Łącznie zmieniono wartość dla: {total_s_inv_type_changed} obiektów.")
            for r in rodzaje:
                if stats[r]['s_inv_type_changed'] > 0:
                    self.output_widget.log_info(f"  - Dla rodzaju '{r}': {stats[r]['s_inv_type_changed']} obiektów")
            if overwrite:
                total_unchanged = sum(stats[r]['s_inv_type_unchanged'] for r in rodzaje)
                self.output_widget.log_info(f"Nie zmieniono (ta sama wartość): {total_unchanged} obiektów.")
            else:
                total_skipped = sum(stats[r]['s_inv_type_skipped'] for r in rodzaje)
                self.output_widget.log_info(f"Pominięto obiektów (istniejąca wartość): {total_skipped} ")
            
            skipped_features = summary.get('skipped_no_rule_features', [])
            if skipped_features:
                self.output_widget.log_warning(f"Pominięte obiekty(brak reguły dopasowania): {len(skipped_features)} , którymi są:")
                for feature in skipped_features:
                    fid = feature.attribute('id') or 'NULL'
                    nazwa = feature.attribute('nazwa') or 'NULL'
                    dl_tras = feature.attribute('dl_tras') or 'NULL'
                    self.output_widget.log_warning(f"* Kabel o id: {fid}, nazwie: {nazwa}, oraz dł. tras: {dl_tras}")

    def refresh_data(self):
        self.output_widget.log_info("Odświeżanie list...")
        self._populate_zakres_combobox()
        self.output_widget.log_info("Listy zostały zaktualizowane.")

print("KONIEC ZARZADZANIE KABLAMI")
