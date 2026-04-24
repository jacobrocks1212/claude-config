#!/usr/bin/env python3
"""
HAR File Analyzer

A comprehensive tool for analyzing HTTP Archive (HAR) files.
Supports request/response summaries, search, filtering, JSON viewing,
error detection, request body inspection, and cookie analysis.

Usage:
    python analyze_har.py <har-file> [options]

Options:
    --summary           Show request summary table
    --search <term>     Search all request/response bodies for term
    --url <pattern>     Filter requests by URL pattern
    --json <pattern>    Pretty-print JSON responses matching URL pattern
    --errors            Show only error responses (4xx, 5xx)
    --body <pattern>    Show request bodies matching URL pattern
    --cookie <name>     Search for specific cookie (original functionality)
    --headers <pattern> Show headers for requests matching URL pattern
    --verbose           Show more detail in output
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass
from urllib.parse import urlparse


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class RequestInfo:
    """Holds extracted request information."""
    index: int
    url: str
    method: str
    status: int
    status_text: str
    content_type: str
    response_size: int
    request_body: str
    response_body: str
    request_headers: list[dict]
    response_headers: list[dict]
    request_cookies: list[dict]
    response_cookies: list[dict]
    time_ms: float


# ============================================================================
# HAR Loading and Parsing
# ============================================================================

def load_har_file(path: str) -> dict:
    """Load and parse HAR file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def parse_entry(index: int, entry: dict) -> RequestInfo:
    """Parse a HAR entry into RequestInfo."""
    request = entry.get('request', {})
    response = entry.get('response', {})

    # Extract content type from response headers
    content_type = ''
    for h in response.get('headers', []):
        if h.get('name', '').lower() == 'content-type':
            content_type = h.get('value', '')
            break

    # Extract response body
    response_content = response.get('content', {})
    response_body = response_content.get('text', '')
    response_size = response_content.get('size', 0)

    # Extract request body
    post_data = request.get('postData', {})
    request_body = post_data.get('text', '')

    return RequestInfo(
        index=index,
        url=request.get('url', ''),
        method=request.get('method', ''),
        status=response.get('status', 0),
        status_text=response.get('statusText', ''),
        content_type=content_type,
        response_size=response_size,
        request_body=request_body,
        response_body=response_body,
        request_headers=request.get('headers', []),
        response_headers=response.get('headers', []),
        request_cookies=request.get('cookies', []),
        response_cookies=response.get('cookies', []),
        time_ms=entry.get('time', 0)
    )


def parse_har(har: dict) -> list[RequestInfo]:
    """Parse all entries from HAR file."""
    entries = har.get('log', {}).get('entries', [])
    return [parse_entry(i, entry) for i, entry in enumerate(entries)]


# ============================================================================
# Filtering Utilities
# ============================================================================

def filter_by_url(requests: list[RequestInfo], pattern: str) -> list[RequestInfo]:
    """Filter requests where URL contains pattern (case-insensitive)."""
    pattern_lower = pattern.lower()
    return [r for r in requests if pattern_lower in r.url.lower()]


def filter_errors(requests: list[RequestInfo]) -> list[RequestInfo]:
    """Filter to only 4xx and 5xx responses."""
    return [r for r in requests if 400 <= r.status < 600]


def get_header_value(headers: list[dict], name: str) -> list[tuple[str, str]]:
    """Get all header values matching a name (case-insensitive)."""
    results = []
    name_lower = name.lower()
    for header in headers:
        header_name = header.get('name', '')
        if header_name.lower() == name_lower:
            results.append((header_name, header.get('value', '')))
    return results


def find_headers_containing(headers: list[dict], substring: str) -> list[tuple[str, str]]:
    """Find all headers where name OR value contains substring (case-insensitive)."""
    results = []
    substring_lower = substring.lower()
    for header in headers:
        name = header.get('name', '')
        value = header.get('value', '')
        if substring_lower in name.lower() or substring_lower in value.lower():
            results.append((name, value))
    return results


# ============================================================================
# Display Utilities
# ============================================================================

def truncate(s: str, max_len: int = 80) -> str:
    """Truncate string with ellipsis if too long."""
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + '...'


