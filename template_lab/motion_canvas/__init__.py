"""Narration-authoritative Motion Canvas scene production."""

from . import pipeline as _pipeline
from .generation_contract import install as _install_generation_contract

_install_generation_contract(_pipeline)

prepare = _pipeline.prepare
generate = _pipeline.generate
validate_and_assemble = _pipeline.validate_and_assemble

__all__ = ["prepare", "generate", "validate_and_assemble"]
