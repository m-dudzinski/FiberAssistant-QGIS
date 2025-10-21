import os

from qgis.PyQt import uic, QtCore
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QListWidgetItem, QPushButton, QHBoxLayout, QFileDialog, QLabel, QApplication, QMessageBox
from qgis.PyQt.QtGui import QIcon

from .core.logger import logger
from . import resources

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'ui/main_window.ui'))

from .functionalities.wyszukiwarka import WyszukiwarkaWidget
from .functionalities.statystyka import StatystykaWidget
from .functionalities.walidator import WalidatorWidget
from .functionalities.przeliczanie_dlugosci import PrzeliczanieDlugosciWidget
from .functionalities.dane_podstawowe_projektu import DanePodstawoweProjektuWidget
from .functionalities.zarzadzanie_kablami import ZarzadzanieKabliWidget
from .functionalities.zarzadzanie_PA import ZarzadzaniePAWidget
from .functionalities.zarzadzanie_PE import ZarzadzaniePEWidget
from .functionalities.karta_krosowan import KartaKrosowanWidget
from .functionalities.stycznosc_wierzcholkow import StycznoscWierzcholkowWidget
from .functionalities.wykorzystanie_infrastruktury import WykorzystanieInfrastrukturyWidget
from .functionalities.elementy_niewybudowane import ElementyNiewybudowaneWidget
from .functionalities.raport_miesieczny_qgis import RaportMiesiecznyQgisWidget
from .functionalities.raport_polroczny_qgis import RaportPolrocznyQgisWidget
from .functionalities.funkcjonalnosci_dla_tok import FunkcjonalnosciDlaTokWidget
from .functionalities.uzupelnianie_struktury_projektu import UzupelnianieStrukturyProjektuWidget
from .functionalities.czyszczenie import CzyszczenieWidget
from .functionalities.funkcje_w_fazie_testow import FunkcjeWFazieTestowWidget
from .functionalities.logi import LogiWidget
from .dialogs.settings_dialog import SettingsDialog

class FiberAssistantDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        super(FiberAssistantDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)
        
        # --- UI Customization ---
        self.setWindowTitle("Fiber Assistant")
        self.resize(1100, 800)
        self.setMinimumSize(800, 500)
        self.main_menu_widget.setStyleSheet("""            
            QListWidget::item { padding-left: 2px; }
            QListWidget::item:selected { background-color: #EFE4B0; color: #000000; }
        """)

        # --- Persistent Log Dialog --- 
        self.log_widget = LogiWidget(self)
        self.log_dialog = QDialog(self)
        self.log_dialog.setWindowTitle("Pełna Konsola Logów Fiber Assistant")
        self.log_dialog.setLayout(QVBoxLayout())
        self.log_dialog.layout().addWidget(self.log_widget)
        self.log_dialog.resize(800, 400)
        
        logger.set_full_log_widget(self.log_widget.log_text_edit) # Connect full log console
        self.log_widget.export_requested.connect(self._export_logs_to_file)

        # --- Dynamic Functionality Loading ---
        from .core.functionalities_menu_list import ENABLED_FUNCTIONALITIES

        # A map containing all possible functionalities and their metadata.
        # The key corresponds to the identifier in `functionalities_menu_list.py`.
        self.ALL_FUNCTIONALITIES_MAP = {
            "wyszukiwarka": {"class": WyszukiwarkaWidget, "name": "Wyszukiwarka", "icon": ":/icons/functions_icons/function_icon_wyszukiwarka.png", "description": "Szukanie obiektów według wartości ich atrybutów.", "init": lambda: WyszukiwarkaWidget(self.iface, self)},
            "statystyka": {"class": StatystykaWidget, "name": "Statystyka", "icon": ":/icons/functions_icons/function_icon_statystyka.png", "description": "Przygotowanie statystyki szczegółowej projektu.", "init": lambda: StatystykaWidget(self)},
            "walidator": {"class": WalidatorWidget, "name": "Walidator", "icon": ":/icons/functions_icons/function_icon_walidator.png", "description": "Sprawdzanie struktury projektu względem wzorca.", "init": lambda: WalidatorWidget(self)},
            "przeliczanie_dlugosci": {"class": PrzeliczanieDlugosciWidget, "name": "Przeliczanie długości", "icon": ":/icons/functions_icons/function_icon_przeliczanie_dlugosci.png", "description": "Kalkulator długości elementów liniowych.", "init": lambda: PrzeliczanieDlugosciWidget(self.iface, self)},
            "dane_podstawowe_projektu": {"class": DanePodstawoweProjektuWidget, "name": "Dane podstawowe projektu", "icon": ":/icons/functions_icons/function_icon_dane_podstawowe_projektu.png", "description": "Masowe wprowadzanie danych projektu.", "init": lambda: DanePodstawoweProjektuWidget(self)},
            "zarzadzanie_kablami": {"class": ZarzadzanieKabliWidget, "name": "Zarządzanie kablami", "icon": ":/icons/functions_icons/function_icon_zarzadzanie_kablami.png", "description": "Masowe ustawianie atrybutów kabli.", "init": lambda: ZarzadzanieKabliWidget(self)},
            "zarzadzanie_PA": {"class": ZarzadzaniePAWidget, "name": "Zarządzanie PA", "icon": ":/icons/functions_icons/function_icon_zarzadzanie_PA.png", "description": "Masowe ustawianie atrybutów PA.", "init": lambda: ZarzadzaniePAWidget(self)},
            "zarzadzanie_PE": {"class": ZarzadzaniePEWidget, "name": "Zarządzanie PE", "icon": ":/icons/functions_icons/function_icon_zarzadzanie_PE.png", "description": "Masowe ustawianie atrybutów dla PE.", "init": lambda: ZarzadzaniePEWidget(self)},
            "karta_krosowan": {"class": KartaKrosowanWidget, "name": "Karta krosowań", "icon": ":/icons/functions_icons/function_icon_karta_krosowan.png", "description": "Przypisywanie adresom portów zasilających.", "init": lambda: KartaKrosowanWidget(self)},
            "stycznosc_wierzcholkow": {"class": StycznoscWierzcholkowWidget, "name": "Styczność wierzchołków", "icon": ":/icons/functions_icons/function_icon_stycznosc_wierzcholkow.png", "description": "Weryfikacja prawidłowego dociągnięcia obiektów.", "init": lambda: StycznoscWierzcholkowWidget(self)},
            "wykorzystanie_infrastruktury": {"class": WykorzystanieInfrastrukturyWidget, "name": "Wykorzystanie infrastruktury", "icon": ":/icons/functions_icons/function_icon_wykorzystanie_infrastruktury.png", "description": "Masowe ustawienie atrybutu o wykorzystaniu obiektów.", "init": lambda: WykorzystanieInfrastrukturyWidget(self)},
            "elementy_niewybudowane": {"class": ElementyNiewybudowaneWidget, "name": "Elementy niewybudowane", "icon": ":/icons/functions_icons/function_icon_elementy_niewybudowane.png", "description": "Przenoszenie obiektów na warstwy robocze.", "init": lambda: ElementyNiewybudowaneWidget(self)},
            "raport_miesieczny_qgis": {"class": RaportMiesiecznyQgisWidget, "name": "Raport miesięczny QGIS", "icon": ":/icons/functions_icons/function_icon_raport_miesieczny_qgis.png", "description": "Masowe przenoszenie obiektów do warstw raportowych.", "init": lambda: RaportMiesiecznyQgisWidget(self)},
            "raport_polroczny_qgis": {"class": RaportPolrocznyQgisWidget, "name": "Raport półroczny QGIS", "icon": ":/icons/functions_icons/function_icon_raport_polroczny_qgis.png", "description": "Masowe przenoszenie obiektów do warstw raportowych.", "init": lambda: RaportPolrocznyQgisWidget(self)},
            "funkcjonalnosci_dla_tok": {"class": FunkcjonalnosciDlaTokWidget, "name": "Funkcjonalności dla TOK", "icon": ":/icons/functions_icons/function_icon_funkcjonalnosci_dla_tok.png", "description": "Dedykowane działania pod wymogi inwestora.", "init": lambda: FunkcjonalnosciDlaTokWidget(self)},
            "uzupelnianie_struktury_projektu": {"class": UzupelnianieStrukturyProjektuWidget, "name": "Uzupełnianie struktury projektu", "icon": ":/icons/functions_icons/function_icon_uzupelnianie_struktury_projektu.png", "description": "Generator, konfigurator i walidator w jednym.", "init": lambda: UzupelnianieStrukturyProjektuWidget(self)},
            "czyszczenie": {"class": CzyszczenieWidget, "name": "Czyszczenie", "icon": ":/icons/functions_icons/function_icon_czyszczenie.png", "description": "Masowe usuwanie dubli i obiektów z błędną geometrią.", "init": lambda: CzyszczenieWidget(self.iface, self)},
            "funkcje_w_fazie_testow": {"class": FunkcjeWFazieTestowWidget, "name": "Funkcje w fazie testów", "icon": ":/icons/functions_icons/function_icon_funkcje_w_fazie_testow.png", "description": "Funkcjonalności eksperymentalne w trakcie testów.", "init": lambda: FunkcjeWFazieTestowWidget(self)}
        }

        self.functionalities = []
        for func_id in ENABLED_FUNCTIONALITIES:
            if func_id in self.ALL_FUNCTIONALITIES_MAP:
                func_data = self.ALL_FUNCTIONALITIES_MAP[func_id]
                self.functionalities.append({
                    "name": func_data["name"],
                    "icon": func_data["icon"],
                    "description": func_data["description"],
                    "widget": func_data["init"]()
                })
            else:
                logger.warning(f"Funkcjonalność '{func_id}' z pliku konfiguracyjnego nie została znaleziona w mapie funkcjonalności.")

        self.setup_function_pages()
        self.populate_main_menu()

        # --- Connections ---
        self.main_menu_widget.currentRowChanged.connect(self.function_stacked_widget.setCurrentIndex)
        self.main_menu_widget.currentRowChanged.connect(self._update_run_button_visibility)
        self.main_menu_widget.currentRowChanged.connect(self.set_status_ready)
        self.show_logs_button.clicked.connect(self._show_logs_dialog)
        self.refresh_button.clicked.connect(self._refresh_content)
        self.export_button.clicked.connect(self._export_content)
        self.copy_button.clicked.connect(self._copy_content)
        self.clean_button.clicked.connect(self._clean_content)
        self.settings_button.clicked.connect(self._open_settings)
        self.help_button.clicked.connect(self._open_help)

        # Connect the global run button
        self.run_button.clicked.connect(self._on_run_button_clicked)

        # --- Tab change handling for logger scoping ---
        self.previous_row = -1
        self.main_menu_widget.currentRowChanged.connect(self._on_menu_row_changed)

        # Set initial visibility for the run button and activate the first widget
        self._update_run_button_visibility(0)
        self._on_menu_row_changed(0) # Activate the first widget

        # --- Initial Log Messages ---
        logger.info("Wtyczka Fiber Assistant uruchomiona.")
        logger.debug("Tryb debugowania aktywny.")
        self.set_status_ready()

    def _on_menu_row_changed(self, current_row):
        # Deactivate the old widget's logger
        if self.previous_row > -1 and self.previous_row < len(self.functionalities):
            old_widget = self.functionalities[self.previous_row].get('widget')
            if old_widget and hasattr(old_widget, 'deactivate'):
                old_widget.deactivate()
                logger.debug(f"Deactivated logger for {old_widget.__class__.__name__}")

        # Activate the new widget's logger
        if current_row > -1 and current_row < len(self.functionalities):
            new_widget = self.functionalities[current_row].get('widget')
            if new_widget and hasattr(new_widget, 'activate'):
                new_widget.activate()
                logger.debug(f"Activated logger for {new_widget.__class__.__name__}")

        self.previous_row = current_row

    def _on_run_button_clicked(self):
        logger.debug("Global run button clicked.")
        current_widget = self._get_current_func_widget()
        if current_widget:
            logger.debug(f"Current active widget: {current_widget.__class__.__name__}")
            if hasattr(current_widget, 'run_main_action'):
                logger.debug(f"Calling run_main_action on {current_widget.__class__.__name__}")
                current_widget.run_main_action()
            else:
                logger.warning(f"Aktywna funkcjonalność ({current_widget.__class__.__name__}) nie posiada metody 'run_main_action'.")
                self.show_status_message("Brak akcji do wykonania dla tej funkcjonalności.")
        else:
            logger.warning("Brak aktywnego widżetu funkcjonalności.")
            self.show_status_message("Brak aktywnej funkcjonalności do uruchomienia.")

    def show_status_message(self, message, timeout=5000):
        self.status_label.setText(message)
        if timeout > 0:
            QTimer.singleShot(timeout, self.set_status_ready)

    def set_status_ready(self, index=None):
        self.status_label.setText("Gotowy")

    def setup_function_pages(self):
        for i, func in enumerate(self.functionalities):
            # Each page of the stacked widget is pre-created in the UI file.
            # We just need to set a layout and add our custom widget to it.
            page = self.function_stacked_widget.widget(i)
            if not page.layout():
                layout = QVBoxLayout(page)
                layout.setContentsMargins(0, 0, 0, 0)
                page.setLayout(layout)
            page.layout().addWidget(func['widget'])

    def populate_main_menu(self):
        for func in self.functionalities:
            item = QListWidgetItem(self.main_menu_widget)
            label = QLabel(f"<b>{func['name']}</b><br/><font size='-1'>{func['description']}</font>")
            label.setTextFormat(QtCore.Qt.RichText)
            label.setWordWrap(True)
            item.setSizeHint(label.sizeHint())
            if func['icon']:
                item.setIcon(QIcon(func['icon']))
            self.main_menu_widget.addItem(item)
            self.main_menu_widget.setItemWidget(item, label)

    def _get_current_func_widget(self):
        current_page = self.function_stacked_widget.currentWidget()
        if current_page and current_page.layout() and current_page.layout().count() > 0:
            return current_page.layout().itemAt(0).widget()
        return None

    def _update_run_button_visibility(self, index):
        """Shows the main run button only for functionalities that require it."""
        RUN_BUTTON_WHITELIST = [
            "Dane podstawowe projektu",
            "Przeliczanie długości"
        ]

        if index < len(self.functionalities):
            selected_function_name = self.functionalities[index]["name"]
            if selected_function_name in RUN_BUTTON_WHITELIST:
                self.run_button.setVisible(True)
            else:
                self.run_button.setVisible(False)
        else:
            self.run_button.setVisible(False)

    def _show_logs_dialog(self):
        self.log_dialog.show()

    def _export_logs_to_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Eksportuj logi", "", "Pliki tekstowe (*.txt)")
        if file_path:
            logger.export_logs(file_path)
            logger.info(f"Logi wyeksportowano do: {file_path}")

    def _export_content(self):
        widget = self._get_current_func_widget()
        content = None
        if hasattr(widget, 'get_active_output_widget_text'):
            content = widget.get_active_output_widget_text()
        elif widget and hasattr(widget, 'output_widget'):
            content = widget.output_widget.get_text_for_copy()
        
        if content is not None:
            file_path, _ = QFileDialog.getSaveFileName(self, "Eksportuj do pliku .txt", "", "Pliki tekstowe (*.txt)")
            if file_path:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.info(f"Pomyślnie wyeksportowano do: {file_path}")
                    self.show_status_message(f"Pomyślnie wyeksportowano do: {os.path.basename(file_path)}")
                except Exception as e:
                    logger.error(f"Błąd podczas eksportu do pliku: {e}")
                    self.show_status_message("Błąd eksportu.", 5000)
        else:
            logger.warning("Brak aktywnego okna z zawartością do wyeksportowania.")

    def _copy_content(self):
        widget = self._get_current_func_widget()
        content = None
        if hasattr(widget, 'get_active_output_widget_text'):
            content = widget.get_active_output_widget_text()
        elif widget and hasattr(widget, 'output_widget'):
            content = widget.output_widget.get_text_for_copy()

        if content is not None:
            clipboard = QApplication.clipboard()
            clipboard.setText(content)
            logger.info("Skopiowano zawartość do schowka.")
            self.show_status_message("Skopiowano do schowka.")
        else:
            logger.warning("Brak aktywnego okna z zawartością do skopiowania.")

    def _refresh_content(self):
        logger.info("Globalne odświeżanie zostało zainicjowane przez użytkownika.")
        self.broadcast_refresh_request()
        self.show_status_message("Dane wtyczki zostały odświeżone.")

    def _clean_content(self):
        widget = self._get_current_func_widget()
        
        # Special handling for widgets with multiple or custom-named output widgets
        if hasattr(widget, 'clear_active_output_widget'):
            widget.clear_active_output_widget()
            logger.info(f"Wyczyszczono aktywne okno komunikatów dla {widget.__class__.__name__}.")
            self.show_status_message("Wyczyszczono okno komunikatów.")
        elif widget and hasattr(widget, 'output_widget'):
            # Generic case for widgets with a single 'output_widget'
            widget.output_widget.clear_log()
            logger.info("Wyczyszczono okno komunikatów.")
            self.show_status_message("Wyczyszczono okno komunikatów.")
        else:
            logger.warning("Brak aktywnego okna do wyczyszczenia lub widget nie obsługuje czyszczenia.")

    def _open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec_()

    def broadcast_settings_changed(self):
        logger.info("Ustawienia zostały zmienione. Aktualizowanie interfejsu...")
        for func in self.functionalities:
            widget = func.get('widget')
            if widget and hasattr(widget, 'on_settings_changed'):
                widget.on_settings_changed()

    def broadcast_refresh_request(self):
        logger.info("Rozgłaszanie żądania odświeżenia do wszystkich modułów...")
        for func in self.functionalities:
            widget = func.get('widget')
            if widget and hasattr(widget, 'refresh_data'):
                logger.debug(f"Wywoływanie refresh_data() dla {widget.__class__.__name__}")
                widget.refresh_data()

    def _open_help(self):
        QMessageBox.information(self, "Pomoc", "Funkcjonalność pomocy nie została jeszcze zaimplementowana.")
        logger.info("Kliknięto przycisk pomocy (funkcjonalność w przygotowaniu).")