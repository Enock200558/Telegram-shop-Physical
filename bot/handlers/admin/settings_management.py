from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.database.models.main import Permission, BotSettings
from bot.database.main import Database
from bot.database.methods.read import get_reference_bonus_percent, get_bot_setting
from bot.states.user_state import SettingsFSM
from bot.keyboards.inline import back, settings_management_keyboard, timezone_selection_keyboard
from bot.filters import HasPermissionFilter
from bot.config import timezone

router = Router()


@router.callback_query(F.data == "settings_management", HasPermissionFilter(Permission.SETTINGS_MANAGE))
async def settings_menu(call: CallbackQuery, state: FSMContext):
    """
    Show settings management menu (admin/owner only).
    Displays current values for all configurable settings.
    """
    await state.clear()

    # Get current settings
    current_percent = get_reference_bonus_percent()
    current_timeout = get_bot_setting('cash_order_timeout_hours', default=24, value_type=int)
    current_timezone = timezone.get_timezone()

    await call.message.edit_text(
        f"⚙️ <b>Bot Settings</b>\n\n"
        f"<b>Current Values:</b>\n"
        f"• Referral Bonus: <b>{current_percent}%</b>\n"
        f"• Order Timeout: <b>{current_timeout} hours</b>\n"
        f"• Timezone: <b>{current_timezone}</b>\n\n"
        f"Select a setting to modify:",
        reply_markup=settings_management_keyboard(),
        parse_mode='HTML'
    )


@router.callback_query(F.data == "setting_referral_percent", HasPermissionFilter(Permission.SETTINGS_MANAGE))
async def set_referral_percent_start(call: CallbackQuery, state: FSMContext):
    """
    Start referral percentage update flow.
    """
    current_percent = get_reference_bonus_percent()

    await call.message.edit_text(
        f"💰 <b>Update Referral Bonus Percentage</b>\n\n"
        f"Current value: <b>{current_percent}%</b>\n\n"
        f"Enter new percentage (0-100):\n"
        f"• Example: <code>5</code> (for 5%)\n"
        f"• Example: <code>10</code> (for 10%)\n"
        f"• Example: <code>0</code> (to disable referral bonuses)\n\n"
        f"<i>This percentage will be applied to all future completed orders.</i>",
        reply_markup=back("settings_management"),
        parse_mode='HTML'
    )
    await state.set_state(SettingsFSM.waiting_referral_percent)


@router.message(SettingsFSM.waiting_referral_percent, F.text)
async def process_referral_percent(message: Message, state: FSMContext):
    """
    Process and save referral percentage.
    Validates input and updates the database.
    """
    try:
        # Validate input - must be integer
        percent_value = int(message.text.strip())

        if percent_value < 0 or percent_value > 100:
            await message.answer(
                "❌ <b>Invalid input</b>\n\n"
                "Percentage must be between 0 and 100.\n"
                "Please try again:",
                reply_markup=back("settings_management"),
                parse_mode='HTML'
            )
            return

        # Update database
        with Database().session() as session:
            setting = session.query(BotSettings).filter_by(
                setting_key='reference_bonus_percent'
            ).first()

            if setting:
                setting.setting_value = str(percent_value)
            else:
                setting = BotSettings(
                    setting_key='reference_bonus_percent',
                    setting_value=str(percent_value)
                )
                session.add(setting)

            session.commit()

        # Show confirmation
        status_text = "enabled" if percent_value > 0 else "disabled"
        await message.answer(
            f"✅ <b>Referral Bonus Updated!</b>\n\n"
            f"New percentage: <b>{percent_value}%</b>\n"
            f"Status: <b>{status_text.upper()}</b>\n\n"
            f"This will apply to all future completed orders.\n"
            f"Users will receive {percent_value}% of their referral's order total as bonus balance.",
            reply_markup=settings_management_keyboard(),
            parse_mode='HTML'
        )

    except ValueError:
        await message.answer(
            "❌ <b>Invalid input</b>\n\n"
            "Please enter a valid whole number (0-100).\n"
            "Examples: 5, 10, 15, 20",
            reply_markup=back("settings_management"),
            parse_mode='HTML'
        )
        return

    await state.clear()


