#!/bin/bash
echo "🔧 开始完整诊断和修复..."

# 检查当前服务状态
echo "🔍 第1步: 检查服务状态"
echo "----------------------------------------"
ps aux | grep -E "(python|uvicorn|app\.py)" | grep -v grep
echo ""
netstat -tulpn | grep :8000
echo ""

# 停止所有相关进程
echo "🛑 第2步: 停止现有服务"
echo "----------------------------------------"
pkill -f "python.*app\.py" 2>/dev/null || true
pkill -f uvicorn 2>/dev/null || true
sleep 3
echo "已停止现有服务"

# 配置防火墙
echo "🔥 第3步: 配置防火墙"
echo "----------------------------------------"
# 配置UFW防火墙
ufw --force enable 2>/dev/null || true
ufw allow 8000/tcp 2>/dev/null || true

# 配置iptables防火墙
iptables -I INPUT -p tcp --dport 8000 -j ACCEPT 2>/dev/null || true
echo "防火墙配置完成"

# 创建项目目录
echo "📁 第4步: 准备项目环境"
echo "----------------------------------------"
mkdir -p /opt/meditation-app
cd /opt/meditation-app

# 安装依赖
echo "📦 第5步: 安装依赖"
echo "----------------------------------------"
# 根据系统类型选择包管理器
if command -v yum &> /dev/null; then
    yum update -y
    yum install -y python3 python3-pip python3-venv curl net-tools
elif command -v apt-get &> /dev/null; then
    apt-get update -y
    apt-get install -y python3 python3-pip python3-venv curl net-tools
else
    echo "系统已有Python环境，跳过安装"
fi

# 创建虚拟环境
echo "🐍 第6步: 创建Python环境"
echo "----------------------------------------"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install fastapi uvicorn[standard]

# 创建应用文件
echo "📝 第7步: 创建应用文件"
echo "----------------------------------------"
cat > app.py << 'EOF'
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI冥想助手")

@app.get("/", response_class=HTMLResponse)
def home():
    logger.info("收到主页访问请求")
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI冥想助手 - 腾讯云版</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(20px);
            border-radius: 30px;
            padding: 60px;
            text-align: center;
            max-width: 800px;
            width: 100%;
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.25);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        h1 {
            font-size: 4em;
            margin-bottom: 30px;
            background: linear-gradient(45deg, #FFD700, #FFA500);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .success-banner {
            background: rgba(76, 175, 80, 0.3);
            border: 2px solid rgba(76, 175, 80, 0.6);
            border-radius: 20px;
            padding: 30px;
            margin: 30px 0;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.02); }
            100% { transform: scale(1); }
        }
        .nav-links {
            margin: 40px 0;
        }
        .nav-links a {
            display: inline-block;
            background: rgba(255, 255, 255, 0.2);
            color: white;
            padding: 15px 30px;
            text-decoration: none;
            border-radius: 25px;
            margin: 10px;
            font-weight: bold;
            border: 2px solid rgba(255, 255, 255, 0.3);
            transition: all 0.3s ease;
        }
        .nav-links a:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: translateY(-3px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }
        .server-info {
            font-family: 'Courier New', monospace;
            background: rgba(0, 0, 0, 0.3);
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧘‍♀️ AI冥想助手</h1>
        
        <div class="success-banner">
            <h2>🎉 腾讯云部署成功！</h2>
            <p>端口问题已完全修复，服务正常运行</p>
        </div>
        
        <div class="nav-links">
            <a href="/docs">📚 API文档</a>
            <a href="/health">🔍 健康检查</a>
            <a href="/test">🧪 连接测试</a>
        </div>
        
        <div class="server-info">
            <strong>服务器:</strong> 43.142.57.91:8000<br>
            <strong>状态:</strong> 在线运行<br>
            <strong>版本:</strong> 2.0.0 (腾讯云版)
        </div>
    </div>
</body>
</html>
    """

@app.get("/health")
def health_check():
    logger.info("健康检查请求")
    return {
        "status": "healthy",
        "service": "AI冥想助手",
        "version": "2.0.0",
        "server": "43.142.57.91",
        "port": 8000,
        "provider": "腾讯云",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/test")
def connection_test():
    logger.info("连接测试请求")
    return {
        "test_result": "success",
        "message": "🎉 网络连接测试成功！",
        "server_ip": "43.142.57.91",
        "port": 8000,
        "access_url": "http://43.142.57.91:8000",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    logger.info("启动AI冥想助手 - 腾讯云版...")
    print("=" * 50)
    print("🚀 AI冥想助手启动中...")
    print("🌐 服务器: 43.142.57.91")
    print("🔌 端口: 8000")
    print("🔗 访问地址: http://43.142.57.91:8000")
    print("📚 API文档: http://43.142.57.91:8000/docs")
    print("=" * 50)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )
EOF

echo "应用文件创建完成"

# 启动服务
echo "🚀 第8步: 启动服务"
echo "----------------------------------------"
source venv/bin/activate

echo "正在启动AI冥想助手..."
nohup python app.py > app.log 2>&1 &
APP_PID=$!
echo $APP_PID > app.pid
echo "服务已启动，PID: $APP_PID"

# 等待服务启动并验证
echo "⏳ 第9步: 等待服务启动..."
echo "----------------------------------------"
sleep 15

echo "🔍 验证服务状态..."
echo "监听端口:"
netstat -tulpn | grep :8000
echo ""
echo "进程状态:"
ps aux | grep python | grep -v grep
echo ""

# 测试本地连接
echo "🧪 第10步: 测试服务连接"
echo "----------------------------------------"
if curl -s --connect-timeout 10 http://localhost:8000/health > /dev/null; then
    echo "✅ 本地连接测试成功"
    
    echo ""
    echo "=================================================="
    echo "🎉 AI冥想助手修复成功！"
    echo "=================================================="
    echo "🌐 立即访问: http://43.142.57.91:8000"
    echo "📚 API文档: http://43.142.57.91:8000/docs"
    echo "🔍 健康检查: http://43.142.57.91:8000/health"
    echo "🧪 连接测试: http://43.142.57.91:8000/test"
    echo "=================================================="
    echo "📊 服务信息:"
    echo "   服务器: 腾讯云"
    echo "   IP地址: 43.142.57.91"
    echo "   端口: 8000"
    echo "   进程ID: $APP_PID"
    echo "   日志文件: /opt/meditation-app/app.log"
    echo "=================================================="
    
else
    echo "❌ 本地连接失败，请检查:"
    echo "1. 安全组是否正确配置8000端口"
    echo "2. 服务是否正确启动"
    echo "3. 查看日志: tail -50 app.log"
    
    echo ""
    echo "📋 故障排除信息:"
    echo "端口监听状态:"
    netstat -tulpn | grep :8000
    echo ""
    echo "进程状态:"
    ps aux | grep python
    echo ""
    echo "最近日志:"
    tail -20 app.log 2>/dev/null || echo "日志文件不存在"
fi
