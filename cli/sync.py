import subprocess

from cli import (
    load_env, env, validate_poller_env,
    ssh_cmd, scp_file, die, PROJECT_DIR,
)

SERVICE_MAP = {
    "gateway": "ib-gateway",
    "ib-gateway": "ib-gateway",
    "novnc": "novnc",
    "vnc": "novnc",
    "caddy": "caddy",
    "relay": "webhook-relay",
    "webhook-relay": "webhook-relay",
    "poller": "poller",
    "poller2": "poller-2",
    "poller-2": "poller-2",
}


def _sync_local_files(droplet_ip):
    """Push local commits and pull them on the droplet."""
    # Must be on main branch
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True, cwd=PROJECT_DIR,
    ).stdout.strip()
    if branch != "main":
        die(f"Cannot sync: on branch '{branch}', switch to 'main' first")

    # Working tree must be clean
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, check=True, cwd=PROJECT_DIR,
    ).stdout.strip()
    if dirty:
        die("Cannot sync: uncommitted changes — commit or stash first")

    print("Pushing to origin...")
    subprocess.run(["git", "push"], check=True, cwd=PROJECT_DIR)

    print("Pulling on droplet...")
    ssh_cmd(droplet_ip, "cd /opt/ibkr-relay && git pull")


def run(args):
    load_env()

    droplet_ip = env("DROPLET_IP")
    profiles = ""
    if validate_poller_env("_2"):
        profiles = "poller2"

    if args.local_files:
        _sync_local_files(droplet_ip)

    build = "--build " if (args.build or args.local_files) else ""

    print("Pushing .env to droplet...")
    scp_file(PROJECT_DIR / ".env", "/opt/ibkr-relay/.env", droplet_ip)

    if not args.services:
        print(f"{'Rebuilding + restarting' if build else 'Restarting'} all services...")
        ssh_cmd(droplet_ip,
                f"cd /opt/ibkr-relay && COMPOSE_PROFILES='{profiles}' "
                f"docker compose up -d {build}--force-recreate")
    else:
        services = []
        for name in args.services:
            svc = SERVICE_MAP.get(name)
            if not svc:
                valid = ", ".join(sorted(set(SERVICE_MAP.keys())))
                die(f"Unknown service: {name}\nValid names: {valid}")
            services.append(svc)

        svc_str = " ".join(services)
        print(f"{'Rebuilding + restarting' if build else 'Restarting'}: {svc_str}...")
        ssh_cmd(droplet_ip,
                f"cd /opt/ibkr-relay && COMPOSE_PROFILES='{profiles}' "
                f"docker compose up -d {build}--force-recreate {svc_str}")

    print("Done.")
