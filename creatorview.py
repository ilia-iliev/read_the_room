"""The 'Create your own' view: a scenario form that starts preloaded with a blank template
— premise fields, one card per character, the disposition matrix as an editable grid. Fill
it by hand, or let the AI author the whole thing from a one-line idea. Attach art, bundle
it, and hand the parsed Scenario off to the Play tab. Nobody edits raw JSON here; Download
bundle still serializes the spec.
"""

import gradio as gr
import pandas as pd

import bundle
import creator
from art import slug

MAX_CAST = 6  # the editor pre-builds this many character cards and shows the live ones
WHO = "Who"  # the grid's display-only first column; cells are read by position, not header


def grid_value(characters):
    """The disposition matrix as a grid: one row per character (first cell their name), then
    one cell per party — Player plus every name; a character's own column is their mood."""
    names = [c.name for c in characters]
    keys = ["Player", *names]
    rows = [[c.name, *(c.disposition.get(k, "") for k in keys)] for c in characters]
    return pd.DataFrame(rows, columns=[WHO, *keys])


def cell(grid, i, j):
    """One grid cell as text, tolerant of rows/columns missing from the live dataframe."""
    if i < grid.shape[0] and j < grid.shape[1]:
        v = grid.iat[i, j]
        return str(v) if pd.notna(v) else ""
    return ""


def rebuild_grid(grid, names):
    """The grid resized and re-headed to `names`, every surviving cell kept by position
    (new parties get empty cells, dropped ones lose theirs)."""
    cols = [WHO, "Player", *names]
    rows = [
        [name, *(cell(grid, i, j) for j in range(1, len(cols)))]
        for i, name in enumerate(names)
    ]
    return pd.DataFrame(rows, columns=cols)


def grid_widths(ncols):
    """Column widths that always fit: a narrow name gutter, then an equal share per
    disposition column — otherwise wide cells push the last columns off the edge and
    they can't be edited."""
    share = f"{92 / max(ncols - 1, 1):.0f}%"
    return ["8%", *[share] * (ncols - 1)]


def grid_update(df):
    return gr.update(value=df, column_widths=grid_widths(len(df.columns)))


def named(values, k):
    """The first k name boxes, blank ones falling back to a placeholder."""
    return [values[i] or f"Character {i + 1}" for i in range(k)]


def assemble(title, intro, goal, max_turns, win, lose, grid, cast, *fields):
    """Read the whole form back into a ScenarioSpec. `fields` is the MAX_CAST name boxes
    then the MAX_CAST persona boxes; the first len(cast) of each are live. Grid cells are
    read by position, so its headers stay display-only."""
    names = named(fields, len(cast))
    keys = ["Player", *names]
    characters = [
        creator.CharSpec(
            name=name,
            persona=fields[MAX_CAST + i] or "",
            disposition={k: cell(grid, i, j + 1) for j, k in enumerate(keys)},
        )
        for i, name in enumerate(names)
    ]
    return creator.ScenarioSpec(
        title=title or "",
        intro=intro or "",
        goal=goal or "",
        max_turns=int(max_turns),
        verdict_labels=[
            win or creator.DEFAULT_LABELS[0],
            lose or creator.DEFAULT_LABELS[1],
        ],
        characters=characters,
    )


# authoring and loading fill the same outputs: a status line (errors only — success is
# silent, the form filling in IS the feedback), every premise field, the grid, the cast
# (drives the avatar uploaders), the art mapping, the scene banner, and the MAX_CAST card
# slots (visibility, name, persona).
def filled(spec, art):
    """The full creator output row for a freshly loaded spec."""
    chars = spec.characters
    labels = spec.verdict_labels
    win = labels[0] if labels else creator.DEFAULT_LABELS[0]
    lose = labels[1] if len(labels) > 1 else creator.DEFAULT_LABELS[1]
    shown = [gr.update(visible=i < len(chars)) for i in range(MAX_CAST)]
    names = [chars[i].name if i < len(chars) else "" for i in range(MAX_CAST)]
    personas = [chars[i].persona if i < len(chars) else "" for i in range(MAX_CAST)]
    return (
        "",
        spec.title,
        spec.intro,
        spec.goal,
        spec.max_turns,
        win,
        lose,
        grid_update(grid_value(chars)),
        [c.name for c in chars],
        art,
        art.get("scene"),
        *shown,
        *names,
        *personas,
    )


def abort(msg):
    """Leave the editor untouched and just show a status line."""
    return (msg, *(gr.update(),) * (10 + 3 * MAX_CAST))


