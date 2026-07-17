import Link from "next/link";
import { Brand } from "./components/brand";
import { ThemeToggle } from "./components/theme-toggle";

export default function Home() {
  return (
    <main className="landing">
      <nav className="public-nav" aria-label="主导航">
        <Brand />
        <div className="nav-actions"><ThemeToggle /><Link className="text-link" href="/login">受邀用户登录</Link><Link className="button small" href="/login">开始体验</Link></div>
      </nav>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow"><span className="pulse-dot" />为此刻的你生成</span>
          <h1>听见此刻，<br /><em>慢慢抵达</em>想去的情绪。</h1>
          <p>说说你现在的感受。AIMusicMed 会循着 ISO 情绪路径，为你准备一段专属的音乐冥想。</p>
          <div className="hero-actions"><Link href="/login" className="button">开始一段音乐冥想 <span aria-hidden="true">→</span></Link><a href="#how" className="button ghost">了解它如何工作</a></div>
          <p className="trust-note"><span>✓</span> 受邀使用 <span>✓</span> 隐私优先 <span>✓</span> 非医疗用途</p>
        </div>
        <div className="hero-visual" aria-label="音乐冥想示例">
          <div className="mist mist-one" /><div className="mist mist-two" />
          <div className="demo-card">
            <div className="demo-head"><span className="demo-avatar"><Brand compact /></span><div><strong>为你准备好了</strong><small>焦虑 · 5 分钟</small></div><span className="soft-badge">音乐库</span></div>
            <div className="journey-line"><span className="stage active">承接焦虑</span><i /><span className="stage">进入平静</span><i /><span className="stage">抵达自信</span></div>
            <button className="play-orb" aria-label="播放示例"><span>▶</span></button>
            <div className="wave-bars" aria-hidden="true">{Array.from({ length: 29 }, (_, i) => <i key={i} style={{ height: `${12 + ((i * 13) % 34)}px` }} />)}</div>
            <div className="demo-time"><span>0:00</span><span>5:18</span></div>
          </div>
        </div>
      </section>
      <section className="how" id="how">
        <p className="section-kicker">一次温柔的情绪旅程</p><h2>不是让情绪消失，而是陪它慢慢流动</h2>
        <div className="feature-grid">
          <article><span>01</span><h3>说出此刻</h3><p>像聊天一样描述感受，不必寻找准确的心理学词汇。</p></article>
          <article><span>02</span><h3>确认路径</h3><p>先查看情绪路径、时长和音乐方案，由你确认后才开始生成。</p></article>
          <article><span>03</span><h3>沉浸聆听</h3><p>音乐与中文引导随情绪渐变，网页关闭后任务也会继续。</p></article>
        </div>
      </section>
      <footer><Brand /><p>音乐冥想，是陪伴情绪的一剂温柔良方。</p><span>© 2026 AIMusicMed</span></footer>
    </main>
  );
}
