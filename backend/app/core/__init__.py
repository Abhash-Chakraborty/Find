"""Core utilities and compatibility helpers for the backend."""

from .compat import apply_monkey_patches


# Run compatibility shims as soon as the package is imported so any downstream
# modules benefit from the patched behaviour.
apply_monkey_patches()