def format_size(size: int) -> str:
    """Format byte size to human-readable string."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


def get_status_indicator(status: int) -> str:
    """Return status indicator for visual distinction."""
    if 200 <= status < 300:
        return "[OK]"
    elif 300 <= status < 400:
        return "[->]"  # redirect
    elif 400 <= status < 500:
        return "[!!]"  # client error
    elif status >= 500:
        return "[XX]"  # server error
    return "[??]"


def print_separator(char: str = '-', width: int = 80):
    """Print a separator line."""
    print(char * width)


def print_header(title: str, char: str = '=', width: int = 80):
    """Print a section header."""
    print()
    print(char * width)
    print(title)
    print(char * width)


# ============================================================================
# Feature: Request Summary
# ============================================================================

def show_summary(requests: list[RequestInfo], verbose: bool = False):
    """Display a summary table of all requests."""
    print_header("REQUEST SUMMARY")
    print(f"Total requests: {len(requests)}")
    print()

    # Count by status
    status_counts: dict[str, int] = {}
    for r in requests:
        category = f"{r.status // 100}xx"
        status_counts[category] = status_counts.get(category, 0) + 1

    print("Status breakdown:", " | ".join(f"{k}: {v}" for k, v in sorted(status_counts.items())))
    print()

    # Table header
    print(f"{'#':>4} {'Method':<6} {'Status':<6} {'Size':>10} {'Type':<25} {'URL'}")
    print_separator('-')

    for r in requests:
        url_display = r.url if verbose else truncate(r.url, 60)
        content_type_display = truncate(r.content_type.split(';')[0], 25)
        status_ind = get_status_indicator(r.status)

        print(f"{r.index:>4} {r.method:<6} {r.status:<3} {status_ind} {format_size(r.response_size):>10} {content_type_display:<25} {url_display}")

    print_separator('-')
    print(f"Total response size: {format_size(sum(r.response_size for r in requests))}")


# ============================================================================
# Feature: Search Bodies
# ============================================================================

def search_bodies(requests: list[RequestInfo], term: str, verbose: bool = False):
    """Search for a term in all request and response bodies."""
    print_header(f"SEARCH RESULTS: '{term}'")

    term_lower = term.lower()
    found_count = 0

    for r in requests:
        matches_in_request = term_lower in r.request_body.lower() if r.request_body else False
        matches_in_response = term_lower in r.response_body.lower() if r.response_body else False

        if matches_in_request or matches_in_response:
            found_count += 1
            print(f"\n#{r.index} [{r.method}] {r.status} - {truncate(r.url, 70)}")

            if matches_in_request:
                print("  [REQUEST BODY]")
                show_match_context(r.request_body, term, verbose)

            if matches_in_response:
                print("  [RESPONSE BODY]")
                show_match_context(r.response_body, term, verbose)

    print()
    print_separator('-')
    print(f"Found '{term}' in {found_count} request(s)")

    if found_count == 0:
        print("Tip: Try --search with a different term, or use --cookie for cookie-specific search")


def show_match_context(text: str, term: str, verbose: bool, context_chars: int = 100):
    """Show context around matches in text."""
    matches = list(re.finditer(re.escape(term), text, re.IGNORECASE))
    shown = 0
    max_matches = 10 if verbose else 3

    for match in matches[:max_matches]:
        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)
        context = text[start:end].replace('\n', ' ').replace('\r', '').strip()

        prefix = '...' if start > 0 else ''
        suffix = '...' if end < len(text) else ''
        print(f"    {prefix}{context}{suffix}")
        shown += 1

    remaining = len(matches) - shown
    if remaining > 0:
        print(f"    ... and {remaining} more match(es)")


# ============================================================================
# Feature: Show Errors
# ============================================================================

def show_errors(requests: list[RequestInfo], verbose: bool = False):
    """Show only error responses (4xx and 5xx)."""
    errors = filter_errors(requests)

    print_header("ERROR RESPONSES (4xx/5xx)")

    if not errors:
        print("No error responses found.")
        return

    print(f"Found {len(errors)} error response(s):")
    print()

    for r in errors:
        status_ind = get_status_indicator(r.status)
        print(f"#{r.index} {status_ind} {r.status} {r.status_text}")
        print(f"  {r.method} {r.url}")
        print(f"  Content-Type: {r.content_type}")

        # Show response body preview for errors
        if r.response_body:
            body_preview = r.response_body[:500].replace('\n', ' ').strip()
            print(f"  Response: {truncate(body_preview, 200)}")
        print()


# ============================================================================
# Feature: JSON Response Viewer
# ============================================================================

def show_json_responses(requests: list[RequestInfo], url_pattern: str, verbose: bool = False):
    """Pretty-print JSON responses matching URL pattern."""
    filtered = filter_by_url(requests, url_pattern)

    print_header(f"JSON RESPONSES matching '{url_pattern}'")

    if not filtered:
        print(f"No requests match URL pattern '{url_pattern}'")
        return

    json_count = 0
    for r in filtered:
        if 'json' in r.content_type.lower() or r.response_body.strip().startswith(('{', '[')):
            try:
                parsed = json.loads(r.response_body)
                json_count += 1

                print(f"\n#{r.index} [{r.method}] {r.status} - {truncate(r.url, 60)}")
                print_separator('-', 60)

                # Pretty print with indentation
                formatted = json.dumps(parsed, indent=2, ensure_ascii=False)

                # Limit output unless verbose
                lines = formatted.split('\n')
                max_lines = 100 if verbose else 30

                if len(lines) > max_lines:
                    print('\n'.join(lines[:max_lines]))
                    print(f"\n... ({len(lines) - max_lines} more lines, use --verbose to see all)")
                else:
                    print(formatted)

            except json.JSONDecodeError:
                # Not valid JSON, skip
                pass

    print()
    print_separator('-')
    print(f"Found {json_count} JSON response(s) matching pattern")


# ============================================================================
# Feature: Request Body Viewer
# ============================================================================

def show_request_bodies(requests: list[RequestInfo], url_pattern: str, verbose: bool = False):
    """Show request bodies for POST/PUT requests matching URL pattern."""
    filtered = filter_by_url(requests, url_pattern)

    print_header(f"REQUEST BODIES matching '{url_pattern}'")

    if not filtered:
        print(f"No requests match URL pattern '{url_pattern}'")
        return

    body_count = 0
    for r in filtered:
        if r.request_body and r.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            body_count += 1

            print(f"\n#{r.index} [{r.method}] {r.status} - {truncate(r.url, 60)}")
            print_separator('-', 60)

            # Try to pretty-print if JSON
            try:
                parsed = json.loads(r.request_body)
                formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                body = formatted
            except json.JSONDecodeError:
                body = r.request_body

            # Limit output unless verbose
            lines = body.split('\n')
            max_lines = 50 if verbose else 20

            if len(lines) > max_lines:
                print('\n'.join(lines[:max_lines]))
                print(f"\n... ({len(lines) - max_lines} more lines, use --verbose to see all)")
            else:
                print(body)

    print()
    print_separator('-')
    print(f"Found {body_count} request(s) with bodies matching pattern")


# ============================================================================
# Feature: Headers Viewer
# ============================================================================

def show_headers(requests: list[RequestInfo], url_pattern: str, verbose: bool = False):
    """Show headers for requests matching URL pattern."""
    filtered = filter_by_url(requests, url_pattern)

    print_header(f"HEADERS for requests matching '{url_pattern}'")

    if not filtered:
        print(f"No requests match URL pattern '{url_pattern}'")
        return

    for r in filtered:
        print(f"\n#{r.index} [{r.method}] {r.status} - {truncate(r.url, 60)}")

        print("\n  Request Headers:")
        for h in r.request_headers:
            name = h.get('name', '')
            value = h.get('value', '')
            value_display = value if verbose else truncate(value, 80)
            print(f"    {name}: {value_display}")

        print("\n  Response Headers:")
        for h in r.response_headers:
            name = h.get('name', '')
            value = h.get('value', '')
            value_display = value if verbose else truncate(value, 80)
            print(f"    {name}: {value_display}")

        print()


# ============================================================================
# Feature: Cookie Analysis (Original Functionality)
# ============================================================================

def analyze_cookies(requests: list[RequestInfo], har: dict, search_cookie: str, verbose: bool = False):
    """Original cookie analysis functionality."""
    print_header(f"COOKIE ANALYSIS: '{search_cookie}'")

    # Track what we find
    set_cookie_count = 0
    cookie_header_count = 0
    cookies_array_count = 0
    search_cookie_count = 0

    # === Response Set-Cookie Headers ===
    print("\n[RESPONSE] Set-Cookie Headers")
    print_separator('-', 40)

    for r in requests:
        # Check for Set-Cookie header
        set_cookies = get_header_value(r.response_headers, 'set-cookie')
        for name, value in set_cookies:
            set_cookie_count += 1
            print(f"\nRequest #{r.index}: {truncate(r.url, 100)}")
            print(f"  Header: {name}")
            print(f"  Value: {value}")

            if search_cookie.lower() in value.lower():
                search_cookie_count += 1
                print(f"  >>> CONTAINS '{search_cookie}' <<<")

        # Check response cookies array
        if r.response_cookies:
            cookies_array_count += 1
            print(f"\nRequest #{r.index}: {truncate(r.url, 100)}")
            print(f"  Response cookies array ({len(r.response_cookies)} cookies):")
            for cookie in r.response_cookies:
                cookie_name = cookie.get('name', '')
                cookie_value = cookie.get('value', '')
                print(f"    {cookie_name} = {truncate(cookie_value, 80)}")
                if search_cookie.lower() in cookie_name.lower():
                    search_cookie_count += 1
                    print(f"    >>> MATCHES '{search_cookie}' <<<")

    if set_cookie_count == 0 and cookies_array_count == 0:
        print("  (none found)")

    # === Request Cookie Headers ===
    print("\n\n[REQUEST] Cookie Headers")
    print_separator('-', 40)

    for r in requests:
        # Check for Cookie header
        cookies = get_header_value(r.request_headers, 'cookie')
        for name, value in cookies:
            cookie_header_count += 1
            print(f"\nRequest #{r.index}: {truncate(r.url, 100)}")
            print(f"  Header: {name}")
            print(f"  Value: {truncate(value, 300)}")

            if search_cookie.lower() in value.lower():
                search_cookie_count += 1
                print(f"  >>> CONTAINS '{search_cookie}' <<<")

        # Check request cookies array
        if r.request_cookies:
            cookies_array_count += 1
            print(f"\nRequest #{r.index}: {truncate(r.url, 100)}")
            print(f"  Request cookies array ({len(r.request_cookies)} cookies):")
            for cookie in r.request_cookies:
                cookie_name = cookie.get('name', '')
                cookie_value = cookie.get('value', '')
                print(f"    {cookie_name} = {truncate(cookie_value, 80)}")
                if search_cookie.lower() in cookie_name.lower():
                    search_cookie_count += 1
                    print(f"    >>> MATCHES '{search_cookie}' <<<")

    if cookie_header_count == 0:
        print("  (none found)")

    # === Search for specific cookie anywhere in headers ===
    print(f"\n\n[SEARCH] Headers containing '{search_cookie}'")
    print_separator('-', 40)

    found_in_headers = False
    for r in requests:
        req_matches = find_headers_containing(r.request_headers, search_cookie)
        for name, value in req_matches:
            found_in_headers = True
            print(f"\nRequest #{r.index} [REQ HEADER]: {truncate(r.url, 80)}")
            print(f"  {name}: {truncate(value, 200)}")

        resp_matches = find_headers_containing(r.response_headers, search_cookie)
        for name, value in resp_matches:
            found_in_headers = True
            print(f"\nRequest #{r.index} [RESP HEADER]: {truncate(r.url, 80)}")
            print(f"  {name}: {truncate(value, 200)}")

    if not found_in_headers:
        print(f"  '{search_cookie}' not found in any headers")

    # === Raw string search in entire HAR ===
    print(f"\n\n[RAW SEARCH] Searching entire HAR file for '{search_cookie}'")
    print_separator('-', 40)

    har_str = json.dumps(har)
    if search_cookie.lower() in har_str.lower():
        print(f"  FOUND '{search_cookie}' in HAR file!")

        matches = list(re.finditer(re.escape(search_cookie), har_str, re.IGNORECASE))
        print(f"  Total occurrences: {len(matches)}")

        max_matches = 20 if verbose else 10
        for i, match in enumerate(matches[:max_matches]):
            start = max(0, match.start() - 50)
            end = min(len(har_str), match.end() + 100)
            context = har_str[start:end].replace('\n', ' ').replace('\r', '')
            print(f"\n  Match {i + 1}:")
            print(f"    ...{context}...")

        if len(matches) > max_matches:
            print(f"\n  ... and {len(matches) - max_matches} more matches")
    else:
        print(f"  '{search_cookie}' NOT found anywhere in HAR file")

    # === Summary ===
    print("\n")
    print_separator('=')
    print("COOKIE SUMMARY")
    print_separator('=')
    print(f"Total requests analyzed: {len(requests)}")
    print(f"Set-Cookie headers found: {set_cookie_count}")
    print(f"Cookie request headers found: {cookie_header_count}")
    print(f"Non-empty cookies arrays: {cookies_array_count}")
    print(f"'{search_cookie}' occurrences in cookies: {search_cookie_count}")

    # HAR export warning
    if set_cookie_count == 0 and cookie_header_count == 0:
        print("""