def author_handler(idea, n):
    idea = (idea or "").strip()
    if not idea:
        return abort("✍️ Describe your idea first.")
    try:
        spec = creator.author(idea, int(n))
    except (
        Exception
    ) as e:  # malformed model output / parse failure — show it, don't crash
        return abort(f"❌ Authoring failed: {e}")
    return filled(spec, {})


def load_handler(zip_path):
    if not zip_path:
        return abort("⬆️ Pick a .zip bundle.")
    try:
        spec_text, art = bundle.unpack(zip_path)
        spec = creator.from_json(spec_text)
    except (
        Exception
    ) as e:  # not a bundle / spec inside is invalid — surface it, keep the editor as-is
        return abort(f"❌ Couldn't load that bundle: {e}")
    if len(spec.characters) > MAX_CAST:
        return abort(f"❌ This editor holds up to {MAX_CAST} characters.")
    return filled(spec, art)


def rename_handler(cast_now, art, grid, *names):
    """Live rename: the cast list, the grid headers, and the art keys all follow the name
    boxes; every disposition cell survives by position."""
    new = named(names, len(cast_now))
    art = dict(art)
    for old, name in zip(cast_now, new):
        if name != old and slug(old) in art:
            art[slug(name)] = art.pop(slug(old))
    return new, art, grid_update(rebuild_grid(grid, new))


# add/remove both write the same outputs: cast, art, grid, and every card slot.
def cards_noop():
    return (gr.update(),) * (3 + 3 * MAX_CAST)


def add_handler(cast_now, grid):
    if len(cast_now) >= MAX_CAST:
        return cards_noop()
    k = len(cast_now)
    name = f"Character {k + 1}"
    new = [*cast_now, name]
    shown = [
        gr.update(visible=True) if i == k else gr.update() for i in range(MAX_CAST)
    ]
    names = [name if i == k else gr.update() for i in range(MAX_CAST)]
    personas = ["" if i == k else gr.update() for i in range(MAX_CAST)]
    return (
        new,
        gr.update(),
        grid_update(rebuild_grid(grid, new)),
        *shown,
        *names,
        *personas,
    )


def remove_handler(cast_now, art, grid):
    if len(cast_now) <= 1:  # a scenario needs at least one character
        return cards_noop()
    new = list(cast_now[:-1])
    art = dict(art)
    art.pop(slug(cast_now[-1]), None)
    shown = [
        gr.update(visible=False) if i == len(new) else gr.update()
        for i in range(MAX_CAST)
    ]
    return (
        new,
        art,
        grid_update(rebuild_grid(grid, new)),
        *shown,
        *cards_noop()[: 2 * MAX_CAST],
    )


def parse_or_raise(*args):
    """Build the Scenario the player is about to play from the form (art rides last), or
    raise a toast they can read. The .success() chain only fires on a clean parse, so the
    Play tab is never half-filled."""
    try:
        return creator.spec_to_scenario(assemble(*args[:-1]), args[-1])
    except Exception as e:  # invalid / incomplete spec — surface the reason as a toast
        raise gr.Error(f"Couldn't load this spec: {e}")


def pack_handler(*args):
    """Serialize the form to the spec JSON and zip it with the art."""
    return bundle.pack(creator.to_json(assemble(*args[:-1])), args[-1])


def set_art(current, key, path):
    """Update the in-session art mapping: bind `key` to the uploaded `path`, or drop it when
    the slot is cleared. Absent slots fall back to the generated placeholders."""
    current = dict(current)
    if path:
        current[key] = path
    else:
        current.pop(key, None)
    return current


