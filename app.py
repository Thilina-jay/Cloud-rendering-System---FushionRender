from flask import Flask, request, jsonify, render_template, Response, send_file
import os
import json
import subprocess
import paramiko
import threading  
import time  
from werkzeug.utils import secure_filename
from transmerge import transmerge_files  
from start import start_temp_vms
from flask import session, redirect, url_for, request, render_template, Response, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from flask import make_response, redirect, url_for, session

def load_vm_details():
    try:
        with open('vms.json', 'r') as file:
            vm_details = json.load(file)
        return vm_details
    except FileNotFoundError:
        return []  # If the file doesn't exist, return an empty list

app = Flask(__name__)

app.secret_key = 'Thilina'  #Encryption  key 
ALLOWED_ROUTES = ['login', 'signup', 'static']

UPLOAD_FOLDER = './uploads'
ALLOWED_EXTENSIONS = {'blend'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# VM details 
VM_DETAILS = load_vm_details()


# VM details for downloading merged file
DOWNLOAD_VM_DETAILS = {
    'ip': '34.61.133.53',
    'user': 'thilinajayaweera2000',
    'key_path': r'C:\\Users\\thili\\.ssh\\google-cloud-key',
    'file_path': '/home/thilinajayaweera2000/uploads/output/combined_output.mkv'
}

uploaded_file = None
total_frames = 0  # Global variable for total frames
render_status = {}  # Dictionary to track rendering progress

@app.after_request
def add_no_cache_headers(response):
    """Add cache control headers to disable caching for every request"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response



@app.before_request
def require_login():
    """Force login check before each request"""
    # List of allowed routes 
    allowed_routes = ['login', 'signup', 'remove_user', 'static']
    
    # Force session check
    if 'username' not in session and request.endpoint not in allowed_routes:
        return redirect(url_for('login'))  # Redirect to login page



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clear_remote_directories(vm):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = paramiko.RSAKey.from_private_key_file(vm['key_path'])
        ssh.connect(vm['ip'], username=vm['user'], pkey=private_key)

        # Command to delete files 
        clear_command = (
            f"find /home/{vm['user']}/uploads/output/ -type f -delete && find /home/{vm['user']}/uploads/ -type f -delete"
        )
        ssh.exec_command(clear_command)
        ssh.close()
        return f"VM {vm['ip']}: Directories cleared."
    except Exception as e:
        return f"VM {vm['ip']}: Error clearing directories - {str(e)}"

def upload_to_vm(file_path, vm):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = paramiko.RSAKey.from_private_key_file(vm['key_path'])
        ssh.connect(vm['ip'], username=vm['user'], pkey=private_key)

        scp = ssh.open_sftp()
        remote_path = f"/home/{vm['user']}/uploads/{os.path.basename(file_path)}"
        scp.put(file_path, remote_path)
        scp.close()
        ssh.close()

        return f"VM {vm['ip']}: {os.path.basename(file_path)} uploaded."
    except Exception as e:
        return f"VM {vm['ip']}: Connection error - {str(e)}"

def render_vm(vm, start_frame, end_frame, engine='BLENDER_EEVEE'):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = paramiko.RSAKey.from_private_key_file(vm['key_path'])
        ssh.connect(vm['ip'], username=vm['user'], pkey=private_key)

        remote_file_path = f"/home/{vm['user']}/uploads/{os.path.basename(uploaded_file)}"
        sftp = ssh.open_sftp()
        try:
            sftp.stat(remote_file_path)
        except FileNotFoundError:
            ssh.close()
            return f"VM {vm['ip']}: File not found"
        sftp.close()

        setup_command = "Xvfb :99 -screen 0 1024x768x24 & export DISPLAY=:99"
        ssh.exec_command(setup_command)

        render_command = (
            f"export DISPLAY=:99 && blender -b {remote_file_path} "
            f"--python-expr \"import bpy; bpy.context.scene.render.engine = '{engine}'\" "
            f"-s {start_frame} -e {end_frame} "
            f"-o /home/{vm['user']}/uploads/output/{os.path.splitext(os.path.basename(uploaded_file))[0]}_{start_frame}_{end_frame}.mkv "
            f"-a --noaudio"
        )
        stdin, stdout, stderr = ssh.exec_command(render_command)
        stdout.channel.recv_exit_status()  # Wait for rendering to finish

        # Create log file after rendering completes
        log_command = (
    f"echo 'Render Complete using {engine}' > "
    f"/home/{vm['user']}/uploads/output/"
    f"{os.path.splitext(os.path.basename(uploaded_file))[0]}_{start_frame}_{end_frame}.log"
)

        ssh.exec_command(log_command)

        render_status[vm['ip']] = f"Rendering frames {start_frame}-{end_frame} on {vm['ip']}..."

        ssh.close()
        return f"VM {vm['ip']}: Rendering started."
    except Exception as e:
        render_status[vm['ip']] = f"Error: {str(e)}"
        return f"VM {vm['ip']}: Rendering failed."

def check_render_status(vm, start_frame, end_frame):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = paramiko.RSAKey.from_private_key_file(vm['key_path'])
        ssh.connect(vm['ip'], username=vm['user'], pkey=private_key)

        log_file = f"/home/{vm['user']}/uploads/output/{os.path.splitext(os.path.basename(uploaded_file))[0]}_{start_frame}_{end_frame}.log"
        sftp = ssh.open_sftp()
        try:
            sftp.stat(log_file)  # Check if the log file exists
            sftp.close()
            ssh.close()
            return True
        except FileNotFoundError:
            sftp.close()
            ssh.close()
            return False
    except Exception as e:
        return False

def download_file_from_vm():
    """Download file from the Google Cloud VM using SSH"""
    local_file = os.path.join('./downloads', os.path.basename(DOWNLOAD_VM_DETAILS['file_path']))
    os.makedirs('./downloads', exist_ok=True)  # Ensure the downloads folder exists

    # Set up SSH client
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # Connect to the VM
        ssh.connect(DOWNLOAD_VM_DETAILS['ip'], username=DOWNLOAD_VM_DETAILS['user'], key_filename=DOWNLOAD_VM_DETAILS['key_path'])

        # Use SFTP to download the file
        sftp = ssh.open_sftp()
        sftp.get(DOWNLOAD_VM_DETAILS['file_path'], local_file)
        sftp.close()
        ssh.close()

        return local_file
    except Exception as e:
        ssh.close()
        raise e
    
def clear_merging_instance_files():
    merging_instance = {
        "ip": "34.61.133.53",  #Merging instance IP
        "user": "thilinajayaweera2000",
        "key_path": r"C:\\Users\\thili\\.ssh\\google-cloud-key"
    }
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = paramiko.RSAKey.from_private_key_file(merging_instance['key_path'])
        ssh.connect(merging_instance['ip'], username=merging_instance['user'], pkey=private_key)

        clear_command = (
            f"find /home/{merging_instance['user']}/uploads/output/ -type f -delete && find /home/{merging_instance['user']}/uploads/ -type f -delete"
        )
        ssh.exec_command(clear_command)
        ssh.close()
        return True, "Merging instance files cleared."
    except Exception as e:
        return False, f"Error clearing merging instance files: {str(e)}"
    

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page route"""
    response = make_response(render_template('login.html', error=None))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            with open('users.json', 'r') as file:
                users = json.load(file)
        except FileNotFoundError:
            users = []

        # Check if credentials match
        for user in users:
            if user['username'] == username and check_password_hash(user['password'], password):
                session['username'] = username  
                return redirect('/')  
        
        return render_template('login.html', error='Invalid username or password')  

    return response

@app.route('/remove_user', methods=['GET', 'POST'])
def remove_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not os.path.exists('users.json'):
            return render_template('removeuser.html', error="User database not found.")

        with open('users.json', 'r') as f:
            users = json.load(f)

        for i, user in enumerate(users):
            if user['username'] == username and check_password_hash(user['password'], password):
                users.pop(i)
                with open('users.json', 'w') as f:
                    json.dump(users, f, indent=4)
                return render_template('removeuser.html', message="Account removed successfully.")

        return render_template('removeuser.html', error="Invalid username or password.")

    return render_template('removeuser.html')



@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check if the passwords match
        if password != confirm_password:
            return render_template('signup.html', error='Passwords do not match')

        try:
            with open('users.json', 'r') as file:
                users = json.load(file)
        except FileNotFoundError:
            users = []

        
        if any(user['username'] == username for user in users):
            return render_template('signup.html', error='Username already exists')
        
        # Hash the password and save the new user
        hashed_pw = generate_password_hash(password)
        users.append({'username': username, 'password': hashed_pw})

        
        with open('users.json', 'w') as file:
            json.dump(users, file, indent=4)

        
        session['username'] = username
        return redirect('/')

    return render_template('signup.html', error=None)


@app.route('/start_vms', methods=['POST'])
def handle_start_vms():
    try:
        data = request.get_json()
        total_frames = int(data.get("frames"))
        result = start_temp_vms(total_frames)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    global uploaded_file, total_frames

    # Reload the latest VM details at upload time
    vm_details = load_vm_details()

    if 'file' not in request.files or 'total_frames' not in request.form:
        return jsonify({'error': 'No file or total frames provided'}), 400

    file = request.files['file']
    total_frames = int(request.form['total_frames'])

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        uploaded_file = filepath

        # Clear output folders on all VMs
        clear_results = [clear_remote_directories(vm) for vm in vm_details]

        # Upload to all VMs
        upload_results = [upload_to_vm(uploaded_file, vm) for vm in vm_details]

        return jsonify({'details': clear_results + upload_results})

    return jsonify({'error': 'Invalid file format'}), 400


@app.route('/render', methods=['POST'])
def render():
    global uploaded_file, total_frames

    if not uploaded_file:
        return jsonify({'error': 'No file uploaded to render'}), 400

    if not total_frames:
        return jsonify({'error': 'Total frames not set'}), 400

    data = request.get_json()
    render_engine = data.get('engine', 'BLENDER_EEVEE')  # Default to Eevee

    vm_details = load_vm_details()
    num_vms = len(vm_details)
    frames_per_vm = total_frames // num_vms

    threads = []
    for idx, vm in enumerate(vm_details):
        start_frame = idx * frames_per_vm + 1
        end_frame = (idx + 1) * frames_per_vm if idx < num_vms - 1 else total_frames

        thread = threading.Thread(target=render_vm, args=(vm, start_frame, end_frame, render_engine))
        threads.append(thread)
        thread.start()

    return jsonify({'details': 'Rendering started on all VMs'})



@app.route('/status', methods=['GET'])
def status():
    def generate():
        while True:
            status_update = "\n".join([f"{ip}: {status}" for ip, status in render_status.items()])
            yield f"data: {status_update}\n\n"
            time.sleep(2)
    return Response(generate(), mimetype='text/event-stream')

@app.route('/check_complete', methods=['GET'])
def check_complete():
    global total_frames

    #Load updated VM list
    vm_details = load_vm_details()
    num_vms = len(vm_details)
    frames_per_vm = total_frames // num_vms

    all_render_complete = all(
        check_render_status(vm, idx * frames_per_vm + 1,
                            (idx + 1) * frames_per_vm if idx < num_vms - 1 else total_frames)
        for idx, vm in enumerate(vm_details)
    )

    if all_render_complete:
        return jsonify({'details': 'Rendering successfully completed.'})
    else:
        return jsonify({'details': 'Rendering still in progress.'})


@app.route('/transfer_and_merge', methods=['POST'])
def transfer_and_merge():
    global uploaded_file
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded to transfer and merge'}), 400

    try:
        results = transmerge_files(uploaded_file)

        return jsonify({'details': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download_file_only', methods=['GET'])
def download_file_only():
    try:
        local_file = download_file_from_vm()
        return send_file(local_file, as_attachment=True)
    except Exception as e:
        return jsonify({"error": f"An error occurred while downloading: {str(e)}"}), 500


@app.route('/stop_temp_vms', methods=['POST'])
def stop_temp_vms():
    try:
        TEMP_VM_NAMES = ["temp-render-node-1", "temp-render-node-2"]
        TEMP_VM_ZONE_MAP = {
            "temp-render-node-1": "us-central1-a",
            "temp-render-node-2": "us-east1-d"
        }

        for vm_name in TEMP_VM_NAMES:
            zone = TEMP_VM_ZONE_MAP.get(vm_name)
            if zone:
                subprocess.run(
                    f"gcloud compute instances stop {vm_name} --zone={zone}",
                    shell=True
                )

        # Reset vms.json to only include always-running VMs
        always_running = [
            {
                "ip": "34.72.97.37",
                "user": "thilinajayaweera2000",
                "key_path": "C:\\Users\\thili\\.ssh\\google-cloud-key",
                "status": 0
            },
            {
                "ip": "34.72.69.122",
                "user": "thilinajayaweera2000",
                "key_path": "C:\\Users\\thili\\.ssh\\google-cloud-key",
                "status": 0
            }
        ]

        with open("vms.json", "w") as f:
            json.dump(always_running, f, indent=4)

        return jsonify({"message": "Temporary VMs stopped successfully."})
    except Exception as e:
        return jsonify({"error": f"Failed to stop VMs: {str(e)}"}), 500
    


@app.route('/clear_merging_instance', methods=['POST'])
def clear_merging_instance_route():
    success, message = clear_merging_instance_files()
    if success:
        return jsonify({"message": message})
    else:
        return jsonify({"message": message}), 500
@app.route('/')
def index():
    """Main page that is only accessible after login."""
    if 'username' not in session:
        return redirect(url_for('login'))  # Explicitly redirect to login if not logged in
    return render_template('index.html') 


from flask import make_response



@app.route('/logout')
def logout():
    """Logout the user by clearing the session."""
    session.pop('username', None) 

    
    response = make_response(redirect(url_for('login')))
    
    # Add Cache-Control headers to prevent caching
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response


if __name__ == '__main__':
    app.run(debug=True)
