from aiogram import Bot


async def get_telegram_username(telegram_id: int, bot: Bot) -> str:
    """
    Get Telegram username using Bot API

    Args:
        telegram_id: Telegram user ID
        bot: Bot instance to use for API calls

    Returns:
        Username (without @ prefix if available) or fallback user_{telegram_id}
    """
    try:
        chat = await bot.get_chat(telegram_id)
        if chat.username:
            return chat.username
    except Exception:
        # If we can't get username from Telegram, use fallback
        pass

    return f"user_{telegram_id}"
