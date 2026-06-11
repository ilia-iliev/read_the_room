"""Read the Room — navigate a complex social situation, directed by AI.

Each scenario is a tab. `gameview` builds every game from the Scenario data, so adding a
scenario in scenarios/ adds a tab here for free; `creatorview` is the author-your-own tab,
which hands a freshly parsed Scenario to the dedicated Play tab.
"""

import gradio as gr

import bundle
import creator
import creatorview
import gameview
from scenarios import REGISTRY

PLAY_TAB_ID = "play_custom"

# The page chrome sits straight on the scene backdrop. The big title gets a white
# text-shadow edge (outline-by-shadow renders everywhere, unlike -webkit-text-stroke
# which eats into the glyphs); at tab-label sizes an outline just smudges, so the tab
# row gets a frosted translucent strip behind it instead and keeps its own typography.


def white_edge(r):
    """A text-shadow outline: 8 white shadows ringing the glyph at radius `r` px."""
    return ",".join(
        f"{dx}px {dy}px 0 #fff" for dx in (-r, 0, r) for dy in (-r, 0, r) if dx or dy
    )


NAV_CSS = (
    f".rtr-title h1{{color:#111;text-shadow:{white_edge(1)},{white_edge(2)}}}"
    ".tab-container{background:rgba(255,255,255,.72);backdrop-filter:blur(8px);"
    "border-radius:10px;padding:0 10px}"
    ".tab-container button:not(.selected){color:#111}"
)

# Gradio's footer Settings panel doesn't work well here — hide it (and its divider dot),
# keeping "Use via API" and the Gradio credit.
FOOTER_CSS = (
    "footer button.settings,footer .divider:not(.show-api-divider)"
    "{display:none !important}"
)


def do_load(scen):
    """Switch to the Play tab and fill it with the freshly parsed scenario."""
    return (gr.update(selected=PLAY_TAB_ID), *gameview.load_into_play(scen))


def load_bundle(zip_path):
    """Open a saved bundle straight in the Play tab — no detour through the editor."""
    try:
        spec_text, art = bundle.unpack(zip_path)
        scen = creator.spec_to_scenario(creator.from_json(spec_text), art)
    except Exception as e:  # not a bundle / spec inside is invalid — surface as a toast
        raise gr.Error(f"Couldn't load that bundle: {e}")
    return gameview.load_into_play(scen)


with gr.Blocks(
    title="Read the Room",
    theme=gr.themes.Soft(primary_hue="indigo"),
    css=gameview.HIDE_CSS + gameview.BG_CSS + NAV_CSS + FOOTER_CSS,
) as demo:
    gr.Markdown("# Read the Room", elem_classes="rtr-title")
    with gr.Tabs() as tabs:
        for scen in REGISTRY.values():
            gameview.build_game(scen)
        play_btn, form, art = creatorview.build_creator()
        with gr.Tab("▶ Play your scenario", id=PLAY_TAB_ID):
            with gr.Row():
                load_play = gr.UploadButton(
                    "⬆️ Load bundle (.zip)",
                    file_types=[".zip"],
                    type="filepath",
                    size="sm",
                    scale=0,
                )
                gr.HTML("")  # spacer keeps the button compact, left-aligned
            _scen_state, play_outs = gameview.build_game_ui()

    parse_state = gr.State()
    play_btn.click(creatorview.parse_or_raise, [*form, art], parse_state).success(
        do_load, parse_state, [tabs, *play_outs]
    )
    load_play.upload(load_bundle, load_play, play_outs)

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
    )
