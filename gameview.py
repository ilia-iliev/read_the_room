"""The playable game view: the room, the transcript, the input, and the per-turn handlers.

One factory (`build_game_ui`) builds every game from the Scenario data, so adding a scenario
in scenarios/ adds a tab for free. Every string and update the layout shows comes from the
pure renderers in render.py; this module only builds the components and wires the handlers.
"""

import gradio as gr

from engine import new_game, play_turn_stream, rewind_to
from render import (
    BLANK_STORY,
    PLAYER_VERB,
    export_debug,
    fresh_turn,
    progress,
    render_debug,
    render_story,
    room_strip,
    turn_outputs,
)

REGEN_CAP = (
    16  # how many per-turn regenerate buttons each game pre-builds (>= any max_turns)
)

# The per-turn regenerate buttons must stay in the DOM to be clickable by the inline ↻ links, so
# they can't use visible=False (Gradio drops those from the DOM entirely). Hide them with CSS
# instead — still rendered, still clickable, just not painted. Wired into the Blocks in app.py.
HIDE_CSS = ".rtr-regen-hide{display:none !important}"

# The scene art is a fixed full-viewport backdrop (`.rtr-bg`, emitted by render.room_strip)
# that hides along with its tab. The page container goes transparent so the backdrop shows
# through, and a game that carries one gets a translucent card behind its text to stay
# readable. Games without art keep the plain page. Wired into the Blocks in app.py.
BG_CSS = (
    ".rtr-bg{position:fixed;inset:0;z-index:-1;"
    "background-size:cover;background-position:center}"
    "gradio-app,.gradio-container{background:transparent !important}"
    ".rtr-game:has(.rtr-bg){background:rgba(255,255,255,.64);"
    "padding:8px 20px 20px;border-radius:14px}"
)


