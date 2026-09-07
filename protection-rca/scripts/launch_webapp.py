"""
Protection RCA — one-click launcher.

Starts API + UI, opens the browser, and keeps a control window open.
Closing that window (or the process exiting) stops API, UI, and related children.
"""

from __future__ import annotations

import atexit
import ctypes
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional


API_BIND = os.environ.get("PROTECTION_RCA_HOST", "0.0.0.0").strip() or "0.0.0.0"
API_PORT = int(os.environ.get("PROTECTION_RCA_PORT", "8001") or "8001")
# Health checks must use loopback; binding 0.0.0.0 is not connectable.
API_CHECK_HOST = "127.0.0.1"
UI_HOST = os.environ.get("PROTECTION_RCA_UI_HOST", "0.0.0.0").strip() or "0.0.0.0"
UI_PORT = int(os.environ.get("PROTECTION_RCA_UI_PORT", "5173") or "5173")
UI_CHECK_HOST = "127.0.0.1"

# PIDs started / adopted by this launcher
_managed_pids: set[int] = set()
_shutdown_done = False
_job_handle: Optional[int] = None


def error_box(title: str, message: str) -> None:
    if os.name == "nt":
        try:
            import ctypes as ct

            ct.windll.user32.MessageBoxW(0, message, title, 0x10)
            return
        except Exception:
            pass
    print(f"{title}: {message}")
    try:
        input("Press Enter to exit...")
    except EOFError:
        pass


def root_dir() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (exe_dir, exe_dir.parent, exe_dir.parent.parent):
            if (candidate / "backend").is_dir() and (candidate / "frontend").is_dir():
                return candidate
        return exe_dir
    return Path(__file__).resolve().parents[1]


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_port(host: str, port: int, timeout_s: float = 90.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if port_open(host, port):
            return True
        time.sleep(0.4)
    return False


def find_python(root: Path) -> Path:
    venv_py = root / "backend" / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        return venv_py
    return Path(sys.executable)


def find_npm(root: Path) -> Path | None:
    portable = root / ".tools" / "node" / "npm.cmd"
    if portable.is_file():
        return portable
    which = shutil.which("npm")
    return Path(which) if which else None


def find_node_dir(root: Path) -> Path | None:
    portable = root / ".tools" / "node"
    if (portable / "node.exe").is_file():
        return portable
    return None


def frontend_dist_ready(root: Path) -> bool:
    return (root / "frontend" / "dist" / "index.html").is_file()


def lan_ipv4_addresses() -> list[str]:
    """Best-effort private LAN IPv4 list for sharing the URL."""
    found: list[str] = []

    def _is_private(ip: str) -> bool:
        if ip.startswith(("192.168.", "10.")):
            return True
        if ip.startswith("172."):
            try:
                second = int(ip.split(".")[1])
            except (IndexError, ValueError):
                return False
            return 16 <= second <= 31
        return False

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if _is_private(ip) and ip not in found:
                found.append(ip)
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        probe.close()
        if ip and not ip.startswith("127.") and ip not in found:
            found.insert(0, ip)
    except OSError:
        pass
    return found


def local_ui_url(portable: bool) -> str:
    if portable:
        return f"http://127.0.0.1:{API_PORT}/"
    return f"http://127.0.0.1:{UI_PORT}/"


def network_urls(portable: bool) -> list[str]:
    port = API_PORT if portable else UI_PORT
    return [f"http://{ip}:{port}/" for ip in lan_ipv4_addresses()]


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    # Hidden console; do NOT use CREATE_BREAKAWAY_FROM_JOB so Job Object can own children.
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _init_windows_job() -> None:
    """Create a Win32 Job Object that kills all assigned children when this process exits."""
    global _job_handle
    if os.name != "nt" or _job_handle is not None:
        return
    try:
        kernel32 = ctypes.windll.kernel32
        JobObjectExtendedLimitInformation = 9
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(handle)
            return
        _job_handle = int(handle)
    except Exception:
        _job_handle = None


def _assign_pid_to_job(pid: int) -> None:
    if os.name != "nt" or not _job_handle or pid <= 0:
        return
    try:
        kernel32 = ctypes.windll.kernel32
        PROCESS_SET_QUOTA = 0x0100
        PROCESS_TERMINATE = 0x0001
        PROCESS_ASSIGN = PROCESS_SET_QUOTA | PROCESS_TERMINATE
        hproc = kernel32.OpenProcess(PROCESS_ASSIGN, False, int(pid))
        if not hproc:
            return
        try:
            kernel32.AssignProcessToJobObject(_job_handle, hproc)
        finally:
            kernel32.CloseHandle(hproc)
    except Exception:
        pass


def popen_managed(cmd: list[str], cwd: Path, env: dict) -> subprocess.Popen:
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=_creation_flags(),
        close_fds=True,
    )
    if proc.pid:
        _managed_pids.add(proc.pid)
        _assign_pid_to_job(proc.pid)
    return proc


