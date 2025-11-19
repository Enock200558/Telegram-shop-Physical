"""
Tests for order code generation
"""
import pytest
from unittest.mock import patch, MagicMock

from bot.utils.order_codes import generate_order_code, generate_unique_order_code


@pytest.mark.unit
@pytest.mark.validators
class TestOrderCodeGeneration:
    """Tests for order code generation"""

    def test_generate_order_code(self):
        """Test generating an order code"""
        code = generate_order_code()

        assert len(code) == 6
        assert code.isupper()
        assert code.isalpha()

    def test_generate_order_code_uniqueness(self):
        """Test that generated codes are random"""
        codes = set()
        for _ in range(100):
            code = generate_order_code()
            codes.add(code)

        # Should generate at least 90 unique codes out of 100
        # (extremely unlikely to have 10+ collisions)
        assert len(codes) >= 90

    def test_generate_unique_order_code(self, db_session):
        """Test generating unique order code"""
        code = generate_unique_order_code(session=db_session)

        assert len(code) == 6
        assert code.isupper()

    def test_generate_unique_order_code_avoids_collision(self, db_session, test_order):
        """Test that unique code avoids existing codes"""
        # Mock to return test_order.order_code first, then a new code
        with patch('bot.utils.order_codes.generate_order_code') as mock_gen:
            mock_gen.side_effect = [test_order.order_code, "UNIQUE"]

            code = generate_unique_order_code(session=db_session)

            # Should not return the existing code
            assert code != test_order.order_code
            assert code == "UNIQUE"

    def test_generate_unique_order_code_max_attempts(self, db_session, test_user):
        """Test that RuntimeError is raised after max attempts"""
        with patch('bot.utils.order_codes.generate_order_code') as mock_gen:
            # Always return same code (will always collide after first)
            mock_gen.return_value = "COLLISION"

            # Pre-create order with this code
            from bot.database.models.main import Order
            order = Order(
                buyer_id=test_user.telegram_id,
                total_price=100,
                payment_method="cash",
                delivery_address="Test",
                phone_number="123",
                order_code="COLLISION"
            )
            db_session.add(order)
            db_session.commit()

            with pytest.raises(RuntimeError, match="Failed to generate unique order code"):
                generate_unique_order_code(session=db_session)