WARNING: No cookie-related headers found!

This HAR file may have been exported without cookies. Chrome's HAR export
strips cookie data for privacy. Consider using:
- Fiddler with HTTPS decryption
- Direct DevTools inspection
- curl -v for specific requests
""")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Analyze HAR (HTTP Archive) files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze_har.py capture.har --summary
  python analyze_har.py capture.har --errors
  python analyze_har.py capture.har --search "api_key"
  python analyze_har.py capture.har --url "/api/" --json "/api/"
  python analyze_har.py capture.har --body "/login"
  python analyze_har.py capture.har --cookie "session_id"
  python analyze_har.py capture.har --headers "/api/users"
"""
    )

    parser.add_argument('har_file', nargs='?',
                        default=r'C:\Users\JacobMadsen\Downloads\www.cognitoforms.com.har',
                        help='Path to HAR file')
    parser.add_argument('--summary', action='store_true',
                        help='Show request summary table')
    parser.add_argument('--search', metavar='TERM',
                        help='Search all request/response bodies for term')
    parser.add_argument('--url', metavar='PATTERN',
                        help='Filter requests by URL pattern (substring match)')
    parser.add_argument('--json', metavar='PATTERN',
                        help='Pretty-print JSON responses matching URL pattern')
    parser.add_argument('--errors', action='store_true',
                        help='Show only error responses (4xx, 5xx)')
    parser.add_argument('--body', metavar='PATTERN',
                        help='Show request bodies matching URL pattern')
    parser.add_argument('--headers', metavar='PATTERN',
                        help='Show headers for requests matching URL pattern')
    parser.add_argument('--cookie', metavar='NAME', default=None,
                        help='Search for specific cookie (original functionality)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show more detail in output')

    # Legacy positional argument support for backward compatibility
    parser.add_argument('legacy_cookie', nargs='?', default=None,
                        help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Handle legacy usage: analyze_har.py <har_file> <cookie_name>
    if args.legacy_cookie and not args.cookie:
        args.cookie = args.legacy_cookie

    # Validate file exists
    har_path = Path(args.har_file)
    if not har_path.exists():
        print(f"Error: HAR file not found: {args.har_file}")
        sys.exit(1)

    # Load HAR file
    try:
        har = load_har_file(args.har_file)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in HAR file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading HAR file: {e}")
        sys.exit(1)

    requests = parse_har(har)

    print(f"HAR File: {args.har_file}")
    print(f"Total requests: {len(requests)}")

    # Apply URL filter if specified (affects most operations)
    filtered_requests = requests
    if args.url:
        filtered_requests = filter_by_url(requests, args.url)
        print(f"Filtered to {len(filtered_requests)} request(s) matching '{args.url}'")

    # Determine what to do
    has_action = any([
        args.summary,
        args.search,
        args.json,
        args.errors,
        args.body,
        args.headers,
        args.cookie
    ])

    # Default to summary if no action specified
    if not has_action:
        args.summary = True

    # Execute requested actions
    if args.summary:
        show_summary(filtered_requests, args.verbose)

    if args.errors:
        show_errors(filtered_requests, args.verbose)

    if args.search:
        search_bodies(filtered_requests, args.search, args.verbose)

    if args.json:
        show_json_responses(requests, args.json, args.verbose)

    if args.body:
        show_request_bodies(requests, args.body, args.verbose)

    if args.headers:
        show_headers(requests, args.headers, args.verbose)

    if args.cookie:
        analyze_cookies(requests, har, args.cookie, args.verbose)


if __name__ == '__main__':
    main()
