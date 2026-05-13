"""
Error handling for Code2Logic.

Provides robust error handling for file/folder analysis with graceful degradation.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class ErrorSeverity(Enum):
    """Error severity levels."""

    WARNING = "warning"  # Non-fatal, continue processing
    ERROR = "error"  # File skipped, continue with others
    CRITICAL = "critical"  # Stop processing


class ErrorType(Enum):
    """Types of errors that can occur during analysis."""

    # Filesystem errors
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_DENIED = "permission_denied"
    FILE_TOO_LARGE = "file_too_large"
    ENCODING_ERROR = "encoding_error"
    SYMLINK_LOOP = "symlink_loop"
    DISK_FULL = "disk_full"
    PATH_TOO_LONG = "path_too_long"

    # Parsing errors
    SYNTAX_ERROR = "syntax_error"
    PARSE_TIMEOUT = "parse_timeout"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    BINARY_FILE = "binary_file"
    EMPTY_FILE = "empty_file"

    # Generation errors
    YAML_SERIALIZATION = "yaml_serialization"
    JSON_SERIALIZATION = "json_serialization"
    OUTPUT_WRITE_ERROR = "output_write_error"

    # System errors
    MEMORY_ERROR = "memory_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class AnalysisError:
    """Represents an error during analysis."""

    type: ErrorType
    severity: ErrorSeverity
    path: str
    message: str
    exception: Optional[str] = None
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "path": self.path,
            "message": self.message,
            "exception": self.exception,
            "suggestion": self.suggestion,
        }


@dataclass
class AnalysisResult:
    """Result of analysis with errors tracked."""

    success: bool = True
    errors: List[AnalysisError] = field(default_factory=list)
    warnings: List[AnalysisError] = field(default_factory=list)
    skipped_files: List[str] = field(default_factory=list)
    processed_files: int = 0
    total_files: int = 0

    def add_error(self, error: AnalysisError):
        """Add an error to the result."""
        if error.severity == ErrorSeverity.WARNING:
            self.warnings.append(error)
        else:
            self.errors.append(error)
            if error.severity == ErrorSeverity.CRITICAL:
                self.success = False

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def summary(self) -> str:
        """Generate error summary."""
        lines = [
            f"Processed: {self.processed_files}/{self.total_files} files",
            f"Errors: {len(self.errors)}, Warnings: {len(self.warnings)}",
        ]
        if self.skipped_files:
            lines.append(f"Skipped: {len(self.skipped_files)} files")
        return "\n".join(lines)


class ErrorHandler:
    """
    Handles errors during analysis with configurable behavior.

    Modes:
    - strict: Stop on first error
    - lenient: Log errors and continue (default)
    - silent: Continue without logging
    """

    # Error suggestions
    SUGGESTIONS = {
        ErrorType.FILE_NOT_FOUND: "Check if file exists and path is correct",
        ErrorType.PERMISSION_DENIED: "Check file permissions or run with elevated privileges",
        ErrorType.FILE_TOO_LARGE: "File exceeds size limit. Consider splitting or excluding",
        ErrorType.ENCODING_ERROR: "Try specifying encoding or use binary mode",
        ErrorType.SYMLINK_LOOP: "Detected circular symlink. Exclude this path",
        ErrorType.DISK_FULL: "Free up disk space or use different output location",
        ErrorType.PATH_TOO_LONG: "Shorten file path or move project to shorter path",
        ErrorType.SYNTAX_ERROR: "Fix syntax errors in source file or skip",
        ErrorType.PARSE_TIMEOUT: "File too complex. Consider simplifying or excluding",
        ErrorType.UNSUPPORTED_LANGUAGE: "Language not supported. Will be skipped",
        ErrorType.BINARY_FILE: "Binary files cannot be analyzed. Skipping",
        ErrorType.EMPTY_FILE: "Empty file, nothing to analyze",
        ErrorType.YAML_SERIALIZATION: "Data contains unsupported types for YAML",
        ErrorType.JSON_SERIALIZATION: "Data contains unsupported types for JSON",
        ErrorType.OUTPUT_WRITE_ERROR: "Cannot write output file. Check permissions",
        ErrorType.MEMORY_ERROR: "Out of memory. Process smaller chunks",
        ErrorType.TIMEOUT: "Operation timed out. Try smaller scope",
        ErrorType.UNKNOWN: "Unknown error occurred",
    }

    def __init__(
        self,
        mode: str = "lenient",
        max_file_size_mb: float = 10.0,
        timeout_seconds: float = 30.0,
        logger: Optional[logging.Logger] = None,
    ):
        self.mode = mode
        self.max_file_size = int(max_file_size_mb * 1024 * 1024)
        self.timeout = timeout_seconds
        self.logger = logger or logging.getLogger(__name__)
        self.result = AnalysisResult()

    def reset(self):
        """Reset error state for new analysis."""
        self.result = AnalysisResult()

    def handle_error(
        self,
        error_type: ErrorType,
        path: str,
        message: str,
        exception: Optional[Exception] = None,
        severity: Optional[ErrorSeverity] = None,
    ) -> bool:
        """
        Handle an error.

        Returns:
            True if processing should continue, False to stop
        """
        if severity is None:
            severity = self._default_severity(error_type)

        error = AnalysisError(
            type=error_type,
            severity=severity,
            path=path,
            message=message,
            exception=str(exception) if exception else None,
            suggestion=self.SUGGESTIONS.get(error_type, ""),
        )

        self.result.add_error(error)

        if self.mode != "silent":
            self._log_error(error)

        if self.mode == "strict" and severity != ErrorSeverity.WARNING:
            return False

        return severity != ErrorSeverity.CRITICAL

    def _default_severity(self, error_type: ErrorType) -> ErrorSeverity:
        """Get default severity for error type."""
        critical_types = {
            ErrorType.DISK_FULL,
            ErrorType.MEMORY_ERROR,
        }
        warning_types = {
            ErrorType.EMPTY_FILE,
            ErrorType.UNSUPPORTED_LANGUAGE,
            ErrorType.BINARY_FILE,
        }

        if error_type in critical_types:
            return ErrorSeverity.CRITICAL
        if error_type in warning_types:
            return ErrorSeverity.WARNING
        return ErrorSeverity.ERROR

    def _log_error(self, error: AnalysisError):
        """Log an error."""
        msg = f"[{error.severity.value}] {error.type.value}: {error.path} - {error.message}"
        if error.severity == ErrorSeverity.WARNING:
            self.logger.warning(msg)
        elif error.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(msg)
        else:
            self.logger.error(msg)

    def safe_read_file(self, path: Path) -> Optional[str]:
        """
        Safely read a file with error handling.

        Returns:
            File content or None if error
        """
        try:
            # Check file size
            if path.stat().st_size > self.max_file_size:
                self.handle_error(
                    ErrorType.FILE_TOO_LARGE,
                    str(path),
                    f"File size {path.stat().st_size} exceeds limit {self.max_file_size}",
                )
                return None

            # Check if binary
            try:
                with open(path, "rb") as f:
                    chunk = f.read(8192)
                    if b"\x00" in chunk:
                        self.handle_error(
                            ErrorType.BINARY_FILE,
                            str(path),
                            "File appears to be binary",
                            severity=ErrorSeverity.WARNING,
                        )
                        return None
            except Exception:
                pass

            # Try reading with different encodings
            encodings = ["utf-8", "latin-1", "cp1252", "utf-16"]
            for encoding in encodings:
                try:
                    content = path.read_text(encoding=encoding, errors="strict")
                    return content
                except UnicodeDecodeError:
                    continue

            # Last resort: ignore errors
            try:
                return path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                self.handle_error(
                    ErrorType.ENCODING_ERROR,
                    str(path),
                    f"Cannot decode file: {e}",
                    exception=e,
                )
                return None

        except FileNotFoundError as e:
            self.handle_error(
                ErrorType.FILE_NOT_FOUND,
                str(path),
                "File not found",
                exception=e,
            )
            return None

        except PermissionError as e:
            self.handle_error(
                ErrorType.PERMISSION_DENIED,
                str(path),
                "Permission denied",
                exception=e,
            )
            return None

        except OSError as e:
            if "name too long" in str(e).lower():
                self.handle_error(
                    ErrorType.PATH_TOO_LONG,
                    str(path),
                    "Path too long",
                    exception=e,
                )
            elif "no space" in str(e).lower():
                self.handle_error(
                    ErrorType.DISK_FULL,
                    str(path),
                    "Disk full",
                    exception=e,
                )
            else:
                self.handle_error(
                    ErrorType.UNKNOWN,
                    str(path),
                    str(e),
                    exception=e,
                )
            return None

        except MemoryError as e:
            self.handle_error(
                ErrorType.MEMORY_ERROR,
                str(path),
                "Out of memory reading file",
                exception=e,
            )
            return None

        except Exception as e:
            self.handle_error(
                ErrorType.UNKNOWN,
                str(path),
                str(e),
                exception=e,
            )
            return None

    def safe_write_file(self, path: Path, content: str) -> bool:
        """
        Safely write a file with error handling.

        Returns:
            True if successful, False otherwise
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return True

        except PermissionError as e:
            self.handle_error(
                ErrorType.PERMISSION_DENIED,
                str(path),
                "Cannot write file: permission denied",
                exception=e,
            )
            return False

        except OSError as e:
            if "no space" in str(e).lower():
                self.handle_error(
                    ErrorType.DISK_FULL,
                    str(path),
                    "Cannot write file: disk full",
                    exception=e,
                )
            else:
                self.handle_error(
                    ErrorType.OUTPUT_WRITE_ERROR,
                    str(path),
                    f"Cannot write file: {e}",
                    exception=e,
                )
            return False

        except Exception as e:
            self.handle_error(
                ErrorType.OUTPUT_WRITE_ERROR,
                str(path),
                str(e),
                exception=e,
            )
            return False

    def safe_parse(
        self, path: str, content: str, parser_func: Callable, *args, **kwargs
    ) -> Any:
        """
        Safely parse content with error handling.

        Returns:
            Parse result or None if error
        """
        try:
            return parser_func(path, content, *args, **kwargs)

        except SyntaxError as e:
            self.handle_error(
                ErrorType.SYNTAX_ERROR,
                path,
                f"Syntax error: {e}",
                exception=e,
            )
            return None

        except RecursionError as e:
            self.handle_error(
                ErrorType.PARSE_TIMEOUT,
                path,
                "Recursion limit exceeded during parsing",
                exception=e,
            )
            return None

        except MemoryError as e:
            self.handle_error(
                ErrorType.MEMORY_ERROR,
                path,
                "Out of memory during parsing",
                exception=e,
            )
            return None

        except Exception as e:
            self.handle_error(
                ErrorType.UNKNOWN,
                path,
                f"Parse error: {e}",
                exception=e,
            )
            return None


def create_error_handler(
    mode: str = "lenient",
    max_file_size_mb: float = 10.0,
) -> ErrorHandler:
    """Create an error handler with default settings."""
    return ErrorHandler(mode=mode, max_file_size_mb=max_file_size_mb)
