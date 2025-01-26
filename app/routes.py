# routes.py
from flask import request, jsonify, current_app
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from app import app, db, CORS
from app.models import Project, LogFile, FilteredFile, View, Data
import json
import os
import re
import datetime
import threading
import hashlib
from .processing import process_file

def is_open_call(line):
    decoded_line = line.decode('utf-8')
    row = re.split(r'\s+', decoded_line)
    if re.search('^(open|openat|open64|fopen|fopenat|fopen64|freopen)$', row[12]):
        return True
    return False

def get_program_name(line):
    decoded_line = line.decode('utf-8')
    row = re.split(r'\s+', decoded_line)
    return row[8]

def get_file_name(line):
    decoded_line = line.decode('utf-8')
    row = re.split(r'\s+', decoded_line)
    if re.search('^(open|open64|fopen|fopen64|freopen)$', row[12]):
        return row[13]
    if re.search('^(openat|fopenat)$', row[12]):
        return row[14]
    else:
        return 'NONE'

def get_access_mode(line):
    decoded_line = line.decode('utf-8')
    row = re.split(r'\s+', decoded_line)
    if re.search('^(open|open64|fopen|fopen64|freopen)$', row[12]):
        raw_access_mode = row[14]
    elif re.search('^(openat|fopenat)$', row[12]):
        raw_access_mode = row[15]
    else:
        return 'UNKNOWN'
    if re.search('^(open|open64|openat)$', row[12]):
        # raw_access_mode contains 'O_RDWR' -> return 'write'
        if 'O_RDWR' in raw_access_mode:
            return 'write'
        # raw_access_mode contains 'O_RDONLY' -> return 'read'
        if 'O_RDONLY' in raw_access_mode:
            return 'read'
    elif re.search('^(fopen|fopen64|fopenat|freopen)$', row[12]):
        # raw_access_mode contains 'w' -> return 'write'
        if 'w' in raw_access_mode:
            return 'write'
        # raw_access_mode contains 'r' -> return 'read'
        if 'r' in raw_access_mode:
            return 'read'

    return 'UNKNOWN'

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

@app.route('/dataflow/<int:project_id>', methods=['GET'])
def get_dataflow(project_id):
    project = Project.query.get(project_id)
    if project is None:
        return jsonify({'error': 'Project not found'}), 404
    print(f'project name: {project.name}')

    # get processed log files if any
    nodes = []
    edges = []
    edge_counter = 1
    node_counter = 1
    raw_log_files = LogFile.query.filter_by(project_id=project.id).all()
    print(f'number of raw log files: {len(raw_log_files)}')
    files = {}
    read_ops = {}
    write_ops = {}
    for index, raw_log in enumerate(raw_log_files):
        print(f'processing log file #{index+1}: {raw_log.file_name}')
        processed_log_file = FilteredFile.query.filter_by(log_file_id=raw_log.id).first()

        # for each log file line determine the program, filepath and access mode
        file_path = processed_log_file.filtered_file_path
        programs = {}
        with open(file_path, 'rb') as file:
            for line in file:
                # check that call is one of open{64,at} or fopen{64,at}
                if not is_open_call(line):
                    continue

                access_mode = get_access_mode(line)
                print(f'access_mode: "{access_mode}"')

                program_name_in_log = f'log-{index}##{get_program_name(line)}'
                if program_name_in_log not in programs:
                    # if program new create a new program node
                    programs[program_name_in_log] = node_counter
                    #nodes.append({ 'id': f'{node_counter}', 'label': program_name_in_log, 'type': 'program', 'position': { 'x': 0, 'y': 0 }, 'data': { 'status': 'null' } })
                    nodes.append({ 'id': f'{node_counter}', 'label': program_name_in_log, 'type': 'program', 'data': { 'status': 'null' } })
                    node_counter = node_counter + 1

                # file_path_in_log = f'log-{index}##{get_file_name(line)}'
                # for files we should not use the prefix 'log-{index}##' or the graph cannot be connected
                file_path_in_log = f'{get_file_name(line)}'
                print(f'file_path_in_log: "{file_path_in_log}"')
                if file_path_in_log not in files:
                    # if file new create a new file node
                    files[file_path_in_log] = node_counter
                    #nodes.append({ 'id': f'{node_counter}', 'label': file_path_in_log, 'type': 'file', 'position': { 'x': 0, 'y': 0 }, 'data': { 'status': 'null' } })
                    nodes.append({ 'id': f'{node_counter}', 'label': file_path_in_log, 'type': 'file', 'data': { 'status': 'null' } })
                    node_counter = node_counter + 1

                # TODO handle case that file was accessed already, but with different access mode;
                #      that is add a node? no, just a reverse edge --> probably hard to make clear
                #        in visualisation, need some better way (no arrow, other color, ...), thus need to pass back some extra information to frontend
                if access_mode == 'read':
                    # if access == read, create an edge from the file to the program node
                    # we assume that each log only represents a single program that would read the file
                    if file_path_in_log not in read_ops:
                        read_ops[file_path_in_log] = edge_counter
                        edges.append({ 'id': f'ed{edge_counter}', 'source': files[file_path_in_log], 'target': programs[program_name_in_log] })
                        edge_counter = edge_counter + 1

                if access_mode == 'write':
                    # TODO FIXME if file is openend for both reading and writing create another node for the file and use that as target
                    #            however that may need that we distinguish the operation in the file_path_in_log, but then this complicates
                    #            the matching of files between programs
                    # if access == write, create an edge from the program to the file node
                    # we assume that each log only represents a single program that would write the file
                    if file_path_in_log not in write_ops:
                        write_ops[file_path_in_log] = edge_counter
                        edges.append({ 'id': f'ed{edge_counter}', 'source': programs[program_name_in_log], 'target': files[file_path_in_log] })
                        edge_counter = edge_counter + 1

    # return both arrays: nodes and edges
    print(f'nodes: {nodes}')
    print(f'edges: {edges}')
    return jsonify({'nodes': nodes, 'edges': edges}), 200

@app.route('/projects', methods=['GET'])
def get_projects():
    projects = Project.query.all()
    return jsonify([{'id': project.id, 'name': project.name} for project in projects]), 200

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

# routes for table View
@app.route('/views', methods=['GET'])
def get_views():
    views = View.query.all()
    return jsonify([{'id': view.id, 'name': view.name} for view in views]), 200

@app.route('/views', methods=['POST'])
def create_view():
    data = request.json
    if 'name' not in data or data['name'] == '':
        return jsonify({'error': 'Invalid view name'}), 400
    new_view = View(name=data['name'])
    db.session.add(new_view)
    db.session.commit()
    return jsonify({'id': new_view.id, 'name': new_view.name}), 201

@app.route('/views/<int:view_id>', methods=['DELETE'])
def delete_view(view_id):
    view = View.query.get(view_id)
    if view is None:
        return jsonify({'error': 'View not found'}), 404
    db.session.delete(view)
    db.session.commit()
    return jsonify({'message': 'View deleted successfully'}), 200
