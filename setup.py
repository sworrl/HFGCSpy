import os
import subprocess
import sys
import shutil

def install_dependencies():
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'flask', 'requests', 'numpy'])
        print("Dependencies installed successfully.")
    except subprocess.CalledProcessError:
        print("Error installing dependencies.")
        sys.exit(1)

def setup_data_directory():
    data_dir = '/hfgcspy_data'
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Created data directory: {data_dir}")
    else:
        print(f"Data directory already exists: {data_dir}")

def copy_web_ui():
    web_dir = '/var/www/hfgcspy'
    if not os.path.exists(web_dir):
        os.makedirs(web_dir)
    try:
        shutil.copy('index.html', os.path.join(web_dir, 'index.html'))
        print("Web UI copied to /var/www/hfgcspy")
    except FileNotFoundError:
        print("Error: index.html not found in current directory.")
        sys.exit(1)

def start_service():
    try:
        subprocess.check_call(['systemctl', 'start', 'hfgcspy'])
        subprocess.check_call(['systemctl', 'enable', 'hfgcspy'])
        print("HFGCSpy service started and enabled.")
    except subprocess.CalledProcessError:
        print("Error starting HFGCSpy service.")
        sys.exit(1)

def uninstall():
    try:
        subprocess.check_call(['systemctl', 'stop', 'hfgcspy'])
        subprocess.check_call(['systemctl', 'disable', 'hfgcspy'])
        shutil.rmtree('/hfgcspy_data', ignore_errors=True)
        shutil.rmtree('/var/www/hfgcspy', ignore_errors=True)
        print("HFGCSpy uninstalled successfully.")
    except subprocess.CalledProcessError:
        print("Error uninstalling HFGCSpy.")
        sys.exit(1)

if __name__ == '__main__':
    if '--uninstall' in sys.argv:
        uninstall()
    else:
        install_dependencies()
        setup_data_directory()
        copy_web_ui()
        start_service()