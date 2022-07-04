import os
import re
import pandas as pd
from datetime import datetime, timedelta

import streamlit as st
import extra_streamlit_components as stx
from st_aggrid import AgGrid
from st_aggrid.grid_options_builder import GridOptionsBuilder
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from nsdata import ns_data_file


COLS_REASON_NUM = ["isf", "target", "tdd", "circadian_sensitivity"]
COLS_GRAPH = ["bg"] + COLS_REASON_NUM

COOKIE_NS_URL = "ns_url"
COOKIE_NS_TOKEN = "ns_token"


@st.cache(allow_output_mutation=True)
def get_manager():
    return stx.CookieManager()


title = "Nightccout Android APS Data Viewer (AIMI Version)"
st.set_page_config(layout="wide", page_title=title)
cookie_manager = get_manager()


def get_openaps(openaps, item_name):
    if openaps is None:
        return None
    item = openaps.get(item_name, None)
    return item


def get_suggested(openaps, item_name):
    sug = get_openaps(openaps, "suggested")
    if sug:
        return sug.get(item_name, None)
    return None


def get_reason_item(reason, item_name):
    if reason is None:
        return None
    rs = re.findall(f"{item_name}[\s]{{0,1}}: ([\d.\s]*),", reason, flags=re.I)
    if len(rs) > 0:
        return rs[0]
    return None


def get_ns_data(ns_url, ns_token, min_date, max_date):
    data_dir = "./temp"
    os.makedirs(data_dir, exist_ok=True)
    fp_status, meta_status = ns_data_file("devicestatus", data_dir, ns_url, ns_token, max_date, min_date)
    if not os.path.exists(fp_status):
        return None
    df = pd.read_json(fp_status)
    if len(df) == 0:
        return None
    df["date"] = df["created_at"].dt.tz_convert("EST")
    df["reason"] = df["openaps"].apply(get_suggested, item_name="reason")
    df["bg"] = df["openaps"].apply(get_suggested, item_name="bg")
    df = df.sort_values("created_at", ascending=False)

    for col in COLS_REASON_NUM:
        df[col] = df["reason"].apply(get_reason_item, item_name=col)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache(show_spinner=False)
def get_cached_ns_data(ns_url, ns_token, min_date, max_date):
    return get_ns_data(ns_url, ns_token, min_date, max_date)


def show_data(df):
    st.subheader("Data:")
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_pagination()
    gb.configure_side_bar()
    grid_options = gb.build()
    AgGrid(df, gridOptions=grid_options, enable_enterprise_modules=True)


def show_graph(df, col_name1, col_name2):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.update_layout(
        xaxis_title="Time",
        # yaxis_title="ISF",
        margin=dict(l=20, r=20, t=60, b=20),
        height=500,
        paper_bgcolor="LightSteelBlue",
    )
    # Define x an ys
    x = df["date"]
    y1 = df[col_name1]
    y2 = df[col_name2]

    # Add traces
    fig.add_trace(go.Scatter(x=x, y=y1, name=col_name1), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=y2, name=col_name2), secondary_y=True)

    # Update axes
    fig.update_yaxes(title_text=col_name1, secondary_y=False)
    fig.update_yaxes(title_text=col_name2, secondary_y=True)

    # Plot graph
    st.plotly_chart(fig, use_container_width=True)


def main():
    with st.sidebar:
        st.title(title)
        with st.form("nsview_options"):
            ns_url_cookie = cookie_manager.get(cookie=COOKIE_NS_URL)
            ns_url_cookie = ns_url_cookie if ns_url_cookie else ""
            ns_url_token = cookie_manager.get(cookie=COOKIE_NS_TOKEN)
            ns_url_token = ns_url_token if ns_url_token else ""

            ns_url = st.text_input("NightScout URL:", ns_url_cookie)
            ns_token = st.text_input("NightScout Read Token:", ns_url_token)

            # Default start date is yesterday
            min_date = datetime.now() + timedelta(days=-1)
            max_date = datetime.now() + timedelta(days=1)

            min_date, max_date = st.date_input("Date Range:", value=[min_date, max_date])
            min_date = str(min_date)
            max_date = str(max_date)

            submit_button = st.form_submit_button("Submit")
    if submit_button or st.session_state.get("button_submit", False):
        st.session_state["button_submit"] = True
        with st.spinner("Fetching data from Nightscout..."):
            if submit_button:
                # Dont use cache, if clicked on the button
                df = get_ns_data(ns_url, ns_token, min_date, max_date)
            else:
                df = get_cached_ns_data(ns_url, ns_token, min_date, max_date)

        if (df is None) or (len(df) == 0):
            st.warning("No data loaded!")
            return

        # Store cookies
        cookie_manager.set(COOKIE_NS_URL, ns_url, key=COOKIE_NS_URL + "_set")
        cookie_manager.set(COOKIE_NS_TOKEN, ns_token, key=COOKIE_NS_TOKEN + "_set")

        # Graph options
        st.subheader("Graphs:")
        col1, col2, col3 = st.columns(3)
        col_name1 = col1.selectbox("Graph Column 1:", COLS_GRAPH, index=0)
        col_name2 = col2.selectbox("Graph Column 2:", COLS_GRAPH, index=1)

        # Show graph
        show_graph(df, col_name1, col_name2)

        # Show data
        show_data(df)


if __name__ == "__main__":
    main()
