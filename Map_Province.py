import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from folium.plugins import FastMarkerCluster
import matplotlib.colors as mcolors
import pydeck as pdk

# ---------- Streamlit Config ----------
st.set_page_config(page_title="Submission Map & Timeline", layout="wide")
st.title("Submission Map & Timeline")

# ---------- File Upload ----------
st.sidebar.header("Upload Data File")
uploaded_file = st.sidebar.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx"])

if not uploaded_file:
    st.warning("Please upload a CSV or Excel file to begin.")
    st.stop()

# ---------- Data Loading ----------
@st.cache_data
def load_data(file):
    """Load file, extract coordinates (primary & secondary), and clean date."""
    # Load file
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file, engine="openpyxl")

    # Check required columns
    if "Province" not in df.columns:
        st.error("The file must contain a 'Province' column.")
        return pd.DataFrame()

    if "SubmissionDate" not in df.columns:
        st.error("The file must contain a 'SubmissionDate' column.")
        return pd.DataFrame()

    # Parse date
    df["SubmissionDate"] = pd.to_datetime(df["SubmissionDate"], errors="coerce")

    # Select coordinates (primary or secondary)
    def pick_coordinates(row):
        if pd.notna(row.get("Geopoint1-Latitude")) and pd.notna(row.get("Geopoint1-Longitude")):
            return row["Geopoint1-Latitude"], row["Geopoint1-Longitude"]
        elif pd.notna(row.get("geopoint-Latitude")) and pd.notna(row.get("geopoint-Longitude")):
            return row["geopoint-Latitude"], row["geopoint-Longitude"]
        else:
            return (pd.NA, pd.NA)

    coords = df.apply(pick_coordinates, axis=1, result_type="expand")
    coords.columns = ["lat", "lon"]
    df = pd.concat([df, coords], axis=1)

    return df


df = load_data(uploaded_file)
if df.empty:
    st.stop()

# ---------- Province Filter ----------
province_list = ["All Provinces"] + sorted(df["Province"].dropna().unique().tolist())
selected_province = st.sidebar.selectbox("Select Province", province_list)

filtered = df.copy()
if selected_province != "All Provinces":
    filtered = filtered[filtered["Province"] == selected_province]

# ---------- Separate missing and valid coordinates ----------
valid_coords = filtered.dropna(subset=["lat", "lon"]).copy()
missing_coords = filtered[filtered["lat"].isna() | filtered["lon"].isna()].copy()

# ---------- Submission Timeline ----------
st.header("Submissions Over Time")
if filtered["SubmissionDate"].notna().any():
    times = filtered.dropna(subset=["SubmissionDate"]).copy()
    times["date_only"] = times["SubmissionDate"].dt.date
    times_by_date = times.groupby("date_only").size().reset_index(name="count")
    fig = px.line(times_by_date, x="date_only", y="count", title="Submissions Over Time")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No valid SubmissionDate values found.")

st.markdown("---")

# ---------- PyDeck Map ----------
st.header("Map of Submissions")

if valid_coords.empty:
    st.info("No valid GPS coordinates found for the selected province.")
else:
    # Center map
    center_lat = valid_coords["lat"].mean()
    center_lon = valid_coords["lon"].mean()

    # Prepare data for PyDeck
    map_df = valid_coords.copy()

    # Default dot color (blue) and white stroke
    fill_color = [31, 119, 180]  # Blue in RGB (same as #1f77b4)
    line_color = [255, 255, 255]  # White stroke

    # Define the layer
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position='[lon, lat]',
        get_radius=50,
        radius_min_pixels=4,
        radius_max_pixels=12,
        stroked=True,
        filled=True,
        get_fill_color=[31, 119, 180, 200],
        get_line_color=[255, 255, 255],
        line_width_min_pixels=2,
        pickable=True,
    )

    # Define tooltip (popup info)
    tooltip = {
        "html": """
        <b>KEY:</b> {KEY} <br/>
        <b>Province:</b> {Province} <br/>
        <b>Submission Date:</b> {SubmissionDate} <br/>
        <b>Lat:</b> {lat}, <b>Lon:</b> {lon}
        """,
        "style": {
            "backgroundColor": "rgba(0, 0, 0, 0.7)",
            "color": "white",
            "fontSize": "12px",
        },
    }

    # Define view
    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=6,
        pitch=0,
    )

    # Create deck
    r = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="mapbox://styles/mapbox/light-v9"
    )

    st.pydeck_chart(r)


# ---------- Missing Coordinates ----------
st.header("Records with No GPS Points")

if missing_coords.empty:
    st.success("All records have GPS Points.")
else:
    st.warning(f"{len(missing_coords)} records are missing GPS Points.")
    st.dataframe(missing_coords)

    csv_data = missing_coords.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Records Missing GPS Points (CSV)",
        data=csv_data,
        file_name="missing_gps.csv",
        mime="text/csv",
    )
