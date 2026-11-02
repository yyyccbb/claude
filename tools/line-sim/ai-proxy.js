// 本地转发：浏览器直连大模型接口被跨域(CORS)拦截时使用
// 用法：node ai-proxy.js            （默认转发到 https://api.xiaomimimo.com）
//       set AI_TARGET=https://xxx    （Windows；macOS/Linux 用 export）改转发目标
// 然后在模拟页「AI 接口设置」里把 API 地址填为 http://localhost:8787/v1
const http = require("http");
const https = require("https");
const { URL } = require("url");

const TARGET = new URL(process.env.AI_TARGET || "https://api.xiaomimimo.com");
const PORT = +process.env.PORT || 8787;
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type,Authorization,x-api-key,anthropic-version,anthropic-beta,anthropic-dangerous-direct-browser-access",
};

http.createServer((req, res) => {
  if (req.method === "OPTIONS") { res.writeHead(204, CORS); return res.end(); }
  const url = new URL(req.url, TARGET);
  const headers = { ...req.headers, host: url.host };
  delete headers.origin; delete headers.referer;
  const up = (url.protocol === "http:" ? http : https).request(url, { method: req.method, headers }, r => {
    res.writeHead(r.statusCode, { ...r.headers, ...CORS });
    r.pipe(res);
  });
  up.on("error", e => { res.writeHead(502, { "Content-Type": "text/plain; charset=utf-8", ...CORS }); res.end("转发失败：" + e.message); });
  req.pipe(up);
}).listen(PORT, "127.0.0.1", () => console.log(`AI 转发已启动：http://localhost:${PORT} → ${TARGET.origin}`));
