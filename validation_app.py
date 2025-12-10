import streamlit as st
import json
from pathlib import Path
from PIL import Image
import pandas as pd
from datetime import datetime
import urllib.parse

DATE = '202301_samples'
VAL_DIR = Path(f"data/{DATE}")
FEEDBACK_FILE = Path(f"feedback/{DATE}/feedback.csv")

def parse_date_from_filename(name: str):
    parts = name.split("_")
    for p in parts:
        try:
            if len(p) == 8 and p.isdigit():
                return datetime.strptime(p, "%Y%m%d").date()
            if len(p) == 10 and "-" in p:
                return datetime.strptime(p, "%Y-%m-%d").date()
        except Exception:
            continue
    return None

def list_images(folder_path: Path):
    if not folder_path.exists():
        return []
    return sorted(
        [f for f in folder_path.iterdir() if f.suffix.lower() in {".jpg", ".jpeg", ".png"}],
        key=lambda f: parse_date_from_filename(f.name) or f.name
    )

def load_image(image_path: Path):
    return Image.open(image_path)

def render_image_gallery_with_captions(image_dir, sat_timeline, source, start_date=None, end_date=None):
    """
    Uses the per-source rewrite metadata.json (new schema) ONLY for:
      - timeline (list of {year, month, day, caption})
      - initial_visual_success / initial_visual_reason (displayed in a separate box outside this function)
    """
    image_files = list_images(image_dir)

    # No images: show a gentle message and bail.
    if not image_files:
        st.warning(f"No images found in: {image_dir}")
        return

    # Build a date->caption mapping from metadata.json, if present
    captions = {}
    for entry in sat_timeline:
        try:
            dt = datetime(
                year=entry["year"],
                month=datetime.strptime(entry["month"], "%B").month,
                day=entry["day"]
            ).date()
            captions[dt] = entry.get("caption", "")
            if start_date and dt == start_date:
                captions[dt] = '(START) ' + captions[dt]
            if end_date and dt == end_date:
                captions[dt] = '(END) ' + captions[dt]
        except Exception:
            continue

    # Filter out images marked "obscured by clouds"
    filtered_files = []
    for image_path in image_files:
        date_obj = parse_date_from_filename(image_path.name)
        caption = captions.get(date_obj, "") if date_obj else ""
        if isinstance(caption, str) and caption.strip().lower() == "obscured by clouds":
            continue  # skip cloud images
        filtered_files.append(image_path)
    image_files = filtered_files

    with st.expander("Timeline Viewer", expanded=True):
        count = len(image_files)

        # Exactly one image: render without a slider (avoids min==max error)
        if count == 1:
            image_path = image_files[0]
            image = load_image(image_path)
            date_obj = parse_date_from_filename(image_path.name)
            caption = captions.get(date_obj, "No caption available") if date_obj else image_path.name
            st.image(image, use_container_width=True)
            st.markdown(
                f"<div style='font-size:1.1rem;'><b>{date_obj}:</b> {caption}</div>",
                unsafe_allow_html=True
            )
            return

        # Multiple images: normal slider
        index = st.slider("Select Image", 0, count - 1, 0, key=source)
        image_path = image_files[index]
        image = load_image(image_path)
        date_obj = parse_date_from_filename(image_path.name)
        caption = captions.get(date_obj, "No caption available") if date_obj else image_path.name
        st.image(image, use_container_width=True)
        st.markdown(
            f"<div style='font-size:1.1rem;'><b>{date_obj}:</b> {caption}</div>",
            unsafe_allow_html=True
        )

@st.cache_data
def get_valid_articles():
    metadata_files = list(VAL_DIR.glob(f"*/metadata.json"))
    valid = []
    for path in metadata_files:
        with open(path) as f:
            data = json.load(f)
        if data['event_type'] != 'no change':
            article_id = path.parent.name
            valid.append((article_id, data))
    return valid

@st.cache_data
def get_article_text(article_id: str):
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"{GCS_PREFIX}/{article_id}.md")
        return blob.download_as_text()
    except Exception as e:
        print(f"[WARN] Could not fetch article text for {article_id}: {e}")
        return None

