"""GLM-5.2 via scnet.cn Anthropic-compatible API. 仅用户明确指定时使用，默认仍走 DeepSeek."""
import os
import json
import urllib.request
import urllib.error

URL = "https://api.scnet.cn/api/llm/anthropic/v1/messages"


def ask_glm(prompt: str, *, max_tokens: int = 196000, system: str | None = None,
            temperature: float | None = None) -> dict:
    """返回完整响应 dict，text 内容在 resp['content'][-1]['text']"""
    api_key = os.environ.get("SCNET_API_KEY")
    if not api_key:
        raise RuntimeError("SCNET_API_KEY 环境变量未设置")

    messages = [{"role": "user", "content": prompt}]
    if system:
        messages.insert(0, {"role": "system", "content": system})

    body = {"messages": messages, "model": "GLM-5.2", "max_tokens": max_tokens, "stream": False}
    if temperature is not None:
        body["temperature"] = temperature

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8')}") from e


def get_text(resp: dict) -> str:
    """从 ask_glm 返回的响应中提取纯文本"""
    for block in resp.get("content", []):
        if block.get("type") == "text":
            return block["text"]
    return ""


if __name__ == "__main__":
    resp = ask_glm("你好")
    print(f"HTTP 200 | tokens: {resp['usage']['input_tokens']}→{resp['usage']['output_tokens']}")
    print(get_text(resp))
