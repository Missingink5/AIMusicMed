# Windows到Linux服务器部署脚本
param(
    [Parameter(Mandatory=$true)]
    [string]$ServerIP,
    
    [string]$Username = "root",
    
    [string]$ProjectName = "meditation-app"
)

# 颜色输出函数
function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    
    switch($Color) {
        "Red" { Write-Host $Message -ForegroundColor Red }
        "Green" { Write-Host $Message -ForegroundColor Green }
        "Yellow" { Write-Host $Message -ForegroundColor Yellow }
        "Blue" { Write-Host $Message -ForegroundColor Blue }
        "Cyan" { Write-Host $Message -ForegroundColor Cyan }
        default { Write-Host $Message }
    }
}

# 检查必需工具
function Test-RequiredTools {
    Write-ColorOutput "🔍 检查必需工具..." "Yellow"
    
    $tools = @("ssh", "scp")
    $missing = @()
    
    foreach ($tool in $tools) {
        try {
            & $tool 2>$null
        } catch {
            $missing += $tool
        }
    }
    
    if ($missing.Count -gt 0) {
        Write-ColorOutput "❌ 缺少工具: $($missing -join ', ')" "Red"
        Write-ColorOutput "请安装OpenSSH或Git Bash" "Yellow"
        Write-ColorOutput "下载地址: https://git-scm.com/download/win" "Blue"
        exit 1
    }
    
    Write-ColorOutput "✅ 工具检查完成" "Green"
}

# 测试服务器连接
function Test-ServerConnection {
    param([string]$Server, [string]$User)
    
    Write-ColorOutput "🔗 测试服务器连接..." "Yellow"
    
    try {
        $result = ssh -o ConnectTimeout=10 -o BatchMode=yes ${User}@${Server} "echo 'Connected'" 2>$null
        if ($result -eq "Connected") {
            Write-ColorOutput "✅ 服务器连接成功" "Green"
            return $true
        }
    } catch {
        Write-ColorOutput "❌ 服务器连接失败" "Red"
        Write-ColorOutput "请检查:" "Yellow"
        Write-ColorOutput "  1. 服务器IP地址是否正确" "White"
        Write-ColorOutput "  2. SSH服务是否启动" "White"
        Write-ColorOutput "  3. 防火墙是否开放22端口" "White"
        Write-ColorOutput "  4. SSH密钥或密码是否正确" "White"
        return $false
    }
}

