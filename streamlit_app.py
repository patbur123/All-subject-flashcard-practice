import streamlit as st
import json
import os
import io
import base64
import time
from random import choice, random

# Configuration
DRIVE_FILE_NAME = "flashcards_data.json"
LOCAL_FILE = "flashcards_data.json"

DICTIONARIES = {
    "level_1": {"name": "Learning", "draw_chance": 0.5},
    "level_2": {"name": "Familiar", "draw_chance": 0.3},
    "level_3": {"name": "Confident", "draw_chance": 0.15},
    "level_4": {"name": "Mastered", "draw_chance": 0.05}
}

DEFAULT_FOLDER = "All Cards"

# Helper utilities for folder handling (exclude internal _meta and support nested folders)
def folder_keys():
    """Return folder names excluding internal _meta."""
    if not isinstance(st.session_state.get("flashcards", {}), dict):
        return [DEFAULT_FOLDER]
    return [k for k in st.session_state.flashcards.keys() if k != "_meta"]


def format_folder_label(name: str) -> str:
    """Pretty-print a folder name showing nesting using `/` as separator.
    The underlying option value remains the full path (e.g. "Parent/Child").
    """
    depth = name.count("/")
    return ("    " * depth) + (name.split("/")[-1] or name)


# Google Drive Functions (Simplified - No external API calls on every load)
def has_google_credentials():
    """Check if Google credentials are available either in session or in secrets."""
    try:
        return st.session_state.get("google_creds") is not None or st.secrets.get("google_credentials") is not None
    except:
        return False

def load_flashcards():
    """Load flashcards from local file only (much faster)."""
    # Fallback to local file
    if os.path.exists(LOCAL_FILE):
        try:
            with open(LOCAL_FILE, "r") as f:
                data = json.load(f)
                # If file contains our metadata wrapper
                if isinstance(data, dict) and "_meta" in data:
                    meta = data.get("_meta", {})
                    folders = {k: v for k, v in data.items() if k != "_meta"}
                    # attach meta to returned structure so initialization can pick it up
                    folders.setdefault("_meta", meta)
                    return folders

                # Handle migration from old format to new format with folders
                if isinstance(data, dict) and "level_1" in data and not isinstance(data.get("level_1"), dict):
                    migrated_data = {DEFAULT_FOLDER: {level: cards for level, cards in data.items()}}
                    return migrated_data

                return data
        except:
            pass
    
    return {DEFAULT_FOLDER: {level: [] for level in DICTIONARIES.keys()}}

def save_flashcards():
    """Save flashcards to local file (primary) and optionally to Google Drive."""
    # Always save locally first (fast and reliable)
    # Compose a file payload that can include meta settings
    to_save = {k: v for k, v in st.session_state.flashcards.items() if k != "_meta"}
    # include meta (draw chances and folder weights) if present
    meta = st.session_state.get("_meta", {})
    if meta:
        to_save["_meta"] = meta

    with open(LOCAL_FILE, "w") as f:
        json.dump(to_save, f, indent=2)
    
    # Try to save to Google Drive if credentials exist (optional, don't block if it fails)
    if has_google_credentials():
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseUpload

            # Prefer session credentials (from an interactive auth during this run).
            creds_obj = st.session_state.get("google_creds")

            if not creds_obj:
                creds_entry = st.secrets.get("google_credentials")
                creds_dict = None
                if creds_entry:
                    # secrets may store JSON string or a dict
                    if isinstance(creds_entry, str):
                        try:
                            creds_dict = json.loads(creds_entry)
                        except Exception:
                            creds_dict = None
                    elif isinstance(creds_entry, dict):
                        creds_dict = creds_entry
                if creds_dict:
                    creds_obj = Credentials.from_authorized_user_info(creds_dict, ['https://www.googleapis.com/auth/drive'])

            if not creds_obj:
                raise ValueError("No valid Google credentials available (add authorized credentials to Streamlit secrets or authorize for this session)")

            service = build('drive', 'v3', credentials=creds_obj)

            # Find file ID
            query = f"name='{DRIVE_FILE_NAME}' and trashed=false"
            results = service.files().list(q=query, spaces='drive', fields='files(id, name)', pageSize=1).execute()
            files = results.get('files', [])
            file_id = files[0]['id'] if files else None

            file_content = json.dumps({k: v for k, v in st.session_state.flashcards.items()}, indent=2)
            media = MediaIoBaseUpload(io.BytesIO(file_content.encode()), mimetype='application/json')

            if file_id:
                # Update existing file
                service.files().update(fileId=file_id, media_body=media).execute()
            else:
                # Create new file
                file_metadata = {'name': DRIVE_FILE_NAME}
                service.files().create(body=file_metadata, media_body=media).execute()
        except Exception as e:
            # Report failure but do not block local save
            try:
                st.warning(f"Google Drive sync failed: {e}")
            except Exception:
                pass