def kill_pid_tree(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=flags,
        )
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass


def pids_listening_on(port: int) -> list[int]:
    """Best-effort: find PIDs bound to a local TCP port (Windows)."""
    if os.name != "nt":
        return []
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            text=True,
            errors="ignore",
            creationflags=flags,
        )
    except Exception:
        return []
    found: set[int] = set()
    needle = f":{port}"
    for line in out.splitlines():
        if "LISTENING" not in line.upper():
            continue
        if needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        local = parts[1] if len(parts) > 1 else ""
        if not (local.endswith(needle) or local.endswith(f"]{needle}")):
            continue
        try:
            found.add(int(parts[-1]))
        except ValueError:
            continue
    return sorted(found)


def pids_matching_cmdline(patterns: list[str]) -> list[int]:
    """Find PIDs whose command line matches any substring (case-insensitive)."""
    if os.name != "nt":
        return []
    try:
        import wmi  # type: ignore

        c = wmi.WMI()
        pats = [p.lower() for p in patterns]
        out: list[int] = []
        for proc in c.Win32_Process():
            cmd = (proc.CommandLine or "") + " " + (proc.Name or "")
            low = cmd.lower()
            if any(p in low for p in pats):
                try:
                    out.append(int(proc.ProcessId))
                except Exception:
                    pass
        return out
    except Exception:
        pass
    # Fallback: WMIC
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.check_output(
            ["wmic", "process", "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
            text=True,
            errors="ignore",
            creationflags=flags,
        )
        pats = [p.lower() for p in patterns]
        found: list[int] = []
        for line in out.splitlines():
            low = line.lower()
            if not any(p in low for p in pats):
                continue
            parts = [p.strip() for p in line.split(",")]
            if not parts:
                continue
            try:
                found.append(int(parts[-1]))
            except ValueError:
                continue
        return found
    except Exception:
        return []


def shutdown_all() -> None:
    """Stop API, UI, and any related child processes. Safe to call multiple times."""
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True

    # 1) Managed process trees
    for pid in list(_managed_pids):
        kill_pid_tree(pid)
    _managed_pids.clear()

    # 2) Anything still listening on our ports
    for port in (UI_PORT, API_PORT):
        for pid in pids_listening_on(port):
            kill_pid_tree(pid)

    # 3) Orphans matching known command lines (uvicorn / vite / npm for this app)
    for pid in pids_matching_cmdline(
        [
            "uvicorn app.main:app",
            f"--port {API_PORT}",
            "vite --host",
            f"--port {UI_PORT}",
            "protection-rca\\frontend",
            "protection-rca/frontend",
            "npm run dev",
        ]
    ):
        # Don't kill ourselves
        if pid == os.getpid():
            continue
        kill_pid_tree(pid)

    # 4) Second pass on ports after a brief settle
    time.sleep(0.3)
    for port in (UI_PORT, API_PORT):
        for pid in pids_listening_on(port):
            kill_pid_tree(pid)


def start_backend(root: Path, *, portable: bool) -> None:
    if port_open(API_CHECK_HOST, API_PORT):
        # Adopt existing listener so close still stops it
        for pid in pids_listening_on(API_PORT):
            _managed_pids.add(pid)
            _assign_pid_to_job(pid)
        return
    py = find_python(root)
    backend = root / "backend"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend)
    # Absolute sqlite path so relaunch / cwd changes don't orphan the DB
    db = backend / "protection_rca_local.db"
    env.setdefault(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{db.resolve().as_posix()}",
    )
    if portable:
        dist = root / "frontend" / "dist"
        env["SERVE_FRONTEND"] = "1"
        env["FRONTEND_DIST"] = str(dist.resolve())
        env.setdefault("APP_ENV", "portable")
    else:
        # Dev: Vite serves UI; do not mount SPA catch-all over API docs casually
        env.setdefault("SERVE_FRONTEND", "0")

    popen_managed(
        [
            str(py),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            API_BIND,
            "--port",
            str(API_PORT),
        ],
        backend,
        env,
    )


def start_frontend(root: Path) -> None:
    if port_open(UI_CHECK_HOST, UI_PORT):
        for pid in pids_listening_on(UI_PORT):
            _managed_pids.add(pid)
            _assign_pid_to_job(pid)
        return

    npm = find_npm(root)
    if npm is None:
        raise RuntimeError(
            "Node/npm not found and frontend/dist is missing.\n"
            "Either run scripts\\build-portable-share.bat (builds UI into frontend\\dist),\n"
            "or place portable Node in .tools\\node / install Node.js."
        )

    frontend = root / "frontend"
    env = os.environ.copy()
    node_dir = find_node_dir(root)
    if node_dir:
        env["PATH"] = str(node_dir) + os.pathsep + env.get("PATH", "")

    # Relative /api uses Vite proxy (same-origin) — avoids browser CORS Network Error.
    (frontend / ".env").write_text("VITE_API_BASE_URL=/api\n", encoding="utf-8")

    if not (frontend / "node_modules").is_dir():
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        subprocess.check_call(
            [str(npm), "install"],
            cwd=str(frontend),
            env=env,
            creationflags=flags,
        )

    popen_managed(
        [str(npm), "run", "dev", "--", "--host", UI_HOST, "--port", str(UI_PORT)],
        frontend,
        env,
    )


