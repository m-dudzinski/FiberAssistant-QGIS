from qgis.PyQt.QtCore import QSettings

class SettingsManager:
    """Manages access to plugin settings."""
    
    SETTINGS_GROUP = "FiberAssistant"

    # --- Keys ---
    EXPERIMENTAL_FEATURES_KEY = "showExperimentalFeatures"
    SCOPE_LIMITATION_DISABLED_KEY = "scopeLimitationDisabled"

    # --- Defaults ---
    DEFAULTS = {
        EXPERIMENTAL_FEATURES_KEY: False,
        SCOPE_LIMITATION_DISABLED_KEY: False,
    }

    def __init__(self):
        self.settings = QSettings()

    def get_setting(self, key, default_value=None):
        """Gets a setting value."""
        if default_value is None:
            default_value = self.DEFAULTS.get(key)
        value = self.settings.value(f"{self.SETTINGS_GROUP}/{key}", default_value)
        # QSettings may return strings for booleans
        if isinstance(default_value, bool):
            if isinstance(value, str):
                return value.lower() in ('true', '1', 't', 'y', 'yes')
        return value

    def set_setting(self, key, value):
        """Sets a setting value."""
        self.settings.setValue(f"{self.SETTINGS_GROUP}/{key}", value)

    def are_experimental_features_enabled(self):
        """Checks if the 'Show experimental features' setting is enabled."""
        return self.get_setting(self.EXPERIMENTAL_FEATURES_KEY)

    def set_experimental_features_enabled(self, enabled: bool):
        """Sets the 'Show experimental features' setting."""
        self.set_setting(self.EXPERIMENTAL_FEATURES_KEY, enabled)

    def is_scope_limitation_disabled(self):
        """Checks if the 'Disable scope limitation' setting is enabled."""
        return self.get_setting(self.SCOPE_LIMITATION_DISABLED_KEY)

    def set_scope_limitation_disabled(self, enabled: bool):
        """Sets the 'Disable scope limitation' setting."""
        self.set_setting(self.SCOPE_LIMITATION_DISABLED_KEY, enabled)