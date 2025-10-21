
import os

# Proaktywne włączenie wyjątków dla OGR/GDAL, aby uniknąć ostrzeżeń w przyszłości
try:
    from osgeo import ogr
    ogr.UseExceptions()
except ImportError:
    pass # W środowisku QGIS osgeo powinno być zawsze dostępne

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

from .main_dialog import FiberAssistantDialog
from . import resources

class FiberAssistantPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = u'&Fiber Assistant'
        self.toolbar = self.iface.addToolBar(u'FiberAssistant')
        self.toolbar.setObjectName(u'FiberAssistant')
        self.dlg = None

    def initGui(self):
        icon_path = ':/icons/FA_icon.png'
        icon = QIcon(icon_path)
        self.action = QAction(icon, u'Uruchom Fiber Assistant', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.toolbar.addAction(self.action)
        self.iface.addPluginToMenu(self.menu, self.action)
        self.actions.append(self.action)

    def onClosePlugin(self):
        self.unload()

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(u'&Fiber Assistant', action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def run(self):
        if self.dlg is None:
            self.dlg = FiberAssistantDialog(self.iface)
        self.dlg.show()
        result = self.dlg.exec_()
        if result:
            pass
