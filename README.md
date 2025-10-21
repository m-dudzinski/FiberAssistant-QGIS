# FiberAssistant

[!ENG DESCRIPTION BELOW!]

Jest to autorska wtyczka dla programu QGIS, usprawniająca proces projektowania FTTH.

## :warning: Status: Wersja Beta

Projekt znajduje się obecnie w aktywnej fazie rozwoju i testów. Główne funkcjonalności są w trakcie tworzenia i walidacji.

W związku z tym, wtyczka może zawierać błędy, działać niestabilnie lub powodować nieoczekiwane rezultaty. Zalecana jest szczególna ostrożność.

**Przed użyciem wtyczki na ważnych danych, prosimy zawsze pracować na kopii zapasowej projektu QGIS (.qgz) oraz źródłowych warstw danych.** Pomoże to zabezpieczyć dane przed ich przypadkową utratą lub trwałym uszkodzeniem.

## Instalacja

Wtyczka nie jest jeszcze dostępna w oficjalnym repozytorium wtyczek QGIS. Zostanie tam dodana po zakończeniu fazy intensywnych testów.

Aby zainstalować wtyczkę ręcznie:

1.  Pobierz najnowszą wersję wtyczki (np. klikając `Code` -> `Download ZIP` i rozpakowując archiwum, lub pobierając z zakładki `Releases`, jeśli ją utworzyłeś).

Domyślnie plik `resources.py` (zawierający ikony i zasoby) nie istnieje w repozytorium, trzeba wygenerować go ręcznie. Do tego celu w systemie Windows najłatwiej jest użyć terminala **OSGeo4W Shell**, który jest instalowany razem z QGIS:

    1.1) Otwórz **OSGeo4W Shell** (znajdziesz go w Menu Start).
    1.2) Przejdź do głównego folderu wtyczki (tego, który zawiera plik `resources.qrc`) używając polecenia `cd`. Przykład:
    ```bash
    # Pamiętaj, aby podać ścieżkę do folderu, w którym jest plik .qrc
    cd C:\sciezka\do\twojego\repo\FiberAssistant\FiberAssistant
    ```
    1.3) Uruchom kompilator zasobów PyQGIS (`pyrcc5`), aby zamienić plik `.qrc` na plik `.py`:
    ```bash
    pyrcc5 -o resources.py resources.qrc
    ```
    1.4) Spowoduje to wygenerowanie wymaganego pliku `resources.py`

2.  Upewnij się, że masz folder zawierający wszystkie pliki wtyczki (jak `metadata.txt`, `init.py` itd.). Nazwijmy go `[nazwa_twojego_folderu_wtyczki]`.
3.  Znajdź folder z profilami użytkownika QGIS. Najprostszy sposób:
    - W QGIS, przejdź do menu: `Ustawienia` -> `Profile użytkownika` -> `Otwórz aktywny folder profilu`.
4.  W otwartym folderze profilu, przejdź do podfolderu `python/plugins/`.
5.  Wklej cały folder wtyczki (`[nazwa_twojego_folderu_wtyczki]`) do folderu `plugins`.
6.  Uruchom ponownie QGIS.
7.  Przejdź do menu `Wtyczki` -> `Zarządzanie wtyczkami...` i aktywuj (zaznacz) nową wtyczkę na liście.

---

This is a custom plugin for QGIS that improves the FTTH design process.

## :warning: Status: Beta Version

This project is currently in an active development and testing phase. Core functionalities are being created and validated.

Therefore, the plugin may contain bugs, behave unstably, or produce unexpected results. Caution is advised.

**Before using this plugin on important data, always work on a backup copy of your QGIS project (.qgz) and source data layers.** This will help protect your data from accidental loss or permanent damage.

## Installation

This plugin is not yet available in the official QGIS Plugin Repository. It will be added after the intensive testing phase is complete.

To install the plugin manually:

1.  Download the latest version of the plugin (e.g., by clicking `Code` -> `Download ZIP` and unpacking the archive, or by downloading from the `Releases` tab, if you have created one).

By default, the `resources.py` file (which contains icons and resources) does not exist in the repository; you must generate it manually. On Windows, the easiest way to do this is by using the **OSGeo4W Shell** terminal, which is installed along with QGIS:

    1.1) Open the **OSGeo4W Shell** (you can find it in your Start Menu).
    1.2) Navigate to the main plugin folder (the one containing the `resources.qrc` file) uusing the `cd` command. Example:
    ```bash
    # Remember to use the path to the folder containing the .qrc file
    cd C:\path\to\your\repo\FiberAssistant\FiberAssistant
    ```
    1.3) Run the PyQGIS resource compiler (`pyrcc5`) to convert the `.qrc` file into a `.py` file:
    ```bash
    pyrcc5 -o resources.py resources.qrc
    ```
    1.4) This will generate the required `resources.py` file.

2.  Make sure you have a folder containing all the plugin files (like `metadata.txt`, `init.py`, etc.). Let's call it `[your_plugin_folder_name]`.
3.  Find your QGIS user profiles folder. The easiest way is:
    - In QGIS, go to the menu: `Settings` -> `User Profiles` -> `Open Active Profile Folder`.
4.  In the opened profile folder, navigate to the `python/plugins/` subfolder.
5.  Paste the entire plugin folder (`[your_plugin_folder_name]`) into the `plugins` directory.
6.  Restart QGIS.
7.  Go to the `Plugins` -> `Manage and Install Plugins...` menu and activate (check) the new plugin in the "Installed" list.