# Define functions first
def add_new_flashcard(question, answer, question_image=None, answer_image=None, folder=DEFAULT_FOLDER):
    """Add a new flashcard to level_1 (highest chance of being drawn)."""
    if question.strip() and answer.strip():
        # Ensure folder exists
        if folder not in st.session_state.flashcards:
            st.session_state.flashcards[folder] = {level: [] for level in DICTIONARIES.keys()}
        
        new_card = {
            "question": question.strip(),
            "answer": answer.strip(),
            "question_image": question_image,
            "answer_image": answer_image
        }
        st.session_state.flashcards[folder]["level_1"].append(new_card)
        save_flashcards()
        return True
    return False

def delete_flashcard(folder, level, index):
    """Delete a flashcard from a specific level in a specific folder."""
    if folder in st.session_state.flashcards:
        if 0 <= index < len(st.session_state.flashcards[folder][level]):
            st.session_state.flashcards[folder][level].pop(index)
            save_flashcards()
            return True
    return False

def edit_flashcard(folder, level, index, new_question, new_answer, question_image=None, answer_image=None):
    """Edit an existing flashcard's question, answer, and optional images."""
    if folder in st.session_state.flashcards:
        if 0 <= index < len(st.session_state.flashcards[folder][level]):
            card = st.session_state.flashcards[folder][level][index]
            card["question"] = new_question.strip()
            card["answer"] = new_answer.strip()

            # Only replace images if provided (None means keep existing)
            if question_image is not None:
                card["question_image"] = question_image
            if answer_image is not None:
                card["answer_image"] = answer_image

            save_flashcards()
            return True
    return False

def move_card_to_folder(from_folder, level, index, to_folder):
    """Move a card from one folder to another."""
    if from_folder in st.session_state.flashcards and to_folder in st.session_state.flashcards:
        if 0 <= index < len(st.session_state.flashcards[from_folder][level]):
            card = st.session_state.flashcards[from_folder][level].pop(index)
            st.session_state.flashcards[to_folder][level].append(card)
            save_flashcards()
            return True
    return False

def reset_all_cards(folder=None):
    """Reset all cards back to Learning level."""
    if folder:
        # Reset only cards in a specific folder
        if folder in st.session_state.flashcards:
            all_cards = []
            for level in st.session_state.flashcards[folder].values():
                all_cards.extend(level)
            st.session_state.flashcards[folder] = {level: [] for level in DICTIONARIES.keys()}
            st.session_state.flashcards[folder]["level_1"] = all_cards
    else:
        # Reset all cards across all folders (skip internal keys)
        for folder_name in folder_keys():
            all_cards = []
            for level in st.session_state.flashcards[folder_name].values():
                all_cards.extend(level)
            st.session_state.flashcards[folder_name] = {level: [] for level in DICTIONARIES.keys()}
            st.session_state.flashcards[folder_name]["level_1"] = all_cards
    
    save_flashcards()

def delete_all_cards(folder=None):
    """Permanently delete all flashcards."""
    if folder:
        # Delete only cards in a specific folder
        if folder in st.session_state.flashcards:
            st.session_state.flashcards[folder] = {level: [] for level in DICTIONARIES.keys()}
    else:
        # Delete all cards across all folders (skip internal keys)
        for folder_name in folder_keys():
            st.session_state.flashcards[folder_name] = {level: [] for level in DICTIONARIES.keys()}
    
    save_flashcards()

def create_folder(folder_name):
    """Create a new folder for organizing flashcards. Supports nested folders using `/`.

    When creating a nested folder like "Parent/Child" the parent folder
    ("Parent") will also be created if it doesn't already exist so it appears in the UI.
    """
    name = folder_name.strip()
    if not name:
        return False

    # create parent chain for nested folders (e.g. 'A/B/C')
    parts = name.split("/")
    for i in range(1, len(parts)):
        parent = "/".join(parts[:i])
        if parent and parent not in st.session_state.flashcards:
            st.session_state.flashcards[parent] = {level: [] for level in DICTIONARIES.keys()}

    if name not in st.session_state.flashcards:
        st.session_state.flashcards[name] = {level: [] for level in DICTIONARIES.keys()}
        save_flashcards()
        return True
    return False

def delete_folder(folder_name):
    """Delete a folder and all its flashcards."""
    if folder_name in st.session_state.flashcards and folder_name != DEFAULT_FOLDER:
        del st.session_state.flashcards[folder_name]
        save_flashcards()
        return True
    return False

def encode_image(uploaded_file):
    """Encode an uploaded image to base64."""
    if uploaded_file is not None:
        return base64.b64encode(uploaded_file.read()).decode()
    return None

def decode_image(image_data):
    """Decode base64 image data."""
    if image_data:
        return base64.b64decode(image_data)
    return None

