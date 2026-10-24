
import streamlit as st

st.set_page_config(page_title="CampusSignal", page_icon="📚")

st.title("📚 CampusSignal")
st.write("Your college communication, organized.")

# Store messages during this app session
if "messages" not in st.session_state:
    st.session_state.messages = []

message = st.text_area(
    "Paste a college Slack message here:",
    placeholder="Example: Register for the college fest!"
)

if st.button("Analyze message"):
    if not message.strip():
        st.warning("Please enter a message.")
    else:
        text = message.lower().strip()

        # Check for an exact match, ignoring capitalization and outer spaces
        duplicate = any(
            old_message.lower().strip() == text
            for old_message in st.session_state.messages
        )

        if duplicate:
            st.warning("🔁 Duplicate detected! This message has already been submitted.")
        else:
            st.session_state.messages.append(message)

            if any(word in text for word in ["worksheet", "assignment", "notes", "lecture"]):
                category = "📚 Academic"
            elif any(word in text for word in ["mandatory", "compulsory", "attendance", "urgent"]):
                category = "🚨 Important / Urgent"
            elif any(word in text for word in ["fest", "concert", "event", "registration"]):
                category = "🎉 Event"
            else:
                category = "💬 Other"

            st.success("New message received!")
            st.write("**Category:**", category)
            st.write("**Message:**", message)

st.divider()
st.subheader("📨 Messages received this session")
st.write(f"Total unique messages: {len(st.session_state.messages)}")

for i, saved_message in enumerate(st.session_state.messages, start=1):
    st.write(f"{i}. {saved_message}")
