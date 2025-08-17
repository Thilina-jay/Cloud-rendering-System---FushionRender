import paramiko
import json
import time

VMS_JSON_PATH = "vms.json"

def load_vm_details():
    try:
        with open(VMS_JSON_PATH, "r") as file:
            return json.load(file)
    except Exception:
        return []

def clear_files_on_vm(vm):
    """Clear the files on the VM after rendering is complete."""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = paramiko.RSAKey.from_private_key_file(vm['key_path'])
        ssh.connect(vm['ip'], username=vm['user'], pkey=private_key)

        # Clear files on the VM 
        clear_command = (
            f"find /home/{vm['user']}/uploads/output/ -type f -delete && find /home/{vm['user']}/uploads/ -type f -delete"
        )
        ssh.exec_command(clear_command)
        ssh.close()
        return f"VM {vm['ip']}: Files cleared."
    except Exception as e:
        return f"VM {vm['ip']}: Error clearing files - {str(e)}"

def transmerge_files(uploaded_file):
    results = []

    #  Always get latest VMs
    vm_details = load_vm_details()

    # Transfer Part 
    for vm in vm_details:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            private_key = paramiko.RSAKey.from_private_key_file(vm['key_path'])
            ssh.connect(vm['ip'], username=vm['user'], pkey=private_key)

            # Kill existing servers on port 8000
            ssh.exec_command("sudo lsof -i :8000 | awk '{print $2}' | tail -n +2 | xargs -r sudo kill")

            # Start a Python HTTP server in the output folder
            ssh.exec_command(f"cd /home/{vm['user']}/uploads/output && nohup python3 -m http.server 8000 --bind 0.0.0.0 &")
            time.sleep(2)
            results.append(f"VM {vm['ip']}: HTTP server started on port 8000.")
            ssh.close()

        except Exception as e:
            results.append(f"VM {vm['ip']}: Failed to start HTTP server - {str(e)}")
            continue

    try:
        # Connect to merging instance
        merging_instance_ip = "34.61.133.53"
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = paramiko.RSAKey.from_private_key_file(r'C:\\Users\\thili\\.ssh\\google-cloud-key')
        ssh.connect(merging_instance_ip, username="thilinajayaweera2000", pkey=private_key)

        # Cleanup on merging instance before transfer
        ssh.exec_command("find /home/thilinajayaweera2000/uploads/output/ -type f -delete && find /home/thilinajayaweera2000/uploads/ -type f -delete")
        ssh.exec_command("mkdir -p /home/thilinajayaweera2000/uploads")

        # Download rendered .mkv files from each VM
        for vm in vm_details:
            try:
                http_server_url = f"http://{vm['ip']}:8000"
                curl_command = (
                    f"curl -s {http_server_url} | grep -oP '(?<=href=\")[^\">]+' | grep -v '/' | grep -v '\\.log' | "
                    f"xargs -I {{}} curl -O {http_server_url}/{{}}"
                )
                ssh.exec_command(f"cd /home/thilinajayaweera2000/uploads && {curl_command}")
                results.append(f"Successfully retrieved files from {http_server_url}")
            except Exception as e:
                results.append(f"Error retrieving from {vm['ip']}: {str(e)}")

        # Merge with ffmpeg
        uploads_dir = "/home/thilinajayaweera2000/uploads"
        file_list_path = f"{uploads_dir}/file_list.txt"

        generate_list_command = (
            f"cd {uploads_dir} && ls -v *.mkv | awk '{{print \"file \\047\"$(realpath $0)\"\\047\"}}' > {file_list_path}"
        )
        ssh.exec_command(generate_list_command)

        validate_command = f"test -s {file_list_path} && echo 'OK' || echo 'EMPTY'"
        stdin, stdout, stderr = ssh.exec_command(validate_command)
        if stdout.read().decode().strip() == "EMPTY":
            results.append("Error: No valid files for merging.")
            raise Exception("file_list.txt is empty.")

        merge_command = f"ffmpeg -f concat -safe 0 -i {file_list_path} -c copy {uploads_dir}/output/combined_output.mkv"
        stdin, stdout, stderr = ssh.exec_command(merge_command)
        exit_status = stdout.channel.recv_exit_status()

        if exit_status == 0:
            results.append("Files successfully merged into combined_output.mkv")
        else:
            results.append("Merging failed.")
    except Exception as e:
        results.append(f"Merging instance error: {str(e)}")
    finally:
        ssh.close()

    # Clear files on all VMs (permanent and temporary) after the merging process
    for vm in vm_details:
        clear_result = clear_files_on_vm(vm)
        results.append(clear_result)

    return results


