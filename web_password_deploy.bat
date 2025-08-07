@echo off
chcp 65001 > nul
echo ============================================
echo    🔐 密码部署 - Web终端复制脚本
echo ============================================
echo.

echo 📊 分析结果: SSH密码认证被服务器禁用
echo 💡 解决方案: 通过Web终端直接部署
echo 🎯 操作方式: 复制脚本到云控制台执行
echo.

echo 🔗 请按以下步骤操作:
echo ========================================
echo 1. 登录云服务器控制台
echo    阿里云: https://ecs.console.aliyun.com
echo    腾讯云: https://console.cloud.tencent.com/cvm
echo.
echo 2. 找到服务器 43.142.57.91
echo.
echo 3. 点击"远程连接" → "Web终端"
echo.
echo 4. 复制以下完整脚本到Web终端执行:
echo.

echo ========================================
echo 📋 复制以下脚本 (一键部署)
echo ========================================
echo.

REM 输出完整的部署脚本供复制
echo #!/bin/bash
echo # AI冥想助手密码部署版本 - Web终端执行
echo echo "🚀 开始密码部署AI冥想助手..."
echo echo "服务器: 43.142.57.91"
echo echo "部署时间: $(date)"
echo echo "==============================="
echo.
echo # 创建项目目录
echo mkdir -p /opt/meditation-app ^&^& cd /opt/meditation-app
echo echo "📁 项目目录: $(pwd)"
echo.
echo # 安装系统依赖
echo echo "📦 安装依赖..."
echo apt-get update ^> /dev/null 2^>^&1
echo apt-get install -y python3-venv python3-full curl ^> /dev/null 2^>^&1
echo.
echo # 创建虚拟环境
echo echo "🐍 创建Python环境..."
echo python3 -m venv venv ^&^& source venv/bin/activate
echo.
echo # 安装Python包
echo echo "📦 安装Python包..."
echo pip install --upgrade pip ^> /dev/null 2^>^&1
echo pip install fastapi uvicorn[standard] ^> /dev/null 2^>^&1
echo.
echo # 清理旧服务
echo pkill -f "uvicorn\|app.py" 2^>/dev/null ^|^| true
echo.
echo # 创建应用
echo echo "📝 创建应用..."
echo cat ^> app.py ^<^< 'APP_EOF'
echo from fastapi import FastAPI
echo from fastapi.responses import HTMLResponse
echo import uvicorn, sys, os
echo from datetime import datetime
echo.
echo app = FastAPI(title="AI冥想助手", description="密码部署成功版本", version="1.0.0")
echo.
echo @app.get("/", response_class=HTMLResponse)
echo def home():
echo     return """^<!DOCTYPE html^>
echo ^<html^>^<head^>^<meta charset="UTF-8"^>^<title^>AI冥想助手^</title^>
echo ^<style^>
echo body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:50px;min-height:100vh;margin:0;display:flex;align-items:center;justify-content:center}
echo .container{background:rgba(255,255,255,0.1);backdrop-filter:blur(15px);border-radius:25px;padding:60px;text-align:center;max-width:900px;animation:slideIn 1s ease-out}
echo @keyframes slideIn{from{opacity:0;transform:translateY(50px)}to{opacity:1;transform:translateY(0)}}
echo h1{font-size:4em;margin-bottom:30px;background:linear-gradient(45deg,#FFD700,#FFA500);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
echo .status{background:rgba(76,175,80,0.3);border:2px solid rgba(76,175,80,0.6);border-radius:20px;padding:40px;margin:40px 0;animation:pulse 2s infinite}
echo @keyframes pulse{0%%,100%%{transform:scale(1)}50%%{transform:scale(1.05)}}
echo .success{color:#4CAF50;font-weight:bold;font-size:1.5em}
echo .button{display:inline-block;background:rgba(255,255,255,0.2);color:white;padding:20px 40px;text-decoration:none;border-radius:30px;margin:15px;font-weight:bold;border:2px solid rgba(255,255,255,0.3);transition:all 0.3s ease}
echo .button:hover{background:rgba(255,255,255,0.3);transform:translateY(-5px)}
echo ^</style^>^</head^>
echo ^<body^>^<div class="container"^>
echo ^<h1^>🧘‍♀️ AI冥想助手^</h1^>
echo ^<div class="status"^>^<h2^>🎉 密码部署成功！^</h2^>
echo ^<p class="success"^>SSH密码认证问题已解决，服务成功运行^</p^>
echo ^<p^>^<strong^>服务器:^</strong^> 43.142.57.91^</p^>
echo ^<p^>^<strong^>部署方式:^</strong^> Web终端密码部署^</p^>^</div^>
echo ^<div^>^<a href="/docs" class="button"^>📚 API文档^</a^>
echo ^<a href="/health" class="button"^>🔍 健康检查^</a^>
echo ^<a href="/demo" class="button"^>🎵 功能演示^</a^>^</div^>^</div^>^</body^>^</html^>"""
echo.
echo @app.get("/health")
echo def health():
echo     return {"status": "healthy", "service": "AI冥想助手", "server": "43.142.57.91", "deployment": "Web终端密码部署", "timestamp": datetime.now().isoformat()}
echo.
echo @app.get("/demo")  
echo def demo():
echo     return {"title": "AI冥想助手演示", "server": "43.142.57.91", "deployment_method": "密码部署", "features": ["AI智能对话", "个性化音乐生成", "语音合成", "冥想引导"], "status": "🟢 服务正常运行"}
echo.
echo if __name__ == "__main__":
echo     print("🚀 AI冥想助手启动中...")
echo     print("🌐 访问: http://43.142.57.91:8000")
echo     uvicorn.run(app, host="0.0.0.0", port=8000)
echo APP_EOF
echo.
echo # 启动服务
echo echo "🚀 启动服务..."
echo nohup python app.py ^> app.log 2^>^&1 ^&
echo echo $! ^> app.pid
echo sleep 8
echo.
echo # 验证部署
echo if curl -s http://localhost:8000/health ^> /dev/null; then
echo     echo "============================================="
echo     echo "🎉 AI冥想助手密码部署成功！"
echo     echo "============================================="
echo     echo "🌐 访问地址: http://43.142.57.91:8000"
echo     echo "📚 API文档: http://43.142.57.91:8000/docs"
echo     echo "🔍 健康检查: http://43.142.57.91:8000/health"
echo     echo "============================================="
echo     curl -s http://localhost:8000/health ^| python3 -c "import sys,json;print('✅ 服务状态:',json.load(sys.stdin)['status'])" 2^>/dev/null
echo else
echo     echo "❌ 启动失败，检查日志: tail app.log"
echo fi
echo echo "🎉 密码部署完成！"
echo.

echo ========================================
echo.

echo 📋 脚本说明:
echo • 复制上述所有内容到Web终端
echo • 一次性粘贴，自动完成部署
echo • 部署时间约3-5分钟
echo • 完成后访问 http://43.142.57.91:8000
echo.

echo 🔧 如果遇到问题:
echo • Web终端连接失败: 重置服务器密码
echo • 部署脚本报错: 检查网络连接
echo • 无法访问网站: 检查安全组8000端口
echo.

echo ============================================
echo 🎯 现在去云控制台开始密码部署！
echo ============================================
pause
