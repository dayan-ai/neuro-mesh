"""Unit tests for the custom Trie-based route matching engine.

Tests cover:
- Route insertion and resolution
- Static segment matching
- Dynamic parameter extraction
- Trailing slash normalization
- Depth limit enforcement
- Duplicate pattern overwrite
- Non-matching path handling
"""

import pytest

from app.trie import Trie, TrieNode


class TestTrieNode:
    """Tests for the TrieNode class initialization."""

    def test_default_attributes(self) -> None:
        node = TrieNode()
        assert node.children == {}
        assert node.dynamic_child is None
        assert node.dynamic_param_name is None
        assert node.destination is None


class TestTrieNormalize:
    """Tests for the Trie._normalize static method."""

    def test_strips_leading_slash(self) -> None:
        assert Trie._normalize("/api/v1") == "api/v1"

    def test_strips_trailing_slash(self) -> None:
        assert Trie._normalize("api/v1/") == "api/v1"

    def test_strips_both_slashes(self) -> None:
        assert Trie._normalize("/api/v1/") == "api/v1"

    def test_no_slashes_unchanged(self) -> None:
        assert Trie._normalize("api/v1") == "api/v1"

    def test_empty_string(self) -> None:
        assert Trie._normalize("") == ""

    def test_single_slash(self) -> None:
        assert Trie._normalize("/") == ""


class TestTrieInsertAndResolve:
    """Tests for basic static route insertion and resolution."""

    def test_single_static_segment(self) -> None:
        trie = Trie()
        trie.insert("/users", "user-service")
        result = trie.resolve("/users")
        assert result == ("user-service", {})

    def test_multi_segment_static_route(self) -> None:
        trie = Trie()
        trie.insert("/api/v1/users", "user-service")
        result = trie.resolve("/api/v1/users")
        assert result == ("user-service", {})

    def test_multiple_routes(self) -> None:
        trie = Trie()
        trie.insert("/api/v1/users", "user-service")
        trie.insert("/api/v1/orders", "order-service")
        assert trie.resolve("/api/v1/users") == ("user-service", {})
        assert trie.resolve("/api/v1/orders") == ("order-service", {})

    def test_root_path(self) -> None:
        trie = Trie()
        trie.insert("/", "root-service")
        assert trie.resolve("/") == ("root-service", {})

    def test_root_path_empty_string(self) -> None:
        trie = Trie()
        trie.insert("/", "root-service")
        assert trie.resolve("") == ("root-service", {})


class TestTrieDynamicParams:
    """Tests for dynamic parameter extraction."""

    def test_single_dynamic_param(self) -> None:
        trie = Trie()
        trie.insert("/users/{id}", "user-service")
        result = trie.resolve("/users/42")
        assert result == ("user-service", {"id": "42"})

    def test_multiple_dynamic_params(self) -> None:
        trie = Trie()
        trie.insert("/users/{user_id}/posts/{post_id}", "post-service")
        result = trie.resolve("/users/alice/posts/99")
        assert result == ("post-service", {"user_id": "alice", "post_id": "99"})

    def test_dynamic_with_static_prefix(self) -> None:
        trie = Trie()
        trie.insert("/api/v1/users/{id}", "user-service")
        result = trie.resolve("/api/v1/users/hello-world")
        assert result == ("user-service", {"id": "hello-world"})

    def test_dynamic_param_matches_any_nonempty_value(self) -> None:
        trie = Trie()
        trie.insert("/{name}", "generic")
        assert trie.resolve("/foo") == ("generic", {"name": "foo"})
        assert trie.resolve("/123") == ("generic", {"name": "123"})
        assert trie.resolve("/a-b_c.d~e") == ("generic", {"name": "a-b_c.d~e"})


