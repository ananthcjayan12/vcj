"""Direct-HTML lesson composition pipeline.

The package deliberately owns only the visual stages of a run. Narration,
audio, and timing remain in the existing MAV pipeline.
"""

from .constants import ANIMATION_MODES, DIRECT_HTML_MODE, LEGACY_MODE

__all__ = ["ANIMATION_MODES", "DIRECT_HTML_MODE", "LEGACY_MODE"]
