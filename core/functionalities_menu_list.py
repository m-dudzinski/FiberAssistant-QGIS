# -*- coding: utf-8 -*-
"""
Lista funkcjonalności dostępnych w menu głównym FiberAssistant.
Kolejność zgodna z nowymi wytycznymi.

Aby włączyć wyświetlanie danej funkcjonalności w menu, wystarczy odkomentować
odpowiednią linię w liście `ENABLED_FUNCTIONALITIES` poniżej.
"""

ENABLED_FUNCTIONALITIES = [
    "wyszukiwarka",                      # 1
    "statystyka",                        # 2
    # "walidator",                         # 3
    "przeliczanie_dlugosci",             # 4
    "dane_podstawowe_projektu",          # 5
    "zarzadzanie_kablami",               # 6
    "zarzadzanie_PA",                    # 7
    "zarzadzanie_PE",                    # 8
    "karta_krosowan",                    # 9
    "stycznosc_wierzcholkow",            # 10
    "wykorzystanie_infrastruktury",      # 11
    # "elementy_niewybudowane",            # 12
    # "raport_miesieczny_qgis",            # 13
    # "raport_polroczny_qgis",             # 14
    # "funkcjonalnosci_dla_tok",           # 15
    # "uzupelnianie_struktury_projektu",   # 16
    "czyszczenie",                       # 17
    # "funkcje_w_fazie_testow",            # 18
]

# Lista nazw funkcjonalności, które powinny aktywować globalny przycisk "Uruchom".
# Nazwy muszą być zgodne z atrybutem "name" w `ALL_FUNCTIONALITIES_MAP` w `main_dialog.py`.
RUN_BUTTON_WHITELIST = [
    "Statystyka",
    "Dane podstawowe projektu",
    "Przeliczanie długości",
    "Styczność wierzchołków",
    "Zarządzanie PA",
    "Zarządzanie PE",
    "Zarządzanie kablami",
    "Karta krosowań",
    "Wykorzystanie infrastruktury",
    "Czyszczenie",
]