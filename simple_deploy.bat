@echo off
chcp 65001 > nul
echo ============================================
echo    🚀 AI冥想助手简化部署 v3.0
echo ============================================
echo.

echo 📋 当前部署状态:
echo ✅ 服务器IP: 43.142.57.91  
echo ✅ SSH密钥已清理
echo ✅ 部署脚本已准备
echo.

echo 🎯 执行SSH密码连接
echo ----------------------------------------
echo 注意: 系统将提示您输入服务器密码
echo 如果不知道密码，请先到云控制台重置密码
echo 建议密码: MeditationApp2025!
echo.

REM SSH密码连接（强制密码认证）
echo 正在连接到服务器 (使用密码认证)...
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=nul -o PreferredAuthentications=password -o PubkeyAuthentication=no root@43.142.57.91

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ SSH连接成功！
) else (
    echo.
    echo ❌ SSH连接失败
    echo.
    echo 🔧 请按以下步骤操作:
    echo 1. 登录云服务器控制台
    echo 2. 找到IP为 43.142.57.91 的服务器
    echo 3. 重置root密码 (建议: MeditationApp2025!)
    echo 4. 重启服务器
    echo 5. 重新运行此脚本
    echo.
)

echo.
echo 📋 如果SSH连接成功，请在服务器中执行以下部署命令:
echo ========================================
echo.
echo # 一键部署AI冥想助手
echo mkdir -p /opt/meditation-app ^&^& cd /opt/meditation-app
echo apt-get update ^&^& apt-get install -y python3-venv curl
echo python3 -m venv venv ^&^& source venv/bin/activate
echo pip install fastapi uvicorn[standard]
echo.
echo # 创建应用文件
echo cat ^> app.py ^<^< 'EOF'
echo from fastapi import FastAPI
echo from fastapi.responses import HTMLResponse
echo import uvicorn
echo.
echo app = FastAPI(title="AI冥想助手")
echo.
echo @app.get("/")
echo def home():
echo     return HTMLResponse("""
echo     ^<html^>^<head^>^<title^>AI冥想助手^</title^>
echo     ^<style^>body{font-family:Arial;text-align:center;background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:50px}
echo     .container{background:rgba(255,255,255,0.1);padding:50px;border-radius:20px}
echo     h1{font-size:3em;color:#FFD700}^</style^>^</head^>
echo     ^<body^>^<div class="container"^>^<h1^>🧘‍♀️ AI冥想助手^</h1^>
echo     ^<h2^>🎉 部署成功！^</h2^>^<p^>服务器: 43.142.57.91^</p^>
echo     ^<a href="/docs" style="color:#FFD700"^>📚 API文档^</a^> ^|
echo     ^<a href="/health" style="color:#FFD700"^>🔍 健康检查^</a^>
echo     ^</div^>^</body^>^</html^>""")
echo.
echo @app.get("/health")
echo def health():
echo     return {"status": "healthy", "service": "AI冥想助手"}
echo.
echo if __name__ == "__main__":
echo     uvicorn.run(app, host="0.0.0.0", port=8000)
echo EOF
echo.
echo # 启动服务
echo nohup python app.py ^> app.log 2^>^&1 ^&
echo echo "🎉 部署完成！访问: http://43.142.57.91:8000"
echo.
echo ========================================
echo.

echo 🎯 部署完成后访问地址:
echo   🌐 主页: http://43.142.57.91:8000
echo   📚 API文档: http://43.142.57.91:8000/docs  
echo   🔍 健康检查: http://43.142.57.91:8000/health
echo.

pause
