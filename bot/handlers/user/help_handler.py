from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from bot.database.main import Database
from bot.database.models.main import BotSettings
from bot.config import EnvKeys
from bot.states.user_state import HelpStates
from bot.keyboards import back
from bot.i18n import localize

router = Router()


@router.message(Command("help"))
async def help_command(message: Message, state: FSMContext):
    """
    Handle /help command - prompt user to enter their message

    Args:
        message: Message object
        state: FSM context
    """
    await message.answer(
        localize("help.prompt") + localize("help.describe_issue"),
        reply_markup=back("cancel_help")
    )
    await state.set_state(HelpStates.waiting_help_message)


@router.message(HelpStates.waiting_help_message)
async def process_help_message(message: Message, state: FSMContext):
    """
    Process the help message and send to admin

    Args:
        message: User's help message
        state: FSM context
    """
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    user_message = message.text

    # Get admin ID from env
    admin_id = EnvKeys.OWNER_ID
    if not admin_id:
        await message.answer(
            localize("help.admin_not_configured"),
            reply_markup=back("back_to_menu")
        )
        await state.clear()
        return

    # Send message to admin
    admin_text = (
        localize("help.admin_notification_title") +
        localize("help.admin_notification_from", username=username, user_id=user_id) +
        localize("help.admin_notification_message", message=user_message)
    )

    try:
        await message.bot.send_message(
            chat_id=int(admin_id),
            text=admin_text
        )

        # Get automated response message from settings
        with Database().session() as session:
            setting = session.query(BotSettings).filter_by(setting_key='help_auto_message').first()
            auto_message = setting.setting_value if setting else "Your message has been sent to the admin. Please wait for a response."

        await message.answer(
            localize("help.sent_success", auto_message=auto_message),
            reply_markup=back("back_to_menu")
        )

    except Exception as e:
        await message.answer(
            localize("help.sent_error", error=str(e)),
            reply_markup=back("back_to_menu")
        )

    await state.clear()


@router.callback_query(F.data == "cancel_help")
async def cancel_help(call: CallbackQuery, state: FSMContext):
    """
    Cancel help request

    Args:
        call: Callback query
        state: FSM context
    """
    await state.clear()
    await call.message.edit_text(
        localize("help.cancelled"),
        reply_markup=back("back_to_menu")
    )
