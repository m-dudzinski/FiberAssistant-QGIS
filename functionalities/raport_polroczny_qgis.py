from qgis.PyQt.QtWidgets import QWidget, QLabel, QVBoxLayout
from qgis.PyQt.QtCore import Qt

class RaportPolrocznyQgisWidget(QWidget):
    def __init__(self, *args, **kwargs):
        parent = None
        for arg in reversed(args):
            if isinstance(arg, QWidget):
                parent = arg
                break
        super(RaportPolrocznyQgisWidget, self).__init__(parent)

        layout = QVBoxLayout(self)
        label = QLabel("Funkcjonalność w trakcie budowy..")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.setLayout(layout)