def write_feedback(article_id, feedback, note=None):
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    columns = ["article_id", "visible", "new_start_date", "new_end_date", "notes"]

    if FEEDBACK_FILE.exists():
        df = pd.read_csv(FEEDBACK_FILE, dtype="object")
    else:
        df = pd.DataFrame(columns=columns)

    if article_id not in df["article_id"].values:
        new_row = pd.DataFrame([[article_id] + [None]*(len(columns)-1)], columns=columns)
        df = pd.concat([df, new_row], ignore_index=True)

    if feedback is not None:
        df.loc[df["article_id"] == article_id, "visible"] = feedback

    if note is not None:
        df.loc[df["article_id"] == article_id, "notes"] = note

    df.to_csv(FEEDBACK_FILE, index=False)
    #clear_cache()

def undo_feedback(article_id):
    if FEEDBACK_FILE.exists():
        df = pd.read_csv(FEEDBACK_FILE, dtype="object")
        if article_id in df["article_id"].values:
            df.loc[df["article_id"] == article_id, "visible"] = pd.NA
            df.to_csv(FEEDBACK_FILE, index=False)
    #clear_cache()


### UI start
st.title("Sky Scraper Validation")

articles = get_valid_articles()
articles = sorted(articles, key=lambda x: x[0])
if not articles:
    st.warning("No articles with metadata.json found.")
    st.stop()

def load_feedback_df():
    if FEEDBACK_FILE.exists():
        return pd.read_csv(FEEDBACK_FILE, dtype="object")
    else:
        return pd.DataFrame(columns=["article_id", "visible", "new_start_date", "new_end_date", "notes",])

feedback_df = load_feedback_df()

st.markdown("### Instructions")
st.markdown('1. Review the article and initial extracted captions and timeline.')
st.markdown('2. Verify that the selected location corresponds with the article location.')
st.markdown('3. Look for the described event in the satellite imagery. Use the article, initial caption/timeline/visual assessment, and rewritten caption for context and assistance.')
st.markdown('4. **Is the event visible?** If the change event is confidently visible, select `Yes`, otherwise select `No`.')
st.markdown('5. **Start/End Dates:** If the event is visible, correct the start/end dates if needed. The start date should be the date of the FIRST satellite image that shows visible evidence of the event. The end date should be the date of the LAST satellite image that the event is STILL visible.')
st.markdown('6. **Notes (Optional):** Record any important notes.')

st.markdown("---")

fully_validated = feedback_df.dropna(subset="visible")
st.markdown(
    f"**Validation Progress:** {len(fully_validated['article_id'].unique())} of {len(articles)} articles fully reviewed"
)

### Jump control (1-based UI, 0-based internal index)
label_col, input_col, button_col, _ = st.columns([1.7, 1, 1, 6])
if "article_index" not in st.session_state:
    st.session_state.article_index = 0

with label_col:
    st.markdown("**Jump to article:**")

with input_col:
    jump_index_ui = st.number_input(
        label="Jump to article index",
        min_value=1,
        max_value=len(articles),
        value=st.session_state.article_index + 1,  # convert to UI index
        step=1,
        label_visibility="collapsed",
        key="jump_input",
    )

with button_col:
    if st.button("Go", key="jump_button"):
        # Convert back to 0-based index
        st.session_state.article_index = jump_index_ui - 1
        st.rerun()

st.markdown("---")

article_id, metadata = articles[st.session_state.article_index]
current_idx = st.session_state.article_index + 1
st.markdown(f"### Article ID: `{article_id}` ({current_idx}/{len(articles)})")

article_text = metadata.get("article_content", "")
if article_text:
    with st.expander("View Article Text", expanded=False):
        styled_text = f"""
        <div style="font-size: 1rem; line-height: 1.6; font-family: sans-serif;">
            {article_text.replace('\n', '<br>')}
        </div>
        """
        st.markdown(styled_text, unsafe_allow_html=True)

# Prepare rewrite metadata for both sources to collect location/coordinates (prefer planet, then sentinel)
meta_path = VAL_DIR / article_id / "metadata.json"
with open(meta_path) as f:
    metadata = json.load(f)

#et, ec, ivs, ivr, conf, loc, coords = read_rewrite_event_fields(meta_path)

