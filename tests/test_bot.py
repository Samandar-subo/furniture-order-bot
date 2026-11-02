"""Тесты: проверка телефона, запись в Excel и весь диалог бота без обращения к Telegram."""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.methods import SendMessage  # noqa: E402
from aiogram.types import Chat, Message, Update, User  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

import bot as bot_module  # noqa: E402
from storage import normalize_phone, save_order  # noqa: E402


def test_normalize_phone():
    assert normalize_phone("+7 700 000 00 00") == "+77000000000"
    assert normalize_phone("8 (700) 000-00-00") == "+77000000000"
    assert normalize_phone("700 000 00 00") == "+77000000000"
    assert normalize_phone("12345") is None
    assert normalize_phone("") is None


def test_save_order_numbers_rows(tmp_path):
    path = tmp_path / "orders.xlsx"
    first = save_order(path, {"product": "Фасад", "phone": "+77000000000"})
    second = save_order(path, {"product": "Комод", "phone": "+77000000001"})
    assert (first, second) == (1, 2)
    sheet = load_workbook(path).active
    assert sheet.max_row == 3
    assert sheet["D3"].value == "Комод"


class FakeSession(BaseSession):
    """Подменяет сеть: запоминает сообщения, которые бот хотел отправить."""

    def __init__(self):
        super().__init__()
        self.sent = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        assert isinstance(method, SendMessage)
        self.sent.append((method.chat_id, method.text))
        return Message(
            message_id=len(self.sent),
            date=datetime.now(),
            chat=Chat(id=method.chat_id, type="private"),
            text=method.text,
        )

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b""


def test_full_order_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("ORDERS_FILE", str(tmp_path / "orders.xlsx"))
    monkeypatch.setenv("ADMIN_CHAT_ID", "999")

    session = FakeSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    dispatcher = bot_module.build_dispatcher()
    user = User(id=1, is_bot=False, first_name="Тест", username="tester")
    chat = Chat(id=1, type="private")

    async def say(text, update_id):
        message = Message(message_id=update_id, date=datetime.now(), chat=chat, from_user=user, text=text)
        await dispatcher.feed_update(bot, Update(update_id=update_id, message=message))

    async def scenario():
        for i, text in enumerate(
            ["/start", "Оформить заказ", "Фасады кухни", "600x400", "abc", "+7 700 000 00 00", "белый матовый"],
            start=1,
        ):
            await say(text, i)

    asyncio.run(scenario())

    sheet = load_workbook(tmp_path / "orders.xlsx").active
    assert sheet.max_row == 2
    row = [cell.value for cell in sheet[2]]
    assert row[1:] == ["@tester", "Тест", "Фасады кухни", "600x400", "+77000000000", "белый матовый"]

    texts = [text for _, text in session.sent]
    assert any("Не получилось распознать номер" in t for t in texts)  # неверный номер был отклонён
    assert any("Заказ №1 принят" in t for t in texts)
    admin_messages = [text for chat_id, text in session.sent if chat_id == 999]
    assert len(admin_messages) == 1 and "Фасады кухни" in admin_messages[0]


def test_cancel_clears_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ORDERS_FILE", str(tmp_path / "orders.xlsx"))
    monkeypatch.delenv("ADMIN_CHAT_ID", raising=False)

    session = FakeSession()
    bot = Bot("123456:TEST_TOKEN", session=session)
    dispatcher = bot_module.build_dispatcher()
    user = User(id=2, is_bot=False, first_name="Тест2")
    chat = Chat(id=2, type="private")

    async def scenario():
        for i, text in enumerate(["Оформить заказ", "Фасады", "Отмена"], start=1):
            message = Message(message_id=i, date=datetime.now(), chat=chat, from_user=user, text=text)
            await dispatcher.feed_update(bot, Update(update_id=i, message=message))

    asyncio.run(scenario())
    assert not (tmp_path / "orders.xlsx").exists()
    assert "Заказ отменён" in session.sent[-1][1]