class TestTrieStaticOverDynamicPriority:
    """Tests for static segment priority over dynamic matches."""

    def test_static_preferred_over_dynamic(self) -> None:
        trie = Trie()
        trie.insert("/users/admin", "admin-service")
        trie.insert("/users/{id}", "user-service")
        result = trie.resolve("/users/admin")
        assert result == ("admin-service", {})

    def test_dynamic_used_when_static_not_matching(self) -> None:
        trie = Trie()
        trie.insert("/users/admin", "admin-service")
        trie.insert("/users/{id}", "user-service")
        result = trie.resolve("/users/bob")
        assert result == ("user-service", {"id": "bob"})

    def test_static_priority_deep_tree(self) -> None:
        trie = Trie()
        trie.insert("/api/v1/items/special", "special-service")
        trie.insert("/api/v1/items/{id}", "item-service")
        assert trie.resolve("/api/v1/items/special") == ("special-service", {})
        assert trie.resolve("/api/v1/items/123") == ("item-service", {"id": "123"})


class TestTrieTrailingSlashNormalization:
    """Tests for trailing slash equivalence."""

    def test_resolve_with_trailing_slash(self) -> None:
        trie = Trie()
        trie.insert("/api/v1/users", "user-service")
        assert trie.resolve("/api/v1/users/") == ("user-service", {})

    def test_resolve_without_trailing_slash(self) -> None:
        trie = Trie()
        trie.insert("/api/v1/users/", "user-service")
        assert trie.resolve("/api/v1/users") == ("user-service", {})

    def test_insert_with_trailing_resolve_without(self) -> None:
        trie = Trie()
        trie.insert("/items/", "item-service")
        assert trie.resolve("/items") == ("item-service", {})

    def test_dynamic_trailing_slash(self) -> None:
        trie = Trie()
        trie.insert("/users/{id}", "user-service")
        assert trie.resolve("/users/42/") == ("user-service", {"id": "42"})


class TestTrieDuplicateOverwrite:
    """Tests for duplicate pattern overwrite behavior."""

    def test_overwrite_destination(self) -> None:
        trie = Trie()
        trie.insert("/api/v1/users", "old-service")
        trie.insert("/api/v1/users", "new-service")
        result = trie.resolve("/api/v1/users")
        assert result == ("new-service", {})

    def test_overwrite_dynamic_route(self) -> None:
        trie = Trie()
        trie.insert("/users/{id}", "old-service")
        trie.insert("/users/{id}", "new-service")
        result = trie.resolve("/users/42")
        assert result == ("new-service", {"id": "42"})


class TestTrieDepthLimit:
    """Tests for the MAX_DEPTH=20 segment limit."""

    def test_exactly_20_segments_succeeds(self) -> None:
        trie = Trie()
        segments = "/".join(["seg"] * 20)
        pattern = f"/{segments}"
        trie.insert(pattern, "deep-service")
        result = trie.resolve(pattern)
        assert result == ("deep-service", {})

    def test_21_segments_returns_none(self) -> None:
        trie = Trie()
        segments = "/".join(["seg"] * 21)
        path = f"/{segments}"
        # Even if a route were registered, resolve should reject >20 segments
        assert trie.resolve(path) is None

    def test_many_segments_returns_none(self) -> None:
        trie = Trie()
        segments = "/".join(["a"] * 50)
        path = f"/{segments}"
        assert trie.resolve(path) is None


class TestTrieNonMatchingPaths:
    """Tests for paths that don't match any registered route."""

    def test_unregistered_path_returns_none(self) -> None:
        trie = Trie()
        trie.insert("/api/v1/users", "user-service")
        assert trie.resolve("/api/v1/orders") is None

    def test_partial_match_returns_none(self) -> None:
        trie = Trie()
        trie.insert("/api/v1/users", "user-service")
        assert trie.resolve("/api/v1") is None

    def test_longer_path_returns_none(self) -> None:
        trie = Trie()
        trie.insert("/api/v1/users", "user-service")
        assert trie.resolve("/api/v1/users/extra/segments") is None

    def test_empty_trie_returns_none(self) -> None:
        trie = Trie()
        assert trie.resolve("/anything") is None

    def test_case_sensitive_mismatch(self) -> None:
        trie = Trie()
        trie.insert("/Users", "user-service")
        assert trie.resolve("/users") is None
