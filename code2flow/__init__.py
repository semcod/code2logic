# Backward-compat alias: the package was renamed from code2flow → code2logic
from code2logic import *  # noqa: F401,F403
from code2logic import __all__ as _all  # noqa: F401

# Re-export submodules that tests may reference
from code2logic import core  # noqa: F401
from code2flow.core.config import FAST_CONFIG, FilterConfig  # noqa: F401
from code2flow.nlp import NLPPipeline, FAST_NLP_CONFIG, EntityResolver  # noqa: F401

# Backward-compat wrapper that accepts old Config-first API
from code2flow._compat import ProjectAnalyzer  # noqa: F401  # shadows code2logic's