et = metadata.get("event_type", "")
ec = metadata.get("event_caption", "")
ivs = metadata.get("initial_success")
ivr = metadata.get("initial_visual_reason")
conf = metadata.get("initial_confidence")
location_name = metadata.get("location_name", "")
coordinates = metadata.get("coordinates", "")
orig_event_caption = metadata.get("initial_caption")
orig_timeline = metadata.get("initial_timeline")
sat_timeline = metadata.get("sat_timeline")
sat_source = metadata.get("source")

# Global "View original captions" dropdown
with st.expander("View Original Captions", expanded=True):
    if orig_event_caption:
        st.markdown("##### Event Caption")
        st.markdown(orig_event_caption)

    st.markdown("##### Timeline")
    if isinstance(orig_timeline, dict) and orig_timeline:
        for date, desc in orig_timeline.items():
            st.markdown(f"**{date}**: {desc}")
    elif isinstance(orig_timeline, list) and orig_timeline:
        for entry in orig_timeline:
            try:
                dt = datetime(
                    year=entry["year"],
                    month=datetime.strptime(entry["month"], "%B").month,
                    day=entry["day"]
                ).date()
                st.markdown(f"**{dt.isoformat()}**: {entry.get('caption', '')}")
            except Exception:
                continue
    else:
        st.markdown("_No timeline available_")

lat, lon = coordinates.split("_", 1)
st.markdown(f"#### Selected Location:")
st.markdown(f"{location_name} ({lat}, {lon})")
maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
st.markdown(f"[📍 ({lat}, {lon}) (Image Center)]({maps_link})")
encoded_query = urllib.parse.quote(location_name)
maps_link = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
st.markdown(f"[📍 {location_name} (Reference)]({maps_link})")


### Imagery section
st.subheader(f"{sat_source.capitalize()} Imagery")

# 1) Imagery gallery (with per-image timeline captions from this source rewrite metadata)
try:
    _start_date = metadata['start_date']
    start_date = datetime(
                    year=_start_date["year"],
                    month=datetime.strptime(_start_date["month"], "%B").month,
                    day=_start_date["day"]
                    ).date()
    _end_date = metadata['end_date']
    end_date = datetime(
                    year=_end_date["year"],
                    month=datetime.strptime(_end_date["month"], "%B").month,
                    day=_end_date["day"]
                    ).date()
except:
    start_date = 'N/A'
    end_date = 'N/A'

image_dir = VAL_DIR / article_id / "imagery"
render_image_gallery_with_captions(image_dir, sat_timeline, sat_source, None if start_date == 'N/A' else start_date, None if end_date == 'N/A' else end_date)

# 2) Initial Visual Assessment (from this source's rewrite metadata)
with st.expander(f"Initial Visual Assessment", expanded=False):
    if ivs:
        st.markdown(f"**Visual Success:** `{ivs}`")
    if ivr:
        st.markdown(f"**Visual Reason:** {ivr}")
    if conf:
        st.markdown(f"**Confidence:** {conf}")

# 3) Rewritten
with st.expander(f"Rewritten", expanded=True):
    st.markdown(f"**Event Type:** {et}")
    st.markdown(f"**Event Caption:** {ec}")


# Load any existing values
existing_visible = feedback_df.loc[feedback_df["article_id"] == article_id, "visible"].values[0] if article_id in feedback_df["article_id"].values else None
existing_note = feedback_df.loc[feedback_df["article_id"] == article_id, "notes"].values[0] if article_id in feedback_df["article_id"].values else ""
existing_note = "" if pd.isna(existing_note) else existing_note
existing_start = feedback_df.loc[feedback_df["article_id"] == article_id, "new_start_date"].values[0] if article_id in feedback_df["article_id"].values else None
existing_end = feedback_df.loc[feedback_df["article_id"] == article_id, "new_end_date"].values[0] if article_id in feedback_df["article_id"].values else None


st.markdown("#### Is the event visible?")
st.markdown("`Yes` if the change event is confidently visible.")
st.markdown("`Unsure` if you cannot make a choice with >50% confidence.")
st.markdown("`No` if change event is not confidently visible.")


# 5 columns: spacer | Yes | Unsure | No | spacer
spacer1, col_yes, col_unsure, col_no, spacer2 = st.columns([1, 3, 3, 3, 1])

