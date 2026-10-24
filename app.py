
import streamlit as st

st.set_page_config(page_title="CampusSignal")

st.title("CampusSignal")
st.write("Your college communication, organized.")

message = st.text_area("Paste a Slack message here")

if st.button("Analyze message"):
    if message.strip():
        st.write("Message received:")
        st.write(message)
    else:
        st.warning("Please enter a message.")
