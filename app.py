"""Read the Room — navigate a complex social situation, directed by AI.

Each scenario is a tab. `gameview` builds every game from the Scenario data, so adding a
scenario in scenarios/ adds a tab here for free; `communityview` browses what other players
shared; `creatorview` is the author-your-own tab. Both hand a freshly parsed Scenario to
the dedicated Play tab.
"""

import threading
import urllib.request

import gradio as gr

import communityview
import creator
import creatorview
import gameview
from art import font_css
from engine import API_BASE
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
    # Alkatra's glyph box runs a few px taller than the h1 line box; Gradio puts
    # overflow:auto on the block as an INLINE style, so without !important the title
    # grows a tiny scrollbar instead of just painting the overhang
    f".rtr-title{{overflow:visible !important}}"
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


def warm_model():
    """Ping the model endpoint so the Modal container boots while the user reads."""

    def ping():
        try:
            # Held open on purpose: serve_modal's gate answers only once the model is
            # loaded, and Modal cancels queued requests whose client disconnects.
            urllib.request.urlopen(
                API_BASE.removesuffix("/v1") + "/health", timeout=300
            )
        except OSError:
            pass

    threading.Thread(target=ping, daemon=True).start()


def do_load(scen):
    """Switch to the Play tab and fill it with the freshly parsed scenario."""
    return (gr.update(selected=PLAY_TAB_ID), *gameview.load_into_play(scen))


def load_scenario(path):
    """Open a saved scenario straight in the Play tab — no detour through the editor."""
    try:
        scen = creator.spec_to_scenario(creator.load_spec(path))
    except Exception as e:  # not a spec / invalid spec — surface as a toast
        raise gr.Error(f"{creator.LOAD_ERROR}: {e}")
    return gameview.load_into_play(scen)


with gr.Blocks(
    title="Read the Room",
    # Soft's bundled "Montserrat" woff2 is really Montserrat Alternates — a display
    # face that's rough on body text. Alkatra keeps the storybook feel but reads better;
    # it ships in fonts/ (inlined by font_css) rather than as a GoogleFont so the app
    # loads nothing from the network. Each name is wrapped in Font (a bare str would
    # crash launch(): gradio compares themes font-by-font and Font.__eq__ can't take str).
    theme=gr.themes.Soft(
        primary_hue="indigo",
        font=(
            gr.themes.Font("Alkatra"),
            gr.themes.Font("ui-sans-serif"),
            gr.themes.Font("system-ui"),
            gr.themes.Font("sans-serif"),
        ),
    ),
    css=font_css()
    + gameview.HIDE_CSS
    + gameview.STORY_CSS
    + gameview.BG_CSS
    + NAV_CSS
    + FOOTER_CSS,
) as demo:
    gr.Markdown("# Read the Room", elem_classes="rtr-title")
    with gr.Tabs() as tabs:
        for scen in REGISTRY.values():
            gameview.build_game(scen)
        comm_play, comm_inputs = communityview.build_community()
        play_btn, form = creatorview.build_creator()
        with gr.Tab("▶ Play your scenario", id=PLAY_TAB_ID):
            with gr.Row():
                load_play = creatorview.load_button()
                gr.HTML("")  # spacer keeps the button compact, left-aligned
            _scen_state, play_outs = gameview.build_game_ui()

    parse_state = gr.State()
    play_btn.click(creatorview.parse_or_raise, form, parse_state).success(
        do_load, parse_state, [tabs, *play_outs]
    )
    comm_play.click(communityview.play_or_raise, comm_inputs, parse_state).success(
        do_load, parse_state, [tabs, *play_outs]
    )
    load_play.upload(load_scenario, load_play, play_outs)
    demo.load(warm_model)

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
    )