@router.callback_query(F.data == "setting_order_timeout", HasPermissionFilter(Permission.SETTINGS_MANAGE))
async def set_order_timeout_start(call: CallbackQuery, state: FSMContext):
    """
    Start order timeout update flow.
    """
    current_timeout = get_bot_setting('cash_order_timeout_hours', default=24, value_type=int)

    await call.message.edit_text(
        f"⏱️ <b>Update Order Timeout</b>\n\n"
        f"Current value: <b>{current_timeout} hours</b>\n\n"
        f"Enter new timeout in hours (1-168):\n"
        f"• Example: <code>24</code> (24 hours / 1 day)\n"
        f"• Example: <code>48</code> (48 hours / 2 days)\n"
        f"• Example: <code>72</code> (72 hours / 3 days)\n\n"
        f"<i>Orders will automatically expire after this time if not paid.</i>",
        reply_markup=back("settings_management"),
        parse_mode='HTML'
    )
    await state.set_state(SettingsFSM.waiting_order_timeout)


@router.message(SettingsFSM.waiting_order_timeout, F.text)
async def process_order_timeout(message: Message, state: FSMContext):
    """
    Process and save order timeout.
    Validates input and updates the database.
    """
    try:
        # Validate input - must be integer
        timeout_hours = int(message.text.strip())

        if timeout_hours < 1 or timeout_hours > 168:  # Max 1 week
            await message.answer(
                "❌ <b>Invalid input</b>\n\n"
                "Timeout must be between 1 and 168 hours (1 week).\n"
                "Please try again:",
                reply_markup=back("settings_management"),
                parse_mode='HTML'
            )
            return

        # Update database
        with Database().session() as session:
            setting = session.query(BotSettings).filter_by(
                setting_key='cash_order_timeout_hours'
            ).first()

            if setting:
                setting.setting_value = str(timeout_hours)
            else:
                setting = BotSettings(
                    setting_key='cash_order_timeout_hours',
                    setting_value=str(timeout_hours)
                )
                session.add(setting)

            session.commit()

        # Calculate days for display
        days = timeout_hours / 24
        days_text = f"{days:.1f} day(s)" if days != int(days) else f"{int(days)} day(s)"

        # Show confirmation
        await message.answer(
            f"✅ <b>Order Timeout Updated!</b>\n\n"
            f"New timeout: <b>{timeout_hours} hours</b> ({days_text})\n\n"
            f"All new orders will automatically expire after {timeout_hours} hours if not paid.\n"
            f"Reserved inventory will be released when orders expire.",
            reply_markup=settings_management_keyboard(),
            parse_mode='HTML'
        )

    except ValueError:
        await message.answer(
            "❌ <b>Invalid input</b>\n\n"
            "Please enter a valid whole number (1-168).\n"
            "Examples: 12, 24, 48, 72",
            reply_markup=back("settings_management"),
            parse_mode='HTML'
        )
        return

    await state.clear()


@router.callback_query(F.data == "setting_timezone", HasPermissionFilter(Permission.SETTINGS_MANAGE))
async def set_timezone_start(call: CallbackQuery, state: FSMContext):
    """
    Start timezone update flow with popular options.
    """
    current_tz = timezone.get_timezone()
    current_time = timezone.get_localized_time()

    await call.message.edit_text(
        f"🌍 <b>Update Timezone</b>\n\n"
        f"Current timezone: <b>{current_tz}</b>\n"
        f"Current time: <b>{current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}</b>\n\n"
        f"Select a timezone from popular options below,\n"
        f"or choose 'Enter manually' to type your own.\n\n"
        f"<i>This affects all logging timestamps.</i>",
        reply_markup=timezone_selection_keyboard(),
        parse_mode='HTML'
    )


