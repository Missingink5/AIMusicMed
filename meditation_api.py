"""
FastAPI版冥想应用Web服务
提供RESTful API接口
"""

import os
import asyncio
import logging
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# 导入冥想应用核心模块
from py313_meditation_app import MeditationApp, MeditationAppError
from config_manager import load_config, AppConfig


# === Pydantic模型定义 ===

class MeditationRequest(BaseModel):
    """冥想会话请求模型"""
    user_input: str = Field(..., description="用户倾诉内容", min_length=1, max_length=1000)
    duration_minutes: Optional[int] = Field(default=3, description="冥想时长(分钟)", ge=1, le=30)
    cleanup: Optional[bool] = Field(default=True, description="是否清理临时文件")
    voice_preference: Optional[str] = Field(default=None, description="语音偏好(可选)")

class MeditationResponse(BaseModel):
    """冥想会话响应模型"""
    session_id: str = Field(..., description="会话ID")
    status: str = Field(..., description="状态: success, processing, error")
    message: str = Field(..., description="响应消息")
    audio_url: Optional[str] = Field(default=None, description="音频文件URL")
    duration_seconds: Optional[float] = Field(default=None, description="实际时长(秒)")
    comfort_message: Optional[str] = Field(default=None, description="安慰语")
    segments_count: Optional[int] = Field(default=None, description="音频段落数")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")

class SessionStatus(BaseModel):
    """会话状态查询响应"""
    session_id: str
    status: str  # processing, completed, error, not_found
    progress: Optional[int] = Field(default=None, description="进度百分比 0-100")
    message: Optional[str] = Field(default=None)
    result: Optional[MeditationResponse] = Field(default=None)

class AppStatus(BaseModel):
    """应用状态响应"""
    status: str
    version: str
    python_version: str
    ai_models_loaded: bool
    active_sessions: int
    total_sessions: int
    uptime_seconds: float
    config_summary: Dict[str, Any]


# === FastAPI应用初始化 ===

