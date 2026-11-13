---
type: source-review
updated: 2026-11-09
status: compiled
sources: [artifacts/gemma-desktop-launch-2026-11-09/configuration.json, artifacts/gemma-desktop-launch-2026-11-09/api-smoke.json, artifacts/gemma-desktop-launch-2026-11-09/ollama-ps.txt, artifacts/gemma-desktop-launch-2026-11-09/services.txt, artifacts/gemma-desktop-launch-2026-11-09/window.txt, src/b12/cli.py, src/b12/desktop/client.py]
tags: [gemma, desktop, deployment, operations]
---
# Запуск Capri на Gemma 4 12B

**Вимога власника:** запустити компаньйона з gemma4:12b. Це окреме операційне доручення після наукових пілотів, де live config не змінювався.

**Виконано:** original config збережено в локальній резервній копії; до ~/.config/b12/config.toml встановлено model=gemma4:12b, постійні model_profile/tokenizer_dir у ~/.local/share/b12. Assets перевірені за SHA-256; використано раніше випробуваний local manifest і профіль Ollama 0.33.3. Context залишено 8192, output_tokens=1024; state_dir лишається ~/.local/state/b12. Модель перемкнуто конфігурацією перед стартом, не через неіснуючий hot-switch manager.

**Перевірено:** doctor ok=true, initialized/consent=true, pending purges/approvals=0. Запущено user units capri-api.service і capri-desktop.service з desktop worktree. API health=true; X11 підтверджує видиме вікно Capri · CAPRI; appearance=capri. Окрема тестова API-сесія завершилася completed і повернула коротке привітання Capri. Після неї active_turns=0. Власний код runtime й persona під час запуску не змінювався.

**GPU саме цього запуску:** Ollama ps показав 34%/66% CPU/GPU, context 8192, size=8141368959 і size_vram=5379477994 bytes. Під час тестового ходу зафіксовано GPU utilization до 100% і VRAM до 6950 MiB. Це часткове розміщення на GPU, не суто GPU inference; показники PROCESSOR не дорівнюють відсотку часу обчислень. Результат стосується поточного запуску й не заповнює відсутні offload-метадані попередніх наукових пілотів.

**Межі:** перевірено один API turn і факт існування Qt-вікна, не повну GUI/voice acceptance. Мікрофон/TTS pipeline не запускали. Owner token прочитано локально без виведення чи копіювання в артефакти. Модель лишено доступною для розмови; Ollama може вивантажити її після idle timeout і завантажити знову на наступний запит.

**Наступна дія власника:** Capri зупинено за прямою командою. Обидва user units inactive/dead, MainPID=0; список моделей Ollama порожній. Сам Ollama server і сховища не видалялися; запуск автоматично не відновлювали.
