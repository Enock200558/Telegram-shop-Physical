from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.database.methods import check_role
from bot.database.models.main import Permission
from bot.states.user_state import ReferenceCodeStates
from bot.keyboards import back, reference_code_admin_keyboard
from bot.keyboards.inline import InlineKeyboardBuilder
from bot.referrals import create_reference_code
from bot.monitoring import get_metrics

router = Router()


@router.callback_query(F.data == "admin_refcode_management")
async def admin_refcode_menu(call: CallbackQuery, state: FSMContext):
    """
    Show reference code management menu (admin only)

    Args:
        call: Callback query
        state: FSM context
    """
    # Check admin permission
    user_role = check_role(call.from_user.id)
    if not (user_role & (Permission.SHOP_MANAGE | Permission.ADMINS_MANAGE)):
        await call.answer("❌ Access denied", show_alert=True)
        return

    await call.message.edit_text(
        "🔑 <b>Reference Code Management</b>\n\n"
        "Manage reference codes for shop access control.\n\n"
        "Admin codes can have custom expiry and usage limits.",
        reply_markup=reference_code_admin_keyboard(),
        parse_mode='HTML'
    )
    await state.clear()


@router.callback_query(F.data == "admin_create_refcode")
async def admin_create_refcode_start(call: CallbackQuery, state: FSMContext):
    """
    Start reference code creation process

    Args:
        call: Callback query
        state: FSM context
    """
    # Check admin permission
    user_role = check_role(call.from_user.id)
    if not (user_role & (Permission.SHOP_MANAGE | Permission.ADMINS_MANAGE)):
        await call.answer("❌ Access denied", show_alert=True)
        return

    await call.message.edit_text(
        "➕ <b>Create Reference Code</b>\n\n"
        "Enter the expiration time in hours:\n"
        "• Send <code>0</code> for no expiry\n"
        "• Send <code>24</code> for 24 hours\n"
        "• Send <code>168</code> for 1 week\n\n"
        "Or click Back to cancel.",
        reply_markup=back("admin_refcode_management"),
        parse_mode='HTML'
    )
    await state.set_state(ReferenceCodeStates.waiting_refcode_expires)


@router.message(ReferenceCodeStates.waiting_refcode_expires)
async def admin_create_refcode_expires(message: Message, state: FSMContext):
    """
    Process expiration hours input

    Args:
        message: Message with expiration hours
        state: FSM context
    """
    try:
        expires_hours = int(message.text)
        if expires_hours < 0:
            await message.answer("❌ Hours must be positive or 0 (no expiry)")
            return

        await state.update_data(expires_hours=expires_hours)

        await message.answer(
            "👥 <b>Maximum Uses</b>\n\n"
            "Enter the maximum number of uses:\n"
            "• Send <code>0</code> for unlimited\n"
            "• Send <code>1</code> for single use\n"
            "• Send <code>10</code> for 10 uses\n\n"
            "Or click Back to cancel.",
            reply_markup=back("admin_refcode_management"),
            parse_mode='HTML'
        )
        await state.set_state(ReferenceCodeStates.waiting_refcode_max_uses)

    except ValueError:
        await message.answer("❌ Please enter a valid number")


@router.message(ReferenceCodeStates.waiting_refcode_max_uses)
async def admin_create_refcode_max_uses(message: Message, state: FSMContext):
    """
    Process max uses input

    Args:
        message: Message with max uses
        state: FSM context
    """
    try:
        max_uses = int(message.text)
        if max_uses < 0:
            await message.answer("❌ Max uses must be positive or 0 (unlimited)")
            return

        await state.update_data(max_uses=max_uses)

        await message.answer(
            "📝 <b>Optional Note</b>\n\n"
            "Enter an optional note for this code (e.g., 'VIP customers', 'Marketing campaign'):\n\n"
            "• Send note text\n"
            "• Or send <code>skip</code> to skip\n\n"
            "Or click Back to cancel.",
            reply_markup=back("admin_refcode_management"),
            parse_mode='HTML'
        )
        await state.set_state(ReferenceCodeStates.waiting_refcode_note)

    except ValueError:
        await message.answer("❌ Please enter a valid number")


