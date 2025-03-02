from flask import Flask, request, jsonify, send_file
from flask_cors import CORS  # Import CORS
import json
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/api/upload', methods=['POST'])
def upload_collection():
    """Upload and process a Postman collection file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not file.filename.endswith('.json'):
        return jsonify({'error': 'Only JSON files are allowed'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    try:
        with open(filepath, 'r') as f:
            collection = json.load(f)
            
        # Basic validation
        if 'info' not in collection or 'item' not in collection:
            return jsonify({'error': 'Invalid Postman collection format'}), 400
        
        return jsonify({
            'success': True,
            'filename': filename,
            'collection': collection
        })
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON file'}), 400

@app.route('/api/collection/<filename>', methods=['GET'])
def get_collection(filename):
    """Retrieve a previously uploaded collection"""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    try:
        with open(filepath, 'r') as f:
            collection = json.load(f)
        return jsonify(collection)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/update-collection', methods=['POST'])
def update_collection():
    """Update a collection with modified parameters"""
    data = request.json
    
    if not data or 'filename' not in data or 'collection' not in data:
        return jsonify({'error': 'Missing required data'}), 400
    
    filename = secure_filename(data['filename'])
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    try:
        with open(filepath, 'w') as f:
            json.dump(data['collection'], f, indent=2)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bulk-update', methods=['POST'])
def bulk_update():
    """Apply bulk updates to parameters across all endpoints"""
    data = request.json
    
    if not data or 'filename' not in data or 'updates' not in data:
        return jsonify({'error': 'Missing required data'}), 400
    
    filename = secure_filename(data['filename'])
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    updates = data['updates']
    
    try:
        with open(filepath, 'r') as f:
            collection = json.load(f)
        
        # Process all items recursively
        def process_items(items):
            for item in items:
                if 'request' in item:
                    # Apply updates to this endpoint
                    for update_type, update_data in updates.items():
                        if update_type == 'headers':
                            # Handle header updates
                            if update_data['action'] == 'add':
                                if 'header' not in item['request']:
                                    item['request']['header'] = []
                                
                                # Add header if it doesn't exist
                                header_exists = False
                                for header in item['request']['header']:
                                    if header['key'] == update_data['key']:
                                        header['value'] = update_data['value']
                                        header_exists = True
                                        break
                                
                                if not header_exists:
                                    item['request']['header'].append({
                                        'key': update_data['key'],
                                        'value': update_data['value'],
                                        'type': update_data.get('type', 'text')
                                    })
                            
                            elif update_data['action'] == 'remove':
                                if 'header' in item['request']:
                                    item['request']['header'] = [
                                        h for h in item['request']['header'] 
                                        if h['key'] != update_data['key']
                                    ]
                        
                        elif update_type == 'query_params':
                            # Handle URL query parameter updates
                            if 'url' not in item['request']:
                                continue
                                
                            if isinstance(item['request']['url'], str):
                                # Convert string URL to object format
                                url_parts = item['request']['url'].split('?')
                                item['request']['url'] = {
                                    'raw': item['request']['url'],
                                    'protocol': url_parts[0].split('://')[0] if '://' in url_parts[0] else None,
                                    'host': url_parts[0].split('://')[1].split('/')[0].split('.') if '://' in url_parts[0] else url_parts[0].split('/')[0].split('.'),
                                    'path': url_parts[0].split('://')[1].split('/')[1:] if '://' in url_parts[0] else url_parts[0].split('/')[1:],
                                    'query': []
                                }
                            
                            if 'query' not in item['request']['url']:
                                item['request']['url']['query'] = []
                                
                            if update_data['action'] == 'add':
                                param_exists = False
                                for param in item['request']['url']['query']:
                                    if param['key'] == update_data['key']:
                                        param['value'] = update_data['value']
                                        param_exists = True
                                        break
                                
                                if not param_exists:
                                    item['request']['url']['query'].append({
                                        'key': update_data['key'],
                                        'value': update_data['value']
                                    })
                                
                                # Update raw URL
                                query_part = '&'.join([f"{q['key']}={q['value']}" for q in item['request']['url']['query']])
                                path_part = '/'.join(item['request']['url'].get('path', []))
                                protocol = item['request']['url'].get('protocol', 'http')
                                host_part = '.'.join(item['request']['url'].get('host', []))
                                item['request']['url']['raw'] = f"{protocol}://{host_part}/{path_part}?{query_part}"
                            
                            elif update_data['action'] == 'remove':
                                if 'query' in item['request']['url']:
                                    item['request']['url']['query'] = [
                                        q for q in item['request']['url']['query'] 
                                        if q['key'] != update_data['key']
                                    ]
                
                if 'item' in item:
                    # Process nested items
                    process_items(item['item'])
        
        process_items(collection['item'])
        
        # Save updated collection
        with open(filepath, 'w') as f:
            json.dump(collection, f, indent=2)
        
        return jsonify({
            'success': True,
            'collection': collection
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/<filename>', methods=['GET'])
def export_collection(filename):
    """Export the modified collection file"""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(filepath, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)