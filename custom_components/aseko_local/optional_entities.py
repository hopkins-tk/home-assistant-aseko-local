from .aseko_data import AsekoDeviceType, AsekoDevice

def get_optional_inactive_entities(device: AsekoDevice) -> tuple[set[str], set[str]]:
    """
    Returns two sets of entity keys for a given device:
    - optional_inactive: Entities should be disabled if their value is None. This is in case if the device does not support them,
      but it's not in used at the moment. (eg. chlorine sensor instead of redox --> redox is disabled)
    - always_inactive: Entities that should always be created in a disabled state for this device type
      independant if their is a value or none.
    """
    optional_inactive: set[str] = set()
    always_inactive: set[str] = set()

    if device.device_type == AsekoDeviceType.SALT:
        optional_inactive = {
            "free_chlorine", "required_free_chlorine", "cl_free_mv",
            "redox", "required_redox"
        }
        always_inactive = {
            "pump_running", "active_pump", "flowrate_chlor", "flowrate_ph_minus"  # Example: always disabled for SALT
        }

    elif device.device_type == AsekoDeviceType.NET:
        optional_inactive = {
            "free_chlorine", "required_free_chlorine", "cl_free_mv",
            "redox", "required_redox"
        }
        always_inactive = {
            "pump_running", "active_pump", "flowrate_chlor", "flowrate_ph_minus"  # Example: always disabled for SALT
        }

    elif device.device_type == AsekoDeviceType.HOME:
        optional_inactive = {
            # Depending on the actual installation: could have Redox OR CLF
            "free_chlorine", "required_free_chlorine", "cl_free_mv",
            "redox", "required_redox", "flowrate_floc"
        }
        always_inactive = {
            "pump_running", "active_pump", "flowrate_chlor", "flowrate_ph_minus", "flowrate_floc"  # Example: always disabled for SALT
        }

    elif device.device_type == AsekoDeviceType.PROFI:
        optional_inactive = {
            # PROFI can have both; if not present, they are created disabled
            "free_chlorine", "required_free_chlorine", "cl_free_mv",
            "redox", "required_redox", "flowrate_floc", "flowrate_ph_plus",
        }
        always_inactive = {
            "pump_running", "active_pump", "flowrate_chlor", "flowrate_ph_minus", "flowrate_ph_plus", "flowrate_floc"  # Example: always disabled for SALT
        }

    return optional_inactive, always_inactive

