"""
简化的冥想应用使用脚本
运行此脚本来创建个性化冥想会话
"""

import asyncio
from complete_meditation_app import MeditationApp

async def create_session():
    """
    创建冥想会话的简单接口
    """
    print("🧘‍♀️ 欢迎使用 AI 冥想助手")
    print("=" * 50)
    
    # 配置
    DEEPSEEK_API_KEY = "sk-9ec64e20ae244fc8aa7fac849d49e5e2"
    
    # 用户输入（您可以修改这里）
    user_inputs = [
        "我最近总是失眠，而且觉得压力很大，什么都做不好。",
        "工作上遇到了很多挫折，感觉很焦虑，需要放松一下。",
        "最近心情很低落，希望能找到内心的平静。"
    ]
    
    print("请选择您的情况，或者输入自定义内容：")
    for i, text in enumerate(user_inputs, 1):
        print(f"{i}. {text}")
    print("4. 自定义输入")
    
    try:
        choice = input("\n请输入选择 (1-4): ").strip()
        
        if choice == "4":
            user_input = input("请描述您当前的心情或困扰: ").strip()
            if not user_input:
                print("❌ 输入为空，使用默认示例")
                user_input = user_inputs[0]
        elif choice in ["1", "2", "3"]:
            user_input = user_inputs[int(choice) - 1]
        else:
            print("使用默认示例")
            user_input = user_inputs[0]
        
        # 询问时长
        duration_input = input("请输入冥想时长 (分钟，默认3分钟): ").strip()
        try:
            duration = int(duration_input) if duration_input else 3
            duration = max(1, min(10, duration))  # 限制在1-10分钟
        except ValueError:
            duration = 3
        
        print(f"\n📝 您的倾诉: {user_input}")
        print(f"⏰ 冥想时长: {duration} 分钟")
        print("\n开始生成您的个性化冥想会话...")
        
        # 创建应用并生成会话
        app = MeditationApp(DEEPSEEK_API_KEY)
        output_file = await app.create_meditation_session(
            user_input=user_input,
            duration_minutes=duration,
            cleanup=True
        )
        
        print(f"\n🎉 恭喜！您的冥想音频已生成完成")
        print(f"📁 文件位置: {output_file}")
        print(f"\n💡 提示: 请使用耳机或音响播放，找一个安静舒适的地方开始您的冥想之旅")
        
    except KeyboardInterrupt:
        print("\n\n👋 程序已退出")
    except Exception as e:
        print(f"\n❌ 生成过程中出现错误: {e}")
        print("请检查网络连接和 API 密钥设置")

if __name__ == "__main__":
    asyncio.run(create_session())