app = FastAPI(
    title="AI冥想助手API",
    description="基于AI的个性化冥想音频生成服务",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === 全局变量和状态管理 ===

# 应用启动时间
app_start_time = datetime.now()

# 会话存储
active_sessions: Dict[str, Dict] = {}
completed_sessions: Dict[str, MeditationResponse] = {}

# 冥想应用实例
meditation_app: Optional[MeditationApp] = None
app_config: Optional[AppConfig] = None

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# === 启动和关闭事件 ===

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    global meditation_app, app_config
    
    try:
        logger.info("正在启动AI冥想助手API服务...")
        
        # 加载配置
        app_config = load_config()
        
        # 创建冥想应用实例
        meditation_app = MeditationApp(app_config)
        
        # 创建静态文件目录
        static_dir = Path(app_config.paths.base_dir) / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        
        # 挂载静态文件服务
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        
        logger.info("AI冥想助手API服务启动成功")
        
    except Exception as e:
        logger.error(f"应用启动失败: {e}")
        raise e

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    logger.info("正在关闭AI冥想助手API服务...")
    
    # 清理活跃会话
    global active_sessions
    active_sessions.clear()
    
    logger.info("AI冥想助手API服务已关闭")


# === 工具函数 ===

def generate_session_id() -> str:
    """生成会话ID"""
    return str(uuid.uuid4())[:8]

def get_uptime_seconds() -> float:
    """获取应用运行时间"""
    return (datetime.now() - app_start_time).total_seconds()

async def process_meditation_session(session_id: str, request: MeditationRequest):
    """后台处理冥想会话生成"""
    try:
        # 更新状态为处理中
        active_sessions[session_id]["status"] = "processing"
        active_sessions[session_id]["progress"] = 10
        
        # 生成冥想会话
        audio_file_path, session_info = await meditation_app.create_meditation_session(
            user_input=request.user_input,
            duration_minutes=request.duration_minutes,
            cleanup=request.cleanup
        )
        
        active_sessions[session_id]["progress"] = 90
        
        # 移动音频文件到静态目录
        static_dir = Path(app_config.paths.base_dir) / "static"
        static_file_name = f"meditation_{session_id}.wav"
        static_file_path = static_dir / static_file_name
        
        # 复制文件到静态目录
        import shutil
        shutil.copy2(audio_file_path, static_file_path)
        
        # 构建音频URL
        audio_url = f"/static/{static_file_name}"
        
        # 创建响应对象
        response = MeditationResponse(
            session_id=session_id,
            status="success",
            message="冥想音频生成成功",
            audio_url=audio_url,
            duration_seconds=session_info.get("total_duration_seconds"),
            comfort_message=session_info.get("comfort"),
            segments_count=session_info.get("generated_segments"),
            created_at=datetime.now()
        )
        
        # 保存到完成会话
        completed_sessions[session_id] = response
        
        # 从活跃会话中移除
        if session_id in active_sessions:
            del active_sessions[session_id]
        
        logger.info(f"会话 {session_id} 处理完成")
        
    except Exception as e:
        logger.error(f"会话 {session_id} 处理失败: {e}")
        
        # 更新为错误状态
        if session_id in active_sessions:
            active_sessions[session_id]["status"] = "error"
            active_sessions[session_id]["error"] = str(e)


# === API路由 ===

@app.get("/", response_model=Dict[str, str])
async def root():
    """根路径欢迎信息"""
    return {
        "message": "欢迎使用AI冥想助手API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "/status"
    }

@app.get("/status", response_model=AppStatus)
async def get_app_status():
    """获取应用状态"""
    try:
        ai_models_loaded = meditation_app is not None and hasattr(meditation_app, 'music_model')
        
        config_summary = {
            "ai_music_enabled": getattr(app_config.audio, 'enable_ai_music', True),
            "high_quality_music": getattr(app_config.audio, 'use_high_quality_music', False),
            "default_duration": app_config.meditation.default_duration_minutes,
            "max_duration": app_config.meditation.max_duration_minutes,
        } if app_config else {}
        
        return AppStatus(
            status="running",
            version="1.0.0",
            python_version="3.13",
            ai_models_loaded=ai_models_loaded,
            active_sessions=len(active_sessions),
            total_sessions=len(completed_sessions),
            uptime_seconds=get_uptime_seconds(),
            config_summary=config_summary
        )
        
    except Exception as e:
        logger.error(f"获取应用状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {e}")

@app.post("/meditation/create", response_model=MeditationResponse)
async def create_meditation_session(
    request: MeditationRequest,
    background_tasks: BackgroundTasks
):
    """创建冥想会话（异步处理）"""
    try:
        # 验证输入
        if not request.user_input.strip():
            raise HTTPException(status_code=400, detail="用户倾诉内容不能为空")
        
        # 生成会话ID
        session_id = generate_session_id()
        
        # 记录到活跃会话
        active_sessions[session_id] = {
            "request": request,
            "status": "queued",
            "progress": 0,
            "created_at": datetime.now()
        }
        
        # 添加后台任务
        background_tasks.add_task(process_meditation_session, session_id, request)
        
        # 立即返回会话信息
        response = MeditationResponse(
            session_id=session_id,
            status="processing",
            message="冥想音频正在生成中，请稍候查询状态",
            created_at=datetime.now()
        )
        
        logger.info(f"创建冥想会话: {session_id}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建冥想会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建会话失败: {e}")

@app.post("/meditation/create-sync", response_model=MeditationResponse)
async def create_meditation_session_sync(request: MeditationRequest):
    """创建冥想会话（同步处理）"""
    try:
        # 验证输入
        if not request.user_input.strip():
            raise HTTPException(status_code=400, detail="用户倾诉内容不能为空")
        
        # 生成会话ID
        session_id = generate_session_id()
        
        logger.info(f"开始同步创建冥想会话: {session_id}")
        
        # 直接生成冥想会话
        audio_file_path, session_info = await meditation_app.create_meditation_session(
            user_input=request.user_input,
            duration_minutes=request.duration_minutes,
            cleanup=request.cleanup
        )
        
        # 移动音频文件到静态目录
        static_dir = Path(app_config.paths.base_dir) / "static"
        static_file_name = f"meditation_{session_id}.wav"
        static_file_path = static_dir / static_file_name
        
        # 复制文件到静态目录
        import shutil
        shutil.copy2(audio_file_path, static_file_path)
        
        # 构建音频URL
        audio_url = f"/static/{static_file_name}"
        
        # 创建响应对象
        response = MeditationResponse(
            session_id=session_id,
            status="success",
            message="冥想音频生成成功",
            audio_url=audio_url,
            duration_seconds=session_info.get("total_duration_seconds"),
            comfort_message=session_info.get("comfort"),
            segments_count=session_info.get("generated_segments"),
            created_at=datetime.now()
        )
        
        # 保存到完成会话
        completed_sessions[session_id] = response
        
        logger.info(f"同步创建冥想会话完成: {session_id}")
        return response
        
    except HTTPException:
        raise
    except MeditationAppError as e:
        logger.error(f"冥想应用错误: {e}")
        raise HTTPException(status_code=500, detail=f"冥想应用错误: {e}")
    except Exception as e:
        logger.error(f"创建冥想会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建会话失败: {e}")

@app.get("/meditation/status/{session_id}", response_model=SessionStatus)
async def get_session_status(session_id: str):
    """查询会话状态"""
    try:
        # 检查是否在活跃会话中
        if session_id in active_sessions:
            session_data = active_sessions[session_id]
            return SessionStatus(
                session_id=session_id,
                status=session_data["status"],
                progress=session_data.get("progress", 0),
                message=session_data.get("error", "正在处理中...")
            )
        
        # 检查是否在完成会话中
        if session_id in completed_sessions:
            completed_session = completed_sessions[session_id]
            return SessionStatus(
                session_id=session_id,
                status="completed",
                progress=100,
                message="会话处理完成",
                result=completed_session
            )
        
        # 会话不存在
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询会话状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询状态失败: {e}")

@app.get("/meditation/download/{session_id}")
async def download_meditation_audio(session_id: str):
    """下载冥想音频文件"""
    try:
        # 检查会话是否存在且完成
        if session_id not in completed_sessions:
            raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在或未完成")
        
        # 获取音频文件路径
        session_data = completed_sessions[session_id]
        if not session_data.audio_url:
            raise HTTPException(status_code=404, detail="音频文件不存在")
        
        # 构建文件路径
        static_dir = Path(app_config.paths.base_dir) / "static"
        file_name = f"meditation_{session_id}.wav"
        file_path = static_dir / file_name
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="音频文件未找到")
        
        # 返回文件下载响应
        return FileResponse(
            path=str(file_path),
            filename=f"meditation_{session_id}.wav",
            media_type="audio/wav"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载音频文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"下载失败: {e}")

