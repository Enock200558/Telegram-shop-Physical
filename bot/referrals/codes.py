import secrets
import string
from datetime import timedelta
from typing import Optional, Tuple
import pytz

from bot.database.main import Database
from bot.database.models.main import ReferenceCode, ReferenceCodeUsage
from bot.export.custom_logging import (
    log_reference_code_creation,
    log_reference_code_usage,
    log_reference_code_deactivation
)
from bot.config.timezone import get_localized_time


def generate_reference_code() -> str:
    """
    Generate a secure 8-character uppercase reference code

    Returns:
        8-character uppercase code
    """
    # Use secrets for cryptographically strong random generation
    characters = string.ascii_uppercase
    code = ''.join(secrets.choice(characters) for _ in range(8))
    return code


def generate_unique_reference_code() -> str:
    """
    Generate a unique reference code that doesn't exist in the database

    Returns:
        Unique 8-character uppercase code
    """
    max_attempts = 100
    attempts = 0

    with Database().session() as session:
        while attempts < max_attempts:
            code = generate_reference_code()

            # Check if code already exists
            existing = session.query(ReferenceCode).filter_by(code=code).first()
            if not existing:
                return code

            attempts += 1

        # If we couldn't generate a unique code after 100 attempts, something is wrong
        raise RuntimeError("Failed to generate unique reference code after 100 attempts")


def create_reference_code(
    created_by: int,
    created_by_username: str,
    is_admin_code: bool = False,
    expires_in_hours: Optional[int] = None,
    max_uses: Optional[int] = None,
    note: Optional[str] = None
) -> str:
    """
    Create a new reference code

    Args:
        created_by: Telegram ID of creator
        created_by_username: Username of creator
        is_admin_code: Whether this is an admin code
        expires_in_hours: Hours until expiration (None for no expiry)
        max_uses: Maximum number of uses (None for unlimited)
        note: Optional note

    Returns:
        Generated reference code

    Raises:
        ValueError: If validation fails
    """
    # Validate parameters
    if not is_admin_code:
        # User codes are limited to 24 hours and 1 use
        expires_in_hours = 24
        max_uses = 1
    else:
        # Admin codes can be customized
        if expires_in_hours is not None and expires_in_hours <= 0:
            raise ValueError("Expiration hours must be positive")
        if max_uses is not None and max_uses <= 0:
            raise ValueError("Max uses must be positive")

    # Generate unique code
    code = generate_unique_reference_code()

    # Calculate expiration time
    expires_at = None
    if expires_in_hours:
        expires_at = get_localized_time() + timedelta(hours=expires_in_hours)

    # Create in database
    with Database().session() as session:
        ref_code = ReferenceCode(
            code=code,
            created_by=created_by,
            expires_at=expires_at,
            max_uses=max_uses,
            note=note,
            is_admin_code=is_admin_code
        )
        session.add(ref_code)
        session.commit()

    # Log creation
    log_reference_code_creation(
        code=code,
        created_by=created_by,
        created_by_username=created_by_username,
        expires_at=expires_at,
        max_uses=max_uses,
        note=note,
        is_admin=is_admin_code
    )

    return code


def validate_reference_code(code: str, user_id: int) -> Tuple[bool, str, Optional[int]]:
    """
    Validate a reference code

    Args:
        code: Reference code to validate
        user_id: Telegram ID of user trying to use the code

    Returns:
        Tuple of (is_valid, error_message, creator_id)
        - is_valid: Whether the code is valid
        - error_message: Error message if invalid, empty string if valid
        - creator_id: Telegram ID of code creator if valid, None if invalid
    """
    with Database().session() as session:
        # Find the reference code
        ref_code = session.query(ReferenceCode).filter_by(code=code).first()

        if not ref_code:
            return False, "Invalid reference code", None

        # Check if active
        if not ref_code.is_active:
            return False, "This reference code has been deactivated", None

        # Check if expired
        if ref_code.expires_at:
            now = get_localized_time()
            # Make expires_at timezone-aware if it isn't
            expires_at = ref_code.expires_at
            if expires_at.tzinfo is None:
                expires_at = pytz.UTC.localize(expires_at)

            if now > expires_at:
                return False, "This reference code has expired", None

        # Check if user is trying to use their own code
        if ref_code.created_by == user_id:
            return False, "You cannot use your own reference code", None

        # Check if already used by this user
        existing_usage = session.query(ReferenceCodeUsage).filter_by(
            code=code,
            used_by=user_id
        ).first()

        if existing_usage:
            return False, "You have already used this reference code", None

        # Check if max uses reached
        if ref_code.max_uses is not None:
            if ref_code.current_uses >= ref_code.max_uses:
                return False, "This reference code has reached its maximum usage limit", None

        return True, "", ref_code.created_by


