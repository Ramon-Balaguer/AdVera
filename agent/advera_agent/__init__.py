"""AdVera desktop Capture Agent (ADR 0010)."""

from importlib.metadata import PackageNotFoundError, version

try:
    # The release workflow stamps the real version into the package when it builds the wheel.
    __version__ = version("advera-agent")
except PackageNotFoundError:
    __version__ = "0.0.0"
