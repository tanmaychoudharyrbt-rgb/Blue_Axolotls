
import streamlit as st

st.set_page_config(page_title="CampusSignal", page_icon="📚")

st.title("📚 CampusSignal")
st.write("Your college communication, organized.")

message = st.text_area(
    "Paste a college Slack message here:",
    placeholder="Example: Mathematics worksheet 3 has been uploaded. Submit by Friday."
)

if st.button("Analyze message"):
    if not message.strip():
        st.warning("Please enter a message.")
    else:
        text = message.lower()

        if any(word in text for word in ["worksheet", "assignment", "notes", "lecture"]):
            category = "📚 Academic"
        elif any(word in text for word in ["mandatory", "compulsory", "attendance", "urgent"]):
            category = "🚨 Important / Urgent"
        elif any(word in text for word in ["fest", "concert", "event", "registration"]):
            category = "🎉 Event"
        else:
            category = "💬 Other"

        st.subheader("Analysis Result")
        st.write("**Category:**", category)
        st.write("**Original message:**", message)
