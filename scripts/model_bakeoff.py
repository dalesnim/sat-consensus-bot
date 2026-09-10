"""Run every candidate model against every labeled image and write a result matrix."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import pathlib
import sys
import time

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from bot.config import ModelConfig, load_settings  # noqa: E402
from bot.orchestrator import client as C  # noqa: E402
from bot.orchestrator.contract import Verdict  # noqa: E402

CANDIDATES: list[ModelConfig] = [
    ModelConfig(id="amazon/nova-premier-v1", lab="amazon", reasoning="minimal"),
    ModelConfig(id="baidu/ernie-4.5-vl-424b-a47b", lab="baidu", reasoning="minimal"),
    ModelConfig(id="minimax/minimax-m3", lab="minimax", reasoning="minimal"),
    ModelConfig(id="meta-llama/llama-4-maverick", lab="meta-llama", reasoning="minimal"),
    ModelConfig(id="stepfun/step-3.7-flash", lab="stepfun", reasoning="minimal"),
    ModelConfig(id="qwen/qwen3-vl-235b-a22b-thinking", lab="qwen", reasoning="minimal"),
]

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def data_url(path: pathlib.Path) -> str:
    mime = MIME.get(path.suffix.lower(), "image/png")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


async def ask(
    http: httpx.AsyncClient, key: str, model: ModelConfig, url: str, max_tokens: int
) -> dict[str, object]:
    started = time.perf_counter()
    try:
        response = await http.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=C.build_payload(model, url, max_tokens=max_tokens),
        )
        elapsed = time.perf_counter() - started
        if response.status_code != 200:
            return {"answer": None, "error": f"HTTP {response.status_code}", "seconds": elapsed}
        body = response.json()
        usage = body.get("usage") or {}
        content = body["choices"][0]["message"].get("content") or ""
        try:
            verdict = Verdict.model_validate_json(content)
        except Exception as exc:  # noqa: BLE001
            return {"answer": None, "error": f"parse: {type(exc).__name__}", "seconds": elapsed}
        return {
            "answer": verdict.answer,
            "question_type": verdict.question_type,
            "error": None,
            "seconds": elapsed,
            "cost_usd": usage.get("cost"),
            "completion_tokens": usage.get("completion_tokens"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "answer": None,
            "error": f"{type(exc).__name__}",
            "seconds": time.perf_counter() - started,
        }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", default="images", help="directory of question images")
    parser.add_argument("--out", default="data/bakeoff.json")
    parser.add_argument("--max-tokens", type=int, default=3000)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    settings = load_settings()
    key = settings.openrouter_api_key.get_secret_value()

    images = sorted(
        path
        for path in pathlib.Path(args.images).iterdir()
        if path.suffix.lower() in MIME and not path.name.startswith(".")
    )
    if not images:
        print(f"error: no images found in {args.images}", file=sys.stderr)
        return 1
    print(f"{len(images)} images × {len(CANDIDATES)} models = {len(images)*len(CANDIDATES)} calls")

    gate = asyncio.Semaphore(args.concurrency)
    results: dict[str, dict[str, object]] = {}

    async with httpx.AsyncClient(
        base_url=settings.openrouter_base_url, timeout=httpx.Timeout(120.0)
    ) as http:

        async def run(image: pathlib.Path, model: ModelConfig) -> None:
            url = data_url(image)
            async with gate:
                outcome = await ask(http, key, model, url, args.max_tokens)
            results.setdefault(image.name, {})[model.id] = outcome
            mark = outcome["answer"] or outcome["error"]
            print(f"  {image.name[:38]:<40} {model.id:<34} {mark}", flush=True)

        await asyncio.gather(*(run(i, m) for i in images for m in CANDIDATES))

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
