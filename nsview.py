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
from plotly.subplots import make_subplots

from nsdata import ns_data_file


COLS_SUGGESTED_NUM = [
    "BG",
    "COB",
    "IOB",
    "eventualBG",
    "targetBG",
    "insulinReq",
    "sensitivityRatio",
    "variable_sens",
]

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

COLS_GRAPH = COLS_REASON_NUM + COLS_SUGGESTED_NUM

COOKIE_NS_URL = "ns_url"
COOKIE_NS_TOKEN = "ns_token"
COOKIE_TIMEZONE = "timezone"


TZ_DONT_CONVERT = "Dont convert"


# @st.experimental_memo(show_spinner=False)
def get_manager():
    return stx.CookieManager()


title = "Nightscout Android APS Data Viewer"
st.set_page_config(layout="wide", page_title=title)
cookie_manager = get_manager()


def get_openaps(openaps, item_name):
    if openaps is None:
        return None
    item = openaps.get(item_name, None)
    return item


def get_suggested(openaps, item_name):
    ret = None
    sug = get_openaps(openaps, "suggested")
    if sug:
        ret = sug.get(item_name, None)
        if ret is None:
            ret = sug.get(item_name.lower(), None)
    return ret


def get_reason_item(reason, item_name):
    if reason is None:
        return None
    rs = re.findall(f"{item_name}[\s]{{0,1}}: ([\d.\s-]*),", reason, flags=re.I)
    if len(rs) > 0:
        return rs[0]
    return None


def get_ns_data(ns_url, ns_token, min_date, max_date, time_zone):
    data_dir = "./temp"
    os.makedirs(data_dir, exist_ok=True)
    fp_status, meta_status = ns_data_file("devicestatus", data_dir, ns_url, ns_token, max_date, min_date)
    if not os.path.exists(fp_status):
        return None
    df = pd.read_json(fp_status)
    if len(df) == 0:
        return None
    if time_zone == TZ_DONT_CONVERT:
        df["date"] = df["created_at"]
    else:
        df["date"] = df["created_at"].dt.tz_convert(tz=time_zone)
    df["reason"] = df["openaps"].apply(get_suggested, item_name="reason")
    # df["BG"] = df["openaps"].apply(get_suggested, item_name="BG")
    df = df.sort_values("created_at", ascending=False)

    for col in COLS_SUGGESTED_NUM:
        df[col] = df["openaps"].apply(get_suggested, item_name=col)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in COLS_REASON_NUM:
        df[col] = df["reason"].apply(get_reason_item, item_name=col)
        df[col] = pd.to_numeric(df[col], errors="coerce")
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
    print(df[["created_at", "date"]].head())


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

        # Show graph
        st.subheader(title)
        # Graph options
        col1, col2, _, _ = st.columns(4)
        col_name1 = col1.selectbox("Graph Column 1:", COLS_GRAPH, index=COLS_GRAPH.index("ISF"))
        col_name2 = col2.selectbox("Graph Column 2:", COLS_GRAPH, index=COLS_GRAPH.index("BG"))

        show_graph(df, col_name1, col_name2)

        # Show data
        st.subheader("Data:")
        show_data(df)


if __name__ == "__main__":
    main()
