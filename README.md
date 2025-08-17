# Cloud Rendering System

A web-based distributed rendering system for Blender animations.  
The project automates rendering across Google Cloud VMs, manages file uploads, merges outputs, and provides the final video for download through a browser interface.

## Features

- User login with multi-user support  
- Start and stop temporary render VMs  
- Upload `.blend` files and choose render engine (Eevee or Cycles)  
- Parallel rendering across multiple VMs  
- Automatic transfer and merge of rendered frames using FFmpeg  
- Download final merged video and clear files on the merging instance  

## Tech Stack

- Backend: Flask (Python), Paramiko, subprocess (gcloud)  
- Frontend: HTML, CSS, JavaScript  
- Infrastructure: Google Cloud Compute Engine  
