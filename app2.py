import asyncio
import os
import time
import pty
from fastapi import FastAPI, WebSocket, Query, UploadFile, File, Form
from fastapi.responses import HTMLResponse

app = FastAPI()

def get_html_structure() -> str:
    """Часть 1: Структура и стили интерфейса."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Мульти-панель Docker</title>
        <style>
            body { background: #1e1e1e; color: white; font-family: sans-serif; padding: 20px; }
            .controls-top { background: #2d2d2d; padding: 15px; border-radius: 6px; margin-bottom: 20px; display: flex; gap: 15px; align-items: center; }
            .btn { padding: 10px 20px; font-size: 15px; cursor: pointer; border: none; border-radius: 4px; font-weight: bold; }
            .btn-add { background: #4caf50; color: white; font-size: 16px; }
            #panels-container { display: flex; flex-direction: column; gap: 30px; }
            .container-panel { background: #252525; border: 2px solid #444; border-radius: 8px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
            .panel-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #444; padding-bottom: 10px; margin-bottom: 15px; }
            .btn-delete { background: #f44336; color: white; }
            .setup-box { padding: 20px; background: #1a1a1a; border-radius: 6px; display: flex; justify-content: space-around; flex-wrap: wrap; gap: 20px; text-align: left; }
            .setup-section { display: flex; flex-direction: column; gap: 8px; width: 45%; min-width: 280px; }
            .setup-box select, .setup-box input[type="text"] { padding: 10px; background: #333; color: white; border: 1px solid #555; border-radius: 4px; font-size: 14px; width: 100%; box-sizing: border-box; }
            .work-zone { display: none; }
            .upload-panel { background: #1a1a1a; padding: 10px; border-radius: 4px; margin-bottom: 10px; border: 1px solid #333; font-size: 13px; }
            .upload-panel input[type="text"] { padding: 5px; background: #333; color: #fff; border: 1px solid #555; border-radius: 4px; width: 150px; }
            .btn-upload { padding: 5px 12px; background: #ff9800; color: #000; font-weight: bold; border: none; border-radius: 4px; cursor: pointer; }
            .terminal-box { width: 100%; height: 350px; background: #000; border: 1px solid #333; padding: 10px; overflow-y: scroll; white-space: pre-wrap; font-family: monospace; font-size: 15px; line-height: 1.3; }
            .input-line { width: 100%; background: #000; color: #00ff00; border: 1px solid #333; border-top: none; padding: 10px; font-family: monospace; font-size: 15px; outline: none; }
            .action-bar { display: flex; gap: 10px; margin-top: 8px; }
            .btn-ctrl { background: #555; color: white; padding: 5px 15px; font-size: 13px; font-family: monospace; }
            .btn-ctrl:hover { background: #777; }
        </style>
    </head>
    <body>
        <h2>🛸 Мульти-панель управления Docker</h2>
        <div class="controls-top">
            <button class="btn btn-add" onclick="createNewPanel()">➕ Добавить новую панель</button>
            <span>Выбирайте локальные образа для старта или подключайтесь к активным контейнерам.</span>
        </div>
        <div id="panels-container"></div>
        <script>
    """

