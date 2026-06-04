from datetime import datetime


async def current_time() -> str:
    now = datetime.now()
    return f"{now.strftime('%Y-%m-%d')} {now.strftime('%H:%M')}"
