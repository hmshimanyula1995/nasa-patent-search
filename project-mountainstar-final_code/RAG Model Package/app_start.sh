pkill -f "streamlit" 2>/dev/null || true
sudo fuser -k 8501/tcp 2>/dev/null || true
echo "Streamlit ready on port 8501"

export STREAMLIT_THEME_BASE=dark
export STREAMLIT_CONFIG="$PWD/streamlit/config.toml"
test -f "$STREAMLIT_CONFIG" && echo "Found config" || echo "Missing config"

nohup streamlit run app_sesh_id.py \
  --server.port 8501 \
  --server.headless true \
  --server.address 127.0.0.1 \
  > streamlit.log 2>&1 &

echo
echo "Streamlit started (PID $!). Please wait for the link..."
echo
echo "🔗 Click the link below to launch the app!"
echo "(It may take a few seconds for the link to appear.)"
cloudflared tunnel --url http://127.0.0.1:8501 2>&1 | grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com'


