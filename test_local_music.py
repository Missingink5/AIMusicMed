#!/usr/bin/env python3
"""
测试本地音乐库功能

这个脚本用于测试 LocalMusicLibrary 类的功能，
包括情绪分析、音乐文件扫描和选择等。
"""

import os
import sys
from local_music_library import LocalMusicLibrary

def test_local_music_library():
    """测试本地音乐库功能"""
    
    print("🎵 测试本地音乐库功能")
    print("=" * 50)
    
    # 创建本地音乐库实例
    music_lib = LocalMusicLibrary("music_library")
    
    # 1. 测试库状态
    print("\n📊 1. 检查音乐库状态:")
    status = music_lib.get_library_status()
    print(f"库状态: {status}")
    total_files = sum(status.values())
    print(f"总文件数: {total_files}")
    
    # 2. 测试情绪分析
    print("\n🧠 2. 测试情绪分析:")
    test_texts = [
        "我今天很开心，一切都很顺利",
        "我感到很愤怒，什么都不顺",
        "我有点担心明天的考试",
        "今天很放松，内心很平静",
        "我觉得有些沮丧",
        "我为自己的成就感到骄傲",
        "和朋友在一起很温暖"
    ]
    
    for text in test_texts:
        emotion = music_lib.analyze_user_emotion(text)
        print(f"文本: '{text}' -> 情绪: {emotion}")
    
    # 3. 测试音乐选择
    print("\n🎼 3. 测试音乐选择:")
    for emotion in ["平静", "喜悦", "忧郁", "焦虑"]:
        music_path = music_lib.get_music_for_emotion(emotion, 60)  # 60秒
        if music_path:
            print(f"情绪 '{emotion}' -> 音乐: {os.path.basename(music_path)}")
        else:
            print(f"情绪 '{emotion}' -> 无音乐文件")
    
    # 4. 测试库扫描
    print("\n🔍 4. 测试库扫描:")
    music_lib.scan_library()
    new_status = music_lib.get_library_status()
    print(f"扫描后状态: {new_status}")
    
    print("\n✅ 测试完成!")

def create_demo_audio_files():
    """提供音乐文件添加说明（不自动创建文件）"""
    
    print("\n📁 本地音乐库文件添加说明...")
    print("=" * 50)
    print("本地音乐库需要您手动添加音乐文件，不会自动生成任何文件。")
    print("\n📂 请在以下目录中添加您喜欢的音乐文件：")
    
    emotions_info = {
        "Quiet": "平静、冥想、放松类音乐",
        "Happy": "欢快、积极、振奋类音乐", 
        "Sad": "悲伤、抒情、治愈类音乐",
        "Anxiety": "舒缓、安抚、减压类音乐",
        "Hostility": "缓和、平复、宁静类音乐",
        "Pride": "自信、成就、激励类音乐",
        "Love": "温暖、关爱、友善类音乐"
    }
    
    for emotion, description in emotions_info.items():
        emotion_dir = os.path.join("music_library", emotion)
        print(f"  📁 {emotion_dir}/")
        print(f"     适合: {description}")
        
        # 检查目录中已有的文件
        if os.path.exists(emotion_dir):
            files = [f for f in os.listdir(emotion_dir) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.flac', '.ogg'))]
            if files:
                print(f"     当前有 {len(files)} 个音乐文件")
            else:
                print(f"     当前为空，请添加音乐文件")
        else:
            print(f"     目录不存在，请先创建")
        print()
    
    print("💡 建议的音乐文件格式：")
    print("  - 格式：MP3, WAV, M4A, FLAC, OGG")
    print("  - 时长：30秒 - 3分钟")
    print("  - 质量：128-320 kbps")
    print("  - 数量：每个情绪目录 5-20 首")
    
    print("\n✅ 音乐库说明完成！请手动添加您的音乐文件。")

if __name__ == "__main__":
    print("🎵 本地音乐库测试程序")
    print("=" * 60)
    
    # 检查音乐库目录是否存在
    if not os.path.exists("music_library"):
        print("❌ music_library 目录不存在!")
        sys.exit(1)
    
    # 运行测试
    test_local_music_library()
    
    # 询问是否查看音乐文件添加说明
    print("\n" + "=" * 60)
    response = input("是否查看音乐文件添加说明？(y/n): ").lower().strip()
    if response in ['y', 'yes', '是']:
        create_demo_audio_files()
        print("\n重新测试音乐库:")
        test_local_music_library()
