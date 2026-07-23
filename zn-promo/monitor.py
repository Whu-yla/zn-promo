#!/usr/bin/env python3
"""
服务监控引擎 - 检查服务状态、触发告警
"""
import json
import os
import subprocess
import time
import logging
import smtplib
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

BASE_DIR = Path("/data/hermes/zn-promo/zn-promo")
STATUS_FILE = BASE_DIR / "monitor_status.json"
CONFIG_FILE = BASE_DIR / "monitor_config.json"
LOG_FILE = BASE_DIR / "monitor.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("monitor")

SERVICES = [
    {"id": "nginx", "name": "Nginx Web 服务器", "type": "systemd", "service": "nginx"},
    {"id": "zn-promo-api", "name": "合作登记系统 API", "type": "systemd", "service": "zn-promo-api", "port": 8000},
    {"id": "zn-promo-watchdog", "name": "保活监控守护进程", "type": "systemd", "service": "zn-promo-watchdog"},
    {"id": "feishu-warren", "name": "飞书Bot - 沃伦·巴菲特", "type": "systemd", "service": "feishu-gateway-warren"},
    {"id": "hermes-gateway", "name": "飞书Bot - 哆啦A梦", "type": "systemd_user", "service": "hermes-gateway"},
    {"id": "website", "name": "网站访问 (www.szkj.site)", "type": "http", "url": "https://www.szkj.site"},
    {"id": "api", "name": "API 接口", "type": "http", "url": "https://www.szkj.site/api/records"},
    {"id": "disk", "name": "磁盘空间", "type": "disk", "threshold": 90},
    {"id": "memory", "name": "内存使用率", "type": "memory", "threshold": 90},
]

DEFAULT_CONFIG = {
    "email": {
        "enabled": False,
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
        "smtp_ssl": True,
        "username": "",
        "password": "",
        "from_addr": "",
        "to_addrs": []
    },
    "sms": {
        "enabled": False,
        "provider": "aliyun",
        "api_url": "",
        "api_key": "",
        "api_secret": "",
        "aliyun_sign_name": "",
        "aliyun_template_code": "",
        "phone_numbers": []
    },
    "global": {
        "check_interval": 30,
        "alert_cooldown": 300
    }
}

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
                # merge with defaults for missing keys
                for k, v in DEFAULT_CONFIG.items():
                    if k not in config:
                        config[k] = v
                return config
        except:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def load_status():
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"services": {}, "last_updated": "", "history": []}

def save_status(status):
    with open(STATUS_FILE, 'w') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

def fix_service(svc_id):
    """Try to fix a service by restarting it"""
    for svc in SERVICES:
        if svc["id"] != svc_id:
            continue
        try:
            if svc["type"] == "systemd":
                r = subprocess.run(["systemctl", "restart", svc["service"]], capture_output=True, text=True, timeout=30)
                if r.returncode == 0:
                    return True, f"{svc['name']} 重启成功"
                else:
                    return False, f"重启失败: {r.stderr.strip()}"
            elif svc["type"] == "systemd_user":
                env = os.environ.copy()
                env["XDG_RUNTIME_DIR"] = "/run/user/0"
                r = subprocess.run(["systemctl", "--user", "restart", svc["service"]], capture_output=True, text=True, timeout=30, env=env)
                if r.returncode == 0:
                    return True, f"{svc['name']} 重启成功"
                else:
                    return False, f"重启失败: {r.stderr.strip()}"
            else:
                return False, f"{svc['name']} 不支持一键修复"
        except Exception as e:
            return False, str(e)
    return False, "未找到服务"

def check_systemd(service_name):
    try:
        r = subprocess.run(["systemctl", "is-active", service_name], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() == "active", r.stdout.strip()
    except Exception as e:
        return False, str(e)

def check_systemd_user(service_name):
    try:
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/0"
        r = subprocess.run(["systemctl", "--user", "is-active", service_name],
                          capture_output=True, text=True, timeout=10, env=env)
        if r.stdout.strip() == "active":
            return True, "active"
        # Fallback: check process
        r2 = subprocess.run(["pgrep", "-f", service_name], capture_output=True, timeout=5)
        return r2.returncode == 0, "active (by process)" if r2.returncode == 0 else "inactive"
    except Exception as e:
        return False, str(e)

def check_http(url):
    try:
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "5", url],
                          capture_output=True, text=True, timeout=10)
        code = r.stdout.strip()
        return code.startswith("2") or code == "301" or code == "302" or code == "401" or code == "403", f"HTTP {code}"
    except Exception as e:
        return False, str(e)

