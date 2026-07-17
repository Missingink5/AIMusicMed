import type { Metadata } from "next";
import { AppDemo } from "../components/app-demo";
export const metadata: Metadata = { title: "我的音乐冥想" };
export default function AppPage() { return <AppDemo />; }
