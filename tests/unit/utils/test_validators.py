"""
Tests for validator utilities
"""
import pytest
from decimal import Decimal
from pydantic import ValidationError

from bot.utils.validators import (
    UserDataUpdate,
    CategoryRequest,
    BroadcastMessage,
    SearchQuery,
    validate_telegram_id,
    validate_money_amount,
    sanitize_html
)


@pytest.mark.unit
@pytest.mark.validators
class TestUserDataUpdate:
    """Tests for UserDataUpdate validator"""

    def test_valid_user_data_update(self):
        """Test valid user data update"""
        data = UserDataUpdate(
            telegram_id=123456789,
            balance=Decimal("100.50")
        )

        assert data.telegram_id == 123456789
        assert data.balance == Decimal("100.50")

    def test_invalid_telegram_id(self):
        """Test invalid telegram ID"""
        with pytest.raises(ValidationError):
            UserDataUpdate(telegram_id=0, balance=Decimal("100"))

    def test_negative_balance(self):
        """Test negative balance validation"""
        with pytest.raises(ValidationError):
            UserDataUpdate(
                telegram_id=123456789,
                balance=Decimal("-10")
            )

    def test_balance_too_large(self):
        """Test balance exceeds maximum"""
        with pytest.raises(ValidationError):
            UserDataUpdate(
                telegram_id=123456789,
                balance=Decimal("2000000")
            )


@pytest.mark.unit
@pytest.mark.validators
class TestCategoryRequest:
    """Tests for CategoryRequest validator"""

    def test_valid_category(self):
        """Test valid category"""
        category = CategoryRequest(name="Electronics")
        assert category.name == "Electronics"

    def test_category_too_short(self):
        """Test category name too short"""
        with pytest.raises(ValidationError):
            CategoryRequest(name="")

    def test_category_too_long(self):
        """Test category name too long"""
        with pytest.raises(ValidationError):
            CategoryRequest(name="A" * 101)

    def test_sanitize_category_name(self):
        """Test sanitizing category name"""
        category = CategoryRequest(name="  Test   Category  ")
        sanitized = category.sanitize_name()

        assert sanitized == "Test Category"

    def test_sanitize_removes_html(self):
        """Test that HTML tags are removed"""
        category = CategoryRequest(name="<script>alert('xss')</script>Test")
        sanitized = category.sanitize_name()

        assert "<script>" not in sanitized
        assert "alert" in sanitized


@pytest.mark.unit
@pytest.mark.validators
class TestBroadcastMessage:
    """Tests for BroadcastMessage validator"""

    def test_valid_broadcast_message(self):
        """Test valid broadcast message"""
        message = BroadcastMessage(
            text="<b>Important</b> announcement!",
            parse_mode="HTML"
        )

        assert message.text == "<b>Important</b> announcement!"
        assert message.parse_mode == "HTML"

    def test_message_too_short(self):
        """Test message too short"""
        with pytest.raises(ValidationError):
            BroadcastMessage(text="", parse_mode="HTML")

    def test_message_too_long(self):
        """Test message too long"""
        with pytest.raises(ValidationError):
            BroadcastMessage(text="A" * 5000, parse_mode="HTML")

    def test_invalid_parse_mode(self):
        """Test invalid parse mode"""
        with pytest.raises(ValidationError):
            BroadcastMessage(text="Test", parse_mode="Invalid")

    def test_unbalanced_html_tags(self):
        """Test unbalanced HTML tags validation"""
        with pytest.raises(ValidationError):
            BroadcastMessage(
                text="<b>Bold text without closing tag",
                parse_mode="HTML"
            )


@pytest.mark.unit
@pytest.mark.validators
class TestSearchQuery:
    """Tests for SearchQuery validator"""

    def test_valid_search_query(self):
        """Test valid search query"""
        query = SearchQuery(query="laptop", limit=20)

        assert query.query == "laptop"
        assert query.limit == 20

    def test_query_too_short(self):
        """Test query too short"""
        with pytest.raises(ValidationError):
            SearchQuery(query="", limit=10)

    def test_limit_too_small(self):
        """Test limit too small"""
        with pytest.raises(ValidationError):
            SearchQuery(query="test", limit=0)

    def test_limit_too_large(self):
        """Test limit too large"""
        with pytest.raises(ValidationError):
            SearchQuery(query="test", limit=200)

    def test_sanitize_query(self):
        """Test sanitizing search query"""
        query = SearchQuery(query="test@#$%query", limit=10)
        sanitized = query.sanitize_query("test@#$%query")

        assert "@" not in sanitized
        assert "#" not in sanitized


@pytest.mark.unit
@pytest.mark.validators
class TestHelperFunctions:
    """Tests for validator helper functions"""

    def test_validate_telegram_id_valid(self):
        """Test validating valid telegram ID"""
        telegram_id = validate_telegram_id(123456789)
        assert telegram_id == 123456789

    def test_validate_telegram_id_string(self):
        """Test validating telegram ID from string"""
        telegram_id = validate_telegram_id("123456789")
        assert telegram_id == 123456789

    def test_validate_telegram_id_invalid(self):
        """Test validating invalid telegram ID"""
        with pytest.raises(ValueError):
            validate_telegram_id("invalid")

    def test_validate_telegram_id_negative(self):
        """Test validating negative telegram ID"""
        with pytest.raises(ValueError):
            validate_telegram_id(-123456789)

    def test_validate_telegram_id_too_large(self):
        """Test validating telegram ID that's too large"""
        with pytest.raises(ValueError):
            validate_telegram_id(99999999999)

    def test_validate_money_amount_valid(self):
        """Test validating valid money amount"""
        amount = validate_money_amount("99.99")
        assert amount == Decimal("99.99")

    def test_validate_money_amount_rounds(self):
        """Test that amount is rounded to 2 decimals"""
        amount = validate_money_amount("99.999")
        assert amount == Decimal("100.00")

    def test_validate_money_amount_too_small(self):
        """Test amount below minimum"""
        with pytest.raises(ValueError):
            validate_money_amount("0.001")

    def test_validate_money_amount_too_large(self):
        """Test amount above maximum"""
        with pytest.raises(ValueError):
            validate_money_amount("2000000")

    def test_sanitize_html_escapes_dangerous(self):
        """Test that dangerous characters are escaped"""
        html = sanitize_html("<script>alert('xss')</script>")

        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_sanitize_html_allows_safe_tags(self):
        """Test that safe tags are allowed"""
        html = sanitize_html("<b>Bold</b> <i>Italic</i>")

        assert "<b>Bold</b>" in html
        assert "<i>Italic</i>" in html

    def test_sanitize_html_mixed(self):
        """Test mixed safe and unsafe content"""
        html = sanitize_html("<b>Safe</b> <script>unsafe</script>")

        assert "<b>Safe</b>" in html
        assert "<script>" not in html
