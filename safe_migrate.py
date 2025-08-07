# -*- coding: utf-8 -*-
import os
import shutil
from pathlib import Path
from datetime import datetime

def migrate_safely():
    migration_plan = [{'source': 'C:\\Users\\34254\\AppData\\Local\\Temp', 'target': 'D:\\CacheMigration\\temp_files\\Temp', 'size': 3989136087, 'size_str': '3.7 GB', 'type': 'temp_files', 'priority': 'high'}, {'source': 'C:\\Users\\34254\\AppData\\Local\\Temp', 'target': 'D:\\CacheMigration\\temp_files\\Temp', 'size': 3989136087, 'size_str': '3.7 GB', 'type': 'temp_files', 'priority': 'high'}, {'source': 'C:\\Users\\34254\\.vscode\\extensions', 'target': 'D:\\CacheMigration\\vscode\\extensions', 'size': 1941467616, 'size_str': '1.8 GB', 'type': 'vscode', 'priority': 'high'}, {'source': 'C:\\Users\\34254\\AppData\\Local\\pip', 'target': 'D:\\CacheMigration\\python_caches\\pip', 'size': 734313105, 'size_str': '700.3 MB', 'type': 'python_cache', 'priority': 'medium'}, {'source': 'C:\\Users\\34254\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cache', 'target': 'D:\\CacheMigration\\browser_caches\\Cache', 'size': 321362759, 'size_str': '306.5 MB', 'type': 'browser_cache', 'priority': 'medium'}, {'source': 'C:\\Users\\34254\\AppData\\Roaming\\Code\\User\\workspaceStorage', 'target': 'D:\\CacheMigration\\vscode\\workspaceStorage', 'size': 178919886, 'size_str': '170.6 MB', 'type': 'vscode', 'priority': 'medium'}, {'source': 'C:\\Users\\34254\\.vscode\\extensions\\prisma.prisma-6.13.0\\node_modules', 'target': 'D:\\CacheMigration\\node_modules\\node_modules', 'size': 153597776, 'size_str': '146.5 MB', 'type': 'node_modules', 'priority': 'medium'}, {'source': 'C:\\Users\\34254\\.vscode\\extensions\\lokalise.i18n-ally-2.13.1\\node_modules', 'target': 'D:\\CacheMigration\\node_modules\\node_modules', 'size': 114033025, 'size_str': '108.8 MB', 'type': 'node_modules', 'priority': 'medium'}]
    
    print("🚀 开始安全迁移C盘文件到D盘...")
    print("=" * 50)
    
    success_count = 0
    total_saved = 0
    
    for i, item in enumerate(migration_plan[:5], 1):  # 前5个最大的
        source = Path(item['source'])
        target = Path(item['target'])
        
        print(f"\n📁 迁移项目 {i}: {source.name} ({item['size_str']})")
        
        if not source.exists():
            print(f"⚠️ 源目录不存在: {source}")
            continue
            
        try:
            # 创建目标目录
            target.parent.mkdir(parents=True, exist_ok=True)
            
            # 移动文件
            if source.is_dir():
                shutil.move(str(source), str(target))
            else:
                shutil.move(str(source), str(target))
                
            print(f"✅ 迁移成功: {source.name}")
            success_count += 1
            total_saved += item['size']
            
        except Exception as e:
            print(f"❌ 迁移失败: {source.name} - {e}")
    
    print(f"\n🎉 迁移完成!")
    print(f"📊 成功迁移: {success_count} 项")
    print(f"💾 释放空间: {total_saved / (1024**3):.1f} GB")

if __name__ == "__main__":
    migrate_safely()
