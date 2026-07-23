from fastapi import FastAPI, HTTPException, Depends, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from typing import Optional, List
import sqlite3
import os
import csv
import io
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SECRET_KEY = "your-secret-key-here-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI(title="中南电力数智科技合作登记系统", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "cooperation.db"

ADMIN_CREDENTIALS = {
    "admin": pwd_context.hash("admin123")
}

class CooperationRecord(BaseModel):
    name: str = Field(..., description="姓名")
    company: str = Field(..., description="单位名称")
    phone: str = Field(..., description="手机号码")
    email: Optional[EmailStr] = Field("", description="电子邮箱")
    interest: str = Field(..., description="感兴趣的方向")
    message: str = Field("", description="合作意向说明")

class CooperationRecordOut(BaseModel):
    id: int
    name: str
    company: str
    phone: str
    email: str
    interest: str
    message: str
    status: str
    created_at: str
    updated_at: str = ""

class StatusUpdate(BaseModel):
    status: str = Field(..., description="状态")

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cooperation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            interest TEXT NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            target_id INTEGER,
            target_name TEXT,
            operator TEXT NOT NULL,
            ip_address TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("数据库初始化完成")

init_db()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(username: str, password: str):
    if username not in ADMIN_CREDENTIALS:
        return False
    hashed_password = ADMIN_CREDENTIALS[username]
    if not verify_password(password, hashed_password):
        return False
    return username

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    if token_data.username not in ADMIN_CREDENTIALS:
        raise credentials_exception
    return token_data.username

