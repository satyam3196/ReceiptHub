import streamlit as st
import pandas as pd
import requests
from datetime import datetime

@st.cache_data(ttl=10)  # Set TTL (time-to-live) to 10 seconds 
def load_bill_data():
    try:
        data = pd.read_excel("../backend/bills_data.xlsx")  # Replace with the actual path
        # Convert relevant columns to datetime
        data['Scanned_on'] = pd.to_datetime(data['Scanned_on'], errors='coerce').dt.date
        
        # Convert 'subtotal' and 'total_amount' to numeric, removing any non-numeric characters
        data['subtotal'] = pd.to_numeric(data['subtotal'].replace('[\$,]', '', regex=True), errors='coerce')
        data['total_amount'] = pd.to_numeric(data['total_amount'].replace('[\$,]', '', regex=True), errors='coerce')
    except FileNotFoundError:
        st.error("Data file not found. Please upload a bill to start.")
        data = pd.DataFrame()  # Empty DataFrame if file is not found
    
    return data

# Function to filter data by selected date or date range
def filter_by_date_range(df, start_date, end_date=None):
    if end_date:
        return df[(df['Scanned_on'] >= start_date) & (df['Scanned_on'] <= end_date)]
    else:
        return df[df['Scanned_on'] == start_date]

# Set page config with a custom title
st.set_page_config(page_title="ReceiptHub", layout="wide")

# Sidebar for navigation and settings
with st.sidebar:
    st.title("ReceiptHub")
    st.markdown("""
    **Streamline your expense tracking!**  
    Upload receipts, categorize expenses, and view insights on a customizable dashboard.
    """)
    page = st.selectbox("Choose a page:", ["Dashboard", "Upload Bill"])

# Load the data
df = load_bill_data()

# Dashboard Page
if page == "Dashboard":
    st.header("Dashboard Overview")
    st.write("""
    **ReceiptHub** helps small business owners, solo entrepreneurs, and small teams streamline their expense tracking.
    Upload receipts, categorize expenses, and view insights on a customizable dashboard that organizes and visualizes your spending.
    """)

    # Check if the DataFrame is empty
    if df.empty:
        st.warning("No data available. Please upload a bill to see the dashboard.")
    else:
        # Set up a date range selector in the sidebar
        with st.sidebar:
            st.subheader("Filter by Date")
            min_date = df['Scanned_on'].min()
            max_date = df['Scanned_on'].max()
            # Provide a fallback date if min_date or max_date is None
            default_start_date = min_date if pd.notnull(min_date) else datetime.today().date()
            default_end_date = max_date if pd.notnull(max_date) else datetime.today().date()
            selected_date_range = st.date_input("Select Date or Date Range", [default_start_date, default_end_date], min_value=min_date, max_value=max_date)
            
            # Check if only one date is selected or two dates are selected
            if len(selected_date_range) == 1:
                start_date = selected_date_range[0]
                end_date = None
            elif len(selected_date_range) == 2:
                start_date, end_date = selected_date_range
            else:
                st.error("Please select a valid date or date range.")

            # Include tax selection
            include_tax = st.checkbox("Include Tax", value=True)

        # Filter data based on the selected date(s)
        df_filtered = filter_by_date_range(df, start_date, end_date)

        # Calculate total amounts
        subtotal = df_filtered['subtotal'].sum()
        total_amount = df_filtered['total_amount'].sum() if include_tax else subtotal

        # Display the metrics
        st.subheader(f"Bills for Date: {start_date}" if not end_date else f"Bills from {start_date} to {end_date}")
        st.metric("Total Subtotal (Excluding Tax)", f"${subtotal:,.2f}")
        st.metric("Total Amount (Including Tax)" if include_tax else "Total Amount", f"${total_amount:,.2f}")

        # Expand to show additional relevant details
        with st.expander("See Bill Details"):
            st.dataframe(df_filtered[['company_name', 'address', 'subtotal', 'total_amount', 'category']])

        # Display the filtered data for the selected date(s)
        with st.expander("See Raw Data"):
            st.dataframe(df_filtered)

# Upload Bill Page
elif page == "Upload Bill":
    st.header("Upload a New Bill")
    st.write("""
    Upload your receipts here to store them in the ReceiptHub database. Select a category for each receipt to
    organize your expenses, making it easy to analyze and review on your dashboard.
    """)

    # File uploader for bill file
    uploaded_file = st.file_uploader("Choose a bill file", type=["pdf", "jpeg", "jpg", "png"])

    # Dropdown for selecting the bill category
    category = st.selectbox("Select Bill Category", ["Office Supplies & Stationery", "Meals & Entertainment", "Travel & Transportation", "Utilities & Internet", "Miscellaneous"])

    # Button to submit the file
    if st.button("Upload and Analyze"):
        if uploaded_file is not None and category:
            # Prepare file and data payload for POST request
            files = {"bill": (uploaded_file.name, uploaded_file, uploaded_file.type)}
            data = {"category": category}

            # Send POST request to Flask backend
            response = requests.post("http://127.0.0.1:5000/upload-bill", files=files, data=data)

            # Handle response from Flask backend
            if response.status_code == 200:
                result = response.json()
                st.success(result.get("message", "Bill uploaded successfully!"))
            else:
                st.error("Error uploading bill.")
                st.write(response.text)
        else:
            st.error("Please upload a file and select a category.")
