from __future__ import annotations

import os
import platform
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def build_task_action(env_path: Path | None, write: bool, stored_settings: bool = False) -> str:
    project_root = _working_directory()
    command = subprocess.list2cmdline(_sync_command(env_path, write, stored_settings=stored_settings))
    return f'cmd.exe /c "cd /d {project_root} && {command}"'


def install_task(
    task_name: str,
    interval_minutes: int,
    env_path: Path | None,
    write: bool,
    print_only: bool,
    stored_settings: bool = False,
) -> None:
    system = platform.system().lower()
    if system == "windows":
        _install_windows_task(task_name, interval_minutes, env_path, write, print_only, stored_settings)
    elif system == "darwin":
        _install_launch_agent(task_name, interval_minutes, env_path, write, print_only, stored_settings)
    elif system == "linux":
        _install_systemd_timer(task_name, interval_minutes, env_path, write, print_only, stored_settings)
    else:
        raise RuntimeError(f"Unsupported scheduler platform: {platform.system()}")


def uninstall_task(task_name: str, print_only: bool) -> None:
    system = platform.system().lower()
    if system == "windows":
        _uninstall_windows_task(task_name, print_only)
    elif system == "darwin":
        _uninstall_launch_agent(task_name, print_only)
    elif system == "linux":
        _uninstall_systemd_timer(task_name, print_only)
    else:
        raise RuntimeError(f"Unsupported scheduler platform: {platform.system()}")


def _sync_command(env_path: Path | None, write: bool, stored_settings: bool = False) -> list[str]:
    if getattr(sys, "frozen", False):
        args = [sys.executable, "run-once"]
    else:
        args = [sys.executable, "-m", "wellpass_sync", "run-once"]
    if stored_settings:
        args.append("--stored-settings")
    elif env_path is not None:
        args.extend(["--env", str(env_path)])
    if write:
        args.append("--write")
    return args


def _working_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _install_windows_task(
    task_name: str,
    interval_minutes: int,
    env_path: Path | None,
    write: bool,
    print_only: bool,
    stored_settings: bool,
) -> None:
    action = build_task_action(env_path, write, stored_settings=stored_settings)
    command = [
        "schtasks.exe",
        "/Create",
        "/SC",
        "MINUTE",
        "/MO",
        str(interval_minutes),
        "/TN",
        task_name,
        "/TR",
        action,
        "/F",
    ]
    print("Task action:")
    print(action)
    if print_only:
        print("Print-only mode: not installing the task.")
        print("schtasks command:")
        print(subprocess.list2cmdline(command))
        return
    subprocess.run(command, check=True)
    print(f"Installed scheduled task: {task_name}")


def _uninstall_windows_task(task_name: str, print_only: bool) -> None:
    command = ["schtasks.exe", "/Delete", "/TN", task_name, "/F"]
    if print_only:
        print(subprocess.list2cmdline(command))
        return
    subprocess.run(command, check=True)
    print(f"Removed scheduled task: {task_name}")


def _install_launch_agent(
    task_name: str,
    interval_minutes: int,
    env_path: Path | None,
    write: bool,
    print_only: bool,
    stored_settings: bool,
) -> None:
    label = _task_label(task_name)
    plist_path = _launch_agent_path(task_name)
    project_root = _working_directory()
    log_dir = Path.home() / "Library" / "Logs"
    payload = {
        "Label": label,
        "ProgramArguments": _sync_command(env_path, write, stored_settings=stored_settings),
        "WorkingDirectory": str(project_root),
        "StartInterval": max(1, interval_minutes) * 60,
        "RunAtLoad": True,
        "StandardOutPath": str(log_dir / f"{label}.out.log"),
        "StandardErrorPath": str(log_dir / f"{label}.err.log"),
    }
    if print_only:
        print(f"LaunchAgent path: {plist_path}")
        print(plistlib.dumps(payload).decode("utf-8"))
        return

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(plistlib.dumps(payload))
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    print(f"Installed LaunchAgent: {label}")


def _uninstall_launch_agent(task_name: str, print_only: bool) -> None:
    plist_path = _launch_agent_path(task_name)
    if print_only:
        print(f"launchctl unload {plist_path}")
        print(f"rm {plist_path}")
        return
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    if plist_path.exists():
        plist_path.unlink()
    print(f"Removed LaunchAgent: {_task_label(task_name)}")


def _install_systemd_timer(
    task_name: str,
    interval_minutes: int,
    env_path: Path | None,
    write: bool,
    print_only: bool,
    stored_settings: bool,
) -> None:
    if not shutil.which("systemctl"):
        raise RuntimeError("systemd user timers require systemctl on PATH")

    label = _task_label(task_name)
    service_path = _systemd_user_dir() / f"{label}.service"
    timer_path = _systemd_user_dir() / f"{label}.timer"
    project_root = _working_directory()
    command = shlex.join(_sync_command(env_path, write, stored_settings=stored_settings))
    service = "\n".join(
        [
            "[Unit]",
            f"Description={task_name}",
            "",
            "[Service]",
            "Type=oneshot",
            f"WorkingDirectory={project_root}",
            f"ExecStart={command}",
            "",
        ]
    )
    timer = "\n".join(
        [
            "[Unit]",
            f"Description=Run {task_name}",
            "",
            "[Timer]",
            "OnBootSec=2min",
            f"OnUnitActiveSec={max(1, interval_minutes)}min",
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    )
    if print_only:
        print(f"systemd service path: {service_path}")
        print(service)
        print(f"systemd timer path: {timer_path}")
        print(timer)
        return

    service_path.parent.mkdir(parents=True, exist_ok=True)
    service_path.write_text(service, encoding="utf-8")
    timer_path.write_text(timer, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", timer_path.name], check=True)
    print(f"Installed systemd user timer: {timer_path.name}")


def _uninstall_systemd_timer(task_name: str, print_only: bool) -> None:
    label = _task_label(task_name)
    service_path = _systemd_user_dir() / f"{label}.service"
    timer_path = _systemd_user_dir() / f"{label}.timer"
    if print_only:
        print(f"systemctl --user disable --now {timer_path.name}")
        print(f"rm {service_path}")
        print(f"rm {timer_path}")
        return

    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "disable", "--now", timer_path.name], check=False)
    for path in (timer_path, service_path):
        if path.exists():
            path.unlink()
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    print(f"Removed systemd user timer: {timer_path.name}")


def _launch_agent_path(task_name: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_task_label(task_name)}.plist"


def _systemd_user_dir() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "systemd" / "user"
    return Path.home() / ".config" / "systemd" / "user"


def _task_label(task_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", task_name.lower()).strip("-")
    return f"com.mertcakir.{slug or 'wellpass-calendar-sync'}"
