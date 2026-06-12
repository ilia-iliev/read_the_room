"""Pure renderers for the game view: everything that turns (scenario, game) into the
strings and component updates the player sees. Nothing here creates a Gradio component —
gameview.py builds the layout and handlers on top of these.
"""

import html

import gradio as gr

from art import avatar_uri, scene_uri
from engine import final_verdict, new_game

WIN_ICON, LOSE_ICON = "🏆", "💀"

# the player-facing verb: the input label, the act button, and the turn status line
PLAYER_VERB = "Say"


def esc(text):
    """Neutralise raw HTML in model/player text. The transcript renders with the HTML
    sanitizer OFF (so our SVG-avatar <img> tags survive), so dynamic text is escaped here
    instead — markdown (*, _, ---) still works, injected tags don't."""
    return html.escape(text or "", quote=False)


# A scenario-agnostic cue to act, shown once at the opening (intros set the scene but don't
# all end on a hook). The player is "you" here; the model channel never sees this line.
# Rendered as a narration beat, so the italics come from the CSS register, not markdown.
PROMPT_TO_SPEAK = "The room turns to you. What do you say?"


# Inline rewind links on each of the player's past lines. Each turn index has its own hidden
# button (`.rtr-regen-N` / `.rtr-edit-N`, wired in gameview.py), so the link just confirms and
# clicks that button — no value passes through the frontend. These prefixes are the contract
# between the links here and the hidden buttons gameview builds.
REGEN_CLS = "rtr-regen"
EDIT_CLS = "rtr-edit"


def _click_hidden(cls, confirm):
    """JS for an inline link: confirm, then click THIS game's hidden `.cls` button (scoped to the
    nearest `.rtr-game`, so the right game answers even with several game tabs in the page)."""
    return (
        f"if(confirm('{confirm}'))"
        f"{{var t=this.closest('.rtr-game').querySelector('.{cls}');"
        # elem_classes lands on the <button> itself for a Button, but on a wrapper for others —
        # so click the element if it's the button, else its inner button.
        "(t.tagName==='BUTTON'?t:t.querySelector('button')).click();}return false;"
    )


def _inline_link(cls_prefix, turn_no, icon, title, confirm):
    """A small inline icon that clicks the hidden `.cls_prefix-turn_no` button for player turn
    `turn_no` (0-based, indexing game.snapshots), after a confirm prompt."""
    return (
        f' <a href="#" title="{title}" '
        'style="text-decoration:none;cursor:pointer;opacity:.5" '
        f'onclick="{_click_hidden(f"{cls_prefix}-{turn_no}", confirm)}">{icon}</a>'
    )


def regen_link(turn_no):
    """↻ — rewind to this turn and replay it with the SAME words, fresh reactions."""
    return _inline_link(
        REGEN_CLS,
        turn_no,
        "↻",
        "Rewind &amp; regenerate from here",
        "Rewind here and replay from this line? Everything after it is discarded.",
    )


def edit_link(turn_no):
    """✎ — rewind to this turn and drop the original words back in the box to reword first."""
    return _inline_link(
        EDIT_CLS,
        turn_no,
        "✎",
        "Rewind &amp; edit this line",
        "Rewind here to reword this line? Everything after it is discarded.",
    )


def _block(cls, body):
    """One transcript entry as a classed <div> whose markdown stays live: the blank lines
    make the tag its own HTML block, so the body still renders as markdown paragraph(s)
    while CSS addresses each kind of entry by class (the registers in gameview.STORY_CSS)."""
    return f'\n\n<div class="{cls}">\n\n{body}\n\n</div>'


def header(scen, started):
    """The setup card: the intro folded into a <details> that stands open until the player's
    first line and collapses to one row after, with the goal pinned visible below it — the
    goal's underline (CSS) is the boundary where the setup ends and play begins."""
    state = "" if started else " open"
    return (
        f'<details class="rtr-setup"{state}><summary>📜 The scene</summary>\n\n'
        f"{esc(scen.intro)}\n\n</details>"
        + _block("rtr-goal", f"**Goal:** {esc(scen.goal)}")
    )