def get_next_question():
    """Select next question based on draw chances from each level."""
    # Get folders to study from
    study_folders = st.session_state.get("study_folders", folder_keys())
    
    # Initialize recently shown list to avoid repeating the same few cards
    if "recently_shown" not in st.session_state:
        st.session_state.recently_shown = []
    if "recent_max" not in st.session_state:
        st.session_state.recent_max = 50

    # Load draw chances from meta if present, otherwise fall back
    meta = st.session_state.get("_meta", {})
    draw_chances = meta.get("draw_chances", {lvl: DICTIONARIES[lvl]["draw_chance"] for lvl in DICTIONARIES.keys()})
    folder_weights = meta.get("folder_weights", {f: 1.0 for f in study_folders})

    # Build a data structure of available cards per folder->level
    available = {}
    for folder in study_folders:
        if folder in st.session_state.flashcards:
            available[folder] = {level: list(cards) for level, cards in st.session_state.flashcards[folder].items()}

    if not available:
        return None

    # Try a limited number of attempts: pick a folder by weight, then pick a level by draw chance
    # If chosen bucket is empty, try again; fallback to any card.
    folders_list = list(available.keys())
    weights = [folder_weights.get(f, 1.0) for f in folders_list]

    def weighted_choice(items, weights_list):
        total = sum(weights_list)
        if total <= 0:
            return choice(items)
        r = random() * total
        upto = 0
        for it, w in zip(items, weights_list):
            upto += w
            if r <= upto:
                return it
        return items[-1]

    attempts = 0
    while attempts < 10:
        attempts += 1
        folder = weighted_choice(folders_list, weights)

        # choose level by drawing against draw_chances
        r = random()
        cumulative = 0
        chosen_level = None
        for lvl in ["level_1", "level_2", "level_3", "level_4"]:
            cumulative += draw_chances.get(lvl, DICTIONARIES[lvl]["draw_chance"])
            if r <= cumulative:
                chosen_level = lvl
                break

        if chosen_level is None:
            chosen_level = "level_4"

        cards = available.get(folder, {}).get(chosen_level, [])
        if cards:
            # pick a card avoiding recently shown first
            candidates = []
            for idx, card in enumerate(cards):
                key = f"{folder}||{chosen_level}||{card.get('question','')}||{card.get('answer','')}"
                candidates.append((idx, card, key))
            non_recent = [c for c in candidates if c[2] not in st.session_state.recently_shown]
            pick_list = non_recent if non_recent else candidates
            idx, selected, key = choice(pick_list)
            st.session_state.recently_shown.append(key)
            if len(st.session_state.recently_shown) > st.session_state.recent_max:
                st.session_state.recently_shown = st.session_state.recently_shown[-st.session_state.recent_max:]
            return (folder, chosen_level, selected, idx)

    # Fallback: pick any available card across study_folders
    all_candidates = []
    for folder, levels in available.items():
        for lvl, cards in levels.items():
            for idx, card in enumerate(cards):
                key = f"{folder}||{lvl}||{card.get('question','')}||{card.get('answer','')}"
                all_candidates.append((folder, lvl, idx, card, key))

    if not all_candidates:
        return None

    non_recent = [c for c in all_candidates if c[4] not in st.session_state.recently_shown]
    pick = choice(non_recent if non_recent else all_candidates)
    folder, lvl, idx, card, key = pick
    st.session_state.recently_shown.append(key)
    if len(st.session_state.recently_shown) > st.session_state.recent_max:
        st.session_state.recently_shown = st.session_state.recently_shown[-st.session_state.recent_max:]
    return (folder, lvl, card, idx)

def move_card_up(folder, current_level, card_index):
    """Move card to next level (reduce draw chance)."""
    level_order = ["level_1", "level_2", "level_3", "level_4"]
    current_idx = level_order.index(current_level)
    
    if current_idx < len(level_order) - 1:
        next_level = level_order[current_idx + 1]
        card = st.session_state.flashcards[folder][current_level].pop(card_index)
        st.session_state.flashcards[folder][next_level].append(card)
        save_flashcards()
        return True
    return False

def move_card_down(folder, current_level, card_index):
    """Move card back to Learning level (when answered incorrectly)."""
    if current_level != "level_1":
        card = st.session_state.flashcards[folder][current_level].pop(card_index)
        st.session_state.flashcards[folder]["level_1"].append(card)
        save_flashcards()
        return True
    return False

def move_card_between_folders(src_folder, level, index, target_folder):
    """Move a card from one folder to another, keeping its current level."""
    if src_folder not in st.session_state.flashcards:
        return False
    if target_folder not in st.session_state.flashcards:
        # Create target folder if it doesn't exist
        st.session_state.flashcards[target_folder] = {lvl: [] for lvl in DICTIONARIES.keys()}
    if 0 <= index < len(st.session_state.flashcards[src_folder][level]):
        card = st.session_state.flashcards[src_folder][level].pop(index)
        st.session_state.flashcards[target_folder][level].append(card)
        save_flashcards()
        return True
    return False

