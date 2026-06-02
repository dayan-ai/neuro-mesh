"""Custom Trie-based route matching engine for the NEURO-MESH API Gateway.

This module implements a prefix tree (Trie) data structure from scratch
for efficient URL path resolution with support for dynamic parameters.

Implementation:
- TrieNode class with children dict, dynamic_child, and destination
- Trie class with insert() and resolve() methods
- Static segment priority over dynamic segments at each level
- Path normalization (trailing slash equivalence)
- Maximum depth enforcement (20 segments)
- Duplicate pattern overwrite behavior
"""

from __future__ import annotations


class TrieNode:
    """Internal node in the Trie data structure.

    Attributes:
        children: Mapping of static segment strings to child TrieNode instances.
        dynamic_child: Optional single dynamic parameter child node.
        dynamic_param_name: Name of the dynamic parameter (e.g., "id") if this
            node has a dynamic child.
        destination: Route destination identifier, set only on terminal nodes.
    """

    def __init__(self) -> None:
        self.children: dict[str, TrieNode] = {}
        self.dynamic_child: TrieNode | None = None
        self.dynamic_param_name: str | None = None
        self.destination: str | None = None


class Trie:
    """Custom prefix tree for URL path resolution.

    Supports insertion of route patterns containing static segments and
    dynamic parameters enclosed in curly braces (e.g., ``{id}``). Resolution
    prioritizes static segment matches over dynamic at each level.

    Attributes:
        MAX_DEPTH: Maximum allowed path depth in segments. Paths exceeding
            this limit return None on resolution.
    """

    MAX_DEPTH: int = 20

    def __init__(self) -> None:
        self._root: TrieNode = TrieNode()

    @staticmethod
    def _normalize(path: str) -> str:
        """Strip leading and trailing slashes for consistent resolution.

        Args:
            path: The raw URL path string.

        Returns:
            The path with leading/trailing slashes removed.
        """
        return path.strip("/")

    def insert(self, pattern: str, destination: str) -> None:
        """Insert a route pattern with its destination.

        Dynamic segments are identified by curly braces (e.g., ``{id}``).
        If the pattern already exists, the destination is overwritten.

        Args:
            pattern: URL pattern such as ``/api/v1/users/{id}``.
            destination: Destination identifier (e.g., ``"user-service"``).
        """
        normalized = self._normalize(pattern)
        segments = normalized.split("/") if normalized else []

        node = self._root
        for segment in segments:
            if segment.startswith("{") and segment.endswith("}"):
                # Dynamic segment
                param_name = segment[1:-1]
                if node.dynamic_child is None:
                    node.dynamic_child = TrieNode()
                node.dynamic_param_name = param_name
                node = node.dynamic_child
            else:
                # Static segment
                if segment not in node.children:
                    node.children[segment] = TrieNode()
                node = node.children[segment]

        node.destination = destination

    def resolve(self, path: str) -> tuple[str, dict[str, str]] | None:
        """Resolve a request path against registered route patterns.

        Normalizes the path (strips leading/trailing slashes), enforces the
        MAX_DEPTH limit, and walks the tree prioritizing static matches over
        dynamic at each level.

        Args:
            path: The incoming request path to resolve.

        Returns:
            A tuple of ``(destination, params)`` where params is a dict of
            extracted dynamic parameter values, or ``None`` if no route matches.
        """
        normalized = self._normalize(path)
        if not normalized:
            # Root path resolution
            if self._root.destination is not None:
                return (self._root.destination, {})
            return None

        segments = normalized.split("/")

        # Enforce MAX_DEPTH
        if len(segments) > self.MAX_DEPTH:
            return None

        return self._walk(self._root, segments, 0, {})

    def _walk(
        self,
        node: TrieNode,
        segments: list[str],
        index: int,
        params: dict[str, str],
    ) -> tuple[str, dict[str, str]] | None:
        """Recursively walk the trie, prioritizing static over dynamic matches.

        Args:
            node: Current trie node.
            segments: List of path segments to match.
            index: Current segment index.
            params: Accumulated dynamic parameter values.

        Returns:
            A tuple of ``(destination, params)`` or ``None``.
        """
        if index == len(segments):
            if node.destination is not None:
                return (node.destination, params)
            return None

        segment = segments[index]

        # Priority 1: Static match
        if segment in node.children:
            result = self._walk(node.children[segment], segments, index + 1, params)
            if result is not None:
                return result

        # Priority 2: Dynamic match (any non-empty segment)
        if node.dynamic_child is not None and segment:
            new_params = {**params}
            if node.dynamic_param_name is not None:
                new_params[node.dynamic_param_name] = segment
            result = self._walk(node.dynamic_child, segments, index + 1, new_params)
            if result is not None:
                return result

        return None
