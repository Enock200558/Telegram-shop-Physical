from dataclasses import dataclass

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from bot.database.methods import check_role_cached
from bot.config import EnvKeys


@dataclass
class HasPermissionFilter(BaseFilter):
    """
    Filter for the presence of a certain permission for the user (bit mask).
    """
    permission: int

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        # check_role_cached(user_id) returns int (bitmask of rights) or None
        user_permissions: int = await check_role_cached(user_id) or 0
        return (user_permissions & self.permission) == self.permission
