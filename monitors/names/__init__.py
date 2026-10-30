"""DNS names for the apps on your tailnet."""

from monitors.names.service import NamesConfig, NamesService, UserError, build_names_service

__all__ = ["NamesConfig", "NamesService", "UserError", "build_names_service"]
