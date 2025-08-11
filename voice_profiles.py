#!/usr/bin/env python3
"""
语音配置模块
根据用户情绪智能选择最适合的TTS语音配置
"""

from typing import Dict, List
import re


# 语音配置数据
VOICE_PROFILES = {
    "zh-CN-XiaoxiaoNeural": {
        "name": "晓晓",
        "gender": "female",
        "style": "温柔甜美",
        "description": "年轻女性，声音甜美温柔，适合放松和冥想",
        "emotions": ["calm", "happy", "gentle", "peaceful"],
        "default_rate": "-40%",
        "default_pitch": "-10Hz"
    },
    "zh-CN-XiaoyiNeural": {
        "name": "晓伊", 
        "gender": "female",
        "style": "温柔自然",
        "description": "温柔自然的女声，特别适合冥想和放松场景",
        "emotions": ["stressed", "anxious", "sad", "tired"],
        "default_rate": "-25%",
        "default_pitch": "-8Hz"
    },
    "zh-CN-XiaochenNeural": {
        "name": "晓辰",
        "gender": "female",
        "style": "成熟温暖",
        "description": "成熟女性，声音温暖治愈，适合深度情感疗愈",
        "emotions": ["sad", "healing", "deep", "motherly"],
        "default_rate": "-35%",
        "default_pitch": "-12Hz"
    },
    "zh-CN-XiaomoNeural": {
        "name": "晓墨",
        "gender": "female", 
        "style": "知性优雅",
        "description": "知性女声，声音优雅沉静，适合正念冥想",
        "emotions": ["focused", "mindful", "elegant"],
        "default_rate": "-28%",
        "default_pitch": "-6Hz"
    },
    "zh-CN-YunxiNeural": {
        "name": "云希",
        "gender": "male", 
        "style": "沉稳温和",
        "description": "年轻男性，声音沉稳温和，适合深度冥想",
        "emotions": ["neutral", "focused", "deep"],
        "default_rate": "-20%",
        "default_pitch": "-5Hz"
    },
    "zh-CN-YunyangNeural": {
        "name": "云扬",
        "gender": "male",
        "style": "成熟稳重", 
        "description": "成熟男性，声音稳重有力，适合引导式冥想",
        "emotions": ["confident", "guided", "structured"],
        "default_rate": "-15%",
        "default_pitch": "-3Hz"
    },
    "zh-CN-YunxiaNeural": {
        "name": "云夏",
        "gender": "male",
        "style": "温润如玉",
        "description": "温润男声，声音如春风化雨，适合治愈系冥想",
        "emotions": ["healing", "gentle", "warm"],
        "default_rate": "-25%",
        "default_pitch": "-8Hz"
    }
}


def analyze_emotion_from_text(text: str) -> str:
    """
    从文本中分析情绪
    
    Args:
        text: 用户输入的文本
        
    Returns:
        检测到的情绪标签
    """
    text_lower = text.lower()
    
    # 情绪关键词映射
    emotion_keywords = {
        "stressed": ["压力", "紧张", "焦虑", "忙碌", "累", "疲惫", "困难", "问题"],
        "anxious": ["担心", "不安", "恐惧", "害怕", "紧张", "焦虑", "不确定"],
        "sad": ["伤心", "难过", "沮丧", "失落", "孤独", "痛苦", "悲伤", "失望"],
        "tired": ["疲惫", "累", "困", "乏", "疲倦", "疲劳", "精疲力竭"],
        "angry": ["生气", "愤怒", "气愤", "不满", "恼火", "烦躁"],
        "happy": ["开心", "高兴", "快乐", "愉快", "兴奋", "喜悦"],
        "calm": ["平静", "放松", "冷静", "安静", "宁静", "舒缓"],
        "neutral": ["一般", "普通", "正常", "还好", "可以"]
    }
    
    # 计算每种情绪的匹配度
    emotion_scores = {}
    for emotion, keywords in emotion_keywords.items():
        score = sum(1 for keyword in keywords if keyword in text_lower)
        if score > 0:
            emotion_scores[emotion] = score
    
    # 返回得分最高的情绪，如果没有匹配则返回neutral
    if emotion_scores:
        return max(emotion_scores.items(), key=lambda x: x[1])[0]
    else:
        return "neutral"


def get_voice_by_emotion(user_input: str) -> Dict[str, str]:
    """
    根据用户输入的情绪选择最适合的语音配置
    
    Args:
        user_input: 用户输入的文本
        
    Returns:
        包含语音配置的字典
    """
    # 分析情绪
    detected_emotion = analyze_emotion_from_text(user_input)
    
    # 为不同情绪选择最适合的语音
    emotion_voice_mapping = {
        "stressed": "zh-CN-XiaoxiaoNeural",  # 甜美温柔，适合压力缓解  
        "anxious": "zh-CN-XiaoxiaoNeural",   # 甜美温柔，适合焦虑缓解
        "sad": "zh-CN-XiaoxiaoNeural",       # 甜美温柔，适合安慰
        "tired": "zh-CN-XiaoxiaoNeural",     # 甜美温柔，适合放松
        "angry": "zh-CN-XiaoxiaoNeural",     # 甜美温柔，适合平复情绪
        "happy": "zh-CN-XiaoxiaoNeural",     # 甜美温柔，保持愉悦
        "calm": "zh-CN-XiaoxiaoNeural",      # 甜美温柔，保持平静
        "neutral": "zh-CN-XiaoxiaoNeural",   # 甜美温柔，适合一般冥想
        "confident": "zh-CN-XiaoxiaoNeural", # 甜美温柔，适合自信建立
        "focused": "zh-CN-XiaoxiaoNeural",   # 甜美温柔，适合专注训练
        "deep": "zh-CN-XiaoxiaoNeural",      # 甜美温柔，适合深度冥想
        "guided": "zh-CN-XiaoxiaoNeural"     # 甜美温柔，适合引导冥想
    }
    
    # 选择语音
    selected_voice = emotion_voice_mapping.get(detected_emotion, "zh-CN-XiaoxiaoNeural")
    voice_profile = VOICE_PROFILES[selected_voice]
    
    return {
        "voice": selected_voice,
        "rate": voice_profile["default_rate"],
        "pitch": voice_profile["default_pitch"],
        "emotion": detected_emotion,
        "description": voice_profile["description"],
        "name": voice_profile["name"]
    }


def get_all_voices() -> Dict[str, Dict]:
    """
    获取所有可用的语音配置
    
    Returns:
        所有语音配置的字典
    """
    return VOICE_PROFILES


def test_voice_selection():
    """测试语音选择功能"""
    test_cases = [
        "我最近工作压力很大，总是睡不好",
        "我感到很焦虑，不知道该怎么办",  
        "今天心情不错，想放松一下",
        "我觉得很累，需要休息",
        "心情一般，想做个冥想",
        "我很生气，需要冷静下来"
    ]
    
    print("🎙️ 语音选择测试")
    print("=" * 50)
    
    for i, text in enumerate(test_cases, 1):
        voice_config = get_voice_by_emotion(text)
        print(f"\n测试 {i}:")
        print(f"  输入: {text}")
        print(f"  检测情绪: {voice_config['emotion']}")
        print(f"  选择语音: {voice_config['name']} ({voice_config['voice']})")
        print(f"  语音描述: {voice_config['description']}")
        print(f"  语速: {voice_config['rate']}, 音调: {voice_config['pitch']}")


if __name__ == "__main__":
    test_voice_selection()