def log_operation(action: str, target_id: int = None, target_name: str = None, 
                  operator: str = "system", ip_address: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO operation_log (action, target_id, target_name, operator, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (action, target_id, target_name, operator, ip_address, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()

@app.post("/token", response_model=Token, summary="获取登录令牌")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user}, expires_delta=access_token_expires
    )
    logger.info(f"用户 {user} 登录成功")
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/submit", response_model=CooperationRecordOut, summary="提交合作意向")
async def submit_cooperation(data: CooperationRecord):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO cooperation (name, company, phone, email, interest, message, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        ''', (data.name, data.company, data.phone, data.email or '', data.interest, data.message, now, now))
        conn.commit()
        record_id = cursor.lastrowid
        
        cursor.execute('SELECT * FROM cooperation WHERE id = ?', (record_id,))
        row = cursor.fetchone()
        logger.info(f"新合作登记: {data.name} - {data.company}")
        log_operation("submit", record_id, data.name)
        return CooperationRecordOut(
            id=row[0], name=row[1], company=row[2], phone=row[3], email=row[4],
            interest=row[5], message=row[6], status=row[8], created_at=row[7], updated_at=row[9]
        )
    except Exception as e:
        conn.rollback()
        logger.error(f"提交合作意向失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/records", response_model=List[CooperationRecordOut], summary="获取登记记录列表")
async def get_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="搜索关键词"),
    interest: str = Query("", description="感兴趣方向筛选"),
    status: str = Query("", description="状态筛选"),
    start_date: str = Query("", description="开始日期"),
    end_date: str = Query("", description="结束日期"),
    current_user: str = Depends(get_current_user)
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        offset = (page - 1) * page_size
        query = 'SELECT * FROM cooperation WHERE 1=1'
        params = []
        
        if search:
            query += ' AND (name LIKE ? OR company LIKE ? OR phone LIKE ? OR email LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%'])
        
        if interest:
            query += ' AND interest = ?'
            params.append(interest)
        
        if status:
            query += ' AND status = ?'
            params.append(status)
        
        if start_date:
            query += ' AND created_at >= ?'
            params.append(f'{start_date} 00:00:00')
        
        if end_date:
            query += ' AND created_at <= ?'
            params.append(f'{end_date} 23:59:59')
        
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([page_size, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [CooperationRecordOut(
            id=row[0], name=row[1], company=row[2], phone=row[3], email=row[4],
            interest=row[5], message=row[6], status=row[8], created_at=row[7], updated_at=row[9]
        ) for row in rows]
    finally:
        conn.close()

@app.get("/api/records/{record_id}", response_model=CooperationRecordOut, summary="获取单条记录")
async def get_record(record_id: int, current_user: str = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM cooperation WHERE id = ?', (record_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        return CooperationRecordOut(
            id=row[0], name=row[1], company=row[2], phone=row[3], email=row[4],
            interest=row[5], message=row[6], status=row[8], created_at=row[7], updated_at=row[9]
        )
    finally:
        conn.close()

@app.put("/api/records/{record_id}/status", summary="更新记录状态")
async def update_status(
    record_id: int,
    data: StatusUpdate,
    current_user: str = Depends(get_current_user)
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    valid_statuses = ['pending', 'contacted', 'cooperated', 'rejected']
    if data.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效状态，可选值: {', '.join(valid_statuses)}")
    
    try:
        cursor.execute('SELECT name FROM cooperation WHERE id = ?', (record_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            UPDATE cooperation SET status = ?, updated_at = ? WHERE id = ?
        ''', (data.status, now, record_id))
        conn.commit()
        
        logger.info(f"用户 {current_user} 更新记录 {record_id} 状态为 {data.status}")
        log_operation("update_status", record_id, row[0], current_user)
        return {"message": "状态更新成功"}
    finally:
        conn.close()

@app.put("/api/records/batch/status", summary="批量更新状态")
async def batch_update_status(
    record_ids: List[int] = Body(...),
    status: str = Body(...),
    current_user: str = Depends(get_current_user)
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    valid_statuses = ['pending', 'contacted', 'cooperated', 'rejected']
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效状态，可选值: {', '.join(valid_statuses)}")
    
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        placeholders = ','.join('?' * len(record_ids))
        cursor.execute(f'''
            UPDATE cooperation SET status = ?, updated_at = ? WHERE id IN ({placeholders})
        ''', [status, now] + record_ids)
        conn.commit()
        
        logger.info(f"用户 {current_user} 批量更新 {len(record_ids)} 条记录状态为 {status}")
        log_operation("batch_update_status", target_name=f"{len(record_ids)} 条记录", operator=current_user)
        return {"message": f"成功更新 {cursor.rowcount} 条记录"}
    finally:
        conn.close()

@app.delete("/api/records/{record_id}", summary="删除记录")
async def delete_record(record_id: int, current_user: str = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT name FROM cooperation WHERE id = ?', (record_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        
        cursor.execute('DELETE FROM cooperation WHERE id = ?', (record_id,))
        conn.commit()
        
        logger.info(f"用户 {current_user} 删除记录 {record_id}")
        log_operation("delete", record_id, row[0], current_user)
        return {"message": "删除成功"}
    finally:
        conn.close()

@app.delete("/api/records/batch", summary="批量删除记录")
async def batch_delete_records(
    record_ids: List[int] = Body(...),
    current_user: str = Depends(get_current_user)
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        placeholders = ','.join('?' * len(record_ids))
        cursor.execute(f'DELETE FROM cooperation WHERE id IN ({placeholders})', record_ids)
        conn.commit()
        
        logger.info(f"用户 {current_user} 批量删除 {len(record_ids)} 条记录")
        log_operation("batch_delete", target_name=f"{len(record_ids)} 条记录", operator=current_user)
        return {"message": f"成功删除 {cursor.rowcount} 条记录"}
    finally:
        conn.close()

@app.get("/api/count", summary="获取记录总数")
async def get_count(
    interest: str = Query("", description="感兴趣方向筛选"),
    status: str = Query("", description="状态筛选"),
    current_user: str = Depends(get_current_user)
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        query = 'SELECT COUNT(*) FROM cooperation WHERE 1=1'
        params = []
        
        if interest:
            query += ' AND interest = ?'
            params.append(interest)
        
        if status:
            query += ' AND status = ?'
            params.append(status)
        
        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        return {"count": count}
    finally:
        conn.close()

@app.get("/api/statistics", summary="获取统计数据")
async def get_statistics(current_user: str = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM cooperation')
        total = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM cooperation WHERE status = "pending"')
        pending = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM cooperation WHERE status = "contacted"')
        contacted = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM cooperation WHERE status = "cooperated"')
        cooperated = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM cooperation WHERE status = "rejected"')
        rejected = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT interest, COUNT(*) as count 
            FROM cooperation 
            GROUP BY interest 
            ORDER BY count DESC
        ''')
        interest_stats = [{"interest": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as count 
            FROM cooperation 
            WHERE created_at >= DATE('now', '-7 days')
            GROUP BY DATE(created_at) 
            ORDER BY date
        ''')
        daily_stats = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        return {
            "total": total,
            "pending": pending,
            "contacted": contacted,
            "cooperated": cooperated,
            "rejected": rejected,
            "interest_distribution": interest_stats,
            "daily_trend": daily_stats
        }
    finally:
        conn.close()

@app.get("/api/export", summary="导出数据为CSV")
async def export_data(
    interest: str = Query("", description="感兴趣方向筛选"),
    status: str = Query("", description="状态筛选"),
    current_user: str = Depends(get_current_user)
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        query = 'SELECT * FROM cooperation WHERE 1=1'
        params = []
        
        if interest:
            query += ' AND interest = ?'
            params.append(interest)
        
        if status:
            query += ' AND status = ?'
            params.append(status)
        
        query += ' ORDER BY created_at DESC'
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', '姓名', '单位', '电话', '邮箱', '感兴趣方向', '合作意向说明', '状态', '创建时间', '更新时间'])
        
        status_map = {'pending': '待处理', 'contacted': '已联系', 'cooperated': '已合作', 'rejected': '暂不考虑'}
        interest_map = {
            'core': '核心支撑平台', 'powerplant': '电厂数字解决方案',
            'grid': '电网数字解决方案', 'newenergy': '新能源数字解决方案',
            'others': '其他数字化解决方案', 'hardware': '玄武系列硬件装备',
            'software': '文鳐系列软件产品', 'custom': '定制化项目合作'
        }
        
        for row in rows:
            writer.writerow([
                row[0], row[1], row[2], row[3], row[4],
                interest_map.get(row[5], row[5]), row[6],
                status_map.get(row[8], row[8]), row[7], row[9]
            ])
        
        output.seek(0)
        filename = f"cooperation_records_{datetime.now().strftime('%Y%m%d')}.csv"
        
        logger.info(f"用户 {current_user} 导出数据，共 {len(rows)} 条记录")
        log_operation("export", target_name=f"{len(rows)} 条记录", operator=current_user)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    finally:
        conn.close()

@app.get("/api/logs", summary="获取操作日志")
async def get_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str = Query("", description="操作类型筛选"),
    current_user: str = Depends(get_current_user)
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        offset = (page - 1) * page_size
        query = 'SELECT * FROM operation_log WHERE 1=1'
        params = []
        
        if action:
            query += ' AND action LIKE ?'
            params.append(f'%{action}%')
        
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([page_size, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [{
            "id": row[0], "action": row[1], "target_id": row[2],
            "target_name": row[3], "operator": row[4],
            "ip_address": row[5], "created_at": row[6]
        } for row in rows]
    finally:
        conn.close()

# ==================== 服务监控 API ====================
MONITOR_STATUS_FILE = os.path.join(os.path.dirname(__file__), "monitor_status.json")
MONITOR_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "monitor_config.json")

@app.get("/api/monitor/status", summary="获取服务监控状态")
async def get_monitor_status():
    try:
        with open(MONITOR_STATUS_FILE) as f:
            return json.load(f)
    except:
        return {"services": {}, "last_updated": "", "summary": {"total": 0, "up": 0, "down": 0}, "history": []}

@app.get("/api/monitor/config", summary="获取告警配置")
async def get_monitor_config():
    try:
        with open(MONITOR_CONFIG_FILE) as f:
            return json.load(f)
    except:
        return {}

@app.post("/api/monitor/config", summary="保存告警配置")
async def save_monitor_config(config: dict):
    with open(MONITOR_CONFIG_FILE, 'w') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return {"success": True, "message": "配置已保存"}

@app.post("/api/monitor/test-email", summary="测试邮件发送")
async def test_email(config: dict):
    try:
        from email.mime.text import MIMEText
        import smtplib
        msg = MIMEText("这是一封来自服务监控系统的测试邮件，收到即表示邮件配置正常。", "plain", "utf-8")
        msg["Subject"] = "[服务监控] 测试邮件"
        msg["From"] = config.get("from_addr", "")
        msg["To"] = ", ".join(config.get("to_addrs", []))
        
        if config.get("smtp_ssl"):
            with smtplib.SMTP_SSL(config["smtp_host"], config["smtp_port"]) as server:
                server.login(config["username"], config["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
                server.starttls()
                server.login(config["username"], config["password"])
                server.send_message(msg)
        return {"success": True, "message": "测试邮件发送成功"}
    except Exception as e:
        return {"success": False, "message": f"发送失败: {str(e)}"}

@app.post("/api/monitor/trigger-check", summary="触发一次手动检查")
async def trigger_check():
    import subprocess
    try:
        r = subprocess.run(["python3", os.path.join(os.path.dirname(__file__), "monitor.py"), "--once"],
                          capture_output=True, text=True, timeout=30)
        return {"success": True, "output": r.stdout}
    except Exception as e:
        return {"success": False, "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)