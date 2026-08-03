# -*- coding: utf-8 -*-
"""导出诊断日志模块。被 ui.py 调用。纯 Python，无 DaVinci 依赖。"""

import zipfile, subprocess, os, time, platform, socket, json, sys as _sys


def export_debug_package(itm_dict, btn_export, error_state, log_fn, data_dir,
                          trial_days_fn, load_keys_fn, version_fn):
    """打包完整诊断信息 → 用户选择目录 → zip → Finder 弹出"""
    # ── 选目录 ──
    dest = ""
    if _sys.platform == "darwin":
        try:
            r = subprocess.run(
                ["osascript", "-e",
                 'POSIX path of (choose folder with prompt "选择导出位置")'],
                capture_output=True, text=True, encoding="utf-8", timeout=60)
            dest = r.stdout.strip()
        except Exception as e:
            log_fn(f"❌ 选目录失败: {e}")
    elif _sys.platform == "win32":
        try:
            # PowerShell folder picker — 兼容性好于 tkinter askdirectory
            ps_code = 'Add-Type -AssemblyName System.Windows.Forms; $f = New-Object System.Windows.Forms.FolderBrowserDialog; $f.ShowDialog(); $f.SelectedPath'
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps_code],
                               capture_output=True, text=True, timeout=60)
            dest = r.stdout.strip() if r.returncode == 0 else ""
        except Exception as e:
            log_fn(f"❌ 选目录失败: {e}")
    if not dest or not os.path.isdir(dest):
        itm_dict[btn_export].Text = "📋 导出日志" if not error_state["count"] else f'⚠️ {error_state["count"]} 个报错'
    # ── 文件名 ──
    now = time.localtime()
    from shared.license import get_machine_fingerprint
    fp = get_machine_fingerprint()[:8]
    zip_name = f"交付自检-诊断报告-{now.tm_mon:02d}{now.tm_mday:02d}-{now.tm_hour:02d}{now.tm_min:02d}-{fp}.zip"
    zip_path = os.path.join(dest, zip_name)

    def _add_str(zf, name, lines):
        zf.writestr(name, "\n".join(lines).encode("utf-8"))

    # ── 收集日志文件 ──
    log_entries = []
    logs_dir = os.path.join(data_dir, "logs")
    today = time.strftime("%Y-%m-%d")
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    if os.path.isdir(logs_dir):
        for f in sorted(os.listdir(logs_dir)):
            full = os.path.join(logs_dir, f)
            if not f.endswith(".log"):
                continue
            if today in f:
                log_entries.append((full, f"logs/ui-{today}.log"))
            elif yesterday in f:
                log_entries.append((full, f"logs/ui-{yesterday}.log"))
    # 拉取系统日志目录下的 launcher 日志
    from shared.cross_platform import app_logs_dir
    _wb_logs = app_logs_dir("交付自检工具")
    if os.path.isdir(_wb_logs):
        for f in sorted(os.listdir(_wb_logs)):
            if f.startswith("launcher_") and f.endswith(".log") and (today in f or yesterday in f):
                full = os.path.join(_wb_logs, f)
                log_entries.append((full, f"logs/{f}"))

    # ── info.txt ──
    info_lines = [
        "交付自检工具 · 完整诊断报告",
        f"版本: {version_fn()}",
        f"系统: {platform.platform()}",
        f"macOS: {platform.mac_ver()[0]}",
        f"主机名: {socket.gethostname()}",
        f"机器指纹: {fp}",
        f"Python: {_sys.version.split()[0]}",
        f"导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    # 附加完整指纹（方便 Base 搜索匹配）
    from shared.license import get_machine_fingerprint as _get_fp
    info_lines.append(f"完整指纹: {_get_fp()}")

    # ── license.txt: 授权完整快照 ──
    license_lines = ["# License 完整快照", ""]
    try:
        from shared.license import load_credential, BACKEND_URL as _be_url
        license_lines.append(f"FC端点: {_be_url or '未配置'}")
        cred = load_credential()
        if cred:
            p = cred.get("payload", {})
            license_lines.append(f"is_trial: {p.get('is_trial', True)}")
            tsd = p.get("trial_start_date", None)
            if tsd:
                from datetime import date as _dt
                d = trial_days_fn(tsd)
                license_lines.append(f"trial_start_date: ordinal={tsd} 剩余={d}天")
            else:
                license_lines.append("trial_start_date: 缺失")
            license_lines.append(f"expire_time: {p.get('expire_time', '缺失')}")
            license_lines.append(f"issue_time: {p.get('issue_time', '缺失')}")
            license_lines.append(f"offline_grant_end: {p.get('offline_grant_end', '缺失')}")
            license_lines.append(f"last_seen: {p.get('last_seen', '缺失')}")
            license_lines.append(f"activate_key: {p.get('activate_key', '')[:12] if p.get('activate_key') else '未激活'}")
            license_lines.append(f"signature: {cred.get('signature', '')[:32]}...")
        else:
            license_lines.append("凭据: 不存在（未初始化）")
    except Exception as e:
        license_lines.append(f"读取失败: {e}")

    # ── network.txt: FC 连通性诊断 ──
    net_lines = ["# 网络连通性诊断", ""]
    try:
        from shared.license import BACKEND_URL as _be_url2
        from urllib.parse import urlparse
        if _be_url2:
            host = urlparse(_be_url2).hostname or ""
            net_lines.append(f"FC端点: {_be_url2}")
            # DNS
            try:
                addr = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
                ip = addr[0][4][0] if addr else "解析失败"
                net_lines.append(f"DNS解析: {host} → {ip}")
            except Exception as e:
                net_lines.append(f"DNS解析: 失败 ({e})")
            # TCP
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((host, 443))
                s.close()
                net_lines.append(f"TCP 443: 可达")
            except Exception as e:
                net_lines.append(f"TCP 443: 不可达 ({e})")
            # curl
            try:
                r = subprocess.run(["curl", "--version"], capture_output=True, text=True, timeout=3)
                net_lines.append(f"curl: {r.stdout.split(chr(10))[0] if r.returncode==0 else '不可用'}")
            except Exception:
                net_lines.append("curl: 未安装")
            # FC API 测试
            try:
                r = subprocess.run(
                    ["curl", "-s", "-m", "10", "-X", "POST", _be_url2 + "/license",
                     "-H", "Content-Type: application/json",
                     "-d", '{"action":"init_trial","machine_fingerprint":"debug-test"}'],
                    capture_output=True, text=True, timeout=15)
                import json as _j
                d = _j.loads(r.stdout) if r.stdout else {}
                net_lines.append(f"FC API测试: {'ok' if d.get('status')=='ok' else d.get('msg','空响应')} (HTTP {r.returncode})")
            except Exception as e:
                net_lines.append(f"FC API测试: 失败 ({e})")
        else:
            net_lines.append("FC端点: 未配置")
    except Exception as e:
        net_lines.append(f"网络诊断失败: {e}")

    # ── activate.txt: 激活失败历史 ──
    activate_lines = ["# 激活失败记录", ""]
    try:
        af_path = os.path.join(data_dir, "activate_fails.jsonl")
        if os.path.exists(af_path):
            activate_lines.append(open(af_path, encoding="utf-8").read())
        else:
            activate_lines.append("无记录")
    except Exception as e:
        activate_lines.append(f"读取失败: {e}")

    # ── .env 快照（密钥已遮罩） ──
    env_lines = ["# .env 快照（密钥已遮罩）", ""]
    try:
        _env_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
            os.path.join(data_dir, ".env"),
        ]
        for _ep in _env_paths:
            if os.path.exists(_ep):
                env_lines.append(f"文件: {_ep}")
                env_lines.append("---")
                with open(_ep, encoding="utf-8") as _ef:
                    for _el in _ef:
                        _el = _el.strip()
                        if not _el or _el.startswith("#"):
                            env_lines.append(_el)
                        elif "=" in _el:
                            k, _, v = _el.partition("=")
                            if any(s in k.upper() for s in ("KEY", "SECRET", "PASSWORD", "TOKEN")):
                                env_lines.append(f"{k}={v[:6]}***{v[-4:]}" if len(v) > 10 else f"{k}=***")
                            else:
                                env_lines.append(_el)
                env_lines.append("")
                break
        else:
            env_lines.append("未找到 .env 文件")
    except Exception as e:
        env_lines.append(f".env 读取失败: {e}")

    state_lines = []
    state_lines.append(f'本次报错数: {error_state["count"]}')
    try:
        _keys = load_keys_fn()
        apis = [k for k in ("deepseek_key", "feishu_app_id", "feishu_secret") if _keys.get(k)]
        state_lines.append(f"API Key: {len(apis)}/3 已配置")
    except Exception:
        state_lines.append("API Key: 读取失败")

    # ── 错误日志（最近 20 条 ❌/⚠/异常/失败） ──
    error_lines = ["# 最近错误日志", ""]
    try:
        # 日志在 ~/Library/Logs/交付自检工具/交付自检工具/ (macOS) 或 %LOCALAPPDATA%/交付自检工具/Logs/ (Win)
        if sys.platform == "darwin":
            log_dir = os.path.join(os.path.expanduser("~/Library/Logs"), "交付自检工具", "交付自检工具")
        else:
            log_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "交付自检工具", "Logs")
        if os.path.isdir(log_dir):
            log_files = sorted(
                [f for f in os.listdir(log_dir) if f.endswith(".log")],
                key=lambda x: os.path.getmtime(os.path.join(log_dir, x)), reverse=True
            )
            keywords = ("❌", "⚠", "Error", "失败", "Traceback", "崩溃", "异常", "🛑")
            found = 0
            for lf in log_files[:3]:  # 最近 3 个日志文件
                try:
                    with open(os.path.join(log_dir, lf), encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if any(k in line for k in keywords):
                                error_lines.append(line.rstrip())
                                found += 1
                                if found >= 20:
                                    break
                    if found >= 20:
                        break
                except Exception:
                    pass
            if found == 0:
                error_lines.append("(未找到错误日志)")
        else:
            error_lines.append("(日志目录不存在)")
    except Exception as e:
        error_lines.append(f"(读取日志失败: {e})")

    # ── 写 zip ──
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for src, arcname in log_entries:
                try:
                    zf.write(src, arcname)
                except Exception:
                    pass
            _add_str(zf, "info.txt", info_lines)
            _add_str(zf, "license.txt", license_lines)
            _add_str(zf, "network.txt", net_lines)
            _add_str(zf, "activate.txt", activate_lines)
            _add_str(zf, "env.txt", env_lines)
            _add_str(zf, "state.txt", state_lines)
            _add_str(zf, "errors.txt", error_lines)
        if _sys.platform == "darwin":
            subprocess.run(["open", "-R", zip_path], check=False)
        else:
            subprocess.run(["explorer", "/select,", zip_path], check=False)
        log_fn(f"✅ 排错包已导出: {zip_name}")
        error_state["count"] = 0
        itm_dict[btn_export].Text = "✅ 已导出"
    except Exception as e:
        log_fn(f"❌ 导出失败: {e}")
        itm_dict[btn_export].Text = "📋 导出日志" if not error_state["count"] else f'⚠️ {error_state["count"]} 个报错'
