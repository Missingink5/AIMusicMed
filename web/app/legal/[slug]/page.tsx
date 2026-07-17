import Link from "next/link";
import { Brand } from "../../components/brand";

const pages: Record<string, { title: string; intro: string }> = {
  privacy: { title: "隐私说明", intro: "我们以最少必要原则处理你的会话、音频与账号数据。个人 API Key 仅在服务器端加密保存，不会出现在网页或日志中。" },
  terms: { title: "用户协议", intro: "AIMusicMed 面向年满 18 岁的受邀用户，用于音乐冥想与日常情绪调节，不提供心理诊断或治疗。" },
  "voice-music": { title: "声音与音乐授权规则", intro: "上传或使用声音与音乐前，你需要确认拥有合法使用权或已取得权利人的明确授权。" },
};
export default async function LegalPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params; const page = pages[slug] ?? pages.terms;
  return <main className="legal-page"><header><Link href="/"><Brand /></Link><Link href="/">返回首页</Link></header><article><p>AIMusicMed</p><h1>{page.title}</h1><h2>首版产品说明草案</h2><p>{page.intro}</p><p>具体的数据保留、第三方服务数据流、账号删除与授权责任，将在正式上线前补充完整并经过审阅。本页面不替代正式法律意见。</p><aside>如你正处于紧急危险中，请立即联系身边可信任的人、当地急救或专业危机支持。本产品不会自动报警或联系管理员。</aside></article></main>;
}