# 准备部署文件
function Prepare-DeploymentFiles {
    Write-ColorOutput "📦 准备部署文件..." "Yellow"
    
    # 创建临时目录
    $tempDir = Join-Path $env:TEMP "meditation-deploy"
    if (Test-Path $tempDir) {
        Remove-Item $tempDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $tempDir | Out-Null
    
    # 要排除的文件和目录
    $excludePatterns = @(
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".git",
        ".vscode",
        "node_modules",
        "*.log",
        "temp\*",
        "cache\*",
        "backup\*"
    )
    
    # 复制项目文件（排除不需要的文件）
    Write-ColorOutput "复制项目文件..." "Cyan"
    $sourceFiles = Get-ChildItem -Path . -Recurse | Where-Object {
        $path = $_.FullName
        $shouldExclude = $false
        
        foreach ($pattern in $excludePatterns) {
            if ($path -like "*$pattern*") {
                $shouldExclude = $true
                break
            }
        }
        
        return -not $shouldExclude
    }
    
    foreach ($file in $sourceFiles) {
        $relativePath = $file.FullName.Substring((Get-Location).Path.Length + 1)
        $destPath = Join-Path $tempDir $relativePath
        
        if ($file.PSIsContainer) {
            New-Item -ItemType Directory -Path $destPath -Force | Out-Null
        } else {
            $destDir = Split-Path $destPath -Parent
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            Copy-Item $file.FullName $destPath
        }
    }
    
    # 压缩文件
    Write-ColorOutput "压缩项目文件..." "Cyan"
    $zipPath = Join-Path $env:TEMP "$ProjectName.zip"
    if (Test-Path $zipPath) {
        Remove-Item $zipPath -Force
    }
    
    Compress-Archive -Path "$tempDir\*" -DestinationPath $zipPath -CompressionLevel Optimal
    
    # 清理临时目录
    Remove-Item $tempDir -Recurse -Force
    
    Write-ColorOutput "✅ 文件准备完成: $zipPath" "Green"
    return $zipPath
}

# 上传文件到服务器
function Upload-Files {
    param([string]$ZipPath, [string]$Server, [string]$User)
    
    Write-ColorOutput "📤 上传文件到服务器..." "Yellow"
    
    try {
        # 上传压缩包
        scp $ZipPath ${User}@${Server}:/tmp/
        
        if ($LASTEXITCODE -eq 0) {
            Write-ColorOutput "✅ 文件上传成功" "Green"
            return $true
        } else {
            Write-ColorOutput "❌ 文件上传失败" "Red"
            return $false
        }
    } catch {
        Write-ColorOutput "❌ 上传过程中出错: $($_.Exception.Message)" "Red"
        return $false
    }
}

# 在服务器上执行部署
function Deploy-OnServer {
    param([string]$Server, [string]$User, [string]$ZipFileName)
    
    Write-ColorOutput "🚀 在服务器上执行部署..." "Yellow"
    
    $deployScript = @"
#!/bin/bash
set -e

echo "🔧 开始服务器端部署..."

# 创建项目目录
sudo mkdir -p /opt/$ProjectName
cd /tmp

# 解压项目文件
echo "📦 解压项目文件..."
sudo unzip -o $ZipFileName -d /opt/$ProjectName/

# 设置权限
sudo chown -R root:root /opt/$ProjectName
sudo chmod -R 755 /opt/$ProjectName

# 进入项目目录
cd /opt/$ProjectName

# 检查部署脚本
if [ -f "deploy.sh" ]; then
    sudo chmod +x deploy.sh
    echo "🎯 运行部署脚本..."
    sudo ./deploy.sh
else
    echo "⚠️  未找到deploy.sh，执行手动部署..."
    
    # 手动部署步骤
    echo "📥 更新系统包..."
    sudo apt update && sudo apt upgrade -y
    
    echo "🐳 安装Docker..."
    if ! command -v docker &> /dev/null; then
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo systemctl start docker
        sudo systemctl enable docker
    fi
    
    echo "🔧 安装Docker Compose..."
    if ! command -v docker-compose &> /dev/null; then
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
    fi
    
    echo "🚀 启动服务..."
    if [ -f "docker-compose.yml" ]; then
        sudo docker-compose up -d --build
    else
        echo "❌ 未找到docker-compose.yml文件"
        exit 1
    fi
fi

# 清理临时文件
sudo rm -f /tmp/$ZipFileName

echo "✅ 服务器端部署完成！"
"@

    try {
        # 将部署脚本写入临时文件
        $scriptPath = Join-Path $env:TEMP "deploy-script.sh"
        $deployScript | Out-File -FilePath $scriptPath -Encoding UTF8
        
        # 上传并执行部署脚本
        scp $scriptPath ${User}@${Server}:/tmp/deploy-script.sh
        ssh ${User}@${Server} "chmod +x /tmp/deploy-script.sh && /tmp/deploy-script.sh"
        
        # 清理临时脚本
        Remove-Item $scriptPath -Force
        
        if ($LASTEXITCODE -eq 0) {
            Write-ColorOutput "✅ 服务器部署成功" "Green"
            return $true
        } else {
            Write-ColorOutput "❌ 服务器部署失败" "Red"
            return $false
        }
    } catch {
        Write-ColorOutput "❌ 部署执行失败: $($_.Exception.Message)" "Red"
        return $false
    }
}

# 验证部署结果
function Test-Deployment {
    param([string]$Server)
    
    Write-ColorOutput "🔍 验证部署结果..." "Yellow"
    
    # 测试API健康检查
    try {
        $response = Invoke-WebRequest -Uri "http://${Server}:8000/health" -TimeoutSec 30 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-ColorOutput "✅ API服务正常运行" "Green"
        } else {
            Write-ColorOutput "⚠️  API服务状态异常: $($response.StatusCode)" "Yellow"
        }
    } catch {
        Write-ColorOutput "⚠️  API健康检查失败，可能服务还在启动中" "Yellow"
        Write-ColorOutput "请稍后手动访问: http://${Server}:8000/health" "Cyan"
    }
    
    # 测试Web界面
    try {
        $response = Invoke-WebRequest -Uri "http://${Server}" -TimeoutSec 30 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-ColorOutput "✅ Web界面可访问" "Green"
        }
    } catch {
        Write-ColorOutput "⚠️  Web界面访问失败，请检查Nginx配置" "Yellow"
    }
}