def use_reference_code(code: str, used_by: int, used_by_username: str) -> Tuple[bool, str, Optional[int]]:
    """
    Mark a reference code as used by a user

    Args:
        code: Reference code
        used_by: Telegram ID of user
        used_by_username: Username of user

    Returns:
        Tuple of (success, error_message, referrer_id)
    """
    # Validate first
    is_valid, error_msg, creator_id = validate_reference_code(code, used_by)

    if not is_valid:
        return False, error_msg, None

    with Database().session() as session:
        # Get the reference code
        ref_code = session.query(ReferenceCode).filter_by(code=code).first()

        if not ref_code:
            return False, "Reference code not found", None

        # Create usage record
        usage = ReferenceCodeUsage(code=code, used_by=used_by)
        session.add(usage)

        # Increment usage count
        ref_code.current_uses += 1

        session.commit()

        # Get creator username for logging
        from bot.database.models.main import User
        creator = session.query(User).filter_by(telegram_id=creator_id).first()
        creator_username = f"user_{creator_id}"  # Default if user not found

        # Log usage
        log_reference_code_usage(
            code=code,
            used_by=used_by,
            used_by_username=used_by_username,
            referred_by=creator_id,
            referred_by_username=creator_username
        )

        return True, "", creator_id


def deactivate_reference_code(code: str, deactivated_by: int,
                              deactivated_by_username: str, reason: str = "Admin action") -> bool:
    """
    Deactivate a reference code

    Args:
        code: Reference code to deactivate
        deactivated_by: Telegram ID of admin
        deactivated_by_username: Username of admin
        reason: Reason for deactivation

    Returns:
        True if successful, False otherwise
    """
    with Database().session() as session:
        ref_code = session.query(ReferenceCode).filter_by(code=code).first()

        if not ref_code:
            return False

        ref_code.is_active = False
        session.commit()

        # Log deactivation
        log_reference_code_deactivation(
            code=code,
            deactivated_by=deactivated_by,
            deactivated_by_username=deactivated_by_username,
            reason=reason
        )

        return True


def get_user_reference_codes(user_id: int, include_inactive: bool = False):
    """
    Get all reference codes created by a user

    Args:
        user_id: Telegram ID
        include_inactive: Whether to include inactive codes

    Returns:
        List of reference code dictionaries
    """
    with Database().session() as session:
        query = session.query(ReferenceCode).filter_by(created_by=user_id)

        if not include_inactive:
            query = query.filter_by(is_active=True)

        codes = query.order_by(ReferenceCode.created_at.desc()).all()

        result = []
        for code in codes:
            result.append({
                'code': code.code,
                'created_at': code.created_at,
                'expires_at': code.expires_at,
                'max_uses': code.max_uses,
                'current_uses': code.current_uses,
                'note': code.note,
                'is_active': code.is_active,
                'is_admin_code': code.is_admin_code
            })

        return result


def get_reference_code_stats(code: str):
    """
    Get statistics for a reference code

    Args:
        code: Reference code

    Returns:
        Dictionary with code statistics or None if not found
    """
    with Database().session() as session:
        ref_code = session.query(ReferenceCode).filter_by(code=code).first()

        if not ref_code:
            return None

        # Get all users who used this code
        usages = session.query(ReferenceCodeUsage).filter_by(code=code).all()

        return {
            'code': code,
            'created_by': ref_code.created_by,
            'created_at': ref_code.created_at,
            'expires_at': ref_code.expires_at,
            'max_uses': ref_code.max_uses,
            'current_uses': ref_code.current_uses,
            'note': ref_code.note,
            'is_active': ref_code.is_active,
            'is_admin_code': ref_code.is_admin_code,
            'users': [{'user_id': u.used_by, 'used_at': u.used_at} for u in usages]
        }
