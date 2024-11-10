from openai import OpenAI
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import tempfile
import json
import re
from datetime import datetime
from llama_parse import LlamaParse
from llama_index.core import SimpleDirectoryReader
import pandas as pd
from PIL import Image  # Import Pillow for image handling
import shutil  # Import shutil for copying files

# Load environment variables
load_dotenv()

# Initialize NVIDIA API client
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv('NVIDIA_API_KEY')
)

# Flask setup
app = Flask(__name__, template_folder='templates')
CORS(app)

# Define the Excel file path
excel_file_path = 'bills_data.xlsx'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload-bill', methods=['POST'])
def upload_bill():
    try:
        if 'bill' not in request.files:
            return jsonify({'error': 'No bill file provided'}), 400

        file = request.files['bill']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        # Retrieve the category from the form data
        category = request.form.get('category')
        if not category:
            return jsonify({'error': 'No category selected'}), 400

        # Detect MIME type
        mime_type = file.content_type

        # Validate file type (PDF or image)
        if mime_type not in ['application/pdf', 'image/jpeg', 'image/png']:
            return jsonify({'error': 'Unsupported file type. Please upload a PDF, JPEG, or PNG file.'}), 400

        # Save the file temporarily
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_file_path = temp_file.name

        if mime_type == 'application/pdf':
            # If the file is a PDF, save directly
            file.save(temp_file_path)
        else:
            # Convert image (JPEG/PNG) to PDF
            image = Image.open(file)
            image.convert('RGB').save(temp_file_path, 'PDF')


                # Directory to store scanned bills
        scanned_bills_dir = 'scanned_bills'
        os.makedirs(scanned_bills_dir, exist_ok=True)  # Ensure the directory exists

        # Add a unique filename for the stored bill
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        file_extension = os.path.splitext(temp_file_path)[1]
        stored_file_path = os.path.join(scanned_bills_dir, f"bill_{timestamp}{file_extension}")

        # Copy the temp file to the scanned_bills directory
        shutil.copy(temp_file_path, stored_file_path)


        # Set up the parser for extracting data from the PDF
        parser = LlamaParse(result_type="markdown")
        file_extractor = {".pdf": parser}

        # Use SimpleDirectoryReader to parse the temporary PDF file
        documents = SimpleDirectoryReader(input_files=[temp_file_path], file_extractor=file_extractor).load_data()

        if not documents:
            return jsonify({'error': 'Failed to extract content from PDF'}), 500

        # Concatenate the extracted text
        parsed_text = "\n".join([doc.text for doc in documents])

        # Send the extracted text to the NVIDIA API
        completion = client.chat.completions.create(
            model="mistralai/mixtral-8x22b-instruct-v0.1",
            messages=[
                {
                    "role": "user",
                    "content": f"""
                    I have the following extracted markdown text from an invoice. Your task is to analyze the text and return the details in the following JSON format:
                    
                    {{
                        "company_name": "(name of the company)",
                        "address": "(company address)",
                        "subtotal": "(total cost without tax)",
                        "total_amount": "(total cost including tax)"
                    }}

                    Please use the extracted markdown below:

                    {parsed_text}
                    """
                }
            ],
            temperature=0.1,
            top_p=0.7,
            max_tokens=1500,
            stream=False
        )

        # Extract the response content
        raw_response = completion.choices[0].message.content.strip()

        if not raw_response:
            return jsonify({'error': 'Received empty response from NVIDIA'}), 500

        # Extract JSON response from NVIDIA API output
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
        if json_match:
            raw_json = json_match.group(1)
        else:
            return jsonify({'error': 'Failed to extract JSON from the response'}), 500

        try:
            bill_record = json.loads(raw_json)
        except json.JSONDecodeError as e:
            return jsonify({'error': f'JSON decoding failed: {e}'}), 500

        # Add the category and upload date to the bill record
        bill_record["category"] = category
        bill_record["Scanned_on"] = datetime.now().strftime('%Y-%m-%d')


        # Save to Excel
        df = pd.DataFrame([bill_record])

        if os.path.exists(excel_file_path):
            # Load the existing workbook and append new data
            with pd.ExcelWriter(excel_file_path, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
                workbook = writer.book
                sheet = workbook['Bills']
                
                # Determine the starting row for the new data
                start_row = sheet.max_row
                df.to_excel(writer, sheet_name='Bills', index=False, header=False, startrow=start_row)
        else:
            # If the file does not exist, create a new one and add the data
            with pd.ExcelWriter(excel_file_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Bills', index=False)

        # Return response
        return jsonify({
            'message': 'Bill details successfully extracted and stored in Excel.',
            'bill_details': bill_record,
            'raw_response': raw_response
        })

    except Exception as e:
        return jsonify({'error': f'An error occurred: {e}'}), 500

    finally:
        if 'temp_file_path' in locals():
            os.unlink(temp_file_path)

if __name__ == '__main__':
    app.run(debug=True)
