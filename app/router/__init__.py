"""4.3.2 智能路由调度器."""
from app.router.department_router import DepartmentRouter
from app.router.fallback import apply_fallback

__all__ = ["DepartmentRouter", "apply_fallback"]
