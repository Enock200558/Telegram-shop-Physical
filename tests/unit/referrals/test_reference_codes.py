"""
Tests for reference code system
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from bot.referrals.codes import (
    generate_reference_code,
    generate_unique_reference_code,
    create_reference_code,
    validate_reference_code,
    use_reference_code,
    deactivate_reference_code,
    get_user_reference_codes,
    get_reference_code_stats
)
from bot.database.models.main import ReferenceCode, ReferenceCodeUsage


@pytest.mark.unit
@pytest.mark.referrals
@pytest.mark.database
class TestReferenceCodeGeneration:
    """Tests for reference code generation"""

    def test_generate_reference_code(self):
        """Test generating a reference code"""
        code = generate_reference_code()

        assert len(code) == 8
        assert code.isupper()
        assert code.isalpha()

    def test_generate_unique_reference_code(self, db_session):
        """Test generating unique reference code"""
        code = generate_unique_reference_code()

        assert len(code) == 8
        # Verify it doesn't exist in database
        existing = db_session.query(ReferenceCode).filter_by(code=code).first()
        assert existing is None

    def test_generate_unique_reference_code_collision(self, db_session, test_user):
        """Test handling code collision"""
        # Pre-create some codes
        for i in range(5):
            ref_code = ReferenceCode(
                code=f"TESTCD{i:02d}",
                created_by=test_user.telegram_id,
                is_admin_code=True
            )
            db_session.add(ref_code)
        db_session.commit()

        # Should still generate a unique code
        code = generate_unique_reference_code()
        assert len(code) == 8


@pytest.mark.unit
@pytest.mark.referrals
@pytest.mark.database
class TestReferenceCodeCreation:
    """Tests for creating reference codes"""

    @patch('bot.referrals.codes.log_reference_code_creation')
    def test_create_admin_reference_code(self, mock_log, db_session, test_admin):
        """Test creating an admin reference code"""
        code = create_reference_code(
            created_by=test_admin.telegram_id,
            created_by_username="test_admin",
            is_admin_code=True,
            expires_in_hours=48,
            max_uses=10,
            note="Test code"
        )

        assert len(code) == 8

        ref_code = db_session.query(ReferenceCode).filter_by(code=code).first()
        assert ref_code is not None
        assert ref_code.is_admin_code == True
        assert ref_code.max_uses == 10
        assert ref_code.is_active == True

        mock_log.assert_called_once()

    @patch('bot.referrals.codes.log_reference_code_creation')
    def test_create_user_reference_code(self, mock_log, db_session, test_user):
        """Test creating a user reference code (limited)"""
        code = create_reference_code(
            created_by=test_user.telegram_id,
            created_by_username="test_user",
            is_admin_code=False
        )

        ref_code = db_session.query(ReferenceCode).filter_by(code=code).first()
        assert ref_code is not None
        assert ref_code.is_admin_code == False
        assert ref_code.max_uses == 1  # User codes limited to 1 use

    @patch('bot.referrals.codes.log_reference_code_creation')
    def test_create_unlimited_reference_code(self, mock_log, db_session, test_admin):
        """Test creating unlimited reference code"""
        code = create_reference_code(
            created_by=test_admin.telegram_id,
            created_by_username="test_admin",
            is_admin_code=True,
            expires_in_hours=None,
            max_uses=None,
            note="Unlimited code"
        )

        ref_code = db_session.query(ReferenceCode).filter_by(code=code).first()
        assert ref_code.expires_at is None
        assert ref_code.max_uses is None


@pytest.mark.unit
@pytest.mark.referrals
@pytest.mark.database
class TestReferenceCodeValidation:
    """Tests for validating reference codes"""

    def test_validate_valid_code(self, db_session, test_reference_code, test_user):
        """Test validating a valid reference code"""
        is_valid, error_msg, creator_id = validate_reference_code(
            test_reference_code.code,
            test_user.telegram_id
        )

        assert is_valid == True
        assert error_msg == ""
        assert creator_id == test_reference_code.created_by

    def test_validate_nonexistent_code(self, db_session, test_user):
        """Test validating non-existent code"""
        is_valid, error_msg, creator_id = validate_reference_code(
            "INVALID1",
            test_user.telegram_id
        )

        assert is_valid == False
        assert "invalid" in error_msg.lower()
        assert creator_id is None

    def test_validate_inactive_code(self, db_session, test_reference_code, test_user):
        """Test validating inactive code"""
        test_reference_code.is_active = False
        db_session.commit()

        is_valid, error_msg, creator_id = validate_reference_code(
            test_reference_code.code,
            test_user.telegram_id
        )

        assert is_valid == False
        assert "deactivated" in error_msg.lower()

    def test_validate_expired_code(self, db_session, test_admin, test_user):
        """Test validating expired code"""
        expired_code = ReferenceCode(
            code="EXPIRED1",
            created_by=test_admin.telegram_id,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            is_admin_code=True
        )
        db_session.add(expired_code)
        db_session.commit()

        is_valid, error_msg, creator_id = validate_reference_code(
            expired_code.code,
            test_user.telegram_id
        )

        assert is_valid == False
        assert "expired" in error_msg.lower()

    def test_validate_own_code(self, db_session, test_reference_code):
        """Test user cannot use their own code"""
        is_valid, error_msg, creator_id = validate_reference_code(
            test_reference_code.code,
            test_reference_code.created_by
        )

        assert is_valid == False
        assert "own" in error_msg.lower()

    def test_validate_already_used_code(self, db_session, test_reference_code, test_user):
        """Test code already used by this user"""
        # Create usage record
        usage = ReferenceCodeUsage(
            code=test_reference_code.code,
            used_by=test_user.telegram_id
        )
        db_session.add(usage)
        db_session.commit()

        is_valid, error_msg, creator_id = validate_reference_code(
            test_reference_code.code,
            test_user.telegram_id
        )

        assert is_valid == False
        assert "already" in error_msg.lower()

    def test_validate_max_uses_reached(self, db_session, test_admin):
        """Test code with max uses reached"""
        ref_code = ReferenceCode(
            code="MAXED001",
            created_by=test_admin.telegram_id,
            max_uses=2,
            current_uses=2,
            is_admin_code=True
        )
        db_session.add(ref_code)
        db_session.commit()

        is_valid, error_msg, creator_id = validate_reference_code(
            ref_code.code,
            999999999
        )

        assert is_valid == False
        assert "maximum" in error_msg.lower()


@pytest.mark.unit
@pytest.mark.referrals
@pytest.mark.database
class TestReferenceCodeUsage:
    """Tests for using reference codes"""

    @patch('bot.referrals.codes.log_reference_code_usage')
    def test_use_reference_code(self, mock_log, db_session, test_reference_code, test_user):
        """Test using a valid reference code"""
        success, error_msg, referrer_id = use_reference_code(
            test_reference_code.code,
            test_user.telegram_id,
            "test_user"
        )

        assert success == True
        assert referrer_id == test_reference_code.created_by

        # Check usage was recorded
        usage = db_session.query(ReferenceCodeUsage).filter_by(
            code=test_reference_code.code,
            used_by=test_user.telegram_id
        ).first()

        assert usage is not None

        # Check current_uses incremented
        db_session.refresh(test_reference_code)
        assert test_reference_code.current_uses == 1

    @patch('bot.referrals.codes.log_reference_code_usage')
    def test_use_invalid_code(self, mock_log, db_session, test_user):
        """Test using invalid code"""
        success, error_msg, referrer_id = use_reference_code(
            "INVALID1",
            test_user.telegram_id,
            "test_user"
        )

        assert success == False
        assert referrer_id is None


@pytest.mark.unit
@pytest.mark.referrals
@pytest.mark.database
class TestReferenceCodeDeactivation:
    """Tests for deactivating reference codes"""

    @patch('bot.referrals.codes.log_reference_code_deactivation')
    def test_deactivate_code(self, mock_log, db_session, test_reference_code, test_admin):
        """Test deactivating a reference code"""
        result = deactivate_reference_code(
            test_reference_code.code,
            test_admin.telegram_id,
            "test_admin",
            "Test deactivation"
        )

        assert result == True

        db_session.refresh(test_reference_code)
        assert test_reference_code.is_active == False

    def test_deactivate_nonexistent_code(self, db_session, test_admin):
        """Test deactivating non-existent code"""
        result = deactivate_reference_code(
            "INVALID1",
            test_admin.telegram_id,
            "test_admin",
            "Test"
        )

        assert result == False


@pytest.mark.unit
@pytest.mark.referrals
@pytest.mark.database
class TestReferenceCodeQueries:
    """Tests for querying reference codes"""

    def test_get_user_reference_codes(self, db_session, test_admin, test_reference_code):
        """Test getting all codes created by a user"""
        codes = get_user_reference_codes(test_admin.telegram_id)

        assert len(codes) >= 1
        assert any(code['code'] == test_reference_code.code for code in codes)

    def test_get_reference_code_stats(self, db_session, test_reference_code, test_user):
        """Test getting code statistics"""
        # Add some usages
        usage = ReferenceCodeUsage(
            code=test_reference_code.code,
            used_by=test_user.telegram_id
        )
        db_session.add(usage)
        test_reference_code.current_uses += 1
        db_session.commit()

        stats = get_reference_code_stats(test_reference_code.code)

        assert stats is not None
        assert stats['code'] == test_reference_code.code
        assert stats['current_uses'] == 1
        assert len(stats['users']) == 1

    def test_get_reference_code_stats_nonexistent(self, db_session):
        """Test getting stats for non-existent code"""
        stats = get_reference_code_stats("INVALID1")
        assert stats is None
