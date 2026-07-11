"""Configuration loading, validation, and the immutable ``ApplicationConfig`` model.

Planned for Milestone 2. The subsystem loads the INI file with :mod:`configparser`,
rejects unknown sections/options, converts values to typed fields, validates numeric
ranges and cross-field constraints, and returns a frozen ``ApplicationConfig`` built
from ``OptionSpec``-driven section schemas. All configuration issues are collected and
reported together via a ``ConfigurationValidationError``.

See ``docs/CONFIG-REFERENCE.md`` for the option catalogue and ``docs/ROADMAP.md`` (M2).
"""

from __future__ import annotations
