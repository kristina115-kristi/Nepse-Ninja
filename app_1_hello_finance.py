import streamlit as st
st.set_page_config(page_title="Hello Finance", page_icon="😂")

st.title("My First Application")
st.write("Welcome to my first application in Python Class")

student_name = st.text_input("Enter Your Name")
Area_of_Interest = st.selectbox(
    "Choose an Area Of Interest",
    ["Financial Management", "Investment", "Auditing", "Accounting"],
)

monthly_investment = st.number_input(
    "Enter your preferred monthly investment:",
    min_value=0,
    value=1000,
    step=500
)

finance_study = st.checkbox("Have you studied finance before?")

st.write(f"Your preferred monthly investment is: {monthly_investment}")
if st.button("Show Welcome Message"):
    if student_name.strip():
        st.success(
            f"Welcome, {student_name}! Your interest in {Area_of_Interest} is really cool."
        )

        if finance_study:
            st.write("Great! You already have some finance knowledge.")
        else:
            st.write("No worries! This app will help you learn finance.")
    else:
        st.warning("Please enter your name.")
