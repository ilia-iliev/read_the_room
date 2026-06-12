"""The playable game view: the room, the transcript, the input, and the per-turn handlers.

One factory (`build_game_ui`) builds every game from the Scenario data, so adding a scenario
in scenarios/ adds a tab for free. Every string and update the layout shows comes from the
pure renderers in render.py; this module only builds the components and wires the handlers.
"""

import gradio as gr

from engine import new_game, play_turn_stream, rewind_to
from render import (
    BLANK_STORY,
    EDIT_CLS,
    PLAYER_VERB,
    REGEN_CLS,
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

# The transcript's reading system. render.py wraps every entry in a classed <div>, and each
# kind gets its own register here: character speech is the plain register (avatar + name),
# narration recedes as italic stage direction, the player's lines are right-hand chat
# bubbles, and the setup folds into a one-line <details> once play starts (the pinned goal
# line underneath carries the border that marks where play begins).
STORY_CSS = (
    ".rtr-story .prose{font-size:1.2em}"  # reads small against the busy scene art
    ".rtr-story .prose p{margin:.45em 0}"  # the theme's prose margins waste vertical space
    ".rtr-setup summary{cursor:pointer;font-weight:600}"
    ".rtr-goal{border-bottom:1px solid rgba(0,0,0,.15);"
    "padding-bottom:.5em;margin-bottom:.7em}"
    ".rtr-you{text-align:right}"
    ".rtr-you p{display:inline-block;text-align:left;max-width:75%;"
    "background:rgba(99,102,241,.12);border:1px solid rgba(99,102,241,.35);"
    "border-radius:12px 12px 2px 12px;padding:.3em .7em;margin:.4em 0}"
    # opacity, not color, so the over-art near-black prose rule can't cancel the muting
    ".rtr-beat{font-style:italic;font-size:.95em;opacity:.85;padding-left:1.2em}"
    # the input is the player's NEXT bubble: same indigo tint, border, and signature
    # corner as .rtr-you, just full-width. The Gradio block wrapper goes transparent
    # so only the bubble shows; !important beats the theme's input/block fills.
    # the gray frame is painted by Gradio's .form GROUPING wrapper, not the textbox —
    # clear it (and every layer inside the box except the textarea) so only the bubble shows
    ".form:has(.rtr-say),.rtr-say,.rtr-say :not(textarea){"
    "background:transparent !important;border:none !important;box-shadow:none !important}"
    # solid, not translucent: the scene art bleeding through made the box murky, and the
    # input should be the brightest spot on the card — white with a breath of indigo
    ".rtr-say textarea{background:#f7f8ff !important;"
    "border:1px solid rgba(99,102,241,.35) !important;"
    "border-radius:12px 12px 2px 12px !important;color:#111 !important;"
    "font-size:1.1em;padding:.5em .8em}"
    # Gradio outlines streaming components with an animated accent border; on the
    # transparent Markdown blocks it reads as a stray blue line over the 🤔 status
    ".rtr-game .generating{border:none !important}"
)

# The scene art is a fixed full-viewport backdrop (`.rtr-bg`, emitted by render.room_strip)
# that hides along with its tab. The page container goes transparent so the backdrop shows
# through, and a game that carries one gets a translucent card behind its text to stay
# readable. Games without art keep the plain page. Wired into the Blocks in app.py.
BG_CSS = (
    ".rtr-bg{position:fixed;inset:0;z-index:-1;"
    "background-size:cover;background-position:center}"
    # body must go transparent too: Gradio 6 paints it opaque, and an in-flow body
    # background covers negative-z fixed elements (html keeps the canvas colour)
    "body,gradio-app,.gradio-container{background:transparent !important}"
    ".rtr-game:has(.rtr-bg){background:rgba(255,255,255,.78);"
    "padding:8px 20px 20px;border-radius:14px}"
    # the theme's gray body text washes out over the translucent card — go near-black.
    # Must hit the descendants, not .prose itself: Gradio paints every child directly
    # via `.prose *{color:var(--body-text-color)}`, which beats inheritance. Links keep
    # their own colour (the inline ↻/✎ controls).
    ".rtr-game:has(.rtr-bg) .prose,"
    ".rtr-game:has(.rtr-bg) .prose :not(a){color:#111}"
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
        # sanitize off so avatar <img> tags AND the inline ↻ links render; dynamic text is esc()'d
        story = gr.Markdown(
            render_story(scen, g0) if scen else BLANK_STORY,
            sanitize_html=False,
            elem_classes="rtr-story",
        )
        recap = gr.HTML(visible=False)
        status = gr.Markdown(progress(scen, g0) if scen else "")
        box = gr.Textbox(
            label=PLAYER_VERB,
            show_label=False,
            lines=2,
            autofocus=True,
            elem_classes="rtr-say",
        )
        with gr.Row():
            act = gr.Button(
                f"{PLAYER_VERB} ▶", variant="primary", interactive=bool(scen)
            )
            reset = gr.Button("New game")
        # utility icons, bottom-right under the whole conversation: copy the readable
        # conversation, or the raw LM traces, to the clipboard. Each handler stashes its
        # text in a hidden box, then JS copies it.
        with gr.Row():
            gr.HTML("")  # spacer pushes the icons to the right
            copy_convo = gr.Button("📋", scale=0, size="sm")
            copy_debug = gr.Button("🐞", scale=0, size="sm")
        clip = gr.Textbox(visible=False)

        # hidden plumbing for the inline ↻ links: one button per turn index, each wired below to
        # rewind to ITS turn. The link clicks the matching `.rtr-regen-N`; nothing is passed
        # through the frontend, so there's no value to lose. No on-screen rewind UI.
        regen_btns = [
            gr.Button(elem_classes=[f"{REGEN_CLS}-{i}", "rtr-regen-hide"])
            for i in range(REGEN_CAP)
        ]
        # the ✎ twin of regen_btns: rewind to ITS turn but prefill the box instead of replaying
        edit_btns = [
            gr.Button(elem_classes=[f"{EDIT_CLS}-{i}", "rtr-regen-hide"])
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

    def rewind_bail(game, scen, turn_no):
        """The early-out frame when a rewind can't run — a blank shell when nothing is
        loaded, a no-op frame when the turn no longer exists — or None when it's valid.
        The one guard both rewind paths (↻ replay and ✎ edit) share."""
        if scen is None or game is None:
            return fresh_turn(None)
        if not (0 <= turn_no < len(game.snapshots)):
            return turn_outputs(scen, game, box=gr.update())  # turn no longer exists
        return None

    def make_regenerate(turn_no):
        """A handler bound to one turn index: rewind to player turn `turn_no` (dropping it and
        everything after) and replay it with the same words. The play LM has caching off, so the
        room reacts anew rather than echoing the original — same streaming path as a fresh Say."""

        async def regenerate(game, scen):
            bail = rewind_bail(game, scen, turn_no)
            if bail is not None:
                yield bail
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
            bail = rewind_bail(game, scen, turn_no)
            if bail is not None:
                return bail
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
