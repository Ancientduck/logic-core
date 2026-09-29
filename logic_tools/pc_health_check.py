import os
import json
import platform
import psutil
import datetime
import subprocess

# Safely try to import wmi (requires 'pip install wmi pywin32')
try:
    import wmi
except ImportError:
    wmi = None

_output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "health_check_output.txt")

def log(*args):
    """Prints to console and writes to the output file simultaneously."""
    msg = " ".join(str(a) for a in args)
    print(msg)
    with open(_output_path, 'a', encoding='utf-8') as f:
        f.write(msg + "\n")

def line(k, v):
    log(f"{k}: {v}")

def warn(issues, msg):
    issues.append(msg)

def get_event_log(log_name, eid, hours=48):
    if wmi is None:
        return "WMI module not installed. Run 'pip install wmi'"
    try:
        c = wmi.WMI()
        # Use UTC time to be timezone-safe for WMI
        since_utc = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
        wmi_time = since_utc.strftime('%Y%m%d%H%M%S.000000+000')
        
        # Native WMI filtering (incredibly fast compared to querying all events)
        wql = (f"SELECT * FROM Win32_NTLogEvent "
               f"WHERE Logfile='{log_name}' AND EventCode={eid} "
               f"AND TimeWritten >= '{wmi_time}'")
        return list(c.query(wql))
    except Exception as e:
        return f"Error querying WMI: {e}"

def check_whea(issues):
    log("\n=== Hardware Errors (WHEA) ===")
    whea = get_event_log("System", 19, 48)
    if isinstance(whea, str):
        log(f"  {whea}")
    elif not whea:
        log("  No WHEA errors in last 48h. Hardware appears stable.")
    else:
        for e in whea[:5]:
            # Safely handle None messages
            msg = (e.Message or "No message")[:100]
            warn(issues, f"WHEA hardware error: {msg}")
        log(f"  {len(whea)} WHEA errors found. Hardware fault suspected.")

def check_kernel_power(issues):
    log("\n=== Unexpected Shutdowns ===")
    kp = get_event_log("System", 41, 48)
    if isinstance(kp, str):
        log(f"  {kp}")
    elif not kp:
        log("  No unexpected shutdowns in last 48h.")
    else:
        for e in kp[:5]:
            warn(issues, f"Kernel-Power 41: unexpected shutdown at {e.TimeWritten}")
        log(f"  {len(kp)} unexpected shutdown events.")

def check_gpu_driver(issues):
    log("\n=== GPU Driver ===")
    if wmi is None:
        log("  WMI module not installed")
        return
    try:
        c = wmi.WMI()
        # Win32_VideoController is vendor-agnostic (Works for AMD, Intel, NVIDIA)
        for gpu in c.Win32_VideoController():
            name = gpu.Name or "Unknown"
            drv = gpu.DriverVersion or "Unknown"
            status = gpu.Status or "Unknown"
            line("Model", name)
            line("Driver", drv)
            line("Status", status)
            if gpu.ConfigManagerErrorCode and gpu.ConfigManagerErrorCode != 0:
                warn(issues, f"GPU {name} has device manager error code {gpu.ConfigManagerErrorCode}")
    except Exception as e:
        log(f"  GPU check unavailable: {e}")

def check_display_reset(issues):
    log("\n=== Display Driver Resets ===")
    resets = get_event_log("System", 4101, 48)
    if isinstance(resets, str):
        log(f"  {resets}")
    elif not resets:
        log("  No display driver resets in last 48h.")
    else:
        for e in resets[:5]:
            msg = (e.Message or "No message")[:100]
            warn(issues, f"Display driver reset: {msg}")
        log(f"  {len(resets)} driver resets found.")

