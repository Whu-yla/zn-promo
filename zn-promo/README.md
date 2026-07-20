# 中南电力数智科技合作登记系统

基于 FastAPI + HTML 构建的企业级合作意向登记管理系统，包含用户端宣传页面和管理员后台管理功能。

## 功能特性

### 用户端功能
- 📋 **合作意向登记表单**：支持姓名、单位、电话、邮箱、感兴趣方向等信息录入
- ✅ **实时表单验证**：手机号、邮箱格式校验，字符长度限制，错误提示
- 📱 **响应式设计**：适配桌面端和移动端
- ⚡ **提交反馈**：加载状态提示、成功/失败反馈

### 管理后台功能
- 🔐 **身份认证**：基于 JWT 的管理员登录认证
- 📊 **数据统计**：总登记数、各状态数量、方向分布、7日趋势
- 🔍 **高级搜索**：支持关键词、方向、状态、日期范围筛选
- ✏️ **状态管理**：待处理/已联系/已合作/暂不考虑四种状态，支持单条和批量更新
- 📥 **数据导出**：导出筛选结果为 CSV 文件
- 📝 **操作日志**：记录所有管理操作，支持查询
- 🗑️ **批量操作**：批量删除、批量更新状态

### 后端 API
- RESTful API 设计
- OAuth2 + JWT 认证
- SQLite 数据库持久化
- CORS 跨域支持
- 详细的 API 文档（Swagger UI）

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 后端框架 | FastAPI | >= 0.115.0 |
| 数据库 | SQLite3 | 内置 |
| 认证 | python-jose + passlib | - |
| 前端 | HTML5 + CSS3 + JavaScript | - |
| 运行环境 | Python | >= 3.8 |

## 快速开始

### 环境要求

- Python >= 3.8
- pip 包管理工具

### 安装依赖

```bash
cd zn-promo
pip install -r requirements.txt
```

### 启动服务

```bash
python app.py
```

服务启动后访问：
- **API 地址**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **管理后台**: 直接打开 `admin.html`
- **用户宣传页**: 直接打开 `zn-promo.html`

## 项目结构

```
zn-promo/
├── assets/                 # 静态资源文件
│   ├── logo_*.png          # 公司 Logo
│   ├── hero_banner.jpg     # 首页横幅
│   ├── hardware_*.jpg      # 硬件产品图片
│   ├── software_*.jpg      # 软件产品图片
│   └── company_*.png       # 公司相关图片
├── admin.html              # 管理后台页面
├── app.py                  # 后端 API 服务
├── cooperation.db          # SQLite 数据库文件
├── qr-poster.html          # 二维码海报页面
├── requirements.txt        # Python 依赖列表
└── zn-promo.html           # 用户端宣传页面
```

## API 接口

### 认证接口

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/token` | 获取登录令牌 |

### 公开接口

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/submit` | 提交合作意向 |

### 管理接口（需认证）

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/records` | 获取登记记录列表 |
| GET | `/api/records/{id}` | 获取单条记录详情 |
| PUT | `/api/records/{id}/status` | 更新记录状态 |
| DELETE | `/api/records/{id}` | 删除记录 |
| PUT | `/api/records/batch/status` | 批量更新状态 |
| DELETE | `/api/records/batch` | 批量删除记录 |
| GET | `/api/count` | 获取记录总数 |
| GET | `/api/statistics` | 获取统计数据 |
| GET | `/api/export` | 导出数据为 CSV |
| GET | `/api/logs` | 获取操作日志 |

## 使用说明

### 管理员登录

- **用户名**: `admin`
- **密码**: `admin123`

登录后进入管理后台，可查看和管理所有合作登记记录。

### 合作方向说明

| 方向代码 | 方向名称 |
|----------|----------|
| core | 核心支撑平台 |
| powerplant | 电厂数字解决方案 |
| grid | 电网数字解决方案 |
| newenergy | 新能源数字解决方案 |
| others | 其他数字化解决方案 |
| hardware | 玄武系列硬件装备 |
| software | 文鳐系列软件产品 |
| custom | 定制化项目合作 |

### 状态说明

| 状态代码 | 状态名称 |
|----------|----------|
| pending | 待处理 |
| contacted | 已联系 |
| cooperated | 已合作 |
| rejected | 暂不考虑 |

## 配置说明

### 修改管理员密码

编辑 `app.py` 文件，修改 `ADMIN_CREDENTIALS` 字典：

```python
ADMIN_CREDENTIALS = {
    "admin": pwd_context.hash("your_new_password")
}
```

### 修改 JWT 密钥

编辑 `app.py` 文件，修改 `SECRET_KEY`：

```python
SECRET_KEY = "your-secret-key-here-change-in-production"
```

### 修改服务端口

编辑 `app.py` 文件末尾：

```python
uvicorn.run(app, host="0.0.0.0", port=8000)
```

## 部署建议

### 开发环境

```bash
python app.py
```

### 生产环境

使用 Gunicorn 作为 WSGI 服务器：

```bash
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app
```

配合 Nginx 反向代理，配置 HTTPS 和域名。

## 许可证

MIT License

## 联系方式

如有问题或建议，请联系开发团队。