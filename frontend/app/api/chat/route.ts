/**
 * Next.js Route Handler for /api/chat
 *
 * 将 useChat 的请求透传给后端 /agent/hermes，
 * 后端负责工具调用 agentic loop 并以 AI SDK v3 data stream 格式流式返回。
 * 前端无需持有 DEEPSEEK_API_KEY，LLM 调用完全在后端。
 */

export const runtime = "nodejs";

const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function POST(req: Request) {
  const body = await req.json();

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/agent/hermes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (e) {
    return new Response(
      JSON.stringify({ error: `连接后端失败：${e}` }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  if (!upstream.ok || !upstream.body) {
    const err = await upstream.text();
    return new Response(
      JSON.stringify({ error: `后端错误 ${upstream.status}：${err}` }),
      { status: upstream.status, headers: { "Content-Type": "application/json" } },
    );
  }

  // 直接透传后端的 AI SDK v3 data stream
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "X-Vercel-AI-Data-Stream": "v1",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
