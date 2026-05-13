# Backward-compat shim: code2flow.core → code2logic.core
from code2logic.core import *  # noqa: F401,F403
from code2logic.core import __all__  # noqa: F401
from .config import FAST_CONFIG, FilterConfig  # noqa: F401
from .analyzer import FileCache, FastFileFilter  # noqa: F401
