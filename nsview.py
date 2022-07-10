import os
import re
import pandas as pd
from datetime import datetime, timedelta
import pytz

import streamlit as st
import extra_streamlit_components as stx
from st_aggrid import AgGrid
from st_aggrid.grid_options_builder import GridOptionsBuilder
import plotly.graph_objects as go

from nsdata import ns_data
from utils import get_list_index


COLS_REASON_NUM = ["ISF",
                   "CR",
                   "Target",
                   "tdd",
                   "circadian_sensitivity",
                   "Dev",
                   "BGI",
                   "aimi_bg",
                   "aimi_delta",
                   "DiaSMB",
                   "DiaManualBolus",
                   "MagicNumber",
                   "smbRatio",
                   "limitIOB",
                   "bgDegree"
                   ]

COOKIE_NS_URL = "ns_url"
COOKIE_NS_TOKEN = "ns_token"
COOKIE_TIMEZONE = "timezone"

TZ_DONT_CONVERT = "Dont convert"

COLOR_COL1 = "red"
COLOR_COL2 = "blue"
COLOR_COL3 = "green"


# @st.experimental_memo(show_spinner=False)
def get_manager():
    return stx.CookieManager()


title = "Nightscout Android APS Data Viewer"
st.set_page_config(layout="wide", page_title=title)
cookie_manager = get_manager()


def get_reason_item(reason, item_name):
    if pd.isna(reason):
        return None
    rs = re.findall(f"{item_name}[\s]{{0,1}}: ([\d.\s-]*),", reason, flags=re.I)
    if len(rs) > 0:
        return rs[0]
    return None


def get_ns_data(ns_url, ns_token, min_date, max_date, time_zone):
    df = ns_data("devicestatus", ns_url, ns_token, max_date, min_date)
    if len(df) == 0:
        return None

    # Parse json columns (might need to handle errors and clean data)
    df = pd.concat([df, pd.json_normalize(df.pump)], axis=1)
    df = pd.concat([df, pd.json_normalize(df.openaps)], axis=1)

    # Date column (used in x axis)
    if time_zone == TZ_DONT_CONVERT:
        df["date"] = df["created_at"]
    else:
        df["date"] = df["created_at"].dt.tz_convert(tz=time_zone)

    # Parse other columns
    for col in COLS_REASON_NUM:
        col_name = "reason." + col
        df[col_name] = df["suggested.reason"].apply(get_reason_item, item_name=col)
        df[col_name] = pd.to_numeric(df[col_name], errors="coerce")

    # Calculated columns
    df["CF"] = df["reason.ISF"].divide(df["reason.CR"])

    df = df.sort_values("created_at", ascending=False)
    return df


@st.experimental_memo(show_spinner=False)
def get_cached_ns_data(ns_url, ns_token, min_date, max_date, time_zone):
    return get_ns_data(ns_url, ns_token, min_date, max_date, time_zone)


def show_data(df):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_pagination()
    gb.configure_side_bar()
    grid_options = gb.build()
    AgGrid(df, gridOptions=grid_options, enable_enterprise_modules=True)


def show_graph(df, col_name1, col_name2, col_name3):
    fig = go.Figure()
    fig.update_layout(
        xaxis_title="Time",
        margin=dict(l=20, r=20, t=60, b=20),
        height=500,
        paper_bgcolor="LightSteelBlue",
        showlegend=False,
    )
    # Define x an ys
    x = df["date"]
    y1 = df[col_name1]
    y2 = df[col_name2]
    y3 = df[col_name3]  if col_name3 != "" else None

    fig.add_trace(go.Scatter(x=x, y=y1, line=dict(color=COLOR_COL1)))
    fig.add_trace(go.Scatter(x=x, y=y2, yaxis="y2", line=dict(color=COLOR_COL2)))
    if col_name3 != "":
        fig.add_trace(go.Scatter(x=x, y=y3, yaxis="y3", line=dict(color=COLOR_COL3)))

    fig.update_layout(
        yaxis=dict(
            title=col_name1,
            titlefont=dict(
                color=COLOR_COL1
            ),
            tickfont=dict(
                color=COLOR_COL1
            )
        ),
        yaxis2=dict(
            title=col_name2,
            titlefont=dict(
                color=COLOR_COL2
            ),
            tickfont=dict(
                color=COLOR_COL2
            ),
            anchor="x",
            overlaying="y",
            side="right"
        ),
    )
    if col_name3 != "":
        fig.update_layout(dict(
            xaxis=dict(
                domain=[0.09, 1.0]
            ),
            yaxis3=dict(
                title=col_name3,
                titlefont=dict(
                    color=COLOR_COL3
                ),
                tickfont=dict(
                    color=COLOR_COL3
                ),
                anchor="free",
                overlaying="y",
                side="left",
            )))

    # Plot graph
    st.plotly_chart(fig, use_container_width=True)


