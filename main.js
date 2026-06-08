const { app, BrowserWindow, shell, dialog } = require('electron');
const http = require('http');
const path = require('path');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const SERVICE_PORT = 5000;
const SERVICE_URL = `http://127.0.0.1:${SERVICE_PORT}`;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let mainWindow = null;
let oauthPollInterval = null;

// ---------------------------------------------------------------------------
// Service probe
// ---------------------------------------------------------------------------

/**
 * Try once to reach the background service health endpoint.
 * Resolves true if reachable within 2 seconds, false otherwise.
 */
function probeService() {
  return new Promise((resolve) => {
    const req = http.get(`${SERVICE_URL}/api/health`, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });

    req.on('error', () => resolve(false));

    req.setTimeout(2000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

// ---------------------------------------------------------------------------
// Window management
// ---------------------------------------------------------------------------

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'Sihcom Toon Tracker',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // ---- External link handling ----

  function isServiceUrl(url) {
    try {
      const parsed = new URL(url);
      return (
        (parsed.hostname === '127.0.0.1' || parsed.hostname === 'localhost') &&
        parsed.port === String(SERVICE_PORT)
      );
    } catch {
      return false;
    }
  }

  function handleExternalUrl(event, url) {
    if (isServiceUrl(url)) return;
    event.preventDefault();
    shell.openExternal(url);
    if (url.includes('login.eveonline.com')) {
      startOAuthPolling();
    }
  }

  // Intercept client-side navigations (e.g. clicking <a href="...">)
  mainWindow.webContents.on('will-navigate', handleExternalUrl);

  // Intercept server-side redirects (e.g. Flask's 302 → login.eveonline.com)
  mainWindow.webContents.on('will-redirect', handleExternalUrl);

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
 * After the user is sent to EVE SSO in the system browser, poll
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
          mainWindow.loadURL(`${SERVICE_URL}/settings`);
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
    .get(`${SERVICE_URL}/api/locations`, (res) => {
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
  createWindow();
  mainWindow.loadFile('loading.html');

  const serviceUp = await probeService();

  if (serviceUp) {
    mainWindow.loadURL(SERVICE_URL);
  } else {
    mainWindow.loadFile('service-offline.html');
  }
});

app.on('window-all-closed', () => {
  // The background service manages its own lifecycle — do not stop it here.
  app.quit();
});
