import secrets
import string


def generate_order_code() -> str:
    """
    Generate a secure 6-character uppercase order code

    Returns:
        6-character uppercase code (e.g., ECBDJI)
    """
    # Use secrets for cryptographically strong random generation
    characters = string.ascii_uppercase
    code = ''.join(secrets.choice(characters) for _ in range(6))
    return code


def generate_unique_order_code(session=None) -> str:
    """
    Generate a unique order code that doesn't exist in the database

    Args:
        session: Optional SQLAlchemy session. If provided, uses that session.
                 Otherwise creates a new one.

    Returns:
        Unique 6-character uppercase code

    Raises:
        RuntimeError: If unable to generate unique code after 100 attempts
    """
    # Lazy import to avoid circular dependency
    from bot.database.models.main import Order

    max_attempts = 100
    attempts = 0

    # Use provided session or create new one
    if session:
        while attempts < max_attempts:
            code = generate_order_code()

            # Check if code already exists
            existing = session.query(Order).filter_by(order_code=code).first()
            if not existing:
                return code

            attempts += 1

        # If we couldn't generate a unique code after 100 attempts, something is wrong
        raise RuntimeError("Failed to generate unique order code after 100 attempts")
    else:
        # Create our own session (lazy import to avoid circular dependency)
        from bot.database.main import Database
        with Database().session() as db_session:
            while attempts < max_attempts:
                code = generate_order_code()

                # Check if code already exists
                existing = db_session.query(Order).filter_by(order_code=code).first()
                if not existing:
                    return code

                attempts += 1

            # If we couldn't generate a unique code after 100 attempts, something is wrong
            raise RuntimeError("Failed to generate unique order code after 100 attempts")
