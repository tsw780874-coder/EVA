#!/usr/bin/env python3
"""EVA 一键部署到阿里云 — Python 自动化版
用法: python deploy_to_aliyun.py
"""

import os
import sys
import getpass
import tarfile
import tempfile
import time
from io import BytesIO

try:
    import paramiko
except ImportError:
    print("正在安装 paramiko...")
    os.system(f"{sys.executable} -m pip install paramiko -q")
    import paramiko

SERVER = "39.96.65.233"
USER = "root"
REMOTE_DIR = "/opt/eva"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

EXCLUDES = {
    ".git", ".venv", "venv", "node_modules", ".next",
    "__pycache__", "*.pyc", ".idea", ".claude", "memory",
    ".pytest_cache", "*.tar.gz", "*.zip", "backend/eva_dev.db",
    "docker-data", ".env",
}

PUBKEY_PATH = os.path.expanduser("~/.ssh/id_rsa.pub")


def step(msg):
    print(f"\n\033[1;32m[{step.counter}/{step.total}]\033[0m {msg}")
    step.counter += 1


def main():
    step.total = 6
    step.counter = 1

    # 1. Get password
    print("\033[1;34m========================================\033[0m")
    print("\033[1;34m  EVA 一键部署 — 阿里云\033[0m")
    print("\033[1;34m========================================\033[0m")
    password = getpass.getpass(f"\n请输入 {USER}@{SERVER} 的密码: ")

    # 2. Connect
    step("连接到服务器...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(SERVER, username=USER, password=password, timeout=10)
    except Exception as e:
        print(f"\033[1;31m✗ 连接失败: {e}\033[0m")
        sys.exit(1)

    # 3. Install SSH key
    step("安装 SSH 公钥...")
    if os.path.exists(PUBKEY_PATH):
        with open(PUBKEY_PATH) as f:
            pubkey = f.read().strip()
        client.exec_command("mkdir -p ~/.ssh && chmod 700 ~/.ssh")
        sftp = client.open_sftp()
        try:
            # Read existing keys
            try:
                with sftp.open("/root/.ssh/authorized_keys", "r") as ak:
                    existing = ak.read().decode()
            except FileNotFoundError:
                existing = ""

            if pubkey not in existing:
                new_keys = (existing + "\n" + pubkey).strip() + "\n"
                with sftp.open("/root/.ssh/authorized_keys", "w") as ak:
                    ak.write(new_keys)
                print("  → SSH 密钥已安装")
            else:
                print("  → SSH 密钥已存在")
        finally:
            sftp.close()
        client.exec_command("chmod 600 ~/.ssh/authorized_keys")
    else:
        print("  ⚠️ 未找到公钥，跳过")

    # 4. Create remote directory
    step("准备远程目录...")
    client.exec_command(f"mkdir -p {REMOTE_DIR}")

    # 5. Package and upload
    step("打包项目文件...")
    tarball_data = BytesIO()
    with tarfile.open(fileobj=tarball_data, mode="w:gz") as tar:
        for root, dirs, files in os.walk(PROJECT_DIR):
            # Filter excluded dirs
            dirs[:] = [d for d in dirs if d not in EXCLUDES and not d.startswith(".")]

            rel_root = os.path.relpath(root, PROJECT_DIR)
            for fname in files:
                # Check file-level excludes
                skip = False
                for ex in EXCLUDES:
                    if ex.startswith("*.") and fname.endswith(ex[1:]):
                        skip = True
                        break
                    if fname == ex:
                        skip = True
                        break
                if skip:
                    continue

                fpath = os.path.join(root, fname)
                arcname = os.path.join(rel_root, fname) if rel_root != "." else fname
                tar.add(fpath, arcname=arcname)

    tarball_data.seek(0)
    size_mb = len(tarball_data.getvalue()) / 1024
    print(f"  → 打包大小: {size_mb:.0f} KB")

    step(f"上传到服务器 ({size_mb:.0f} KB)...")
    sftp = client.open_sftp()
    try:
        sftp.putfo(tarball_data, f"{REMOTE_DIR}/eva-deploy.tar.gz")
    finally:
        sftp.close()
    print("  → 上传完成")

    # 6. Extract and deploy
    step("服务器端部署...")
    commands = f"""
cd {REMOTE_DIR}
tar -xzf eva-deploy.tar.gz
rm -f eva-deploy.tar.gz
test -f .env || cp .env.production .env
docker compose -f docker-compose.light.yml down --remove-orphans 2>/dev/null || true
docker compose -f docker-compose.light.yml up -d --build 2>&1
"""
    stdin, stdout, stderr = client.exec_command(commands)
    # Stream output
    for line in iter(stdout.readline, ""):
        print(f"  {line.rstrip()}")
    exit_code = stdout.channel.recv_exit_status()

    if exit_code != 0:
        print(f"\033[1;33m⚠ docker-compose 退出码: {exit_code}\033[0m")
        for line in stderr:
            print(f"  \033[1;31m{line.rstrip()}\033[0m")

    # 7. Health check
    step("等待服务就绪...")
    for i in range(30):
        time.sleep(5)
        stdin, stdout, _ = client.exec_command(
            "curl -sf http://localhost/health 2>/dev/null"
        )
        if stdout.channel.recv_exit_status() == 0:
            print("\n\033[1;32m========================================\033[0m")
            print("\033[1;32m  ✅ EVA 部署成功！\033[0m")
            print("\033[1;32m========================================\033[0m")
            print(f"\n  访问地址: \033[1;36mhttp://{SERVER}\033[0m")
            print(f"  健康检查: \033[1;36mhttp://{SERVER}/health\033[0m")
            print("\n  默认账号:")
            print("    管理员: admin@eva.com / admin123")
            print("    体验用户: user@eva.com / user123")
            print()
            break
        print(".", end="", flush=True)
    else:
        print("\n\033[1;33m⚠ 健康检查超时，请手动验证\033[0m")
        stdin, stdout, _ = client.exec_command("docker compose -f docker-compose.light.yml ps")
        print(stdout.read().decode())

    client.close()
    print("\n\033[1;34m部署流程完成\033[0m")


if __name__ == "__main__":
    main()
