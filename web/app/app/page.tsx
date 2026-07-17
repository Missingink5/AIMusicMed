import type { Metadata } from "next";
import { AppDemo } from "../components/core-experience";
import { ErrorBoundary } from "../components/error-boundary";
export const metadata: Metadata = { title: "我的音乐冥想" };
export default function AppPage() { return <ErrorBoundary><AppDemo /></ErrorBoundary>; }
