import logging
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from app.database.db import get_stats, log_admin_action
router = Router()
logger = logging.getLogger(__name__)
class BroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirmation = State()
def is_admin(message: Message) -> bool:
    import os
    admin_ids = {
        int(value.strip())
        for value in os.getenv("ADMIN_IDS", "").split(",")
        if value.strip().isdigit()
    }
    return bool(
        message.from_user
        and message.from_user.id in admin_ids
    )
def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="admin:stats",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📣 Рассылка",
                    callback_data="admin:broadcast",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="admin:cancel",
                )
            ],
        ]
    )
@router.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext):
    if not is_admin(message):
        await message.answer("⛔ Доступ запрещён.")
        return
    await state.clear()
    await message.answer(
        "🔐 Панель администратора",
        reply_markup=admin_keyboard(),
    )
@router.callback_query(F.data == "admin:stats")
async def stats_callback(callback: CallbackQuery):
    if not callback.from_user:
        await callback.answer()
        return
    import os
    admin_ids = {
        int(value.strip())
        for value in os.getenv("ADMIN_IDS", "").split(",")
        if value.strip().isdigit()
    }
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещён.", show_alert=True)
        return
    await callback.answer()
    stats = await get_stats()
    await callback.message.answer(
        "📊 Статистика бота\n\n"
        f"👥 Всего пользователей: {stats['users']}\n"
        f"🆕 Зарегистрировались сегодня: {stats['today']}\n"
        f"📅 Зарегистрировались в этом месяце: {stats['month']}\n\n"
        f"🎬 Всего заданий: {stats['jobs']}\n"
        f"✅ Успешно: {stats['success']}\n"
        f"❌ С ошибкой: {stats['failed']}"
    )
@router.callback_query(F.data == "admin:broadcast")
async def broadcast_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    import os
    admin_ids = {
        int(value.strip())
        for value in os.getenv("ADMIN_IDS", "").split(",")
        if value.strip().isdigit()
    }
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещён.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.message.answer(
        "📣 Отправь следующим сообщением текст рассылки.\n\n"
        "Пока сообщение не будет отправлено пользователям. "
        "Сначала появится предварительный просмотр."
    )
@router.message(BroadcastState.waiting_for_message, F.text)
async def broadcast_preview(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        await message.answer("Отправь текст рассылки, не команду.")
        return
    await state.update_data(broadcast_text=text)
    await state.set_state(BroadcastState.waiting_for_confirmation)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Отправить всем",
                    callback_data="admin:broadcast_confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="admin:cancel",
                )
            ],
        ]
    )
    await message.answer(
        "👀 Предварительный просмотр рассылки:\n\n" + text,
        reply_markup=keyboard,
    )
@router.callback_query(F.data == "admin:broadcast_confirm")
async def broadcast_confirm(
    callback: CallbackQuery,
    state: FSMContext,
):
    import asyncio
    import os
    from aiogram.exceptions import TelegramAPIError
    from app.database.db import list_users
    admin_ids = {
        int(value.strip())
        for value in os.getenv("ADMIN_IDS", "").split(",")
        if value.strip().isdigit()
    }
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещён.", show_alert=True)
        return
    if await state.get_state() != BroadcastState.waiting_for_confirmation.state:
        await callback.answer("Рассылка не найдена.", show_alert=True)
        return
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text or not callback.message:
        await callback.answer("Нет текста для рассылки.", show_alert=True)
        return
    await callback.answer()
    await state.clear()
    users = await list_users(limit=100000)
    sent = 0
    failed = 0
    await callback.message.answer(
        f"⏳ Начинаю рассылку. Получателей в базе: {len(users)}."
    )
    for row in users:
        user_id = row[0]
        try:
            await callback.bot.send_message(user_id, text)
            sent += 1
        except TelegramAPIError:
            failed += 1
        except Exception:
            logger.exception("Broadcast failed for user %s", user_id)
            failed += 1
        await asyncio.sleep(0.05)
    await log_admin_action(
        callback.from_user.id,
        "broadcast",
        f"sent={sent}; failed={failed}",
    )
    await callback.message.answer(
        "📣 Рассылка завершена.\n\n"
        f"✅ Отправлено: {sent}\n"
        f"⚠️ Не доставлено: {failed}"
    )
@router.callback_query(F.data == "admin:cancel")
async def cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    import os
    admin_ids = {
        int(value.strip())
        for value in os.getenv("ADMIN_IDS", "").split(",")
        if value.strip().isdigit()
    }
    if callback.from_user.id not in admin_ids:
        await callback.answer("Доступ запрещён.", show_alert=True)
        return
    await state.clear()
    await callback.answer("Отменено.")
    if callback.message:
        await callback.message.answer("Действие отменено.")