def run_control_window(*, portable: bool) -> None:
    """Keep UI open until user closes it — then shut everything down."""
    import tkinter as tk
    from tkinter import font as tkfont

    local = local_ui_url(portable)
    lan = network_urls(portable)
    lan_text = "\n".join(f"  LAN: {u}" for u in lan[:3]) if lan else "  LAN: (no private IP detected)"
    mode = "Portable (API+UI on one port)" if portable else "Dev (Vite UI + API)"
    docs = f"http://127.0.0.1:{API_PORT}/docs"

    root = tk.Tk()
    root.title("Protection RCA")
    root.geometry("520x320")
    root.minsize(520, 300)
    root.resizable(False, False)
    root.configure(bg="#0f172a")

    title_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")
    body_font = tkfont.Font(family="Segoe UI", size=10)
    btn_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")

    tk.Label(
        root,
        text="Protection RCA is running",
        fg="#e2e8f0",
        bg="#0f172a",
        font=title_font,
    ).pack(pady=(20, 6))

    tk.Label(
        root,
        text=(
            f"{mode}\n\n"
            f"This PC: {local}\n"
            f"API docs: {docs}\n"
            f"{lan_text}\n\n"
            "Others on your network open a LAN URL above.\n"
            "Allow Windows Firewall for the port if asked.\n"
            "Close this window to shut everything down."
        ),
        fg="#94a3b8",
        bg="#0f172a",
        font=body_font,
        justify="left",
    ).pack(padx=24)

    def on_close() -> None:
        try:
            root.withdraw()
        except Exception:
            pass
        shutdown_all()
        try:
            root.destroy()
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", on_close)

    btn_wrap = tk.Frame(root, bg="#0f172a")
    btn_wrap.pack(pady=(12, 18))
    btn = tk.Label(
        btn_wrap,
        text="Stop & Close",
        bg="#b91c1c",
        fg="#ffffff",
        font=btn_font,
        padx=22,
        pady=10,
        cursor="hand2",
        relief="raised",
        bd=1,
        highlightthickness=0,
    )
    btn.pack()

    def _btn_enter(_: object) -> None:
        btn.configure(bg="#dc2626")

    def _btn_leave(_: object) -> None:
        btn.configure(bg="#b91c1c")

    def _btn_click(_: object) -> None:
        on_close()

    btn.bind("<Enter>", _btn_enter)
    btn.bind("<Leave>", _btn_leave)
    btn.bind("<Button-1>", _btn_click)

    root.mainloop()


def main() -> int:
    global _shutdown_done
    _shutdown_done = False
    _init_windows_job()
    atexit.register(shutdown_all)
    if os.name == "nt":
        try:
            signal.signal(signal.SIGTERM, lambda *_: shutdown_all())
            signal.signal(signal.SIGINT, lambda *_: shutdown_all())
        except Exception:
            pass

    root = root_dir()
    if not (root / "backend").is_dir() or not (root / "frontend").is_dir():
        error_box(
            "Protection RCA",
            "backend/ or frontend/ not found.\n"
            "Place ProtectionRCA.exe inside the protection-rca folder\n"
            "(or inside the portable share folder).",
        )
        return 1

    portable = frontend_dist_ready(root)
    force_dev = os.environ.get("PROTECTION_RCA_DEV", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if force_dev:
        portable = False
    # Force portable-only if env set
    if os.environ.get("PROTECTION_RCA_PORTABLE", "").strip().lower() in ("1", "true", "yes"):
        if not frontend_dist_ready(root):
            error_box(
                "Protection RCA",
                "PROTECTION_RCA_PORTABLE=1 but frontend\\dist\\index.html is missing.\n"
                "Run scripts\\build-portable-share.bat first.",
            )
            return 1
        portable = True

    try:
        start_backend(root, portable=portable)
        if not wait_port(API_CHECK_HOST, API_PORT, 60):
            raise RuntimeError(f"API did not start on port {API_PORT}.")
        if not portable:
            start_frontend(root)
            if not wait_port(UI_CHECK_HOST, UI_PORT, 120):
                raise RuntimeError(f"UI did not start on port {UI_PORT}.")
    except Exception as exc:
        shutdown_all()
        error_box("Protection RCA", str(exc))
        return 1

    open_url = local_ui_url(portable)
    threading.Timer(0.4, lambda: webbrowser.open(open_url)).start()
    try:
        run_control_window(portable=portable)
    finally:
        shutdown_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
