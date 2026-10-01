"""HTTP 路由层（只做形状；业务真值在 app/repository.py）。"""

from . import jobs  # noqa: F401

__all__ = ["jobs"]
