"""Input validation utilities for the NEURO-MESH API Gateway.

This module provides path validation logic that runs before any
business logic to fail fast on malformed input.

Validation checks:
- Empty/whitespace path detection
- Invalid character detection using regex (RFC 3986 unreserved + / + %XX)

Returns error message string if invalid, None if valid.
"""

import re

VALID_PATH_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9\-._~/%]+$")


def validate_path(path: str) -> str | None:
    """Validate a request path for correctness before route resolution.

    Checks that the path is non-empty and contains only valid characters
    per RFC 3986 (unreserved characters, forward slashes, and percent-encoded
    sequences).

    Args:
        path: The request path string to validate.

    Returns:
        None if the path is valid.
        A descriptive error message string if the path is invalid.
    """
    # Check for empty or whitespace-only paths
    if not path.strip():
        return "Request path must not be empty"

    # Check for invalid characters
    if not VALID_PATH_PATTERN.match(path):
        # Find all invalid characters
        invalid_chars: set[str] = set()
        for char in path:
            if not re.match(r"[A-Za-z0-9\-._~/%]", char):
                invalid_chars.add(char)
        return f"Invalid characters in path: {''.join(sorted(invalid_chars))}"

    return None
