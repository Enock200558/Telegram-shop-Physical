from datetime import datetime

from sqlalchemy import exists

from bot.database.models import User, Goods, Categories, ShoppingCart
from bot.database import Database
from bot.logger_mesh import logger


def create_user(telegram_id: int, registration_date: datetime, referral_id: int | None, role: int = 1) -> None:
    """Create user if missing; commit."""
    with Database().session() as s:
        if s.query(exists().where(User.telegram_id == telegram_id)).scalar():
            return
        s.add(
            User(
                telegram_id=telegram_id,
                role_id=role,
                registration_date=registration_date,
                referral_id=referral_id,
            )
        )


def create_item(item_name: str, item_description: str, item_price: int, category_name: str) -> None:
    """Insert item (goods); commit."""
    with Database().session() as s:
        if s.query(exists().where(Goods.name == item_name)).scalar():
            return
        s.add(
            Goods(
                name=item_name,
                description=item_description,
                price=item_price,
                category_name=category_name,
            )
        )


def create_category(category_name: str) -> None:
    """Insert category; commit."""
    with Database().session() as s:
        if s.query(exists().where(Categories.name == category_name)).scalar():
            return
        s.add(Categories(name=category_name))


async def add_to_cart(user_id: int, item_name: str, quantity: int = 1) -> tuple[bool, str]:
    """
    Add item to cart or update quantity if already exists

    Args:
        user_id: User's telegram ID
        item_name: Name of the item to add
        quantity: Quantity to add (default 1)

    Returns:
        Tuple of (success, message)
    """
    # Import here to avoid circular import
    from bot.database.methods.read import check_value, select_item_values_amount_cached

    try:
        with Database().session() as session:
            # Check if item exists and has stock
            good = session.query(Goods).filter_by(name=item_name).first()
            if not good:
                return False, "Item not found"

            # Check stock availability
            is_unlimited = check_value(item_name)
            if not is_unlimited:
                available_stock = await select_item_values_amount_cached(item_name)
                existing_cart = session.query(ShoppingCart).filter_by(
                    user_id=user_id, item_name=item_name
                ).first()

                current_cart_qty = existing_cart.quantity if existing_cart else 0
                total_requested = current_cart_qty + quantity

                if available_stock < total_requested:
                    return False, f"Only {available_stock} items available in stock"

            # Add or update cart item
            cart_item = session.query(ShoppingCart).filter_by(
                user_id=user_id,
                item_name=item_name
            ).first()

            if cart_item:
                cart_item.quantity += quantity
            else:
                cart_item = ShoppingCart(
                    user_id=user_id,
                    item_name=item_name,
                    quantity=quantity
                )
                session.add(cart_item)

            session.commit()
            return True, "Item added to cart"

    except Exception as e:
        logger.error(f"Error adding to cart: {e}")
        return False, str(e)
