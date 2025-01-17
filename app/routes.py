# routes.py
from flask import request, jsonify, current_app
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from app import app, db, CORS
from app.models import Project, LogFile, FilteredFile
import json
import os
import datetime
import threading
import hashlib
from .processing import process_file

def allowed_log_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'txt', 'csv', 'json', 'log'}

def background_processing(log_file_id, filters):
    with app.app_context():
        log_file = LogFile.query.get(log_file_id)
        if log_file:
            original_filepath = log_file.file_path
            print(f"background_processing: org_path={original_filepath}")
            processed_filepath = process_file(original_filepath, filters)  # Process the file
            checksum = calculate_checksum(processed_filepath)
            processed_time = datetime.datetime.now()
                
            # Save processed file metadata to the database
            filtered_file = FilteredFile(
                log_file_id=log_file_id,
                filtered_file_name=os.path.basename(processed_filepath),
                filtered_file_path=processed_filepath,
                checksum=checksum,
                processed_time=processed_time
            )
            db.session.add(filtered_file)
            db.session.commit()

def calculate_checksum(file_path):
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def ensure_upload_directory_exists():
    # base directory where uploaded files will be saved
    # for each project we create a subdirectory projectName and a symlink projectId -> projectName
    # in that subdirectory, we create a directory 'logs' that will contain log files
    if not os.path.exists(current_app.config['UPLOAD_DIRECTORY']):
        os.makedirs(current_app.config['UPLOAD_DIRECTORY'])

@app.route('/projects', methods=['GET'])
def get_projects():
    projects = Project.query.all()
    return jsonify([{'id': project.id, 'name': project.name} for project in projects])

@app.route('/projects', methods=['POST'])
def create_project():
    data = request.json
    if 'name' not in data or data['name'] == '':
        return jsonify({'error': 'Invalid project name'}), 400
    new_project = Project(name=data['name'])
    db.session.add(new_project)
    db.session.commit()
    return jsonify({'id': new_project.id, 'name': new_project.name}), 201

@app.route('/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    project = Project.query.get(project_id)
    if project is None:
        return jsonify({'error': 'Project not found'}), 404
    db.session.delete(project)
    db.session.commit()
    return jsonify({'message': 'Project deleted successfully'}), 200

@app.route('/upload/<string:project_name>', methods=['POST'])
def upload_files(project_name):
    #files = request.files.getlist('files')
    #file_names = [secure_filename(file.filename) for file in files if file]
    #filters = request.form.get('filters')
    #project_name = project_name
    #response_data = {
    #    'files': file_names,
    #    'filters': filters,
    #    'project_name': project_name
    #}
    #return jsonify(response_data)

    if 'files' not in request.files:
        return jsonify({"error": "No files part in the request"}), 400

    project_id = request.form.get('projectId')
    if not project_id:
        return jsonify({"error": "No project Id provided"}), 400

    # check if the project exists
    project = Project.query.filter_by(name=project_name).first()
    if not project:
       # create a new project if it does not exist
       project = Project(name=project_name)
       db.session.add(project)
       db.session.commit()

    sec_project_name = f"{secure_filename(project_name)}_{project_id}"
    project_dir = os.path.join(current_app.config['UPLOAD_DIRECTORY'], sec_project_name, 'raw_logs')
    os.makedirs(project_dir, exist_ok=True)

    filters_json = request.form.get('filters')  # Specify the filters (regular expressions)
    filters = json.loads(filters_json) if filters_json else []

    files = request.files.getlist('files')
    for file in files:
        if file.filename == '':
            return jsonify({'error': 'Filename empty or no selected file'}), 400

        sec_file_name = secure_filename(file.filename)
        if file and allowed_log_file(sec_file_name):
            # save raw file
            raw_file_path = os.path.join(project_dir, sec_file_name)
            file.save(raw_file_path)

            checksum = calculate_checksum(raw_file_path)
            processed_time = datetime.datetime.now()

            # save file info to database
            log_file = LogFile(
                project_id = project.id,
                file_name = sec_file_name,
                file_path = raw_file_path,
                checksum = checksum,
                processed_time = processed_time,
            )
            db.session.add(log_file)
            db.session.commit()

            # trigger background processing
            threading.Thread(target=background_processing, args=(log_file.id, filters)).start()

    # TODO provide detailed status, e.g., some files may not have been uploaded
    return jsonify({"message": "Files uploaded successfully"})

@app.route('/projects/<string:project_name>/rawlogfiles', methods=['GET'])
def get_project_rawlogfiles(project_name):
    project = Project.query.filter_by(name=project_name).first()
    if not project:
        return jsonify({"error": "Project not found"}), 404

    log_files = LogFile.query.filter_by(project_id=project.id).all()

    files_data = [{"id": file.id, "file_name": file.file_name} for file in log_files]

    return jsonify({"project_name": project_name, "log_files": files_data})

@app.route('/projects/<string:project_name>/processedlogfiles', methods=['GET'])
def get_project_processed_logfiles(project_name):
    project = Project.query.filter_by(name=project_name).first()
    if not project:
        return jsonify({"error": "Project not found"}), 404

    log_files = LogFile.query.filter_by(project_id=project.id).all()

    files_data = [{"id": file.id, "file_name": file.file_name} for file in log_files]

    return jsonify({"project_name": project_name, "log_files": files_data})

@app.route('/projects/<int:project_id>/<int:file_id>', methods=['DELETE'])
def delete_log_file(project_id, file_id):
    #project = Project.query.get(project_id)
    #if project is None:
    #    return jsonify({'error': 'Project not found'}), 404
    query = LogFile.query
    query = query.filter(LogFile.project_id == project_id)
    query = query.filter(LogFile.id == file_id)
    log_files = query.all()

    for file in log_files:
      db.session.delete(file)
      db.session.commit()
      # unlink file.file_path
      if os.path.isfile(file.file_path):
        os.remove(file.file_path)

    return jsonify({'message': 'Log file(s) deleted successfully'}), 200
