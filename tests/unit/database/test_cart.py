"""
Tests for shopping cart functionality
"""
import pytest
from decimal import Decimal
from unittest.mock import patch

from bot.database.methods.read import get_cart_items, calculate_cart_total
from bot.database.methods.create import add_to_cart
from bot.database.models.main import ShoppingCart


@pytest.mark.unit
@pytest.mark.cart
@pytest.mark.database
class TestShoppingCart:
    """Tests for shopping cart operations"""

    @pytest.mark.asyncio
    async def test_get_cart_items(self, db_session, test_shopping_cart, test_goods):
        """Test getting cart items"""
        items = await get_cart_items(test_shopping_cart.user_id)

        assert len(items) >= 1
        assert items[0]['item_name'] == test_goods.name
        assert items[0]['quantity'] == 2

    @pytest.mark.asyncio
    async def test_get_cart_items_empty(self, db_session, test_user):
        """Test getting cart items for user with empty cart"""
        items = await get_cart_items(test_user.telegram_id + 1)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_calculate_cart_total(self, db_session, test_shopping_cart, test_goods):
        """Test calculating cart total"""
        total = await calculate_cart_total(test_shopping_cart.user_id)

        expected_total = test_goods.price * test_shopping_cart.quantity
        assert total == expected_total

    @pytest.mark.asyncio
    async def test_add_to_cart_new_item(self, db_session, test_user, test_goods):
        """Test adding new item to cart"""
        with patch('bot.database.methods.read.check_value', return_value=False):
            with patch('bot.database.methods.read.select_item_values_amount_cached', return_value=100):
                success, message = await add_to_cart(test_user.telegram_id, test_goods.name, 3)

                assert success == True

                cart_item = db_session.query(ShoppingCart).filter_by(
                    user_id=test_user.telegram_id,
                    item_name=test_goods.name
                ).first()

                assert cart_item is not None
                assert cart_item.quantity == 3

    @pytest.mark.asyncio
    async def test_add_to_cart_update_quantity(self, db_session, test_shopping_cart):
        """Test updating quantity for existing cart item"""
        with patch('bot.database.methods.read.check_value', return_value=False):
            with patch('bot.database.methods.read.select_item_values_amount_cached', return_value=100):
                initial_quantity = test_shopping_cart.quantity

                success, message = await add_to_cart(
                    test_shopping_cart.user_id,
                    test_shopping_cart.item_name,
                    2
                )

                assert success == True

                db_session.refresh(test_shopping_cart)
                assert test_shopping_cart.quantity == initial_quantity + 2

    @pytest.mark.asyncio
    async def test_add_to_cart_exceeds_stock(self, db_session, test_user, test_goods_low_stock):
        """Test adding more items than available stock"""
        with patch('bot.database.methods.read.check_value', return_value=False):
            with patch('bot.database.methods.read.select_item_values_amount_cached', return_value=2):
                success, message = await add_to_cart(
                    test_user.telegram_id,
                    test_goods_low_stock.name,
                    5
                )

                assert success == False
                assert "available" in message.lower()

    @pytest.mark.asyncio
    async def test_add_to_cart_nonexistent_item(self, db_session, test_user):
        """Test adding non-existent item to cart"""
        with patch('bot.database.methods.read.check_value', return_value=False):
            success, message = await add_to_cart(
                test_user.telegram_id,
                "Non-Existent Product",
                1
            )

            assert success == False
            assert "not found" in message.lower()
