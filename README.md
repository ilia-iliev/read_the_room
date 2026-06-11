---
title: Read The Room
emoji: 💻
colorFrom: yellow
colorTo: yellow
sdk: gradio
sdk_version: 6.16.0
python_version: "3.13"
app_file: app.py
pinned: false
---

# Track 2: Read the Room

This is the repository for the second track. 

I'm building a game where the player navigates a complex social situation to achieve a goal - and the AI is a director of the scene. The game is winnable and genuinely hard. The script is loose and the AI is in control of how the character progresses through the story - the player just provides some input every once in a while.

Ships with two rooms to read — a warlord's hall and an engagement dinner where the in-laws lean no — plus a **Create your own** tab: describe a standoff and how many people are in it, and the AI writes the whole scenario (cast, the premise, the fairness rules that keep it winnable). Edit anything, then play it. Each character has a face — upload your own scene banner and avatars, and **Download bundle** packs the whole scenario (spec + art) into one `.zip` you can share and **Load bundle** back in. The end screen shows how every mind in the room finally read you.

The engine talks to any OpenAI-compatible server — local llama.cpp/vLLM/Ollama, or a hosted
endpoint. All three env vars are required (the HF Space sets them as secrets):

```bash
export RTR_MODEL=Qwen3.6-27B                    # served model name
export RTR_API_BASE=http://localhost:8081/v1    # your server
export RTR_API_KEY=not-needed                   # or a real key for hosted endpoints

uv run app.py          # Gradio app at http://localhost:7860
uv run evaluate.py     # check the invariants (--strict for the all-of-3 gate; pegs the GPU)
```
