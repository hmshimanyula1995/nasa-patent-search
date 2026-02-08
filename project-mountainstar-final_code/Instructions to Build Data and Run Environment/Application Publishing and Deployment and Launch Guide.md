Application Publishing/Deployment and Launch Guide

This section provides basic instructions and options for deploying the NASA Patent Matching Tool, a Streamlit-based web application that matches patent documents via similarity analysis. The guide is written for non-IT users or basic-level system administrators and includes three deployment options:
  ·	**Option A:** Public temporary URL via Cloudflare Tunnel
  ·	**Option B:** Private/internal use via local IP (Intranet)
  ·	**Option C:** Full-scale production with permanent public URL

The app requires Python 3.8+, Streamlit, and other dependencies. It can be launched on a virtual machine (VM), a physical server, or a cloud environment (e.g., Google Cloud Vertex AI, AWS EC2, Azure VM).
 
**DEPLOYMENT OPTION A:** Temporary Public Access via Cloudflare Tunnel
This is the easiest and fastest way to share the tool publicly for demo/testing with collaborators. No domain name or complex configuration is needed.

**A1. Basic Concept**
You launch the Streamlit app locally on the VM or server and then use Cloudflare Tunnel to expose it to the internet via a temporary HTTPS URL (like https://green-lab-quick.cloudflared.link).


**A2. Where to Run This**
Open a terminal window or SSH into the server/VM where the codebase is located. Ensure you’re inside the project root folder (the one with app.py, streamlit/, and config.toml).

**A3. One-Time Setup Steps (First-Time Only)**
These steps only need to be done once per machine.

1.	Install Python Packages
	o	Run the following in Terminal:
		 python3 -m pip install --upgrade pip
		 pip install streamlit papermill pandas nbformat nbclient Pillow
		 pip install streamlit-autorefresh beautifulsoup4 lxml requests

2.	Install Cloudflare Tunnel (cloudflared)

		sudo apt-get update && sudo apt-get install -y cloudflared
		sudo rm -f /etc/apt/sources.list.d/cloudflared.list
		sudo rm -f /usr/share/keyrings/cloudflare-main.gpg /usr/share/keyrings/cloudflare-public-v2.gpg
  		sudo mkdir -p --mode=0755 /usr/share/keyrings
		curl -fsSL https://pkg.cloudflare.com/cloudflare-public-v2.gpg \
			| sudo tee /usr/share/keyrings/cloudflare-public-v2.gpg >/dev/null
  		echo 'deb [signed-by=/usr/share/keyrings/cloudflare-public-v2.gpg] https://pkg.cloudflare.com/cloudflared any main' \
  			| sudo tee /etc/apt/sources.list.d/cloudflared.list
  		sudo apt-get update
  		sudo apt-get install -y cloudflared
  		cloudflared --version

**A4. If you want to automate it every time you start the machine/instance:**
	Create a script, for example run_app_with_tunnel.sh:
		
		#!/usr/bin/env bash
		set -euo pipefail
		 
		APP_PORT=8501
		APP_HOST=127.0.0.1
		 
		APP_LOG="$HOME/logs/streamlit_app.log"
		TUNNEL_LOG="$HOME/logs/cloudflared.log"
		 
		mkdir -p "$(dirname "$APP_LOG")"
		 
		echo "Stopping any previous Streamlit / tunnel instances..."
		pkill -f "streamlit run app.py" 2>/dev/null || true
		pkill -f "cloudflared tunnel" 2>/dev/null || true
		sudo fuser -k ${APP_PORT}/tcp 2>/dev/null || true
		 
		echo "Setting Streamlit theme and config..."
		export STREAMLIT_THEME_BASE=dark
		export STREAMLIT_CONFIG="$PWD/streamlit/config.toml"
		 
		echo "Starting Streamlit on ${APP_HOST}:${APP_PORT}..."
		streamlit run app.py \
		  --server.port "$APP_PORT" \
		  --server.headless true \
		  --server.address "$APP_HOST" \
		  > "$APP_LOG" 2>&1 &
		 
		APP_PID=$!
		echo "Streamlit PID: $APP_PID"
		 
		# Give Streamlit a few seconds to start listening
		sleep 5
		 
		echo "Starting Cloudflare Tunnel..."
		cloudflared tunnel --url "http://${APP_HOST}:${APP_PORT}" --protocol http2 | tee "$TUNNEL_LOG"
		 
And then:
 
		chmod +x run_app_with_tunnel.sh
		./run_app_with_tunnel.sh
		 
What this does:
	•	Kills any old Streamlit or cloudflared processes on that port.
	•	Sets the dark theme and config env vars.
	•	Starts Streamlit in the background and logs to ~/logs/streamlit_app.log.
	•	Waits a few seconds, then starts cloudflared tunnel in the same terminal, printing the public URL as usual.
	•	When you stop the tunnel with Ctrl+C, the Streamlit process will still be running in the background. If you want it to stop as well, you can add a trap and kill $APP_PID on exit, but often for demos it is fine to leave it running.

If you want Streamlit to stop when you close the terminal, you can wrap the tunnel and Streamlit in a simple trap, for example:
		
		trap 'echo "Stopping app..."; kill $APP_PID 2>/dev/null || true' INT TERM

On a Vertex AI instance, GCE VM, or any Linux server:
	1.	Copy your project folder and this script to the VM.
	2.	Install streamlit, cloudflared, and other Python deps in your environment.
	3.	Run:

		cd /path/to/project
		./run_app_with_tunnel.sh

For basic automation (so it starts on boot, or you do not need to remember the command):
	•	Put the same content into a systemd service or a GCE startup script. For example, on a GCE or standard VM you can set a 	metadata startup script that calls:

		#!/usr/bin/env bash
		cd /path/to/project
		./run_app_with_tunnel.sh

**DEPLOYMENT OPTION B: Private/Internal Access via Intranet**
This allows your organization (e.g., NASA internal users) to access the app via a local IP address (e.g., http://10.1.1.25:8501). Best used when deployed inside a secured NASA network with internal-only access.

**B1. Where to Host**
Use any network-accessible machine (baremetal server, VM, GCE or any cloud instance like Vertex AI) with a static IP. Users on the same network should be able to reach the machine’s IP.

**B2. First-Time Setup**
Follow the same installation steps as A3 and A4 to install Python packages and cloudflared (you don’t need to use Cloudflare in this case, but packages are harmless).

**B3. Launch the App**
		
		pkill -f "streamlit" 2>/dev/null || true
		sudo fuser -k 8501/tcp 2>/dev/null || true
		export STREAMLIT_THEME_BASE=dark
		export STREAMLIT_CONFIG="$PWD/streamlit/config.toml"
		streamlit run app.py --server.port 8501 --server.headless true --server.address 0.0.0.0
		
This tells Streamlit to accept requests from any machine (not just localhost).

Now open a browser and navigate to:
	http://<your-server-ip>:8501
	Example:
	http://10.10.2.55:8501

**B4. Make It Easier to Access (Optional)**
Instead of remembering the IP, you can assign a custom internal domain like:
	http://patents.nasa.local

**B5. Optional Internal DNS or Reverse Proxy (Expanded)**
To configure a friendly internal domain name, your IT Admin can take either of these two approaches:
	·	Option 1: Internal DNS Mapping
		o	On the internal DNS server (e.g., Windows Server DNS or internal BIND):
			Create a DNS A record mapping patents.nasa.local to the server’s static IP.
			Example: patents.nasa.local -> 10.10.2.55
		o	Ensure that internal clients are using the same DNS server.
		o	Then users can open: http://patents.nasa.local:8501
	·	Option 2: Reverse Proxy with SSL (e.g., Apache/Nginx)
		o	Install Apache2 or Nginx on the server (or a separate gateway).
		o	Configure it to listen on port 80 or 443 and proxy traffic to port 8501.
			Example Nginx config:
				server {
				     listen 80;
				     server_name patents.nasa.local;
				 
				    location / {
				         proxy_pass http://127.0.0.1:8501;
				         proxy_set_header Host $host;
				         proxy_set_header X-Real-IP $remote_addr;
				     }
				 }
		·	Reload nginx: sudo systemctl reload nginx
		·	Now the app is available at: http://patents.nasa.local

If desired, install SSL certificates as well.


**DEPLOYMENT OPTION C: Full Public Production (with Domain Name)**
If the tool is meant for ongoing use by multiple external partners or the public, this is the ideal option.

**C1. Use Case**
	·	Production-level deployment with HTTPS, domain name (e.g., https://patentmatcher.nasa.gov)
	·	Hosted on a proper VM (Google Cloud, AWS EC2, etc.)
	·	Managed by your IT team or web operations group

**C2. Process Overview**
	1.	Provision a VM instance (e.g., Vertex AI instance, AWS EC2, Azure VM)
	2.	Assign a static external IP
	3.	Register a domain (e.g., patentmatcher.nasa.gov) and point it to that IP
	4.	Set up a reverse proxy (Nginx, Apache) to forward requests to Streamlit
	5.	Set up SSL certificates (Let’s Encrypt or internal cert authority)

**C3. Prerequisites**
	·	Follow same Python + Streamlit (Option B, but without the cloudflared tunnelling) installation as before
	·	Open ports 80 and 443 in firewall

**C4. Launch App**
		
		pkill -f "streamlit" 2>/dev/null || true
		 sudo fuser -k 8501/tcp 2>/dev/null || true
		 export STREAMLIT_THEME_BASE=dark
		 export STREAMLIT_CONFIG="$PWD/streamlit/config.toml"
		 streamlit run app.py --server.port 8501 --server.headless true --server.address 127.0.0.1

**C5. Reverse Proxy Setup (Example: for NGNIX)**

		server {
		     listen 80;
		     server_name patentmatcher.nasa.gov;
		 
		    location / {
		         proxy_pass http://127.0.0.1:8501;
		         proxy_set_header Host $host;
		         proxy_set_header X-Real-IP $remote_addr;
		     }
		 }
		 
Then install SSL:

		sudo apt install certbot python3-certbot-nginx
		sudo certbot --nginx -d patentmatcher.nasa.gov

You now have a production-grade public-facing app with HTTPS.

**FAQs**

*Q1: Can this run on a physical machine?*
Yes. You can deploy it on a physical server inside a datacenter, as long as Python and the dependencies are installed.

*Q2: Can we host it inside Google Cloud / Vertex AI?*
Yes. A Vertex AI or Compute Engine VM can run Streamlit just like any Linux machine.

*Q3: Do we have to use Cloudflare?*
No. It’s only needed for Option A (quick public URL). In Options B and C, it is optional for use and is not needed if an intranet domain name/URL or public domain/URL is already allocated.

*Q4: Can we assign a domain for internal users?*
Yes. Use your internal DNS to map names like patents.nasa.local to internal IPs. This improves usability.

*Q5: What if I get a Streamlit port error?*
That means another Streamlit app is already running. Use:
		
		pkill -f "streamlit"
		sudo fuser -k 8501/tcp

*Q6: Can multiple users access this at the same time?*
Yes. Streamlit supports concurrent users, but performance depends on server specs.