# ✅ YES
with col_yes:
    if existing_visible == "Yes":
        st.markdown(
            '<div style="background-color:#2e7d32;padding:0.5em 1em;border-radius:6px;text-align:center;color:white;width:100%;"><b>✅ Selected Yes</b></div>',
            unsafe_allow_html=True
        )
    else:
        if st.button("✅ Yes", key="yes", use_container_width=True):
            write_feedback(article_id, "Yes", existing_note)
            st.session_state["visibility_saved"] = "Yes"
            st.rerun()

# 🤔 UNSURE
with col_unsure:
    if existing_visible == "Unsure":
        st.markdown(
            '<div style="background-color:#f9a825;padding:0.5em 1em;border-radius:6px;text-align:center;color:black;width:100%;"><b>🤔 Selected Unsure</b></div>',
            unsafe_allow_html=True
        )
    else:
        if st.button("🤔 Unsure", key="unsure", use_container_width=True):
            write_feedback(article_id, "Unsure", existing_note)
            st.session_state["visibility_saved"] = "Unsure"
            st.rerun()

# ❌ NO
with col_no:
    if existing_visible == "No":
        st.markdown(
            '<div style="background-color:#c62828;padding:0.5em 1em;border-radius:6px;text-align:center;color:white;width:100%;"><b>❌ Selected No</b></div>',
            unsafe_allow_html=True
        )
    else:
        if st.button("❌ No", key="no", use_container_width=True):
            write_feedback(article_id, "No", existing_note)
            st.session_state["visibility_saved"] = "No"
            st.rerun()

# ↩️ UNDO row below all three
_, col_undo, _ = st.columns([4, 2, 4])
with col_undo:
    if existing_visible in ("Yes", "No", "Unsure"):
        if st.button("↩️ Undo", key="undo", use_container_width=True):
            undo_feedback(article_id)
            st.session_state["visibility_saved"] = None
            st.rerun()


