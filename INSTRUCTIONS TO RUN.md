# INSTRUCTIONS TO RUN

This document provides step-by-step instructions for running the complete ColdGuard project locally on your machine without requiring Docker.

## Prerequisites
- Node.js (v18+)
- Python (v3.10+)

## Step 1: Start the Backend (FastAPI)
The backend requires a Python virtual environment with dependencies installed.

1. Open a terminal.
2. Navigate to the backend directory:
   ```bash
   cd c:\RVCE\CI\coldguard\backend
   ```
3. Activate the virtual environment (if it exists, otherwise create it and run `pip install -r requirements.txt`):
   ```bash
   .\venv\Scripts\activate
   ```
4. Start the FastAPI backend server:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   *The backend API will be accessible at http://127.0.0.1:8000*

## Step 2: Run the Simulator (Optional but Recommended)
To see data flowing into the application, you can run the simulator script in a separate terminal. This will populate the database with storage units, mock temperature readings, and trigger violations.

1. Open a new terminal.
2. Navigate to the backend directory:
   ```bash
   cd c:\RVCE\CI\coldguard\backend
   ```
3. Activate the virtual environment:
   ```bash
   .\venv\Scripts\activate
   ```
4. Run the interactive demo scenario script:
   ```bash
   python scripts/run_demo.py
   ```
   *Alternatively, the frontend has a built-in simulator UI you can use once it is running.*

## Step 3: Start the Frontend (React Dashboard)
The frontend requires Node.js to serve the Vite React application.

1. Open a new terminal.
2. Navigate to the frontend directory:
   ```bash
   cd c:\RVCE\CI\coldguard\frontend
   ```
3. Install dependencies (if you haven't already):
   ```bash
   npm install
   ```
4. Start the Vite development server:
   ```bash
   npm run dev
   ```
   *The frontend dashboard will be accessible at http://localhost:5173*

---

Once both the backend and frontend are running, you can open your web browser, navigate to `http://localhost:5173`, and interact with the complete ColdGuard platform.
