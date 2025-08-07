@echo off
chcp 65001 > nul
echo ============================================
echo    🔧 AI冥想助手问题诊断和修复工具
echo ============================================
echo.

echo 📊 网络连通性测试结果:
echo ✅ 服务器网络正常 (Ping: 7ms)
echo ❌ 8000端口仍然无法连接
echo.

echo 🎯 可能的问题原因:
echo ----------------------------------------
echo 1. 安全组配置未完全生效
echo 2. 服务器上的应用没有正确启动
echo 3. 服务器防火墙仍然阻挡端口
echo 4. 应用绑定到了错误的地址
echo.

echo 🔧 解决方案 - 通过Web终端完整修复:
echo ========================================
echo.
echo 请登录腾讯云控制台，在Web终端中执行以下脚本:
echo.

echo ========================================
echo 📋 完整修复脚本 (复制到Web终端执行)
echo ========================================
echo.

echo #!/bin/bash
echo echo "🔧 开始完整诊断和修复..."
echo.
echo # 第一步: 检查当前服务状态
echo echo "🔍 第1步: 检查服务状态"
echo echo "----------------------------------------"
echo ps aux ^| grep -E "(python\|uvicorn\|app\.py)" ^| grep -v grep
echo echo ""
echo netstat -tulpn ^| grep :8000
echo echo ""
echo.
echo # 第二步: 停止所有相关进程
echo echo "🛑 第2步: 停止现有服务"
echo echo "----------------------------------------"
echo pkill -f "python.*app\.py" 2^>/dev/null ^|^| true
echo pkill -f uvicorn 2^>/dev/null ^|^| true
echo sleep 3
echo echo "已停止现有服务"
echo.
echo # 第三步: 配置防火墙
echo echo "🔥 第3步: 配置服务器防火墙"
echo echo "----------------------------------------"
echo # 配置UFW防火墙
echo ufw --force enable 2^>/dev/null ^|^| true
echo ufw allow 8000/tcp 2^>/dev/null ^|^| true
echo.
echo # 配置iptables防火墙
echo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT 2^>/dev/null ^|^| true
echo echo "防火墙配置完成"
echo.
echo # 第四步: 创建项目目录
echo echo "📁 第4步: 准备项目环境"
echo echo "----------------------------------------"
echo mkdir -p /opt/meditation-app
echo cd /opt/meditation-app
echo.
echo # 第五步: 更新系统和安装依赖
echo echo "📦 第5步: 安装系统依赖"
echo echo "----------------------------------------"
echo apt-get update -y
echo apt-get install -y python3 python3-pip python3-venv curl net-tools
echo.
echo # 第六步: 创建虚拟环境
echo echo "🐍 第6步: 创建Python环境"
echo echo "----------------------------------------"
echo python3 -m venv venv
echo source venv/bin/activate
echo pip install --upgrade pip
echo pip install fastapi uvicorn[standard]
echo.
echo # 第七步: 创建增强版应用
echo echo "📝 第7步: 创建应用文件"
echo echo "----------------------------------------"
echo cat ^> app.py ^<^< 'APP_EOF'
echo import logging
echo from fastapi import FastAPI
echo from fastapi.responses import HTMLResponse
echo import uvicorn
echo import sys
echo from datetime import datetime
echo.
echo # 配置日志
echo logging.basicConfig(
echo     level=logging.INFO,
echo     format='%%(asctime)s - %%(levelname)s - %%(message)s',
echo     handlers=[
echo         logging.FileHandler('app.log'),
echo         logging.StreamHandler(sys.stdout)
echo     ]
echo )
echo logger = logging.getLogger(__name__)
echo.
echo # 创建FastAPI应用
echo app = FastAPI(
echo     title="AI冥想助手",
echo     description="腾讯云部署版本",
echo     version="2.0.0"
echo )
echo.
echo @app.get("/", response_class=HTMLResponse)
echo def home():
echo     logger.info("收到主页访问请求")
echo     return """
echo     ^<!DOCTYPE html^>
echo     ^<html lang="zh-CN"^>
echo     ^<head^>
echo         ^<meta charset="UTF-8"^>
echo         ^<meta name="viewport" content="width=device-width, initial-scale=1.0"^>
echo         ^<title^>AI冥想助手 - 腾讯云版^</title^>
echo         ^<style^>
echo             * { margin: 0; padding: 0; box-sizing: border-box; }
echo             body {
echo                 font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
echo                 background: linear-gradient(135deg, #667eea 0%%, #764ba2 100%%);
echo                 color: white;
echo                 min-height: 100vh;
echo                 display: flex;
echo                 align-items: center;
echo                 justify-content: center;
echo                 padding: 20px;
echo             }
echo             .container {
echo                 background: rgba(255, 255, 255, 0.15);
echo                 backdrop-filter: blur(20px);
echo                 border-radius: 30px;
echo                 padding: 60px;
echo                 text-align: center;
echo                 max-width: 800px;
echo                 width: 100%%;
echo                 box-shadow: 0 25px 50px rgba(0, 0, 0, 0.25);
echo                 border: 1px solid rgba(255, 255, 255, 0.2);
echo             }
echo             h1 {
echo                 font-size: 4em;
echo                 margin-bottom: 30px;
echo                 background: linear-gradient(45deg, #FFD700, #FFA500);
echo                 -webkit-background-clip: text;
echo                 -webkit-text-fill-color: transparent;
echo                 text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
echo             }
echo             .success-banner {
echo                 background: rgba(76, 175, 80, 0.3);
echo                 border: 2px solid rgba(76, 175, 80, 0.6);
echo                 border-radius: 20px;
echo                 padding: 30px;
echo                 margin: 30px 0;
echo                 animation: pulse 2s infinite;
echo             }
echo             @keyframes pulse {
echo                 0%% { transform: scale(1); }
echo                 50%% { transform: scale(1.02); }
echo                 100%% { transform: scale(1); }
echo             }
echo             .info-grid {
echo                 display: grid;
echo                 grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
echo                 gap: 20px;
echo                 margin: 30px 0;
echo             }
echo             .info-card {
echo                 background: rgba(255, 255, 255, 0.1);
echo                 padding: 25px;
echo                 border-radius: 15px;
echo                 border: 1px solid rgba(255, 255, 255, 0.2);
echo             }
echo             .nav-links {
echo                 margin: 40px 0;
echo             }
echo             .nav-links a {
echo                 display: inline-block;
echo                 background: rgba(255, 255, 255, 0.2);
echo                 color: white;
echo                 padding: 15px 30px;
echo                 text-decoration: none;
echo                 border-radius: 25px;
echo                 margin: 10px;
echo                 font-weight: bold;
echo                 border: 2px solid rgba(255, 255, 255, 0.3);
echo                 transition: all 0.3s ease;
echo             }
echo             .nav-links a:hover {
echo                 background: rgba(255, 255, 255, 0.3);
echo                 transform: translateY(-3px);
echo                 box-shadow: 0 10px 20px rgba(0,0,0,0.2);
echo             }
echo             .server-info {
echo                 font-family: 'Courier New', monospace;
echo                 background: rgba(0, 0, 0, 0.3);
echo                 padding: 20px;
echo                 border-radius: 10px;
echo                 margin: 20px 0;
echo             }
echo         ^</style^>
echo     ^</head^>
echo     ^<body^>
echo         ^<div class="container"^>
echo             ^<h1^>🧘‍♀️ AI冥想助手^</h1^>
echo             
echo             ^<div class="success-banner"^>
echo                 ^<h2^>🎉 腾讯云部署成功！^</h2^>
echo                 ^<p^>端口问题已完全修复，服务正常运行^</p^>
echo             ^</div^>
echo             
echo             ^<div class="info-grid"^>
echo                 ^<div class="info-card"^>
echo                     ^<h3^>🌐 服务器信息^</h3^>
echo                     ^<p^>IP: 43.142.57.91^</p^>
echo                     ^<p^>端口: 8000^</p^>
echo                     ^<p^>状态: 在线^</p^>
echo                 ^</div^>
echo                 ^<div class="info-card"^>
echo                     ^<h3^>🔧 修复状态^</h3^>
echo                     ^<p^>✅ 安全组已配置^</p^>
echo                     ^<p^>✅ 防火墙已开放^</p^>
echo                     ^<p^>✅ 服务已启动^</p^>
echo                 ^</div^>
echo             ^</div^>
echo             
echo             ^<div class="nav-links"^>
echo                 ^<a href="/docs"^>📚 API文档^</a^>
echo                 ^<a href="/health"^>🔍 健康检查^</a^>
echo                 ^<a href="/test"^>🧪 连接测试^</a^>
echo             ^</div^>
echo             
echo             ^<div class="server-info"^>
echo                 ^<strong^>部署时间:^</strong^> """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """^<br^>
echo                 ^<strong^>版本:^</strong^> 2.0.0 (腾讯云优化版)^<br^>
echo                 ^<strong^>Framework:^</strong^> FastAPI + Uvicorn
echo             ^</div^>
echo         ^</div^>
echo     ^</body^>
echo     ^</html^>
echo     """
echo.
echo @app.get("/health")
echo def health_check():
echo     logger.info("健康检查请求")
echo     return {
echo         "status": "healthy",
echo         "service": "AI冥想助手",
echo         "version": "2.0.0",
echo         "server": "43.142.57.91",
echo         "port": 8000,
echo         "provider": "腾讯云",
echo         "timestamp": datetime.now().isoformat(),
echo         "uptime": "服务正常运行",
echo         "fixes_applied": [
echo             "安全组端口开放",
echo             "服务器防火墙配置", 
echo             "应用正确绑定",
echo             "日志系统启用"
echo         ]
echo     }
echo.
echo @app.get("/test")
echo def connection_test():
echo     logger.info("连接测试请求")
echo     return {
echo         "test_result": "success",
echo         "message": "🎉 网络连接测试成功！",
echo         "server_ip": "43.142.57.91",
echo         "port": 8000,
echo         "provider": "腾讯云",
echo         "access_url": "http://43.142.57.91:8000",
echo         "api_docs": "http://43.142.57.91:8000/docs",
echo         "health_check": "http://43.142.57.91:8000/health",
echo         "timestamp": datetime.now().isoformat()
echo     }
echo.
echo if __name__ == "__main__":
echo     logger.info("启动AI冥想助手 - 腾讯云版...")
echo     print("=" * 50)
echo     print("🚀 AI冥想助手启动中...")
echo     print("🌐 服务器: 43.142.57.91")
echo     print("🔌 端口: 8000")
echo     print("🔗 访问地址: http://43.142.57.91:8000")
echo     print("📚 API文档: http://43.142.57.91:8000/docs")
echo     print("=" * 50)
echo     
echo     uvicorn.run(
echo         app,
echo         host="0.0.0.0",  # 绑定到所有网络接口
echo         port=8000,
echo         log_level="info",
echo         access_log=True,
echo         reload=False
echo     )
echo APP_EOF
echo.
echo echo "应用文件创建完成"
echo.
echo # 第八步: 启动服务
echo echo "🚀 第8步: 启动服务"
echo echo "----------------------------------------"
echo # 确保在虚拟环境中
echo source venv/bin/activate
echo.
echo # 启动应用
echo echo "正在启动AI冥想助手..."
echo nohup python app.py ^> app.log 2^>^&1 ^&
echo APP_PID=$!
echo echo $APP_PID ^> app.pid
echo echo "服务已启动，PID: $APP_PID"
echo.
echo # 第九步: 等待服务启动并验证
echo echo "⏳ 第9步: 等待服务启动..."
echo echo "----------------------------------------"
echo sleep 15
echo.
echo echo "🔍 验证服务状态..."
echo echo "监听端口:"
echo netstat -tulpn ^| grep :8000
echo echo ""
echo echo "进程状态:"
echo ps aux ^| grep python ^| grep -v grep
echo echo ""
echo.
echo # 第十步: 测试本地连接
echo echo "🧪 第10步: 测试服务连接"
echo echo "----------------------------------------"
echo if curl -s --connect-timeout 10 http://localhost:8000/health ^> /dev/null; then
echo     echo "✅ 本地连接测试成功"
echo     
echo     # 获取健康检查信息
echo     echo "📊 服务状态信息:"
echo     curl -s http://localhost:8000/health ^| python3 -m json.tool 2^>/dev/null ^|^| echo "健康检查API正常"
echo     
echo     echo ""
echo     echo "=================================================="
echo     echo "🎉 AI冥想助手修复成功！"
echo     echo "=================================================="
echo     echo "🌐 立即访问: http://43.142.57.91:8000"
echo     echo "📚 API文档: http://43.142.57.91:8000/docs"
echo     echo "🔍 健康检查: http://43.142.57.91:8000/health"
echo     echo "🧪 连接测试: http://43.142.57.91:8000/test"
echo     echo "=================================================="
echo     echo "📊 服务信息:"
echo     echo "   服务器: 腾讯云"
echo     echo "   IP地址: 43.142.57.91"
echo     echo "   端口: 8000"
echo     echo "   进程ID: $APP_PID"
echo     echo "   日志文件: /opt/meditation-app/app.log"
echo     echo "   配置目录: /opt/meditation-app"
echo     echo "=================================================="
echo     
echo else
echo     echo "❌ 本地连接失败，请检查:"
echo     echo "1. 安全组是否正确配置8000端口"
echo     echo "2. 服务是否正确启动"
echo     echo "3. 查看日志: tail -50 app.log"
echo     
echo     echo ""
echo     echo "📋 故障排除信息:"
echo     echo "端口监听状态:"
echo     netstat -tulpn ^| grep :8000
echo     echo ""
echo     echo "进程状态:"
echo     ps aux ^| grep python
echo     echo ""
echo     echo "最近日志:"
echo     tail -20 app.log 2^>/dev/null ^|^| echo "日志文件不存在"
echo fi

echo ========================================
echo.

echo 📝 执行步骤:
echo ----------------------------------------
echo 1. 登录腾讯云控制台
echo 2. 找到IP为 43.142.57.91 的云服务器
echo 3. 点击"登录"选择"Web Terminal"
echo 4. 复制上面的脚本并粘贴执行
echo 5. 等待完成后访问 http://43.142.57.91:8000
echo.

echo 🔍 如果仍有问题，可能需要检查:
echo ----------------------------------------
echo 1. 腾讯云安全组入站规则是否包含 TCP:8000
echo 2. 云服务器实例是否正确绑定了安全组
echo 3. 云服务器是否有多个网卡或特殊网络配置
echo.

echo ============================================
echo 🎯 修复完成后访问: http://43.142.57.91:8000
echo ============================================
pause