def speaker_tag(uri, name):
    """The lead-in for a character's spoken line: their avatar followed by their name."""
    attr = html.escape(name)
    return (
        f'<img src="{uri}" alt="{attr}" title="{attr}" width="30" height="30" '
        'style="display:inline-block;border-radius:50%;vertical-align:middle;'
        'margin:0 8px 0 0">'
        f'<strong style="vertical-align:middle;margin-right:8px">{attr}:</strong>'
    )


def render_story(scen, game, current=None):
    """Rebuild the player-facing transcript from the game log. `current` is whatever is being
    written live and not yet committed to the log: a speaker's partial dict (name/line), or a
    scene beat the director is writing (`{"beat": text}`). Private reasoning is never shown
    here — it lives in the debug log."""
    avatars = {c.name: avatar_uri(scen, c) for c in scen.characters}
    started = any(e.kind == "player" for e in game.log)
    md = header(scen, started)
    if not started:  # opening: cue the player to speak
        md += _block("rtr-beat", PROMPT_TO_SPEAK)
    turn_no = 0  # 0-based index of each player turn, matching game.snapshots for rewind
    for e in game.log[1:]:  # log[0] is the intro; the setup card already shows it
        if e.kind == "beat":
            md += _block("rtr-beat", esc(e.text))
        elif e.kind == "player":
            md += _block(
                "rtr-you",
                f"“{esc(e.text)}”{regen_link(turn_no)}{edit_link(turn_no)}",
            )
            turn_no += 1
        elif e.kind == "line":
            md += _block(
                "rtr-line", f"{speaker_tag(avatars[e.who], e.who)} {esc(e.text)}"
            )
    if current and "name" in current:  # a character speaking live
        tag = speaker_tag(avatars[current["name"]], current["name"])
        md += _block("rtr-line", f"{tag} {esc(current['line'])} ▌")
    elif current:  # a scene beat the director is writing live
        md += _block("rtr-beat", f"{esc(current['beat'])} ▌")
    return md


def render_debug(scen, game):
    """The full plain-text transcript for copy-paste debugging: every beat, the player's
    words, and each character's PRIVATE reasoning alongside what they said."""
    if scen is None or game is None:
        return "(nothing to copy yet)"
    lines = [f"SETUP: {scen.intro}", f"GOAL: {scen.goal}", ""]
    for e in game.log:
        if e.kind == "beat":
            lines.append(f"[scene] {e.text}")
        elif e.kind == "player":
            lines.append(f"YOU: {e.text}")
        elif e.kind == "line":
            if e.reasoning:
                lines.append(f"{e.who} (thinks): {e.reasoning}")
            lines.append(f"{e.who}: {e.text}")
    if not game.active:
        lines += ["", f"RESULT: {final_verdict(game)}"]
    lines += ["", "-- current dispositions --"]
    for name, cs in game.chars.items():
        row = cs.disposition
        lines.append(f"{name}:")
        lines.append(f"    player: {row.get('Player', '')}")
        lines.append(f"    self:   {row.get(name, '')}")
        lines += [
            f"    -> {k}: {v}" for k, v in row.items() if k not in ("Player", name)
        ]
    return "\n".join(lines)


def export_debug(game):
    """The full raw LM input+output for every turn — the trace."""
    return "\n".join(game.trace) if game and game.trace else "(no turns yet)"


def progress(scen, game):
    used, total = game.turn, scen.max_turns
    if not game.active:
        return "**Game Over**"
    return f"**You {PLAYER_VERB.lower()}…** ({used + 1}/{total})"


