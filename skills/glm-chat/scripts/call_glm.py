"""GLM-5.2 API caller — prompt via --file or stdin, response to stdout."""
import sys
import os
import io

# 强制 stdout 和 stderr 用 UTF-8，避免 Windows 下编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# scnet_glm52.py: look in same directory as this script first, home dir as fallback
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)
sys.path.insert(0, os.path.expanduser("~"))

from scnet_glm52 import ask_glm, get_text


def main():
    # --file <path> 方式：从 UTF-8 文件读取 prompt（推荐，避免管道编码问题）
    if len(sys.argv) >= 3 and sys.argv[1] == "--file":
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            prompt = f.read().strip()
    else:
        # stdin 方式：Windows 下 stdin 默认编码可能不是 UTF-8，显式指定
        sys.stdin.reconfigure(encoding="utf-8")
        prompt = sys.stdin.read().strip()

    if not prompt:
        print("ERROR: empty prompt", file=sys.stderr)
        sys.exit(1)

    retries = 2
    for attempt in range(retries):
        try:
            resp = ask_glm(prompt)
            text = get_text(resp)
            print(text)
            return
        except Exception as e:
            if attempt < retries - 1:
                continue
            print(f"GLM API 调用失败（已重试{retries}次）: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
