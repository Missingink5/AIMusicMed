@echo off
chcp 65001 > nul
echo ============================================
echo    🔧 修复Web访问问题 - 端口和防火墙
echo ============================================
echo.

echo 📊 问题诊断结果:
echo ✅ 服务器部署成功
echo ✅ 网络连通正常 (7ms延迟)
echo ❌ 8000端口无法访问
echo.

echo 🎯 问题分析:
echo 1. 云服务器安全组可能未开放8000端口
echo 2. 服务器防火墙可能阻挡了8000端口
echo 3. 应用可能没有正确启动
echo.

echo 🔧 解决方案:
echo ========================================
echo.

echo 方案1: 开放云服务器安全组端口 (推荐)
echo ----------------------------------------
echo 1. 登录云服务器控制台
echo 2. 找到您的服务器实例
echo 3. 点击"安全组"设置
echo 4. 添加入站规则:
echo    - 端口范围: 8000
echo    - 协议: TCP  
echo    - 源IP: 0.0.0.0/0 (所有IP)
echo    - 操作: 允许
echo 5. 保存设置
echo.

echo 方案2: 通过Web终端修复服务器端问题
echo ----------------------------------------
echo 请在云控制台Web终端中执行以下脚本:
echo.

echo ========================================
echo 📋 修复脚本 (复制到Web终端)
echo ========================================
echo.

echo #!/bin/bash
echo # 修复AI冥想助手访问问题
echo echo "🔧 开始修复Web访问问题..."
echo.
echo # 检查服务状态
echo echo "🔍 检查服务状态..."
echo ps aux ^| grep -E "(uvicorn\|app.py)" ^| grep -v grep
echo.
echo # 检查端口占用
echo echo "🔍 检查8000端口状态..."
echo netstat -tulpn ^| grep :8000
echo.
echo # 开放防火墙端口
echo echo "🔥 配置防火墙..."
echo ufw allow 8000/tcp 2^>/dev/null ^|^| true
echo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT 2^>/dev/null ^|^| true
echo.
echo # 进入项目目录
echo cd /opt/meditation-app
echo.
echo # 重新启动服务
echo echo "🚀 重新启动服务..."
echo pkill -f "uvicorn\|app.py" 2^>/dev/null ^|^| true
echo sleep 3
echo.
echo # 激活虚拟环境并启动
echo source venv/bin/activate
echo nohup python app.py ^> app.log 2^>^&1 ^&
echo service_pid=$!
echo echo $service_pid ^> app.pid
echo echo "✅ 服务已启动，PID: $service_pid"
echo.
echo # 等待服务启动
echo sleep 10
echo.
echo # 验证服务
echo echo "🔍 验证服务状态..."
echo if curl -s http://localhost:8000/health ^> /dev/null; then
echo     echo "✅ 本地服务正常"
echo     echo "🌐 服务地址: http://43.142.57.91:8000"
echo     
echo     # 检查网络配置
echo     echo "📡 网络配置检查:"
echo     echo "监听端口: \$(netstat -tulpn ^| grep :8000)"
echo     echo "进程状态: \$(ps aux ^| grep python ^| grep -v grep)"
echo     
echo else
echo     echo "❌ 服务启动失败，查看日志:"
echo     tail -20 app.log
echo fi

echo ========================================
echo.

echo 📝 执行建议:
echo ----------------------------------------
echo 1. **首先尝试方案1** (开放安全组端口)
echo 2. 如果方案1无效，复制方案2脚本到Web终端执行
echo 3. 执行后等待5-10分钟
echo 4. 访问 http://43.142.57.91:8000 测试
echo.

echo 🔍 常见云服务商安全组设置:
echo ----------------------------------------
echo • 阿里云: ECS控制台 → 安全组 → 配置规则 → 添加安全组规则
echo • 腾讯云: CVM控制台 → 安全组 → 入站规则 → 添加规则  
echo • 华为云: ECS控制台 → 安全组 → 入方向规则 → 添加规则
echo.

echo ============================================
echo 🎯 修复完成后请访问: http://43.142.57.91:8000
echo ============================================
pause
