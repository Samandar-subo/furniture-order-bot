"""Хранение заказов в Excel и проверка телефона."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

HEADERS = ["Дата", "Telegram", "Имя", "Изделие", "Размер", "Телефон", "Комментарий"]
COLUMN_WIDTHS = (18, 18, 20, 26, 18, 18, 40)


def normalize_phone(text: str) -> str | None:
    """Приводит номер к виду +7XXXXXXXXXX. Если номер не похож на казахстанский или российский, возвращает None."""
    digits = re.sub(r"\D", "", text or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    else:
        return None
    return "+" + digits


def save_order(path: str | Path, order: dict) -> int:
    """Добавляет заказ в Excel-файл (создаёт файл, если его нет). Возвращает номер заказа."""
    path = Path(path)
    if path.exists():
        workbook = load_workbook(path)
        sheet = workbook.active
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Заказы"
        sheet.append(HEADERS)
        for column, width in zip("ABCDEFG", COLUMN_WIDTHS):
            sheet.column_dimensions[column].width = width

    sheet.append(
        [
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            order.get("telegram", ""),
            order.get("name", ""),
            order.get("product", ""),
            order.get("size", ""),
            order.get("phone", ""),
            order.get("comment", ""),
        ]
    )
    workbook.save(path)
    return sheet.max_row - 1
