"""Unit tests for app/codes.py.

Pure logic tests: no database, no HTTP, no external dependencies.
Exhaustively tests encode, decode, validate_custom, normalise_url, and is_safe.
Over 70+ test cases covering alphabet rules, reserved words, length limits,
URL normalisation, default ports, and SSRF security checks.
"""
import pytest

from app.codes import (
    ALPHABET,
    RESERVED,
    LinkError,
    decode,
    encode,
    is_safe,
    normalise_url,
    validate_custom,
)


class TestEncode:
    """Test integer to short-code encoding."""

    def test_encode_zero(self):
        assert encode(0) == ALPHABET[0]

    def test_encode_one(self):
        assert encode(1) == ALPHABET[1]

    def test_encode_base_minus_one(self):
        base = len(ALPHABET)
        assert encode(base - 1) == ALPHABET[base - 1]

    def test_encode_base(self):
        base = len(ALPHABET)
        expected = ALPHABET[1] + ALPHABET[0]
        assert encode(base) == expected

    def test_encode_arbitrary_integers(self):
        assert isinstance(encode(42), str)
        assert isinstance(encode(100), str)
        assert isinstance(encode(999999), str)
        assert isinstance(encode(123456789), str)

    def test_encode_negative_raises_link_error(self):
        with pytest.raises(LinkError, match="cannot encode a negative number"):
            encode(-1)

    def test_encode_large_negative_raises_link_error(self):
        with pytest.raises(LinkError, match="cannot encode a negative number"):
            encode(-1000)

    @pytest.mark.parametrize("n", [0, 1, 2, 10, 55, 56, 100, 500, 31337, 1000000, 987654321])
    def test_encode_decode_roundtrip(self, n):
        assert decode(encode(n)) == n

    def test_encode_only_uses_alphabet_characters(self):
        alphabet_set = set(ALPHABET)
        for n in [0, 5, 55, 56, 1234, 99999]:
            code = encode(n)
            assert all(ch in alphabet_set for ch in code)


class TestDecode:
    """Test short-code to integer decoding."""

    def test_decode_single_chars(self):
        for idx, ch in enumerate(ALPHABET):
            assert decode(ch) == idx

    def test_decode_empty_string(self):
        assert decode("") == 0

    @pytest.mark.parametrize("excluded", ["0", "O", "1", "l", "I", "o"])
    def test_decode_deliberately_excluded_characters_raise_error(self, excluded):
        with pytest.raises(LinkError, match=f"{excluded!r} is not in the alphabet"):
            decode(f"abc{excluded}xyz")

    @pytest.mark.parametrize("invalid_char", ["!", "@", "#", "$", "%", "-", "_", " ", "\t", "+"])
    def test_decode_invalid_special_chars_raise_error(self, invalid_char):
        with pytest.raises(LinkError, match="is not in the alphabet"):
            decode(f"cde{invalid_char}")

    def test_decode_unicode_char_raises_error(self):
        with pytest.raises(LinkError, match="is not in the alphabet"):
            decode("code🚀")


class TestValidateCustom:
    """Test custom short-code validation rules."""

    @pytest.mark.parametrize("valid_code", ["abc", "234", "xyz", "MyKey", "k9Z", "a" * 32, "m8K"])
    def test_valid_custom_codes_accepted(self, valid_code):
        assert validate_custom(valid_code) == valid_code

    def test_validate_custom_strips_whitespace(self):
        assert validate_custom("  mykey  ") == "mykey"

    @pytest.mark.parametrize("short_code", ["", "a", "ab", "  a  ", "  23  "])
    def test_code_too_short_raises_error(self, short_code):
        with pytest.raises(LinkError, match="a code must be 3-32 characters from the allowed alphabet"):
            validate_custom(short_code)

    def test_code_too_long_raises_error(self):
        long_code = "a" * 33
        with pytest.raises(LinkError, match="a code must be 3-32 characters from the allowed alphabet"):
            validate_custom(long_code)

    @pytest.mark.parametrize("excluded_char", ["0", "O", "1", "l", "I", "o"])
    def test_custom_code_with_excluded_chars_raises_error(self, excluded_char):
        with pytest.raises(LinkError, match="a code must be 3-32 characters from the allowed alphabet"):
            validate_custom(f"abc{excluded_char}xyz")

    @pytest.mark.parametrize("special_char", ["-", "_", ".", "/", "?", "@", " "])
    def test_custom_code_with_special_chars_raises_error(self, special_char):
        with pytest.raises(LinkError, match="a code must be 3-32 characters from the allowed alphabet"):
            validate_custom(f"abc{special_char}xyz")

    @pytest.mark.parametrize("reserved", ["api", "admin", "static"])
    def test_exact_reserved_words_raise_error(self, reserved):
        with pytest.raises(LinkError, match="is reserved"):
            validate_custom(reserved)

    def test_reserved_word_with_whitespace_raises_error(self):
        with pytest.raises(LinkError, match="is reserved"):
            validate_custom("  api  ")
        with pytest.raises(LinkError, match="is reserved"):
            validate_custom("  admin  ")

    @pytest.mark.parametrize("reserved", list(RESERVED))
    def test_all_reserved_words_are_rejected(self, reserved):
        # Reserved words either fail alphabet regex or raise 'is reserved'
        with pytest.raises(LinkError):
            validate_custom(reserved)

    def test_custom_code_containing_reserved_substring_is_allowed(self):
        # Strings that contain reserved substrings but are not reserved words themselves
        assert validate_custom("apixyz") == "apixyz"
        assert validate_custom("myadmin") == "myadmin"
        assert validate_custom("statics") == "statics"

    def test_validate_custom_non_string_input(self):
        # Integer whose string representation is in ALPHABET and len >= 3
        assert validate_custom(234) == "234"