def rename_folder(old_name, new_name):
    """Rename a folder while preserving its cards."""
    if not new_name.strip() or old_name not in st.session_state.flashcards:
        return False
    if new_name in st.session_state.flashcards:
        return False
    st.session_state.flashcards[new_name] = st.session_state.flashcards.pop(old_name)
    # Update study_folders if necessary
    if old_name in st.session_state.get("study_folders", []):
        sf = st.session_state.study_folders
        st.session_state.study_folders = [new_name if f == old_name else f for f in sf]
    save_flashcards()
    return True

def get_stats(folders=None):
    """Return statistics about flashcard progress. Skips internal keys like "_meta"."""
    if folders is None:
        folders = folder_keys()

    # normalize folder list to existing folders only
    folders = [f for f in folders if f in st.session_state.flashcards and f != "_meta"]

    stats = {}
    total = 0
    for level in DICTIONARIES.keys():
        count = 0
        for folder in folders:
            # defensive: skip folders that don't have expected level structure
            lvl_bucket = st.session_state.flashcards.get(folder, {}).get(level, [])
            count += len(lvl_bucket)
        stats[level] = count
        total += count
    stats["total"] = total
    return stats

# Initialize session state
if "flashcards" not in st.session_state:
    st.session_state.flashcards = load_flashcards()
    # Ensure default folder exists
    if DEFAULT_FOLDER not in st.session_state.flashcards:
        st.session_state.flashcards[DEFAULT_FOLDER] = {level: [] for level in DICTIONARIES.keys()}
if "current_question" not in st.session_state:
    st.session_state.current_question = None
if "show_answer" not in st.session_state:
    st.session_state.show_answer = False
if "study_folders" not in st.session_state:
    # default to all real folders (exclude internal keys)
    st.session_state.study_folders = folder_keys() or [DEFAULT_FOLDER]
if "form_submit_count" not in st.session_state:
    st.session_state.form_submit_count = 0
# Initialize meta settings (draw chances & folder weights)
if "_meta" not in st.session_state:
    file_meta = st.session_state.flashcards.get("_meta", {}) if isinstance(st.session_state.flashcards, dict) else {}
    # default draw chances from DICTIONARIES
    default_draw = {lvl: DICTIONARIES[lvl]["draw_chance"] for lvl in DICTIONARIES.keys()}
    draw_chances = file_meta.get("draw_chances", default_draw)
    # default folder weights: 1.0 for each existing folder (exclude internal keys)
    folder_weights = file_meta.get("folder_weights", {f: 1.0 for f in (st.session_state.flashcards.keys() if isinstance(st.session_state.flashcards, dict) else []) if f != "_meta"})
    st.session_state["_meta"] = {"draw_chances": draw_chances, "folder_weights": folder_weights}

    # make sure the in-memory flashcards structure does NOT carry an internal "_meta" key
    if isinstance(st.session_state.flashcards, dict) and "_meta" in st.session_state.flashcards:
        st.session_state.flashcards.pop("_meta", None)

# UI
st.set_page_config(page_title="Flashcard Practice", layout="wide")
st.title("🎯 Spaced Repetition Flashcard App")

# Sidebar with stats
with st.sidebar:
    st.subheader("📊 Progress")
    stats = get_stats()
    st.metric("Total Cards", stats["total"])
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Learning", stats["level_1"])
        st.metric("Confident", stats["level_3"])
    with col2:
        st.metric("Familiar", stats["level_2"])
        st.metric("Mastered", stats["level_4"])
    st.divider()
    if st.button("🔁 Reload data from file", use_container_width=True):
        # Re-load flashcards from the local JSON file into session state
        st.session_state.flashcards = load_flashcards()
        # Ensure study_folders stays in sync with available folders
        st.session_state.study_folders = folder_keys() or [DEFAULT_FOLDER]
        st.success("Reloaded flashcards from flashcards_data.json")
        st.rerun()

# Main content tabs
tab1, tab2, tab3, tab4 = st.tabs(["Add Questions", "Practice", "Manage Questions", "Setup"])

