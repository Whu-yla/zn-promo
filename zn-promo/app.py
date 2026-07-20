from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
import sqlite3
import os

app = FastAPI(title="中南电力数智科技合作登记系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "cooperation.db"

class CooperationRecord(BaseModel):
    name: str = Field(..., description="姓名")
    company: str = Field(..., description="单位名称")
    phone: str = Field(..., description="手机号码")
    email: str = Field("", description="电子邮箱")
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
    created_at: str

def init_db():
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE cooperation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                company TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                interest TEXT NOT NULL,
                message TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        print("数据库初始化完成")

init_db()

@app.post("/api/submit", response_model=CooperationRecordOut, summary="提交合作意向")
async def submit_cooperation(data: CooperationRecord):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO cooperation (name, company, phone, email, interest, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (data.name, data.company, data.phone, data.email, data.interest, data.message, created_at))
        conn.commit()
        record_id = cursor.lastrowid
        
        cursor.execute('SELECT * FROM cooperation WHERE id = ?', (record_id,))
        row = cursor.fetchone()
        return CooperationRecordOut(
            id=row[0],
            name=row[1],
            company=row[2],
            phone=row[3],
            email=row[4],
            interest=row[5],
            message=row[6],
            created_at=row[7]
        )
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/records", response_model=list[CooperationRecordOut], summary="获取所有登记记录")
async def get_records(page: int = 1, page_size: int = 20):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        offset = (page - 1) * page_size
        cursor.execute('SELECT * FROM cooperation ORDER BY created_at DESC LIMIT ? OFFSET ?', (page_size, offset))
        rows = cursor.fetchall()
        return [CooperationRecordOut(
            id=row[0],
            name=row[1],
            company=row[2],
            phone=row[3],
            email=row[4],
            interest=row[5],
            message=row[6],
            created_at=row[7]
        ) for row in rows]
    finally:
        conn.close()

@app.get("/api/records/{record_id}", response_model=CooperationRecordOut, summary="获取单条记录")
async def get_record(record_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM cooperation WHERE id = ?', (record_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        return CooperationRecordOut(
            id=row[0],
            name=row[1],
            company=row[2],
            phone=row[3],
            email=row[4],
            interest=row[5],
            message=row[6],
            created_at=row[7]
        )
    finally:
        conn.close()

@app.delete("/api/records/{record_id}", summary="删除记录")
async def delete_record(record_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM cooperation WHERE id = ?', (record_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="记录不存在")
        return {"message": "删除成功"}
    finally:
        conn.close()

@app.get("/api/count", summary="获取记录总数")
async def get_count():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM cooperation')
        count = cursor.fetchone()[0]
        return {"count": count}
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)