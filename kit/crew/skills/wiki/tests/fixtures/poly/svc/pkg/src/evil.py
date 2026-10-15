"""Evil docstrings are data: <script>alert(1)</script> <img src=x onerror=alert(1)>"""


def render():
    """Return markup. <script>alert(1)</script> and <img src=x onerror=alert(1)> stay text."""
    return "<b>ok</b>"
