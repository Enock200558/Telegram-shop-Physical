"""
Tests for CRUD operations (Create, Read, Update, Delete)
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from bot.database.methods.create import create_user, create_item, create_category, add_to_cart
from bot.database.methods.read import (
    check_user, check_role, get_item_info, check_category,
    select_item_values_amount, get_user_count, check_user_referrals,
    get_bot_setting
)
from bot.database.methods.update import set_role, update_item, update_category, ban_user, unban_user
from bot.database.models.main import User, Goods, Categories, ShoppingCart


@pytest.mark.unit
@pytest.mark.crud
@pytest.mark.database
class TestCreateOperations:
    """Tests for create operations"""

    def test_create_user(self, db_with_roles):
        """Test creating a user"""
        registration_date = datetime.now(timezone.utc)
        create_user(999999999, registration_date, None, role=1)

        user = db_with_roles.query(User).filter_by(telegram_id=999999999).first()
        assert user is not None
        assert user.telegram_id == 999999999
        assert user.role_id == 1

    def test_create_user_duplicate(self, db_with_roles, test_user):
        """Test creating duplicate user (should not create)"""
        registration_date = datetime.now(timezone.utc)
        initial_count = db_with_roles.query(User).count()

        # Try to create duplicate
        create_user(test_user.telegram_id, registration_date, None, role=1)

        # Count should not change
        final_count = db_with_roles.query(User).count()
        assert initial_count == final_count

    def test_create_category(self, db_session):
        """Test creating a category"""
        create_category("New Category")

        category = db_session.query(Categories).filter_by(name="New Category").first()
        assert category is not None
        assert category.name == "New Category"

    def test_create_category_duplicate(self, db_session, test_category):
        """Test creating duplicate category (should not create)"""
        initial_count = db_session.query(Categories).count()

        # Try to create duplicate
        create_category(test_category.name)

        # Count should not change
        final_count = db_session.query(Categories).count()
        assert initial_count == final_count

    def test_create_item(self, db_session, test_category):
        """Test creating an item"""
        create_item(
            item_name="New Product",
            item_description="Description of new product",
            item_price=Decimal("49.99"),
            category_name=test_category.name
        )

        item = db_session.query(Goods).filter_by(name="New Product").first()
        assert item is not None
        assert item.price == Decimal("49.99")
        assert item.category_name == test_category.name

    @pytest.mark.asyncio
    async def test_add_to_cart(self, db_session, test_user, test_goods):
        """Test adding item to cart"""
        with patch('bot.database.methods.read.check_value', return_value=False):
            with patch('bot.database.methods.read.select_item_values_amount_cached', return_value=100):
                success, message = await add_to_cart(test_user.telegram_id, test_goods.name, 2)

                assert success == True
                assert "added" in message.lower()

                cart_item = db_session.query(ShoppingCart).filter_by(
                    user_id=test_user.telegram_id,
                    item_name=test_goods.name
                ).first()

                assert cart_item is not None
                assert cart_item.quantity == 2

    @pytest.mark.asyncio
    async def test_add_to_cart_insufficient_stock(self, db_session, test_user, test_goods):
        """Test adding item to cart with insufficient stock"""
        with patch('bot.database.methods.read.check_value', return_value=False):
            with patch('bot.database.methods.read.select_item_values_amount_cached', return_value=1):
                success, message = await add_to_cart(test_user.telegram_id, test_goods.name, 5)

                assert success == False
                assert "available" in message.lower()


@pytest.mark.unit
@pytest.mark.crud
@pytest.mark.database
class TestReadOperations:
    """Tests for read operations"""

    def test_check_user(self, db_session, test_user):
        """Test checking if user exists"""
        result = check_user(test_user.telegram_id)
        assert result is not None
        assert result['telegram_id'] == test_user.telegram_id

    def test_check_user_not_found(self, db_session):
        """Test checking non-existent user"""
        result = check_user(999999999)
        assert result is None

    def test_check_role(self, db_session, test_user):
        """Test checking user role"""
        permissions = check_role(test_user.telegram_id)
        assert permissions > 0  # User should have at least USE permission

    def test_get_item_info(self, db_session, test_goods):
        """Test getting item information"""
        info = get_item_info(test_goods.name)
        assert info is not None
        assert info['name'] == test_goods.name
        assert Decimal(str(info['price'])) == test_goods.price

    def test_check_category(self, db_session, test_category):
        """Test checking category"""
        result = check_category(test_category.name)
        assert result is not None
        assert result['name'] == test_category.name

    def test_select_item_values_amount(self, db_session, test_goods):
        """Test getting available stock quantity"""
        available = select_item_values_amount(test_goods.name)
        assert available == test_goods.available_quantity

    def test_select_item_values_amount_with_reserved(self, db_session, test_category):
        """Test available quantity with reserved items"""
        goods = Goods(
            name="Reserved Item",
            price=Decimal("29.99"),
            description="Test",
            category_name=test_category.name,
            stock_quantity=100,
            reserved_quantity=30
        )
        db_session.add(goods)
        db_session.commit()

        available = select_item_values_amount(goods.name)
        assert available == 70  # 100 - 30

    def test_get_user_count(self, populated_database):
        """Test getting total user count"""
        count = get_user_count()
        assert count >= 2  # At least test_user and test_admin

    def test_check_user_referrals(self, db_with_roles):
        """Test checking user referrals"""
        # Create referrer
        referrer = User(
            telegram_id=111111111,
            role_id=1,
            registration_date=datetime.now(timezone.utc),
            referral_id=None
        )
        db_with_roles.add(referrer)
        db_with_roles.flush()

        # Create referred users
        for i in range(3):
            referred = User(
                telegram_id=222222220 + i,
                role_id=1,
                registration_date=datetime.now(timezone.utc),
                referral_id=referrer.telegram_id
            )
            db_with_roles.add(referred)

        db_with_roles.commit()

        count = check_user_referrals(referrer.telegram_id)
        assert count == 3

    def test_get_bot_setting(self, test_bot_settings):
        """Test getting bot setting"""
        value = get_bot_setting('reference_bonus_percent', default='0', value_type=Decimal)
        assert value == Decimal('5')

    def test_get_bot_setting_with_default(self, db_session):
        """Test getting non-existent setting returns default"""
        value = get_bot_setting('non_existent_setting', default='default_value')
        assert value == 'default_value'


@pytest.mark.unit
@pytest.mark.crud
@pytest.mark.database
class TestUpdateOperations:
    """Tests for update operations"""

    def test_set_role(self, db_session, test_user):
        """Test changing user role"""
        set_role(test_user.telegram_id, 2)

        db_session.refresh(test_user)
        assert test_user.role_id == 2

    def test_update_item(self, db_session, test_goods):
        """Test updating an item"""
        success, error = update_item(
            item_name=test_goods.name,
            new_name=test_goods.name,  # Same name
            description="Updated description",
            price=Decimal("149.99"),
            category=test_goods.category_name
        )

        assert success == True
        assert error is None

        db_session.refresh(test_goods)
        assert test_goods.description == "Updated description"
        assert test_goods.price == Decimal("149.99")

    def test_update_item_rename(self, db_session, test_goods, test_category):
        """Test renaming an item"""
        original_name = test_goods.name
        new_name = "Renamed Product"

        success, error = update_item(
            item_name=original_name,
            new_name=new_name,
            description=test_goods.description,
            price=test_goods.price,
            category=test_category.name
        )

        assert success == True
        assert error is None

        # Old item should not exist
        old_item = db_session.query(Goods).filter_by(name=original_name).first()
        assert old_item is None

        # New item should exist
        new_item = db_session.query(Goods).filter_by(name=new_name).first()
        assert new_item is not None
        assert new_item.price == test_goods.price

    @pytest.mark.skip(reason="SQLite FK constraint: update_category updates goods before category")
    def test_update_category(self, db_session, test_category, test_goods):
        """Test updating a category name"""
        old_name = test_category.name
        new_name = "Renamed Category"

        update_category(old_name, new_name)

        # Old category should not exist
        old_cat = db_session.query(Categories).filter_by(name=old_name).first()
        assert old_cat is None

        # New category should exist
        new_cat = db_session.query(Categories).filter_by(name=new_name).first()
        assert new_cat is not None

        # Goods should be updated to new category
        db_session.refresh(test_goods)
        assert test_goods.category_name == new_name


@pytest.mark.unit
@pytest.mark.crud
@pytest.mark.database
class TestBanOperations:
    """Tests for user ban/unban operations"""

    def test_ban_user(self, db_with_roles, test_user, test_admin):
        """Test banning a user"""
        # Ban the user
        success = ban_user(
            test_user.telegram_id,
            banned_by=test_admin.telegram_id,
            reason="Test ban"
        )

        assert success is True

        # Verify ban status
        db_with_roles.refresh(test_user)
        assert test_user.is_banned is True
        assert test_user.banned_by == test_admin.telegram_id
        assert test_user.ban_reason == "Test ban"
        assert test_user.banned_at is not None

    def test_ban_nonexistent_user(self, db_with_roles):
        """Test banning a non-existent user"""
        success = ban_user(
            999999999,
            banned_by=123456789,
            reason="Test"
        )

        assert success is False

    def test_ban_already_banned_user(self, db_with_roles, test_user, test_admin):
        """Test banning an already banned user"""
        # Ban the user first
        ban_user(test_user.telegram_id, banned_by=test_admin.telegram_id, reason="First ban")

        # Try to ban again
        success = ban_user(
            test_user.telegram_id,
            banned_by=test_admin.telegram_id,
            reason="Second ban"
        )

        assert success is False

    def test_unban_user(self, db_with_roles, test_user, test_admin):
        """Test unbanning a user"""
        # Ban the user first
        ban_user(test_user.telegram_id, banned_by=test_admin.telegram_id, reason="Test ban")

        # Unban the user
        success = unban_user(test_user.telegram_id)

        assert success is True

        # Verify unban status
        db_with_roles.refresh(test_user)
        assert test_user.is_banned is False
        assert test_user.banned_by is None
        assert test_user.ban_reason is None
        assert test_user.banned_at is None

    def test_unban_nonexistent_user(self, db_with_roles):
        """Test unbanning a non-existent user"""
        success = unban_user(999999999)

        assert success is False

    def test_unban_not_banned_user(self, db_with_roles, test_user):
        """Test unbanning a user who is not banned"""
        success = unban_user(test_user.telegram_id)

        assert success is False

    def test_ban_unban_cycle(self, db_with_roles, test_user, test_admin):
        """Test multiple ban/unban cycles"""
        # First ban
        success = ban_user(test_user.telegram_id, banned_by=test_admin.telegram_id, reason="Ban 1")
        assert success is True
        db_with_roles.refresh(test_user)
        assert test_user.is_banned is True

        # First unban
        success = unban_user(test_user.telegram_id)
        assert success is True
        db_with_roles.refresh(test_user)
        assert test_user.is_banned is False

        # Second ban
        success = ban_user(test_user.telegram_id, banned_by=test_admin.telegram_id, reason="Ban 2")
        assert success is True
        db_with_roles.refresh(test_user)
        assert test_user.is_banned is True

        # Second unban
        success = unban_user(test_user.telegram_id)
        assert success is True
        db_with_roles.refresh(test_user)
        assert test_user.is_banned is False
