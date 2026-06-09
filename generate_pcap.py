"""NEURO-MESH PCAP Generator — Wireshark-compatible traffic capture.

Generates a real neuro_mesh_traffic.pcap file containing 50 simulated packets:
- TCP 3-way handshakes (SYN, SYN-ACK, ACK)
- HTTP POST requests to the API gateway proxy endpoint
- HTTP 200 responses (successful routing)
- HTTP 503 responses (simulated server crash)

Usage:
    pip install scapy
    python generate_pcap.py

Output:
    neuro_mesh_traffic.pcap — open in Wireshark for analysis
"""

import random
from datetime import datetime

from scapy.all import (
    IP,
    TCP,
    Raw,
    Ether,
    wrpcap,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GATEWAY_IP: str = "10.10.0.1"
GATEWAY_PORT: int = 8000
GATEWAY_MAC: str = "aa:bb:cc:dd:ee:01"

CLIENT_IPS: list[str] = [
    "192.168.1.101", "192.168.1.102", "10.0.0.45",
    "172.16.0.88", "192.168.2.77", "10.0.0.12",
]
CLIENT_MAC: str = "aa:bb:cc:dd:ee:02"

PRIMARY_IP: str = "10.10.1.1"
FALLBACK_IP: str = "10.10.1.2"

PATHS: list[str] = [
    "/proxy/api/v1/users",
    "/proxy/api/v1/users/42",
    "/proxy/api/v1/orders",
    "/proxy/api/v1/orders/789",
    "/proxy/api/v1/products",
    "/proxy/api/v1/products/100",
    "/proxy/api/v1/payments",
    "/proxy/api/v1/auth/login",
    "/proxy/api/v1/notifications",
    "/proxy/api/v2/analytics/events",
]

SERVICES: list[str] = [
    "user-service", "order-service", "product-service",
    "payment-service", "auth-service", "notification-service",
    "analytics-service",
]

OUTPUT_FILE: str = "neuro_mesh_traffic.pcap"


# ---------------------------------------------------------------------------
# Packet Generation
# ---------------------------------------------------------------------------


def generate_tcp_handshake(
    client_ip: str, seq_base: int, sport: int
) -> list:
    """Generate a TCP 3-way handshake (SYN, SYN-ACK, ACK)."""
    syn = (
        Ether(src=CLIENT_MAC, dst=GATEWAY_MAC)
        / IP(src=client_ip, dst=GATEWAY_IP)
        / TCP(sport=sport, dport=GATEWAY_PORT, flags="S", seq=seq_base)
    )
    syn_ack = (
        Ether(src=GATEWAY_MAC, dst=CLIENT_MAC)
        / IP(src=GATEWAY_IP, dst=client_ip)
        / TCP(sport=GATEWAY_PORT, dport=sport, flags="SA", seq=1000, ack=seq_base + 1)
    )
    ack = (
        Ether(src=CLIENT_MAC, dst=GATEWAY_MAC)
        / IP(src=client_ip, dst=GATEWAY_IP)
        / TCP(sport=sport, dport=GATEWAY_PORT, flags="A", seq=seq_base + 1, ack=1001)
    )
    return [syn, syn_ack, ack]


def generate_http_request(
    client_ip: str, path: str, sport: int, seq: int
) -> list:
    """Generate an HTTP POST request packet."""
    body = '{"timestamp": "' + datetime.utcnow().isoformat() + '"}'
    http_payload = (
        f"POST {path} HTTP/1.1\r\n"
        f"Host: {GATEWAY_IP}:{GATEWAY_PORT}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: keep-alive\r\n"
        f"\r\n"
        f"{body}"
    )
    pkt = (
        Ether(src=CLIENT_MAC, dst=GATEWAY_MAC)
        / IP(src=client_ip, dst=GATEWAY_IP)
        / TCP(sport=sport, dport=GATEWAY_PORT, flags="PA", seq=seq, ack=1001)
        / Raw(load=http_payload.encode())
    )
    return [pkt]


def generate_http_response(
    client_ip: str, sport: int, status_code: int,
    server: str, destination: str, path: str
) -> list:
    """Generate an HTTP response packet (200 or 503)."""
    if status_code == 200:
        body = (
            '{"server": "' + server + '", '
            '"destination": "' + destination + '", '
            '"routing_decision": "' + server.capitalize() + ' server selected: healthy", '
            '"timestamp": "' + datetime.utcnow().isoformat() + '"}'
        )
        status_line = "HTTP/1.1 200 OK"
    else:
        body = '{"error": "No healthy servers available", "path": "' + path + '"}'
        status_line = "HTTP/1.1 503 Service Unavailable"

    http_payload = (
        f"{status_line}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: keep-alive\r\n"
        f"\r\n"
        f"{body}"
    )
    pkt = (
        Ether(src=GATEWAY_MAC, dst=CLIENT_MAC)
        / IP(src=GATEWAY_IP, dst=client_ip)
        / TCP(sport=GATEWAY_PORT, dport=sport, flags="PA", seq=1001, ack=500)
        / Raw(load=http_payload.encode())
    )
    return [pkt]


def main() -> None:
    """Generate 50 simulated network packets and save as PCAP."""
    print("=" * 60)
    print("  NEURO-MESH PCAP Generator")
    print("  Generating Wireshark-compatible traffic capture...")
    print("=" * 60)

    packets = []
    seq_counter = 100

    for i in range(50):
        client_ip = random.choice(CLIENT_IPS)
        sport = random.randint(49152, 65535)
        path = random.choice(PATHS)
        service = random.choice(SERVICES)

        # Decide if this is a normal request or a crash scenario
        is_crash = random.random() < 0.12  # ~12% are 503 errors

        if i % 8 == 0:
            # Every 8th request gets a full TCP handshake
            handshake = generate_tcp_handshake(client_ip, seq_counter, sport)
            packets.extend(handshake)
            seq_counter += 1

        # HTTP Request
        request_pkts = generate_http_request(client_ip, path, sport, seq_counter)
        packets.extend(request_pkts)
        seq_counter += 100

        # HTTP Response
        if is_crash:
            response_pkts = generate_http_response(
                client_ip, sport, 503, "none", "", path
            )
            status_str = "503 CRASH"
        else:
            server = random.choice(["primary", "fallback"])
            response_pkts = generate_http_response(
                client_ip, sport, 200, server, service, path
            )
            status_str = f"200 → {server}"

        packets.extend(response_pkts)

        print(f"  [{i+1:02d}/50] {client_ip}:{sport} → {GATEWAY_IP}:{GATEWAY_PORT} | {path} | {status_str}")

    # Write PCAP
    wrpcap(OUTPUT_FILE, packets)

    print()
    print(f"  ✓ Generated {len(packets)} packets across 50 requests")
    print(f"  ✓ Saved to: {OUTPUT_FILE}")
    print(f"  ✓ Open in Wireshark: wireshark {OUTPUT_FILE}")
    print()
    print("  Packet breakdown:")
    print(f"    TCP Handshakes: {sum(1 for i in range(50) if i % 8 == 0) * 3}")
    print(f"    HTTP Requests:  50")
    print(f"    HTTP Responses: 50")
    print(f"    Total:          {len(packets)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
