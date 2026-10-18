"""Component 4 dashboard.  From research/component_4:  .venv\\Scripts\\python.exe -m streamlit run dashboard/app.py"""
import streamlit as st

st.set_page_config(page_title="Horton Plains – Trail Crowd Forecast", page_icon=":material/hiking:", layout="wide")

pages = [
    st.Page("views/overview.py", title="Overview", icon=":material/home:", default=True),
    st.Page("views/plan.py", title="Plan a visit", icon=":material/travel_explore:"),
    st.Page("views/book.py", title="Book a slot", icon=":material/confirmation_number:"),
    st.Page("views/forecast.py", title="Daily forecast", icon=":material/calendar_month:"),
    st.Page("views/control.py", title="Entry control", icon=":material/gate:"),
    st.Page("views/trail.py", title="Trail and data", icon=":material/map:"),
    st.Page("views/simulator.py", title="Simulator", icon=":material/groups:"),
    st.Page("views/models.py", title="Model comparison", icon=":material/monitoring:"),
    st.Page("views/capacity.py", title="Capacity method", icon=":material/rule:"),
]
st.navigation(pages).run()