def build_creator():
    """A tab with the scenario form, preloaded blank, that the AI can fill from a one-line
    idea; pressing Play hands it to the dedicated Play tab. Returns the refs the top-level
    needs to wire that handoff: (play_btn, form_inputs, art)."""
    blank = creator.blank_spec(3)
    with gr.Tab("✨ Create your own"):
        gr.Markdown(
            "### Author a scenario\n"
            "Describe a social standoff and how many people are in the room. The AI writes the "
            "whole thing — the cast, the premise, the fairness rules that keep it winnable "
            "— and you can edit any of it before you play. Or just fill the form by hand."
        )
        with gr.Row():
            idea = gr.Textbox(
                label="Your idea",
                placeholder="A high-school reunion — I need my estranged best friend to "
                "forgive me before the night is over.",
                lines=2,
                scale=3,
            )
            n = gr.Slider(
                1,
                MAX_CAST,
                value=len(blank.characters),
                step=1,
                label="People in the room",
                scale=1,
            )
        with gr.Row():
            author_btn = gr.Button("Author with AI ✨", variant="primary")
            load_btn = gr.UploadButton(
                "⬆️ Load bundle (.zip)", file_types=[".zip"], type="filepath"
            )
        status = gr.Markdown()

        title = gr.Textbox(label="Title")
        intro = gr.Textbox(label="Intro — the scene, addressed to you", lines=3)
        with gr.Row():
            goal = gr.Textbox(label="Goal — the win condition", lines=2, scale=3)
            max_turns = gr.Slider(
                1, 12, value=blank.max_turns, step=1, label="Max turns", scale=1
            )
        gr.Markdown("#### The cast")
        groups, names, personas = [], [], []
        for i in range(MAX_CAST):
            live = i < len(blank.characters)
            # table-like: the column labels show on the first card only
            with gr.Group(visible=live) as g:
                with gr.Row():
                    nm = gr.Textbox(
                        value=blank.characters[i].name if live else "",
                        label="Name",
                        show_label=i == 0,
                        scale=1,
                    )
                    pe = gr.Textbox(
                        label="Persona — who they are, their voice, what they want",
                        show_label=i == 0,
                        lines=2,
                        scale=4,
                    )
            groups.append(g)
            names.append(nm)
            personas.append(pe)
        with gr.Row():
            add_btn = gr.Button("➕ Add character", size="sm")
            remove_btn = gr.Button("➖ Remove last", size="sm")

        start_grid = grid_value(blank.characters)
        grid = gr.Dataframe(
            value=start_grid,
            label="Dispositions — how each mind reads the room "
            "(rows react to columns; their own column is their current mood)",
            interactive=True,
            wrap=True,
            static_columns=[0],
            column_widths=grid_widths(len(start_grid.columns)),
        )

        with gr.Row():
            win = gr.Textbox(
                label="Verdict when you win", value=creator.DEFAULT_LABELS[0]
            )
            lose = gr.Textbox(
                label="Verdict when you lose", value=creator.DEFAULT_LABELS[1]
            )

        # art rides along with the spec: 'scene' + one entry per character slug -> a
        # filepath. absent slots fall back to the generated placeholders. cast drives
        # the uploader layout.
        art = gr.State({})
        cast = gr.State([c.name for c in blank.characters])
        with gr.Accordion(
            "🎨 Art (optional) — pictures bundle with the scenario", open=False
        ):
            scene_img = gr.Image(label="Scene banner", type="filepath", height=160)

            @gr.render(inputs=[cast, art])
            def render_avatars(cast_now, art_now):
                with gr.Row():
                    for name in cast_now:
                        s = slug(name)
                        pic = gr.Image(
                            label=name,
                            type="filepath",
                            height=140,
                            value=art_now.get(s),
                        )
                        pic.change(
                            lambda path, current, s=s: set_art(current, s, path),
                            [pic, art],
                            art,
                        )

        with gr.Row():
            play_btn = gr.Button("Play it ▶", variant="primary", scale=3)
            download_btn = gr.DownloadButton("⬇️ Download bundle (.zip)", scale=1)

        form_inputs = [title, intro, goal, max_turns, win, lose, grid, cast]
        form_inputs += [*names, *personas]
        outputs = [status, *form_inputs[:7], cast, art, scene_img]
        outputs += [*groups, *names, *personas]

        # everything the player could press or type locks while the AI authors, so a
        # half-written room can't be edited or re-authored mid-flight.
        lockable = [
            author_btn,
            idea,
            n,
            load_btn,
            play_btn,
            download_btn,
            add_btn,
            remove_btn,
            *form_inputs[:7],
            *names,
            *personas,
        ]
        author_btn.click(
            lambda: [gr.update(interactive=False)] * len(lockable), None, lockable
        ).then(author_handler, [idea, n], outputs).then(
            lambda: [gr.update(interactive=True)] * len(lockable), None, lockable
        )
        load_btn.upload(load_handler, [load_btn], outputs)
        # .input (not .change) so programmatic fills don't echo back through the handler
        for nm in names:
            nm.input(rename_handler, [cast, art, grid, *names], [cast, art, grid])
        card_outputs = [cast, art, grid, *groups, *names, *personas]
        add_btn.click(add_handler, [cast, grid], card_outputs)
        remove_btn.click(remove_handler, [cast, art, grid], card_outputs)
        scene_img.change(
            lambda path, current: set_art(current, "scene", path),
            [scene_img, art],
            art,
        )
        download_btn.click(pack_handler, [*form_inputs, art], download_btn)

    return play_btn, form_inputs, art
