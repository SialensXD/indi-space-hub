"""Pure domain helpers used by bot handlers."""

import math
import re
from datetime import timedelta


def parse_time(time_str: str) -> timedelta:
    """Parse durations such as 10m, 2h, or 1d."""
    match = re.fullmatch(r"(\d+)\s*([mhdмчд])", time_str.strip().lower())
    if not match:
        raise ValueError("invalid duration")

    value = int(match.group(1))
    unit = match.group(2)
    if unit in {"m", "м"}:
        return timedelta(minutes=value)
    if unit in {"h", "ч"}:
        return timedelta(hours=value)
    return timedelta(days=value)


def get_level(xp: int) -> int:
    if xp < 5:
        return 0
    return int(math.sqrt(xp / 5))


def get_next_level_xp(level: int) -> int:
    return 5 * ((level + 1) ** 2)


def get_rank_title(xp: int) -> str:
    level = get_level(xp)
    if level < 5:
        return "Новичок"
    if level < 15:
        return "Пережил Вьетнам"
    if level < 30:
        return "Без личной жизни"
    if level < 50:
        return "Оптимус Прайм"
    if level < 100:
        return "ПОТУЖНЫЙ"
    if level < 200:
        return "сигма-скибиди228"
    return "I REGRET NOTHING"


def generate_progress_bar(current: int, target: int, length: int = 10) -> str:
    if target <= 0:
        return "█" * length
    progress = min(1.0, current / target)
    filled_blocks = int(length * progress)
    return f"[{'█' * filled_blocks}{'░' * (length - filled_blocks)}]"
