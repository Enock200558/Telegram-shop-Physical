from aiogram import Router, F
from aiogram.types import CallbackQuery, Message

from bot.database.models import Permission
from bot.database.methods import check_item_cached, update_item

from bot.keyboards.inline import back
from bot.logger_mesh import audit_logger
from bot.filters import HasPermissionFilter
from bot.config import EnvKeys
from bot.i18n import localize
from bot.states import UpdateItemFSM

router = Router()


@router.callback_query(F.data == 'update_item_amount', HasPermissionFilter(permission=Permission.SHOP_MANAGE))
async def update_item_amount_callback_handler(call: CallbackQuery, state):
    """
    Redirects to stock management (now handled in goods_management_states.py).
    """
    await call.message.edit_text(
        localize('admin.goods.stock.redirect_message'),
        reply_markup=back("goods_management")
    )
    await state.clear()


@router.callback_query(F.data == 'update_item', HasPermissionFilter(permission=Permission.SHOP_MANAGE))
async def update_item_callback_handler(call: CallbackQuery, state):
    """Starts the item update flow (name, description, price only)."""
    await call.message.edit_text(
        localize('admin.goods.update.prompt.name'),
        reply_markup=back("goods_management")
    )
    await state.set_state(UpdateItemFSM.waiting_item_name_for_update)


@router.message(UpdateItemFSM.waiting_item_name_for_update, F.text)
async def check_item_name_for_update(message: Message, state):
    """Validate item and ask for a new name."""
    item_name = message.text.strip()
    item = await check_item_cached(item_name)
    if not item:
        await message.answer(
            localize('admin.goods.update.not_exists'),
            reply_markup=back('goods_management')
        )
        return

    await state.update_data(item_old_name=item_name, item_category=item['category_name'])
    await message.answer(
        localize('admin.goods.update.prompt.new_name'),
        reply_markup=back('goods_management')
    )
    await state.set_state(UpdateItemFSM.waiting_item_new_name)


@router.message(UpdateItemFSM.waiting_item_new_name, F.text)
async def update_item_name(message: Message, state):
    """Ask for item description."""
    await state.update_data(item_new_name=message.text.strip())
    await message.answer(
        localize('admin.goods.update.prompt.description'),
        reply_markup=back('goods_management')
    )
    await state.set_state(UpdateItemFSM.waiting_item_description)


@router.message(UpdateItemFSM.waiting_item_description, F.text)
async def update_item_description(message: Message, state):
    """Ask for new price."""
    await state.update_data(item_description=message.text.strip())
    await message.answer(
        localize('admin.goods.add.prompt.price', currency=EnvKeys.PAY_CURRENCY),
        reply_markup=back('goods_management')
    )
    await state.set_state(UpdateItemFSM.waiting_item_price)


@router.message(UpdateItemFSM.waiting_item_price, F.text)
async def update_item_price_and_finish(message: Message, state):
    """
    Validate price and complete the update.
    Stock is managed separately via the stock management interface.
    """
    price_text = message.text.strip()
    if not price_text.isdigit():
        await message.answer(
            localize('admin.goods.add.price.invalid'),
            reply_markup=back('goods_management')
        )
        return

    await state.update_data(item_price=int(price_text))
    data = await state.get_data()
    item_old_name = data.get('item_old_name')
    item_new_name = data.get('item_new_name')
    item_description = data.get('item_description')
    category = data.get('item_category')
    price = data.get('item_price')

    # Update item metadata (stock is managed separately)
    update_item(item_old_name, item_new_name, item_description, price, category)

    await message.answer(
        localize('admin.goods.update.success'),
        reply_markup=back('goods_management')
    )

    admin_info = await message.bot.get_chat(message.from_user.id)
    audit_logger.info(
        f'Admin {message.from_user.id} ({admin_info.first_name}) updated item "{item_old_name}" → "{item_new_name}".'
    )
    await state.clear()