def check_smart(issues):
    log("\n=== Disk S.M.A.R.T. ===")
    try:
        ps_cmd = "Get-PhysicalDisk | Select-Object FriendlyName,HealthStatus,OperationalStatus,Size | ConvertTo-Json -Compress"
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        out = res.stdout.strip()
        disks = json.loads(out) if out else []
        
        # Handle single disk output (JSON object instead of array)
        if isinstance(disks, dict):
            disks = [disks]
            
        if not disks:
            log("  No disks found.")
            return
            
        for d in disks:
            model = d.get("FriendlyName", "Unknown")
            status = d.get("HealthStatus", "Unknown")
            size = int(d.get("Size", 0) or 0)
            size_gb = size / 1024**3
            line(model, f"{status} ({size_gb:.0f} GB)")
            if status != "Healthy":
                warn(issues, f"Disk {model} health: {status}")
    except Exception as e:
        log(f"  S.M.A.R.T. check unavailable: {e}")

def check_disk_space(issues):
    log("\n=== Disk Space ===")
    try:
        for part in psutil.disk_partitions(all=False):
            if part.fstype:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    total_gb = usage.total / 1024**3
                    free_gb = usage.free / 1024**3
                    percent = usage.percent
                    line(f"Drive {part.mountpoint}", f"{free_gb:.1f} GB free / {total_gb:.1f} GB total ({percent}% used)")
                    if percent > 90:
                        warn(issues, f"Disk {part.mountpoint} is {percent}% full!")
                except OSError:
                    pass # Skip empty CD-ROMs or unmounted drives
    except Exception as e:
        log(f"  Disk space check unavailable: {e}")

def check_minidumps(issues):
    log("\n=== BSOD Minidumps ===")
    try:
        dump_dir = r"C:\Windows\Minidump"
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=48)
        dumps = []
        if os.path.exists(dump_dir):
            for f in os.listdir(dump_dir):
                fp = os.path.join(dump_dir, f)
                if f.endswith(".dmp") and os.path.getmtime(fp) > cutoff.timestamp():
                    dumps.append(f)
        if not dumps:
            log("  No recent BSOD minidumps found in last 48h.")
        else:
            warn(issues, f"Found {len(dumps)} recent BSOD minidump(s): {', '.join(dumps)}")
    except PermissionError:
        log("  Skipped: Reading minidumps requires admin privileges.")
    except Exception as e:
        log(f"  Minidump check unavailable: {e}")

def check_chkdsk(issues):
    log("\n=== Disk Integrity (read-only) ===")
    try:
        res = subprocess.run(
            ["chkdsk", "C:"],
            capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace"
        )
        out = (res.stdout or "") + (res.stderr or "")
        lines = out.strip().splitlines()
        
        # Print the summary (last 15 lines) to avoid massive log spam
        summary = "\n".join(lines[-15:])
        log("  " + summary.replace("\n", "\n  "))
        
        if "has no problems" in out.lower() or "did not find any problems" in out.lower():
            log("  C: drive integrity OK.")
        elif "access denied" in out.lower() or "elevated mode" in out.lower():
            log("  Skipped: chkdsk requires admin privileges for this drive.")
        else:
            for l in lines:
                if "error" in l.lower() or "problem" in l.lower():
                    warn(issues, f"chkdsk: {l.strip()}")
    except Exception as e:
        log(f"  chkdsk unavailable: {e}")

def main():
    # Reset output file at the start of the run
    issues = []
    log("=== System ===")
    line("OS", f"{platform.system()} {platform.release()}")
    line("Node", platform.node())
    uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
    line("Uptime", str(uptime).split('.')[0])

    check_whea(issues)
    check_kernel_power(issues)
    check_gpu_driver(issues)
    check_display_reset(issues)
    check_smart(issues)
    check_disk_space(issues)
    check_minidumps(issues)
    check_chkdsk(issues)

    log("\n=== Verdict ===")
    if not issues:
        log("No hardware or driver faults detected. System is healthy.")
    else:
        log("Issues detected:")
        for i in issues:
            log(f"  - {i}")
    log("\nDiagnostic complete.")

if __name__ == "__main__":
    main()