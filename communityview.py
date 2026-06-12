"""The 'Community' view: a gallery of scenarios other players shared — pick a card, read
the premise, play it. Sharing happens in the creator tab (its 🌍 button publishes the
form); this tab's Share-yours button just jumps there.
"""

import gradio as gr

import art
import community
import creator


def gallery_items(entries):
    return [
        (
            art.thumbnail(e.image) if e.image else art.banner_image(e.spec.title),
            e.spec.title or "Untitled",
        )
        for e in entries
    ]


def describe(spec):
    """The premise card for a selected entry."""
    parts = [f"### {spec.title or 'Untitled'}", spec.intro]
    if spec.goal:
        parts.append(f"**Your goal:** {spec.goal}")
    return "\n\n".join(p for p in parts if p)


def matches(spec, query):
    """Case-insensitive substring match over what a card could tell you: title, premise,
    goal, and who's in the room."""
    hay = " ".join(
        [spec.title, spec.intro, spec.goal, *(c.name for c in spec.characters)]
    )
    return query.lower() in hay.lower()


def filter_entries(entries, query):
    query = (query or "").strip()
    return [e for e in entries if matches(e.spec, query)] if query else entries


# refreshing, entering the tab, and typing in the search box fill the same outputs: all
# entries, the shown (filtered) subset, the gallery, a status line, and a cleared
# selection (index + premise card).
def show(entries, query):
    """The gallery narrowed to the current search; no refetch."""
    shown = filter_entries(entries, query)
    if not entries:
        note = "Nothing here yet — be the first to share a scenario!"
    else:
        note = "" if shown else "No scenarios match your search."
    return entries, shown, gr.update(value=gallery_items(shown)), note, None, ""


def refresh(query):
    """Reload the gallery from the dataset; missing config or network trouble lands in the
    status line instead of a crash."""
    try:
        entries = community.entries()
    except Exception as e:  # no RTR_COMMUNITY_REPO / hub unreachable — show it in place
        err = f"❌ Couldn't load the community: {e}"
        return [], [], gr.update(value=[]), err, None, ""
    return show(entries, query)


def ensure_loaded(entries, query):
    """Fill the gallery the first time the tab opens; once loaded, only Refresh refetches."""
    if entries:
        return (gr.update(),) * 6
    return refresh(query)


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


def build_community():
    """The Community tab. Returns (play_btn, inputs, share_btn) — the first two for the
    top level to wire the Play-tab handoff (the same handshake the creator hands back),
    the last to wire the jump to the creator tab."""
    with gr.Tab("🌍 Community") as tab:
        entries_state, shown_state = gr.State([]), gr.State([])
        picked = gr.State()
        with gr.Row():
            gr.Markdown("Scenarios other players shared. Pick a card, then play it.")
            query = gr.Textbox(
                placeholder="🔍 Search",
                show_label=False,
                container=False,
                scale=0,
                min_width=220,
            )
            refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=0)
        status = gr.Markdown()
        gallery = gr.Gallery(
            show_label=False,
            columns=4,
            fit_columns=False,  # a lone card stays card-sized instead of going full-width
            allow_preview=False,
            interactive=False,
        )
        details = gr.Markdown()
        play_btn = gr.Button("Play it ▶", variant="primary")
        share_btn = gr.Button(
            "🌍 Share yours — make it in ✨ Create your own", size="sm"
        )

        refresh_outs = [entries_state, shown_state, gallery, status, picked, details]
        refresh_btn.click(refresh, query, refresh_outs)
        tab.select(ensure_loaded, [entries_state, query], refresh_outs)
        query.change(show, [entries_state, query], refresh_outs)
        gallery.select(select_handler, shown_state, [picked, details])

    return play_btn, [shown_state, picked], share_btn