class TestNormaliseUrl:
    """Test URL normalisation and canonicalisation rules."""

    def test_none_url_raises_error(self):
        with pytest.raises(LinkError, match="url is required"):
            normalise_url(None)

    def test_empty_url_raises_error(self):
        with pytest.raises(LinkError, match="url cannot be empty"):
            normalise_url("")

    def test_whitespace_only_url_raises_error(self):
        with pytest.raises(LinkError, match="url cannot be empty"):
            normalise_url("   \t  \n ")

    def test_adds_https_when_scheme_missing(self):
        assert normalise_url("example.com") == "https://example.com/"
        assert normalise_url("example.com/path") == "https://example.com/path"

    def test_preserves_existing_http_scheme(self):
        assert normalise_url("http://example.com") == "http://example.com/"

    def test_preserves_existing_https_scheme(self):
        assert normalise_url("https://example.com") == "https://example.com/"

    @pytest.mark.parametrize("bad_scheme", [
        "ftp://example.com/file",
        "file://example.com/etc/passwd",
        "ws://example.com/socket",
        "wss://example.com/secure",
        "ssh://example.com/repo",
        "git://example.com/repo",
        "gopher://example.com/",
    ])
    def test_disallowed_schemes_raise_error(self, bad_scheme):
        with pytest.raises(LinkError, match="only http and https URLs are allowed"):
            normalise_url(bad_scheme)

    def test_missing_host_raises_error(self):
        with pytest.raises(LinkError, match="that URL has no host"):
            normalise_url("https://")
        with pytest.raises(LinkError, match="that URL has no host"):
            normalise_url("https:///only/a/path")

    def test_lowercases_host(self):
        assert normalise_url("https://EXAMPLE.COM/Path") == "https://example.com/Path"
        assert normalise_url("http://ExAmPlE.CoM/Path") == "http://example.com/Path"

    def test_removes_trailing_dot_from_host(self):
        assert normalise_url("https://example.com./path") == "https://example.com/path"

    def test_removes_default_http_port_80(self):
        assert normalise_url("http://example.com:80/path") == "http://example.com/path"

    def test_removes_default_https_port_443(self):
        assert normalise_url("https://example.com:443/path") == "https://example.com/path"

    def test_preserves_non_default_http_port(self):
        assert normalise_url("http://example.com:8080/path") == "http://example.com:8080/path"

    def test_preserves_non_default_https_port(self):
        assert normalise_url("https://example.com:8443/path") == "https://example.com:8443/path"

    def test_preserves_port_443_on_http_scheme(self):
        assert normalise_url("http://example.com:443/path") == "http://example.com:443/path"

    def test_preserves_port_80_on_https_scheme(self):
        assert normalise_url("https://example.com:80/path") == "https://example.com:80/path"

    def test_empty_path_becomes_slash(self):
        assert normalise_url("https://example.com") == "https://example.com/"

    def test_preserves_path(self):
        assert normalise_url("https://example.com/deep/nested/page") == "https://example.com/deep/nested/page"

    def test_preserves_query_string(self):
        assert (
            normalise_url("https://example.com/search?q=fastapi&sort=desc")
            == "https://example.com/search?q=fastapi&sort=desc"
        )

    def test_strips_fragment(self):
        assert normalise_url("https://example.com/page#heading-1") == "https://example.com/page"

    def test_strips_surrounding_whitespace(self):
        assert normalise_url("   https://example.com/path   ") == "https://example.com/path"


class TestIsSafe:
    """Test SSRF protection and internal network blocking."""

    @pytest.mark.parametrize("blocked_host", [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "metadata.google.internal",
    ])
    def test_blocked_special_hostnames(self, blocked_host):
        assert is_safe(f"http://{blocked_host}/") is False
        assert is_safe(f"https://{blocked_host}:8080/secret") is False

    def test_blocked_ipv6_loopback(self):
        # RFC 3986 specifies IPv6 host literals are bracketed: http://[::1]/
        assert is_safe("http://[::1]/") is False

    @pytest.mark.parametrize("ip_10", ["10.0.0.1", "10.1.2.3", "10.255.255.255"])
    def test_blocks_10_dot_private_network(self, ip_10):
        assert is_safe(f"http://{ip_10}/") is False

    @pytest.mark.parametrize("ip_192", ["192.168.0.1", "192.168.1.100", "192.168.254.254"])
    def test_blocks_192_168_private_network(self, ip_192):
        assert is_safe(f"http://{ip_192}/") is False

    @pytest.mark.parametrize("ip_169", ["169.254.169.254", "169.254.0.1"])
    def test_blocks_169_254_link_local_and_cloud_metadata(self, ip_169):
        assert is_safe(f"http://{ip_169}/") is False

    @pytest.mark.parametrize("safe_url", [
        "https://example.com",
        "https://google.com/search",
        "https://github.com/nikhil1403621/url-shortener-python",
        "http://8.8.8.8/",
        "http://1.1.1.1/dns-query",
        "http://192.169.1.1/",  # Not 192.168
        "http://11.0.0.1/",     # Not 10.
        "https://subdomain.domain.org:9000/path?param=1",
    ])
    def test_safe_public_urls_allowed(self, safe_url):
        assert is_safe(safe_url) is True

    def test_empty_host_handling(self):
        assert is_safe("http:///no-host") is True
