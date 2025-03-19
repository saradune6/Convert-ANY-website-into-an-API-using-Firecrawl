import streamlit as st
import os
import gc
from firecrawl import FirecrawlApp
from dotenv import load_dotenv
import time
import pandas as pd
import base64
from pydantic import BaseModel
import json

# Load API key
load_dotenv()
firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")

@st.cache_resource
def load_app():
    return FirecrawlApp(api_key=firecrawl_api_key)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "schema_fields" not in st.session_state:
    st.session_state.schema_fields = [{"name": "", "type": "str"}]

def reset_chat():
    st.session_state.messages = []
    gc.collect()

def create_dynamic_model(fields):
    """Create a dynamic Pydantic model from schema fields."""
    field_annotations = {}
    type_mapping = {"str": str, "bool": bool, "int": int, "float": float}

    for field in fields:
        if field["name"]:
            field_annotations[field["name"]] = type_mapping.get(field["type"], str)
    
    return type("ExtractSchema", (BaseModel,), {"__annotations__": field_annotations})

def create_schema_from_fields(fields):
    """Create schema using Pydantic model."""
    if not any(field["name"] for field in fields):
        return None
    return create_dynamic_model(fields).model_json_schema()

def flatten_json(nested_json, parent_key="", sep="_"):
    """Flattens a nested dictionary into a single-level dictionary."""
    items = []
    if isinstance(nested_json, dict):
        for k, v in nested_json.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten_json(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    items.extend(flatten_json(item, f"{new_key}_{i}", sep=sep).items())
            else:
                items.append((new_key, v))
    elif isinstance(nested_json, list):
        return [flatten_json(item, parent_key, sep=sep) for item in nested_json]
    else:
        return nested_json
    return dict(items)

def convert_to_table(data):
    """Convert a list or dictionary to a markdown table."""
    if not data:
        return "No data available."

    try:
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            df = pd.DataFrame([data])
        elif isinstance(data, str):
            return f"Extracted text: {data}"
        else:
            return "Invalid data format received."

        return df.to_markdown(index=False)
    
    except Exception as e:
        return f"Error converting data to table: {str(e)}"

def stream_text(text: str, delay: float = 0.001):
    """Stream text with a typing effect."""
    placeholder = st.empty()
    displayed_text = ""

    for char in text:
        displayed_text += char
        placeholder.markdown(displayed_text)
        time.sleep(delay)
    
    return placeholder

# Main app layout
st.markdown("""
    # Convert ANY website into an API using <img src="data:image/png;base64,{}" width="250" style="vertical-align: -25px;">
""".format(base64.b64encode(open("assets/firecrawl.png", "rb").read()).decode()), unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("Configuration")
    website_url = st.text_input("Enter Website URL", placeholder="https://example.com")

    st.divider()
    st.subheader("Schema Builder (Optional)")
    
    for i, field in enumerate(st.session_state.schema_fields):
        col1, col2 = st.columns([2, 1])
        with col1:
            field["name"] = st.text_input("Field Name", value=field["name"], key=f"name_{i}", placeholder="e.g., company_mission")
        with col2:
            field["type"] = st.selectbox("Type", ["str", "bool", "int", "float"], key=f"type_{i}", index=["str", "bool", "int", "float"].index(field["type"]))

    if len(st.session_state.schema_fields) < 5 and st.button("Add Field ➕"):
        st.session_state.schema_fields.append({"name": "", "type": "str"})

# Chat interface
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about the website..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if not website_url:
            st.error("Please enter a website URL first!")
        else:
            try:
                with st.spinner("Extracting data from website..."):
                    app = load_app()
                    schema = create_schema_from_fields(st.session_state.schema_fields)
                    
                    extract_params = {'prompt': prompt}
                    if schema:
                        extract_params['schema'] = schema

                    data = app.extract([website_url], extract_params)

                    # Debugging output
                    st.write("Raw API Response:", json.dumps(data, indent=2))

                    # Validate API response structure
                    if not isinstance(data, dict) or "data" not in data:
                        st.error("Unexpected API response format. Please check the API key and request.")
                        st.stop()  # Stop execution safely

                    api_data = data.get("data")

                    # Convert extracted data to table format
                    if isinstance(api_data, list):
                        table_data = [flatten_json(item) for item in api_data]
                        table = convert_to_table(table_data)
                    elif isinstance(api_data, dict):
                        table = convert_to_table(flatten_json(api_data))
                    else:
                        table = "Invalid data format."

                    # Stream response
                    placeholder = stream_text(table)
                    st.session_state.messages.append({"role": "assistant", "content": table})

            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

# Footer
st.markdown("---")
st.markdown("Built with Firecrawl and Streamlit")
