import { contextBridge, ipcRenderer, webUtils } from 'electron'

contextBridge.exposeInMainWorld('hermesDesktop', {
  getConnection: profile => ipcRenderer.invoke('sparkii:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('sparkii:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('sparkii:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('sparkii:gateway:ws-url', profile),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('sparkii:window:openSession', sessionId, opts),
  openWindow: () => ipcRenderer.invoke('sparkii:window:openInstance'),
  claimAmbientCue: key => ipcRenderer.invoke('sparkii:ambient:claim', key),
  wakeIndicator: {
    getState: () => ipcRenderer.invoke('sparkii:wake-indicator:get'),
    setState: state => ipcRenderer.send('sparkii:wake-indicator:set', state),
    onState: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('sparkii:wake-indicator:state', listener)

      return () => ipcRenderer.removeListener('sparkii:wake-indicator:state', listener)
    }
  },
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('sparkii:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('sparkii:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('sparkii:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('sparkii:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('sparkii:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('sparkii:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('sparkii:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('sparkii:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('sparkii:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('sparkii:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('sparkii:pet-overlay:control', listener)
    }
  },
  // HUD mode: the chrome-free floating chat. A full app renderer (own gateway)
  // sized as a floating bar, so it mounts the real composer. Main owns the
  // window; `onChanged` keeps every window's toggle truthful.
  hud: {
    open: request => ipcRenderer.invoke('sparkii:hud:open', request),
    close: () => ipcRenderer.invoke('sparkii:hud:close'),
    setIgnoreMouse: ignore => ipcRenderer.send('sparkii:hud:ignore-mouse', ignore),
    moveBy: delta => ipcRenderer.send('sparkii:hud:move-by', delta),
    setBounds: bounds => ipcRenderer.send('sparkii:hud:set-bounds', bounds),
    setVibrancy: on => ipcRenderer.invoke('sparkii:hud:vibrancy', on),
    // The HUD tells main which session it is on; main hands that back to the
    // app window when the HUD closes, so the app can re-home onto it.
    setSession: sessionId => ipcRenderer.send('sparkii:hud:session', sessionId),
    onGoto: callback => {
      const listener = (_event, sessionId) => callback(sessionId)
      ipcRenderer.on('sparkii:hud:goto', listener)

      return () => ipcRenderer.removeListener('sparkii:hud:goto', listener)
    },
    onChanged: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('sparkii:hud:changed', listener)

      return () => ipcRenderer.removeListener('sparkii:hud:changed', listener)
    },
    // Linux only, and silent elsewhere: where the cursor is, in page
    // coordinates, or null when it has left the window. Stands in for the
    // mousemove that `setIgnoreMouseEvents(true, { forward: true })` delivers on
    // macOS and Windows but not here.
    onCursor: callback => {
      const listener = (_event, point) => callback(point)
      ipcRenderer.on('sparkii:hud:cursor', listener)

      return () => ipcRenderer.removeListener('sparkii:hud:cursor', listener)
    }
  },
  // Quick Entry: the global-hotkey mini composer window. Main owns the OS
  // shortcut + the persisted preference; the quick window only captures text
  // and hands it back, and the primary renderer submits it through the normal
  // prompt path.
  quickEntry: {
    getSettings: () => ipcRenderer.invoke('sparkii:quick-entry:settings:get'),
    setSettings: patch => ipcRenderer.invoke('sparkii:quick-entry:settings:set', patch),
    submit: payload => ipcRenderer.send('sparkii:quick-entry:submit', payload),
    dismiss: () => ipcRenderer.send('sparkii:quick-entry:dismiss'),
    // Primary renderer → main → quick window: gateway connection state + the
    // recent-session options the target picker offers. Main caches the latest
    // payload so a freshly spawned quick window starts from truth.
    pushState: payload => ipcRenderer.send('sparkii:quick-entry:state', payload),
    // Quick window subscribes to those pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('sparkii:quick-entry:state', listener)

      return () => ipcRenderer.removeListener('sparkii:quick-entry:state', listener)
    },
    // Main → primary renderer: a submit captured by the quick window.
    onSubmit: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('sparkii:quick-entry:submit', listener)

      return () => ipcRenderer.removeListener('sparkii:quick-entry:submit', listener)
    },
    // Main → quick window: you were just summoned (reset draft + refocus).
    onShown: callback => {
      const listener = () => callback()
      ipcRenderer.on('sparkii:quick-entry:shown', listener)

      return () => ipcRenderer.removeListener('sparkii:quick-entry:shown', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('sparkii:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('sparkii:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('sparkii:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('sparkii:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('sparkii:connection-config:test', payload),
  sshConfigHosts: () => ipcRenderer.invoke('sparkii:ssh-config:hosts'),
  sshResolveHost: host => ipcRenderer.invoke('sparkii:ssh-config:resolve', host),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('sparkii:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('sparkii:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('sparkii:connection-config:oauth-logout', remoteUrl),
  // Sparkii Cloud: one portal login powers discovery + silent per-agent sign-in
  // (cloud-auto-discovery Phase 3).
  cloud: {
    status: () => ipcRenderer.invoke('sparkii:cloud:status'),
    login: () => ipcRenderer.invoke('sparkii:cloud:login'),
    logout: () => ipcRenderer.invoke('sparkii:cloud:logout'),
    discover: org => ipcRenderer.invoke('sparkii:cloud:discover', org),
    agentSignIn: dashboardUrl => ipcRenderer.invoke('sparkii:cloud:agent-sign-in', dashboardUrl)
  },
  profile: {
    get: () => ipcRenderer.invoke('sparkii:profile:get'),
    set: name => ipcRenderer.invoke('sparkii:profile:set', name)
  },
  api: request => ipcRenderer.invoke('sparkii:api', request),
  notify: payload => ipcRenderer.invoke('sparkii:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('sparkii:requestMicrophoneAccess'),
  readWindowBelow: () => ipcRenderer.invoke('sparkii:window:readBelow'),
  readFileDataUrl: filePath => ipcRenderer.invoke('sparkii:readFileDataUrl', filePath),
  readFileDataUrlForAttach: filePath => ipcRenderer.invoke('sparkii:readFileDataUrlForAttach', filePath),
  dataUrlReadMax: {
    get: () => ipcRenderer.invoke('sparkii:data-url-read-max:get'),
    set: maxMb => ipcRenderer.invoke('sparkii:data-url-read-max:set', maxMb)
  },
  readFileText: filePath => ipcRenderer.invoke('sparkii:readFileText', filePath),
  selectPaths: options => ipcRenderer.invoke('sparkii:selectPaths', options),
  selectSavePath: options => ipcRenderer.invoke('sparkii:selectSavePath', options),
  writeClipboard: text => ipcRenderer.invoke('sparkii:writeClipboard', text),
  readClipboard: () => ipcRenderer.invoke('sparkii:readClipboard'),
  saveImageFromUrl: url => ipcRenderer.invoke('sparkii:saveImageFromUrl', url),
  saveImageBuffer: (data, ext) => ipcRenderer.invoke('sparkii:saveImageBuffer', { data, ext }),
  saveClipboardImage: () => ipcRenderer.invoke('sparkii:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('sparkii:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('sparkii:watchPreviewFile', url),
  watchDirectory: dir => ipcRenderer.invoke('sparkii:watchDirectory', dir),
  stopPreviewFileWatch: id => ipcRenderer.invoke('sparkii:stopPreviewFileWatch', id),
  setActiveWork: payload => ipcRenderer.send('sparkii:active-work', payload),
  setTitleBarTheme: payload => ipcRenderer.send('sparkii:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('sparkii:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('sparkii:translucency', payload),
  setKeepAwake: on => ipcRenderer.send('sparkii:keep-awake', on),
  setPreviewShortcutActive: active => ipcRenderer.send('sparkii:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('sparkii:openExternal', url),
  openPreviewInBrowser: url => ipcRenderer.invoke('sparkii:openPreviewInBrowser', url),
  fetchLinkTitle: url => ipcRenderer.invoke('sparkii:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('sparkii:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('sparkii:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('sparkii:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('sparkii:setting:defaultProjectDir:pick')
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('sparkii:zoom:get'),
    setPercent: percent => ipcRenderer.send('sparkii:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('sparkii:zoom:changed', listener)

      return () => ipcRenderer.removeListener('sparkii:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('sparkii:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('sparkii:logs:recent'),
  // Fire-and-forget: persists a renderer error-boundary catch (with component
  // stack) to desktop.log so crashes survive the window (#79428).
  reportRendererError: report => ipcRenderer.send('sparkii:logs:renderer-error', report),
  readDir: dirPath => ipcRenderer.invoke('sparkii:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('sparkii:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('sparkii:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('sparkii:fs:openDir', dirPath),
  desktopPluginsRoot: () => ipcRenderer.invoke('sparkii:fs:desktopPluginsRoot'),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('sparkii:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('sparkii:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('sparkii:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('sparkii:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('sparkii:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('sparkii:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('sparkii:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('sparkii:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('sparkii:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('sparkii:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('sparkii:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('sparkii:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('sparkii:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('sparkii:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('sparkii:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('sparkii:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('sparkii:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('sparkii:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('sparkii:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('sparkii:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('sparkii:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('sparkii:git:review:shipInfo', repoPath),
      prList: (repoPath, branches, numbers) =>
        ipcRenderer.invoke('sparkii:git:review:prList', repoPath, branches, numbers),
      createPr: repoPath => ipcRenderer.invoke('sparkii:git:review:createPr', repoPath)
    }
  },
  terminal: {
    cwd: id => ipcRenderer.invoke('sparkii:terminal:cwd', id),
    dispose: id => ipcRenderer.invoke('sparkii:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('sparkii:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('sparkii:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('sparkii:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `sparkii:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `sparkii:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('sparkii:close-preview-requested', listener)

    return () => ipcRenderer.removeListener('sparkii:close-preview-requested', listener)
  },
  onOpenFolderRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('sparkii:open-folder-requested', listener)

    return () => ipcRenderer.removeListener('sparkii:open-folder-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('sparkii:open-updates', listener)

    return () => ipcRenderer.removeListener('sparkii:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('sparkii:deep-link', listener)

    return () => ipcRenderer.removeListener('sparkii:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('sparkii:deep-link-ready'),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('sparkii:window-state-changed', listener)

    return () => ipcRenderer.removeListener('sparkii:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('sparkii:focus-session', listener)

    return () => ipcRenderer.removeListener('sparkii:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('sparkii:notification-action', listener)

    return () => ipcRenderer.removeListener('sparkii:notification-action', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('sparkii:preview-file-changed', listener)

    return () => ipcRenderer.removeListener('sparkii:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('sparkii:backend-exit', listener)

    return () => ipcRenderer.removeListener('sparkii:backend-exit', listener)
  },
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('sparkii:connection:applied', listener)

    return () => ipcRenderer.removeListener('sparkii:connection:applied', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('sparkii:power-resume', listener)

    return () => ipcRenderer.removeListener('sparkii:power-resume', listener)
  },
  // AC ↔ battery transitions; renderers slow their backstop polls on battery.
  getOnBattery: () => ipcRenderer.invoke('sparkii:power-battery:get'),
  onBatteryChanged: callback => {
    const listener = (_event, onBattery) => callback(Boolean(onBattery))
    ipcRenderer.on('sparkii:power-battery', listener)

    return () => ipcRenderer.removeListener('sparkii:power-battery', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('sparkii:boot-progress', listener)

    return () => ipcRenderer.removeListener('sparkii:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('sparkii:bootstrap:get'),
  continueBootstrapLocal: () => ipcRenderer.invoke('sparkii:bootstrap:continue-local'),
  resetBootstrap: () => ipcRenderer.invoke('sparkii:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('sparkii:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('sparkii:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('sparkii:bootstrap:event', listener)

    return () => ipcRenderer.removeListener('sparkii:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('sparkii:version'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('sparkii:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('sparkii:uninstall:summary'),
    run: mode => ipcRenderer.invoke('sparkii:uninstall:run', { mode })
  },
  updates: {
    check: () => ipcRenderer.invoke('sparkii:updates:check'),
    apply: opts => ipcRenderer.invoke('sparkii:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('sparkii:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('sparkii:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('sparkii:updates:progress', listener)

      return () => ipcRenderer.removeListener('sparkii:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('sparkii:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('sparkii:vscode-theme:search', query)
  },
  // Find-in-page (Ctrl/Cmd+F): delegates to Electron's
  // webContents.findInPage on the IPC sender's window so a Cmd+F pressed
  // in a secondary session window searches THAT window, not the primary.
  // `onFoundInPage` returns the unsubscribe fn; the renderer wires it via
  // `initFindInPageListener` in store/find-in-page.ts and tears it down
  // when the FindBar unmounts.
  findInPage: (query, options) => ipcRenderer.invoke('sparkii:find-in-page', query, options),
  stopFindInPage: () => ipcRenderer.invoke('sparkii:stop-find-in-page'),
  onFoundInPage: callback => {
    const listener = (_event, result) => callback(result)
    ipcRenderer.on('sparkii:found-in-page', listener)

    return () => ipcRenderer.removeListener('sparkii:found-in-page', listener)
  }
})
