from .main import router as main_router
from .shop_and_goods import router as shop_and_goods_router
from .referral_system import router as referral_system_router
from .reference_code_handler import router as reference_code_router
from .help_handler import router as help_router
from .cart_handler import router as cart_router
from .order_handler import router as order_router
from .orders_view_handler import router as orders_view_router

from aiogram import Router

router = Router()
router.include_router(main_router)
router.include_router(reference_code_router)
router.include_router(help_router)
router.include_router(cart_router)
router.include_router(order_router)
router.include_router(orders_view_router)
router.include_router(shop_and_goods_router)
router.include_router(referral_system_router)