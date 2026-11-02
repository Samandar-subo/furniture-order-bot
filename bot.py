"""Telegram-бот приёма заказов на мебельные фасады (демо-проект).

Клиент отвечает на 4 вопроса, заказ записывается в Excel,
а владельцу приходит уведомление в Telegram.
"""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from storage import normalize_phone, save_order

try:  # .env необязателен: можно задать переменные окружения вручную
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BTN_ORDER = "Оформить заказ"
BTN_FAQ = "Частые вопросы"
BTN_CANCEL = "Отмена"

GREETING = (
    "Здравствуйте! Я помогу оформить заказ на мебельные фасады.\n"
    "Нажмите «Оформить заказ» или выберите «Частые вопросы»."
)

# Пример текста: замените на ответы вашего бизнеса.
FAQ_TEXT = (
    "Сроки: простой фасад от 3 рабочих дней, сложный орнамент от 7.\n"
    "Материал: МДФ 16-19 мм, любой цвет по каталогу RAL.\n"
    "Доставка: по городу и по Казахстану транспортной компанией.\n"
    "Оплата: предоплата 50%, остальное при получении."
)


def orders_file() -> str:
    return os.getenv("ORDERS_FILE", "orders.xlsx")


def admin_chat_id() -> str | None:
    return os.getenv("ADMIN_CHAT_ID")


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_ORDER)], [KeyboardButton(text=BTN_FAQ)]],
        resize_keyboard=True,
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)


class OrderForm(StatesGroup):
    product = State()
    size = State()
    phone = State()
    comment = State()


HANDLERS: list = []


def handler(*filters):
    """Запоминает обработчик; роутер собирается заново в build_router()."""

    def decorator(func):
        HANDLERS.append((filters, func))
        return func

    return decorator


def build_router() -> Router:
    router = Router()
    for filters, func in HANDLERS:
        router.message.register(func, *filters)
    return router


@handler(Command("cancel"))
@handler(F.text == BTN_CANCEL)
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Заказ отменён. Можно начать заново.", reply_markup=main_menu())


@handler(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(GREETING, reply_markup=main_menu())


@handler(Command("faq"))
@handler(F.text == BTN_FAQ)
async def faq(message: Message) -> None:
    await message.answer(FAQ_TEXT, reply_markup=main_menu())


@handler(Command("order"))
@handler(F.text == BTN_ORDER)
async def order_start(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderForm.product)
    await message.answer(
        "Что нужно изготовить? Например: фасады кухни, дверь шкафа, комод.",
        reply_markup=cancel_menu(),
    )


@handler(OrderForm.product, F.text)
async def got_product(message: Message, state: FSMContext) -> None:
    await state.update_data(product=message.text.strip()[:100])
    await state.set_state(OrderForm.size)
    await message.answer("Размеры в мм (ширина × высота) или напишите «не знаю».")


@handler(OrderForm.size, F.text)
async def got_size(message: Message, state: FSMContext) -> None:
    await state.update_data(size=message.text.strip()[:100])
    await state.set_state(OrderForm.phone)
    await message.answer("Ваш номер телефона, чтобы мы могли связаться. Пример: +7 700 000 00 00")


@handler(OrderForm.phone, F.text)
async def got_phone(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text)
    if phone is None:
        await message.answer("Не получилось распознать номер. Пример: +7 700 000 00 00")
        return
    await state.update_data(phone=phone)
    await state.set_state(OrderForm.comment)
    await message.answer("Комментарий к заказу (цвет, материал, срок) или напишите «нет».")


@handler(OrderForm.comment, F.text)
async def got_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    user = message.from_user
    order = {
        "telegram": f"@{user.username}" if user and user.username else str(user.id if user else ""),
        "name": user.full_name if user else "",
        "product": data.get("product", ""),
        "size": data.get("size", ""),
        "phone": data.get("phone", ""),
        "comment": message.text.strip()[:300],
    }
    number = save_order(orders_file(), order)
    await state.clear()
    await message.answer(
        f"Заказ №{number} принят. Мы свяжемся с вами по номеру {order['phone']}.",
        reply_markup=main_menu(),
    )

    chat_id = admin_chat_id()
    if chat_id:
        text = (
            f"Новый заказ №{number}\n"
            f"Изделие: {order['product']}\n"
            f"Размер: {order['size']}\n"
            f"Телефон: {order['phone']}\n"
            f"Клиент: {order['name']} ({order['telegram']})\n"
            f"Комментарий: {order['comment']}"
        )
        await bot.send_message(int(chat_id), text)


@handler()
async def fallback(message: Message) -> None:
    await message.answer("Не понял. Используйте кнопки меню или команду /cancel.", reply_markup=main_menu())


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_router())
    return dispatcher


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("Не задан BOT_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather.")
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token)
    await build_dispatcher().start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