# TAB 1: Add new questions
with tab1:
    st.subheader("➕ Add New Questions")
    
    # Initialize session state for images
    if "temp_q_image" not in st.session_state:
        st.session_state.temp_q_image = None
    if "temp_a_image" not in st.session_state:
        st.session_state.temp_a_image = None
    
    # Select folder
    selected_folder = st.selectbox("Select Folder:", options=folder_keys(), format_func=format_folder_label, key="add_folder_select")
    
    # Text inputs - use form_submit_count to trigger clearing
    question_input = st.text_input("Question", placeholder="Enter your question", key=f"question_input_{st.session_state.form_submit_count}")
    answer_input = st.text_area("Answer", placeholder="Enter the answer", height=100, key=f"answer_input_{st.session_state.form_submit_count}")
    submitted = st.button("Add Question", use_container_width=True, key=f"add_question_btn_{st.session_state.form_submit_count}")
    
    # Image uploaders OUTSIDE form (better compatibility)
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.temp_q_image = st.file_uploader("Question Image (optional)", type=['png', 'jpg', 'jpeg'], key=f"q_img_{st.session_state.form_submit_count}")
    with col2:
        st.session_state.temp_a_image = st.file_uploader("Answer Image (optional)", type=['png', 'jpg', 'jpeg'], key=f"a_img_{st.session_state.form_submit_count}")
    
    # Handle form submission
    if submitted:
        if question_input.strip() and answer_input.strip():
            q_img_data = encode_image(st.session_state.temp_q_image)
            a_img_data = encode_image(st.session_state.temp_a_image)
            
            if add_new_flashcard(question_input, answer_input, q_img_data, a_img_data, selected_folder):
                st.success("✅ Question added to Learning level!")
                st.session_state.form_submit_count += 1
                st.session_state.temp_q_image = None
                st.session_state.temp_a_image = None
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ Error adding question")
        else:
            st.error("❌ Please enter both question and answer")

    # Math helper snippets: allow quick insertion of LaTeX/math into current inputs
    q_key = f"question_input_{st.session_state.form_submit_count}"
    a_key = f"answer_input_{st.session_state.form_submit_count}"
    snippets = ["$x$", "$\\frac{a}{b}$", "$\\int_a^b f(x) \,dx$", "$\\sum_{i=1}^n i$", "$$\\frac{d}{dx}\\sin x$$"]
    st.caption("Use LaTeX inline with $...$ or display math with $$...$$. Select a snippet and insert into the active field.")
    col_s1, col_s2, col_s3 = st.columns([3,2,2])
    with col_s1:
        chosen = st.selectbox("Quick math snippets:", options=snippets, key=f"snippet_select_{st.session_state.form_submit_count}")
    with col_s2:
        if st.button("Insert into Question", key=f"insert_q_{st.session_state.form_submit_count}"):
            st.session_state[q_key] = st.session_state.get(q_key, "") + (" " + chosen)
    with col_s3:
        if st.button("Insert into Answer", key=f"insert_a_{st.session_state.form_submit_count}"):
            st.session_state[a_key] = st.session_state.get(a_key, "") + (" " + chosen)

