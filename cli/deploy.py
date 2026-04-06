import os
import shutil
import stat
from pathlib import Path

from cli import (
    PROJECT_DIR,
    PROJECT_NAME,
    REMOTE_DIR,
    compose_profiles,
    die,
    env,
    load_env,
    require_env,
    scp_file,
    ssh_cmd,
    ssh_key_path,
    terraform,
)


def _deploy_standalone():
    """Deploy via Terraform (own droplet)."""
    for cmd in ["terraform", "curl"]:
        if not shutil.which(cmd):
            die(f"'{cmd}' is required but not installed.")

    require_env(
        "DO_API_TOKEN", "TWS_USERID", "TWS_PASSWORD",
        "VNC_SERVER_PASSWORD", "WEBHOOK_SECRET",
        "IBKR_FLEX_TOKEN", "IBKR_FLEX_QUERY_ID",
    )

    # Export TF_VAR_* for Terraform
    tf = {
        "do_token": env("DO_API_TOKEN"),
        "tws_userid": env("TWS_USERID"),
        "tws_password": env("TWS_PASSWORD"),
        "trading_mode": env("TRADING_MODE", "paper"),
        "vnc_password": env("VNC_SERVER_PASSWORD"),
        "webhook_url": env("TARGET_WEBHOOK_URL", ""),
        "webhook_secret": env("WEBHOOK_SECRET"),
        "flex_token": env("IBKR_FLEX_TOKEN"),
        "flex_query_id": env("IBKR_FLEX_QUERY_ID"),
        "poll_interval": env("POLL_INTERVAL_SECONDS", "600"),
        "time_zone": env("TIME_ZONE", "America/New_York"),
        "java_heap_size": env("JAVA_HEAP_SIZE", "768"),
        # Poller-2 (optional)
        "flex_token_2": env("IBKR_FLEX_TOKEN_2", ""),
        "flex_query_id_2": env("IBKR_FLEX_QUERY_ID_2", ""),
        "webhook_url_2": env("TARGET_WEBHOOK_URL_2", ""),
        "webhook_secret_2": env("WEBHOOK_SECRET_2", ""),
        "poll_interval_2": env("POLL_INTERVAL_SECONDS_2", "600"),
    }
    for key, val in tf.items():
        os.environ[f"TF_VAR_{key}"] = val

    # Validate poller-2 config (sets COMPOSE_PROFILES if configured)
    compose_profiles()

    terraform("init", "-input=false")
    terraform("apply", "-auto-approve", "-input=false")

    droplet_ip = terraform("output", "-raw", "droplet_ip", capture=True).stdout.strip()
    vnc_url = terraform("output", "-raw", "vnc_url", capture=True).stdout.strip()

    # Save SSH key for subsequent sync/ssh commands
    key = terraform("output", "-raw", "ssh_private_key", capture=True).stdout
    key_path = Path(ssh_key_path())
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(key)
    key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600

    print()
    print("=" * 44)
    print("  Deployment complete!")
    print("=" * 44)
    print()
    print(f"  Droplet IP:  {droplet_ip}")
    print(f"  VNC URL:     {vnc_url}")
    print(f"  SSH key:     {key_path}")
    print()
    print("  Next steps:")
    print(f"  1. Add DROPLET_IP={droplet_ip} to .env")
    print("  2. Open the VNC URL and complete 2FA")
    print()


def _deploy_shared():
    """Deploy to an existing shared droplet (no Terraform)."""
    from cli.sync import _run_checks, _sync_local_files

    droplet_ip = env("DROPLET_IP")
    profiles = compose_profiles()

    _run_checks(skip_e2e=True)
    _sync_local_files(droplet_ip)

    print("Pushing .env to droplet...")
    scp_file(PROJECT_DIR / ".env", f"{REMOTE_DIR}/.env", droplet_ip)

    print("Starting services (shared mode)...")
    ssh_cmd(droplet_ip,
            f"cd {REMOTE_DIR} && COMPOSE_PROFILES='{profiles}' "
            f"docker compose -f docker-compose.yml -f docker-compose.shared.yml "
            f"up -d --build --force-recreate")

    print()
    print("=" * 44)
    print("  Shared deployment complete!")
    print("=" * 44)
    print()
    print("  Deploy Caddy snippets from the host project to enable routing:")
    print("    infra/caddy/sites/ibkr.caddy   → TRADE_DOMAIN /ibkr/* routes")
    print("    infra/caddy/domains/ibkr-vnc.caddy → VNC_DOMAIN site block")
    print()


def run(args):
    load_env()

    from cli import deploy_mode
    mode = deploy_mode()

    if mode == "standalone":
        _deploy_standalone()
    else:
        _deploy_shared()
