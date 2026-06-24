import os
import sys
import json
import urllib.request
import urllib.parse
import html
from flask import Flask, request, jsonify, render_template_string
from yt_dlp import YoutubeDL

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>מוריד שירים מיוטיוב</title>
    <style>
        body { font-family: sans-serif; background-color: #f4f4f9; margin: 0; padding: 20px; text-align: center; }
        .container { max-width: 600px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        input[type="text"] { width: 80%; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 4px; font-size: 16px; }
        button { padding: 10px 20px; border: none; background-color: #007bff; color: white; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 16px; }
        button:disabled { background-color: #ccc; }
        .controls { margin: 20px 0; display: flex; justify-content: space-between; align-items: center; background: #eee; padding: 10px; border-radius: 4px; }
        .song-list { text-align: right; max-height: 400px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 4px; margin-top: 10px; }
        .song-item { padding: 10px; border-bottom: 1px solid #eee; display: flex; align-items: center; }
        .song-item input[type="checkbox"] { margin-left: 12px; transform: scale(1.2); }
        #status { margin-top: 15px; font-weight: bold; color: #28a745; min-height: 24px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>מוריד מוזיקה ל-MP3</h2>
        <input type="text" id="singerInput" placeholder="הכנס שם זמר...">
        <button id="searchBtn" onclick="searchSongs()">חפש שירים</button>
        
        <div id="controlsContainer" class="controls" style="display: none;">
            <label><input type="checkbox" id="selectAll" onchange="toggleSelectAll(this)"> בחר את כל השירים</label>
            <button id="downloadBtn" onclick="downloadSelected()">הורד שירים שנבחרו</button>
        </div>

        <div id="songList" class="song-list" style="display: none;"></div>
        <div id="status"></div>
    </div>

    <script>
        let songsData = [];

        if (Notification.permission === 'default') {
            Notification.requestPermission();
        }

        async function searchSongs() {
            const singer = document.getElementById('singerInput').value.trim();
            if (!singer) return alert('נא להזין שם זמר');
            
            document.getElementById('status').innerText = 'מחפש שירים, אנא המתן...';
            document.getElementById('searchBtn').disabled = true;
            
            try {
                const response = await fetch(`/search?q=${encodeURIComponent(singer)}`);
                songsData = await response.json();
                
                const listDiv = document.getElementById('songList');
                listDiv.innerHTML = '';
                
                if (songsData.length === 0) {
                    document.getElementById('status').innerText = 'לא נמצאו תוצאות.';
                    return;
                }

                songsData.forEach((song, index) => {
                    const item = document.createElement('div');
                    item.className = 'song-item';
                    item.innerHTML = `<input type="checkbox" class="song-checkbox" data-id="${song.id}" data-title="${song.title}"> <span>${index + 1}. ${song.title}</span>`;
                    listDiv.appendChild(item);
                });

                document.getElementById('controlsContainer').style.display = 'flex';
                listDiv.style.display = 'block';
                document.getElementById('status').innerText = `נמצאו ${songsData.length} שירים.`;
                document.getElementById('selectAll').checked = false;
            } catch (e) {
                document.getElementById('status').innerText = 'שגיאה בחיפוש השירים.';
            } finally {
                document.getElementById('searchBtn').disabled = false;
            }
        }

        function toggleSelectAll(master) {
            const checkboxes = document.querySelectorAll('.song-checkbox');
            checkboxes.forEach(cb => cb.checked = master.checked);
        }

        async function downloadSelected() {
            if (Notification.permission !== 'granted') {
                await Notification.requestPermission();
            }

            const checkboxes = document.querySelectorAll('.song-checkbox:checked');
            if (checkboxes.length === 0) return alert('לא נבחרו שירים להורדה');

            document.getElementById('downloadBtn').disabled = true;

            for (let i = 0; i < checkboxes.length; i++) {
                const cb = checkboxes[i];
                const id = cb.getAttribute('data-id');
                const title = cb.getAttribute('data-title');

                document.getElementById('status').innerText = `מוריד (${i + 1}/${checkboxes.length}): ${title}`;
                
                if (Notification.permission === 'granted') {
                    new Notification('הורדת שיר החלה', { body: `מוריד כעת: ${title}`, icon: 'https://cdn-icons-png.flaticon.com/512/2382/2382661.png' });
                }

                try {
                    const res = await fetch('/download_single', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: id })
                    });
                    const data = await res.json();
                    
                    if (data.status === 'success' && Notification.permission === 'granted') {
                        new Notification('ההורדה הסתיימה', { body: `השיר "${title}" הורד בהצלחה!`, icon: 'https://cdn-icons-png.flaticon.com/512/190/190411.png' });
                    }
                } catch (err) {
                    console.error(err);
                }
            }

            document.getElementById('status').innerText = 'כל ההורדות שנבחרו הסתיימו בהצלחה!';
            document.getElementById('downloadBtn').disabled = false;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
        
    songs = []
    next_page_token = ""
    api_key = "AIzaSyAKK4VTbQJ_8tsHfxb2tcDZ9SSR9gWXH-0"
    
    # ביצוע 2 בקשות רצופות של 50 תוצאות כדי להגיע ל-100 תוצאות בסך הכל
    for _ in range(2):
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={urllib.parse.quote(query)}&type=video&maxResults=50&key={api_key}"
        if next_page_token:
            url += f"&pageToken={next_page_token}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                for item in data.get('items', []):
                    video_id = item.get('id', {}).get('videoId')
                    title = item.get('snippet', {}).get('title')
                    if video_id and title:
                        songs.append({'id': video_id, 'title': html.unescape(title)})
                next_page_token = data.get('nextPageToken')
                if not next_page_token:
                    break
        except Exception:
            break
            
    return jsonify(songs[:100])

@app.route('/download_single', methods=['POST'])
def download_single():
    data = request.json or {}
    video_id = data.get('id')
    if not video_id:
        return jsonify({'status': 'error', 'message': 'Missing ID'}), 400
        
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join('.', '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'nocheckcertificate': True,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
