"""Read the Room — navigate a complex social situation, directed by AI.

Each scenario is a tab. `gameview` builds every game from the Scenario data, so adding a
scenario in scenarios/ adds a tab here for free; `creatorview` is the author-your-own tab,
which hands a freshly parsed Scenario to the dedicated Play tab.
"""

import gradio as gr

import creatorview
import gameview
from scenarios import REGISTRY

PLAY_TAB_ID = "play_custom"


def do_load(scen):
    """Switch to the Play tab and fill it with the freshly parsed scenario."""
    return (gr.update(selected=PLAY_TAB_ID), *gameview.load_into_play(scen))


with gr.Blocks(title="Read the Room", css=gameview.HIDE_CSS) as demo:
    gr.Markdown("# 🎭 Read the Room")
    with gr.Tabs() as tabs:
        for scen in REGISTRY.values():
            gameview.build_game(scen)
        play_btn, spec, art = creatorview.build_creator()
        with gr.Tab("▶ Play your scenario", id=PLAY_TAB_ID):
            _scen_state, play_outs = gameview.build_game_ui()

    parse_state = gr.State()
    play_btn.click(creatorview.parse_or_raise, [spec, art], parse_state).success(
        do_load, parse_state, [tabs, *play_outs]
    )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        theme=gr.themes.Soft(primary_hue="amber"),
    )
