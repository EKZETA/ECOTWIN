\# How to Start the City Grid Monitor



\## 1. Open the project



Open this folder in VS Code:



```text

C:\\Users\\iamch\\Downloads\\Project 1\\Project 1

```



Open a terminal using \*\*Terminal → New Terminal\*\*.



Confirm the terminal is in the project root:



```powershell

cd "C:\\Users\\iamch\\Downloads\\Project 1\\Project 1"

```



\## 2. Check Python



Run:



```powershell

py --version

```



If this command fails, install Python from \[python.org](https://www.python.org/downloads/).



During installation, enable \*\*Add Python to PATH\*\*, then restart VS Code.



\## 3. Create the backend environment



Run these commands one at a time:



```powershell

Remove-Item -Recurse -Force .\\venv -ErrorAction SilentlyContinue

py -m venv .\\venv

Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

.\\venv\\Scripts\\Activate.ps1

```



The terminal should now start with:



```text

(venv)

```



\## 4. Install backend dependencies



Run:



```powershell

python -m pip install --upgrade pip

python -m pip install -r requirements.txt

```



\## 5. Check SUMO



Run:



```powershell

Test-Path "C:\\Program Files (x86)\\Eclipse\\Sumo"

```



If the result is `True`, run:



```powershell

$env:SUMO\_HOME = "C:\\Program Files (x86)\\Eclipse\\Sumo"

```



If the result is `False`, install SUMO or set `SUMO\_HOME` to the correct SUMO folder.



\## 6. Start the backend



Keep the first terminal open and run:



```powershell

python -m uvicorn backend.main:app --reload --port 8000

```



Test the backend by opening:



```text

http://localhost:8000/docs

```



The FastAPI documentation page should appear.



\## 7. Start the frontend



Open a second terminal in VS Code by clicking the \*\*+\*\* button.



Run:



```powershell

cd "C:\\Users\\iamch\\Downloads\\Project 1\\Project 1\\frontend"

npm install

npm run dev

```



Open the URL displayed by Vite. It is usually:



```text

http://localhost:5173

```



\## 8. Keep both terminals open



\- Terminal 1 runs the backend on port `8000`.

\- Terminal 2 runs the frontend on port `5173`.



The frontend will not work if the backend terminal is closed.



\## Troubleshooting



\### Python is not recognized



Install Python and select \*\*Add Python to PATH\*\*. Restart VS Code.



\### `Activate.ps1` cannot be found



Recreate the virtual environment:



```powershell

Remove-Item -Recurse -Force .\\venv -ErrorAction SilentlyContinue

py -m venv .\\venv

.\\venv\\Scripts\\Activate.ps1

```



\### npm is not recognized



Install Node.js from \[nodejs.org](https://nodejs.org/), restart VS Code, and run:



```powershell

cd "C:\\Users\\iamch\\Downloads\\Project 1\\Project 1\\frontend"

npm install

npm run dev

```



\### Telemetry is offline



Check that:



1\. The backend terminal is still running.

2\. SUMO is installed.

3\. The frontend was opened using the Vite URL, not by double-clicking `index.html`.



\### Stop the servers



Click each terminal and press:



```text

Ctrl+C

```