@router.message(ReferenceCodeStates.waiting_refcode_note)
async def admin_create_refcode_note(message: Message, state: FSMContext):
    """
    Process note and create the reference code

    Args:
        message: Message with note
        state: FSM context
    """
    note = None if message.text.lower() == 'skip' else message.text
    user_id = message.from_user.id
    username = message.from_user.username or f"admin_{user_id}"

    # Get stored data
    data = await state.get_data()
    expires_hours = data.get('expires_hours', 0)
    max_uses = data.get('max_uses', 0)

    try:
        code = create_reference_code(
            created_by=user_id,
            created_by_username=username,
            is_admin_code=True,
            expires_in_hours=expires_hours if expires_hours > 0 else None,
            max_uses=max_uses if max_uses > 0 else None,
            note=note
        )

        # Track admin referral code creation
        metrics = get_metrics()
        if metrics:
            metrics.track_event("admin_referral_code_created", user_id, {
                "code": code,
                "expires_hours": expires_hours,
                "max_uses": max_uses,
                "has_note": bool(note)
            })

        expires_text = f"{expires_hours} hours" if expires_hours > 0 else "Never"
        max_uses_text = str(max_uses) if max_uses > 0 else "Unlimited"

        await message.answer(
            f"✅ <b>Reference Code Created!</b>\n\n"
            f"🔑 Code: <code>{code}</code>\n\n"
            f"⏰ Expires in: {expires_text}\n"
            f"👤 Max uses: {max_uses_text}\n"
            f"📝 Note: {note or 'None'}\n\n"
            f"Share this code to grant shop access.",
            reply_markup=reference_code_admin_keyboard(),
            parse_mode='HTML'
        )
    except Exception as e:
        await message.answer(
            f"❌ Error creating code: {str(e)}",
            reply_markup=reference_code_admin_keyboard()
        )

    await state.clear()


@router.callback_query(F.data == "admin_list_refcodes")
async def admin_list_refcodes(call: CallbackQuery, state: FSMContext):
    """
    List all reference codes

    Args:
        call: Callback query
        state: FSM context
    """
    # Check admin permission
    user_role = check_role(call.from_user.id)
    if not (user_role & (Permission.SHOP_MANAGE | Permission.ADMINS_MANAGE)):
        await call.answer("❌ Access denied", show_alert=True)
        return

    from bot.database.main import Database
    from bot.database.models.main import ReferenceCode

    with Database().session() as session:
        codes = session.query(ReferenceCode).order_by(
            ReferenceCode.created_at.desc()
        ).limit(20).all()

        if not codes:
            await call.message.edit_text(
                "ℹ️ No reference codes found.",
                reply_markup=back("admin_refcode_management")
            )
            return

        text = "📋 <b>Reference Codes</b> (Latest 20)\n\n"

        for code in codes:
            status = "✅" if code.is_active else "❌"
            code_type = "👑 Admin" if code.is_admin_code else "👤 User"
            max_uses = str(code.max_uses) if code.max_uses else "∞"
            expires = code.expires_at.strftime('%Y-%m-%d %H:%M') if code.expires_at else "Never"

            text += (
                f"{status} <code>{code.code}</code> {code_type}\n"
                f"   Uses: {code.current_uses}/{max_uses} | Expires: {expires}\n"
            )
            if code.note:
                text += f"   Note: {code.note}\n"
            text += "\n"

        # Build keyboard with disable options
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Back", callback_data="admin_refcode_management")
        kb.adjust(1)

        await call.message.edit_text(
            text,
            reply_markup=kb.as_markup(),
            parse_mode='HTML'
        )

    await state.clear()
