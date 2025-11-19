"""
Tests for database models
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from bot.database.models.main import (
    Role, User, Categories, Goods, Order, OrderItem,
    CustomerInfo, BitcoinAddress, ReferenceCode, ReferenceCodeUsage,
    ShoppingCart, InventoryLog, Permission
)


@pytest.mark.unit
@pytest.mark.models
class TestRoleModel:
    """Tests for Role model"""

    def test_create_role(self, db_session):
        """Test creating a role"""
        role = Role(name='TEST_ROLE', permissions=15)
        db_session.add(role)
        db_session.commit()

        assert role.id is not None
        assert role.name == 'TEST_ROLE'
        assert role.permissions == 15

    def test_role_permissions(self, db_session):
        """Test role permission methods"""
        role = Role(name='TEST', permissions=0)

        # Test add_permission
        role.add_permission(Permission.USE)
        assert role.has_permission(Permission.USE)

        role.add_permission(Permission.BROADCAST)
        assert role.has_permission(Permission.BROADCAST)
        assert role.permissions == 3  # USE + BROADCAST

        # Test remove_permission
        role.remove_permission(Permission.USE)
        assert not role.has_permission(Permission.USE)
        assert role.has_permission(Permission.BROADCAST)

        # Test reset_permissions
        role.reset_permissions()
        assert role.permissions == 0


@pytest.mark.unit
@pytest.mark.models
class TestUserModel:
    """Tests for User model"""

    def test_create_user(self, db_with_roles):
        """Test creating a user"""
        user = User(
            telegram_id=123456789,
            role_id=1,
            registration_date=datetime.now(timezone.utc),
            referral_id=None
        )
        db_with_roles.add(user)
        db_with_roles.commit()

        assert user.telegram_id == 123456789
        assert user.role_id == 1
        assert user.referral_id is None

    def test_user_with_referral(self, db_with_roles):
        """Test user with referral"""
        referrer = User(
            telegram_id=111111111,
            role_id=1,
            registration_date=datetime.now(timezone.utc),
            referral_id=None
        )
        db_with_roles.add(referrer)
        db_with_roles.commit()

        referred_user = User(
            telegram_id=222222222,
            role_id=1,
            registration_date=datetime.now(timezone.utc),
            referral_id=referrer.telegram_id
        )
        db_with_roles.add(referred_user)
        db_with_roles.commit()

        assert referred_user.referral_id == referrer.telegram_id

    def test_user_ban_fields(self, db_with_roles):
        """Test user ban fields"""
        admin = User(
            telegram_id=111111111,
            role_id=2,  # Admin
            registration_date=datetime.now(timezone.utc),
            referral_id=None
        )
        db_with_roles.add(admin)
        db_with_roles.commit()

        user = User(
            telegram_id=222222222,
            role_id=1,
            registration_date=datetime.now(timezone.utc),
            referral_id=None,
            is_banned=True,
            banned_at=datetime.now(timezone.utc),
            banned_by=admin.telegram_id,
            ban_reason="Test ban"
        )
        db_with_roles.add(user)
        db_with_roles.commit()

        assert user.is_banned is True
        assert user.banned_at is not None
        assert user.banned_by == admin.telegram_id
        assert user.ban_reason == "Test ban"

    def test_user_default_not_banned(self, db_with_roles):
        """Test user is not banned by default"""
        user = User(
            telegram_id=123456789,
            role_id=1,
            registration_date=datetime.now(timezone.utc),
            referral_id=None
        )
        db_with_roles.add(user)
        db_with_roles.commit()

        assert user.is_banned is False
        assert user.banned_at is None
        assert user.banned_by is None
        assert user.ban_reason is None


@pytest.mark.unit
@pytest.mark.models
class TestGoodsModel:
    """Tests for Goods model"""

    def test_create_goods(self, db_session, test_category):
        """Test creating goods"""
        goods = Goods(
            name="Test Item",
            price=Decimal("29.99"),
            description="Test description",
            category_name=test_category.name,
            stock_quantity=50,
            reserved_quantity=0
        )
        db_session.add(goods)
        db_session.commit()

        assert goods.name == "Test Item"
        assert goods.price == Decimal("29.99")
        assert goods.stock_quantity == 50
        assert goods.reserved_quantity == 0

    def test_available_quantity_property(self, db_session, test_category):
        """Test available_quantity property"""
        goods = Goods(
            name="Test Item",
            price=Decimal("29.99"),
            description="Test description",
            category_name=test_category.name,
            stock_quantity=100,
            reserved_quantity=30
        )
        db_session.add(goods)
        db_session.commit()

        assert goods.available_quantity == 70

    def test_available_quantity_never_negative(self, db_session, test_category):
        """Test that available_quantity never goes negative"""
        goods = Goods(
            name="Test Item",
            price=Decimal("29.99"),
            description="Test description",
            category_name=test_category.name,
            stock_quantity=10,
            reserved_quantity=20  # More reserved than stock
        )
        db_session.add(goods)
        db_session.commit()

        assert goods.available_quantity == 0


@pytest.mark.unit
@pytest.mark.models
class TestOrderModel:
    """Tests for Order model"""

    def test_create_order(self, db_session, test_user):
        """Test creating an order"""
        order = Order(
            buyer_id=test_user.telegram_id,
            total_price=Decimal("99.99"),
            payment_method="cash",
            delivery_address="123 Test St",
            phone_number="+1234567890",
            order_status="pending",
            order_code="ABC123"
        )
        db_session.add(order)
        db_session.commit()

        assert order.id is not None
        assert order.buyer_id == test_user.telegram_id
        assert order.order_status == "pending"
        assert order.order_code == "ABC123"

    def test_order_with_items(self, db_session, test_user, test_goods):
        """Test order with items"""
        order = Order(
            buyer_id=test_user.telegram_id,
            total_price=Decimal("99.99"),
            payment_method="cash",
            delivery_address="123 Test St",
            phone_number="+1234567890",
            order_status="pending",
            order_code="ABC123"
        )
        db_session.add(order)
        db_session.flush()

        order_item = OrderItem(
            order_id=order.id,
            item_name=test_goods.name,
            price=test_goods.price,
            quantity=2
        )
        db_session.add(order_item)
        db_session.commit()

        assert len(order.items) == 1
        assert order.items[0].quantity == 2
        assert order.items[0].item_name == test_goods.name


@pytest.mark.unit
@pytest.mark.models
class TestCustomerInfoModel:
    """Tests for CustomerInfo model"""

    def test_create_customer_info(self, db_session, test_user):
        """Test creating customer info"""
        customer_info = CustomerInfo(
            telegram_id=test_user.telegram_id,
            phone_number="+1234567890",
            delivery_address="123 Test St",
            delivery_note="Ring doorbell"
        )
        db_session.add(customer_info)
        db_session.commit()

        assert customer_info.telegram_id == test_user.telegram_id
        assert customer_info.total_spendings == Decimal("0")
        assert customer_info.completed_orders_count == 0
        assert customer_info.bonus_balance == Decimal("0")

    def test_customer_info_defaults(self, db_session, test_user):
        """Test default values are set correctly"""
        customer_info = CustomerInfo(
            telegram_id=test_user.telegram_id
        )
        db_session.add(customer_info)
        db_session.commit()

        # Test that numeric fields default to 0
        assert customer_info.total_spendings == Decimal("0")
        assert customer_info.completed_orders_count == 0
        assert customer_info.bonus_balance == Decimal("0")


@pytest.mark.unit
@pytest.mark.models
class TestBitcoinAddressModel:
    """Tests for BitcoinAddress model"""

    def test_create_bitcoin_address(self, db_session):
        """Test creating a Bitcoin address"""
        btc_addr = BitcoinAddress(address="bc1qtest123456789")
        db_session.add(btc_addr)
        db_session.commit()

        assert btc_addr.address == "bc1qtest123456789"
        assert btc_addr.is_used == False
        assert btc_addr.used_by is None

    def test_mark_bitcoin_address_used(self, db_session, test_user):
        """Test marking Bitcoin address as used"""
        btc_addr = BitcoinAddress(address="bc1qtest123456789")
        db_session.add(btc_addr)
        db_session.commit()

        btc_addr.is_used = True
        btc_addr.used_by = test_user.telegram_id
        btc_addr.used_at = datetime.now(timezone.utc)
        db_session.commit()

        assert btc_addr.is_used == True
        assert btc_addr.used_by == test_user.telegram_id
        assert btc_addr.used_at is not None


@pytest.mark.unit
@pytest.mark.models
class TestReferenceCodeModel:
    """Tests for ReferenceCode model"""

    def test_create_reference_code(self, db_session, test_admin):
        """Test creating a reference code"""
        ref_code = ReferenceCode(
            code="TESTCODE",
            created_by=test_admin.telegram_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            max_uses=10,
            note="Test code",
            is_admin_code=True
        )
        db_session.add(ref_code)
        db_session.commit()

        assert ref_code.code == "TESTCODE"
        assert ref_code.created_by == test_admin.telegram_id
        assert ref_code.current_uses == 0
        assert ref_code.is_active == True


@pytest.mark.unit
@pytest.mark.models
class TestShoppingCartModel:
    """Tests for ShoppingCart model"""

    def test_create_cart_item(self, db_session, test_user, test_goods):
        """Test creating a shopping cart item"""
        cart_item = ShoppingCart(
            user_id=test_user.telegram_id,
            item_name=test_goods.name,
            quantity=3
        )
        db_session.add(cart_item)
        db_session.commit()

        assert cart_item.user_id == test_user.telegram_id
        assert cart_item.item_name == test_goods.name
        assert cart_item.quantity == 3


@pytest.mark.unit
@pytest.mark.models
class TestInventoryLogModel:
    """Tests for InventoryLog model"""

    def test_create_inventory_log(self, db_session, test_goods, test_admin):
        """Test creating an inventory log entry"""
        log_entry = InventoryLog(
            item_name=test_goods.name,
            change_type='add',
            quantity_change=50,
            admin_id=test_admin.telegram_id,
            comment="Restocking"
        )
        db_session.add(log_entry)
        db_session.commit()

        assert log_entry.item_name == test_goods.name
        assert log_entry.change_type == 'add'
        assert log_entry.quantity_change == 50
        assert log_entry.admin_id == test_admin.telegram_id