# TAB 2: Practice
with tab2:
    st.subheader("📚 Practice Questions")
    
    # Folder selection for studying
    st.write("**Select folders to study from:**")
    available_folders = folder_keys()
    
    selected_study_folders = st.multiselect(
        "Choose one or more folders:",
        options=available_folders,
        format_func=format_folder_label,
        default=st.session_state.study_folders,
        key="study_folders_select"
    )
    
    if selected_study_folders:
        st.session_state.study_folders = selected_study_folders
    
    st.divider()
    
    stats = get_stats(st.session_state.study_folders)
    if stats["total"] == 0:
        st.info("📝 No questions in selected folders! Add some questions in the 'Add Questions' tab to get started.")
    elif stats["level_4"] == stats["total"]:
        st.success("🎉 Congratulations! You've mastered all questions in selected folders!")
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Reset to Learning", use_container_width=True, type="secondary"):
                if st.session_state.get("confirm_reset"):
                    for folder in st.session_state.study_folders:
                        reset_all_cards(folder)
                    st.session_state.confirm_reset = False
                    st.success("All cards in selected folders moved back to Learning level!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.session_state.confirm_reset = True
                    st.rerun()
        
        with col2:
            if st.button("🗑️ Delete Selected", use_container_width=True, type="secondary"):
                if st.session_state.get("confirm_delete"):
                    for folder in st.session_state.study_folders:
                        delete_all_cards(folder)
                    st.session_state.confirm_delete = False
                    st.success("All cards in selected folders deleted!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.session_state.confirm_delete = True
                    st.rerun()
        
        # Show confirmation messages
        if st.session_state.get("confirm_reset"):
            st.warning("⚠️ Reset all cards in selected folders back to Learning level?")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Confirm Reset", use_container_width=True, key="confirm_reset_btn"):
                    for folder in st.session_state.study_folders:
                        reset_all_cards(folder)
                    st.session_state.confirm_reset = False
                    st.success("All cards moved back to Learning level!")
                    time.sleep(0.5)
                    st.rerun()
            with col_b:
                if st.button("Cancel", use_container_width=True, key="cancel_reset_btn"):
                    st.session_state.confirm_reset = False
                    st.rerun()
        
        if st.session_state.get("confirm_delete"):
            st.error("🚨 This will permanently delete all flashcards in selected folders!")
            col_c, col_d = st.columns(2)
            with col_c:
                if st.button("Yes, Delete All", use_container_width=True, type="primary", key="confirm_delete_btn"):
                    for folder in st.session_state.study_folders:
                        delete_all_cards(folder)
                    st.session_state.confirm_delete = False
                    st.success("All cards deleted!")
                    time.sleep(0.5)
                    st.rerun()
            with col_d:
                if st.button("Cancel", use_container_width=True, key="cancel_delete_btn"):
                    st.session_state.confirm_delete = False
                    st.rerun()
    else:
        # Get question on load
        if st.session_state.current_question is None:
            result = get_next_question()
            if result:
                st.session_state.current_folder, st.session_state.current_level, st.session_state.current_card, st.session_state.card_index = result
                st.session_state.current_question = st.session_state.current_card["question"]
        
        if st.session_state.current_question:
            # Display current folder being studied
            st.caption(f"📁 From: {st.session_state.current_folder}")
            
            # Display question
            st.write("### Question:")
            st.markdown(f"**{st.session_state.current_question}**")
            
            # Display question image if exists
            if st.session_state.current_card.get("question_image"):
                st.image(decode_image(st.session_state.current_card["question_image"]), use_column_width=True)
            
            # Display answer if shown
            if st.session_state.show_answer:
                st.divider()
                st.write("### Answer:")
                st.markdown(f"**{st.session_state.current_card['answer']}**")
                
                # Display answer image if exists
                if st.session_state.current_card.get("answer_image"):
                    st.image(decode_image(st.session_state.current_card["answer_image"]), use_column_width=True)
                
                # Result buttons
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("✅ Correct!", use_container_width=True, type="primary"):
                        current_folder = st.session_state.current_folder
                        current_level = st.session_state.current_level
                        card_index = st.session_state.card_index
                        
                        # Move card up and check if successful
                        if move_card_up(current_folder, current_level, card_index):
                            level_order = ["level_1", "level_2", "level_3", "level_4"]
                            next_idx = level_order.index(current_level) + 1
                            next_level = level_order[next_idx]
                            st.success(f"Moved to '{DICTIONARIES[next_level]['name']}' level!")
                        else:
                            st.success("🎉 Already at highest level - Mastered!")
                        
                        st.session_state.current_question = None
                        st.session_state.show_answer = False
                        time.sleep(0.5)
                        st.rerun()
                
                with col3:
                    if st.button("❌ Incorrect", use_container_width=True):
                        current_folder = st.session_state.current_folder
                        current_level = st.session_state.current_level
                        card_index = st.session_state.card_index
                        
                        # Move card back to Learning level
                        if current_level != "level_1":
                            move_card_down(current_folder, current_level, card_index)
                            st.warning("⬇️ Moved back to Learning level. Keep practicing!")
                        else:
                            st.info("Keep practicing! Same question next time.")
                        
                        st.session_state.current_question = None
                        st.session_state.show_answer = False
                        time.sleep(0.5)
                        st.rerun()
            else:
                # Show answer button
                if st.button("Reveal Answer", use_container_width=True, type="secondary"):
                    st.session_state.show_answer = True
                    st.rerun()
                    st.rerun()

# TAB 3: Manage Questions
with tab3:
    st.subheader("📋 View & Manage All Questions")
    
    # Folder management section
    st.write("**Folder Management:**")
    col1, col2 = st.columns([3, 1])
    
    with col1:
        new_folder_name = st.text_input("Create new folder:", placeholder="Enter folder name", key="new_folder_input")
        # Rename folder helper
        rename_from = st.selectbox("Rename folder:", options=folder_keys(), format_func=format_folder_label, key="rename_from_select")
        rename_to = st.text_input("New name for selected folder:", key="rename_to_input")
    
    with col2:
        if st.button("Create", use_container_width=True):
            if new_folder_name.strip():
                if create_folder(new_folder_name.strip()):
                    st.success(f"✅ Folder '{new_folder_name}' created!")
                    st.rerun()
                else:
                    st.error("❌ Folder already exists!")
            else:
                st.error("❌ Please enter a folder name")
        if st.button("Rename", use_container_width=True, key="rename_folder_btn"):
            if rename_from and rename_to.strip():
                if rename_folder(rename_from, rename_to.strip()):
                    st.success(f"✅ Folder renamed to '{rename_to.strip()}'")
                    st.rerun()
                else:
                    st.error("❌ Rename failed - target name may already exist or be invalid")
            else:
                st.error("❌ Select a folder and enter a new name")
    
    st.divider()
    
    # Display folders and their contents
    for folder_name in folder_keys():
        with st.expander(f"📁 {folder_name}", expanded=True):
            folder_data = st.session_state.flashcards[folder_name]
            
            # Folder stats
            total_in_folder = sum(len(cards) for cards in folder_data.values())
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Questions", total_in_folder)
            
            with col2:
                st.metric("Learning", len(folder_data["level_1"]))
            
            with col3:
                if folder_name != DEFAULT_FOLDER:
                    if not st.session_state.get(f"confirm_delete_folder_{folder_name}"):
                        if st.button("🗑️ Delete Folder", key=f"delete_folder_{folder_name}", use_container_width=True):
                            st.session_state[f"confirm_delete_folder_{folder_name}"] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ This will delete folder '{folder_name}' and all its flashcards!")
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("Confirm Delete", key=f"confirm_del_folder_{folder_name}", use_container_width=True):
                                delete_folder(folder_name)
                                st.session_state[f"confirm_delete_folder_{folder_name}"] = False
                                st.success(f"Folder deleted!")
                                st.rerun()
                        with col_b:
                            if st.button("Cancel", key=f"cancel_del_folder_{folder_name}", use_container_width=True):
                                st.session_state[f"confirm_delete_folder_{folder_name}"] = False
                                st.rerun()
                else:
                    st.caption("(Default folder - cannot delete)")
            
            st.divider()
            
            # Create tabs for each level within this folder
            level_tabs = st.tabs([
                f"Learning ({len(folder_data['level_1'])})",
                f"Familiar ({len(folder_data['level_2'])})",
                f"Confident ({len(folder_data['level_3'])})",
                f"Mastered ({len(folder_data['level_4'])})"
            ])
            
            levels = ["level_1", "level_2", "level_3", "level_4"]
            
            for tab_idx, level in enumerate(levels):
                with level_tabs[tab_idx]:
                    cards = folder_data[level]
                    
                    if not cards:
                        st.info(f"No questions in {DICTIONARIES[level]['name']} level")
                    else:
                        for idx, card in enumerate(cards):
                            with st.expander(f"Q: {card['question'][:50]}..."):
                                st.write("**Question:**")
                                st.markdown(card['question'])
                                
                                if card.get('question_image'):
                                    st.image(decode_image(card['question_image']), caption="Question Image", use_column_width=True)
                                
                                st.write("**Answer:**")
                                st.markdown(card['answer'])
                                
                                if card.get('answer_image'):
                                    st.image(decode_image(card['answer_image']), caption="Answer Image", use_column_width=True)
                                
                                # Edit button - toggles inline edit fields
                                edit_flag_key = f"editing_{folder_name}_{level}_{idx}"
                                if st.button(f"✏️ Edit", key=f"edit_{folder_name}_{level}_{idx}", use_container_width=True):
                                    st.session_state[edit_flag_key] = True
                                    st.rerun()

                                # Inline edit form
                                if st.session_state.get(edit_flag_key):
                                    # Keys for the edit fields
                                    q_edit_key = f"edit_q_{folder_name}_{level}_{idx}"
                                    a_edit_key = f"edit_a_{folder_name}_{level}_{idx}"
                                    q_img_key = f"edit_qimg_{folder_name}_{level}_{idx}"
                                    a_img_key = f"edit_aimg_{folder_name}_{level}_{idx}"

                                    st.text_input("Edit Question", value=card['question'], key=q_edit_key)
                                    st.text_area("Edit Answer", value=card['answer'], key=a_edit_key, height=120)
                                    col_e1, col_e2 = st.columns(2)
                                    with col_e1:
                                        new_q_img = st.file_uploader("Replace Question Image (leave empty to keep)", type=['png','jpg','jpeg'], key=q_img_key)
                                    with col_e2:
                                        new_a_img = st.file_uploader("Replace Answer Image (leave empty to keep)", type=['png','jpg','jpeg'], key=a_img_key)

                                    col_save, col_cancel = st.columns(2)
                                    with col_save:
                                        if st.button("Save Changes", key=f"save_edit_{folder_name}_{level}_{idx}"):
                                            new_q = st.session_state.get(q_edit_key, card['question'])
                                            new_a = st.session_state.get(a_edit_key, card['answer'])
                                            q_img_data = encode_image(new_q_img) if new_q_img is not None else None
                                            a_img_data = encode_image(new_a_img) if new_a_img is not None else None
                                            # If user didn't upload new images, pass None so edit_flashcard keeps existing
                                            edit_flashcard(folder_name, level, idx, new_q, new_a, question_image=(q_img_data if q_img_data is not None else None), answer_image=(a_img_data if a_img_data is not None else None))
                                            st.session_state[edit_flag_key] = False
                                            st.success("✅ Changes saved")
                                            st.rerun()
                                    with col_cancel:
                                        if st.button("Cancel", key=f"cancel_edit_{folder_name}_{level}_{idx}"):
                                            st.session_state[edit_flag_key] = False
                                            st.rerun()

                                # Move card to another folder
                                move_key = f"move_target_{folder_name}_{level}_{idx}"
                                target = st.selectbox("Move to folder:", options=folder_keys(), format_func=format_folder_label, key=move_key)
                                if st.button("Move", key=f"move_btn_{folder_name}_{level}_{idx}"):
                                    if target and target != folder_name:
                                        if move_card_between_folders(folder_name, level, idx, target):
                                            st.success(f"Moved to folder '{target}'")
                                            st.rerun()
                                        else:
                                            st.error("Move failed")
                                    else:
                                        st.info("Select a different target folder to move")

                                if st.button(f"🗑️ Delete", key=f"delete_{folder_name}_{level}_{idx}", use_container_width=True):
                                    delete_flashcard(folder_name, level, idx)
                                    st.success("Question deleted!")
                                    st.rerun()

# TAB 4: Setup Instructions
with tab4:
    st.subheader("🔧 Google Drive Setup")

    st.subheader("⚖️ Sampling Settings")
    st.info("Adjust how often levels and folders are drawn during practice. Changes persist to your local data file.")
    meta = st.session_state.get("_meta", {})
    draw_chances = meta.get("draw_chances", {lvl: DICTIONARIES[lvl]["draw_chance"] for lvl in DICTIONARIES.keys()})

    st.write("**Level draw probabilities (will be normalized automatically)**")
    cols = st.columns(len(draw_chances))
    new_draw = {}
    for i, lvl in enumerate(["level_1", "level_2", "level_3", "level_4"]):
        with cols[i]:
            new_draw[lvl] = st.slider(DICTIONARIES[lvl]["name"], min_value=0.0, max_value=1.0, value=float(draw_chances.get(lvl, DICTIONARIES[lvl]["draw_chance"])), step=0.01, key=f"draw_{lvl}")

    # Normalize
    total = sum(new_draw.values()) or 1.0
    normalized = {k: (v / total) for k, v in new_draw.items()}

    st.write("**Folder draw weights**")
    folder_weights = meta.get("folder_weights", {})
    # ensure all folders are present
    for f in folder_keys():
        folder_weights.setdefault(f, 1.0)

    fw = {}
    for f in folder_weights.keys():
        fw[f] = st.slider(f, min_value=0.0, max_value=5.0, value=float(folder_weights.get(f, 1.0)), step=0.1, key=f"fw_{f}")

    if st.button("Save Sampling Settings", use_container_width=True):
        # save into the dedicated _meta session entry (persisted by save_flashcards)
        st.session_state._meta = {"draw_chances": normalized, "folder_weights": fw}
        save_flashcards()
        st.success("Sampling settings saved")
        st.rerun()

    # -- Optional: interactive OAuth for this session (useful if you can't put authorized creds into secrets)
    if st.secrets.get("google_oauth_client"):
        if st.button("Authorize Google Drive (this browser/session)"):
            try:
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_config(st.secrets.get("google_oauth_client"), scopes=['https://www.googleapis.com/auth/drive'])
                creds = flow.run_local_server(port=0)
                st.session_state['google_creds'] = creds
                st.success("Authorized for this session — Google Drive sync enabled.")
                # attempt an immediate background sync
                save_flashcards()
            except Exception as e:
                st.error(f"Authorization failed: {e}")
    else:
        st.info("To authorize from this device add a `google_oauth_client` JSON entry to Streamlit secrets (see instructions below).")

    st.divider()
    
    st.info(
        """
        This app can sync your flashcards to Google Drive so you can access them from any device!
        
        Follow these steps to enable Google Drive sync:
        """
    )
    
    st.markdown("""
    ### Step 1: Set Up Google Cloud Project
    1. Go to [Google Cloud Console](https://console.cloud.google.com/)
    2. Create a new project (top left, click project selector)
    3. Name it "Flashcard App"
    4. Wait for it to be created
    
    ### Step 2: Enable Google Drive API
    1. In the top search bar, search for "Google Drive API"
    2. Click on it and press **Enable**
    3. Go to "Credentials" (left sidebar)
    4. Click **Create Credentials** → OAuth Client ID
    5. If prompted, configure OAuth consent screen first:
       - Choose "External" user type
       - Fill in app name: "Flashcard App"
       - Add your email as a test user
       - Save and continue
    6. Back to credentials, click **Create Credentials** → OAuth Client ID
    7. Select "Desktop app" as application type
    8. Click **Create**
    
    ### Step 3: Get Your Credentials
    1. Click the download icon next to your OAuth 2.0 Client ID
    2. Save the downloaded JSON file
    3. Copy the entire contents of the JSON file
    
    ### Step 4: Add to Streamlit Secrets
    1. In your workspace, create or edit `.streamlit/secrets.toml`
    2. Add this line and paste your JSON credentials:
    ```
    google_credentials = {"type": "OAuth2.0", "client_id": "...", ...}
    ```
    3. (Optional) instead of pasting authorized credentials you can add the OAuth client JSON under `google_oauth_client` to perform a one-time interactive authorization from your browser.
    4. Save the file
    
    ### Step 5: Restart the App
    - Refresh your browser or restart Streamlit
    - Your flashcards will now sync to Google Drive!
    """)
    
    st.success("✅ Once set up, your data will automatically sync to Google Drive while keeping a local backup!")
    
    st.divider()
    st.subheader("ℹ️ How the App Works")
    st.markdown("""
    - **Fast Local Storage**: All flashcards are saved locally for instant access
    - **Optional Google Drive Sync**: If you set up Google credentials, your data also syncs to the cloud
    - **No Slowdown**: The app works perfectly without Google Drive set up - Google Drive sync happens in the background
    - **Backup System**: You always have a local copy, even if Google Drive sync fails
    """)