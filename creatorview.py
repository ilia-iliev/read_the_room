"""The 'Create your own' view: author a scenario from a prompt (or a blank template), edit
the spec, attach art, bundle it, and hand the parsed Scenario off to the Play tab.
"""

import gradio as gr

import bundle
import creator
from art import slug


# authoring/scratch/load all yield the same five outputs: spec text, a status line, the
# cast names (which lay out the avatar uploaders), the art mapping, and the scene-banner value.
def loaded(spec_text, status, names, art):
    """The five creator outputs for a freshly loaded spec: the spec text, a status line, the
    cast (drives the avatar uploaders), the art mapping, and the scene banner read from it."""
    return spec_text, status, names, art, art.get("scene")


def abort(msg):
    """Leave the editor untouched and just show a status line — the five creator outputs."""
    return gr.update(), msg, gr.update(), gr.update(), gr.update()


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
    return loaded(
        creator.to_json(spec),
        "✅ Authored — add art (optional), tweak, then **Play it ▶**",
        [c.name for c in spec.characters],
        {},  # fresh cast, so drop any art from a previous scenario
    )


def scratch_handler(n):
    text = creator.blank_json(int(n))
    return loaded(
        text,
        "✏️ Blank template — fill it in, add art, then **Play it ▶**",
        creator.cast_names(text),
        {},
    )


def load_handler(zip_path):
    if not zip_path:
        return abort("⬆️ Pick a .zip bundle.")
    try:
        spec_text, art = bundle.unpack(zip_path)
        names = creator.cast_names(spec_text)
    except (
        Exception
    ) as e:  # not a bundle / spec inside is invalid — surface it, keep the editor as-is
        return abort(f"❌ Couldn't load that bundle: {e}")
    return loaded(
        spec_text, "✅ Loaded — tweak, swap art, then **Play it ▶**", names, art
    )


def parse_or_raise(spec_text, art):
    """Build the Scenario the player is about to play, or raise a toast they can read. The
    .success() chain only fires on a clean parse, so the Play tab is never half-filled."""
    try:
        return creator.scenario_from_json(spec_text, art)
    except Exception as e:  # invalid / incomplete spec — surface the reason as a toast
        raise gr.Error(f"Couldn't load this spec: {e}")


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
    """A tab that authors a scenario from a prompt (or a blank template) and lets the player
    edit the spec; pressing Play hands it to the dedicated Play tab. Returns the refs the
    top-level needs to wire that handoff: (play_btn, spec, art)."""
    with gr.Tab("✨ Create your own"):
        gr.Markdown(
            "### Author a scenario\n"
            "Describe a social standoff and how many people are in the room. The AI writes the "
            "whole thing — the cast, the premise, the fairness rules that keep it winnable "
            "— and you can edit any of it before you play. Or start from scratch."
        )
        with gr.Row():
            idea = gr.Textbox(
                label="Your idea",
                placeholder="A high-school reunion — I need my estranged best friend to "
                "forgive me before the night is over.",
                lines=2,
                scale=3,
            )
            n = gr.Slider(1, 4, value=3, step=1, label="People in the room", scale=1)
        with gr.Row():
            author_btn = gr.Button("Author with AI ✨", variant="primary")
            scratch_btn = gr.Button("Start from scratch ✏️")
        status = gr.Markdown()
        spec = gr.Code(language="json", label="Scenario spec — edit freely")

        # art rides along with the spec: 'scene' + one entry per character slug -> a filepath.
        # absent slots fall back to the generated placeholders. cast drives the uploader layout.
        art = gr.State({})
        cast = gr.State([])
        with gr.Accordion(
            "🎨 Art (optional) — pictures bundle with the scenario", open=False
        ):
            scene_img = gr.Image(label="Scene banner", type="filepath", height=160)

            @gr.render(inputs=[cast, art])
            def render_avatars(names, art_now):
                if not names:
                    gr.Markdown("*Author or load a scenario to add avatars.*")
                    return
                with gr.Row():
                    for name in names:
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
                download_btn = gr.DownloadButton("⬇️ Download bundle (.zip)")
                load_btn = gr.UploadButton(
                    "⬆️ Load bundle", file_types=[".zip"], type="filepath"
                )

        play_btn = gr.Button("Play it ▶", variant="primary")

        outputs = [spec, status, cast, art, scene_img]
        author_btn.click(author_handler, [idea, n], outputs)
        scratch_btn.click(scratch_handler, [n], outputs)
        load_btn.upload(load_handler, [load_btn], outputs)
        scene_img.change(
            lambda path, current: set_art(current, "scene", path),
            [scene_img, art],
            art,
        )
        download_btn.click(bundle.pack, [spec, art], download_btn)

    return play_btn, spec, art
