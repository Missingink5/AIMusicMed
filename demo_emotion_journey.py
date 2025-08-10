#!/usr/bin/env python3
"""
情绪转换冥想系统演示（离线功能）
展示系统的核心功能，不依赖API调用
"""

from py313_meditation_app import MeditationApp

def demo_emotion_journey():
    print("🎭 情绪转换冥想系统演示")
    print("=" * 50)
    
    try:
        app = MeditationApp()
        
        test_cases = [
            {
                "input": "我最近工作压力特别大，总是失眠，心里很焦虑，希望能找到内心的平静。",
                "description": "焦虑压力状态"
            },
            {
                "input": "失恋了，心情很低落，觉得生活没有意义，感到很悲伤。",
                "description": "悲伤低落状态"
            },
            {
                "input": "和同事发生了激烈争吵，现在很生气，想要发泄这种愤怒情绪。",
                "description": "愤怒敌意状态"
            },
            {
                "input": "今天心情不错，感觉挺好的，想要更加平静安宁一些。",
                "description": "平静状态"
            }
        ]
        
        for i, case in enumerate(test_cases, 1):
            print(f"\n📝 案例 {i}: {case['description']}")
            print(f"💭 用户倾诉: {case['input']}")
            print()
            
            # 1. 情绪分析
            emotion = app.local_music_lib.analyze_user_emotion(case['input'])
            print(f"🧠 情绪分析结果: {emotion}")
            
            # 2. 情绪转换计划
            journey = app.plan_emotion_journey(case['input'], 8)  # 8分钟
            path = " → ".join([stage["emotion_cn"] for stage in journey])
            print(f"🗺️ 转换路径: {path}")
            
            # 3. 时长分配
            print("⏱️ 时间分配:")
            for stage in journey:
                print(f"   阶段{stage['stage']}: {stage['emotion_cn']} ({stage['duration']}秒) - {stage['description']}")
            
            # 4. 音乐选择演示
            print("🎵 音乐选择:")
            for stage in journey:
                emotion_en = stage['emotion_en']
                music_file = app.local_music_lib.get_music_for_emotion_english(emotion_en, 60)
                if music_file:
                    import os
                    filename = os.path.basename(music_file)
                    print(f"   {stage['emotion_cn']}音乐: {filename}")
                else:
                    print(f"   {stage['emotion_cn']}音乐: 无可用文件")
            
            print("-" * 40)
        
        # 系统状态总结
        print(f"\n📊 系统状态:")
        music_status = app.local_music_lib.get_library_status()
        total_music = sum(music_status.values())
        print(f"🎵 音乐库: {total_music}首音乐，{len(music_status)}种情绪分类")
        print(f"🎭 转换路径: 消极→中性→积极")
        print(f"⚙️ 智能时长分配: 根据情绪状态动态调整")
        print(f"🔄 同步引导: 音乐与冥想指导语完全同步")
        
        print(f"\n✅ 离线功能演示完成!")
        print(f"💡 提示: 完整体验需要配置DeepSeek API来生成个性化冥想引导语")
        
    except Exception as e:
        print(f"❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    demo_emotion_journey()
