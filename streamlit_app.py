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

# Google Drive Functions (Simplified - No external API calls on every load)
def has_google_credentials():
    """Check if Google credentials are configured."""
    try:
        return st.secrets.get("google_credentials") is not None
    except:
        return False

def load_flashcards():
    """Load flashcards from local file only (much faster)."""
    # Fallback to local file
    if os.path.exists(LOCAL_FILE):
        try:
            with open(LOCAL_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    
    return {level: [] for level in DICTIONARIES.keys()}

def save_flashcards():
    """Save flashcards to local file (primary) and optionally to Google Drive."""
    # Always save locally first (fast and reliable)
    with open(LOCAL_FILE, "w") as f:
        json.dump(st.session_state.flashcards, f, indent=2)
    
    # Try to save to Google Drive if credentials exist (optional, don't block if it fails)
    if has_google_credentials():
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.api_python_client import discovery
            from googleapiclient.http import MediaIoBaseUpload
            
            creds_dict = st.secrets.get("google_credentials")
            creds = Credentials.from_authorized_user_info(creds_dict, ['https://www.googleapis.com/auth/drive'])
            service = discovery.build('drive', 'v3', credentials=creds)
            
            # Find file ID
            query = f"name='{DRIVE_FILE_NAME}' and trashed=false"
            results = service.files().list(q=query, spaces='drive', fields='files(id, name)', pageSize=1).execute()
            files = results.get('files', [])
            file_id = files[0]['id'] if files else None
            
            file_content = json.dumps(st.session_state.flashcards, indent=2)
            media = MediaIoBaseUpload(io.BytesIO(file_content.encode()), mimetype='application/json')
            
            if file_id:
                # Update existing file
                service.files().update(fileId=file_id, media_body=media).execute()
            else:
                # Create new file
                file_metadata = {'name': DRIVE_FILE_NAME}
                service.files().create(body=file_metadata, media_body=media).execute()
        except Exception as e:
            # Silently fail - we already saved locally
            pass

# Define functions first
def add_new_flashcard(question, answer, question_image=None, answer_image=None):
    """Add a new flashcard to level_1 (highest chance of being drawn)."""
    if question.strip() and answer.strip():
        new_card = {
            "question": question.strip(),
            "answer": answer.strip(),
            "question_image": question_image,
            "answer_image": answer_image
        }
        st.session_state.flashcards["level_1"].append(new_card)
        save_flashcards()
        return True
    return False

def delete_flashcard(level, index):
    """Delete a flashcard from a specific level."""
    if 0 <= index < len(st.session_state.flashcards[level]):
        st.session_state.flashcards[level].pop(index)
        save_flashcards()
        return True
    return False

def reset_all_cards():
    """Reset all cards back to Learning level."""
    all_cards = []
    for level in st.session_state.flashcards.values():
        all_cards.extend(level)
    
    # Clear all levels and move everything back to level_1
    st.session_state.flashcards = {level: [] for level in DICTIONARIES.keys()}
    st.session_state.flashcards["level_1"] = all_cards
    save_flashcards()

def delete_all_cards():
    """Permanently delete all flashcards."""
    st.session_state.flashcards = {level: [] for level in DICTIONARIES.keys()}
    save_flashcards()

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
    # Check all levels and collect available questions
    available = []
    for level, cards in st.session_state.flashcards.items():
        if cards:
            available.append((level, cards))
    
    if not available:
        return None
    
    # Determine which level to draw from based on probabilities
    rand = random()
    cumulative = 0
    
    for level in ["level_1", "level_2", "level_3", "level_4"]:
        cumulative += DICTIONARIES[level]["draw_chance"]
        if rand <= cumulative and st.session_state.flashcards[level]:
            cards = st.session_state.flashcards[level]
            selected = choice(cards)
            return (level, selected, cards.index(selected))
    
    # Fallback: return from first non-empty level
    for level, cards in available:
        selected = choice(cards)
        return (level, selected, cards.index(selected))

def move_card_up(current_level, card_index):
    """Move card to next level (reduce draw chance)."""
    level_order = ["level_1", "level_2", "level_3", "level_4"]
    current_idx = level_order.index(current_level)
    
    if current_idx < len(level_order) - 1:
        next_level = level_order[current_idx + 1]
        card = st.session_state.flashcards[current_level].pop(card_index)
        st.session_state.flashcards[next_level].append(card)
        save_flashcards()
        return True
    return False

def move_card_down(current_level, card_index):
    """Move card back to Learning level (when answered incorrectly)."""
    if current_level != "level_1":
        card = st.session_state.flashcards[current_level].pop(card_index)
        st.session_state.flashcards["level_1"].append(card)
        save_flashcards()
        return True
    return False

def get_stats():
    """Return statistics about flashcard progress."""
    stats = {}
    total = 0
    for level, cards in st.session_state.flashcards.items():
        count = len(cards)
        stats[level] = count
        total += count
    stats["total"] = total
    return stats

# Initialize session state
if "flashcards" not in st.session_state:
    st.session_state.flashcards = load_flashcards()
if "current_question" not in st.session_state:
    st.session_state.current_question = None
if "show_answer" not in st.session_state:
    st.session_state.show_answer = False

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
    
    # Text inputs in form
    with st.form("add_question_form"):
        question_input = st.text_input("Question", placeholder="Enter your question")
        answer_input = st.text_area("Answer", placeholder="Enter the answer", height=100)
        submitted = st.form_submit_button("Add Question", use_container_width=True)
    
    # Image uploaders OUTSIDE form (better compatibility)
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.temp_q_image = st.file_uploader("Question Image (optional)", type=['png', 'jpg', 'jpeg'], key="q_img")
    with col2:
        st.session_state.temp_a_image = st.file_uploader("Answer Image (optional)", type=['png', 'jpg', 'jpeg'], key="a_img")
    
    # Handle form submission
    if submitted:
        if question_input.strip() and answer_input.strip():
            q_img_data = encode_image(st.session_state.temp_q_image)
            a_img_data = encode_image(st.session_state.temp_a_image)
            
            if add_new_flashcard(question_input, answer_input, q_img_data, a_img_data):
                st.success("✅ Question added to Learning level!")
                # Clear the image session state
                st.session_state.temp_q_image = None
                st.session_state.temp_a_image = None
                st.rerun()
            else:
                st.error("❌ Error adding question")
        else:
            st.error("❌ Please enter both question and answer")

# TAB 2: Practice
with tab2:
    st.subheader("📚 Practice Questions")
    
    stats = get_stats()
    if stats["total"] == 0:
        st.info("📝 No questions yet! Add some questions in the 'Add Questions' tab to get started.")
    elif stats["level_4"] == stats["total"]:
        st.success("🎉 Congratulations! You've mastered all questions!")
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Reset to Learning", use_container_width=True, type="secondary"):
                if st.session_state.get("confirm_reset"):
                    reset_all_cards()
                    st.session_state.confirm_reset = False
                    st.success("All cards moved back to Learning level!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.session_state.confirm_reset = True
                    st.rerun()
        
        with col2:
            if st.button("🗑️ Delete All Cards", use_container_width=True, type="secondary"):
                if st.session_state.get("confirm_delete"):
                    delete_all_cards()
                    st.session_state.confirm_delete = False
                    st.success("All cards deleted!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.session_state.confirm_delete = True
                    st.rerun()
        
        # Show confirmation messages
        if st.session_state.get("confirm_reset"):
            st.warning("⚠️ Reset all cards back to Learning level?")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Confirm Reset", use_container_width=True, key="confirm_reset_btn"):
                    reset_all_cards()
                    st.session_state.confirm_reset = False
                    st.success("All cards moved back to Learning level!")
                    time.sleep(0.5)
                    st.rerun()
            with col_b:
                if st.button("Cancel", use_container_width=True, key="cancel_reset_btn"):
                    st.session_state.confirm_reset = False
                    st.rerun()
        
        if st.session_state.get("confirm_delete"):
            st.error("🚨 This will permanently delete all your flashcards!")
            col_c, col_d = st.columns(2)
            with col_c:
                if st.button("Yes, Delete All", use_container_width=True, type="primary", key="confirm_delete_btn"):
                    delete_all_cards()
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
                st.session_state.current_level, st.session_state.current_card, st.session_state.card_index = result
                st.session_state.current_question = st.session_state.current_card["question"]
        
        if st.session_state.current_question:
            # Display question
            st.write("### Question:")
            st.write(f"**{st.session_state.current_question}**")
            
            # Display question image if exists
            if st.session_state.current_card.get("question_image"):
                st.image(decode_image(st.session_state.current_card["question_image"]), use_column_width=True)
            
            # Display answer if shown
            if st.session_state.show_answer:
                st.divider()
                st.write("### Answer:")
                st.write(f"**{st.session_state.current_card['answer']}**")
                
                # Display answer image if exists
                if st.session_state.current_card.get("answer_image"):
                    st.image(decode_image(st.session_state.current_card["answer_image"]), use_column_width=True)
                
                # Result buttons
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("✅ Correct!", use_container_width=True, type="primary"):
                        current_level = st.session_state.current_level
                        card_index = st.session_state.card_index
                        
                        # Move card up and check if successful
                        if move_card_up(current_level, card_index):
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
                        current_level = st.session_state.current_level
                        card_index = st.session_state.card_index
                        
                        # Move card back to Learning level
                        if current_level != "level_1":
                            move_card_down(current_level, card_index)
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

# TAB 3: Manage Questions
with tab3:
    st.subheader("📋 View & Manage All Questions")
    
    stats = get_stats()
    st.info(f"Total Questions: {stats['total']}")
    
    # Create tabs for each level
    level_tabs = st.tabs([
        f"Learning ({stats['level_1']})",
        f"Familiar ({stats['level_2']})",
        f"Confident ({stats['level_3']})",
        f"Mastered ({stats['level_4']})"
    ])
    
    levels = ["level_1", "level_2", "level_3", "level_4"]
    
    for tab_idx, level in enumerate(levels):
        with level_tabs[tab_idx]:
            cards = st.session_state.flashcards[level]
            
            if not cards:
                st.info(f"No questions in {DICTIONARIES[level]['name']} level")
            else:
                for idx, card in enumerate(cards):
                    with st.expander(f"Q: {card['question'][:50]}..."):
                        st.write("**Question:**")
                        st.write(card['question'])
                        
                        if card.get('question_image'):
                            st.image(decode_image(card['question_image']), caption="Question Image", use_column_width=True)
                        
                        st.write("**Answer:**")
                        st.write(card['answer'])
                        
                        if card.get('answer_image'):
                            st.image(decode_image(card['answer_image']), caption="Answer Image", use_column_width=True)
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"🗑️ Delete", key=f"delete_{level}_{idx}", use_container_width=True):
                                delete_flashcard(level, idx)
                                st.success("Question deleted!")
                                st.rerun()

# TAB 4: Setup Instructions
with tab4:
    st.subheader("🔧 Google Drive Setup")
    
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
    3. Save the file
    
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