def main():
    ns_url_cookie = cookie_manager.get(cookie=COOKIE_NS_URL)
    ns_url_cookie = ns_url_cookie if ns_url_cookie else ""
    ns_token_cookie = cookie_manager.get(cookie=COOKIE_NS_TOKEN)
    ns_token_cookie = ns_token_cookie if ns_token_cookie else ""
    timezone_cookie = cookie_manager.get(cookie=COOKIE_TIMEZONE)
    timezone_cookie = timezone_cookie if timezone_cookie else TZ_DONT_CONVERT

    with st.sidebar:
        st.subheader(title)
        with st.form("nsview_options"):
            ns_url = st.text_input("NightScout URL:", ns_url_cookie)
            if ns_url.endswith("/"):
                ns_url = ns_url[:-1]
            if not ns_url.lower().startswith("https://"):
                ns_url = "https://" + ns_url
            ns_token = st.text_input("NightScout Read Token:", ns_token_cookie)

            # Default start date is yesterday
            min_date = datetime.now() + timedelta(days=-1)
            max_date = datetime.now()

            min_date, max_date = st.date_input("Date Range:", value=[min_date, max_date])

            tzs = [TZ_DONT_CONVERT] + [str(tz) for tz in pytz.common_timezones]
            try:
                tz_cookie_index = tzs.index(timezone_cookie)
            except ValueError:
                tz_cookie_index = 0
            timezone_name = st.selectbox("Convert to Timezone:", options=tzs, index=tz_cookie_index)

            if timezone_name != TZ_DONT_CONVERT:
                tz = pytz.timezone(timezone_name)
            else:
                tz = pytz.timezone("UTC")
            max_date = tz.localize(datetime(max_date.year, max_date.month, max_date.day))
            min_date = tz.localize(datetime(min_date.year, min_date.month, min_date.day))

            submit_button = st.form_submit_button("Submit")
        st.write("\n__Author:__ [Rafael Del Rey](https://www.linkedin.com/in/rafaeldelrey)")

    if submit_button or st.session_state.get("button_submit", False):
        st.session_state["button_submit"] = True
        if ns_url == "":
            st.warning("Invalid Nightscout URL")
            return
        with st.spinner("Fetching data from Nightscout..."):
            # Lets add a day on max_date, so it is included on the fetch
            max_date += timedelta(days=1)

            # Convert dates to string in UTC
            min_date = min_date.replace(tzinfo=pytz.utc)
            max_date = max_date.replace(tzinfo=pytz.utc)
            # st.write(max_date)

            if submit_button:
                # Dont use cache, if clicked on the button
                df = get_ns_data(ns_url, ns_token, str(min_date), str(max_date), timezone_name)
            else:
                df = get_cached_ns_data(ns_url, ns_token, str(min_date), str(max_date), timezone_name)

        if (df is None) or (len(df) == 0):
            st.warning("No data loaded!")
            return

        # Store cookies
        cookie_manager.set(COOKIE_NS_URL, ns_url, key=COOKIE_NS_URL + "_set")
        cookie_manager.set(COOKIE_NS_TOKEN, ns_token, key=COOKIE_NS_TOKEN + "_set")
        cookie_manager.set(COOKIE_TIMEZONE, timezone_name, key=COOKIE_TIMEZONE + "_set")

        st.subheader(title)

        # Define columns to plot
        col1, col2, col3 = st.columns(3)
        cols_graph_first = ["suggested.bg", "reason.ISF", "reason.CR", "CF"]       # Show these first
        cols_graph_first = [col for col in cols_graph_first if col in df.columns]  # if they exist in the data
        cols_graph = cols_graph_first + sorted(set(df.columns) - set(cols_graph_first))
        index1 = get_list_index(cols_graph, "suggested.bg", 0)
        index2 = get_list_index(cols_graph, "reason.ISF", 1)

        col_name1 = col1.selectbox("Graph Column 1:", cols_graph, index=index1)
        col_name2 = col2.selectbox("Graph Column 2:", cols_graph, index=index2)
        col_name3 = col3.selectbox("Graph Column 3:", [""] + cols_graph, index=0)

        # Show graph with the selected columns
        show_graph(df, col_name1, col_name2, col_name3)

        # Show data
        st.subheader("Data:")
        show_data(df)


if __name__ == "__main__":
    main()
