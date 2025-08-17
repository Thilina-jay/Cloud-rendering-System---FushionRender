from flask import Flask, send_file, jsonify
import paramiko
import os

app = Flask(__name__)

# Google Cloud VM Details
vm_details = {
    'ip': '34.61.133.53',
    'user': 'thilinajayaweera2000',
    'key_path': r'C:\\Users\\thili\\.ssh\\google-cloud-key',
    'file_path': '/home/thilinajayaweera2000/uploads/output/combined_output.mkv'
}

def download_file_from_vm():
    """Download file from the Google Cloud VM using SSH"""
    local_file = os.path.join('./downloads', os.path.basename(vm_details['file_path']))
    os.makedirs('./downloads', exist_ok=True)  # Ensure the downloads folder exists

    # Set up SSH client
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # Connect to the VM
        ssh.connect(vm_details['ip'], username=vm_details['user'], key_filename=vm_details['key_path'])

        # Use SFTP to download the file
        sftp = ssh.open_sftp()
        sftp.get(vm_details['file_path'], local_file)
        sftp.close()
        ssh.close()

        return local_file
    except Exception as e:
        ssh.close()
        raise e

@app.route('/download', methods=['GET'])
def download():
    try:
        # Download the file from the VM
        local_file = download_file_from_vm()

        # Serve the file for download
        return send_file(local_file, as_attachment=True)
    except Exception as e:
        return jsonify({"error": f"An error occurred while downloading: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)
