from datetime import datetime


async def current_time() -> str:
    now = datetime.now()
    return f"{now.strftime('%Y-%m-%d')} {now.strftime('%H:%M')}"


async def convert_date_to_timestamp(date_str: str) -> str:
    """Convert a date/time string to Unix timestamp (seconds). Formats: 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD HH:MM:SS'"""
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return str(int(datetime.strptime(date_str.strip(), fmt).timestamp()))
        except ValueError:
            continue
    return f"error: invalid date format '{date_str}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM"