def room_strip(scen):
    """The scene art as a full-page backdrop behind the story (`.rtr-bg`, styled in
    gameview.BG_CSS) — only when the scenario carries a real image; otherwise nothing and
    the plain page stands. The cast appear inline as they speak in the transcript, and how
    they finally read you is the end screen."""
    uri = scene_uri(scen)
    if not uri:
        return ""
    return f'<div class="rtr-bg" style="background-image:url({uri})"></div>'


def _web_rows(scen, game, c):
    """The lines of one character's final stance web: their read of the player, of each other
    character, then their own closing mood (self) — each pulled straight from the matrix."""
    row = game.chars[c.name].disposition
    out = [f"<b>You:</b> {esc(row.get('Player', ''))}"]
    out += [
        f"<b>{esc(o.name)}:</b> {esc(row.get(o.name, ''))}"
        for o in scen.characters
        if o.name != c.name and row.get(o.name)
    ]
    mood = row.get(c.name, "")
    if mood:
        out.append(f"<b>Self:</b> <i>{esc(mood)}</i>")
    return out


def end_screen(scen, game):
    """The verdict card: the result, plus how each mind finally read the player, the others,
    and itself — straight from the disposition matrix, no extra model calls. Gated on
    `concluded`, not the derived `active`: the clock-cap turn flips `active` off before
    `outcome` is known, and the finale must stream without flashing an undecided verdict."""
    if not game.concluded:
        return gr.update(value="", visible=False)
    verdict = final_verdict(game)
    icon = WIN_ICON if verdict == scen.verdict_labels[0] else LOSE_ICON
    cards = "".join(
        f'<div style="display:flex;gap:12px;align-items:flex-start;margin:12px 0">'
        f'<img src="{avatar_uri(scen, c)}" '
        f'style="width:52px;height:52px;border-radius:50%;flex:none"/>'
        f"<div><b>{esc(c.name)}</b>"
        + "".join(
            f'<div style="opacity:.85;font-size:.92em">{line}</div>'
            for line in _web_rows(scen, game, c)
        )
        + "</div></div>"
        for c in scen.characters
    )
    return gr.update(
        value=(
            f'<div style="text-align:center;font-size:44px;line-height:1">{icon}</div>'
            f'<div style="text-align:center;font-size:24px;font-weight:700;'
            f'letter-spacing:3px;margin-top:2px">{verdict}</div>'
            f'<hr style="margin:14px 0">'
            f'<div style="font-weight:600;margin-bottom:2px">How the room ended up</div>'
            f"{cards}"
        ),
        visible=True,
    )


def buttons(active):
    """(act, reset) button states. While playing, act is the bright primary; once the tale
    is told, act greys out and New game becomes the obvious next move."""
    if active:
        return (
            gr.update(interactive=True, variant="primary"),
            gr.update(variant="secondary"),
        )
    return (
        gr.update(interactive=False, variant="secondary"),
        gr.update(variant="primary"),
    )


BLANK_STORY = (
    "*Author a scenario in **✨ Create your own**, then press **Play it ▶** "
    "— it opens here. Already have a saved scenario? Load the `.txt` above.*"
)


def turn_outputs(scen, game, *, box, status=None, current=None):
    """The seven per-turn outputs in build_game_ui's turn_outs order, for a live game.
    `box` is the input update; `status` and `current` override the defaults for the
    live-streaming frame (a fixed think cue and the in-progress speaker)."""
    return (
        render_story(scen, game, current),
        progress(scen, game) if status is None else status,
        box,
        game,
        *buttons(game.active),
        end_screen(scen, game),
    )


def fresh_turn(scen):
    """The seven per-turn outputs for a brand-new game of `scen`, or a blank shell when
    `scen` is None (the custom tab before anything is loaded into it)."""
    if scen is None:
        return (
            BLANK_STORY,
            "",
            gr.update(value="", visible=False),
            None,
            *buttons(False),
            gr.update(value="", visible=False),
        )
    return turn_outputs(scen, new_game(scen), box=gr.update(value="", visible=True))
