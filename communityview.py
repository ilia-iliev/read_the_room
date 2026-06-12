"""The 'Community' view: a gallery of scenarios other players shared — pick a card, read
the premise, play it — plus a share box that publishes a saved .txt (+ optional picture)
for everyone. The creator tab shares the same way through its own button; both land in the
dataset that `community` wraps.
"""

import gradio as gr

import art
import community
import creator


def gallery_items(entries):
    return [
        (e.image or art.banner_image(e.spec.title), e.spec.title or "Untitled")
        for e in entries
    ]


def describe(spec):
    """The premise card for a selected entry."""
    parts = [f"### {spec.title or 'Untitled'}", spec.intro]
    if spec.goal:
        parts.append(f"**Your goal:** {spec.goal}")
    return "\n\n".join(p for p in parts if p)


# refreshing and entering the tab fill the same outputs: the entries, the gallery, a status
# line, and a cleared selection (index + premise card).
def refresh():
    """Reload the gallery from the dataset; missing config or network trouble lands in the
    status line instead of a crash."""
    try:
        entries = community.entries()
    except Exception as e:  # no RTR_COMMUNITY_REPO / hub unreachable — show it in place
        return [], gr.update(value=[]), f"❌ Couldn't load the community: {e}", None, ""
    note = "" if entries else "Nothing here yet — be the first to share a scenario!"
    return entries, gr.update(value=gallery_items(entries)), note, None, ""


def ensure_loaded(entries):
    """Fill the gallery the first time the tab opens; once loaded, only Refresh refetches."""
    if entries:
        return (gr.update(),) * 5
    return refresh()


def select_handler(entries, evt: gr.SelectData):
    return evt.index, describe(entries[evt.index].spec)


def play_or_raise(entries, picked):
    """The selected entry as a playable Scenario, or a toast explaining why not."""
    if picked is None or picked >= len(entries):
        raise gr.Error("Pick a scenario from the gallery first")
    try:
        return community.to_scenario(entries[picked])
    except Exception as e:  # a shared spec that doesn't play — surface the reason
        raise gr.Error(f"{creator.LOAD_ERROR}: {e}")


def share_handler(path, image):
    if not path:
        raise gr.Error("Pick a scenario .txt to share")
    try:
        spec = creator.load_spec(path)
        creator.spec_to_scenario(spec)  # publish only what actually plays
        community.publish(spec, image)
    except Exception as e:  # invalid spec / missing config / failed upload
        raise gr.Error(f"Couldn't share: {e}")
    gr.Info("Shared 🌍 — hit Refresh to see it in the gallery")


def build_community():
    """The Community tab. Returns (play_btn, inputs) for the top level to wire the
    Play-tab handoff — the same handshake the creator hands back."""
    with gr.Tab("🌍 Community") as tab:
        entries_state, picked = gr.State([]), gr.State()
        with gr.Row():
            gr.Markdown("Scenarios other players shared. Pick a card, then play it.")
            refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=0)
        status = gr.Markdown()
        gallery = gr.Gallery(
            show_label=False,
            columns=4,
            allow_preview=False,
            interactive=False,
        )
        details = gr.Markdown()
        play_btn = gr.Button("Play it ▶", variant="primary")

        with gr.Accordion("Share yours", open=False):
            gr.Markdown(
                "Anyone can add a scenario: upload a saved .txt (the creator's ⬇️ Save"
                " format), add a picture if you like, and it appears here for everyone."
            )
            with gr.Row():
                spec_file = gr.File(
                    label="Scenario (.txt)", file_types=[".txt"], type="filepath"
                )
                picture = gr.Image(
                    label="Picture (optional)",
                    type="filepath",
                    sources=["upload"],
                    height=160,
                )
            share_btn = gr.Button("🌍 Share it", scale=0)

        refresh_outs = [entries_state, gallery, status, picked, details]
        refresh_btn.click(refresh, None, refresh_outs)
        tab.select(ensure_loaded, entries_state, refresh_outs)
        gallery.select(select_handler, entries_state, [picked, details])
        share_btn.click(share_handler, [spec_file, picture], None)

    return play_btn, [entries_state, picked]