def build_game_ui(scen=None):
    """The playable game for one scenario: the room, the transcript, the input, and the
    handlers. With a `scen` it builds a fixed game (the static tabs). With None it builds a
    blank shell whose scenario is supplied at runtime through the returned state — the custom
    'Play your scenario' tab. The handlers read the scenario from that state, so the same
    builder serves both. Returns (scen_state, load_outputs) for the caller to wire a loader."""
    scen_state = gr.State(scen)
    # a factory so each browser session gets its own game object, never a shared mutable one
    game = gr.State((lambda: new_game(scen)) if scen else None)
    g0 = new_game(scen) if scen else None

    # one scoped root per game so an inline ↻ link reaches THIS game's hidden regen controls
    # (via JS `closest('.rtr-game')`) and never another tab's, even with several games in the page
    with gr.Column(elem_classes="rtr-game"):
        banner = gr.HTML(room_strip(scen) if scen else "")
        # utility icons, top-right: copy the readable conversation, or the raw LM traces, to
        # the clipboard. Each handler stashes its text in a hidden box, then JS copies it.
        with gr.Row():
            gr.HTML("")  # spacer pushes the icons to the right
            copy_convo = gr.Button("📋", scale=0, size="sm")
            copy_debug = gr.Button("🐞", scale=0, size="sm")
        clip = gr.Textbox(visible=False)
        # sanitize off so avatar <img> tags AND the inline ↻ links render; dynamic text is esc()'d
        story = gr.Markdown(
            render_story(scen, g0) if scen else BLANK_STORY, sanitize_html=False
        )
        recap = gr.HTML(visible=False)
        status = gr.Markdown(progress(scen, g0) if scen else "")
        box = gr.Textbox(
            label=PLAYER_VERB,
            show_label=False,
            lines=2,
            autofocus=True,
        )
        with gr.Row():
            act = gr.Button(
                f"{PLAYER_VERB} ▶", variant="primary", interactive=bool(scen)
            )
            reset = gr.Button("New game")

        # hidden plumbing for the inline ↻ links: one button per turn index, each wired below to
        # rewind to ITS turn. The link clicks the matching `.rtr-regen-N`; nothing is passed
        # through the frontend, so there's no value to lose. No on-screen rewind UI.
        regen_btns = [
            gr.Button(elem_classes=[f"rtr-regen-{i}", "rtr-regen-hide"])
            for i in range(REGEN_CAP)
        ]
        # the ✎ twin of regen_btns: rewind to ITS turn but prefill the box instead of replaying
        edit_btns = [
            gr.Button(elem_classes=[f"rtr-edit-{i}", "rtr-regen-hide"])
            for i in range(REGEN_CAP)
        ]

    turn_outs = [story, status, box, game, act, reset, recap]
    load_outs = [banner, *turn_outs, scen_state]

    async def submit(directive, game, scen):
        directive = (directive or "").strip()
        if scen is None or game is None:  # blank custom tab — nothing to play yet
            yield fresh_turn(None)
            return
        if not directive or not game.active:
            yield turn_outputs(
                scen, game, box=gr.update(value=directive, visible=game.active)
            )
            return
        async for out in play_forward(scen, game, directive):
            yield out

    async def play_forward(scen, game, directive):
        """Stream one turn and the trailing frame. Shared by a fresh Say and a ↻ replay."""
        async for current, _ in play_turn_stream(game, directive):
            yield turn_outputs(scen, game, box="", status="🤔 …", current=current)
        box = gr.update(value="", visible=False) if not game.active else ""
        yield turn_outputs(scen, game, box=box)

    def make_regenerate(turn_no):
        """A handler bound to one turn index: rewind to player turn `turn_no` (dropping it and
        everything after) and replay it with the same words. The play LM has caching off, so the
        room reacts anew rather than echoing the original — same streaming path as a fresh Say."""

        async def regenerate(game, scen):
            if scen is None or game is None:
                yield fresh_turn(None)
                return
            if not (0 <= turn_no < len(game.snapshots)):
                yield turn_outputs(scen, game, box=gr.update())  # turn no longer exists
                return
            directive = rewind_to(game, turn_no)
            async for out in play_forward(scen, game, directive):
                yield out

        return regenerate

    def make_edit(turn_no):
        """A handler bound to one turn index: rewind to player turn `turn_no` (dropping it and
        everything after) and drop the original words back into the box, UNPLAYED, so the player
        can reword before pressing Say. Rewind-only — no streaming — so it's a plain sync return."""

        def edit(game, scen):
            if scen is None or game is None:
                return fresh_turn(None)
            if not (0 <= turn_no < len(game.snapshots)):
                return turn_outputs(
                    scen, game, box=gr.update()
                )  # turn no longer exists
            directive = rewind_to(game, turn_no)
            return turn_outputs(
                scen, game, box=gr.update(value=directive, visible=True)
            )

        return edit

    act.click(submit, [box, game, scen_state], turn_outs)
    box.submit(submit, [box, game, scen_state], turn_outs)
    reset.click(fresh_turn, [scen_state], turn_outs)
    for i, btn in enumerate(regen_btns):
        btn.click(make_regenerate(i), [game, scen_state], turn_outs)
    for i, btn in enumerate(edit_btns):
        btn.click(make_edit(i), [game, scen_state], turn_outs)
    to_clipboard = "(t) => { navigator.clipboard.writeText(t); }"
    copy_convo.click(render_debug, [scen_state, game], clip).then(
        None, clip, None, js=to_clipboard
    )
    copy_debug.click(export_debug, [game], clip).then(None, clip, None, js=to_clipboard)

    return scen_state, load_outs


def load_into_play(scen):
    """Fill the custom Play tab with a fresh game of `scen` — banner, transcript, the lot —
    in the order of build_game_ui's load_outs ([banner, *turn, scen_state])."""
    return (room_strip(scen), *fresh_turn(scen), scen)


def build_game(scen):
    """Wrap one scenario's game in its own tab."""
    with gr.Tab(scen.title):
        build_game_ui(scen)
