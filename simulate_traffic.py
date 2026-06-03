"""NEURO-MESH Traffic Simulator & Visual Dashboard.

Sends continuous traffic to the gateway and displays a live terminal dashboard
showing routing decisions, ML predictions, and server health status.

Color coding:
  GREEN  = Success / Primary server handling traffic
  YELLOW = ML Predictive Reroute / Fallback serving traffic
  RED    = Server crash / 503 error

Usage:
    1. Start the gateway:  uvicorn app.main:app --reload
    2. Run this script:    python simulate_traffic.py

Requirements: requests, colorama
"""

import os
import random
import sys
import time
from datetime import datetime

import requests
from colorama import Fore, Style, init

# Initialize colorama for Windows terminal color support
init(autoreset=True)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GATEWAY_URL: str = "http://127.0.0.1:8000"
PROXY_PATHS: list[str] = [
    "/proxy/api/v1/users",
    "/proxy/api/v1/users/42",
    "/proxy/api/v1/users/100",
    "/proxy/api/v1/orders",
    "/proxy/api/v1/orders/789",
    "/proxy/api/v1/orders/555",
]
REQUEST_INTERVAL: float = 0.5  # seconds between requests
CRASH_PROBABILITY: float = 0.08  # 8% chance of simulating a server crash
RECOVERY_PROBABILITY: float = 0.3  # 30% chance of recovering after crash

# ---------------------------------------------------------------------------
# Dashboard State
# ---------------------------------------------------------------------------

stats = {
    "total_requests": 0,
    "primary_routed": 0,
    "fallback_routed": 0,
    "ml_reroutes": 0,
    "errors_503": 0,
    "errors_other": 0,
    "primary_status": "Alive",
    "fallback_status": "Alive",
}


def clear_screen() -> None:
    """Clear terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def print_header() -> None:
    """Print the dashboard header."""
    print(f"{Fore.CYAN}{Style.BRIGHT}")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║          NEURO-MESH  ·  Fault-Tolerant API Gateway             ║")
    print("║        Live Traffic Dashboard  |  ML Predictive Failover       ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"{Style.RESET_ALL}")


def print_server_status() -> None:
    """Print current server health status."""
    primary_color = Fore.GREEN if stats["primary_status"] == "Alive" else Fore.RED
    fallback_color = Fore.GREEN if stats["fallback_status"] == "Alive" else Fore.RED

    print(f"  ┌─ Server Status ──────────────────────────────────────────────┐")
    print(f"  │  Primary:  {primary_color}{stats['primary_status']:6s}{Style.RESET_ALL}  │  "
          f"Fallback: {fallback_color}{stats['fallback_status']:6s}{Style.RESET_ALL}    │")
    print(f"  └─────────────────────────────────────────────────────────────────┘")


def print_stats() -> None:
    """Print traffic statistics."""
    total = stats["total_requests"] or 1
    print(f"\n  ┌─ Traffic Statistics ───────────────────────────────────────────┐")
    print(f"  │  Total Requests:    {stats['total_requests']:>6}                               │")
    print(f"  │  {Fore.GREEN}Primary Routed:    {stats['primary_routed']:>6}  "
          f"({stats['primary_routed']/total*100:>5.1f}%){Style.RESET_ALL}                   │")
    print(f"  │  {Fore.YELLOW}Fallback Routed:   {stats['fallback_routed']:>6}  "
          f"({stats['fallback_routed']/total*100:>5.1f}%){Style.RESET_ALL}                   │")
    print(f"  │  {Fore.MAGENTA}ML Reroutes:       {stats['ml_reroutes']:>6}  "
          f"({stats['ml_reroutes']/total*100:>5.1f}%){Style.RESET_ALL}                   │")
    print(f"  │  {Fore.RED}503 Errors:        {stats['errors_503']:>6}  "
          f"({stats['errors_503']/total*100:>5.1f}%){Style.RESET_ALL}                   │")
    print(f"  └─────────────────────────────────────────────────────────────────┘")


def print_event(event_type: str, message: str, path: str) -> None:
    """Print a single traffic event."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

    if event_type == "primary":
        icon = f"{Fore.GREEN}✓{Style.RESET_ALL}"
        color = Fore.GREEN
    elif event_type == "fallback":
        icon = f"{Fore.YELLOW}⟳{Style.RESET_ALL}"
        color = Fore.YELLOW
    elif event_type == "ml_reroute":
        icon = f"{Fore.MAGENTA}⚡{Style.RESET_ALL}"
        color = Fore.MAGENTA
    elif event_type == "crash":
        icon = f"{Fore.RED}✗{Style.RESET_ALL}"
        color = Fore.RED
    else:
        icon = f"{Fore.WHITE}?{Style.RESET_ALL}"
        color = Fore.WHITE

    print(f"  {icon} [{timestamp}] {color}{message}{Style.RESET_ALL}")
    print(f"       Path: {Fore.CYAN}{path}{Style.RESET_ALL}")


