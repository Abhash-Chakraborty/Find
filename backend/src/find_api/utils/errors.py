import re


def sanitize_error(e: Exception) -> str:
    """
    Sanitize exception messages before storing in database or sending over API.
    Removes filesystem paths, URLs that might contain credentials, and truncates length.
    """
    msg = str(e)

    # 1. Strip Windows/Unix filesystem paths
    # Matches C:\foo\bar or /usr/local/bin/foo
    path_pattern = r"(?:[a-zA-Z]:[\\/]+|\b\/)(?:[\w\-. ]+[\\/]+)*[\w\-. ]+"
    msg = re.sub(path_pattern, "<path>", msg)

    # 2. Strip credentials in URLs
    url_pattern = r"(https?://)[^:\s/]+:[^@\s/]+@"
    msg = re.sub(url_pattern, r"\1<credentials>@", msg)

    # 3. Truncate long messages to prevent DB/payload bloat
    max_len = 150
    if len(msg) > max_len:
        msg = msg[:max_len] + "..."

    return f"{e.__class__.__name__}: {msg}"
