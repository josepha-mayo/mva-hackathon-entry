"""Read-only Windows storage checks before any controlled-data ingestion."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

GIB = 1024 ** 3
MINIMUM_FREE = {"minimal": 100 * GIB, "full": 650 * GIB}
SYNC_PARTS = {"onedrive", "dropbox", "google drive", "googledrive"}


@dataclass(frozen=True)
class PreflightResult:
    root: Path
    mode: str
    issues: tuple[str, ...]
    free_bytes: int | None

    @property
    def ok(self) -> bool:
        return not self.issues


def _powershell(script: str, env: dict[str, str]) -> tuple[int, str]:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if not executable:
        return 127, ""
    completed = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, **env},
        check=False,
    )
    return completed.returncode, completed.stdout.strip()


def _json_query(script: str, env: dict[str, str]) -> object | None:
    returncode, output = _powershell(script, env)
    if returncode != 0 or not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def _is_reparse(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return False
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return path.is_symlink() or bool(getattr(details, "st_file_attributes", 0) & flag)


def _existing_ancestor(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _bitlocker_ok(drive: str) -> bool:
    data = _json_query(
        "$v=Get-BitLockerVolume -MountPoint $env:MVA_PREFLIGHT_DRIVE -ErrorAction Stop; "
        "$v | Select-Object VolumeStatus,ProtectionStatus,EncryptionPercentage | "
        "ConvertTo-Json -Compress",
        {"MVA_PREFLIGHT_DRIVE": drive},
    )
    if not isinstance(data, dict):
        return False
    status = str(data.get("VolumeStatus", "")).replace(" ", "").lower()
    protection = str(data.get("ProtectionStatus", "")).lower()
    try:
        percentage = int(data.get("EncryptionPercentage", -1))
    except (TypeError, ValueError):
        percentage = -1
    return status == "fullyencrypted" and protection in {"on", "1"} and percentage == 100


def _volume_ok(drive: str) -> tuple[bool, str]:
    data = _json_query(
        "$letter=$env:MVA_PREFLIGHT_DRIVE.Substring(0,1); "
        "Get-Volume -DriveLetter $letter -ErrorAction Stop | "
        "Select-Object FileSystem,DriveType,HealthStatus | ConvertTo-Json -Compress",
        {"MVA_PREFLIGHT_DRIVE": drive},
    )
    if not isinstance(data, dict):
        return False, "volume metadata could not be verified"
    filesystem = str(data.get("FileSystem", ""))
    drive_type = str(data.get("DriveType", ""))
    health = str(data.get("HealthStatus", ""))
    ok = filesystem.upper() == "NTFS" and drive_type.lower() in {"fixed", "3"} and health.lower() == "healthy"
    return ok, f"filesystem={filesystem or 'unknown'}, type={drive_type or 'unknown'}, health={health or 'unknown'}"


def _acl_issues(target: Path, root_exists: bool) -> list[str]:
    data = _json_query(
        "$acl=Get-Acl -LiteralPath $env:MVA_PREFLIGHT_PATH -ErrorAction Stop; "
        "[pscustomobject]@{Protected=$acl.AreAccessRulesProtected;Owner=$acl.Owner;"
        "Access=@($acl.Access | ForEach-Object {[pscustomobject]@{"
        "Identity=$_.IdentityReference.Value;Rights=$_.FileSystemRights.ToString();"
        "Type=$_.AccessControlType.ToString();Inherited=$_.IsInherited}})} | "
        "ConvertTo-Json -Depth 5 -Compress",
        {"MVA_PREFLIGHT_PATH": str(target)},
    )
    if not isinstance(data, dict):
        return ["ACL and inheritance could not be verified"]

    whoami = subprocess.run(
        ["whoami"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace", check=False,
    ).stdout.strip().lower()
    allowed = {
        whoami,
        "builtin\\administrators",
        "nt authority\\system",
        "s-1-5-18",
        "s-1-5-32-544",
    }

    issues: list[str] = []
    if not root_exists:
        issues.append("private root does not exist and therefore has no protected ACL")
    if not bool(data.get("Protected")):
        issues.append("ACL inheritance is enabled")
    owner = str(data.get("Owner", "")).lower()
    if owner not in allowed:
        issues.append("owner is not the current user, SYSTEM, or Administrators")

    access = data.get("Access", [])
    if isinstance(access, dict):
        access = [access]
    current_has_full_control = False
    if not isinstance(access, list):
        return issues + ["ACL entries could not be parsed"]
    for entry in access:
        if not isinstance(entry, dict):
            issues.append("ACL entry could not be parsed")
            continue
        identity = str(entry.get("Identity", "")).lower()
        rule_type = str(entry.get("Type", "")).lower()
        rights = str(entry.get("Rights", "")).lower()
        if identity not in allowed:
            issues.append("ACL grants access to a principal outside the approved set")
        if rule_type != "allow":
            issues.append("ACL contains a non-Allow rule")
        if identity == whoami and "fullcontrol" in rights and rule_type == "allow":
            current_has_full_control = True
    if root_exists and not current_has_full_control:
        issues.append("current user lacks an explicit FullControl rule")
    return sorted(set(issues))


def preflight(root: Path, mode: str = "minimal") -> PreflightResult:
    root = root.expanduser().resolve(strict=False)
    issues: list[str] = []
    free_bytes: int | None = None

    if os.name != "nt":
        issues.append("storage preflight currently supports Windows only")
        return PreflightResult(root, mode, tuple(issues), free_bytes)
    if mode not in MINIMUM_FREE:
        issues.append(f"unknown mode: {mode}")
    if not root.anchor or root == Path(root.anchor):
        issues.append("private root must be a named directory, not a drive root")

    public_repo = Path(__file__).resolve().parents[1]
    try:
        if root == public_repo or root.is_relative_to(public_repo):
            issues.append("private root is inside the public repository")
    except ValueError:
        pass

    lowered_parts = {part.lower() for part in root.parts}
    if lowered_parts & SYNC_PARTS:
        issues.append("private root appears to be inside a sync-provider path")
    for name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer", "Dropbox"):
        value = os.environ.get(name)
        if not value:
            continue
        sync_root = Path(value).resolve(strict=False)
        try:
            if root == sync_root or root.is_relative_to(sync_root):
                issues.append("private root is inside a configured sync-provider path")
        except ValueError:
            pass

    for parent in (root, *root.parents):
        if (parent / ".git").exists():
            issues.append("private root is inside a Git working tree")
            break

    current = Path(root.anchor)
    for part in root.parts[1:]:
        current /= part
        if current.exists() and _is_reparse(current):
            issues.append("private path contains a symlink, junction, or reparse point")
            break

    drive = root.drive.upper()
    volume_ok, volume_detail = _volume_ok(drive)
    if not volume_ok:
        issues.append(f"target volume is not verified fixed, healthy NTFS ({volume_detail})")
    for protected_drive in sorted({Path.cwd().drive.upper(), drive}):
        if not protected_drive or not _bitlocker_ok(protected_drive):
            issues.append(f"BitLocker encryption/protection could not be verified for {protected_drive or 'a required drive'}")

    existing = _existing_ancestor(root)
    try:
        free_bytes = shutil.disk_usage(existing).free
        required = MINIMUM_FREE.get(mode, MINIMUM_FREE["full"])
        if free_bytes < required:
            issues.append(f"free space is below the {required // GIB} GiB {mode} threshold")
    except OSError:
        issues.append("free space could not be verified")

    issues.extend(_acl_issues(existing, root.exists() and root.is_dir()))
    if root.exists() and not root.is_dir():
        issues.append("private root exists but is not a directory")

    return PreflightResult(root, mode, tuple(sorted(set(issues))), free_bytes)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.environ.get("MVA_PRIVATE_ROOT"))
    parser.add_argument("--mode", choices=sorted(MINIMUM_FREE), default="minimal")
    args = parser.parse_args()
    if not args.root:
        print("NO-GO: set MVA_PRIVATE_ROOT or pass --root")
        return 2
    result = preflight(Path(args.root), args.mode)
    if result.issues:
        print(f"NO-GO: controlled-storage preflight failed ({result.mode} mode)")
        for issue in result.issues:
            print(f"- {issue}")
        return 3
    print(f"GO: controlled-storage preflight passed ({result.mode} mode)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