def check_port(port):
    try:
        r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
        return f":{port}" in r.stdout, f"端口 {port}"
    except Exception as e:
        return False, str(e)

def check_disk(threshold):
    try:
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        line = r.stdout.strip().split("\n")[1]
        parts = line.split()
        used_pct = int(parts[4].replace("%", ""))
        return used_pct < threshold, f"已用 {used_pct}%"
    except Exception as e:
        return False, str(e)

def check_memory(threshold):
    try:
        r = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split("\n")
        parts = lines[1].split()
        total = int(parts[1])
        available = int(parts[6])
        used_pct = round((total - available) / total * 100)
        return used_pct < threshold, f"已用 {used_pct}%"
    except Exception as e:
        return False, str(e)

def check_service(svc):
    svc_id = svc["id"]
    svc_type = svc["type"]
    
    try:
        if svc_type == "systemd":
            ok, detail = check_systemd(svc["service"])
        elif svc_type == "systemd_user":
            ok, detail = check_systemd_user(svc["service"])
        elif svc_type == "http":
            ok, detail = check_http(svc["url"])
        elif svc_type == "port":
            ok, detail = check_port(svc["port"])
        elif svc_type == "disk":
            ok, detail = check_disk(svc["threshold"])
        elif svc_type == "memory":
            ok, detail = check_memory(svc["threshold"])
        else:
            ok, detail = False, "未知检查类型"
    except Exception as e:
        ok, detail = False, str(e)
    
    return {
        "id": svc_id,
        "name": svc["name"],
        "status": "up" if ok else "down",
        "detail": detail,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def send_email_alert(config, subject, body):
    email_cfg = config.get("email", {})
    if not email_cfg.get("enabled") or not email_cfg.get("to_addrs"):
        return False
    
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = email_cfg["from_addr"]
        msg["To"] = ", ".join(email_cfg["to_addrs"])
        
        if email_cfg.get("smtp_ssl"):
            with smtplib.SMTP_SSL(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
                server.login(email_cfg["username"], email_cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
                server.starttls()
                server.login(email_cfg["username"], email_cfg["password"])
                server.send_message(msg)
        logger.info(f"告警邮件已发送至 {email_cfg['to_addrs']}")
        return True
    except Exception as e:
        logger.error(f"发送邮件失败: {e}")
        return False

def send_sms_alert(config, content):
    sms_cfg = config.get("sms", {})
    if not sms_cfg.get("enabled") or not sms_cfg.get("phone_numbers"):
        return False
    
    try:
        if sms_cfg.get("provider") == "aliyun":
            from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
            from alibabacloud_dysmsapi20170525 import models as dysmsapi_models
            from alibabacloud_tea_openapi import models as open_api_models
            
            access_key_id = sms_cfg.get("api_key", "")
            access_key_secret = sms_cfg.get("api_secret", "")
            sign_name = sms_cfg.get("aliyun_sign_name", "")
            template_code = sms_cfg.get("aliyun_template_code", "")
            
            if not all([access_key_id, access_key_secret, sign_name, template_code]):
                logger.warning("阿里云短信配置不完整，跳过发送")
                return False
            
            api_config = open_api_models.Config(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret
            )
            api_config.endpoint = 'dysmsapi.aliyuncs.com'
            client = DysmsapiClient(api_config)
            
            # Template param: pass the alert content as a variable
            import json as _json
            from datetime import datetime as _dt
            _now_str = _dt.now().strftime("%m月%d日 %H:%M")
            template_param = _json.dumps({"name": content[:50], "time": _now_str}, ensure_ascii=False)
            
            request = dysmsapi_models.SendSmsRequest(
                phone_numbers=",".join(sms_cfg["phone_numbers"]),
                sign_name=sign_name,
                template_code=template_code,
                template_param=template_param
            )
            response = client.send_sms(request)
            body = response.body
            if body.code == "OK":
                logger.info(f"阿里云短信发送成功: {body.biz_id}")
            else:
                logger.warning(f"阿里云短信发送失败: code={body.code}, message={body.message}")
            return body.code == "OK"
        
        elif sms_cfg.get("provider") == "custom" and sms_cfg.get("api_url"):
            data = {
                "phone": ",".join(sms_cfg["phone_numbers"]),
                "content": content,
                "key": sms_cfg.get("api_key", "")
            }
            if sms_cfg.get("api_secret"):
                data["secret"] = sms_cfg["api_secret"]
            encoded = urllib.parse.urlencode(data).encode()
            req = urllib.request.Request(sms_cfg["api_url"], data=encoded)
            urllib.request.urlopen(req, timeout=10)
            logger.info(f"自定义短信已发送至 {sms_cfg['phone_numbers']}")
            return True
        
        return True
    except Exception as e:
        logger.error(f"发送短信失败: {e}")
        return False

def run_checks():
    config = load_config()
    status = load_status()
    
    # Initialize
    if "services" not in status:
        status["services"] = {}
    if "history" not in status:
        status["history"] = []
    
    # Check all services
    for svc in SERVICES:
        result = check_service(svc)
        svc_id = svc["id"]
        prev = status["services"].get(svc_id, {})
        prev_status = prev.get("status", "up")
        
        # Update status
        status["services"][svc_id] = result
        
        # Alert on transition up→down
        if prev_status == "up" and result["status"] == "down":
            now = time.time()
            last_alert = prev.get("last_alert_at", 0)
            cooldown = config.get("global", {}).get("alert_cooldown", 300)
            
            if now - last_alert > cooldown:
                alert_msg = f"[服务告警] {result['name']} 异常！\n状态: {result['detail']}\n时间: {result['checked_at']}"
                logger.warning(alert_msg)
                
                # Save alert time
                status["services"][svc_id]["last_alert_at"] = now
                status["services"][svc_id]["last_alert_time"] = result["checked_at"]
                
                # Record in history
                status["history"].append({
                    "type": "alert",
                    "service": svc_id,
                    "name": result["name"],
                    "message": f"{result['name']} 服务异常: {result['detail']}",
                    "time": result["checked_at"]
                })
                
                # Send alerts
                send_email_alert(config, f"[服务监控] {result['name']} 异常", alert_msg)
                send_sms_alert(config, f"【服务告警】{result['name']}异常:{result['detail']}")
        
        # Recovery notification
        if prev_status == "down" and result["status"] == "up":
            recovery_msg = f"[服务恢复] {result['name']} 已恢复正常"
            logger.info(recovery_msg)
            status["history"].append({
                "type": "recovery",
                "service": svc_id,
                "name": result["name"],
                "message": f"{result['name']} 已恢复正常",
                "time": result["checked_at"]
            })
            send_email_alert(config, f"[服务监控] {result['name']} 已恢复", recovery_msg)
    
    # Clean up history (keep last 500)
    if len(status["history"]) > 500:
        status["history"] = status["history"][-500:]
    
    status["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status["summary"] = {
        "total": len(SERVICES),
        "up": sum(1 for s in status["services"].values() if s["status"] == "up"),
        "down": sum(1 for s in status["services"].values() if s["status"] == "down")
    }
    
    save_status(status)
    return status

def run_once():
    """Run a single check cycle"""
    result = run_checks()
    summary = result.get("summary", {})
    print(f"[{result['last_updated']}] 服务状态: {summary.get('up', 0)} up / {summary.get('down', 0)} down")
    for svc_id, svc in result["services"].items():
        icon = "✅" if svc["status"] == "up" else "❌"
        print(f"  {icon} {svc['name']}: {svc['detail']}")

def run_loop():
    """Run continuously"""
    config = load_config()
    interval = config.get("global", {}).get("check_interval", 30)
    logger.info(f"服务监控引擎启动，检查间隔 {interval} 秒")
    
    while True:
        try:
            run_checks()
        except Exception as e:
            logger.error(f"检查循环异常: {e}")
        time.sleep(interval)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_once()
    else:
        run_loop()