import os
import shutil
import stat
from pathlib import Path

from cli.core import (
    config,
    deploy_mode,
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
    cfg = config()

    for cmd in ["terraform", "curl"]:
        if not shutil.which(cmd):
            die(f"'{cmd}' is required but not installed.")

    require_env(*cfg.required_env)

    # Export TF_VAR_* for Terraform
    for tf_name, env_key in cfg.terraform_vars.items():
        os.environ[f"TF_VAR_{tf_name}"] = env(env_key, "")

    terraform("init", "-input=false")
    terraform("apply", "-auto-approve", "-input=false")

    droplet_ip = terraform("output", "-raw", "droplet_ip", capture=True).stdout.strip()

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
    print(f"  SSH key:     {key_path}")
    print()
    print("  Next steps:")
    print(f"  1. Add DROPLET_IP={droplet_ip} to .env")
    if cfg.post_deploy_message:
        print(f"  2. {cfg.post_deploy_message}")
    print()


def _deploy_shared():
    """Deploy to an existing shared droplet (no Terraform)."""
    from cli.core.sync import _run_checks, _sync_local_files

    cfg = config()
    droplet_ip = env("DROPLET_IP")
    profiles = cfg.compose_profiles()

    _run_checks(skip_e2e=True)
    _sync_local_files(droplet_ip)

    print("Pushing .env to droplet...")
    scp_file(cfg.project_dir / ".env", f"{cfg.remote_dir}/.env", droplet_ip)

    print("Starting services (shared mode)...")
    ssh_cmd(droplet_ip,
            f"cd {cfg.remote_dir} && COMPOSE_PROFILES='{profiles}' "
            f"docker compose -f docker-compose.yml -f docker-compose.shared.yml "
            f"up -d --build --force-recreate")

    print()
    print("=" * 44)
    print("  Shared deployment complete!")
    print("=" * 44)
    print()


def run(args):
    load_env()

    mode = deploy_mode()

    if mode == "standalone":
        _deploy_standalone()
    else:
        _deploy_shared()
