# Performance notes (GAP-PERF-013)

Predictable behaviour for large / dual-end disturbance records.

## Waveform caps (configurable)

| Setting | Env | Default | Where applied |
|---------|-----|--------:|---------------|
| Sample downsample | `WAVEFORM_MAX_POINTS` | 20 000 | COMTRADE ingest (`waveform_service`) — timestamps + each channel trimmed |
| Channel select | `WAVEFORM_MAX_CHANNELS` | 128 | Waveform API load (`load_waveform_payload`) — prefers protection digitals |

Raise only when the host has headroom; very large dual overlays still use one COMTRADE file id at a time (lazy remote end via `comtrade_file_id`).

## Dual-end / Local–Remote

- Overlay loads one end per request; switch `comtrade_file_id` for REMOTE.
- Electrical dual-end 87L compare uses phasor summaries, not full sample series.
- Cap tests: `tests/test_waveform_channel_cap.py`.

## Uploads

- `MAX_UPLOAD_SIZE_MB` (default 200) enforced in `file_service`.
- ZIP expand is bounded by member path safety; do not disable extension allow-list.

## Analysis jobs

- Prefer async jobs (`RUN_ANALYSIS_SYNC=false`) under load.
- SQLite / portable: keep one writer; orphan job heal skips `RUNNING`.

## Acceptance

- Channel-cap unit tests remain green.
- Waveform note string when channels omitted (`Showing N of M channels…`).
- No full-resolution sample JSON returned to the browser beyond `WAVEFORM_MAX_POINTS`.