def simulate_crash() -> None:
    """Randomly simulate a server crash by updating health via the API."""
    if random.random() < CRASH_PROBABILITY:
        # Crash primary
        try:
            resp = requests.put(
                f"{GATEWAY_URL}/health/primary",
                json={"status": "Dead"},
                timeout=2,
            )
            if resp.status_code == 200:
                stats["primary_status"] = "Dead"
                print(f"\n  {Fore.RED}{Style.BRIGHT}⚠ SIMULATED CRASH: "
                      f"Primary server marked DEAD!{Style.RESET_ALL}\n")
        except requests.exceptions.ConnectionError:
            pass


def simulate_recovery() -> None:
    """Randomly recover a dead server."""
    if stats["primary_status"] == "Dead" and random.random() < RECOVERY_PROBABILITY:
        try:
            resp = requests.put(
                f"{GATEWAY_URL}/health/primary",
                json={"status": "Alive"},
                timeout=2,
            )
            if resp.status_code == 200:
                stats["primary_status"] = "Alive"
                print(f"\n  {Fore.GREEN}{Style.BRIGHT}✓ RECOVERY: "
                      f"Primary server back ALIVE!{Style.RESET_ALL}\n")
        except requests.exceptions.ConnectionError:
            pass


def send_request() -> None:
    """Send a single proxy request and process the response."""
    path = random.choice(PROXY_PATHS)
    stats["total_requests"] += 1

    try:
        response = requests.post(f"{GATEWAY_URL}{path}", timeout=5)
        data = response.json()

        if response.status_code == 200:
            server = data.get("server", "unknown")
            decision = data.get("routing_decision", "")

            if "ML PREDICTIVE REROUTE" in decision:
                stats["ml_reroutes"] += 1
                stats["fallback_routed"] += 1
                print_event("ml_reroute", f"ML PREDICTIVE REROUTE → {server}", path)
            elif server == "primary":
                stats["primary_routed"] += 1
                print_event("primary", f"Routed to PRIMARY ({data.get('destination', '')})", path)
            else:
                stats["fallback_routed"] += 1
                print_event("fallback", f"Routed to FALLBACK ({data.get('destination', '')})", path)

        elif response.status_code == 503:
            stats["errors_503"] += 1
            print_event("crash", f"503 - {data.get('error', 'No healthy servers')}", path)

        else:
            stats["errors_other"] += 1
            print_event("crash", f"HTTP {response.status_code} - {data.get('error', 'Unknown')}", path)

    except requests.exceptions.ConnectionError:
        stats["errors_other"] += 1
        print(f"  {Fore.RED}✗ CONNECTION ERROR: Gateway not reachable at {GATEWAY_URL}{Style.RESET_ALL}")
        print(f"    Make sure the server is running: uvicorn app.main:app --reload")


def refresh_health() -> None:
    """Fetch current health from the gateway."""
    try:
        resp = requests.get(f"{GATEWAY_URL}/health", timeout=2)
        if resp.status_code == 200:
            servers = resp.json().get("servers", {})
            stats["primary_status"] = servers.get("primary", {}).get("status", "Unknown")
            stats["fallback_status"] = servers.get("fallback", {}).get("status", "Unknown")
    except requests.exceptions.ConnectionError:
        pass


def main() -> None:
    """Run the traffic simulation loop."""
    clear_screen()
    print_header()
    print(f"\n  {Fore.WHITE}Connecting to gateway at {GATEWAY_URL}...{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}Press Ctrl+C to stop{Style.RESET_ALL}\n")

    # Check if gateway is reachable
    try:
        requests.get(f"{GATEWAY_URL}/health", timeout=3)
        print(f"  {Fore.GREEN}✓ Gateway connected!{Style.RESET_ALL}\n")
    except requests.exceptions.ConnectionError:
        print(f"  {Fore.RED}✗ Cannot reach gateway at {GATEWAY_URL}")
        print(f"  Start it first: uvicorn app.main:app --reload{Style.RESET_ALL}")
        sys.exit(1)

    time.sleep(1)
    request_count = 0

    try:
        while True:
            request_count += 1

            # Every 10 requests, refresh the dashboard view
            if request_count % 10 == 1:
                clear_screen()
                print_header()
                refresh_health()
                print_server_status()
                print_stats()
                print(f"\n  ┌─ Live Traffic Log ─────────────────────────────────────────────┐")

            # Simulate crashes and recoveries
            simulate_crash()
            simulate_recovery()

            # Send request
            send_request()

            time.sleep(REQUEST_INTERVAL)

    except KeyboardInterrupt:
        print(f"\n\n  {Fore.CYAN}{Style.BRIGHT}── Simulation Stopped ──{Style.RESET_ALL}")
        print_stats()
        print(f"\n  {Fore.WHITE}Thank you for using NEURO-MESH!{Style.RESET_ALL}\n")


if __name__ == "__main__":
    main()
