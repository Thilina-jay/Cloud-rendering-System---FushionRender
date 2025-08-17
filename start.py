import subprocess
import json
import time

# Mapping each temp VM to zone
VM_ZONE_MAP = {
    "temp-render-node-1": "us-central1-a",
    "temp-render-node-2": "us-east1-d"
}

VMS_JSON_PATH = "vms.json"
ALWAYS_RUNNING_VM_COUNT = 2
FRAMES_PER_VM = 5 #frames per vm

def start_temp_vms(total_frames):
    try:
        total_required_vms = (total_frames + FRAMES_PER_VM - 1) // FRAMES_PER_VM
        temp_vms_needed = max(0, total_required_vms - ALWAYS_RUNNING_VM_COUNT)

        started_vms = []

        for i in range(temp_vms_needed):
            instance_name = f"temp-render-node-{i + 1}"

            # Get zone for instance
            zone = VM_ZONE_MAP.get(instance_name)
            if not zone:
                started_vms.append(f"{instance_name}: Zone not defined.")
                continue

            # Start the VM
            subprocess.run(
                f"gcloud compute instances start {instance_name} --zone={zone}",
                shell=True, check=True
            )

            time.sleep(5)  # Allow VM to boot

            # Get the external IP
            external_ip = subprocess.check_output(
                f"gcloud compute instances describe {instance_name} "
                f"--zone={zone} --format=\"get(networkInterfaces[0].accessConfigs[0].natIP)\"",
                shell=True
            ).decode().strip()

            # Create VM record
            new_vm = {
                "ip": external_ip,
                "user": "thilinajayaweera2000",
                "key_path": "C:\\Users\\thili\\.ssh\\google-cloud-key",
                "status": 0
            }

            # Load current vms.json
            try:
                with open(VMS_JSON_PATH, "r") as f:
                    vms_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                vms_data = []

            # Add new VM and save
            vms_data.append(new_vm)
            with open(VMS_JSON_PATH, "w") as f:
                json.dump(vms_data, f, indent=4)

            started_vms.append(f"{instance_name} started in {zone} - IP: {external_ip}")

        return {"status": "success", "started_vms": started_vms}

    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": f"Command failed: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