def get_js_combined_logic() -> str:
    """Часть 2: Объединенный JS-код управления панелями, селекторами и веб-сокетом."""
    return """
            let panelCounter = 0;

            async function createNewPanel() {
                panelCounter++;
                const panelId = `panel-${panelCounter}`;
                let imageOptions = '<option value="">-- Выберите образ --</option>';
                let containerOptions = '<option value="">-- Выберите контейнер --</option>';
                
                try {
                    const res = await fetch('/api/resources');
                    const resources = await res.json();
                    resources.images.forEach(img => { imageOptions += `<option value="${img}">${img}</option>`; });
                    resources.containers.forEach(c => { containerOptions += `<option value="${c.id}">${c.name} (${c.id})</option>`; });
                } catch(e) { console.error("ресурсы не загружены", e); }

                const panelHtml = `
                    <div class="container-panel" id="${panelId}">
                        <div class="panel-header">
                            <h3>Панель #${panelCounter}: <span id="title-${panelId}" style="color: #aaa;">Ожидание выбора</span></h3>
                            <button class="btn btn-delete" style="display:none;" id="del-btn-${panelId}">❌ Уничтожить</button>
                            <button class="btn" style="background:#555; color:white;" onclick="closePanel('${panelId}')">Убрать</button>
                        </div>
                        <div class="setup-box" id="setup-${panelId}">
                            <div class="setup-section">
                                <label style="font-weight:bold; color:#4caf50;">Создать из доступных образов:</label>
                                <select id="select-img-${panelId}">${imageOptions}</select>
                                <button class="btn" style="background:#4caf50; color:white;" onclick="createFromImage('${panelId}')">🚀 Создать и запустить</button>
                            </div>
                            <div class="setup-section">
                                <label style="font-weight:bold; color:#2196f3;">Подключиться к запущенным:</label>
                                <select id="select-c-${panelId}" onchange="document.getElementById('input-id-${panelId}').value = this.value">${containerOptions}</select>
                                <input type="text" id="input-id-${panelId}" placeholder="Или введите ID/Имя вручную">
                                <button class="btn" style="background:#2196f3; color:white;" onclick="connectContainer('${panelId}', document.getElementById('input-id-${panelId}').value)">🔌 Подключиться</button>
                            </div>
                        </div>
                        <div class="work-zone" id="work-${panelId}">
                            <div class="upload-panel">
                                <form onsubmit="uploadFile(event, '${panelId}')" enctype="multipart/form-data" style="display:flex; gap:15px; align-items:center;">
                                    <input type="hidden" name="container_id" id="form-cid-${panelId}">
                                    <label>Файл: <input type="file" name="file" required></label>
                                    <label>Папка: <input type="text" name="dest_path" value="/" required></label>
                                    <button type="submit" class="btn-upload">📥 Загрузить файл</button>
                                    <span id="up-status-${panelId}" style="color:#ff9800;"></span>
                                </form>
                            </div>
                            <div class="terminal-box" id="box-${panelId}">Ожидание...</div>
                            <input type="text" class="input-line" id="line-${panelId}" placeholder="Команда + Enter..." disabled>
                            <div class="action-bar">
                                <button class="btn btn-ctrl" onclick="sendCtrl('${panelId}', 'C')">Ctrl + C</button>
                                <button class="btn btn-ctrl" onclick="sendCtrl('${panelId}', 'Z')">Ctrl + Z</button>
                            </div>
                        </div>
                    </div>
                `;
                document.getElementById('panels-container').insertAdjacentHTML('beforeend', panelHtml);
                const panelEl = document.getElementById(panelId);
                panelEl.cmdHistory = []; panelEl.historyIdx = -1;
            }

            function closePanel(panelId) {
                const el = document.getElementById(panelId);
                if(el.ws) el.ws.close();
                el.remove();
            }

            async function createFromImage(panelId) {
                const imgName = document.getElementById(`select-img-${panelId}`).value;
                if(!imgName) { alert("Выберите образ!"); return; }
                const titleEl = document.getElementById(`title-${panelId}`);
                titleEl.innerText = "Запуск контейнера..."; titleEl.style.color = "#ff9800";
                try {
                    const response = await fetch(`/api/create?image=${encodeURIComponent(imgName)}`, { method: 'POST' });
                    const data = await response.json();
                    if(data.id) connectContainer(panelId, data.id);
                    else { titleEl.innerText = "Ошибка запуска"; alert("Ошибка: " + data.error); }
                } catch(e) { alert("Ошибка сети"); }
            }

            function connectContainer(panelId, containerId) {
                if(!containerId) return;
                containerId = containerId.trim();
                const panelEl = document.getElementById(panelId);
                const titleEl = document.getElementById(`title-${panelId}`);
                const delBtn = document.getElementById(`del-btn-${panelId}`);
                const termBox = document.getElementById(`box-${panelId}`);
                const termInput = document.getElementById(`line-${panelId}`);
                
                document.getElementById(`form-cid-${panelId}`).value = containerId;
                titleEl.innerText = containerId; titleEl.style.color = "#4caf50";
                document.getElementById(`setup-${panelId}`).style.display = "none";
                document.getElementById(`work-${panelId}`).style.display = "block";

                delBtn.style.display = "block";
                delBtn.onclick = async () => {
                    if(confirm(`Удалить ${containerId}?`)) {
                        if(panelEl.ws) panelEl.ws.close();
                        await fetch(`/api/delete?id=${containerId}`, { method: 'POST' });
                        panelEl.remove();
                    }
                };

                const ws = new WebSocket(`ws://${window.location.host}/ws?id=${containerId}`);
                panelEl.ws = ws;

                ws.onopen = () => { termBox.innerHTML = ""; termInput.removeAttribute('disabled'); termInput.focus(); };
                ws.onmessage = (e) => {
                    termBox.innerHTML += e.data.replace(/\\x1B\\[[0-9;]*[a-zA-Z]/g, '');
                    termBox.scrollTop = termBox.scrollHeight;
                };

                termInput.onkeydown = (e) => {
                    if (e.ctrlKey && e.key.toLowerCase() === 'c') { e.preventDefault(); ws.send("\\x03"); return; }
                    if (e.ctrlKey && e.key.toLowerCase() === 'z') { e.preventDefault(); ws.send("\\x1a"); return; }
                    if (e.key === 'ArrowUp') {
                        e.preventDefault();
                        if (panelEl.cmdHistory.length > 0 && panelEl.historyIdx < panelEl.cmdHistory.length - 1) {
                            panelEl.historyIdx++; termInput.value = panelEl.cmdHistory[panelEl.cmdHistory.length - 1 - panelEl.historyIdx];
                        }
                        return;
                    }
                    if (e.key === 'ArrowDown') {
                        e.preventDefault();
                        if (panelEl.historyIdx > 0) {
                            panelEl.historyIdx--; termInput.value = panelEl.cmdHistory[panelEl.cmdHistory.length - 1 - panelEl.historyIdx];
                        } else if (panelEl.historyIdx === 0) { panelEl.historyIdx = -1; termInput.value = ''; }
                        return;
                    }
                    if (e.key === 'Enter') {
                        const cmd = termInput.value;
                        if (cmd.trim() !== '') panelEl.cmdHistory.push(cmd);
                        panelEl.historyIdx = -1; ws.send(cmd + "\\n"); termInput.value = '';
                    }
                };

                ws.onclose = () => { termBox.innerHTML += "\\n[Соединение закрыто]"; termInput.setAttribute('disabled', 'true'); titleEl.style.color = "#f44336"; };
            }

            async function uploadFile(event, panelId) {
                event.preventDefault();
                const statusSpan = document.getElementById(`up-status-${panelId}`);
                statusSpan.innerText = "⏳...";
                try {
                    await fetch('/api/upload', { method: 'POST', body: new FormData(event.target) });
                    statusSpan.innerText = "✅"; setTimeout(() => statusSpan.innerText = "", 2000);
                } catch(e) { alert("Ошибка сети"); }
            }

            function sendCtrl(panelId, key) {
                const panelEl = document.getElementById(panelId);
                if (panelEl && panelEl.ws && panelEl.ws.readyState === WebSocket.OPEN) {
                    if (key === 'C') panelEl.ws.send("\\x03");
                    if (key === 'Z') panelEl.ws.send("\\x1a");
                }
            }

            window.onload = createNewPanel;
        </script>
    </body>
    </html>
    """

