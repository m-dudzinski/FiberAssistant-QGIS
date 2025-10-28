import os
from collections import defaultdict

import csv
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QApplication, QFileDialog
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
    QgsSpatialIndex,
    QgsPointXY
)

from .base_widget import FormattedOutputWidget
from ..core.logger import logger

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), '../ui/statystyka_widget.ui'))

class StatystykaWidget(QWidget, FORM_CLASS):
    def __init__(self, iface, parent=None):
        super(StatystykaWidget, self).__init__(parent)
        self.iface = iface
        self.logger = logger
        self.setupUi(self)
        
        self._setup_widgets()
        self.setup_connections()
        self.refresh_data()
        self.checkbox_full.setChecked(True)

    def _setup_widgets(self):
        self.results_widget = FormattedOutputWidget()
        results_layout = QVBoxLayout()
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.addWidget(self.results_widget)
        self.results_widget_placeholder.setLayout(results_layout)

        self.logs_widget = FormattedOutputWidget()
        logs_layout = QVBoxLayout()
        logs_layout.setContentsMargins(0, 0, 0, 0)
        logs_layout.addWidget(self.logs_widget)
        self.logs_widget_placeholder.setLayout(logs_layout)

    def get_active_output_widget_text(self):
        # This method is for the main dialog to get the text from the logs widget
        return self.logs_widget.get_text_for_copy()

    def clear_active_output_widget(self):
        # This method is for the main dialog to clear both widgets
        self.results_widget.clear_log()
        self.logs_widget.clear_log()
        self.logs_widget.log_info("Wyniki i logi zostały wyczyszczone.")

    def setup_connections(self):
        self.refresh_scope_button.clicked.connect(self.refresh_data)
        self.checkbox_full.stateChanged.connect(self._toggle_all_checkboxes)
        self.copy_button.clicked.connect(self.copy_results_to_clipboard)
        self.export_csv_button.clicked.connect(self.export_results_to_csv)
        self.clear_results_button.clicked.connect(self.clear_results)

    def refresh_data(self):
        self._populate_scope_combobox()

    def run_main_action(self):
        self.logs_widget.clear_log()
        self.results_widget.clear_log()
        self.logs_widget.log_info("Uruchomiono generowanie statystyk...")

        selected_scope_feature = self.scope_combobox.currentData()
        if not selected_scope_feature:
            self.logs_widget.log_error("Nie wybrano zakresu zadania. Przerwano operację.")
            return

        if not any(cb.isChecked() for cb in [self.checkbox_lengths, self.checkbox_quantities, self.checkbox_overlaps, self.checkbox_adjacencies, self.checkbox_ids]):
            self.logs_widget.log_warning("Nie wybrano żadnego rodzaju statystyk do wygenerowania.")
            return

        if not selected_scope_feature.geometry() or not selected_scope_feature.geometry().isGeosValid():
            self.logs_widget.log_error("Wybrany zakres ma nieprawidłową geometrię. Przerwano operację.")
            return

        self.logs_widget.log_success("Walidacja pomyślna. Rozpoczynanie obliczeń...")
        self.logs_widget.log_info("<b>UWAGA!</b> Pamiętaj, że każdy obiekt liniowy (np. kabel, trakt) w zakresie zadania jest zliczany, jeśli jego wierzchołek końcowy znajduje się wewnątrz zakresu.")

        if self.checkbox_lengths.isChecked():
            self._calculate_lengths(selected_scope_feature)
        if self.checkbox_quantities.isChecked():
            self._calculate_quantities(selected_scope_feature)
        if self.checkbox_overlaps.isChecked():
            self._check_overlaps(selected_scope_feature)
        if self.checkbox_adjacencies.isChecked():
            self._check_adjacencies(selected_scope_feature)
        if self.checkbox_ids.isChecked():
            self._check_ids(selected_scope_feature)

        self.logs_widget.log_success("Zakończono generowanie statystyk.")

    def clear_results(self):
        self.results_widget.clear_log()
        self.logs_widget.log_info("Wyniki zostały wyczyszczone.")

    def _populate_scope_combobox(self):
        self.scope_combobox.clear()
        self.logs_widget.log_info("Odświeżanie listy zakresów...")
        layer = QgsProject.instance().mapLayersByName("zakres_zadania")
        if not layer:
            self.logs_widget.log_error("Nie znaleziono warstwy 'zakres_zadania'.")
            return

        for feature in layer[0].getFeatures():
            try:
                self.scope_combobox.addItem(feature.attribute("nazwa"), feature)
            except KeyError:
                self.logs_widget.log_error("Warstwa 'zakres_zadania' nie posiada atrybutu 'nazwa'.")
                self.scope_combobox.clear()
                break
        self.logs_widget.log_info(f"Znaleziono {self.scope_combobox.count()} zakresów.")

    def _toggle_all_checkboxes(self, state):
        is_checked = (state == 2)
        checkboxes = [
            self.checkbox_lengths,
            self.checkbox_quantities,
            self.checkbox_overlaps,
            self.checkbox_adjacencies,
            self.checkbox_ids
        ]
        for cb in checkboxes:
            cb.setChecked(is_checked)
            cb.setEnabled(not is_checked)

    def _get_features_in_scope(self, layer_name, scope_geom, is_line=False, all_intersecting=False):
        layer_list = QgsProject.instance().mapLayersByName(layer_name)
        if not layer_list:
            self.logs_widget.log_warning(f"Nie znaleziono warstwy '{layer_name}'.")
            return []
        
        layer = layer_list[0]
        features_in_scope = []
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if not geom or not geom.intersects(scope_geom):
                continue

            if all_intersecting:
                 features_in_scope.append(feature)
                 continue

            if is_line:
                wkb_type = geom.wkbType()
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
                    
                    if last_vertex_point and QgsGeometry.fromPointXY(last_vertex_point).intersects(scope_geom):
                        features_in_scope.append(feature)

                except IndexError:
                    continue
            else:
                features_in_scope.append(feature)
        return features_in_scope

    def _create_html_table(self, headers, rows, title=""):
        html = ""
        if title:
            html += f"<h4>{title}</h4>"
        html += "<table border='1' style='border-collapse: collapse; width: 100%;'>"
        # Headers
        html += "<tr>"
        for header in headers:
            html += f"<th style='padding: 5px; text-align: left;'>{header}</th>"
        html += "</tr>"
        # Rows
        for row in rows:
            html += "<tr>"
            for cell in row:
                html += f"<td style='padding: 5px;'>{cell}</td>"
            html += "</tr>"
        html += "</table>"
        return f'<div style="background-color: #f7f7f9; border: 1px solid #e1e1e8; padding: 8px; border-radius: 4px; margin-top: 5px;">{html}</div>'

    def _calculate_lengths(self, scope_feature):
        final_html_parts = ['<h3><br>&#128207; A) DŁUGOŚCI</h3>']
        scope_geom = scope_feature.geometry()
        scope_mr = scope_feature.attribute('MR') if 'MR' in scope_feature.fields().names() else None

        # --- KABLE ---
        layer_name = "kable"
        cable_layer = QgsProject.instance().mapLayersByName(layer_name)
        if not cable_layer:
            self.logs_widget.log_warning(f"Nie znaleziono warstwy '{layer_name}'.")
        else:
            cable_layer = cable_layer[0]
            
            stats_basic = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {'count': 0, 'dl_tras': 0, 'dl_inst': 0})))
            stats_mr = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {'count': 0, 'dl_tras': 0, 'dl_inst': 0})))

            features_basic = self._get_features_in_scope(layer_name, scope_geom, is_line=True)
            for f in features_basic:
                segment = f.attribute('segment') or "BRAK"
                rodzaj = f.attribute('rodzaj') or "BRAK"
                poj = str(f.attribute('poj')) if f.attribute('poj') else "BRAK"
                dl_tras = f.attribute('dl_tras') or 0
                dl_inst = f.attribute('dl_inst') or 0
                
                stats_basic[segment][rodzaj][poj]['count'] += 1
                stats_basic[segment][rodzaj][poj]['dl_tras'] += dl_tras
                stats_basic[segment][rodzaj][poj]['dl_inst'] += dl_inst

            if scope_mr:
                for f in cable_layer.getFeatures():
                    if f.attribute('MR') and str(f.attribute('MR')) == str(scope_mr):
                        segment = f.attribute('segment') or "BRAK"
                        rodzaj = f.attribute('rodzaj') or "BRAK"
                        poj = str(f.attribute('poj')) if f.attribute('poj') else "BRAK"
                        dl_tras = f.attribute('dl_tras') or 0
                        dl_inst = f.attribute('dl_inst') or 0

                        stats_mr[segment][rodzaj][poj]['count'] += 1
                        stats_mr[segment][rodzaj][poj]['dl_tras'] += dl_tras
                        stats_mr[segment][rodzaj][poj]['dl_inst'] += dl_inst

            def format_cable_report_rows(stats):
                rows = []
                for segment, rodzaje in sorted(stats.items()):
                    seg_count = sum(d['count'] for r in rodzaje.values() for d in r.values())
                    seg_tras = sum(d['dl_tras'] for r in rodzaje.values() for d in r.values())
                    seg_inst = sum(d['dl_inst'] for r in rodzaje.values() for d in r.values())
                    rows.append([f"<b>Segment '{segment}'</b>", f"<b>{seg_count}</b>", f"<b>{seg_tras:.2f}</b>", f"<b>{seg_inst:.2f}</b>"])
                    for rodzaj, pojemnosci in sorted(rodzaje.items()):
                        rodz_count = sum(d['count'] for d in pojemnosci.values())
                        rodz_tras = sum(d['dl_tras'] for d in pojemnosci.values())
                        rodz_inst = sum(d['dl_inst'] for d in pojemnosci.values())
                        rows.append([f"&nbsp;&nbsp;&nbsp;&nbsp;Rodzaj '{rodzaj}'", rodz_count, f"{rodz_tras:.2f}", f"{rodz_inst:.2f}"])
                        for poj, data in sorted(pojemnosci.items()):
                            rows.append([f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Pojemność '{poj}'", data['count'], f"{data['dl_tras']:.2f}", f"{data['dl_inst']:.2f}"])
                return rows

            headers = ["Typ", "Ilość", "Dł. tras. [m]", "Dł. inst. [m]"]
            cable_rows = format_cable_report_rows(stats_basic)
            final_html_parts.append(self._create_html_table(headers, cable_rows, title="Warstwa: kable (Metoda podstawowa)"))
            if scope_mr:
                cable_rows_mr = format_cable_report_rows(stats_mr)
                final_html_parts.append(self._create_html_table(headers, cable_rows_mr, title="Warstwa: kable (Metoda MR)"))
                
                features_in_scope_geom = self._get_features_in_scope(layer_name, scope_geom, all_intersecting=True)
                unique_mr_in_scope = set()
                for f in features_in_scope_geom:
                    mr_val = f.attribute('MR')
                    if mr_val:
                        unique_mr_in_scope.add(str(mr_val))
                
                diagnostic_html = "<div style='font-size: small; margin-left: 10px; margin-top: -5px; margin-bottom: 10px;'>"
                diagnostic_html += f"INFO: Wartość 'MR' w zakresie zadania: <b>{scope_mr}</b><br>"
                if unique_mr_in_scope:
                    diagnostic_html += f"Unikalne wartości 'MR' znalezione wewnątrz geometrii zakresu: <b>{', '.join(sorted(list(unique_mr_in_scope)))}</b>"
                else:
                    diagnostic_html += "Nie znaleziono żadnych obiektów z wartością 'MR' wewnątrz geometrii zakresu."
                diagnostic_html += "</div>"
                final_html_parts.append(diagnostic_html)

        # --- TRAKT ---
        layer_name = "trakt"
        trakt_layer = QgsProject.instance().mapLayersByName(layer_name)
        if not trakt_layer:
            self.logs_widget.log_warning(f"Nie znaleziono warstwy '{layer_name}'.")
        else:
            trakt_layer = trakt_layer[0]
            fields = trakt_layer.fields().names()
            has_dl_inst = 'dl_inst' in fields
            has_dl_tras = 'dl_tras' in fields

            if not has_dl_tras:
                self.logs_widget.log_warning("Warstwa 'trakt' nie posiada atrybutu 'dl_tras'. Zliczanie długości tras dla tej warstwy zostanie pominięte.")
            if not has_dl_inst:
                self.logs_widget.log_warning("Warstwa 'trakt' nie posiada atrybutu 'dl_inst'. Zliczanie długości instalacyjnych dla tej warstwy zostanie pominięte.")

            stats_basic = {}
            stats_mr = {}

            features_basic = self._get_features_in_scope(layer_name, scope_geom, is_line=True)
            for f in features_basic:
                group = f.attribute('trakt') or "BRAK"
                if group not in stats_basic:
                    stats_basic[group] = {'count': 0, 'dl_tras': 0, 'dl_inst': 0}
                stats_basic[group]['count'] += 1
                if has_dl_tras:
                    stats_basic[group]['dl_tras'] += f.attribute('dl_tras') or 0
                if has_dl_inst:
                    stats_basic[group]['dl_inst'] += f.attribute('dl_inst') or 0

            if scope_mr:
                for f in trakt_layer.getFeatures():
                    if f.attribute('MR') and str(f.attribute('MR')) == str(scope_mr):
                        group = f.attribute('trakt') or "BRAK"
                        if group not in stats_mr:
                            stats_mr[group] = {'count': 0, 'dl_tras': 0, 'dl_inst': 0}
                        stats_mr[group]['count'] += 1
                        if has_dl_tras:
                            stats_mr[group]['dl_tras'] += f.attribute('dl_tras') or 0
                        if has_dl_inst:
                            stats_mr[group]['dl_inst'] += f.attribute('dl_inst') or 0

            def format_trakt_report_rows(stats):
                rows = []
                total_count = sum(d['count'] for d in stats.values())
                total_tras = sum(d['dl_tras'] for d in stats.values())
                total_inst = sum(d['dl_inst'] for d in stats.values())
                for group, data in sorted(stats.items()):
                    rows.append([f"Grupa '{group}'", data['count'], f"{data['dl_tras']:.2f}", f"{data['dl_inst']:.2f}"])
                rows.append([f"<b>Suma całkowita</b>", f"<b>{total_count}</b>", f"<b>{total_tras:.2f}</b>", f"<b>{total_inst:.2f}</b>"])
                return rows

            headers = ["Grupa", "Ilość", "Dł. tras. [m]", "Dł. inst. [m]"]
            trakt_rows = format_trakt_report_rows(stats_basic)
            final_html_parts.append(self._create_html_table(headers, trakt_rows, title="Warstwa: trakt (Metoda podstawowa)"))
            if scope_mr:
                trakt_rows_mr = format_trakt_report_rows(stats_mr)
                final_html_parts.append(self._create_html_table(headers, trakt_rows_mr, title="Warstwa: trakt (Metoda MR)"))

                features_in_scope_geom = self._get_features_in_scope(layer_name, scope_geom, all_intersecting=True)
                unique_mr_in_scope = set()
                for f in features_in_scope_geom:
                    mr_val = f.attribute('MR')
                    if mr_val:
                        unique_mr_in_scope.add(str(mr_val))
                
                diagnostic_html = "<div style='font-size: small; margin-left: 10px; margin-top: -5px; margin-bottom: 10px;'>"
                diagnostic_html += f"INFO: Wartość 'MR' w zakresie zadania: <b>{scope_mr}</b><br>"
                if unique_mr_in_scope:
                    diagnostic_html += f"Unikalne wartości 'MR' znalezione wewnątrz geometrii zakresu: <b>{', '.join(sorted(list(unique_mr_in_scope)))}</b>"
                else:
                    diagnostic_html += "Nie znaleziono żadnych obiektów z wartością 'MR' wewnątrz geometrii zakresu."
                diagnostic_html += "</div>"
                final_html_parts.append(diagnostic_html)

        self.results_widget.output_console.append("<br>".join(final_html_parts))

    def _calculate_quantities(self, scope_feature):
        final_html_parts = ['<h3><br>&#128200; B) ILOŚCI</h3>']
        scope_geom = scope_feature.geometry()

        # --- lista_pa ---
        features = self._get_features_in_scope("lista_pa", scope_geom)
        if features:
            rows = []
            total_count = len(features)
            sum_lokal = sum(f.attribute('Licz_lokal') or 0 for f in features)
            sum_przed = sum(f.attribute('Licz_przed') or 0 for f in features)
            sum_sed = sum(f.attribute('Licz_SED') or 0 for f in features)
            
            rows.append(["Ilość obiektów w zakresie", total_count])
            rows.append(["Suma 'Licz_lokal'", sum_lokal])
            rows.append(["Suma 'Licz_przed'", sum_przed])
            rows.append(["Suma 'Licz_SED'", sum_sed])

            stats_rodzaj = defaultdict(int)
            for f in features:
                rodzaj = f.attribute('Rodzaj pun') or "BRAK"
                stats_rodzaj[rodzaj] += 1
            
            rows.append(["<b>Podział wg 'Rodzaj_pun':</b>", ""])
            for rodzaj, count in sorted(stats_rodzaj.items()):
                rows.append([f"&nbsp;&nbsp;&nbsp;&nbsp;'{rodzaj}'", f"{count} obiektów"])
            
            final_html_parts.append(self._create_html_table(["Metryka", "Wartość"], rows, title="Warstwa: lista_pa"))

        # --- punkty_elastycznosci ---
        features = self._get_features_in_scope("punkty_elastycznosci", scope_geom)
        if features:
            rows = []
            total_count = len(features)
            sum_lspl = sum(f.attribute('l_spl') or 0 for f in features)
            
            rows.append(["Ilość obiektów w zakresie", total_count])
            rows.append(["Suma 'l_spl'", sum_lspl])

            stats_group = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
            for f in features:
                typ = f.attribute('typ') or "BRAK"
                status = f.attribute('status') or "BRAK"
                rodzaj = f.attribute('rodzaj') or "BRAK"
                stats_group[typ][status][rodzaj] += 1
            
            rows.append(["<b>Podział wg 'typ' -> 'status' -> 'rodzaj':</b>", ""])
            for typ, statuses in sorted(stats_group.items()):
                rows.append([f"<b>Typ '{typ}'</b>", ""])
                for status, rodzaje in sorted(statuses.items()):
                    rows.append([f"&nbsp;&nbsp;&nbsp;&nbsp;Status '{status}'", ""])
                    for rodzaj, count in sorted(rodzaje.items()):
                        rows.append([f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Rodzaj '{rodzaj}'", f"{count} obiektów"])

            l_spl_errors = 0
            splitter_logic_errors = 0
            for f in features:
                l_spl = f.attribute('l_spl')
                if l_spl is not None and not (0 <= l_spl <= 3):
                    l_spl_errors += 1
                
                splitter_fields = [f.attribute('spl_i-rz'), f.attribute('spl_ii-rz'), f.attribute('spl_iii-rz')]
                non_brak_splitters = sum(1 for s in splitter_fields if s and s != 'BRAK')
                
                if non_brak_splitters > 0 and (l_spl is None or l_spl <= 0):
                    splitter_logic_errors += 1
                elif non_brak_splitters == 1 and (l_spl is None or l_spl <= 0):
                     splitter_logic_errors += 1
                elif non_brak_splitters == 2 and (l_spl is None or l_spl <= 1):
                     splitter_logic_errors += 1
                elif non_brak_splitters == 3 and (l_spl is None or l_spl <= 2):
                     splitter_logic_errors += 1

            rows.append(["<b>Walidacja:</b>", ""])
            rows.append(["Ilość obiektów z 'l_spl' poza zakresem 0-3", f"<font color='red'>{l_spl_errors}</font>"])
            rows.append(["Ilość obiektów z błędną logiką liczby spliterów", f"<font color='red'>{splitter_logic_errors}</font>"])

            final_html_parts.append(self._create_html_table(["Metryka", "Wartość"], rows, title="Warstwa: punkty_elastycznosci"))

        # --- obiekty_punktowe ---
        features = self._get_features_in_scope("obiekty_punktowe", scope_geom)
        if features:
            rows = []
            rows.append([f"Ilość obiektów w zakresie: {len(features)}", ""])
            
            stats_group = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
            for f in features:
                rodzaj = f.attribute('rodzaj') or "BRAK"
                status = f.attribute('status') or "BRAK"
                model = f.attribute('model') or "BRAK"
                stats_group[rodzaj][status][model] += 1

            rows.append(["<b>Podział wg 'rodzaj' -> 'status' -> 'model':</b>", ""])
            for rodzaj, statuses in sorted(stats_group.items()):
                rows.append([f"<b>Rodzaj '{rodzaj}'</b>", ""])
                for status, modele in sorted(statuses.items()):
                    rows.append([f"&nbsp;&nbsp;&nbsp;&nbsp;Status '{status}'", ""])
                    for model, count in sorted(modele.items()):
                        rows.append([f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Model '{model}'", f"{count} obiektów"])
            final_html_parts.append(self._create_html_table(["Metryka", "Wartość"], rows, title="Warstwa: obiekty_punktowe"))

        # --- obiekty_osłonowe ---
        features = self._get_features_in_scope("obiekty_osłonowe", scope_geom, is_line=True)
        if features:
            rows = []
            stats_group = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'dl_tras': 0, 'dl_inst': 0}))
            for f in features:
                rodzaj = f.attribute('rodzaj') or "BRAK"
                model = f.attribute('model') or "BRAK"
                stats_group[rodzaj][model]['count'] += 1
                stats_group[rodzaj][model]['dl_tras'] += f.attribute('dl_tras') or 0
                stats_group[rodzaj][model]['dl_inst'] += f.attribute('dl_inst') or 0
            
            rows.append(["<b>Podział wg 'rodzaj' -> 'model':</b>", "", "", ""])
            for rodzaj, modele in sorted(stats_group.items()):
                rodzaj_count = sum(d['count'] for d in modele.values())
                rodzaj_tras = sum(d['dl_tras'] for d in modele.values())
                rodzaj_inst = sum(d['dl_inst'] for d in modele.values())
                rows.append([f"<b>Rodzaj '{rodzaj}'</b>", f"{rodzaj_count}", f"{rodzaj_tras:.2f}", f"{rodzaj_inst:.2f}"])
                for model, data in sorted(modele.items()):
                    rows.append([f"&nbsp;&nbsp;&nbsp;&nbsp;Model '{model}'", data['count'], f"{data['dl_tras']:.2f}", f"{data['dl_inst']:.2f}"])
            final_html_parts.append(self._create_html_table(["Typ", "Ilość", "Dł. tras. [m]", "Dł. inst. [m]"], rows, title="Warstwa: obiekty_osłonowe"))

        # --- Warstwy z wykorzystaniem infrastruktury ---
        for layer_name in ["nN_nn", "slupy_opl", "studnie_opl"]:
            features = self._get_features_in_scope(layer_name, scope_geom, all_intersecting=True)
            if features:
                rows = []
                total_count = len(features)
                wykorzystane_count = sum(1 for f in features if f.attribute('X_wykorzystanie') == 'TAK')
                rows.append(["Ilość obiektów w zakresie", total_count])
                rows.append(["Ilość z 'X_wykorzystanie' = TAK", wykorzystane_count])
                final_html_parts.append(self._create_html_table(["Metryka", "Wartość"], rows, title=f"Warstwa: {layer_name}"))

        # --- dzialki_raport ---
        features = self._get_features_in_scope("działki_raport", scope_geom)
        if features:
            rows = []
            rows.append([f"Ilość obiektów w zakresie: {len(features)}", ""])

            stats_group = defaultdict(lambda: defaultdict(int))
            for f in features:
                zgoda = f.attribute('zgoda_dz') or "BRAK"
                wlasnosc = f.attribute('wlasn_dz') or "BRAK"
                stats_group[zgoda][wlasnosc] += 1
            
            rows.append(["<b>Podział wg 'zgoda_dz' -> 'wlasn_dz':</b>", ""])
            for zgoda, wlasnosci in sorted(stats_group.items()):
                rows.append([f"<b>Zgoda '{zgoda}'</b>", ""])
                for wlasnosc, count in sorted(wlasnosci.items()):
                    rows.append([f"&nbsp;&nbsp;&nbsp;&nbsp;Własność '{wlasnosc}'", f"{count} obiektów"])
            final_html_parts.append(self._create_html_table(["Metryka", "Wartość"], rows, title="Warstwa: działki_raport"))
        
        self.results_widget.output_console.append("<br>".join(final_html_parts))

    def _check_overlaps(self, scope_feature):
        final_html_parts = ['<h3><br>&#128230; C) NAKŁADKI</h3>']
        scope_geom = scope_feature.geometry()
        
        for layer_name in ["kable", "trakt"]:
            layer = QgsProject.instance().mapLayersByName(layer_name)
            if not layer:
                self.logs_widget.log_warning(f"Nie znaleziono warstwy '{layer_name}' do sprawdzenia nakładek.")
                continue
            layer = layer[0]

            features = self._get_features_in_scope(layer_name, scope_geom, is_line=True, all_intersecting=True)
            if not features:
                rows = [["Brak obiektów w zakresie.", ""]]
                final_html_parts.append(self._create_html_table([], rows, title=f"Warstwa: {layer_name}"))
                continue

            index = QgsSpatialIndex()
            feat_map = {}
            for f in features:
                index.addFeature(f)
                feat_map[f.id()] = f

            overlapping_fids = set()
            
            for feat1 in features:
                candidate_ids = index.intersects(feat1.geometry().boundingBox())
                for fid in candidate_ids:
                    if feat1.id() >= fid:
                        continue
                    
                    feat2 = feat_map.get(fid)
                    if not feat2:
                        continue

                    intersection = feat1.geometry().intersection(feat2.geometry())
                    if not intersection.isEmpty() and intersection.wkbType() in [QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString]:
                        overlapping_fids.add(feat1.id())
                        overlapping_fids.add(feat2.id())

            rows = []
            if overlapping_fids:
                headers = ["ID", "Nazwa", "Dł. tras. [m]"]
                rows.append([f"<font color='red'>Znaleziono {len(overlapping_fids)} nakładających się obiektów:</font>", "", ""])
                for fid in overlapping_fids:
                    f = feat_map.get(fid)
                    if f:
                        rows.append([f.attribute("id"), f.attribute("nazwa"), f"{f.attribute('dl_tras'):.2f}"])
                final_html_parts.append(self._create_html_table(headers, rows, title=f"Warstwa: {layer_name}"))
            else:
                rows.append(["<font color='green'>Brak nakładających się obiektów.</font>", ""])
                final_html_parts.append(self._create_html_table([], rows, title=f"Warstwa: {layer_name}"))
        
        self.results_widget.output_console.append("<br>".join(final_html_parts))

    def _check_adjacencies(self, scope_feature):
        final_html_parts = ['<h3><br>&#128279; D) STYCZNOŚCI</h3>']
        scope_geom = scope_feature.geometry()
        infra_layers = ['obiekty_punktowe', 'punkty_elastycznosci', 'studnie_opl', 'slupy_opl']
        
        infra_features = []
        for layer_name in infra_layers:
            infra_features.extend(self._get_features_in_scope(layer_name, scope_geom, all_intersecting=True))

        if not infra_features:
            self.logs_widget.log_warning("Brak warstw infrastruktury do sprawdzania styczności.")
            return
            
        infra_index = QgsSpatialIndex()
        for f in infra_features:
            infra_index.addFeature(f)

        for layer_name in ["kable", "trakt"]:
            layer = QgsProject.instance().mapLayersByName(layer_name)
            if not layer:
                self.logs_widget.log_warning(f"Nie znaleziono warstwy '{layer_name}' do sprawdzenia styczności.")
                continue
            layer = layer[0]

            features = self._get_features_in_scope(layer_name, scope_geom, is_line=True)
            if not features:
                rows = [["Brak obiektów w zakresie.", ""]]
                final_html_parts.append(self._create_html_table([], rows, title=f"Warstwa: {layer_name}"))
                continue

            unconnected_features = []
            for f in features:
                geom = f.geometry()
                is_connected = True
                for vertex in geom.vertices():
                    vertex_geom = QgsGeometry(vertex)
                    # Use a small buffer for intersection check to handle precision issues
                    if not infra_index.intersects(vertex_geom.buffer(0.1, 5).boundingBox()):
                        is_connected = False
                        break
                if not is_connected:
                    unconnected_features.append(f)
            
            rows = []
            if unconnected_features:
                headers = ["ID", "Nazwa", "Dł. tras. [m]"]
                rows.append([f"<font color='red'>Znaleziono {len(unconnected_features)} obiektów z wierzchołkami bez styczności:</font>", "", ""])
                for f in unconnected_features:
                     rows.append([f.attribute("id"), f.attribute("nazwa"), f"{f.attribute('dl_tras'):.2f}"])
                final_html_parts.append(self._create_html_table(headers, rows, title=f"Warstwa: {layer_name}"))
            else:
                rows.append(["<font color='green'>Wszystkie obiekty mają zachowaną styczność.</font>", ""])
                final_html_parts.append(self._create_html_table([], rows, title=f"Warstwa: {layer_name}"))
        
        self.results_widget.output_console.append("<br>".join(final_html_parts))


    def _check_ids(self, scope_feature):
        final_html_parts = ['<h3><br>&#128273; E) ID</h3>']
        scope_geom = scope_feature.geometry()
        layers_to_check = ["kable", "trakt", "punkty_elastycznosci", "obiekty_punktowe", "obiekty_osłonowe", "zakres_splitera"]

        for layer_name in layers_to_check:
            rows = []
            layer_list = QgsProject.instance().mapLayersByName(layer_name)
            if not layer_list:
                rows.append([f"<font color='orange'>Nie znaleziono warstwy.</font>", ""])
                final_html_parts.append(self._create_html_table([], rows, title=f"Warstwa: {layer_name}"))
                continue

            layer = layer_list[0]
            if 'id' not in layer.fields().names():
                rows.append([f"<font color='orange'>Warstwa nie posiada atrybutu 'id'.</font>", ""])
                final_html_parts.append(self._create_html_table([], rows, title=f"Warstwa: {layer_name}"))
                continue

            features = self._get_features_in_scope(layer_name, scope_geom, all_intersecting=True)
            if not features:
                rows.append(["Brak obiektów w zakresie.", ""])
                final_html_parts.append(self._create_html_table([], rows, title=f"Warstwa: {layer_name}"))
                continue

            ids = defaultdict(list)
            missing_id_count = 0
            for f in features:
                fid = f.attribute('id')
                if fid:
                    ids[fid].append(f.id())
                else:
                    missing_id_count += 1
            
            duplicates = {k: v for k, v in ids.items() if len(v) > 1}

            rows.append(["Unikalne ID", len(ids)])
            if missing_id_count > 0:
                rows.append([f"<font color='red'>Brakujące ID</font>", missing_id_count])
            
            if duplicates:
                rows.append([f"<font color='red'>Powielone ID ({len(duplicates)}):</font>", ""])
                for dup_id, fids in duplicates.items():
                    rows.append([f"&nbsp;&nbsp;&nbsp;&nbsp;ID '{dup_id}'", f"występuje {len(fids)} razy"])
            
            if missing_id_count == 0 and not duplicates:
                 rows.append(["<font color='green'>Wszystkie obiekty posiadają unikalne ID.</font>", ""])

            final_html_parts.append(self._create_html_table(["Metryka", "Wartość"], rows, title=f"Warstwa: {layer_name}"))
        
        self.results_widget.output_console.append("<br>".join(final_html_parts))

    def copy_results_to_clipboard(self):
        QApplication.clipboard().setText(self.results_widget.get_text_for_copy())
        self.logs_widget.log_success("Wyniki skopiowano do schowka.")

    def export_results_to_csv(self):
        self.logs_widget.log_info("Funkcjonalność eksportu do CSV jest w trakcie implementacji.")
        # TODO: Implement export to CSV
        pass
