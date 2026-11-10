import json
import time
import urllib.request
import subprocess
from evals.capri_comprehensive.runners.runner import ScenarioRunner
from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition

def get_ollama_ps():
    res = subprocess.run(["ollama", "ps"], capture_output=True, text=True)
    return res.stdout.strip()

def get_vram_info():
    cmd = ["nvidia-smi", "--query-gpu=memory.used,memory.free,memory.total", "--format=csv,noheader,nounits"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        used, free, total = res.stdout.strip().split(", ")
        return {"used_mib": int(used), "free_mib": int(free), "total_mib": int(total)}
    return {}

def test_raw_api(model: str, prompt: str, num_ctx: int = 2048, temperature: float = 0.7):
    url = "http://127.0.0.1:11434/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "num_ctx": num_ctx,
            "temperature": temperature,
        }
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    t1 = time.perf_counter()
    
    total_duration_s = data.get("total_duration", 0) / 1e9
    load_duration_s = data.get("load_duration", 0) / 1e9
    prompt_eval_duration_s = data.get("prompt_eval_duration", 0) / 1e9
    eval_duration_s = data.get("eval_duration", 0) / 1e9
    prompt_eval_count = data.get("prompt_eval_count", 0)
    eval_count = data.get("eval_count", 0)
    
    ttft_s = load_duration_s + prompt_eval_duration_s
    prompt_eval_rate = (prompt_eval_count / prompt_eval_duration_s) if prompt_eval_duration_s > 0 else 0
    eval_rate = (eval_count / eval_duration_s) if eval_duration_s > 0 else 0
    wall_clock_s = t1 - t0
    
    return {
        "model": model,
        "content": data.get("message", {}).get("content", "").strip(),
        "wall_clock_s": round(wall_clock_s, 3),
        "total_duration_s": round(total_duration_s, 3),
        "load_duration_s": round(load_duration_s, 3),
        "prompt_eval_duration_s": round(prompt_eval_duration_s, 4),
        "eval_duration_s": round(eval_duration_s, 3),
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
        "ttft_ms": round(ttft_s * 1000, 2),
        "prompt_eval_rate_tok_per_s": round(prompt_eval_rate, 2),
        "eval_rate_tok_per_s": round(eval_rate, 2),
    }

def main():
    print("=== Initial Hardware State ===")
    print(f"VRAM: {get_vram_info()}")
    print(f"Ollama PS:\n{get_ollama_ps()}\n")
    
    # 1. Primary Model: b12-bolt-e4b:q4km
    print("=== Testing Primary Model: b12-bolt-e4b:q4km ===")
    print("--- Cold Run (raw API) ---")
    cold_primary = test_raw_api("b12-bolt-e4b:q4km", "Привіт! Хто ти? Відповідай коротко одним реченням.", num_ctx=2048)
    print(json.dumps(cold_primary, indent=2, ensure_ascii=False))
    print(f"Post-cold VRAM: {get_vram_info()}")
    print(f"Post-cold Ollama PS:\n{get_ollama_ps()}\n")
    
    print("--- Warm Run (raw API, num_ctx=2048) ---")
    warm_primary_2048 = test_raw_api("b12-bolt-e4b:q4km", "Поясни принцип збереження енергії у двох коротких реченнях.", num_ctx=2048)
    print(json.dumps(warm_primary_2048, indent=2, ensure_ascii=False))
    
    print("--- Warm Run (raw API, num_ctx=4096) ---")
    warm_primary_4096 = test_raw_api("b12-bolt-e4b:q4km", "Поясни третій закон Ньютона у двох коротких реченнях.", num_ctx=4096)
    print(json.dumps(warm_primary_4096, indent=2, ensure_ascii=False))
    
    # 2. Test ScenarioRunner._call_ollama_bridge for Primary Model
    print("--- ScenarioRunner._call_ollama_bridge test (Primary) ---")
    runner = ScenarioRunner()
    bridge_res_primary = runner._call_ollama_bridge(
        model="b12-bolt-e4b:q4km",
        prompt="Скажи тестову фразу: Б-12 готовий до роботи.",
    )
    print(json.dumps(bridge_res_primary, indent=2, ensure_ascii=False))
    
    # 3. Secondary Model: gemma4:12b
    print("\n=== Testing Secondary Model: gemma4:12b ===")
    print("--- Cold Run (raw API, num_ctx=4096) ---")
    cold_sec = test_raw_api("gemma4:12b", "Привіт! Хто ти? Відповідай коротко одним реченням.", num_ctx=4096)
    print(json.dumps(cold_sec, indent=2, ensure_ascii=False))
    print(f"Post-cold Secondary VRAM: {get_vram_info()}")
    print(f"Post-cold Secondary Ollama PS:\n{get_ollama_ps()}\n")
    
    print("--- Warm Run (raw API, num_ctx=4096) ---")
    warm_sec_4096 = test_raw_api("gemma4:12b", "Поясни третій закон Ньютона у двох коротких реченнях.", num_ctx=4096)
    print(json.dumps(warm_sec_4096, indent=2, ensure_ascii=False))
    
    # 4. Test ScenarioRunner._call_ollama_bridge for Secondary Model
    print("--- ScenarioRunner._call_ollama_bridge test (Secondary) ---")
    bridge_res_sec = runner._call_ollama_bridge(
        model="gemma4:12b",
        prompt="Скажи тестову фразу: Модель Gemma 4 12B активна.",
    )
    print(json.dumps(bridge_res_sec, indent=2, ensure_ascii=False))
    
    print("\n=== Final Hardware State ===")
    print(f"VRAM: {get_vram_info()}")
    print(f"Ollama PS:\n{get_ollama_ps()}\n")

if __name__ == "__main__":
    main()
