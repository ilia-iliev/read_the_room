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

Play [here](https://huggingface.co/spaces/build-small-hackathon/read_the_room)

You're a player in a situation where each character has an agenda and an opinion of everyone else, including you. You talk your way to a goal. The inspiration is text adventures RPGs like Zork crossed with social deduction games like Avalon and Werewolf. The social dynamic is the game - I've always wished videogame dialogues gave me more options to explore. Traditional games have always been constrained in this and current AI games dodge the social element: they usually focus on one character, or fixed characters on rails. So I built a game with multiple AIs reacting to each other and especially you (the player)

Anyone can publish a scenario (optional but recommended scene picture) and play what others shared


# Merit Badges

## Off the grid

The app makes zero network requests of its own - art and font are bundled and inlined. Point `RTR_API_BASE` at a local llama.cpp/vLLM and it runs fully offline (the hosted Space points it at a Modal GPU instead)

## Off-Brand

The default Gradio doesn't work well for a game, so I gave it some style with a custom front-end

## Llama champion

Llama.cpp is the canon way to play the game - start a server locally and wire it up. I playtested with Qwen3.6-27B (Q8_K_XL gguf from unsloth)

## Sharing is Caring

Playthrough traces - raw prompt and completions are available. You can use 🐞 export function to see what happened each turn - what fed into the LLM and what the response was. Here is one: [Ilia-Iliev/read-the-room-traces](https://huggingface.co/datasets/Ilia-Iliev/read-the-room-traces)

## Field Notes

More details in my [blogpost](https://ilia.foo/blog/read_the_room)

[Video](https://www.youtube.com/watch?v=eY81SvsOJy4)

[Social Media post](https://www.linkedin.com/posts/ilia-iliev-7903a015a_read-the-room-a-hugging-face-space-by-build-small-hackathon-activity-7471300743883522048-rKGz?utm_source=share&utm_medium=member_desktop&rcm=ACoAACYk8lwBA6YMOvmo6sowMJ679w1Iy48UvP0)
