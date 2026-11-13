from app.models.enums import ViolationSeverity

# Map Severity to list of alert types to trigger
# Alert types match what we will define/use in the AlertService
ALERT_RULES = {
    ViolationSeverity.WARNING: ["DASHBOARD"],
    ViolationSeverity.HIGH: ["DASHBOARD", "EMAIL"],
    ViolationSeverity.CRITICAL: ["DASHBOARD", "EMAIL"]
}

# In a real enterprise app, recipients would be queried from an Admin/Operator group 
# or specific notification subscription tables. For now, we use a central config.
DEFAULT_ALERT_EMAIL = "alerts@coldguard.local"
DEFAULT_ADMIN_EMAIL = "admin@coldguard.local"
