Cloud Run Deployment Instructions for NASA TTO Streamlit App
Overview
This document provides step-by-step instructions to deploy the NASA TTO ? AI Tool for 
Patent Matching Streamlit application to Google Cloud Run. The workflow consists of 
preparing the project folder, building a Docker container image, pushing it to Google 
Container Registry, and deploying it to Cloud Run.
1. Prepare Your App Folder
Organize your application files into a single folder. This folder MUST contain the following:
? app.py (Streamlit front-end)
? RAGModelTesting-V3-UI.ipynb (main notebook used by papermill)
? streamlit/config.toml (theme configuration)
? requirements.txt (Python dependencies)
? Dockerfile (build instructions)
? .dockerignore (ignored items during Docker build)
? cloudbuild.yaml (optional: for Cloud Build automation)

Example folder structure:
my-patent-app/
    app.py
    RAGModelTesting-V3-UI.ipynb
    streamlit/
        config.toml
    requirements.txt
    Dockerfile
    .dockerignore
    cloudbuild.yaml
2. Open Google Cloud Shell
1. Navigate to https://console.cloud.google.com
2. Click the Cloud Shell icon (>_) on the top-right.
3. Cloud Shell opens a terminal at the bottom of the page.
4. Upload your project folder or clone it into Cloud Shell.
5. Navigate to the folder:
   cd my-patent-app
6. Confirm the contents with: ls
3. Build and Push the Docker Image
Run the following command inside Cloud Shell, from the folder containing Dockerfile:

gcloud builds submit --tag gcr.io/PROJECT_ID/nasa-tto-streamlit .

Replace PROJECT_ID with your actual GCP Project ID.
This command will:
? Build a Docker image using your Dockerfile
? Install all dependencies from requirements.txt
? Push the image to Google Container Registry
4. Deploy the Container Image to Cloud Run
Once the image is built, deploy it to Cloud Run:

gcloud run deploy nasa-tto-streamlit \
  --image gcr.io/PROJECT_ID/nasa-tto-streamlit \
  --platform managed \
  --region REGION \
  --allow-unauthenticated \
  --port 8080

Replace:
? PROJECT_ID with your actual project ID
? REGION with your chosen region (e.g., us-central1)

Cloud Run will output a public URL such as:
https://nasa-tto-streamlit-xxxxxx-uc.a.run.app
5. How This Replaces the Clean Terminal Script
Your original terminal script required:
? Installing Python packages manually
? Installing cloudflared for tunneling
? Running Streamlit locally on 127.0.0.1:8501
? Running cloudflared in a second terminal window

Cloud Run eliminates all of this. The container:
? Installs dependencies automatically
? Runs Streamlit inside a fully managed environment
? Exposes the service globally via HTTPS (NO cloudflared needed)
? Requires only one command to deploy once the image is built
6. Summary
To deploy to Cloud Run:
1. Prepare your folder with the generated deployment files
2. Open Cloud Shell
3. Navigate to the folder
4. Run: gcloud builds submit
5. Run: gcloud run deploy
6. Access your app using the HTTPS URL provided by Cloud Run

You now have a fully hosted, production-ready deployment of your NASA TTO Patent 
Matching App.
