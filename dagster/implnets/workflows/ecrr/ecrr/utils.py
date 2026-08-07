def strtobool(val):
    """Convert a string representation of truth to 1 (true) or 0 (false).

    Replacement for distutils.util.strtobool, which was removed in Python 3.12.
    """
    val = str(val).lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return 1
    if val in ("n", "no", "f", "false", "off", "0"):
        return 0
    raise ValueError(f"invalid truth value {val!r}")
