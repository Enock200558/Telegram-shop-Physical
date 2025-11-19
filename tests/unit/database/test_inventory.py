"""
Tests for inventory management system
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from bot.database.methods.inventory import (
    reserve_inventory,
    release_reservation,
    deduct_inventory,
    add_inventory,
    get_inventory_stats,
    log_inventory_change
)
from bot.database.models.main import Goods, Order, OrderItem, InventoryLog


@pytest.mark.unit
@pytest.mark.inventory
@pytest.mark.database
class TestInventoryReservation:
    """Tests for inventory reservation"""

    def test_reserve_inventory(self, db_session, test_order, test_goods):
        """Test reserving inventory for an order"""
        initial_reserved = test_goods.reserved_quantity

        items = [{'item_name': test_goods.name, 'quantity': 5}]
        success, message = reserve_inventory(test_order.id, items, 'cash', db_session)
        db_session.commit()  # Inventory functions don't commit when session is passed

        assert success == True
        assert "success" in message.lower()

        db_session.refresh(test_goods)
        assert test_goods.reserved_quantity == initial_reserved + 5

        db_session.refresh(test_order)
        assert test_order.order_status == 'reserved'
        assert test_order.reserved_until is not None

    def test_reserve_inventory_insufficient_stock(self, db_session, test_order, test_goods_low_stock):
        """Test reserving more inventory than available"""
        items = [{'item_name': test_goods_low_stock.name, 'quantity': 10}]
        success, message = reserve_inventory(test_order.id, items, 'cash', db_session)

        assert success == False
        assert "insufficient" in message.lower()

    def test_reserve_inventory_nonexistent_item(self, db_session, test_order):
        """Test reserving non-existent item"""
        items = [{'item_name': 'Non-Existent Product', 'quantity': 1}]
        success, message = reserve_inventory(test_order.id, items, 'cash', db_session)

        assert success == False
        assert "not found" in message.lower()

    def test_reserve_inventory_multiple_items(self, db_session, test_order, multiple_products):
        """Test reserving multiple items at once"""
        items = [
            {'item_name': multiple_products[0].name, 'quantity': 5},
            {'item_name': multiple_products[1].name, 'quantity': 3},
        ]

        success, message = reserve_inventory(test_order.id, items, 'cash', db_session)

        assert success == True

        db_session.refresh(multiple_products[0])
        db_session.refresh(multiple_products[1])

        assert multiple_products[0].reserved_quantity == 5
        assert multiple_products[1].reserved_quantity == 3


@pytest.mark.unit
@pytest.mark.inventory
@pytest.mark.database
class TestInventoryRelease:
    """Tests for releasing inventory reservations"""

    def test_release_reservation(self, db_session, test_goods, test_user):
        """Test releasing reserved inventory"""
        # Create order with reservation
        order = Order(
            buyer_id=test_user.telegram_id,
            total_price=Decimal("99.99"),
            payment_method="cash",
            delivery_address="123 Test St",
            phone_number="+1234567890",
            order_status="reserved",
            order_code="REL001"
        )
        db_session.add(order)
        db_session.flush()

        order_item = OrderItem(
            order_id=order.id,
            item_name=test_goods.name,
            price=test_goods.price,
            quantity=10
        )
        db_session.add(order_item)

        # Reserve inventory
        test_goods.reserved_quantity += 10
        db_session.commit()

        initial_reserved = test_goods.reserved_quantity

        # Release reservation
        with patch('bot.database.methods.inventory.get_metrics', return_value=None):
            success, message = release_reservation(order.id, "Order cancelled", db_session)
        db_session.commit()  # Inventory functions don't commit when session is passed

        assert success == True

        db_session.refresh(test_goods)
        assert test_goods.reserved_quantity == initial_reserved - 10

    def test_release_reservation_nonexistent_order(self, db_session):
        """Test releasing reservation for non-existent order"""
        success, message = release_reservation(999999, "Test", db_session)

        assert success == False
        assert "not found" in message.lower()


@pytest.mark.unit
@pytest.mark.inventory
@pytest.mark.database
class TestInventoryDeduction:
    """Tests for deducting inventory (actual stock reduction)"""

    def test_deduct_inventory(self, db_session, test_goods, test_user, test_admin):
        """Test deducting inventory on order completion"""
        # Create order
        order = Order(
            buyer_id=test_user.telegram_id,
            total_price=Decimal("199.98"),
            payment_method="cash",
            delivery_address="123 Test St",
            phone_number="+1234567890",
            order_status="confirmed",
            order_code="DED001"
        )
        db_session.add(order)
        db_session.flush()

        order_item = OrderItem(
            order_id=order.id,
            item_name=test_goods.name,
            price=test_goods.price,
            quantity=10
        )
        db_session.add(order_item)

        # Reserve inventory first
        test_goods.reserved_quantity += 10
        initial_stock = test_goods.stock_quantity
        db_session.commit()

        # Deduct inventory
        with patch('bot.database.methods.inventory.get_metrics', return_value=None):
            success, message = deduct_inventory(order.id, test_admin.telegram_id, db_session)
        db_session.commit()  # Inventory functions don't commit when session is passed

        assert success == True

        db_session.refresh(test_goods)
        assert test_goods.stock_quantity == initial_stock - 10
        assert test_goods.reserved_quantity == 0

    def test_deduct_inventory_would_go_negative(self, db_session, test_goods_low_stock, test_user):
        """Test that deduction fails if stock would go negative"""
        order = Order(
            buyer_id=test_user.telegram_id,
            total_price=Decimal("99.99"),
            payment_method="cash",
            delivery_address="123 Test St",
            phone_number="+1234567890",
            order_status="confirmed",
            order_code="NEG001"
        )
        db_session.add(order)
        db_session.flush()

        # Try to deduct more than available
        order_item = OrderItem(
            order_id=order.id,
            item_name=test_goods_low_stock.name,
            price=test_goods_low_stock.price,
            quantity=100  # More than stock
        )
        db_session.add(order_item)
        test_goods_low_stock.reserved_quantity += 100
        db_session.commit()

        with patch('bot.database.methods.inventory.get_metrics', return_value=None):
            success, message = deduct_inventory(order.id, None, db_session)

        assert success == False
        assert "negative" in message.lower()


@pytest.mark.unit
@pytest.mark.inventory
@pytest.mark.database
class TestInventoryAddition:
    """Tests for adding inventory (restocking)"""

    def test_add_inventory(self, db_session, test_goods, test_admin):
        """Test adding inventory (restocking)"""
        initial_stock = test_goods.stock_quantity

        success, message = add_inventory(
            test_goods.name,
            quantity=50,
            admin_id=test_admin.telegram_id,
            comment="Restocking",
            session=db_session
        )
        db_session.commit()  # Inventory functions don't commit when session is passed

        assert success == True

        db_session.refresh(test_goods)
        assert test_goods.stock_quantity == initial_stock + 50

    def test_add_inventory_nonexistent_item(self, db_session):
        """Test adding inventory for non-existent item"""
        success, message = add_inventory(
            "Non-Existent Product",
            quantity=50,
            session=db_session
        )

        assert success == False
        assert "not found" in message.lower()


@pytest.mark.unit
@pytest.mark.inventory
@pytest.mark.database
class TestInventoryStats:
    """Tests for inventory statistics"""

    def test_get_inventory_stats(self, db_session, test_goods):
        """Test getting inventory statistics"""
        test_goods.stock_quantity = 100
        test_goods.reserved_quantity = 20
        db_session.commit()

        stats = get_inventory_stats(test_goods.name)

        assert stats is not None
        assert stats['stock'] == 100
        assert stats['reserved'] == 20
        assert stats['available'] == 80

    def test_get_inventory_stats_nonexistent(self, db_session):
        """Test getting stats for non-existent item"""
        stats = get_inventory_stats("Non-Existent Product")
        assert stats is None


@pytest.mark.unit
@pytest.mark.inventory
@pytest.mark.database
class TestInventoryLogging:
    """Tests for inventory change logging"""

    def test_log_inventory_change(self, db_session, test_goods, test_admin):
        """Test logging inventory change"""
        log_inventory_change(
            item_name=test_goods.name,
            change_type='add',
            quantity_change=50,
            admin_id=test_admin.telegram_id,
            comment="Test log entry",
            session=db_session
        )

        log_entry = db_session.query(InventoryLog).filter_by(
            item_name=test_goods.name
        ).first()

        assert log_entry is not None
        assert log_entry.change_type == 'add'
        assert log_entry.quantity_change == 50
        assert log_entry.admin_id == test_admin.telegram_id
