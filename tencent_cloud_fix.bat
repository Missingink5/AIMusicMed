@echo off
chcp 65001 > nul
echo ============================================
echo    🔧 腾讯云安全组配置指南 - 开放8000端口
echo ============================================
echo.

echo 📊 问题确诊:
echo ✅ AI冥想助手已成功部署到服务器
echo ✅ 服务器网络连通正常 (Ping: 7ms)
echo ❌ 8000端口被腾讯云安全组阻挡
echo.

echo 🎯 解决方案: 配置腾讯云安全组
echo ========================================
echo.

echo 🔧 腾讯云安全组配置步骤:
echo ----------------------------------------
echo.
echo 1. 登录腾讯云控制台
echo    网址: https://console.cloud.tencent.com/
echo.
echo 2. 进入云服务器 CVM 控制台
echo    导航: 产品 → 云服务器 → 实例
echo.
echo 3. 找到您的服务器实例
echo    IP地址: 43.142.57.91
echo    (点击实例ID或IP进入详情页)
echo.
echo 4. 配置安全组
echo    点击 "安全组" 选项卡
echo    或点击右侧 "更多" → "安全组" → "配置安全组"
echo.
echo 5. 编辑安全组规则
echo    点击安全组ID (如: sg-xxxxxxxx)
echo    选择 "入站规则" 选项卡
echo    点击 "添加规则"
echo.
echo 6. 添加8000端口规则
echo    --------------------------------
echo    类型: 自定义
echo    来源: 0.0.0.0/0 (所有IP)
echo    协议端口: TCP:8000
echo    策略: 允许
echo    备注: AI冥想助手Web端口
echo    --------------------------------
echo    点击 "完成" 保存规则
echo.
echo 7. 等待生效 (通常30秒内)
echo.

echo 🚀 快速配置链接:
echo ----------------------------------------
echo 腾讯云CVM控制台:
echo https://console.cloud.tencent.com/cvm/instance
echo.
echo 安全组管理:
echo https://console.cloud.tencent.com/cvm/securitygroup
echo.

echo 📱 移动端配置:
echo ----------------------------------------
echo 1. 下载腾讯云APP
echo 2. 登录后选择 "云服务器"
echo 3. 找到IP为 43.142.57.91 的实例
echo 4. 点击 "安全组" → "配置规则"
echo 5. 添加入站规则: TCP:8000, 来源:0.0.0.0/0
echo.

echo 🔍 配置验证:
echo ----------------------------------------
echo 配置完成后，请等待30秒，然后访问:
echo.
echo   🌐 主页: http://43.142.57.91:8000
echo   📚 API文档: http://43.142.57.91:8000/docs
echo   🔍 健康检查: http://43.142.57.91:8000/health
echo.
echo 如果仍无法访问，请检查:
echo • 安全组规则是否正确配置
echo • 是否选择了正确的安全组
echo • 规则是否已生效 (等待1-2分钟)
echo.

echo 💡 腾讯云常见安全组模板:
echo ----------------------------------------
echo 如果您想使用预设模板:
echo.
echo 1. 在安全组页面点击 "新建"
echo 2. 选择 "自定义" 模板
echo 3. 或者选择 "放通全部端口" (不推荐生产环境)
echo 4. 将新安全组绑定到您的CVM实例
echo.

echo ⚠️  安全提示:
echo ----------------------------------------
echo 当前配置允许所有IP访问8000端口
echo 如需更高安全性，可以限制来源IP:
echo • 仅允许您的IP: [您的公网IP]/32
echo • 仅允许特定网段: 如 192.168.1.0/24
echo.

echo 🆘 如果遇到问题:
echo ----------------------------------------
echo 1. 确认服务器实例状态为 "运行中"
echo 2. 检查安全组是否正确绑定到实例
echo 3. 尝试重启CVM实例
echo 4. 联系腾讯云技术支持
echo.

echo ============================================
echo 🎯 配置完成后立即访问: 
echo    http://43.142.57.91:8000
echo ============================================
echo.
echo 📞 腾讯云技术支持: 95716
echo 📚 腾讯云文档: https://cloud.tencent.com/document/product/213/12452
echo.

pause
