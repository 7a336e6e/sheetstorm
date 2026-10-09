"""Spreadsheet formula-injection (CWE-1236) neutralisation for CSV exports.

Every cell of every CSV the backend produces goes through ``csv_safe``.
"""

_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r', '\n')


def csv_safe(value) -> str:
    """Return ``value`` as a CSV-safe string.

    None becomes ''. A cell starting with = + - @ TAB CR or LF is prefixed with
    a single quote so spreadsheet applications treat it as text, not a formula.
    """
    if value is None:
        return ''
    text = str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text
