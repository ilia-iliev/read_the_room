---
title: Read The Room
emoji: 👀
colorFrom: yellow
colorTo: yellow
sdk: gradio
sdk_version: 6.16.0
python_version: "3.13"
app_file: app.py
pinned: false
---

# Track 2: Read the Room

Read the Room drops you into a room full of people - each character has an agenda and opinion of each other. You talk, they react, alliances shift, and every word either opens a door or closes one. Make smart choices and read the social cues. I have defined 2 scenarios - but you can build your own with a template

## Off the grid

The app makes zero network requests of its own - art and font are bundled and inlined. Point `RTR_API_BASE` at a local llama.cpp/vLLM and it runs fully offline (the hosted Space points it at a Modal GPU instead).
