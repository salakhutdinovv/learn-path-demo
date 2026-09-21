import os

import streamlit as st

from planner import generate, cost_label

st.set_page_config(page_title="MIT Learn path demo", page_icon="🎓")

# Simple shared-password gate. Set APP_PASSWORD in Streamlit secrets (or env) to enable.
try:
    _pw = st.secrets.get("APP_PASSWORD", "")
except Exception:  # no secrets file locally
    _pw = ""
_pw = _pw or os.environ.get("APP_PASSWORD", "")
if _pw and not st.session_state.get("authed"):
    if st.text_input("Password", type="password") == _pw:
        st.session_state["authed"] = True
        st.rerun()
    st.stop()
st.title("Personalized learning plan from MIT Learn")
st.caption("Tell us what you want to learn and a bit about yourself. "
           "The plan is built only from resources returned by the MIT Learn catalog search.")

request = st.text_area(
    "What do you want to learn?",
    placeholder="I'm a parent with a basic bio background, I have about an hour, how does the covid vaccine work?",
    height=110,
)

if st.button("Generate plan", type="primary", disabled=not request.strip()):
    with st.spinner("Breaking down your request, searching MIT Learn, and building your plan..."):
        try:
            out = generate(request.strip())
        except Exception as e:  # keep the demo alive on API hiccups
            st.error(f"Something went wrong: {e}")
            st.stop()

    st.subheader("Your plan")
    st.write(f"**Rough total time:** {out['total_time']}")
    for i, s in enumerate(out["steps"], 1):
        with st.container(border=True):
            st.markdown(f"**{i}. [{s['title']}]({s['url']})**")
            st.markdown(
                f"`{s['resource_type'].replace('_', ' ')}` · {cost_label(s)} · ~{s['estimated_time']} · "
                f"{s['offered_by'] or s['platform']} · *{s['subtopic']}*"
            )
            st.write(s["why"])

    st.markdown(f"**Why this plan:** {out['rationale']}")
    st.info(f"**What the catalog doesn't cover well:** {out['gaps']}")
    if out["dropped_ids"]:
        st.warning(f"Dropped {len(out['dropped_ids'])} step(s) that referenced resources not returned by the search.")

    with st.expander("Behind the scenes: sub-topic searches and raw results"):
        st.write(f"**Learner summary:** {out['subtopics']['learner_summary']}")
        for st_ in out["subtopics"]["subtopics"]:
            rs = out["results"].get(st_["title"], [])
            st.markdown(f"#### {st_['title']}")
            st.markdown(f"Search query: `{st_['search_query']}` — {len(rs)} results  \n_{st_['why']}_")
            if rs:
                st.dataframe(
                    [{"id": r["id"], "title": r["title"], "type": r["resource_type"],
                      "offered by": r["offered_by"], "cost": cost_label(r), "time": r["time"], "url": r["url"]}
                     for r in rs],
                    hide_index=True, use_container_width=True,
                )
            else:
                st.write("No results.")
        st.json(out["results"], expanded=False)