@router.callback_query(F.data.startswith("tz_select:"), HasPermissionFilter(Permission.SETTINGS_MANAGE))
async def select_timezone_from_button(call: CallbackQuery, state: FSMContext):
    """
    Process timezone selection from inline buttons.
    """
    # Extract timezone from callback_data
    timezone_str = call.data.split(":", 1)[1]

    # Validate timezone
    if not timezone.validate_timezone(timezone_str):
        await call.answer("❌ Invalid timezone!", show_alert=True)
        return

    # Update database
    with Database().session() as session:
        setting = session.query(BotSettings).filter_by(
            setting_key='timezone'
        ).first()

        if setting:
            setting.setting_value = timezone_str
        else:
            setting = BotSettings(
                setting_key='timezone',
                setting_value=timezone_str
            )
            session.add(setting)

        session.commit()

    # Hot reload timezone
    timezone.reload_timezone()
    new_time = timezone.get_localized_time()

    # Show confirmation
    await call.message.edit_text(
        f"✅ <b>Timezone Updated!</b>\n\n"
        f"New timezone: <b>{timezone_str}</b>\n"
        f"Current time: <b>{new_time.strftime('%Y-%m-%d %H:%M:%S %Z')}</b>\n\n"
        f"All logging timestamps will now use this timezone.\n"
        f"Changes applied immediately (hot reload).",
        reply_markup=settings_management_keyboard(),
        parse_mode='HTML'
    )

    await state.clear()


@router.callback_query(F.data == "tz_manual", HasPermissionFilter(Permission.SETTINGS_MANAGE))
async def set_timezone_manual(call: CallbackQuery, state: FSMContext):
    """
    Start manual timezone input.
    """
    current_tz = timezone.get_timezone()

    await call.message.edit_text(
        f"🌍 <b>Enter Timezone Manually</b>\n\n"
        f"Current timezone: <b>{current_tz}</b>\n\n"
        f"Enter timezone in IANA format:\n"
        f"• Example: <code>UTC</code>\n"
        f"• Example: <code>Europe/Moscow</code>\n"
        f"• Example: <code>America/New_York</code>\n"
        f"• Example: <code>Asia/Tokyo</code>\n\n"
        f"📋 Full list: <a href='https://en.wikipedia.org/wiki/List_of_tz_database_time_zones'>Wikipedia</a>\n\n"
        f"<i>Timezone must be valid according to the IANA time zone database.</i>",
        reply_markup=back("settings_management"),
        parse_mode='HTML'
    )
    await state.set_state(SettingsFSM.waiting_timezone)


@router.message(SettingsFSM.waiting_timezone, F.text)
async def process_timezone_input(message: Message, state: FSMContext):
    """
    Process and validate manually entered timezone.
    """
    timezone_str = message.text.strip()

    # Validate timezone
    if not timezone.validate_timezone(timezone_str):
        await message.answer(
            f"❌ <b>Invalid Timezone</b>\n\n"
            f"'{timezone_str}' is not a valid IANA timezone.\n\n"
            f"Please use the correct format:\n"
            f"• UTC\n"
            f"• Europe/Moscow\n"
            f"• America/New_York\n"
            f"• Asia/Tokyo\n\n"
            f"Check the full list: "
            f"<a href='https://en.wikipedia.org/wiki/List_of_tz_database_time_zones'>Wikipedia</a>",
            reply_markup=back("settings_management"),
            parse_mode='HTML'
        )
        return

    # Update database
    with Database().session() as session:
        setting = session.query(BotSettings).filter_by(
            setting_key='timezone'
        ).first()

        if setting:
            setting.setting_value = timezone_str
        else:
            setting = BotSettings(
                setting_key='timezone',
                setting_value=timezone_str
            )
            session.add(setting)

        session.commit()

    # Hot reload timezone
    timezone.reload_timezone()
    new_time = timezone.get_localized_time()

    # Show confirmation
    await message.answer(
        f"✅ <b>Timezone Updated!</b>\n\n"
        f"New timezone: <b>{timezone_str}</b>\n"
        f"Current time: <b>{new_time.strftime('%Y-%m-%d %H:%M:%S %Z')}</b>\n\n"
        f"All logging timestamps will now use this timezone.\n"
        f"Changes applied immediately (hot reload).",
        reply_markup=settings_management_keyboard(),
        parse_mode='HTML'
    )

    await state.clear()