# 显示部署信息
function Show-DeploymentInfo {
    param([string]$Server)
    
    Write-ColorOutput "" "White"
    Write-ColorOutput "=======================================" "Green"
    Write-ColorOutput "🎉 AI冥想助手部署完成！" "Green"
    Write-ColorOutput "=======================================" "Green"
    Write-ColorOutput "" "White"
    
    Write-ColorOutput "🌐 访问地址:" "Blue"
    Write-ColorOutput "  主应用:    http://$Server" "White"
    Write-ColorOutput "  API文档:   http://$Server/docs" "White"
    Write-ColorOutput "  健康检查:  http://$Server/health" "White"
    Write-ColorOutput "" "White"
    
    Write-ColorOutput "🔧 管理命令 (在服务器上执行):" "Blue"
    Write-ColorOutput "  查看状态:  docker-compose ps" "White"
    Write-ColorOutput "  查看日志:  docker-compose logs -f" "White"
    Write-ColorOutput "  重启服务:  docker-compose restart" "White"
    Write-ColorOutput "  停止服务:  docker-compose down" "White"
    Write-ColorOutput "" "White"
    
    Write-ColorOutput "📁 重要路径:" "Blue"
    Write-ColorOutput "  项目目录:  /opt/$ProjectName" "White"
    Write-ColorOutput "  配置文件:  /opt/$ProjectName/config.json" "White"
    Write-ColorOutput "  日志目录:  /opt/$ProjectName/logs" "White"
    Write-ColorOutput "" "White"
    
    Write-ColorOutput "⚠️  注意事项:" "Yellow"
    Write-ColorOutput "  1. 请编辑配置文件设置API密钥" "White"
    Write-ColorOutput "  2. 生产环境建议配置SSL证书" "White"
    Write-ColorOutput "  3. 定期备份重要数据" "White"
    Write-ColorOutput "" "White"
}

# 主函数
function Main {
    Write-ColorOutput "======================================" "Cyan"
    Write-ColorOutput "🚀 AI冥想助手 - Windows部署工具" "Cyan"
    Write-ColorOutput "======================================" "Cyan"
    Write-ColorOutput "" "White"
    
    # 检查工具
    Test-RequiredTools
    
    # 测试连接
    if (-not (Test-ServerConnection -Server $ServerIP -User $Username)) {
        Write-ColorOutput "请解决连接问题后重试" "Red"
        exit 1
    }
    
    # 准备文件
    $zipPath = Prepare-DeploymentFiles
    $zipFileName = Split-Path $zipPath -Leaf
    
    try {
        # 上传文件
        if (-not (Upload-Files -ZipPath $zipPath -Server $ServerIP -User $Username)) {
            throw "文件上传失败"
        }
        
        # 服务器部署
        if (-not (Deploy-OnServer -Server $ServerIP -User $Username -ZipFileName $zipFileName)) {
            throw "服务器部署失败"
        }
        
        # 验证部署
        Test-Deployment -Server $ServerIP
        
        # 显示部署信息
        Show-DeploymentInfo -Server $ServerIP
        
    } finally {
        # 清理临时文件
        if (Test-Path $zipPath) {
            Remove-Item $zipPath -Force
        }
    }
}

# 脚本入口点
if ($MyInvocation.InvocationName -ne '.') {
    Main
}