@app.get("/meditation/sessions", response_model=List[MeditationResponse])
async def list_completed_sessions(
    limit: int = Query(default=10, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(default=0, ge=0, description="偏移量")
):
    """获取已完成的会话列表"""
    try:
        # 获取所有完成的会话
        sessions = list(completed_sessions.values())
        
        # 按创建时间倒序排序
        sessions.sort(key=lambda x: x.created_at, reverse=True)
        
        # 应用分页
        paginated_sessions = sessions[offset:offset + limit]
        
        return paginated_sessions
        
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取会话列表失败: {e}")

@app.delete("/meditation/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话及其音频文件"""
    try:
        # 检查会话是否存在
        if session_id not in completed_sessions:
            raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
        
        # 删除音频文件
        static_dir = Path(app_config.paths.base_dir) / "static"
        file_name = f"meditation_{session_id}.wav"
        file_path = static_dir / file_name
        
        if file_path.exists():
            file_path.unlink()
        
        # 从会话记录中删除
        del completed_sessions[session_id]
        
        return {"message": f"会话 {session_id} 已删除"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除会话失败: {e}")

@app.post("/meditation/cleanup")
async def cleanup_old_sessions(
    older_than_hours: int = Query(default=24, ge=1, description="清理多少小时前的会话")
):
    """清理旧的会话文件"""
    try:
        current_time = datetime.now()
        deleted_count = 0
        
        # 查找需要删除的会话
        sessions_to_delete = []
        for session_id, session_data in completed_sessions.items():
            hours_diff = (current_time - session_data.created_at).total_seconds() / 3600
            if hours_diff >= older_than_hours:
                sessions_to_delete.append(session_id)
        
        # 删除旧会话
        for session_id in sessions_to_delete:
            try:
                # 删除音频文件
                static_dir = Path(app_config.paths.base_dir) / "static"
                file_path = static_dir / f"meditation_{session_id}.wav"
                if file_path.exists():
                    file_path.unlink()
                
                # 从记录中删除
                del completed_sessions[session_id]
                deleted_count += 1
                
            except Exception as e:
                logger.warning(f"删除会话 {session_id} 时出错: {e}")
        
        return {
            "message": f"清理完成，删除了 {deleted_count} 个旧会话",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        logger.error(f"清理旧会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理失败: {e}")


# === 健康检查端点 ===

@app.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        # 检查关键组件
        checks = {
            "api": "ok",
            "meditation_app": "ok" if meditation_app else "error",
            "config": "ok" if app_config else "error",
            "storage": "ok" if Path(app_config.paths.base_dir).exists() else "error"
        }
        
        # 检查是否有错误
        has_error = any(status == "error" for status in checks.values())
        
        return {
            "status": "error" if has_error else "healthy",
            "checks": checks,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# === 主程序入口 ===

if __name__ == "__main__":
    import uvicorn
    
    # 启动FastAPI服务器
    uvicorn.run(
        "meditation_api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
