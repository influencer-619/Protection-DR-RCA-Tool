"""Peer link types: line remote vs cascade roles (plant config only)."""

from __future__ import annotations

from app.services import remote_peer


def test_peer_end_labels_line():
    class R:
        metadata_json = {"remote_relay_id": "p1", "peer_type": "line_remote"}

    r = R()  # type: ignore[assignment]
    assert remote_peer.get_peer_type(r) == "line_remote"  # type: ignore[arg-type]
    assert remote_peer.peer_end_label_for_local(r) == "LOCAL"  # type: ignore[arg-type]
    assert remote_peer.peer_end_label_for_peer(r) == "REMOTE"  # type: ignore[arg-type]


def test_peer_end_labels_cascade_initiator():
    class R:
        metadata_json = {
            "remote_relay_id": "p2",
            "peer_type": "cascade",
            "cascade_role": "INITIATOR",
        }

    r = R()  # type: ignore[assignment]
    assert remote_peer.get_peer_type(r) == "cascade"  # type: ignore[arg-type]
    assert remote_peer.peer_end_label_for_local(r) == "INITIATOR"  # type: ignore[arg-type]
    assert remote_peer.peer_end_label_for_peer(r) == "BACKUP"  # type: ignore[arg-type]


def test_peer_end_labels_cascade_backup():
    class R:
        metadata_json = {
            "remote_relay_id": "p3",
            "peer_type": "cascade",
            "cascade_role": "BACKUP",
        }

    r = R()  # type: ignore[assignment]
    assert remote_peer.peer_end_label_for_local(r) == "BACKUP"  # type: ignore[arg-type]
    assert remote_peer.peer_end_label_for_peer(r) == "INITIATOR"  # type: ignore[arg-type]


def test_legacy_remote_id_implies_line():
    class R:
        metadata_json = {"remote_relay_id": "old"}

    r = R()  # type: ignore[assignment]
    assert remote_peer.get_peer_type(r) == "line_remote"  # type: ignore[arg-type]
