const { app, BrowserWindow, shell, dialog } = require('electron');
const { spawn, execSync } = require('child_process');
const http = require('http');
const path = require('path');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const FLASK_PORT = 5000;
const FLASK_URL = `http://localhost:${FLASK_PORT}`;
const APP_DIR = __dirname;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let mainWindow = null;
let flaskProcess = null;
let oauthPollInterval = null;

// ---------------------------------------------------------------------------
// Flask process management
// ---------------------------------------------------------------------------

/**
 * Find a working Python command on this system.
 * Tries 'python', 'python3', and the Windows 'py' launcher.
 */
function findPython() {
  for (const cmd of ['python', 'python3', 'py']) {
    try {
      execSync(`${cmd} --version`, { stdio: 'pipe' });
      return cmd;
    } catch {
      continue;
    }
  }
  return null;
}

/**
 * Spawn the Flask server as a child process.
 */
function startFlask() {
  const pythonCmd = findPython();
  if (!pythonCmd) {
    dialog.showErrorBox(
      'Python Not Found',
      'Could not find Python on your system. Please install Python 3 and make sure it is on your PATH.'
    );
    app.quit();
    return;
  }

  flaskProcess = spawn(pythonCmd, ['app.py', '--electron'], {
    cwd: APP_DIR,
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  flaskProcess.stdout.on('data', (data) => {
    console.log(`[Flask] ${data.toString().trim()}`);
  });

  flaskProcess.stderr.on('data', (data) => {
    console.error(`[Flask] ${data.toString().trim()}`);
  });

  flaskProcess.on('close', (code) => {
    console.log(`Flask process exited with code ${code}`);
    flaskProcess = null;
  });
}

/**
 * Kill the Flask child process (and its entire process tree on Windows).
 */
function killFlask() {
  if (!flaskProcess) return;

  try {
    if (process.platform === 'win32') {
      // On Windows, process.kill() doesn't reliably kill child trees.
      spawn('taskkill', ['/pid', String(flaskProcess.pid), '/f', '/t']);
    } else {
      flaskProcess.kill('SIGTERM');
    }
  } catch (err) {
    console.error('Error killing Flask process:', err);
  }

  flaskProcess = null;
}

/**
 * Poll Flask until it responds to an HTTP request.
 * Resolves when Flask is ready, rejects after timeout.
 */
function waitForFlask(maxAttempts = 50, interval = 200) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    const check = () => {
      attempts++;

      const req = http.get(FLASK_URL, (res) => {
        // Any response means Flask is up
        res.resume(); // drain the response
        resolve();
      });

      req.on('error', () => {
        if (attempts >= maxAttempts) {
          reject(new Error(`Flask did not start after ${maxAttempts} attempts`));
        } else {
          setTimeout(check, interval);
        }
      });

      req.setTimeout(1000, () => {
        req.destroy();
        if (attempts >= maxAttempts) {
          reject(new Error(`Flask did not start after ${maxAttempts} attempts`));
        } else {
          setTimeout(check, interval);
        }
      });
    };

    check();
  });
}

// ---------------------------------------------------------------------------
// Window management
// ---------------------------------------------------------------------------

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'EVE Character Tracker',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // Show the loading page first, then switch to Flask once ready
  mainWindow.loadFile('loading.html');

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // ---- External link handling ----

  // Intercept in-page navigation (clicking links without target="_blank")
  mainWindow.webContents.on('will-navigate', (event, url) => {
    // Allow navigation within our Flask app
    try {
      const parsed = new URL(url);
      if (parsed.hostname === 'localhost' && parsed.port === String(FLASK_PORT)) {
        return;
      }
    } catch {
      return;
    }

    // Everything else opens in the system browser
    event.preventDefault();
    shell.openExternal(url);

    // If this was an EVE SSO login, start polling for the OAuth callback
    if (url.includes('login.eveonline.com')) {
      startOAuthPolling();
    }
  });

  // Intercept window.open() / target="_blank" links
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

// ---------------------------------------------------------------------------
// OAuth completion detection
// ---------------------------------------------------------------------------

/**
 * After the user is sent to EVE SSO in the system browser, we poll
 * /api/locations to detect when a new character has been added.
 * Once detected, navigate the Electron window to /settings.
 */
function startOAuthPolling() {
  if (oauthPollInterval) clearInterval(oauthPollInterval);

  let lastCharacterCount = null;

  // Snapshot the current character count
  fetchCharacterCount((count) => {
    lastCharacterCount = count;
  });

  oauthPollInterval = setInterval(() => {
    fetchCharacterCount((count) => {
      if (lastCharacterCount !== null && count > lastCharacterCount) {
        // A new character was added — navigate to settings
        if (mainWindow) {
          mainWindow.loadURL(`${FLASK_URL}/settings`);
        }
        clearInterval(oauthPollInterval);
        oauthPollInterval = null;
      }
    });
  }, 2000);

  // Give up after 5 minutes
  setTimeout(() => {
    if (oauthPollInterval) {
      clearInterval(oauthPollInterval);
      oauthPollInterval = null;
    }
  }, 5 * 60 * 1000);
}

function fetchCharacterCount(callback) {
  http
    .get(`${FLASK_URL}/api/locations`, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        try {
          callback(JSON.parse(data).length);
        } catch {
          callback(0);
        }
      });
    })
    .on('error', () => {});
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  startFlask();
  createWindow();

  try {
    await waitForFlask();
    // Flask is up — switch from loading screen to the real app
    if (mainWindow) {
      mainWindow.loadURL(FLASK_URL);
    }
  } catch (err) {
    dialog.showErrorBox(
      'Startup Error',
      'Could not start the Flask server.\n\n' +
        'Make sure Python is installed, dependencies are installed (pip install -r requirements.txt), ' +
        'and port 5000 is not in use.\n\n' +
        err.message
    );
    killFlask();
    app.quit();
  }
});

app.on('window-all-closed', () => {
  killFlask();
  app.quit();
});

app.on('before-quit', () => {
  killFlask();
});

process.on('exit', () => {
  killFlask();
});
