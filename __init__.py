def classFactory(iface):
    from .FiberAssistant import FiberAssistantPlugin
    return FiberAssistantPlugin(iface)