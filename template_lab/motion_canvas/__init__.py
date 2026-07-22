"""Narration-authoritative Motion Canvas scene production."""

from . import pipeline as _pipeline
from .generation_contract import install as _install_generation_contract
from .lesson_review_integration import install as _install_lesson_review

_install_generation_contract(_pipeline)
_install_lesson_review(_pipeline)

prepare = _pipeline.prepare
generate = _pipeline.generate
validate_and_assemble = _pipeline.validate_and_assemble

__all__ = ["prepare", "generate", "validate_and_assemble"]
