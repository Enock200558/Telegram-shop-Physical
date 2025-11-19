"""
Integration tests for complete order lifecycle
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from bot.database.models.main import Order, OrderItem, Goods, CustomerInfo
from bot.database.methods.inventory import (
    reserve_inventory,
    release_reservation,
    deduct_inventory
)
from bot.utils.order_codes import generate_unique_order_code


@pytest.mark.integration
@pytest.mark.orders
@pytest.mark.database
class TestCompleteOrderLifecycle:
    """Integration tests for complete order lifecycle"""

    def test_full_order_flow_cash_payment(self, db_session, test_user, test_goods, test_admin):
        """Test complete order flow with cash payment"""
        # 1. Create order
        order = Order(
            buyer_id=test_user.telegram_id,
            total_price=Decimal("199.98"),
            payment_method="cash",
            delivery_address="123 Test Street, Test City",
            phone_number="+1234567890",
            delivery_note="Ring doorbell",
            order_status="pending",
            order_code=generate_unique_order_code(db_session)
        )
        db_session.add(order)
        db_session.flush()

        # 2. Add order items
        order_item = OrderItem(
            order_id=order.id,
            item_name=test_goods.name,
            price=test_goods.price,
            quantity=2
        )
        db_session.add(order_item)
        db_session.commit()

        assert order.id is not None
        assert order.order_status == "pending"

        # 3. Reserve inventory
        items = [{'item_name': test_goods.name, 'quantity': 2}]
        success, message = reserve_inventory(order.id, items, 'cash', db_session)
        db_session.commit()  # Inventory functions don't commit when session is passed

        assert success == True
        db_session.refresh(order)
        db_session.refresh(test_goods)

        assert order.order_status == 'reserved'
        assert test_goods.reserved_quantity == 2
        assert test_goods.available_quantity == test_goods.stock_quantity - 2

        initial_stock = test_goods.stock_quantity

        # 4. Confirm order (deduct inventory)
        order.order_status = 'confirmed'
        db_session.commit()

        with patch('bot.database.methods.inventory.get_metrics', return_value=None):
            success, message = deduct_inventory(order.id, test_admin.telegram_id, db_session)
        db_session.commit()  # Inventory functions don't commit when session is passed

        assert success == True
        db_session.refresh(test_goods)

        assert test_goods.stock_quantity == initial_stock - 2
        assert test_goods.reserved_quantity == 0

        # 5. Mark as delivered
        order.order_status = 'delivered'
        order.completed_at = datetime.now(timezone.utc)
        db_session.commit()

        assert order.order_status == 'delivered'
        assert order.completed_at is not None

    def test_order_cancellation_flow(self, db_session, test_user, test_goods):
        """Test order cancellation with inventory release"""
        # 1. Create order
        order = Order(
            buyer_id=test_user.telegram_id,
            total_price=Decimal("99.99"),
            payment_method="bitcoin",
            delivery_address="123 Test Street",
            phone_number="+1234567890",
            order_status="pending",
            order_code=generate_unique_order_code(db_session)
        )
        db_session.add(order)
        db_session.flush()

        order_item = OrderItem(
            order_id=order.id,
            item_name=test_goods.name,
            price=test_goods.price,
            quantity=5
        )
        db_session.add(order_item)
        db_session.commit()

        # 2. Reserve inventory
        items = [{'item_name': test_goods.name, 'quantity': 5}]
        success, message = reserve_inventory(order.id, items, 'bitcoin', db_session)
        db_session.commit()  # Inventory functions don't commit when session is passed

        assert success == True
        db_session.refresh(test_goods)

        initial_reserved = test_goods.reserved_quantity
        assert initial_reserved == 5

        # 3. Cancel order
        with patch('bot.database.methods.inventory.get_metrics', return_value=None):
            success, message = release_reservation(order.id, "User cancelled", db_session)
        db_session.commit()  # Inventory functions don't commit when session is passed

        assert success == True
        db_session.refresh(test_goods)

        # Inventory should be released
        assert test_goods.reserved_quantity == initial_reserved - 5

        order.order_status = 'cancelled'
        db_session.commit()

        assert order.order_status == 'cancelled'

    def test_order_with_multiple_items(self, db_session, test_user, multiple_products, test_admin):
        """Test order with multiple different items"""
        # Create order
        total_price = sum(product.price * 2 for product in multiple_products[:3])
        order = Order(
            buyer_id=test_user.telegram_id,
            total_price=total_price,
            payment_method="cash",
            delivery_address="123 Test Street",
            phone_number="+1234567890",
            order_status="pending",
            order_code=generate_unique_order_code(db_session)
        )
        db_session.add(order)
        db_session.flush()

        # Add multiple items
        items = []
        for product in multiple_products[:3]:
            order_item = OrderItem(
                order_id=order.id,
                item_name=product.name,
                price=product.price,
                quantity=2
            )
            db_session.add(order_item)
            items.append({'item_name': product.name, 'quantity': 2})

        db_session.commit()

        # Reserve all items
        success, message = reserve_inventory(order.id, items, 'cash', db_session)

        assert success == True

        # Check all items are reserved
        for product in multiple_products[:3]:
            db_session.refresh(product)
            assert product.reserved_quantity == 2

        # Deduct inventory
        order.order_status = 'confirmed'
        db_session.commit()

        with patch('bot.database.methods.inventory.get_metrics', return_value=None):
            success, message = deduct_inventory(order.id, test_admin.telegram_id, db_session)

        assert success == True

        # Check all items are deducted
        for product in multiple_products[:3]:
            db_session.refresh(product)
            assert product.reserved_quantity == 0

    def test_order_with_customer_info_update(self, db_session, test_user, test_goods, test_admin):
        """Test order updates customer info on completion"""
        # Create customer info
        customer_info = CustomerInfo(
            telegram_id=test_user.telegram_id,
            phone_number="+1234567890",
            delivery_address="123 Test Street"
        )
        db_session.add(customer_info)
        db_session.commit()

        initial_spendings = customer_info.total_spendings
        initial_orders_count = customer_info.completed_orders_count

        # Create and complete order
        order = Order(
            buyer_id=test_user.telegram_id,
            total_price=Decimal("99.99"),
            payment_method="cash",
            delivery_address="123 Test Street",
            phone_number="+1234567890",
            order_status="pending",
            order_code=generate_unique_order_code(db_session)
        )
        db_session.add(order)
        db_session.flush()

        order_item = OrderItem(
            order_id=order.id,
            item_name=test_goods.name,
            price=test_goods.price,
            quantity=1
        )
        db_session.add(order_item)
        db_session.commit()

        # Reserve and deduct
        items = [{'item_name': test_goods.name, 'quantity': 1}]
        reserve_inventory(order.id, items, 'cash', db_session)

        order.order_status = 'confirmed'
        db_session.commit()

        with patch('bot.database.methods.inventory.get_metrics', return_value=None):
            deduct_inventory(order.id, test_admin.telegram_id, db_session)

        # Mark as delivered
        order.order_status = 'delivered'
        order.completed_at = datetime.now(timezone.utc)

        # Update customer info (normally done by handler)
        customer_info.total_spendings += order.total_price
        customer_info.completed_orders_count += 1
        db_session.commit()

        db_session.refresh(customer_info)

        assert customer_info.total_spendings == initial_spendings + order.total_price
        assert customer_info.completed_orders_count == initial_orders_count + 1

    def test_order_insufficient_stock(self, db_session, test_user, test_goods_low_stock):
        """Test order fails when insufficient stock"""
        order = Order(
            buyer_id=test_user.telegram_id,
            total_price=Decimal("999.99"),
            payment_method="cash",
            delivery_address="123 Test Street",
            phone_number="+1234567890",
            order_status="pending",
            order_code=generate_unique_order_code(db_session)
        )
        db_session.add(order)
        db_session.flush()

        order_item = OrderItem(
            order_id=order.id,
            item_name=test_goods_low_stock.name,
            price=test_goods_low_stock.price,
            quantity=100  # More than available
        )
        db_session.add(order_item)
        db_session.commit()

        # Try to reserve
        items = [{'item_name': test_goods_low_stock.name, 'quantity': 100}]
        success, message = reserve_inventory(order.id, items, 'cash', db_session)

        assert success == False
        assert "insufficient" in message.lower()
