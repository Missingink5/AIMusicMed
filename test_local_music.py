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
    """创建一些演示音频文件（静音文件）"""
    
    print("\n🎵 创建演示音频文件...")
    
    try:
        from audio_compat import AudioSegment
    except ImportError:
        print("❌ 无法导入 AudioSegment，跳过音频文件创建")
        return
    
    # 创建一些简短的静音音频文件作为演示
    emotions = ["Quiet", "Happy", "Sad", "Anxiety", "Hostility", "Pride", "Love"]
    
    for emotion in emotions:
        emotion_dir = os.path.join("music_library", emotion)
        
        # 为每种情绪创建2-3个演示文件
        for i in range(3):
            filename = f"demo_{emotion}_{i+1}.wav"
            file_path = os.path.join(emotion_dir, filename)
            
            if not os.path.exists(file_path):
                # 创建30秒的静音音频作为演示
                silence = AudioSegment.silent(duration=30000)  # 30秒
                silence.export(file_path, format="wav")
                print(f"  ✓ 创建: {file_path}")
    
    print("✅ 演示音频文件创建完成!")

if __name__ == "__main__":
    print("🎵 本地音乐库测试程序")
    print("=" * 60)
    
    # 检查音乐库目录是否存在
    if not os.path.exists("music_library"):
        print("❌ music_library 目录不存在!")
        sys.exit(1)
    
    # 运行测试
    test_local_music_library()
    
    # 询问是否创建演示文件
    print("\n" + "=" * 60)
    response = input("是否创建演示音频文件？(y/n): ").lower().strip()
    if response in ['y', 'yes', '是']:
        create_demo_audio_files()
        print("\n重新测试音乐库:")
        test_local_music_library()