@app.get("/")
async def get_index():
    # ИСПРАВЛЕНО: Склеиваем две новые монолитные функции
    full_html = get_html_structure() + get_js_combined_logic()
    return HTMLResponse(content=full_html)

@app.get("/api/resources")
async def api_get_local_resources():
    images = []
    containers = []
    try:
        img_proc = await asyncio.create_subprocess_exec(
            "docker", "images", "--format", "{{.Repository}}:{{.Tag}}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        img_stdout, _ = await img_proc.communicate()
        for line in img_stdout.decode().strip().split('\n'):
            if line.strip() and not line.startswith('<none>'):
                images.append(line.strip())

        c_proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "--format", "{{.ID}}|{{.Names}}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        c_stdout, _ = await c_proc.communicate()
        for line in c_stdout.decode().strip().split('\n'):
            if line.strip():
                cid, name = line.split('|')
                containers.append({"id": cid[:12], "name": name})
    except Exception as e:
        print(f"Ошибка сканирования ресурсов хоста: {e}")
    return {"images": sorted(list(set(images))), "containers": containers}

@app.post("/api/create")
async def api_create_from_selected_image(image: str = Query(...)):
    try:
        safe_img_name = image.replace(':', '_').replace('/', '_')
        container_name = f"{safe_img_name}_{int(time.time())}_{os.urandom(1).hex()}"
        
        cmd = ["docker", "run", "-d", "--name", container_name]
        
        # ЕСЛИ ВЫБРАН ОБРАЗ WINDOWS - добавляем параметры графики и KVM
        if "windows" in image:
            cmd.extend([
                "--device=/dev/kvm",           # Проброс аппаратного ускорения (KVM)
                "--cap-add=NET_ADMIN",         # Права для настройки сети внутри винды
                "-p", "8006:8006",             # Порт для графики в браузере (HTML5)
                "-p", "3389:3389/tcp",         # Порт для классического RDP (Удаленный рабочий стол)
                "-p", "3389:3389/udp",
                "-e", "VERSION=11",            # По умолчанию ставим Windows 11 (можно поменять на 10 или 7)
                "-e", "RAM_SIZE=4G",           # Выделяем 4 ГБ оперативной памяти
                "-e", "CPU_CORES=2"            # Выделяем 2 ядра процессора
            ])
        
        cmd.append(image)
        
        # Для обычных легковесных ОС Linux добавляем sleep infinity
        if any(os_name in image for os_name in ["alpine", "ubuntu", "debian", "busybox"]):
            cmd.extend(["sleep", "infinity"])

        run_proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await run_proc.communicate()
        if run_proc.returncode != 0:
            return {"error": stderr.decode().strip()}
        return {"id": container_name}
    except Exception as e:
        return {"error": str(e)}
        
@app.post("/api/upload")
async def api_upload(container_id: str = Form(...), dest_path: str = Form(...), file: UploadFile = File(...)):
    temp_host_path = f"/tmp/upload_{int(time.time())}_{file.filename}"
    try:
        contents = await file.read()
        with open(temp_host_path, "wb") as f: f.write(contents)
        if not dest_path.endswith('/'): dest_path += '/'
        cp_proc = await asyncio.create_subprocess_exec("docker", "cp", temp_host_path, f"{container_id}:{dest_path}")
        await cp_proc.wait()
        return {"status": "success"}
    except Exception as e: return HTMLResponse(content=str(e), status_code=500)
    finally:
        if os.path.exists(temp_host_path): os.remove(temp_host_path)

@app.post("/api/delete")
async def api_delete(id: str):
    rm_proc = await asyncio.create_subprocess_exec("docker", "rm", "-f", id)
    await rm_proc.wait()
    return {"status": "deleted"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, id: str):
    await websocket.accept()
    master_fd, slave_fd = pty.openpty()
    process = await asyncio.create_subprocess_exec(
        "docker", "exec", "-it", id, "sh",
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, preexec_fn=os.setsid
    )
    os.close(slave_fd)

    async def read_output():
        loop = asyncio.get_running_loop()
        try:
            while True:
                chunk = await loop.run_in_executor(None, os.read, master_fd, 1024)
                if not chunk: break
                await websocket.send_text(chunk.decode('utf-8', errors='ignore'))
        except: pass

    async def write_input():
        try:
            while True:
                data = await websocket.receive_text()
                os.write(master_fd, data.encode('utf-8'))
        except: pass

    stdout_task = asyncio.create_task(read_output())
    stdin_task = asyncio.create_task(write_input())

    await process.wait()
    stdout_task.cancel(); stdin_task.cancel()
    try: os.close(master_fd)
    except: pass
    try: await websocket.close()
    except: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