### Start/end dates
st.markdown("#### Correct event start/end dates (if applicable)")
with st.expander("Correct Event Dates", expanded=True):

    start_key = f"start_date_{article_id}"
    end_key   = f"end_date_{article_id}"

    # Clear widget state ONLY when article changes
    last_article = st.session_state.get("dates_article_id")
    if last_article != article_id:
        st.session_state.pop(start_key, None)
        st.session_state.pop(end_key, None)
        st.session_state["dates_article_id"] = article_id

    # Load saved CSV values
    saved_start = None
    saved_end = None

    if article_id in feedback_df["article_id"].values:
        row = feedback_df.loc[feedback_df["article_id"] == article_id].iloc[0]

        if isinstance(row["new_start_date"], str) and row["new_start_date"].strip():
            saved_start = datetime.fromisoformat(row["new_start_date"]).date()

        if isinstance(row["new_end_date"], str) and row["new_end_date"].strip():
            saved_end = datetime.fromisoformat(row["new_end_date"]).date()

    # FORCE CLEAR FLAGS
    if st.session_state.pop(f"force_clear_start_{article_id}", False):
        saved_start = None
        st.session_state.pop(start_key, None)

    if st.session_state.pop(f"force_clear_end_{article_id}", False):
        saved_end = None
        st.session_state.pop(end_key, None)

    # START DATE
    st.markdown(f"**Predicted Start Date:** {start_date}")
    col_s1, col_s2 = st.columns([4, 1])

    with col_s1:
        new_start = st.date_input(
            " ",
            value=saved_start,
            key=start_key,
            label_visibility="collapsed",
        )

    with col_s2:
        if st.button("↩️ Clear", key=f"clear_start_{article_id}", use_container_width=True):

            df = pd.read_csv(FEEDBACK_FILE, dtype=str) if FEEDBACK_FILE.exists() else \
                 pd.DataFrame(columns=["article_id","visible","new_start_date","new_end_date","notes"])

            if article_id not in df["article_id"].values:
                df.loc[len(df)] = [article_id, None, "", "", ""]

            df.loc[df["article_id"] == article_id, "new_start_date"] = ""
            df.to_csv(FEEDBACK_FILE, index=False)

            st.session_state[f"force_clear_start_{article_id}"] = True
            st.session_state["date_message"] = {
                "type": "success",
                "text": "Cleared corrected start date."
            }
            st.rerun()

    # END DATE
    st.markdown(f"**Predicted End Date:** {end_date}")
    col_e1, col_e2 = st.columns([4, 1])

    with col_e1:
        new_end = st.date_input(
            " ",
            value=saved_end,
            key=end_key,
            label_visibility="collapsed",
        )

    with col_e2:
        if st.button("↩️ Clear", key=f"clear_end_{article_id}", use_container_width=True):

            df = pd.read_csv(FEEDBACK_FILE, dtype=str) if FEEDBACK_FILE.exists() else \
                 pd.DataFrame(columns=["article_id","visible","new_start_date","new_end_date","notes"])

            if article_id not in df["article_id"].values:
                df.loc[len(df)] = [article_id, None, "", "", ""]

            df.loc[df["article_id"] == article_id, "new_end_date"] = ""
            df.to_csv(FEEDBACK_FILE, index=False)

            st.session_state[f"force_clear_end_{article_id}"] = True
            st.session_state["date_message"] = {
                "type": "success",
                "text": "Cleared corrected end date."
            }
            st.rerun()

    # SAVE DATES
    if st.button("💾 Save Corrected Dates", key=f"save_dates_{article_id}", use_container_width=True):

        visible_val = None
        if article_id in feedback_df["article_id"].values:
            visible_val = feedback_df.loc[
                feedback_df["article_id"] == article_id, "visible"
            ].values[0]

        if visible_val not in ("Yes", "No", "Unsure"):
            st.session_state["date_message"] = {
                "type": "error",
                "text": "ERROR: Please select whether the event is visible before saving dates."
            }
            st.rerun()

        df = pd.read_csv(FEEDBACK_FILE, dtype=str) if FEEDBACK_FILE.exists() else \
             pd.DataFrame(columns=["article_id","visible","new_start_date","new_end_date","notes"])

        if article_id not in df["article_id"].values:
            df.loc[len(df)] = [article_id, visible_val, "", "", ""]

        df.loc[df["article_id"] == article_id, "new_start_date"] = (
            new_start.isoformat() if new_start else ""
        )
        df.loc[df["article_id"] == article_id, "new_end_date"] = (
            new_end.isoformat() if new_end else ""
        )

        df.to_csv(FEEDBACK_FILE, index=False)

        st.session_state["date_message"] = {
            "type": "success",
            "text": "Saved corrected dates."
        }
        st.rerun()

msg = st.session_state.get("date_message")
if msg:
    if msg["type"] == "error":
        st.error(msg["text"])
    else:
        st.success(msg["text"])

    st.session_state["date_message"] = None


### Notes
note_key = f"feedback_note_{article_id}"

# Clear stale notes when switching articles
last_note_article = st.session_state.get("note_article_id")
if last_note_article != article_id:
    st.session_state.pop(note_key, None)
    st.session_state["note_article_id"] = article_id

# Load note from CSV ONLY if it exists
existing_note = ""
if article_id in feedback_df["article_id"].values:
    saved_note = feedback_df.loc[
        feedback_df["article_id"] == article_id, "notes"
    ].values[0]

    if isinstance(saved_note, str) and saved_note.strip():
        existing_note = saved_note

# Notes text area (empty unless CSV has content)
note = st.text_area(
    "💬 Feedback Notes (Optional)",
    value=existing_note,
    key=note_key,
    height=100
)

# Save notes
if st.button("💾 Submit Notes", key=f"submit_note_{article_id}"):

    write_feedback(article_id, existing_visible, note)

    st.session_state["date_message"] = {
        "type": "success",
        "text": "Submitted notes."
    }
    st.rerun()


### Navigation
st.markdown("---")
spacer1, col_prev, col_next, spacer2 = st.columns([1, 3, 3, 1])

with col_prev:
    if st.button("⬅️ Previous Article", use_container_width=True):
        st.session_state.article_index = (st.session_state.article_index - 1) % len(articles)
        st.rerun()

with col_next:
    if st.button("Next Article ➡️", use_container_width=True):
        st.session_state.article_index = (st.session_state.article_index + 1) % len(articles)
        st.rerun()