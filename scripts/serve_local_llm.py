# -*- coding: utf-8 -*-
"""本地部署：把微调好的 HF merged 模型 serve 成 OpenAI 兼容接口，供项目 LLM 双线 local 使用。

用法：
  py scripts/serve_local_llm.py --model data/models/qwen3-ugov --port 8011

然后 .env：
  LLM_MODE=local
  LOCAL_BASE_URL=http://127.0.0.1:8011/v1
  LOCAL_MODEL=qwen3-ugov

注意：CPU 推理较慢，0.6B 一条回复约数秒~数十秒，适合本机离线/回复生成。
"""
import argparse
import glob
import os

import torch
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# ---- OpenAI 兼容请求模型（必须放模块顶层：FastAPI 才能把注解解析成 body）----
class ChatMsg(BaseModel):
    role: str
    content: str = ""


class ChatReq(BaseModel):
    model: str = "qwen3-ugov"
    messages: list[ChatMsg]
    temperature: float = 0.3
    max_tokens: int = 256


def find_model_dir(hint: str) -> str:
    """自动定位含 config.json + *.safetensors 的目录。"""
    if os.path.isfile(os.path.join(hint, "config.json")):
        return hint
    for c in glob.glob(os.path.join(hint, "**", "config.json"), recursive=True):
        d = os.path.dirname(c)
        if glob.glob(os.path.join(d, "*.safetensors")):
            return d
    raise FileNotFoundError(f"没在 {hint} 找到 HF 模型（需 config.json + *.safetensors）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                    "data", "models", "qwen3-ugov"))
    ap.add_argument("--port", type=int, default=8011)
    args = ap.parse_args()

    model_dir = find_model_dir(args.model)
    print("model dir:", model_dir, flush=True)

    tok = AutoTokenizer.from_pretrained(model_dir)
    if getattr(tok, "enable_thinking", None):
        try:
            tok.enable_thinking(False)   # Qwen3 关思考，直出回复
        except Exception:
            pass
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.float32)
    model.eval()
    print(f"[serve] loaded {model_dir} (device cpu, params={model.num_parameters()/1e6:.0f}M)", flush=True)

    app = FastAPI(title="ugov-qwen3 local")

    @app.get("/health")
    def health():
        return {"ok": True, "model_dir": model_dir}

    @app.post("/v1/chat/completions")
    def chat(req: ChatReq):
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ids = tok(text, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=max(1, min(req.max_tokens, 512)),
                                 do_sample=req.temperature > 0, temperature=max(req.temperature, 1e-5),
                                 pad_token_id=tok.pad_token_id)
        new = out[0][ids["input_ids"].shape[-1]:]
        content = tok.decode(new, skip_special_tokens=True)
        if "<think>" in content:
            content = content.split("</think>", 1)[-1].strip()
        return {"id": "local", "object": "chat.completion", "model": req.model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]}

    import uvicorn
    print(f"[serve] listening on http://127.0.0.1:{args.port}/v1", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
