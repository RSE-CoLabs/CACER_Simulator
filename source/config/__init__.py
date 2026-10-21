# Architecture: Expose the configuration-stage entry point.

"""Configuration domain."""

from source.config.config_pipeline import run_config_pipeline

__all__ = ["run_config_pipeline"]
